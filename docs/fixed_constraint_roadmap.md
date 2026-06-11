# Fixed Constraint Roadmap

작성일: 2026-06-10

## 현재 상태 요약

현재 fixed constraint teleop은 이전의 단순 projection 방식보다 발전된 상태다.

이미 구현된 것:

| 기능 | 상태 |
| --- | --- |
| `tau_ext` bias/deadzone | 완료 |
| MDH FK + numerical Jacobian | 완료 |
| TCP-frame command 해석 | 완료 |
| task wrench pseudo-inverse/damped inverse hook | 완료 |
| mode별 reference lazy capture | 완료 |
| fixed point RCM error | 완료 |
| fixed line/plane error | 완료 |
| tangent projection | 완료 |
| PD restore velocity | 완료 |
| restore shadow mode | 완료 |
| rate/filter/cumulative limit | 완료 |
| singularity slowdown | 완료 |
| backend telemetry + CSV trace | 완료 |

남은 핵심 과제:

| 과제 | 이유 |
| --- | --- |
| `control_state.p`와 FK/tool frame 검증 | frame mismatch가 가장 큰 체감 문제 원인 |
| fixed point 의미 분리 | `rcm_point`와 `tcp_point`가 사용자 언어에서 혼동됨 |
| 정식 admittance state | 현재는 gain mapping에 가까움 |
| joint velocity QP/null-space 제어 | constraint를 joint level에서 직접 보장하지 않음 |
| line/plane/RCM calibration workflow | 현장 tool axis와 기준점 검증 필요 |

## 단기 개선

### 1. Pose frame audit

문제: `_current_tcp_pose()`는 `control_state.p`를 base 기준 TCP pose로 신뢰한다. 만약 실제 값이 flange pose거나 tool 적용 전 pose면 restore가 틀어진다.

권장 작업:

```text
control_state.p
FK(q) + tool_transform
robot reported tool_frame/ref_frame
MoveTeleLTCP response pose
```

위 값을 같은 log row에 남기고 position/orientation 차이를 비교한다.

완료 기준:

| 항목 | 기준 |
| --- | --- |
| position 차이 | 정지 상태에서 허용 오차 안 |
| orientation 차이 | tool axis 방향이 일치 |
| pose_source | 의도한 source로 고정 |

### 2. fixed point mode naming 정리

현재 config상 fixed point는 `rcm_point`다. UI/voice에서 "점고정"이 TCP point인지 RCM point인지 명확하지 않다.

권장:

| 사용자 표현 | 내부 mode |
| --- | --- |
| 점고정/TCP 고정 | `tcp_point` |
| RCM/삽입점/포트 고정 | `rcm_point` |

가능하면 UI label도 `FIXED POINT`와 `RCM POINT`를 분리한다.

### 3. fixed point insertion 지원 여부 결정

현재 fixed point는 x/y/z 사용자 translation을 막고 u/v rotation만 허용한다. RCM 수술 도구 조작에서는 tool 축 방향 insertion/retraction이 필요할 수 있다.

선택지:

| 선택 | 장점 | 단점 |
| --- | --- | --- |
| 현재 유지 | pivot 안정성 좋음 | 삽입/후퇴 불가 |
| fixed point에 tool-axis tangent translation 추가 | RCM 조작 자연스러움 | axis mapping/limit 복잡 |
| 별도 RCM insertion mode 추가 | UI/튜닝 명확 | mode 추가 필요 |

권장은 별도 RCM insertion mode다.

## 중기 개선

### 1. Explicit admittance state

현재는 wrench 또는 `J * tau_ext`를 velocity로 바로 변환한다. 이 방식은 빠르지만 mass/damping 개념이 없어 부드러움과 반응성을 동시에 튜닝하기 어렵다.

권장 구조:

```text
M_d * xddot + D_d * xdot + K_d * x = F_ext
```

discrete 구현:

```text
a_des = (F_ext - D_d * v - K_d * x) / M_d
v_next = clamp(v + a_des * dt)
x_next = x + v_next * dt
```

mode별 적용:

| mode | admittance 대상 |
| --- | --- |
| fixed point | u/v rotation, optional insertion |
| fixed line | line tangent translation |
| fixed plane | plane tangent translation |
| restore | 별도 PD 또는 critically damped error dynamics |

튜닝 직관:

