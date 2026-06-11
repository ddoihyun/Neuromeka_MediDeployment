# Fixed Constraint Modes and Frames

작성일: 2026-06-10

## 목적

이 문서는 fixed point/line/plane의 현재 의미와 좌표계 규칙을 정리한다. 좌표계가 어긋나면 사용자가 미는 방향과 로봇이 움직이는 방향이 달라져 반응성이 낮거나 불안정하게 느껴진다.

## 좌표계 원칙

현재 구현은 다음 원칙을 사용한다.

1. `MoveTeleLTCP` command는 TCP frame delta라고 가정한다.
2. Jacobian은 FK로 base frame에서 계산한 뒤 TCP frame으로 변환한다.
3. `tau_ext`는 TCP-frame Jacobian을 통해 TCP-frame wrench/velocity로 해석한다.
4. constraint reference와 error는 base frame에서 계산한다.
5. restore velocity는 base frame에서 계산한 뒤 `R_tcp.T`로 TCP frame command로 변환한다.
6. line/plane tangent projection은 base 기준 reference axis를 현재 TCP frame으로 변환한 뒤 command에 적용한다.

요약하면 사용자 command는 TCP frame, constraint geometry는 base frame이다. 둘 사이의 변환이 명확해야 한다.

## Pose source

현재 TCP pose는 다음 우선순위로 얻는다.

| 우선순위 | source | 조건 |
| --- | --- | --- |
| 1 | `control_state["p"]` | 6축 pose가 있고 finite value일 때 |
| 2 | `q + MDH + tool_transform` FK | `p`가 없거나 유효하지 않을 때 |

중요한 점: `control_state.p`가 실제 TCP pose인지, flange pose인지, tool frame 적용 전 pose인지 반드시 확인해야 한다. 현재 controller는 `p`를 base 기준 TCP pose `[x, y, z, u, v, w]`로 해석한다.

확인할 telemetry:

| 필드 | 정상 기대 |
| --- | --- |
| `pose_source` | 대부분 `control_state.p`, fallback이면 `fk_mdh` |
| `constraint_frame` | tcp 기준 axis면 `base_from_tcp`, base 기준이면 `base` 또는 `base_from_base` |
| `reference_pose` | mode 진입 시점의 현재 pose |
| `constraint_error_norm` | 가만히 있을 때 deadband 안에서 유지 |

## Fixed Point

현재 config의 fixed point는 `rcm_point`다. 즉 TCP 위치를 공간상 한 점에 고정하는 모드가 아니라, tool shaft가 reference RCM point를 지나도록 유지하는 모드다.

현재 설정:

```json
"fixed_point": {
  "axis_mask": [0, 0, 0, 1, 1, 0],
  "constraint": {
    "type": "rcm_point",
    "reference_source": "entry_pose",
    "tool_axis_frame": "tcp",
    "tool_axis": [0, 0, 1]
  },
  "rotation_input": {
    "enabled": true,
    "source": "joint_admittance"
  }
}
```

### RCM point error

mode 진입 시 reference RCM point를 저장한다.

```text
axis_base = R_tcp * tool_axis_tcp
reference_rcm = tcp_position + axis_base * rcm_offset_mm
```

매 cycle error는 reference point에서 현재 tool shaft까지의 최단거리다.

```text
axis_base = current tool axis in base frame
s = dot(reference_rcm - tcp_position, axis_base)
closest_on_shaft = tcp_position + s * axis_base
e_rcm = closest_on_shaft - reference_rcm
```

restore는 `e_rcm`을 줄이는 방향으로 translation command를 만든다.

```text
restore_base = -Kp * e_rcm - Kd * de_rcm/dt
restore_tcp = R_tcp.T * restore_base
```

### 허용 입력

현재 fixed point의 사용자 입력은 translation을 모두 막고 `u`, `v` rotation만 허용한다. `w` roll은 axis mask에서 0이다.

| command 축 | 사용자 입력 | restore 입력 |
| --- | --- | --- |
| x/y/z | 차단 | RCM error 복원 목적이면 허용 |
| u/v | 허용 | 없음 |
| w | 차단 | 없음 |

tool 축 방향 삽입/후퇴까지 원하는 RCM 조작이라면 현재 설정은 제한적이다. 이 경우 `fixed_point`를 "pivot rotation only"로 유지하고, 별도 RCM insertion mode를 추가하는 편이 명확하다.

