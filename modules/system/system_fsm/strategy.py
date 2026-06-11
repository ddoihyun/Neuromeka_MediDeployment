import pygame
import time
from modules.constants import *
from modules.global_data import ControlMode, JoystickCommand
from modules.global_vars import backend_vars, joystick_manager, voice_manager
from modules.global_func import *
from modules.system.system_fsm.context import *
from modules.global_func import _is_feature_enabled
from queue import Empty

bb = GlobalBlackboard()

class not_ready_strategy(Strategy):
    def __init__(self):
        self._next_connection_retry_time = 0.0
        self._next_connection_log_time = 0.0

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.NOT_READY)
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")

        
        # --------------------------------------------

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if bb.get("robot/enabled")==False:
            current_time = time.monotonic()
            if not bb.get("robot/check_connection"):
                if current_time < self._next_connection_retry_time:
                    return SystemFsmEvent.NONE
                bb.set("robot/check_connection",True)
                self._next_connection_retry_time = current_time + ROBOT_CONNECTION_RETRY_INTERVAL_SEC
            while True:
                if bb.get("robot/check_connection") == False:
                    break
                if bb.get("robot/enabled") == True:
                    bb.set("robot/check_connection", False)
                    break
                current_time = time.monotonic()
                if current_time >= self._next_connection_log_time:
                    Logger.debug(f"{get_time()}: Check robot connection...")
                    self._next_connection_log_time = current_time + ROBOT_CONNECTION_LOG_INTERVAL_SEC
                time.sleep(0.1)

        if bb.get("robot/enabled")==True:
            self._next_connection_retry_time = 0.0
            self._next_connection_log_time = 0.0
            if bb.get("robot/state/op")==RobotState.OP_IDLE:
                bb.set("robot/command_post_processing",True)
                next_log_time = 0
                while True:
                    if bb.get("robot/command_post_processing") == False:
                        break
                    current_time = time.time()
                    if current_time >= next_log_time:
                        Logger.debug(f"{get_time()}: Robot initialize...")
                        next_log_time = current_time + 1
                    time.sleep(0.1)
                return SystemFsmEvent.PREP # 로봇이 잘 연결되면 넘김
        
            if bb.get("robot/state/op")==RobotState.TELE_OP:
                bb.set("teleop/disable",True)
                while True:
                    if bb.get("teleop/disable")==False:
                        break
                    else:
                        time.sleep(1)
        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class prep_strategy(Strategy): # 조이스틱이 정상연결되는지 확인 필요
    def __init__(self):
        self.wait_cockpit_release = False

    def prepare(self, context: SystemContext, **kwargs):        
        bb.set("robot/state/fsm",SystemFsmState.PREP)
        bb.set("control/mode", ControlMode.FIXED_JOINT)
        self.wait_cockpit_release = bb.get("cockpit/pressed") == True
        if self.wait_cockpit_release:
            Logger.debug(f"{get_time()}: [PREP] Waiting cockpit release")
        
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")        

    def operate(self, context: SystemContext) -> SystemFsmEvent: 
        if context.error_check():        
            return SystemFsmEvent.ERROR

        if self.wait_cockpit_release:
            if bb.get("cockpit/pressed") == True:
                return SystemFsmEvent.NONE
            self.wait_cockpit_release = False

        if backend_vars.read("MOVE_FLAG") == True:      
            return SystemFsmEvent.MANUAL_CONTROL
        
        if bb.get("robot/request/activate_motion") == True:
            bb.set("robot/request/activate_motion",False)
            return SystemFsmEvent.DEBUG_MOTION

        check_home = _is_feature_enabled("check_home", default=True)
        if not check_home:
            return SystemFsmEvent.IDLE

        if bb.get("robot/state/is_home_once"): # 한번이라도 홈 갔으면 ok지
            return SystemFsmEvent.IDLE

        if bb.get("robot/state/is_home"): # 홈에 있을 때
            bb.set("robot/state/is_home_once",True)
            return SystemFsmEvent.IDLE
        
        return SystemFsmEvent.NONE
        # 에러 뜨면 홈 가고 난 후에 동작하게 해야 할까? 이건 생각 좀

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        # bb.set("robot/request/go_home",False)
        # bb.set("robot/request/go_setting",False)
        # bb.set("robot/request/go_packaging",False)
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class idle_strategy(Strategy):
    def __init__(self):
        self.wait_cockpit_release = False

    def prepare(self, context: SystemContext, **kwargs):        
        bb.set("robot/state/fsm",SystemFsmState.IDLE)
        bb.set("control/mode", ControlMode.FIXED_JOINT)
        bb.set("control/request_jts_update",False) # 다른 곳에서 돌아오면 버튼 누른 거 초기화. 이런 식으로 쓰는 거 좋네
        bb.set("voice/request_control",False)
        self.wait_cockpit_release = bb.get("cockpit/pressed") == True
        if self.wait_cockpit_release:
            Logger.debug(f"{get_time()}: [IDLE] Waiting cockpit release")

        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")        

    def operate(self, context: SystemContext) -> SystemFsmEvent: 
        if context.error_check(): 
            return SystemFsmEvent.ERROR

        if self.wait_cockpit_release:
            if bb.get("cockpit/pressed") == True:
                return SystemFsmEvent.NONE
            self.wait_cockpit_release = False

        if bb.get("cockpit/pressed")==True:
            desired_mode = bb.get("control/desired_mode")
            if desired_mode in [ControlMode.FREE_MOTION]:
                return SystemFsmEvent.DIRECT_TEACHING
            if desired_mode == ControlMode.FIXED_POINT:
                return SystemFsmEvent.FIXED_POINT_CONTROL
            if desired_mode == ControlMode.FIXED_LINE:
                return SystemFsmEvent.FIXED_LINE_CONTROL
            if desired_mode == ControlMode.FIXED_PLANE:
                return SystemFsmEvent.FIXED_PLANE_CONTROL

        if bb.get("joystick/state/connect"):
            try:
                if len(joystick_manager.event_list) >0:
                    action, value = joystick_manager.event_list.pop(0)
                else:
                    action, value = None, None
            except Empty:
                action, value = None, None
            if action is not None:
                pass
            if action==JoystickCommand.ENABLE and value == True:
                Logger.debug(f"{get_time()}: [JOYSTICK] Control Enabled")
                return SystemFsmEvent.JOYSTICK_CONTROL

        if backend_vars.read("MOVE_FLAG") == True:      
            return SystemFsmEvent.MANUAL_CONTROL
        
        if bb.get("control/request_jts_update")==True:
            bb.set("control/request_jts_update",False)
            return SystemFsmEvent.UPDATE_GAIN
        
        if bb.get("robot/request/activate_motion") == True:
            bb.set("robot/request/activate_motion",False)
            return SystemFsmEvent.DEBUG_MOTION
        
        use_button = _is_feature_enabled("use_button", default=False)
        if use_button and bb.get("button/pressed") == 1 :
            Logger.debug(f"{get_time()}: [Button] Button pressed")
            if bb.get("button/mode") in [ControlMode.FREE_MOTION,
                                         ControlMode.FIXED_PLANE,
                                         ControlMode.FIXED_POINT,
                                         ControlMode.FIXED_LINE,
                                         ControlMode.FIXED_JOINT]:
                return SystemFsmEvent.BUTTON_CONTROL

        if bb.get("voice/request_control"):
            bb.set("voice/request_control",False)
            return SystemFsmEvent.VOICE_CONTROL

        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        # bb.set("robot/request/go_home",False)
        # bb.set("robot/request/go_setting",False)
        # bb.set("robot/request/go_packaging",False)
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class direct_teaching_strategy(Strategy):
    def __init__(self):
        pass

    def prepare(self, context: SystemContext, **kwargs):      
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")        
        bb.set("robot/state/fsm",SystemFsmState.DIRECT_TEACHING)
        if bb.get("robot/state/op")!= RobotState.OP_TEACHING:
            bb.set("dt/enable",True)
            deadline = time.time() + 3.0
            while bb.get("dt/enable")==True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting DT change")
                time.sleep(0.1)
            if bb.get("dt/enable")==True:
                Logger.warn(f"{get_time()}: [DT] Timed out waiting for DT start")
                bb.set("dt/enable",False)
                return


    def operate(self, context: SystemContext) -> SystemFsmEvent: 
        if context.error_check(): 
            return SystemFsmEvent.ERROR


        if bb.get("cockpit/pressed") != True:
            check_home = _is_feature_enabled("check_home", default=True)
            if (not check_home) or bb.get("robot/state/is_home_once"):
                return SystemFsmEvent.IDLE
            else:
                return SystemFsmEvent.PREP


        
        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:

        bb.set("dt/disable",True)
        deadline = time.time() + 3.0
        while bb.get("dt/disable")==True and time.time() < deadline:
            Logger.debug(f"{get_time()}: Waiting DT change")
            time.sleep(0.1)
        if bb.get("dt/disable")==True:
            Logger.warn(f"{get_time()}: [BUTTON] Timed out waiting for DT stop")
            bb.set("dt/disable",False)

        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class update_gain_strategy(Strategy):
    def __init__(self):
        pass
    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.UPDATE_GAIN)
        self.start_time_var = time.time()
        bb.set("control/request_tau_bias_update", True)
        
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")        

    def operate(self, context: SystemContext) -> SystemFsmEvent: 
        if context.error_check(): 
            return SystemFsmEvent.ERROR

        if bb.get("control/request_tau_bias_update") == True:
            return SystemFsmEvent.NONE

        return SystemFsmEvent.IDLE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class error_strategy(Strategy):
    def __init__(self):
        pass

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.ERROR)
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")
        
        # --------------------------------------------

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if bb.get("robot/request_recover") == True: # 자동으로 넘어가게 하지말자
            bb.set("robot/request_recover",False)
            return SystemFsmEvent.RECOVER 
        if bb.get("robot/state/op")==RobotState.OP_SYSTEM_OFF:
            return SystemFsmEvent.NOT_READY 
        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class recover_strategy(Strategy):
    def __init__(self):
        pass

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.RECOVER)
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")
        if context.violation_check():            
            bb.set("robot/do_recover",True)
            while True:
                if bb.get("robot/do_recover") == False:
                    break
                Logger.debug(f"{get_time()}: [Robot] Recovering...")
                time.sleep(1)
            pass # do recover

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        """ Check Error """
        if context.violation_check():            
            if context.violation_code == ViolationCode.RECOVERING:
                return SystemFsmEvent.NONE
            else:
                # 리커버 
                return SystemFsmEvent.ERROR          
        else: # violtation이 아닐 경우 
            return SystemFsmEvent.IDLE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class voice_control_strategy(Strategy):
    def __init__(self):
        self.next_event = SystemFsmEvent.NONE
        self.wait_voice_movel_done = False
        self.voice_movel_seen_moving = False
        self.voice_movel_start_deadline = 0.0

    def _mode_from_voice_aux(self, aux0):
        aux0 = str(aux0).strip().lower()
        if aux0 == "free":
            return ControlMode.FREE_MOTION
        if aux0 == "fix":
            return ControlMode.FIXED_JOINT
        if aux0 == "point":
            return ControlMode.FIXED_POINT
        if aux0 == "line":
            return ControlMode.FIXED_LINE
        if aux0 in ["plane", "rcm"]:
            return ControlMode.FIXED_PLANE
        return ControlMode.FIXED_JOINT

    def _request_voice_movel(self, voice_json, tts_text):
        tpos = voice_json.get("tpos", [])
        if not isinstance(tpos, (list, tuple)) or len(tpos) < 6:
            bb.set("voice/speak_contents","이동 명령 값을 확인하지 못했어요.")
            bb.set("voice/speak_flag",True)
            return False

        try:
            command = [float(tpos[i]) for i in range(6)]
        except (TypeError, ValueError):
            bb.set("voice/speak_contents","이동 명령 값이 올바르지 않아요.")
            bb.set("voice/speak_flag",True)
            return False

        if bb.get("robot/state/op") == RobotState.OP_MOVING:
            bb.set("voice/speak_contents","로봇이 이동 중이라 새 이동 명령을 실행하지 못했어요.")
            bb.set("voice/speak_flag",True)
            return False

        if not self._stop_teleop_for_movel():
            bb.set("voice/speak_contents","텔레옵 종료를 기다리다 시간이 초과되어 이동하지 못했어요.")
            bb.set("voice/speak_flag",True)
            return False

        bb.set("robot/request/voice_movel_tpos",command)
        bb.set("robot/request/voice_movel_label",tts_text)
        bb.set("robot/request/voice_movel",True)
        self.wait_voice_movel_done = True
        self.voice_movel_seen_moving = False
        self.voice_movel_start_deadline = time.time() + 3.0
        if tts_text:
            bb.set("voice/speak_contents",tts_text)
            bb.set("voice/speak_flag",True)
        return True

    def _voice_movel_wait_event(self):
        if not getattr(self, "wait_voice_movel_done", False):
            return None

        robot_op = bb.get("robot/state/op")
        if robot_op == RobotState.OP_MOVING:
            self.voice_movel_seen_moving = True
            return SystemFsmEvent.NONE

        if self.voice_movel_seen_moving and robot_op == RobotState.OP_IDLE:
            self.wait_voice_movel_done = False
            return SystemFsmEvent.IDLE

        if not self.voice_movel_seen_moving and time.time() >= self.voice_movel_start_deadline:
            Logger.warn(f"{get_time()}: [Voice] MoveL did not start before timeout")
            self.wait_voice_movel_done = False
            return SystemFsmEvent.IDLE

        return SystemFsmEvent.NONE

    def _voice_mode_event(self, mode, current_mode=None):
        if current_mode == mode and mode != ControlMode.FIXED_JOINT:
            return SystemFsmEvent.NONE
        if mode == ControlMode.FREE_MOTION:
            return SystemFsmEvent.VOICE_DIRECT_TEACHING
        if mode == ControlMode.FIXED_POINT:
            return SystemFsmEvent.VOICE_FIXED_POINT_CONTROL
        if mode == ControlMode.FIXED_LINE:
            return SystemFsmEvent.VOICE_FIXED_LINE_CONTROL
        if mode == ControlMode.FIXED_PLANE:
            return SystemFsmEvent.VOICE_FIXED_PLANE_CONTROL
        return SystemFsmEvent.IDLE

    def _stop_teleop_for_movel(self):
        robot_op = bb.get("robot/state/op")
        if robot_op == RobotState.OP_TEACHING:
            bb.set("dt/disable", True)
            deadline = time.time() + 3.0
            while bb.get("dt/disable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting DT change")
                time.sleep(0.1)
            if bb.get("dt/disable") == True:
                Logger.warn(f"{get_time()}: [Voice] Timed out waiting for DT stop before MoveL")
                bb.set("dt/disable", False)
                return False
            return True

        if robot_op != RobotState.TELE_OP:
            return True

        bb.set("teleop/disable", True)
        deadline = time.time() + 3.0
        while bb.get("teleop/disable") == True and time.time() < deadline:
            Logger.debug(f"{get_time()}: Waiting TeleOP change")
            time.sleep(0.1)
        if bb.get("teleop/disable") == True:
            Logger.warn(f"{get_time()}: [Voice] Timed out waiting for TeleOP stop before MoveL")
            bb.set("teleop/disable", False)
            return False
        return True

    def _event_from_voice_json(self, voice_json, current_mode=None):
        if not isinstance(voice_json, dict):
            return SystemFsmEvent.IDLE

        voice_mode = voice_json.get("action", "")
        aux0 = voice_json.get("aux0", "")
        tts_text = voice_json.get("aux1") or voice_json.get("aux0") or ""

        if voice_mode == "mode":
            bb.set("voice/speak_contents", tts_text)
            bb.set("voice/speak_flag", True)
            mode = self._mode_from_voice_aux(aux0)
            return self._voice_mode_event(mode, current_mode=current_mode)
        if voice_mode == "movel":
            if self._request_voice_movel(voice_json, tts_text):
                return SystemFsmEvent.NONE
            return SystemFsmEvent.IDLE
        return SystemFsmEvent.IDLE

    def _consume_voice_event(self, current_mode=None):
        if not bb.get("voice/request_control"):
            return SystemFsmEvent.NONE
        bb.set("voice/request_control", False)
        return self._event_from_voice_json(
            bb.get("voice/action_json"),
            current_mode=current_mode,
        )

    def _manual_idle_event(self):
        if bb.get("cockpit/pressed") == True:
            Logger.debug(f"{get_time()}: [Voice] Cockpit pressed")
            return SystemFsmEvent.IDLE

        button_pressed = bb.get("button/pressed")
        if button_pressed not in (0, False, None):
            Logger.debug(f"{get_time()}: [Voice] Button pressed")
            return SystemFsmEvent.IDLE

        try:
            if bb.get("joystick/state/connect"):
                if len(joystick_manager.event_list) > 0:
                    action, value = joystick_manager.event_list.pop(0)
                else:
                    action, value = None, None
            else:
                action, value = None, None
        except Empty:
            action, value = None, None

        if action == JoystickCommand.ENABLE and value == False:
            Logger.debug(f"{get_time()}: [Voice] Joystick released")
            return SystemFsmEvent.IDLE
        return SystemFsmEvent.NONE

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm", SystemFsmState.VOICE_CONTROL)
        bb.set("voice/request_control", False)
        self.next_event = self._event_from_voice_json(bb.get("voice/action_json"))
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if context.error_check():
            return SystemFsmEvent.ERROR

        manual_event = self._manual_idle_event()
        if manual_event != SystemFsmEvent.NONE:
            return manual_event

        move_event = self._voice_movel_wait_event()
        if move_event is not None:
            return move_event

        if self.next_event != SystemFsmEvent.NONE:
            event = self.next_event
            self.next_event = SystemFsmEvent.NONE
            return event

        voice_event = self._consume_voice_event()
        if voice_event != SystemFsmEvent.NONE:
            return voice_event

        return SystemFsmEvent.IDLE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")


