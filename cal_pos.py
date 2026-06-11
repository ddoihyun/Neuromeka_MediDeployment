import numpy as np

def make_tip_R(u_deg, v_deg, w_deg):
    """
    RPY(Roll-Pitch-Yaw) 각도(deg)를 입력받아 회전 행렬을 반환
    순서: X(Roll) -> Y(Pitch) -> Z(Yaw) 회전 (Fixed Frame 기준)
    수식: R = Rz * Ry * Rx
    """
    # Degree -> Radian 변환
    u = np.radians(u_deg)
    v = np.radians(v_deg)
    w = np.radians(w_deg)

    # 기본 회전 행렬 정의
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(u), -np.sin(u)],
        [0, np.sin(u), np.cos(u)]
    ])

    Ry = np.array([
        [np.cos(v), 0, np.sin(v)],
        [0, 1, 0],
        [-np.sin(v), 0, np.cos(v)]
    ])

    Rz = np.array([
        [np.cos(w), -np.sin(w), 0],
        [np.sin(w), np.cos(w), 0],
        [0, 0, 1]
    ])

    # 행렬 곱셈 (@ 연산자 사용)
    return Rz @ Ry @ Rx

def get_rpy_from_R(R):
    """
    Extract RPY angles [u, v, w] in degrees from a rotation matrix made by
    R = Rz(w) * Ry(v) * Rx(u).
    """
    R = np.asarray(R, dtype=float).reshape(3, 3)
    sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)

    singular = sy < 1e-6

    if not singular:
        x_rad = np.arctan2(R[2, 1], R[2, 2])
        y_rad = np.arctan2(-R[2, 0], sy)
        z_rad = np.arctan2(R[1, 0], R[0, 0])
    else:
        x_rad = np.arctan2(-R[1, 2], R[1, 1])
        y_rad = np.arctan2(-R[2, 0], sy)
        z_rad = 0

    return np.degrees([x_rad, y_rad, z_rad])

def get_tool_tip_pose(tip_p, tip_R, tip_length):
    """
    입력:
      tip_p: 오프셋 위치 벡터 (numpy array shape (3,))
      tip_R: 회전 행렬 (numpy array shape (3, 3))
      tip_length: 툴 길이 (float)
    출력:
      [x, y, z, u, v, w] 리스트 (위치 + RPY 각도)
    """
    # 1. 최종 위치 (Position) 계산
    # 툴 좌표계 기준 Z방향 벡터 (0, 0, length)
    tip_vec_local = np.array([0, 0, tip_length])
    
    # 회전 적용 후 오프셋에 더하기
    final_xyz = tip_p + (tip_R @ tip_vec_local)

    # 2. 최종 각도 (Orientation) 계산 - 회전 행렬에서 RPY 추출
    final_u, final_v, final_w = get_rpy_from_R(tip_R)

    return [final_xyz[0], final_xyz[1], final_xyz[2], final_u, final_v, final_w]

def get_tool_tip_pose_world(flange_p, flange_R, tip_p, tip_R, tip_length):
    """
    Calculate TCP pose in base/world coordinates.

    Args:
        flange_p: Flange position in base/world frame, shape (3,), unit m.
        flange_R: Flange rotation in base/world frame, shape (3, 3).
        tip_p: Tool reference point offset from flange, shape (3,), unit m.
        tip_R: Tool rotation with respect to flange, shape (3, 3).
        tip_length: Tool reference point to TCP distance along tool local +Z, unit m.

    Returns:
        [x, y, z, u, v, w] in base/world frame. Position unit m, angles deg.
    """
    flange_p = np.asarray(flange_p, dtype=float).reshape(3)
    flange_R = np.asarray(flange_R, dtype=float).reshape(3, 3)
    tip_p = np.asarray(tip_p, dtype=float).reshape(3)
    tip_R = np.asarray(tip_R, dtype=float).reshape(3, 3)

    tcp_p_flange = tip_p + (tip_R @ np.array([0, 0, tip_length]))
    tcp_p_world = flange_p + (flange_R @ tcp_p_flange)
    tcp_R_world = flange_R @ tip_R
    tcp_u, tcp_v, tcp_w = get_rpy_from_R(tcp_R_world)

    return [tcp_p_world[0], tcp_p_world[1], tcp_p_world[2], tcp_u, tcp_v, tcp_w]

# --- 실행 예시 ---
if __name__ == "__main__":
    # 1. 입력값 설정
    tip_length = 103.2234 / 1000
    tip_p = np.array([0.0, 0.0, 112.43 / 1000])
    tip_p = np.array([0.0, 0.0, 50.43 / 1000])

    # 2. 각도 입력 (아까 계산한 값)
    u_input = 30.0
    v_input = -35.26439  # atan(-1/sqrt(2)) 값
    w_input = 0.0

    # 3. 회전 행렬 생성
    tip_R = make_tip_R(u_input, v_input, w_input)

    # 4. 최종 TCP 계산
    result = get_tool_tip_pose(tip_p, tip_R, tip_length)

    print("=== Final TCP Pose ===")
    print(f"X : {result[0]*1000:.5f} mm")
    print(f"Y : {result[1]*1000:.5f} mm")
    print(f"Z : {result[2]*1000:.5f} mm")
    print(f"U : {result[3]:.5f} deg")
    print(f"V : {result[4]:.5f} deg")
    print(f"W : {result[5]:.5f} deg")

    # 5. Flange pose in base/world frame. Replace these with measured values.
    # Position unit: m, angle unit: deg.
    flange_p = np.array([0.0, 0.0, 0.0])
    flange_u_input = 0.0
    flange_v_input = 0.0
    flange_w_input = 0.0
    flange_R = make_tip_R(flange_u_input, flange_v_input, flange_w_input)

    result_world = get_tool_tip_pose_world(
        flange_p,
        flange_R,
        tip_p,
        tip_R,
        tip_length,
    )

    print("")
    print("=== Final TCP Pose (Base/World Frame) ===")
    print(f"X : {result_world[0]*1000:.5f} mm")
    print(f"Y : {result_world[1]*1000:.5f} mm")
    print(f"Z : {result_world[2]*1000:.5f} mm")
    print(f"U : {result_world[3]:.5f} deg")
    print(f"V : {result_world[4]:.5f} deg")
    print(f"W : {result_world[5]:.5f} deg")