### TCP point 고정으로 쓰고 싶을 때

만약 fixed point의 의도가 "TCP 위치 자체 고정"이면 config를 다음 개념으로 바꿔야 한다.

```json
"constraint": {
  "type": "tcp_point",
  "reference_source": "entry_pose"
}
```

이때 error는 단순히 다음이다.

```text
e_point = current_tcp_position - reference_point
```

## Fixed Line

fixed line은 TCP 또는 tool point가 reference line 위에 머물도록 한다. line 방향 movement는 허용하고, line에 수직인 error만 restore한다.

현재 설정:

```json
"fixed_line": {
  "axis_mask": [0, 0, 1, 0, 0, 0],
  "constraint": {
    "type": "line",
    "reference_source": "entry_pose",
    "axis_frame": "tcp",
    "line_axis": [0, 0, 1]
  },
  "force_to_line": {
    "enabled": true,
    "force_direction": [0.30734449954312976, 0.15367224977156488, 0.9391081930484522]
  }
}
```

mode 진입 시 `line_axis`를 base frame으로 변환해 저장한다.

```text
line_axis_base = R_tcp_entry * line_axis_tcp
line_origin = tcp_position_entry
```

error:

```text
p_line = line_origin + dot(p_now - line_origin, line_axis_base) * line_axis_base
e_line = p_now - p_line
```

사용자 입력 projection:

```text
line_axis_tcp_now = R_tcp_now.T * line_axis_base
v_tangent = dot(v_tcp, line_axis_tcp_now) * line_axis_tcp_now
```

주의: `force_to_line.force_direction`은 현재 line axis와 다르다. 의도적으로 handle force direction을 보정한 값일 수 있지만, 이 값이 실제 사용자 힘 방향과 맞지 않으면 "비스듬히 밀어야 전진하는" 느낌이 날 수 있다.

## Fixed Plane

fixed plane은 TCP 또는 tool point가 reference plane 위에 머물도록 한다. plane 내부 movement는 허용하고, normal 방향 error만 restore한다.

현재 설정:

```json
"fixed_plane": {
  "axis_mask": [1, 1, 0, 0, 0, 0],
  "constraint": {
    "type": "plane",
    "reference_source": "entry_pose",
    "normal_frame": "tcp",
    "plane_normal": [0, 0, 1]
  }
}
```

mode 진입 시 plane normal을 base frame으로 저장한다.

```text
normal_base = R_tcp_entry * plane_normal_tcp
plane_point = tcp_position_entry
```

error:

```text
e_scalar = dot(p_now - plane_point, normal_base)
e_plane = e_scalar * normal_base
```

사용자 입력 projection:

```text
normal_tcp_now = R_tcp_now.T * normal_base
v_tangent = v_tcp - dot(v_tcp, normal_tcp_now) * normal_tcp_now
```

## axis_mask와 user_axis_mask

`axis_mask`는 restore disabled 경로에서 hard projection 역할을 한다. restore enabled일 때는 사용자 입력과 restore 입력의 역할이 분리된다.

`user_axis_mask`가 mode config에 있으면 사용자 입력에 먼저 적용한다. 없으면 다음 fallback을 사용한다.

| 조건 | user axis |
| --- | --- |
| restore enabled + fixed line/plane | `[1, 1, 1, 0, 0, 0]` |
| 그 외 | `axis_mask` |

즉 line/plane에서는 사용자 translation을 일단 모두 살린 뒤 line/plane tangent projection으로 제한한다. fixed point는 translation 사용자 입력을 항상 0으로 만든다.

## 좌표계 체크리스트

문제가 있을 때 다음 순서로 확인한다.

1. `pose_source`가 `control_state.p`인지 확인한다.
2. `control_state.p`와 FK pose를 별도로 비교한다. 위치가 지속적으로 차이나면 tool frame 또는 pose source가 다르다.
3. mode 진입 직후 `reference_valid=true`가 되는지 확인한다.
4. 손으로 작은 힘을 줬을 때 `tau_processed -> raw_velocity -> tangent_velocity` 부호가 기대와 맞는지 본다.
5. constraint error를 일부러 만들었을 때 `restore_velocity`가 error를 줄이는 방향인지 본다.
6. `last_command`와 실제 pose 변화 방향이 다르면 `MoveTeleLTCP` command frame 가정부터 의심한다.
