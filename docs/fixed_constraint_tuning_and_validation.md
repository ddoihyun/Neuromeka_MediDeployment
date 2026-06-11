# Fixed Constraint Tuning and Validation

작성일: 2026-06-10

## 목적

fixed constraint teleop의 반응성, 부드러움, 좌표계 일관성을 검증하고 튜닝하는 절차를 정리한다.

## 튜닝 전 안전 조건

hardware에서 gain을 올리기 전에 다음 상태를 맞춘다.

1. emergency stop과 collision/violation handling이 정상인지 확인한다.
2. robot이 `TELE_OP`로 들어가고 나오는지 확인한다.
3. `tau_bias`를 정지 상태에서 갱신한다.
4. `save_control_trace_log=true` 상태에서 짧은 trace를 남긴다.
5. `restore.shadow_mode=true`로 방향을 먼저 확인한 뒤 실제 restore를 켠다.
6. 낮은 velocity/cumulative limit에서 시작한다.

## 병목 찾는 순서

반응성이 낮을 때 gain부터 올리지 말고 telemetry를 순서대로 본다.

| 단계 | 볼 필드 | 해석 |
| --- | --- | --- |
| 1 | `tau_ext` | 센서 입력이 실제로 들어오는가 |
| 2 | `tau_processed` | bias/deadzone 후 입력이 살아 있는가 |
| 3 | `task_wrench` | Jacobian inverse가 이상하지 않은가 |
| 4 | `raw_velocity` | gain/mapping 결과가 충분한가 |
| 5 | `tangent_velocity` | projection 후 허용 방향 성분이 살아 있는가 |
| 6 | `restore_limited_velocity` | restore가 너무 느리게 blend/limit되는가 |
| 7 | `limited_velocity` | rate/filter가 command를 많이 줄이는가 |
| 8 | `singularity_speed_scale` | singularity slowdown이 걸렸는가 |
| 9 | 실제 pose 변화 | SDK TeleOp smoothing 또는 robot side limit이 병목인가 |

## 좌표계 검증

### 기본 확인

1. fixed mode 진입 직후 `reference_valid=true`인지 확인한다.
2. `pose_source`가 기대와 맞는지 확인한다.
3. `constraint_frame`이 config와 맞는지 확인한다.
4. 가만히 있을 때 `constraint_error_norm`이 deadband 근처에서 유지되는지 확인한다.

### 부호 확인

작은 힘만 주고 다음을 확인한다.

| 입력 | 기대 |
| --- | --- |
| fixed point u/v 방향 회전 입력 | `raw_velocity[3:5]`, `tangent_velocity[3:5]`가 기대 부호 |
| fixed line line axis 방향 입력 | line 방향 `tangent_velocity[0:3]`만 남음 |
| fixed plane plane 내부 입력 | normal 성분 제거 후 plane 내부 `tangent_velocity[0:3]`만 남음 |
| constraint error를 일부러 만들기 | `restore_velocity`가 error를 줄이는 방향 |

`last_command`는 기대와 맞는데 실제 pose 변화가 다르면 `MoveTeleLTCP` command frame 가정 또는 SDK TeleOp parameter를 확인한다.

## Fixed Point 튜닝

현재 fixed point는 RCM point 유지 + u/v pivot rotation에 가깝다.

현재 profile:

```json
"fixed_point": {
  "gain": 0.03,
  "velocity_limit_deg_s": 12.0,
  "cumulative_limit_deg": 20.0,
  "filter_time_constant_sec": 0.04
}
```

### 회전 반응성 올리기

권장 순서:

```text
gain: 0.03 -> 0.04 -> 0.05
velocity_limit_deg_s: 12 -> 16 -> 20
filter_time_constant_sec: 0.04 -> 0.025 -> 0.015
```

튜닝 중 진동이 보이면:

```text
gain을 한 단계 낮춤
filter_time_constant_sec를 한 단계 높임
singularity_speed_scale 확인
```

### RCM restore 반응성 올리기

현재 restore:

```json
"kp": [0.8, 0.8, 0.8],
"kd": [0.03, 0.03, 0.03],
"deadband_mm": 0.5,
"max_velocity_mm_s": 15.0,
"command_velocity_limit_mm_s": 8.0,
"blend_time_constant_sec": 0.1
```

권장 순서:

```text
blend_time_constant_sec: 0.10 -> 0.06 -> 0.04
command_velocity_limit_mm_s: 8 -> 12
max_velocity_mm_s: 15 -> 20
kp: 0.8 -> 1.0
kd: 0.03 -> 0.05 if oscillation appears
```

`constraint_error_norm`이 deadband 안으로 들어가지 못하고 천천히 남으면 `kp`, `command_velocity_limit_mm_s`, `max_velocity_mm_s`를 본다. error가 줄다가 지나치면 `kd`와 blend time을 본다.

## Fixed Line 튜닝

현재 profile:

```json
"fixed_line": {
  "gain": 1.0,
  "velocity_limit_mm_s": 55.0,
  "cumulative_limit_mm": 70.0,
  "filter_time_constant_sec": 0.035
}
```

확인 순서:

1. line axis 방향 입력에서 `tangent_velocity`가 충분히 큰지 확인한다.
2. 수직 입력에서 tangent 성분이 거의 0인지 확인한다.
3. `force_to_line.force_direction`이 실제 힘 방향과 맞는지 확인한다.
4. line 밖 drift를 만들고 `constraint_error_norm`이 감소하는지 본다.

