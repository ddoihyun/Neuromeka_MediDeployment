# Fixed Point RCM tau_ext 입력 개선안

## 목표

fixed point 모드에서 관절 `tau_ext`를 이용해 RCM 모션을 만들 때, 사용자가 힘을 주는 방향과 현재 제어 축이 정확히 맞지 않아도 부드럽게 움직이도록 한다. 핵심은 입력 축을 완벽히 맞추는 것이 아니라, 관절 외력에서 사용자의 의도를 러프하게 추정하고 RCM 제약은 별도의 기하 feed-forward와 복원 제어로 안정적으로 유지하는 것이다.

## 현재 구조에서 생기는 뻑뻑함

현재 fixed point 흐름은 대략 다음과 같다.

1. `tau_ext`에서 bias/deadzone을 뺀다.
2. Jacobian으로 task wrench 또는 joint admittance twist를 만든다.
3. fixed point에서는 translation을 0으로 막고, 회전축 일부만 `axis_mask`로 통과시킨다.
4. RCM 오차는 `restore` PD로 다시 끌어온다.

이 구조는 축이 잘 맞으면 동작하지만, 실제 손으로 미는 힘은 관절 축, 마찰, 자세, TCP 축 오차에 따라 섞여 들어온다. 그래서 의도가 pitch/roll이어도 변환 후 값이 허용 축 밖으로 새면 거의 버려지고, RCM translation도 먼저 만들어지는 것이 아니라 오차가 생긴 뒤 restore가 따라가는 느낌이 된다. 체감상 "축이 맞을 때만 움직이는" 상태가 된다.

## 권장 방향

입력 처리와 RCM 제약 생성을 분리한다.

1. `tau_ext`는 정확한 물리 wrench로 믿기보다 사용자의 2D 회전 의도 신호로 본다.
2. fixed point RCM은 회전 명령에 맞는 TCP translation을 feed-forward로 같이 만든다.
3. RCM 오차는 막는 제약이 아니라 부드럽게 줄이는 elastic constraint로 처리한다.
4. 축 신뢰도가 낮을 때는 보정된 rough mapping 또는 직전 유효 방향을 짧게 유지해 dead feeling을 줄인다.

## 1. Soft joint intent layer 추가

`rotation_input.source`에 `hybrid_joint_intent` 같은 모드를 추가한다. 기존 `joint_admittance`처럼 `jacobian @ tau_ext`를 바로 쓰되, 허용 축에 딱 맞지 않는 성분을 즉시 버리지 않는다.

처리 순서 예시:

```python
tau = soft_deadzone(tau_ext - tau_bias)
qdot_intent = joint_gain * tau
twist_tcp = jacobian @ qdot_intent
omega_raw = twist_tcp[3:6]  # TCP angular intent

tool_axis = [0, 0, 1]
omega_perp = omega_raw - dot(omega_raw, tool_axis) * tool_axis
confidence = norm(omega_perp) / (norm(omega_raw) + eps)
```

`confidence`가 충분하면 `omega_perp`를 사용한다. 낮으면 축이 틀어진 입력으로 보고, 아래의 calibrated basis 또는 직전 방향 hold를 섞는다.

```python
if confidence < confidence_min and tau_norm > intent_threshold:
    omega_basis = calibrated_tau_to_omega_xy(tau)
    omega_xy = blend(omega_perp, omega_basis, fallback_blend)
else:
    omega_xy = omega_perp
```

이 방식은 축이 완전히 맞지 않아도 "대충 이쪽으로 돌리려는구나"를 받아준다.

## 2. Rough tau basis calibration

Jacobian 기반 변환만으로는 관절 외력 축 불일치를 다 흡수하기 어렵다. fixed point 전용으로 `tau_ext -> RCM pitch/roll` 2D basis를 둔다.

간단한 calibration 절차:

1. 사용자가 fixed point 상태에서 위/아래/좌/우로 가볍게 힘을 준다.
2. 각 방향의 `tau_processed` 평균을 기록한다.
3. 서로 반대 방향을 빼서 pitch, roll basis를 만든 뒤 정규화한다.

사용 시:

```python
pitch_intent = dot(tau_processed, tau_basis_pitch)
roll_intent = dot(tau_processed, tau_basis_roll)
omega_tcp = [
    roll_gain * roll_intent,
    pitch_gain * pitch_intent,
    0.0,
]
```

초기에는 basis mapping을 fallback으로만 쓰고, 축 신뢰도가 낮을 때만 섞는 것이 안전하다.

설정 예시:

```json
"rotation_input": {
  "enabled": true,
  "source": "hybrid_joint_intent",
  "joint_admittance_gain": 0.03,
  "joint_gain": [1.0, 1.0, 1.0, 0.6, 0.6, 0.4],
  "confidence_min": 0.35,
  "fallback_blend": 0.7,
  "last_direction_hold_sec": 0.15,
  "calibrated_basis_enabled": true,
  "tau_basis_pitch": [0, 0, 0, 0, 0, 0],
  "tau_basis_roll": [0, 0, 0, 0, 0, 0],
  "pitch_gain": 1.0,
  "roll_gain": 1.0
}
```

## 3. RCM tangent feed-forward 추가

현재 fixed point에서는 사용자의 tangent translation을 0으로 만들고, RCM 오차를 restore가 나중에 보정한다. 이러면 회전 입력이 들어와도 처음에는 제약이 따라오는 느낌이 강하다.