class voice_direct_teaching_strategy(voice_control_strategy):
    def __init__(self):
        self.quick_return = False

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm", SystemFsmState.VOICE_DIRECT_TEACHING)
        bb.set("voice/request_control", False)
        self.quick_return = False

        if bb.get("robot/state/op") != RobotState.OP_TEACHING:
            bb.set("dt/enable", True)
            deadline = time.time() + 3.0
            while bb.get("dt/enable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting DT change")
                time.sleep(0.1)
            if bb.get("dt/enable") == True:
                Logger.warn(f"{get_time()}: [VoiceDT] Timed out waiting for DT start")
                bb.set("dt/enable", False)
                self.quick_return = True

        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if context.error_check():
            return SystemFsmEvent.ERROR
        if self.quick_return:
            return SystemFsmEvent.IDLE

        manual_event = self._manual_idle_event()
        if manual_event != SystemFsmEvent.NONE:
            return manual_event

        move_event = self._voice_movel_wait_event()
        if move_event is not None:
            return move_event

        return self._consume_voice_event(current_mode=ControlMode.FREE_MOTION)

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        if bb.get("robot/state/op") == RobotState.OP_TEACHING:
            bb.set("dt/disable", True)
            deadline = time.time() + 3.0
            while bb.get("dt/disable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting DT change")
                time.sleep(0.1)
            if bb.get("dt/disable") == True:
                Logger.warn(f"{get_time()}: [VoiceDT] Timed out waiting for DT stop")
                bb.set("dt/disable", False)

        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")


