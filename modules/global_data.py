from enum import IntEnum

from modules.global_func import _is_feature_enabled

# Voice 사용 여부를 제어하는 옵션
Use_Voice = _is_feature_enabled("use_voice", default=False)
# Joystick 사용 여부를 제어하는 옵션
Use_Joystick = _is_feature_enabled("use_joystick", default=True)

ALARM_TEMPLATES = [
    {
        "code": "ER-FW-001",
        "message": "펌웨어 미구동: 로봇 제어 SW가 동작하지 않았습니다",
        "action": "상태 업데이트 버튼 터치 혹은 재부팅. 필요 시 서비스 연락",
        "severity": "error",
    },
    {
        "code": "ER-RB-001",
        "message": "충돌 감지: 로봇 팔이 외부 물체와 접촉이 감지되었습니다",
        "action": "로봇 주변 확인 후 상태 업데이트 버튼 터치 혹은 재부팅",
        "severity": "error",
    },
    {
        "code": "ER-RB-002",
        "message": "관절 제한 범위 초과: 로봇이 설정된 동작 허용 범위를 벗어나려 했습니다",
        "action": "필요 시 제조업체로 연락하세요",
        "severity": "error",
    },
    {
        "code": "ER-CON-001",
        "message": "컨트롤러 USB 연결 불안정 또는 포트 인식 실패",
        "action": "연결 상태 확인 후 상태 업데이트 버튼 터치",
        "severity": "error",
    },
    {
        "code": "ER-EMG-001",
        "message": "비상 정지 스위치가 눌렸습니다.",
        "action": "비상 정지 해제 후 상태 업데이트 버튼 터치 혹은 재부팅",
        "severity": "error",
    },
]

class JoystickCommand:
    DISCONNECT = -1
    NONE = 0
    ROTATE_CCW = 1
    ROTATE_CW = 2
    ENABLE = 3
    TILT_U = 6
    TILT_V = 7
    TILT_W = 8

    TILT_NONE = 9
    TILT_LEFT = 10
    TILT_RIGHT = 11
    TILT_UP = 12
    TILT_DOWN = 13

    CUSTOM_MODE = 14
    FREE_MOTION_MODE = 15
    FIXED_POINT_MODE = 16
    FIXED_LINE_MODE = 17
    UPDATE_JTS = 18

    MODE_CHANGE = 19
    ZOOM_IN = 20    
    ZOOM_OUT = 21

    TILT_W_CW = 22
    TILT_W_CCW = 23


class ControlMode(IntEnum):
    NONE = -1
    FIXED_JOINT = 0
    FREE_MOTION = 1
    FIXED_POINT = 2
    FIXED_LINE  = 3
    UPDATE_JTS  = 4
    FIXED_PLANE = 5
    
class ControlMotion(IntEnum):
    NONE = 0
    ROTATE_CCW = 1
    ROTATE_CW = 2
    ZOOM_OUT = 4
    ZOOM_IN = 5
    TILT_LEFT = 9
    TILT_RIGHT = 10
    TILT_UP = 11
    TILT_DOWN = 12

class RobotState(IntEnum):
    OP_SYSTEM_OFF = 0
    OP_SYSTEM_ON = 1
    OP_VIOLATE = 2
    OP_RECOVER_HARD = 3
    OP_RECOVER_SOFT = 4
    OP_IDLE = 5
    OP_MOVING = 6
    OP_TEACHING = 7
    OP_COLLISION = 8
    OP_STOP_AND_OFF = 9
    OP_COMPLIANCE = 10
    OP_BRAKE_CONTROL = 11
    OP_SYSTEM_RESET = 12
    OP_SYSTEM_SWITCH = 13
    OP_VIOLATE_HARD = 15
    OP_MANUAL_RECOVER = 16
    TELE_OP = 17