반응성을 올리는 순서:

```text
gain: 1.0 -> 1.2 -> 1.5
velocity_limit_mm_s: 55 -> 70
filter_time_constant_sec: 0.035 -> 0.025
restore.blend_time_constant_sec: 0.08 -> 0.05
```

## Fixed Plane 튜닝

현재 profile:

```json
"fixed_plane": {
  "gain": 1.35,
  "velocity_limit_mm_s": 85.0,
  "cumulative_limit_mm": 85.0,
  "filter_time_constant_sec": 0.04
}
```

확인 순서:

1. plane 내부 힘에서 `tangent_velocity`가 자연스럽게 나온다.
2. normal 방향 힘은 사용자 입력에서 제거된다.
3. normal error가 생기면 `restore_velocity`가 plane으로 되돌린다.
4. `constraint_error_norm`이 deadband 안으로 수렴한다.

반응성을 올리는 순서:

```text
gain: 1.35 -> 1.6
velocity_limit_mm_s: 85 -> 100
filter_time_constant_sec: 0.04 -> 0.025
restore.kp: 0.5 -> 0.7
```

plane mode는 line/point보다 사용자가 체감하는 translation 속도가 커질 수 있으므로 cumulative limit도 같이 확인한다.

## tau bias/deadzone 절차

1. 로봇이 정지하고 외력을 받지 않는 자세로 둔다.
2. tau bias update를 요청한다.
3. 약 2초간 sample 평균이 `tau_bias`로 저장된다.
4. 손을 떼고 `tau_processed`가 거의 0인지 확인한다.
5. 작은 의도 입력을 줬을 때 deadzone에 먹히지 않는지 확인한다.

deadzone은 현재 낮은 편이다. 노이즈가 보이면 deadzone을 먼저 올리고, 반응성이 부족하면 gain/filter/limit을 조정한다.

## Trace 분석

`save_control_trace_log=true`이면 `LOG` 아래 CSV trace가 남는다.

우선 확인할 column:

| column | 용도 |
| --- | --- |
| `record_type` | `fixed_enter`, `fixed_sample`, `fixed_skip`, `fixed_exit` 구분 |
| `skip_reason`, `last_reason` | command가 안 나간 이유 |
| `fixed_mode_name` | mode 확인 |
| `pose_source`, `constraint_frame` | 좌표계 확인 |
| `reference_valid` | 기준 capture 확인 |
| `constraint_error_norm` | constraint 유지 성능 |
| `raw_velocity_*` | 입력 mapping |
| `tangent_velocity_*` | projection 결과 |
| `restore_velocity_*` | restore 방향 |
| `limited_velocity_*` | 최종 제한 후 속도 |
| `singularity_speed_scale` | singularity slowdown |
| `sent_command_*` | 실제 보낸 command |

## Simulated tau API

backend는 test용 API를 제공한다.

```http
POST /api/robot/simulated-tau
Content-Type: application/json

{
  "enabled": true,
  "tau_ext": [0, 0, 0, 0, 0, 0]
}
```

enabled이면 blackboard의 `robot/simulated_tau/tau_ext`와 `robot/state/tau_ext`가 갱신되고, control loop에서 실제 `control_state["tau_ext"]`를 simulated 값으로 대체한다.

비활성화:

```json
{
  "enabled": false,
  "tau_ext": [0, 0, 0, 0, 0, 0]
}
```

## Last reason 해석

| reason | 의미 | 조치 |
| --- | --- | --- |
| `inactive` | controller 비활성 | FSM/mode 확인 |
| `missing_q` | control_state에 q 없음 | RTDE control state 확인 |
| `jacobian_failed` | FK/Jacobian/inverse 실패 | q, MDH, damping 확인 |
| `missing_pose` | p도 FK도 pose 산출 실패 | control_state, q 확인 |
| `missing_reference` | reference capture 실패 | pose source 확인 |
| `constraint_error_too_large` | restore max error 초과 | mode 재진입 또는 수동 복귀 |
| `zero_command` | command가 min threshold 이하 | deadzone/gain/force 확인 |
| `non_finite_command` | NaN/Inf command | config와 input 데이터 확인 |

## Hardware 검증 시나리오

### 공통

1. low gain/low limit으로 시작한다.
2. fixed mode 진입 직후 reference가 잡히는지 확인한다.
3. 각 허용 방향과 금지 방향 입력을 분리해 준다.
4. trace에서 command 방향과 실제 pose 방향을 비교한다.
5. singularity 근처 자세는 피해서 기본 방향성을 먼저 맞춘다.

### Fixed point

1. 진입 직후 `reference_rcm_point`가 저장된다.
2. u/v 방향 입력에서 pivot rotation이 생긴다.
3. x/y/z 사용자 입력은 `tangent_velocity`에서 제거된다.
4. shaft가 RCM에서 벗어나면 restore가 error를 줄인다.
5. `constraint_error_norm`이 deadband 또는 허용 오차 안에 머문다.

### Fixed line

1. line 방향 입력은 살아남는다.
2. line 수직 입력은 사용자 성분에서 제거된다.
3. line 밖 drift는 restore로 줄어든다.
4. line axis를 바꿔도 같은 수식으로 동작한다.

### Fixed plane

1. plane 내부 입력은 살아남는다.
2. normal 입력은 사용자 성분에서 제거된다.
3. plane 밖 drift는 restore로 줄어든다.
4. normal axis를 바꿔도 같은 수식으로 동작한다.