| 파라미터 | 낮추면 | 높이면 |
| --- | --- | --- |
| `M_d` | 반응 빨라짐, 떨림 가능 | 묵직함 |
| `D_d` | 즉답성 증가, overshoot 가능 | 안정적, 느림 |
| `K_d` | center 복원 강함 | free motion 느낌 감소 |

### 2. Constraint Jacobian/QP

현재는 task-space command를 만들고 `MoveTeleLTCP` 추종에 맡긴다. constraint를 더 단단하게 유지하려면 joint velocity level에서 풀어야 한다.

기본 QP:

```text
minimize ||J_task(q) qdot - v_user||^2
       + ||Jc(q) qdot + Kc e||^2
       + lambda ||qdot||^2

subject to qdot_min <= qdot <= qdot_max
           optional joint/velocity/singularity limits
```

mode별 constraint:

| mode | constraint |
| --- | --- |
| tcp point | `p_tcp(q) - p_ref = 0` |
| rcm point | shortest distance from RCM point to tool shaft = 0 |
| fixed line | normal distance to line = 0 |
| fixed plane | signed normal distance to plane = 0 |

QP 장점:

1. constraint 유지와 사용자 의도를 같은 최적화 문제에서 다룬다.
2. singularity/joint limit을 명시적으로 다룰 수 있다.
3. TCP command frame 의존도를 줄일 수 있다.

주의:

1. SDK가 joint velocity command를 안정적으로 받을 수 있어야 한다.
2. control period와 QP solve time을 보장해야 한다.
3. safety validation이 새로 필요하다.

## 장기 개선

### 1. Calibration workflow

RCM/tool shaft 제어는 tool axis calibration이 성능을 좌우한다.

필요한 workflow:

```text
tool frame set
tool axis verification
entry pose capture
RCM point validation
small rotation test
trace-based error check
```

UI에 보여줄 값:

| 값 | 목적 |
| --- | --- |
| current tool axis base | axis 방향 확인 |
| reference RCM point | 기준점 확인 |
| shaft-to-RCM distance | RCM error 직관화 |
| restore saturation | 복원 한계 확인 |

### 2. Mode-specific handle mapping

현재 fixed line에는 `force_to_line.force_direction`이 있다. 실제 handle/force sensor 배치가 작업 좌표계와 다르면 mode별 handle frame mapping을 명시하는 편이 낫다.

권장 config 개념:

```json
"input_frame": {
  "type": "handle",
  "rotation_to_tcp": [...],
  "force_axis_map": [...]
}
```

이렇게 하면 `task_wrench_sign`만으로 처리하기 어려운 축 섞임을 명확히 보정할 수 있다.

### 3. Safety supervisor

restore가 능동적으로 로봇을 움직이므로 safety supervisor를 별도 계층으로 분리하는 것이 좋다.

감시 항목:

| 항목 | action |
| --- | --- |
| pose stale | hold |
| constraint error too large | hold and require re-entry |
| restore saturation 지속 | warn/slowdown |
| singularity near stop | scale or hold |
| command/pose direction mismatch | disable restore |

## 권장 작업 순서

1. pose frame audit와 trace 비교를 먼저 한다.
2. fixed point의 용어를 `tcp_point`와 `rcm_point`로 분리한다.
3. current controller에서 tuning을 마무리한다.
4. explicit admittance state를 mode별로 추가한다.
5. RCM insertion 요구가 있으면 mode를 분리해 추가한다.
6. joint velocity QP 가능성을 SDK command path 기준으로 검토한다.

## 완료 기준

현재 구조의 완료 기준:

| 기준 | 목표 |
| --- | --- |
| fixed point RCM | `constraint_error_norm`이 deadband 근처 유지 |
| fixed line | 수직 error가 감소하고 line 방향 입력이 자연스러움 |
| fixed plane | normal error가 감소하고 plane 내부 입력이 자연스러움 |
| telemetry | 문제 발생 시 last_reason과 trace로 원인 추적 가능 |
| safety | max error, singularity, command limit이 예측 가능하게 동작 |

QP/admittance 확장 완료 기준:

| 기준 | 목표 |
| --- | --- |
| admittance | mass/damping 조절로 반응성/부드러움이 독립적으로 튜닝됨 |
| QP | constraint error가 MoveTele 추종 오차보다 안정적으로 작음 |
| calibration | tool axis와 RCM point 검증 절차가 재현 가능 |
