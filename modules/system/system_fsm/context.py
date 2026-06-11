from modules.constants import *
from pkg.utils.blackboard import GlobalBlackboard

from pkg.utils.process_control import Flagger, reraise
import inspect
bb = GlobalBlackboard()
from modules.global_vars import backend_vars

class SystemContext(ContextBase):
    violation_code: ViolationType

    def __init__(self, *args, **kwargs):
        ContextBase.__init__(self)
        self.error_case = None
        self.violation_code = ViolationCode.NONE

    def reset_vars(self):
        pass

    def error_check(self):
        if bb.get("robot/state/op") not in [RobotState.OP_IDLE, RobotState.OP_MOVING, RobotState.OP_TEACHING, RobotState.TELE_OP,RobotState.OP_SYSTEM_RESET]: # OP moving 가는 건 manual control strategy에서 처리됨. 딜레이 고려
            self.error_case = 1
            return True
        
        self.error_case = 0
        return False
                # context.recover_robot()
                # context.violation_code = MyViolation.RECOVERING
# class MyViolation(ViolationType):
#     NONE = 0
#     NOT_READY = 1
#     VIOLATION = 2
#     COLLISION = 3
#     RECOVERING = 4
#     BRAKE_CONTROL = 5
#     NC = 6


    def violation_check(self):
        robot_state = bb.get("robot/state/op")

        if robot_state in (RobotState.OP_IDLE, RobotState.OP_MOVING, RobotState.OP_TEACHING, RobotState.TELE_OP):
            self.violation_code = ViolationCode.NONE
            return False
        else:
            if robot_state in (RobotState.OP_SYSTEM_OFF, RobotState.OP_SYSTEM_ON,
                                        RobotState.OP_STOP_AND_OFF):
                self.violation_code = ViolationCode.NOT_READY
                return True

            if robot_state in (RobotState.OP_VIOLATE, RobotState.OP_VIOLATE_HARD,
                                        RobotState.OP_SYSTEM_RESET, RobotState.OP_SYSTEM_SWITCH):
                self.violation_code = ViolationCode.VIOLATION
                return True

            if robot_state == RobotState.OP_COLLISION:
                self.violation_code = ViolationCode.COLLISION
                return True

            if robot_state == RobotState.OP_BRAKE_CONTROL:
                self.violation_code = ViolationCode.BRAKE_CONTROL
                return True

            if robot_state in (RobotState.OP_RECOVER_HARD, RobotState.OP_RECOVER_SOFT,
                                        RobotState.OP_MANUAL_RECOVER):
                self.violation_code = ViolationCode.RECOVERING
                return True