회전 속도 `omega_tcp`가 정해졌다면, RCM 기준으로 TCP가 같이 움직여야 할 translation을 직접 만든다.

```python
omega_base = R_tcp_to_base @ deg_to_rad(omega_tcp)
lever_mm = tcp_position_mm - reference_rcm_point_mm
v_base_mm_s = cross(omega_base, lever_mm)
v_tcp_mm_s = R_base_to_tcp @ v_base_mm_s
```

그 다음 command velocity를 다음처럼 만든다.

```python
command_velocity[0:3] = rcm_feedforward_gain * v_tcp_mm_s
command_velocity[3:6] = omega_tcp
command_velocity += restore_velocity
```

주의: 실제 `MoveTeleLTCP`의 부호 convention에 따라 `cross(omega, lever)` 부호는 반대일 수 있다. trace에서 회전 직후 `constraint_error_norm`이 커지면 부호를 뒤집어 확인한다.

설정 예시:

```json
"rcm_feedforward": {
  "enabled": true,
  "gain": 1.0,
  "max_velocity_mm_s": 25.0,
  "blend_time_constant_sec": 0.05
}
```

이 feed-forward를 넣으면 restore는 주 제어가 아니라 잔여 오차 보정 역할이 된다. 축이 조금 틀어져도 움직임이 먼저 자연스럽게 만들어진다.

## 4. Hard block 대신 soft constraint scale

현재 `max_error_mm`을 넘으면 명령을 막는 방식은 안전하지만, 사용자 입장에서는 갑자기 뻑뻑해진다. fixed point에서는 hard block 전에 user angular velocity를 점진적으로 줄이고 restore는 계속 살리는 방식이 좋다.

예시:

```python
scale = 1.0 - smoothstep(soft_error_mm, hard_error_mm, error_norm)
user_velocity *= scale
restore_velocity = restore_velocity  # 줄이지 않음
```

권장 기본값:

```json
"restore": {
  "soft_error_mm": 8.0,
  "hard_error_mm": 40.0,
  "deadband_mm": 0.8,
  "max_velocity_mm_s": 20.0
}
```

`hard_error_mm` 이상에서는 사용자 입력은 막고 restore만 허용한다. 이렇게 하면 RCM이 크게 틀어지는 상황은 막으면서, 작은 오차에서는 손맛이 갑자기 끊기지 않는다.

## 5. Stick-slip 완화

축 불일치가 있을 때 hard deadzone과 sign-change reset은 작은 입력을 더 뻑뻑하게 만든다.

개선안:

1. hard deadzone 대신 soft deadzone을 쓴다.
2. fixed point에서는 `reset_on_sign_change`를 끄거나, 완전 reset 대신 짧은 slew limit으로 바꾼다.
3. tau 입력과 최종 angular velocity에 각각 low-pass filter를 둔다.
4. `tau_norm`이 threshold를 넘으면 최소 angular speed를 아주 작게 보장한다.

예시:

```python
def soft_deadzone(x, dz, width):
    mag = abs(x)
    if mag <= dz:
        return 0.0
    t = clamp((mag - dz) / width, 0.0, 1.0)
    eased = t * t * (3.0 - 2.0 * t)
    return sign(x) * eased * (mag - dz)
```

이 처리는 "어느 순간 갑자기 움직임"보다 "조금씩 살아남"에 가깝게 만든다.

## 6. 구현 순서

1. Trace 필드 추가
   - `omega_raw`
   - `omega_projected`
   - `axis_confidence`
   - `omega_basis`
   - `rcm_feedforward_velocity`
   - `constraint_scale`

2. RCM tangent feed-forward 먼저 구현
   - fixed point + `rcm_point`에서만 활성화한다.
   - 기존 restore는 그대로 둔다.
   - 부호와 velocity limit만 trace로 검증한다.

3. Soft joint intent layer 구현
   - 기존 `joint_admittance`를 유지하고 새 source를 추가한다.
   - `confidence_min` 이하에서만 fallback을 섞는다.

4. Rough tau basis calibration 추가
   - 처음에는 config 수동 입력 또는 간단한 script로 평균값을 저장한다.
   - 나중에 UI 버튼으로 "좌/우/상/하 basis 기록"을 붙인다.

5. Soft constraint scale 추가
   - `max_error_mm` hard block은 마지막 안전장치로 남긴다.
   - hard block 전에는 user velocity만 서서히 줄인다.

## MVP 추천

가장 먼저 넣을 최소 변경은 다음 두 가지다.

1. fixed point RCM feed-forward translation
2. `hybrid_joint_intent` 입력에서 confidence가 낮을 때 calibrated tau basis fallback

이 두 가지가 들어가면 축을 정확히 밀어야만 움직이는 느낌이 크게 줄어든다. 이후 deadzone/filter/soft constraint는 손맛 튜닝으로 다듬으면 된다.

## 검증 기준

1. `tau_ext` 방향이 의도 축과 20~30% 정도 어긋나도 fixed point 회전 명령이 생성된다.
2. RCM 회전 중 `constraint_error_norm`이 급격히 증가하지 않고, 정상 상태에서 2~3 mm 안쪽으로 수렴한다.
3. 입력을 놓으면 drift 없이 멈춘다.
4. 방향 전환 시 command가 끊기지 않고 100~200 ms 안에 부드럽게 반전된다.
5. `constraint_error_norm`이 hard limit에 가까워질수록 사용자 입력은 줄고 restore만 살아난다.

