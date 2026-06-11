# Fixed Constraint Teleop Architecture

작성일: 2026-06-10

## 목적

이 문서는 fixed point/line/plane teleop의 최신 코드 구조를 설명한다. 대상 구현은 `FixedConstraintTeleopController`와 `RobotCommunication.control_cockpit_tele()` 경로다.

## 제어 목표

사용자는 cockpit 또는 voice mode로 fixed constraint mode에 진입한다. controller는 로봇에서 들어오는 `tau_ext`를 사용자의 조작 의도로 보고, 모드별 constraint를 깨지 않는 방향의 command와 constraint error를 줄이는 restore command를 합성한다.

최종 command는 SDK `MoveTeleLTCP(tpos=[x, y, z, u, v, w])`로 전송된다. 현재 구현은 joint velocity QP가 아니라 TCP-frame 누적 command를 보내는 구조다.

## 전체 데이터 흐름

```text
RTDE GetControlState()
  -> latest_control_state(q, qdot, p, pdot, tau, tau_ext)
  -> FixedConstraintTeleopController.update()
  -> cumulative MoveTeleLTCP command
  -> singularity slowdown
  -> control_client.MoveTeleLTCP()
  -> blackboard fixed_constraint_teleop/snapshot
  -> backend /api/robot/telemetry
  -> frontend telemetry + CSV trace
```

주요 실행 위치:

| 단계 | 코드 |
| --- | --- |
| control state 수집 | `modules/robot/robot_control.py`, `get_DCP_robot_data()` |
| fixed mode 판별 | `RobotCommunication._fixed_constraint_state_mode()` |
| controller update | `RobotCommunication.control_cockpit_tele()` |
| command 생성 | `FixedConstraintTeleopController.update()` |
| 실제 전송 | `RobotCommunication.move_tele()` |
| telemetry publish | `_publish_fixed_teleop_snapshot()` |

## FSM 진입 경로

### Cockpit 기반 fixed mode

`PREP` 또는 `IDLE` 상태에서 cockpit이 눌리고 `control/desired_mode`가 fixed mode면 fixed FSM state로 전이한다.

| desired mode | FSM event | FSM state | controller mode |
| --- | --- | --- | --- |
| `ControlMode.FIXED_POINT` | `FIXED_POINT_CONTROL` | `FIXED_POINT_CONTROL` | `fixed_point` |
| `ControlMode.FIXED_LINE` | `FIXED_LINE_CONTROL` | `FIXED_LINE_CONTROL` | `fixed_line` |
| `ControlMode.FIXED_PLANE` | `FIXED_PLANE_CONTROL` | `FIXED_PLANE_CONTROL` | `fixed_plane` |

`fixed_constraint_teleop_strategy.prepare()`는 다음을 수행한다.

```text
robot/state/fsm = fixed state
control/mode = fixed mode
fixed_constraint_teleop/active_mode = fixed mode
fixed_constraint_teleop/reset = True
teleop/enable = True if robot is not TELE_OP
```

종료 조건:

| 조건 | 동작 |
| --- | --- |
| cockpit release | `IDLE`로 복귀 |
| `control/desired_mode` 변경 | `IDLE`로 복귀 |
| error | `ERROR` |
| TeleOP start timeout | `IDLE`로 복귀 |

종료 시 `fixed_constraint_teleop/reset=True`, `control/mode=NONE`, 필요 시 `teleop/disable=True`를 설정한다.

### Voice 기반 fixed mode

voice mode도 fixed mode 전용 strategy를 갖는다. `VOICE_FIXED_POINT_CONTROL`, `VOICE_FIXED_LINE_CONTROL`, `VOICE_FIXED_PLANE_CONTROL` 상태에서 같은 controller를 사용한다. voice fixed strategy는 cockpit release 대신 voice event와 manual idle event를 소비하면서 fixed mode를 유지한다.

## Controller pipeline

`FixedConstraintTeleopController.update()`의 현재 흐름은 다음과 같다.

```text
1. loop_dt sanitize
2. tau_ext -> raw_delta
3. restore enabled면:
   - current TCP pose 획득
   - reference lazy capture
   - raw_delta -> user_velocity
   - tangent projection
   - constraint error 계산
   - restore velocity 계산
   - tangent + restore 합성
4. restore disabled면 legacy projection 적용
5. rate limit + soft limit + velocity filter
6. cumulative limit
7. command zero check
8. command return
```

### tau_ext에서 raw velocity까지

```text
tau_processed[i] = tau_ext[i] - tau_bias[i]
abs(tau_processed[i]) < tau_deadzone[i] => 0
```

