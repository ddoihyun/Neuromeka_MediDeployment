# Fixed Constraint Config Reference

작성일: 2026-06-10

대상 파일: `configs/fixed_constraint_teleop_config.json`

## 개요

fixed constraint teleop 설정은 크게 네 종류다.

| 종류 | 섹션 |
| --- | --- |
| 입력 처리 | `tau_bias`, `tau_deadzone`, `task_wrench_sign` |
| 기구학/역변환 | `mdh`, `jacobian_eps_rad`, `jacobian_rcond`, optional `task_wrench` |
| mode 동작 | `mode_profiles`, `modes.*` |
| 제한/안전 | `timing`, `clip`, `singularity_slowdown`, `restore.*` |

controller는 config 파일 변경을 주기적으로 reload한다. 잘못된 config가 들어오면 기존 config로 fallback한다.

## 입력 처리

### `tau_bias`

정지 상태의 외력 offset을 제거한다.

```text
tau_processed[i] = tau_ext[i] - tau_bias[i]
```

현재 값은 모두 0이다. backend/UI에서 bias update 요청이 들어오면 `RobotCommunication._update_fixed_teleop_tau_bias()`가 약 2초간 sample을 평균내어 저장한다.

### `tau_deadzone`

작은 외력/노이즈를 제거한다.

현재 값:

```json
[0.02, 0.02, 0.02, 0.01, 0.01, 0.01]
```

반응성을 올리고 싶다고 deadzone부터 줄이면 drift가 늘 수 있다. 먼저 bias가 맞는지 확인한다.

### `task_wrench_sign`

축별 command 부호 보정이다. 사용자가 + 방향으로 미는데 telemetry상 command가 - 방향이면 이 값을 검토한다.

## 기구학 설정

### `mdh`

MDH 기반 FK와 numerical Jacobian 계산에 사용한다.

```json
"mdh": {
  "a_m": [...],
  "alpha_rad": [...],
  "d_m": [...],
  "theta0_rad": [...]
}
```

tool frame은 `modules/robot/robot_info.json`의 `tool_pos`에서 읽어 controller에 전달된다. `set_tool_frame()` 호출 시 controller의 tool transform도 같이 갱신된다.

### `jacobian_eps_rad`

central difference Jacobian의 joint perturbation이다. 현재 값은 `1e-5` rad다.

### `jacobian_rcond`

`np.linalg.pinv(J.T, rcond=...)`의 cutoff다. 현재 값은 `0.0001`이다.

### optional `task_wrench.damping`

코드는 `task_wrench.damping`, mode별 `task_wrench_damping`, 또는 top-level `jacobian_damping`을 지원한다. 값이 0보다 크면 SVD 기반 damped inverse를 사용한다.

현재 config에는 damping 항목이 없다. singularity 근처 wrench가 과도하면 damping을 추가하는 것이 좋다.

예:

```json
"task_wrench": {
  "damping": 0.02,
  "norm_limit": 100.0
}
```

## 공통 timing/limit

### `timing`

```json
"timing": {
  "default_loop_dt_sec": 0.1,
  "min_loop_dt_sec": 0.001,
  "max_loop_dt_sec": 0.1
}
```

`control_run`은 1 ms 주기를 목표로 하지만, controller는 전달된 `loop_dt`를 이 범위 안으로 clamp한다.

### `clip.soft_limit`

`true`이면 hard clamp 대신 `tanh` 기반 soft limit을 쓴다. 현재 `true`다.

### `clip.cumulative`

mode별 cumulative limit이 없을 때 fallback으로 쓰는 누적 command 제한이다. 현재 mode profile이 대부분 mode별 cumulative을 생성하므로 fallback 성격이다.

### `singularity_slowdown`

최종 command delta에 적용되는 singularity 감속이다.

```json
"singularity_slowdown": {
  "sigma_stop": 0.015,
  "sigma_slow": 0.08,
  "condition_slow": 60.0,
  "condition_stop": 180.0,
  "min_scale": 0.45
}
```

반응성이 낮을 때 `singularity_speed_scale`이 1보다 작으면 gain 문제가 아니라 slowdown 문제일 수 있다.

## `mode_profiles`

`mode_profiles`는 사람이 튜닝하기 쉬운 값이고, controller가 mode config의 `rate`, `cumulative`, `tangent_velocity_limit`, gain 관련 설정으로 확장한다.

현재 값:

| mode | gain | velocity limit | cumulative limit | filter time constant |
| --- | ---: | ---: | ---: | ---: |
| fixed point | 0.03 | 12 deg/s | 20 deg | 0.04 s |
| fixed line | 1.0 | 55 mm/s | 70 mm | 0.035 s |
| fixed plane | 1.35 | 85 mm/s | 85 mm | 0.04 s |