class voice_fixed_constraint_teleop_strategy(voice_control_strategy):
    fixed_mode = ControlMode.NONE
    fixed_state = SystemFsmState.NONE

    def __init__(self):
        self.quick_return = False

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm", self.fixed_state)
        bb.set("voice/request_control", False)
        bb.set("control/mode", self.fixed_mode)
        bb.set("fixed_constraint_teleop/active_mode", self.fixed_mode)
        bb.set("fixed_constraint_teleop/reset", True)
        self.quick_return = False

        if bb.get("robot/state/op") != RobotState.TELE_OP:
            bb.set("teleop/enable", True)
            deadline = time.time() + 3.0
            while bb.get("teleop/enable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting TeleOP change")
                time.sleep(0.1)
            if bb.get("teleop/enable") == True:
                Logger.warn(f"{get_time()}: [VoiceFixedTeleOP] Timed out waiting for TeleOP start")
                bb.set("teleop/enable", False)
                self.quick_return = True

        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if context.error_check():
            return SystemFsmEvent.ERROR
        if self.quick_return:
            return SystemFsmEvent.IDLE

        manual_event = self._manual_idle_event()
        if manual_event != SystemFsmEvent.NONE:
            return manual_event

        move_event = self._voice_movel_wait_event()
        if move_event is not None:
            return move_event

        return self._consume_voice_event(current_mode=self.fixed_mode)

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        bb.set("fixed_constraint_teleop/active_mode", ControlMode.NONE)
        bb.set("fixed_constraint_teleop/reset", True)
        bb.set("control/mode", ControlMode.NONE)

        if bb.get("robot/state/op") == RobotState.TELE_OP:
            bb.set("teleop/disable", True)
            deadline = time.time() + 3.0
            while bb.get("teleop/disable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting TeleOP change")
                time.sleep(0.1)
            if bb.get("teleop/disable") == True:
                Logger.warn(f"{get_time()}: [VoiceFixedTeleOP] Timed out waiting for TeleOP stop")
                bb.set("teleop/disable", False)

        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")


