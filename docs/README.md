# MediDeployment Docs

작성일: 2026-06-10

이 디렉터리는 현재 `MediDeployment` 구현 기준의 운영/제어 문서만 담는다. 이전 fixed constraint 문서는 오래된 projection-only 설명과 현재 restore/RCM 구현이 섞여 있어 모두 제거하고 새로 작성했다.

## 문서 목록

| 문서 | 내용 |
| --- | --- |
| [fixed_constraint_teleop_architecture.md](fixed_constraint_teleop_architecture.md) | fixed point/line/plane teleop의 최신 제어 파이프라인, FSM 진입/종료, backend/trace 흐름 |
| [fixed_constraint_modes_and_frames.md](fixed_constraint_modes_and_frames.md) | mode별 constraint 의미, TCP/base 좌표계 변환, RCM/fixed point 해석 |
| [fixed_constraint_config_reference.md](fixed_constraint_config_reference.md) | `configs/fixed_constraint_teleop_config.json` 설정 항목과 현재 값의 의미 |
| [fixed_constraint_tuning_and_validation.md](fixed_constraint_tuning_and_validation.md) | 반응성 튜닝 순서, telemetry 확인법, hardware 검증 절차 |
| [fixed_constraint_roadmap.md](fixed_constraint_roadmap.md) | 현재 구현의 한계와 QP/null-space/admittance 개선 방향 |

## 현재 구현의 핵심

현재 fixed constraint teleop은 joystick 축 입력이 아니라 로봇 제어 상태의 `tau_ext`를 주 입력으로 사용한다. `tau_ext`는 `q`와 MDH 기반 numerical Jacobian을 통해 task-space wrench 또는 mode-specific velocity로 변환되고, fixed constraint의 tangent 성분과 restore 성분을 합성한 뒤 `MoveTeleLTCP`로 전달된다.

현재 구조는 단순 `axis_mask` 방식이 아니다. mode 진입 시 reference geometry를 lazy capture하고, 매 cycle constraint error를 계산해 PD restore velocity를 만든다.

```text
control_state(q, p, tau_ext)
  -> tau bias/deadzone
  -> FK + TCP-frame Jacobian
  -> task wrench / mode-specific velocity
  -> reference capture
  -> tangent projection
  -> constraint error restore
  -> rate/filter/cumulative/singularity limit
  -> MoveTeleLTCP
```

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `modules/robot/fixed_constraint_teleop.py` | `tau_ext`를 fixed constraint teleop command로 변환하는 controller |
| `modules/robot/robot_control.py` | RTDE/TeleOP 상태 수집, controller 호출, `MoveTeleLTCP` 전송 |
| `configs/fixed_constraint_teleop_config.json` | gain, MDH, constraint, restore, limit, filter 설정 |
| `modules/system/system_fsm/strategy.py` | cockpit/voice fixed mode 진입 및 종료 |
| `modules/system/system_fsm/fsm.py` | fixed/voice fixed FSM transition table |
| `modules/backend/backend.py` | `/api/robot/telemetry`, `/api/robot/simulated-tau` 제공 |
| `modules/robot/control_trace_logger.py` | fixed teleop CSV trace 필드 정의 |

## 빠른 판단

현재 구현은 fixed constraint teleop의 기본 방향이 잘 잡혀 있다. 특히 RCM restore, tangent projection, 좌표계 변환, telemetry가 들어가 있어 디버깅 가능한 구조다.

가장 중요한 확인점은 세 가지다.

1. `control_state.p`, FK, tool frame, `MoveTeleLTCP` command frame이 같은 의미로 맞물리는지 확인한다.
2. fixed point가 실제로는 `rcm_point`인지, 말 그대로 TCP position 고정인 `tcp_point`인지 작업 의도와 맞춘다.
3. 반응성이 낮을 때 gain만 올리지 말고 `tau_processed`, `raw_velocity`, `tangent_velocity`, `restore_limited_velocity`, `limited_velocity`, `singularity_speed_scale` 순서로 병목을 찾는다.