## Fixed Point 설정

현재 fixed point는 `rcm_point`다.

| 항목 | 현재 값 | 의미 |
| --- | --- | --- |
| `axis_mask` | `[0, 0, 0, 1, 1, 0]` | 사용자 입력으로 translation과 roll 차단 |
| `constraint.type` | `rcm_point` | TCP 고정이 아니라 tool shaft RCM 유지 |
| `tool_axis_frame` | `tcp` | tool axis가 TCP frame 기준 |
| `tool_axis` | `[0, 0, 1]` | TCP +Z를 shaft axis로 사용 |
| `rotation_input.source` | `joint_admittance` | fixed point 회전을 task wrench 대신 `J * tau_ext` 기반으로 생성 |

restore:

| 항목 | 현재 값 | 의미 |
| --- | ---: | --- |
| `kp` | `[0.8, 0.8, 0.8]` | RCM error P gain |
| `kd` | `[0.03, 0.03, 0.03]` | RCM error D gain |
| `deadband_mm` | 0.5 | 이 안에서는 restore target 0 |
| `max_velocity_mm_s` | 15 | base restore velocity norm limit |
| `command_velocity_limit_mm_s` | 8 | mode profile이 translation rate로 사용 |
| `command_cumulative_limit_mm` | 12 | mode profile이 translation cumulative로 사용 |
| `max_error_mm` | 50 | 초과 시 자동 restore 차단 |
| `blend_time_constant_sec` | 0.1 | restore velocity smoothing |

## Fixed Line 설정

| 항목 | 현재 값 | 의미 |
| --- | --- | --- |
| `axis_mask` | `[0, 0, 1, 0, 0, 0]` | restore disabled fallback에서 Z translation만 허용 |
| `constraint.type` | `line` | line constraint |
| `axis_frame` | `tcp` | 진입 시 TCP frame의 line axis를 base로 저장 |
| `line_axis` | `[0, 0, 1]` | entry TCP +Z 방향 line |
| `force_to_line.enabled` | `true` | 특정 force direction을 line velocity로 변환 |
| `force_to_line.force_direction` | `[0.3073, 0.1537, 0.9391]` | line command를 만들 때 참조하는 힘 방향 |

restore는 수직 error를 줄인다. 현재 `kp=0.6`, `kd=0.02`, `max_velocity_mm_s=20`, `deadband_mm=0.5`, `max_error_mm=60`, `blend_time_constant_sec=0.08`이다.

## Fixed Plane 설정

| 항목 | 현재 값 | 의미 |
| --- | --- | --- |
| `axis_mask` | `[1, 1, 0, 0, 0, 0]` | restore disabled fallback에서 XY translation만 허용 |
| `constraint.type` | `plane` | plane constraint |
| `normal_frame` | `tcp` | 진입 시 TCP frame의 normal을 base로 저장 |
| `plane_normal` | `[0, 0, 1]` | entry TCP +Z 방향 normal |

restore는 normal error를 줄인다. 현재 `kp=0.5`, `kd=0.02`, `max_velocity_mm_s=20`, `deadband_mm=0.5`, `max_error_mm=60`, `blend_time_constant_sec=0.08`이다.

## 반응성 관련 우선순위

반응성을 올릴 때 보는 순서는 다음이 좋다.

1. `tau_bias`가 맞는가.
2. `tau_deadzone` 때문에 `tau_processed`가 0으로 죽지 않는가.
3. mode profile `gain`이 너무 낮지 않은가.
4. `tangent_velocity_limit` 또는 mode `rate`에 막히지 않는가.
5. `filter_time_constant_sec` 또는 `restore.blend_time_constant_sec`가 너무 크지 않은가.
6. `singularity_slowdown`이 command를 줄이고 있지 않은가.
7. 실제 로봇이 늦으면 `SetTeleOpParams(smooth_factor, cutoff_freq, error_gain)` 쪽도 확인한다.

## Config 변경 시 주의

1. `axis_frame`, `normal_frame`, `tool_axis_frame`은 `tcp` 또는 `base`만 사용한다.
2. `line_axis`, `plane_normal`, `tool_axis`는 non-zero vector여야 한다. zero에 가까우면 기본 `[0, 0, 1]`로 normalize된다.
3. restore `max_error_mm`를 너무 크게 잡으면 큰 오차에서 로봇이 예상보다 적극적으로 복원할 수 있다.
4. `shadow_mode=true`는 restore 계산 telemetry만 보고 실제 restore command는 0으로 만든다. hardware 전 검증에 유용하다.
5. fixed point에서 TCP 고정이 목적이면 `rcm_point`가 아니라 `tcp_point`로 명시해야 한다.