class voice_fixed_point_strategy(voice_fixed_constraint_teleop_strategy):
    fixed_mode = ControlMode.FIXED_POINT
    fixed_state = SystemFsmState.VOICE_FIXED_POINT_CONTROL


class voice_fixed_line_strategy(voice_fixed_constraint_teleop_strategy):
    fixed_mode = ControlMode.FIXED_LINE
    fixed_state = SystemFsmState.VOICE_FIXED_LINE_CONTROL


class voice_fixed_plane_strategy(voice_fixed_constraint_teleop_strategy):
    fixed_mode = ControlMode.FIXED_PLANE
    fixed_state = SystemFsmState.VOICE_FIXED_PLANE_CONTROL


class joystick_control_strategy(Strategy):
    def __init__(self):
        self.zoom_in_active = 0
        self.zoom_out_active = 0
        self.zoom_in_flag = False
        self.zoom_out_flag = False

        self.tilt_cw_active = 0
        self.tilt_ccw_active = 0
        self.tilt_cw_flag = False
        self.tilt_ccw_flag = False
        self.enabled = False
        self.prev_tilt_u_sign = 0
        self.prev_tilt_v_sign = 0
        self.quick_return = False

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.JOYSTICK_CONTROL)
        self.quick_return = False
        bb.set("teleop/enable",True)
        deadline = time.time() + 3.0
        while bb.get("teleop/enable")==True and time.time() < deadline:
            Logger.debug(f"{get_time()}: Waiting TeleOP change")
            time.sleep(0.1)
        if bb.get("teleop/enable")==True:
            Logger.warn(f"{get_time()}: [JOYSTICK] Timed out waiting for TeleOP start")
            bb.set("teleop/enable",False)
            self.quick_return = True

        bb.set("stick/init/left_right", bb.get("stick/left_right"))
        bb.set("stick/init/up_down", bb.get("stick/up_down"))
        bb.set("stick/init/CCW_CW", bb.get("stick/CCW_CW"))


        bb.set("stick/teleop/left_right", 0) 
        bb.set("stick/teleop/up_down",  0) 
        bb.set("stick/teleop/CCW_CW", 0) 

        self.zoom_in_active = 0
        self.zoom_out_active = 0
        self.zoom_in_flag = False
        self.zoom_out_flag = False

        self.tilt_cw_active = 0
        self.tilt_ccw_active = 0
        self.tilt_cw_flag = False
        self.tilt_ccw_flag = False
        self.enabled = True
        self.prev_tilt_u_sign = 0
        self.prev_tilt_v_sign = 0

        

        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")
        pass

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if self.quick_return:
            return SystemFsmEvent.IDLE

        while True: # FSM 루프 자체가 느리기 때문에 while로 안 묶으면 딜레이 생김
            if context.error_check():        
                return SystemFsmEvent.ERROR
            if bb.get("joystick/state/connect")== False:
                return SystemFsmEvent.IDLE # 
            try:
                if len(joystick_manager.event_list) >0:
                    action, value = joystick_manager.event_list.pop(0)
                else:
                    action, value = None, None
            except Empty:
                action, value = None, None
            if action is not None:
                pass
                # print("fsm loop: ",action, value)
            if action==JoystickCommand.ENABLE and value == False:
                self.enabled = False
                return SystemFsmEvent.IDLE
            
            elif bb.get("button/pressed") != 0 :
                status_prefix = "[Enabled]" if self.enabled else "[Disabled]"
                Logger.debug(f"{get_time()}: [JOYSTICK] {status_prefix} Button pressed")
                return SystemFsmEvent.IDLE
            
            elif action in [JoystickCommand.TILT_U, JoystickCommand.TILT_V, JoystickCommand.TILT_W]:
                if action == JoystickCommand.TILT_U: # 좌우
                    bb.set("stick/left_right", value)
                elif action == JoystickCommand.TILT_V: # 앞뒤
                    bb.set("stick/up_down", value)                
                elif action == JoystickCommand.TILT_W: # 상하   
                    bb.set("stick/CCW_CW", value)       

                diff_left_right = bb.get("stick/left_right") - bb.get("stick/init/left_right")
                diff_up_down = bb.get("stick/up_down") - bb.get("stick/init/up_down")
                diff_CCW_CW = bb.get("stick/CCW_CW") - bb.get("stick/init/CCW_CW")

                diff_left_right = joystick_manager.clamp_teleop_delta("tilt_u", diff_left_right)
                diff_up_down = joystick_manager.clamp_teleop_delta("tilt_v", diff_up_down)
                diff_CCW_CW = joystick_manager.clamp_teleop_delta("tilt_w", diff_CCW_CW)

                # diff_left_right = round(float(diff_left_right), 3)
                # diff_up_down = round(float(diff_up_down), 3)
                # diff_CCW_CW = round(float(diff_CCW_CW), 3)

                bb.set("stick/teleop/left_right", diff_left_right) 
                bb.set("stick/teleop/up_down",  diff_up_down) 
                bb.set("stick/teleop/CCW_CW", diff_CCW_CW) 

                # (요청에 따라 텔레옵 축 반영/축 입력 관련 로그는 출력하지 않음)


            elif action == JoystickCommand.ZOOM_OUT:  # 왼쪽
                self.zoom_out_flag = value
                Logger.debug(f"{get_time()}: [JOYSTICK] Zoom out button: {self.zoom_out_flag}")

            elif action == JoystickCommand.ZOOM_IN: # 오른쪽 
                self.zoom_in_flag = value
                Logger.debug(f"{get_time()}: [JOYSTICK] Zoom in button: {self.zoom_in_flag}")


            elif action == JoystickCommand.TILT_W_CCW:  # 왼쪽
                self.tilt_ccw_flag = value
                Logger.debug(f"{get_time()}: [JOYSTICK] Tilt CCW button: {self.tilt_ccw_flag}")

            elif action == JoystickCommand.TILT_W_CW: # 오른쪽 
                self.tilt_cw_flag = value
                Logger.debug(f"{get_time()}: [JOYSTICK] Tilt CW button: {self.tilt_cw_flag}")


            if self.tilt_ccw_flag == True and self.tilt_cw_flag == True:
                self.tilt_cw_active = 0
                self.tilt_ccw_active = 0
            else:
                if self.tilt_ccw_flag == True:
                    self.tilt_ccw_active = 1 
                else:
                    self.tilt_ccw_active = 0

                if self.tilt_cw_flag == True:
                    self.tilt_cw_active = 1 
                else:
                    self.tilt_cw_active = 0

            bb.set("stick/teleop/tilt_cw_active",self.tilt_cw_active) 
            bb.set("stick/teleop/tilt_ccw_active",self.tilt_ccw_active) 

            if self.zoom_in_flag == True and self.zoom_out_flag == True:
                self.zoom_in_active = 0
                self.zoom_out_active = 0
            else:
                if self.zoom_in_flag == True:
                    self.zoom_in_active = 1 # self.zoom_in_count +1 
                else:
                    self.zoom_in_active = 0

                if self.zoom_out_flag == True:
                    self.zoom_out_active = 1 # self.zoom_out_count + 1
                else:
                    self.zoom_out_active = 0


            bb.set("stick/teleop/zoom_in_active",self.zoom_in_active) 
            bb.set("stick/teleop/zoom_out_active",self.zoom_out_active) 

        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        bb.set("teleop/disable",True)
        deadline = time.time() + 3.0
        while bb.get("teleop/disable")==True and time.time() < deadline:
            Logger.debug(f"{get_time()}: Waiting TeleOP change")
            time.sleep(0.1)
        if bb.get("teleop/disable")==True:
            Logger.warn(f"{get_time()}: [JOYSTICK] Timed out waiting for TeleOP stop")
            bb.set("teleop/disable",False)

        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class fixed_constraint_teleop_strategy(Strategy):
    fixed_mode = ControlMode.NONE
    fixed_state = SystemFsmState.NONE

    def __init__(self):
        self.quick_return = False

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm", self.fixed_state)
        bb.set("control/mode", self.fixed_mode)
        bb.set("fixed_constraint_teleop/active_mode", self.fixed_mode)
        bb.set("fixed_constraint_teleop/reset", True)
        self.quick_return = False

        if bb.get("robot/state/op") != RobotState.TELE_OP:
            bb.set("teleop/enable", True) 
            deadline = time.time() + 3.0
            while bb.get("teleop/enable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting TeleOP change")
                time.sleep(0.1)
            if bb.get("teleop/enable") == True:
                Logger.warn(f"{get_time()}: [FixedTeleOP] Timed out waiting for TeleOP start")
                bb.set("teleop/enable", False)
                self.quick_return = True
                return # 텔레옵이 안 켜졌으면 리턴 필요
            

        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if context.error_check():
            return SystemFsmEvent.ERROR

        if self.quick_return:
            return SystemFsmEvent.IDLE

        if bb.get("cockpit/pressed") != True: # 콕핏 릴리즈되면 리턴
            Logger.debug(f"{get_time()}: [FixedTeleOP] Cockpit released")
            return SystemFsmEvent.IDLE
        

        if bb.get("control/desired_mode") != self.fixed_mode: # 컨트롤 모드가 바뀌면 리턴
            Logger.debug(f"{get_time()}: [FixedTeleOP] Desired mode changed")
            return SystemFsmEvent.IDLE

        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        bb.set("fixed_constraint_teleop/active_mode", ControlMode.NONE)
        bb.set("fixed_constraint_teleop/reset", True)
        bb.set("control/mode", ControlMode.NONE)

        if bb.get("robot/state/op") == RobotState.TELE_OP:
            bb.set("teleop/disable", True)
            deadline = time.time() + 3.0
            while bb.get("teleop/disable") == True and time.time() < deadline:
                Logger.debug(f"{get_time()}: Waiting TeleOP change")
                time.sleep(0.1)
            if bb.get("teleop/disable") == True:
                Logger.warn(f"{get_time()}: [FixedTeleOP] Timed out waiting for TeleOP stop")
                bb.set("teleop/disable", False)

        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")