그 다음 `q`를 radian으로 변환하고, MDH FK 기반 numerical Jacobian을 계산한다.

```text
tau = J_tcp(q)^T * wrench_tcp
wrench_tcp ~= pinv(J_tcp(q)^T) * tau
```

현재 Jacobian은 base frame에서 central difference로 계산한 뒤 TCP frame으로 회전 변환한다. 이는 `MoveTeleLTCP`가 TCP-frame delta를 받는다는 가정 때문이다.

### mode-specific velocity mapping

기본은 `task_wrench * gain * sign`이다. 다만 일부 mode는 별도 mapping을 사용한다.

| mode | mapping |
| --- | --- |
| fixed point | `rotation_input.source = joint_admittance`이면 `jacobian @ tau_ext`의 angular component를 사용 |
| fixed line | `force_to_line.enabled = true`이면 `force_direction` 방향 힘을 line velocity로 변환 |
| fixed plane | task wrench에 mode profile gain 적용 |

## Restore path

restore가 켜져 있으면 controller는 단순 mask를 적용하지 않는다. 사용자 입력은 tangent 방향으로 제한하고, constraint error를 줄이는 restore command는 따로 살아남는다.

```text
user_velocity = raw_delta / dt
tangent_velocity = project_to_constraint_tangent(user_velocity)
error = current_geometry - reference_geometry
restore_base = -Kp * error - Kd * d(error)/dt
restore_tcp = R_tcp.T * restore_base
command_velocity = tangent_velocity + restore_tcp
```

restore disabled일 때만 `_apply_constraint()`가 command 전체에 hard projection을 건다. restore enabled일 때는 cumulative command에 다시 `_apply_constraint()`를 적용하지 않아 restore translation이 제거되지 않는다.

## Limit and safety

| 제한 | 위치 | 의미 |
| --- | --- | --- |
| `tau_deadzone` | raw input | 작은 외력/노이즈 제거 |
| `task_wrench_damping` | wrench inverse | singular 근처 inverse 완화 |
| `task_wrench_norm_limit` | wrench output | 과도한 wrench 제한 |
| `tangent_velocity_limit` | tangent command | 사용자 입력 속도 제한 |
| `restore.max_velocity_mm_s` | restore base velocity | 복원 속도 제한 |
| `restore.max_error_mm` | restore safety gate | error가 너무 크면 자동복원 차단 |
| mode `rate` | per-cycle delta | tick당 변화량 제한 |
| mode `cumulative` | cumulative command | 누적 command 제한 |
| `singularity_slowdown` | RobotCommunication | 최종 command delta scale |

## Telemetry and trace

controller snapshot은 blackboard의 `fixed_constraint_teleop/snapshot`에 기록된다. backend는 `/api/robot/telemetry`에서 이 snapshot을 그대로 포함한다.

주요 telemetry:

| 필드 | 의미 |
| --- | --- |
| `active`, `state`, `mode_name` | controller 상태 |
| `last_reason` | command 미생성 또는 safety 이유 |
| `tau_ext`, `tau_processed`, `task_wrench` | 입력과 wrench 변환 상태 |
| `raw_velocity`, `tangent_velocity`, `restore_velocity`, `limited_velocity` | 제어 pipeline 단계별 속도 |
| `reference_valid`, `reference_*` | mode 진입 기준 형상 |
| `constraint_error`, `constraint_error_norm` | 현재 constraint 이탈량 |
| `constraint_frame`, `pose_source` | 좌표계 디버깅 핵심 |
| `axis_mask`, `user_axis_mask` | 사용자 입력/출력 축 제한 |

`configs/function_flags.json`에서 `save_control_trace_log=true`이면 `ControlTraceLogger`가 CSV trace를 저장한다. trace에는 fixed controller 필드뿐 아니라 FSM, robot state, command delta, singularity slowdown 정보가 같이 들어간다.

## 현재 구현 판단

현재 구현은 권장 구조의 대부분을 갖춘 상태다.

| 기준 | 현재 상태 |
| --- | --- |
| tau_ext 기반 task-space 해석 | 구현됨 |
| TCP/base frame 변환 | 구현됨 |
| tangent/restore 분리 | 구현됨 |
| RCM error 계산 | 구현됨 |
| telemetry 기반 디버깅 | 구현됨 |
| joint-level constraint QP | 아직 없음 |
| 정식 mass-damper admittance state | 아직 없음 |

따라서 현재 문제는 구조 부재라기보다 frame contract 검증과 튜닝 문제일 가능성이 크다.