class fixed_point_strategy(fixed_constraint_teleop_strategy):
    fixed_mode = ControlMode.FIXED_POINT
    fixed_state = SystemFsmState.FIXED_POINT_CONTROL


class fixed_line_strategy(fixed_constraint_teleop_strategy):
    fixed_mode = ControlMode.FIXED_LINE
    fixed_state = SystemFsmState.FIXED_LINE_CONTROL


class fixed_plane_strategy(fixed_constraint_teleop_strategy):
    fixed_mode = ControlMode.FIXED_PLANE
    fixed_state = SystemFsmState.FIXED_PLANE_CONTROL

class button_control_strategy(Strategy):
    def __init__(self):
        self.quick_return = True
        self.activated_mode = ControlMode.NONE

    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.BUTTON_CONTROL)
        self.quick_return = True

        button_mode = bb.get("button/mode")
        button_pressed = bb.get("button/pressed")

        if button_pressed == 1: 
            if button_mode in [ControlMode.FREE_MOTION,
                               ControlMode.FIXED_PLANE,
                               ControlMode.FIXED_POINT,
                               ControlMode.FIXED_LINE,
                               ControlMode.FIXED_JOINT]:
                bb.set("teleop/enable",True)
                deadline = time.time() + 3.0
                while bb.get("teleop/enable")==True and time.time() < deadline:
                    Logger.debug(f"{get_time()}: Waiting TeleOP change")
                    time.sleep(0.1)
                if bb.get("teleop/enable")==True:
                    Logger.warn(f"{get_time()}: [BUTTON] Timed out waiting for TeleOP start")
                    bb.set("teleop/enable",False)
                    return

                bb.set("control/mode", button_mode)
                self.activated_mode = button_mode
                self.quick_return = False
        
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")
        # --------------------------------------------


    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if context.error_check():        
            return SystemFsmEvent.ERROR
        if self.quick_return == True:
            return SystemFsmEvent.IDLE        

        button_mode = bb.get("button/mode")
        button_pressed = bb.get("button/pressed")

        if button_pressed != 1: 
            Logger.debug(f"{get_time()}: [BUTTON] button released")
            return SystemFsmEvent.IDLE
        
        else:
            if button_mode != self.activated_mode:
                Logger.debug(f"{get_time()}: [BUTTON] mode changed during operation")
                return SystemFsmEvent.IDLE
        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        bb.set("control/mode", ControlMode.NONE)
        bb.set("teleop/disable",True)
        deadline = time.time() + 3.0
        while bb.get("teleop/disable")==True and time.time() < deadline:
            Logger.debug(f"{get_time()}: Waiting TeleOP change")
            time.sleep(0.1)
        if bb.get("teleop/disable")==True:
            Logger.warn(f"{get_time()}: [BUTTON] Timed out waiting for TeleOP stop")
            bb.set("teleop/disable",False)
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class manual_control_strategy(Strategy):
    def __init__(self):
        self.move_mode = 0
        self.move_flag = False
    def prepare(self, context: SystemContext, **kwargs):
        bb.set("robot/state/fsm",SystemFsmState.MANUAL_CONTROL)
        while True: 
            if bb.get("robot/request/go_home")==False and bb.get("robot/request/go_packaging")==False and bb.get("robot/request/go_setting")==False:
                break
            else:
                Logger.debug(f"{get_time()}: Waiting previous request to finish...")
                time.sleep(0.1)
        self.move_flag = backend_vars.read("MOVE_FLAG")        
        self.move_mode = backend_vars.read("MOVE_MODE")
        
        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")

    def operate(self, context: SystemContext) -> SystemFsmEvent:
        if context.error_check():        
            return SystemFsmEvent.ERROR

        if self.move_flag == True:
            if backend_vars.read("MOVE_FLAG") == False:
                Logger.debug(f"{get_time()}: [MANUAL] Move flag disabled")
                bb.set("robot/request/go_home",False)
                bb.set("robot/request/go_setting",False)
                bb.set("robot/request/go_packaging",False)
                check_home = _is_feature_enabled("check_home", default=True)
                if (not check_home) or bb.get("robot/state/is_home_once"):
                    return SystemFsmEvent.IDLE
                else:
                    return SystemFsmEvent.PREP
            else:
                if self.move_mode == 0:
                        bb.set("robot/request/go_home",True)
                elif self.move_mode == 1:   
                        bb.set("robot/request/go_setting",True)
                elif self.move_mode == 2:   
                        bb.set("robot/request/go_packaging",True)
        else:
            return SystemFsmEvent.IDLE             
        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        bb.set("robot/request/go_home",False)
        bb.set("robot/request/go_setting",False)
        bb.set("robot/request/go_packaging",False)
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")

class debug_motion_strategy(Strategy):
    def __init__(self):
        pass

    def prepare(self, context: SystemContext, **kwargs):        
        bb.set("robot/state/fsm",SystemFsmState.DEBUG_MOTION)
        bb.set("robot/program/play",True)
        while True:
            if bb.get("robot/program/play")==False:
                break
            else:
                Logger.debug(f"{get_time()}: Waiting Program start")
                time.sleep(0.1)

        Logger.debug(f"{get_time()}: [Robot] Enter {self.__class__.__name__} State.")        

    def operate(self, context: SystemContext) -> SystemFsmEvent: 
        if context.error_check(): 
            return SystemFsmEvent.ERROR

        # if bb.get("robot/state/op") == RobotState.OP_IDLE:
        #     if bb.get("robot/state/is_home_once"):
        #         return SystemFsmEvent.IDLE
        #     else:
        #         return SystemFsmEvent.PREP

        if bb.get("robot/request/deactivate_motion")==True:
            bb.set("robot/request/deactivate_motion",False)
            bb.set("robot/program/stop",True)
            while True:
                if bb.get("robot/program/stop")==False:
                    break
                else:
                    Logger.debug(f"{get_time()}: Waiting Program stop")
                    time.sleep(0.1)
            return SystemFsmEvent.NOT_READY
        
        return SystemFsmEvent.NONE

    def exit(self, context: SystemContext, event: OpEvent) -> None:
        Logger.debug(f"{get_time()}: [Robot] Exit {self.__class__.__name__} State.")
