import threading
import traceback
import subprocess
import sys
import math
from pathlib import Path

from modules.constants import DigitalState, SystemFsmState, ROBOT_CONNECTION_LOG_INTERVAL_SEC
from modules.global_data import *
from modules.global_vars import backend_vars, joystick_manager
from modules.robot.control_trace_logger import ControlTraceLogger
from modules.robot.fixed_constraint_teleop import FixedConstraintTeleopController
from pkg.utils.blackboard import GlobalBlackboard

from pkg.utils.file_io import load_json
# import common as common
sys.path.append("./PythonMiddleware")

from modules.global_func import get_time, get_di, _is_feature_enabled
from pkg.utils.logging import Logger
import time

from interfaces.control_socket_client import ControlSocketClient
from interfaces.rtde_socket_client import RTDESocketClient
from interfaces.ethercat_client import EtherCATClient
from interfaces.device_socket_client import DeviceSocketClient
from interfaces.config_socket_client import ConfigSocketClient
from interfaces.conty_test_client import ContySocketClient

bb = GlobalBlackboard()

count_max = 20
count_sleep = 0.05


class RobotCommunication:
    def __init__(self, *args, **kwargs):
        self.init_control_mode = ControlMode.FREE_MOTION
        bb.set("control/desired_mode",self.init_control_mode)
        self.prev_desired_control_mode = self.init_control_mode

        self.home_pos = None
        self.packaging_pos = None
        self.setting_pos = None
        self.tool_pos = None

        self.check_home_threshold = 5

        self.moveJ_vel = 10
        self.moveJ_acc = 50

        
        self.vel_ratio = 0.5
        self.acc_ratio = 10
        self.voice_movel_vel_ratio = 10
        self.voice_movel_acc_ratio = 50
        self.voice_movel_teaching_mode = False
  

        self.smooth_factor = 0.2 # STEP에서 바로 돌릴 땐 이게 맞는 듯
        self.cutoff_freq = 2000
        self.error_gain = 4 # 

        self.robot_enabled = False
        self._next_robot_not_connected_log_time = 0.0

        """ Thread related """
        # self.di_fixed_line = DigitalState.OFF
        # self.di_fixed_point = DigitalState.OFF
        self.di_free_motion = DigitalState.OFF
        self.di_handle = DigitalState.OFF
        # self.di_enable = DigitalState.OFF
        
        self.running = False
        self.thread = None
        self.dcp_thread = None
        self.tele_thread = None
        self.user_input_thread = None
        self.control_thread = None
        self.conty_thread = None

        self.config = load_json("configs/robot_config.json")
        self.use_button = _is_feature_enabled("use_button", default=True)
        self.mimic_conty = _is_feature_enabled("mimic_conty", default=True)
        self.use_teleop_singularity_slowdown = _is_feature_enabled(
            "use_teleop_singularity_slowdown",
            default=True,
        )
        self.control_trace_logger = ControlTraceLogger(
            enabled=_is_feature_enabled("save_control_trace_log", default=False)
        )
        self._control_trace_flag_check_perf = 0.0
        self.fixed_constraint_teleop = FixedConstraintTeleopController()
        self.latest_control_state = None
        self.load_info()

        """ Variables """

        self.robot_state = -1
        self.previous_enable = False
        self.current_cockpit = False
        self.previous_cockpit = False
        self.di_on_number = 0
        self.joint4_limit_min = 90
        self.joint4_limit_max = 270
        self.joint6_limit_min = -110
        self.joint6_limit_max = 65


        ''' Indy command '''
        self.control_data = 0

        self.u_cumulative = 0 
        self.v_cumulative = 0 
        self.w_cumulative = 0 
        self.z_cumulative = 0 
        self.teleop_entry_pose = [0, 0, 0, 0, 0, 0]
        self.teleop_pose_initialized = False

        self.control_client = None
        self.rtde_client = None
        self.ecat_client = None
        self.device_client = None
        self.config_client = None
        self.conty_client = None

        self.t_start = 0
        self.t_end = 0

        self.conty_flag = False
        self.start()
    
    def post_processing(self):
        if bb.get("robot/command_post_processing"):
            """ Post processing """
            self.config_client.SetTeleOpParams(smooth_factor = self.smooth_factor,
                                        cutoff_freq=self.cutoff_freq,
                                        error_gain=self.error_gain)

            bb.set("robot/license_activated",True)

            """ Post processing """
            self.set_tool_property()
            self.set_tool_frame()
            bb.set("robot/command_post_processing",False)    

    def check_connection(self):
        if bb.get("robot/check_connection"):
            self.control_client = ControlSocketClient(self.config["nuri5s"]["ip"])
            self.rtde_client = RTDESocketClient(self.config["nuri5s"]["ip"])
            self.ecat_client = EtherCATClient(self.config["nuri5s"]["ip"])
            self.device_client = DeviceSocketClient(self.config["nuri5s"]["ip"])
            self.config_client = ConfigSocketClient(self.config["nuri5s"]["ip"])

            self.control_data = self.rtde_client.GetControlData()
            if self.control_data == None or not self._is_robot_connected(self.control_data):
                self.robot_enabled = False
                self.robot_state = RobotState.OP_SYSTEM_OFF
                self._log_robot_not_connected()
                bb.set("robot/state/op", self.robot_state)
            else:
                self.robot_enabled = True
                self._next_robot_not_connected_log_time = 0.0
                self.robot_state = self.control_data["op_state"]

            bb.set("robot/enabled", self.robot_enabled)
            bb.set("robot/check_connection",False)
        

    def load_info(self):
        robot_info_path = Path(__file__).resolve().with_name("robot_info.json")
        robot_info = load_json(str(robot_info_path))

        # self.di_adr_fixed_line = robot_info["di_adr"]["fixed_line"]
        # self.di_adr_fixed_point =robot_info["di_adr"]["fixed_point"]
        # self.di_adr_enable =robot_info["di_adr"]["enable"]
        self.di_adr_free_motion =robot_info["di_adr"]["free_motion"]
        self.di_adr_rcm_motion =robot_info["di_adr"]["rcm_motion"]

        self.home_pos = robot_info["home_pos"]
        self.packaging_pos = robot_info["packaging_pos"]
        self.setting_pos = robot_info["setting_pos"]
        self.tool_mass = robot_info["tool_mass"] 
        self.tool_pos = robot_info["tool_pos"] # 툴 포즈 세팅 필요
        if hasattr(self, "fixed_constraint_teleop"):
            self.fixed_constraint_teleop.set_tool_pos(self.tool_pos)

    @staticmethod
    def _finite_values(values):
        try:
            return all(math.isfinite(float(value)) for value in values)
        except (TypeError, ValueError):
            return False

    def set_tool_frame(self):
        self.config_client.SetToolFrame(self.tool_pos)
        self.fixed_constraint_teleop.set_tool_pos(self.tool_pos)
        Logger.debug(f"{get_time()}: [Control] Tool frame set to {self.tool_pos}")
    def set_tool_property(self):
        self.config_client.SetToolProperty(mass= self.tool_mass,
                                           center_of_mass = [0.0,0.0,0.0],
                                           inertia = [0.0,0.0,0.0,0.0,0.0,0.0])
        Logger.debug(f"{get_time()}: [Control] Tool mass set to {self.tool_mass}")

    @staticmethod
    def _is_robot_connected(control_data):
        if not isinstance(control_data, dict):
            return False
        if "is_robot_connected" not in control_data:
            return True
        return bool(control_data.get("is_robot_connected"))

    def _log_robot_not_connected(self):
        current_time = time.monotonic()
        if current_time >= self._next_robot_not_connected_log_time:
            Logger.error(f"{get_time()}: [Control] Robot not connected...")
            self._next_robot_not_connected_log_time = current_time + ROBOT_CONNECTION_LOG_INTERVAL_SEC

    def start(self):
        """ Start the robot communication thread """
        if not self.running:
            self.running = True

            self.dt_dcp_run = 0.001 # 
            self.dt_tele_run = 0.01
            self.dt_user_input_run = 0.001
            self.dt_control_run = 0.001
            self.dt_conty_run = 0.9

            self.dcp_thread = threading.Thread(target=self.dcp_run, daemon=True)
            self.dcp_thread.start() # DCP 명령어. 시간 소요 큼

            self.dt_tele_run = 0.01
            self.tele_thread = threading.Thread(target=self.tele_run, daemon=True)
            self.tele_thread.start() # tele 명령어 수행

            self.dt_user_input_run = 0.1
            self.user_input_thread = threading.Thread(target=self.user_input_run, daemon=True)
            self.user_input_thread.start() # DI, 콕핏 버튼 등

            self.dt_control_run = 0.001
            self.control_thread = threading.Thread(target=self.control_run, daemon=True)
            self.control_thread.start() # 

            if self.mimic_conty:
                self.dt_conty_run = 0.9
                self.conty_thread = threading.Thread(target=self.conty_run, daemon=True)
                self.conty_thread.start() #

    def stop(self):
        if self.running:
            self.running = False
            if self.dcp_thread:
                self.dcp_thread.join()

            if self.tele_thread:
                self.tele_thread.join()

            if self.user_input_thread:
                self.user_input_thread.join()

            if self.control_thread:
                self.control_thread.join()

            if self.conty_thread:
                self.conty_thread.join()

        self.control_trace_logger.stop()

    def get_DCP_robot_data(self):
        self.control_data = self.rtde_client.GetControlData()


        if self.control_data == None or not self._is_robot_connected(self.control_data):
            self.robot_enabled = False
            self.robot_state = RobotState.OP_SYSTEM_OFF

            bb.set("robot/violation/collision",False)
            bb.set("robot/violation/limit",False)
            bb.set("robot/violation/emg",False)  

        else:
            self.robot_enabled = True
            self.robot_state = self.control_data["op_state"]
            bb.set("robot/state/sim_mode", bool(self.control_data.get("sim_mode", False)))


            if self.robot_state == RobotState.OP_COLLISION:
                bb.set("robot/violation/collision",True)
            else:
                bb.set("robot/violation/collision",False)

            if self.robot_state ==RobotState.OP_VIOLATE:
                violation_data = self.rtde_client.GetViolationData()
                violation_code = violation_data['violation_code']
                if violation_code == '128':
                    bb.set("robot/violation/limit",True)
                else:
                    bb.set("robot/violation/limit",False)

                if violation_code == '262144':
                    bb.set("robot/violation/emg",True)
                elif violation_code == '2097152':
                    bb.set("robot/violation/emg",True)
                else:
                    bb.set("robot/violation/emg",False)        
            else:
                bb.set("robot/violation/collision",False)
                bb.set("robot/violation/limit",False)
                bb.set("robot/violation/emg",False)  
            
            control_state = self.rtde_client.GetControlState()
            if control_state == None: 
                self.robot_enabled = False
                self.robot_state = RobotState.OP_SYSTEM_OFF
                self.latest_control_state = None
            else:
                simulated_tau_ext = self._simulated_tau_ext()
                if simulated_tau_ext is not None:
                    control_state = dict(control_state)
                    control_state["tau_ext"] = simulated_tau_ext
                    bb.set("robot/state/sim_mode", True)

                self.latest_control_state = control_state
                bb.set("robot/state/qdata",control_state.get("q", [0, 0, 0, 0, 0, 0])) 
                bb.set("robot/state/qdot",control_state.get("qdot", [0, 0, 0, 0, 0, 0])) 
                bb.set("robot/state/pdata",control_state.get("p", [0, 0, 0, 0, 0, 0])) 
                bb.set("robot/state/pdot",control_state.get("pdot", [0, 0, 0, 0, 0, 0])) 
                bb.set("robot/state/taudata",control_state.get("tau", [0, 0, 0, 0, 0, 0])) 
                bb.set("robot/state/tau_ext",control_state.get("tau_ext", [0, 0, 0, 0, 0, 0])) 

                q = control_state.get("q", [0, 0, 0, 0, 0, 0])
                is_home_pos = all( - self.check_home_threshold <= a - b <= self.check_home_threshold for a, b in zip(q, self.home_pos))
                bb.set("robot/state/is_home",is_home_pos) 
                
                if bb.get("robot/state/is_home_once")==False:
                    if is_home_pos == True:
                        bb.set("robot/state/is_home_once",True)

        prev_op = bb.get("robot/state/op")
        if self.robot_state != prev_op:
            Logger.debug(f"{get_time()}: [Control] OP {prev_op} to {self.robot_state}")
            bb.set("robot/state/op", self.robot_state)
        bb.set("robot/enabled", self.robot_enabled)

    def bb_enable_teleop(self):
        if bb.get("teleop/enable")== True:
            self.start_teleop()
            count = 0
            while True:
                if self.robot_state == RobotState.TELE_OP:
                    break
                else:
                    count = count + 1
                    if count>count_max:
                        count = 0
                        self.start_teleop()
                    time.sleep(count_sleep)
                
            bb.set("teleop/enable", False)        
    def bb_diable_teleop(self):
        if bb.get("teleop/disable")== True:
            self.stop_teleop()
            count = 0
            while True:
                if self.robot_state != RobotState.TELE_OP:
                    break
                else:
                    count = count + 1
                    if count > count_max:
                        count = 0
                        self.stop_teleop()
                    time.sleep(count_sleep)
            bb.set("teleop/disable", False)

    def bb_enable_direct_teaching(self):
            if bb.get("dt/enable")== True:
                self.start_direct_teaching()
                count = 0
                while True:
                    if self.robot_state == RobotState.OP_TEACHING:
                        break
                    else:
                        count = count + 1
                        if count > count_max:
                            count = 0
                            self.start_direct_teaching()
                        time.sleep(count_sleep)
                bb.set("dt/enable", False)

    def bb_disable_direct_teaching(self):
            if bb.get("dt/disable")== True:
                self.stop_direct_teaching()
                count = 0
                while True:
                    if self.robot_state != RobotState.OP_TEACHING:
                        break
                    else:
                        count = count + 1
                        if count > count_max:
                            count = 0
                            self.stop_direct_teaching()
                        time.sleep(count_sleep)
                bb.set("dt/disable", False)


    def start_teleop(self):        
        # self.robot.start_teleop(method=2) # TCP_TASK method=JointTeleopType.RELATIVE
        self.config_client.SetTeleOpParams(smooth_factor = self.smooth_factor,
                                           cutoff_freq=self.cutoff_freq,
                                           error_gain=self.error_gain)
        # smooth_factor, cutoff_freq, error_gain
        self.control_client.StartTeleOp(method=2)
    
    def stop_teleop(self):
        self.control_client.StopTeleOp()

    def start_direct_teaching(self):
        self.control_client.SetDirectTeaching(True)

    def stop_direct_teaching(self):
        self.control_client.SetDirectTeaching(False)

    def handle_fixed_teleop_tau_bias_update(self):
        if bb.get("control/request_tau_bias_update") != True:
            return

        try:
            if self._update_fixed_teleop_tau_bias():
                Logger.info(f"{get_time()}: [Control] Updated fixed teleop tau_bias from current tau_ext")
        finally:
            bb.set("control/request_tau_bias_update", False)
            self._restore_mode_control_highlight()

    def _update_fixed_teleop_tau_bias(self) -> bool:
        samples = []
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            tau_ext = self._current_tau_ext_sample()
            if tau_ext is not None:
                samples.append(tau_ext)
            time.sleep(0.02)

        if not samples:
            Logger.warn(f"{get_time()}: [Control] No valid tau_ext samples for fixed teleop tau_bias")
            return False

        sample_count = len(samples)
        tau_ext = [
            sum(sample[index] for sample in samples) / sample_count
            for index in range(6)
        ]

        try:
            updated_bias = self.fixed_constraint_teleop.update_tau_bias(tau_ext)
        except (OSError, ValueError, TypeError) as exc:
            Logger.warn(f"{get_time()}: [Control] Failed to update fixed teleop tau_bias: {exc}")
            return False

        bb.set("robot/state/tau_ext_bias", updated_bias)
        Logger.info(f"{get_time()}: [Control] Averaged {sample_count} tau_ext samples for fixed teleop tau_bias")
        return True

    def _current_tau_ext_sample(self):
        if isinstance(self.latest_control_state, dict):
            raw_tau_ext = self.latest_control_state.get("tau_ext")
        else:
            raw_tau_ext = bb.get("robot/state/tau_ext")
        try:
            values = [float(raw_tau_ext[index]) for index in range(6)]
        except (TypeError, ValueError, IndexError):
            return None
        if not self._finite_values(values):
            return None
        return values

    def _restore_mode_control_highlight(self) -> None:
        return_mode = backend_vars.read("MODE_CONTROL_RETURN_MODE", "release")
        if not isinstance(return_mode, str) or return_mode == "update_jts":
            return_mode = backend_vars.read("MODE_CONTROL_LAST_ACTIVE_MODE", "release")
        if not isinstance(return_mode, str) or return_mode == "update_jts":
            return_mode = "release"
        backend_vars.write("MODE_CONTROL_MODE", return_mode)
        backend_vars.write("CURRENT_MODE", self._mode_control_label(return_mode))

    @staticmethod
    def _mode_control_label(mode: str) -> str:
        labels = {
            "fixed_joint": "FIXED JOINT",
            "release": "RELEASE",
            "fixed_point": "FIXED POINT",
            "fixed_line": "FIXED LINE",
            "fixed_plane": "FIXED PLANE",
            "update_jts": "UPDATE JTS",
            "rcm": "FIXED PLANE",
        }
        return labels.get(mode, mode)

    @staticmethod
    def _fixed_constraint_state_mode(fsm_state):
        if hasattr(fsm_state, "value"):
            fsm_state = fsm_state.value
        if fsm_state in (
            SystemFsmState.FIXED_POINT_CONTROL.value,
            SystemFsmState.VOICE_FIXED_POINT_CONTROL.value,
        ):
            return ControlMode.FIXED_POINT
        if fsm_state in (
            SystemFsmState.FIXED_LINE_CONTROL.value,
            SystemFsmState.VOICE_FIXED_LINE_CONTROL.value,
        ):
            return ControlMode.FIXED_LINE
        if fsm_state in (
            SystemFsmState.FIXED_PLANE_CONTROL.value,
            SystemFsmState.VOICE_FIXED_PLANE_CONTROL.value,
        ):
            return ControlMode.FIXED_PLANE
        return ControlMode.NONE

    @staticmethod
    def _enum_name(enum_cls, value):
        if hasattr(value, "name") and hasattr(value, "value"):
            return value.name
        if hasattr(value, "value"):
            value = value.value
        try:
            return enum_cls(int(value)).name
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _enum_value(value):
        if hasattr(value, "value"):
            return value.value
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _state_vec(control_state, key):
        if isinstance(control_state, dict):
            value = control_state.get(key)
            if isinstance(value, (list, tuple)):
                return list(value[:6])
        return None

    def _simulated_tau_ext(self):
        if bb.get("robot/simulated_tau/enabled") != True:
            return None
        raw_tau_ext = bb.get("robot/simulated_tau/tau_ext")
        if not isinstance(raw_tau_ext, (list, tuple)) or len(raw_tau_ext) < 6:
            return [0.0] * 6
        try:
            values = [float(raw_tau_ext[index]) for index in range(6)]
        except (TypeError, ValueError):
            return [0.0] * 6
        return values if self._finite_values(values) else [0.0] * 6

    def _publish_fixed_teleop_snapshot(self, fixed_snapshot=None):
        fixed_snapshot = fixed_snapshot or self.fixed_constraint_teleop.snapshot()
        bb.set("fixed_constraint_teleop/snapshot", fixed_snapshot)
        return fixed_snapshot

    def _is_release_trace_state(self, fsm_state):
        fsm_value = self._enum_value(fsm_state)
        if fsm_value in (
            self._enum_value(SystemFsmState.DIRECT_TEACHING),
            self._enum_value(SystemFsmState.VOICE_DIRECT_TEACHING),
        ):
            return True
        if self._enum_value(bb.get("control/desired_mode")) == self._enum_value(ControlMode.FREE_MOTION):
            return True
        if self._enum_value(bb.get("control/mode")) == self._enum_value(ControlMode.FREE_MOTION):
            return True
        if self._enum_value(bb.get("button/mode")) == self._enum_value(ControlMode.FREE_MOTION):
            return True
        return False

    def _log_release_state_trace(self, loop_dt=None, source="dcp_run"):
        if not self.control_trace_logger.enabled:
            return

        fsm_state = bb.get("robot/state/fsm")
        if self._fixed_constraint_state_mode(fsm_state) != ControlMode.NONE:
            return

        robot_state_value = self._enum_value(self.robot_state)
        direct_teaching = (
            robot_state_value == self._enum_value(RobotState.OP_TEACHING)
            or self._enum_value(fsm_state) == self._enum_value(SystemFsmState.DIRECT_TEACHING)
            or self._enum_value(fsm_state) == self._enum_value(SystemFsmState.VOICE_DIRECT_TEACHING)
        )
        if not direct_teaching and not self._is_release_trace_state(fsm_state):
            return

        self._log_control_trace(
            record_type="direct_teaching_sample" if direct_teaching else "release_sample",
            source=source,
            loop_dt=loop_dt,
            skip_reason="direct_teaching" if direct_teaching else "release_mode",
            control_state=self.latest_control_state,
            fixed_snapshot=self.fixed_constraint_teleop.snapshot(),
        )

    def _refresh_control_trace_logger(self, force=False):
        now = time.perf_counter()
        if not force and now - self._control_trace_flag_check_perf < 1.0:
            return
        self._control_trace_flag_check_perf = now
        enabled = _is_feature_enabled("save_control_trace_log", default=False)
        self.control_trace_logger.set_enabled(enabled)

    def _log_control_trace(
        self,
        record_type,
        source,
        loop_dt=None,
        skip_reason="",
        control_state=None,
        fixed_snapshot=None,
        previous_command=None,
        command_delta=None,
        scaled_delta=None,
        sent_command=None,
        move_sent=False,
        move_error="",
        singularity=None,
        joystick_trace=None,
    ):
        if not self.control_trace_logger.enabled:
            return

        fixed_snapshot = fixed_snapshot or self.fixed_constraint_teleop.snapshot()
        singularity = singularity or {}
        joystick_trace = joystick_trace or {}
        joystick_singularity = joystick_trace.get("singularity", {})
        if not isinstance(joystick_singularity, dict):
            joystick_singularity = {}
        desired_mode = bb.get("control/desired_mode")
        button_mode = bb.get("button/mode")
        fsm_state = bb.get("robot/state/fsm")

        record = {
            "record_type": record_type,
            "source": source,
            "skip_reason": skip_reason,
            "last_reason": fixed_snapshot.get("last_reason", ""),
            "loop_dt_sec": loop_dt,
            "robot_enabled": self.robot_enabled,
            "robot_state": self._enum_value(self.robot_state),
            "robot_state_name": self._enum_name(RobotState, self.robot_state),
            "fsm_state": self._enum_value(fsm_state),
            "fsm_state_name": self._enum_name(SystemFsmState, fsm_state),
            "desired_mode": self._enum_value(desired_mode),
            "desired_mode_name": self._enum_name(ControlMode, desired_mode),
            "control_mode": self._enum_value(bb.get("control/mode")),
            "control_mode_name": self._enum_name(ControlMode, bb.get("control/mode")),
            "button_pressed": bb.get("button/pressed"),
            "button_mode": self._enum_value(button_mode),
            "button_mode_name": self._enum_name(ControlMode, button_mode),
            "cockpit_pressed": bb.get("cockpit/pressed"),
            "joystick_connected": bb.get("joystick/state/connect"),
            "joystick_enabled": bb.get("joystick/enabled"),
            "joystick_active_model": getattr(joystick_manager, "active_model_name", ""),
            "joystick_event_queue_len": len(getattr(joystick_manager, "event_list", [])),
            "joystick_axis_deadzone": joystick_trace.get("axis_deadzone", ""),
            "joystick_singularity_sigma_min": joystick_singularity.get("sigma_min", ""),
            "joystick_singularity_condition_number": joystick_singularity.get("condition_number", ""),
            "joystick_singularity_speed_scale": joystick_singularity.get("speed_scale", ""),
            "fixed_active": fixed_snapshot.get("active", False),
            "fixed_controller_state": fixed_snapshot.get("state", ""),
            "fixed_mode": fixed_snapshot.get("mode", ControlMode.NONE),
            "fixed_mode_name": fixed_snapshot.get("mode_name", "inactive"),
            "fixed_reset_requested": bb.get("fixed_constraint_teleop/reset"),
            "restore_enabled": fixed_snapshot.get("restore_enabled", False),
            "restore_saturation": fixed_snapshot.get("restore_saturation", False),
            "tangent_velocity_saturation": fixed_snapshot.get("tangent_velocity_saturation", False),
            "reference_valid": fixed_snapshot.get("reference_valid", False),
            "constraint_error_norm": fixed_snapshot.get("constraint_error_norm", ""),
            "constraint_frame": fixed_snapshot.get("constraint_frame", ""),
            "pose_source": fixed_snapshot.get("pose_source", ""),
            "control_state_ok": isinstance(control_state, dict),
            "move_sent": move_sent,
            "move_error": move_error,
            "vel_ratio": self.vel_ratio,
            "acc_ratio": self.acc_ratio,
            "integration_dt_sec": fixed_snapshot.get("integration_dt", ""),
            "rate_limit_mode": fixed_snapshot.get("rate_limit_mode", ""),
            "task_input_source": fixed_snapshot.get("task_input_source", ""),
            "singularity_sigma_min": singularity.get("sigma_min", ""),
            "singularity_condition_number": singularity.get("condition_number", ""),
            "singularity_speed_scale": singularity.get("speed_scale", ""),
            "q": self._state_vec(control_state, "q") or bb.get("robot/state/qdata"),
            "qdot": self._state_vec(control_state, "qdot") or bb.get("robot/state/qdot"),
            "p": self._state_vec(control_state, "p") or bb.get("robot/state/pdata"),
            "pdot": self._state_vec(control_state, "pdot") or bb.get("robot/state/pdot"),
            "tau": self._state_vec(control_state, "tau") or bb.get("robot/state/taudata"),
            "tau_ext": self._state_vec(control_state, "tau_ext") or bb.get("robot/state/tau_ext"),
            "tau_bias": fixed_snapshot.get("tau_bias"),
            "tau_deadzone": fixed_snapshot.get("tau_deadzone"),
            "task_gain": fixed_snapshot.get("task_gain"),
            "tau_processed": fixed_snapshot.get("tau_processed"),
            "task_wrench": fixed_snapshot.get("task_wrench"),
            "raw_velocity": fixed_snapshot.get("raw_velocity"),
            "tangent_velocity": fixed_snapshot.get("tangent_velocity"),
            "restore_velocity": fixed_snapshot.get("restore_velocity"),
            "restore_limited_velocity": fixed_snapshot.get("restore_limited_velocity"),
            "constrained_velocity": fixed_snapshot.get("constrained_velocity"),
            "limited_velocity": fixed_snapshot.get("limited_velocity"),
            "raw_delta": fixed_snapshot.get("raw_delta"),
            "constrained_delta": fixed_snapshot.get("constrained_delta"),
            "clamped_delta": fixed_snapshot.get("clamped_delta"),
            "last_applied_delta": fixed_snapshot.get("last_applied_delta"),
            "previous_command": previous_command,
            "controller_command": fixed_snapshot.get("last_command"),
            "command_delta": command_delta,
            "scaled_delta": scaled_delta,
            "sent_command": sent_command,
            "joystick_axis_state": joystick_trace.get("axis_state"),
            "joystick_axis_init": joystick_trace.get("axis_init"),
            "joystick_axis_input": joystick_trace.get("axis_input"),
            "joystick_button_input": joystick_trace.get("button_input"),
            "joystick_gain": joystick_trace.get("gain"),
            "joystick_limit": joystick_trace.get("limit"),
            "joystick_raw_delta": joystick_trace.get("raw_delta"),
            "joystick_scaled_delta": joystick_trace.get("scaled_delta"),
            "joystick_applied_delta": joystick_trace.get("applied_delta"),
            "joystick_previous_cumulative": joystick_trace.get("previous_cumulative"),
            "joystick_cumulative": joystick_trace.get("cumulative"),
            "axis_mask": fixed_snapshot.get("axis_mask"),
            "user_axis_mask": fixed_snapshot.get("user_axis_mask"),
            "constraint_vector": fixed_snapshot.get("constraint_vector"),
            "reference_point": fixed_snapshot.get("reference_point"),
            "reference_line_origin": fixed_snapshot.get("reference_line_origin"),
            "reference_line_axis": fixed_snapshot.get("reference_line_axis"),
            "reference_plane_point": fixed_snapshot.get("reference_plane_point"),
            "reference_plane_normal": fixed_snapshot.get("reference_plane_normal"),
            "reference_rcm_point": fixed_snapshot.get("reference_rcm_point"),
            "constraint_error": fixed_snapshot.get("constraint_error"),
            "constraint_error_velocity": fixed_snapshot.get("constraint_error_velocity"),
            "rate_limit": fixed_snapshot.get("rate_limit"),
            "delta_limit": fixed_snapshot.get("delta_limit"),
            "clip_delta_per_tick": fixed_snapshot.get("clip_delta_per_tick"),
            "clip_cumulative": fixed_snapshot.get("clip_cumulative"),
        }
        self.control_trace_logger.log(record)

    def dcp_run(self):
        prev_trace_time = time.perf_counter()
        while self.running: 
            try:  
                self._refresh_control_trace_logger()
                curr_trace_time = time.perf_counter()
                trace_loop_dt = curr_trace_time - prev_trace_time
                prev_trace_time = curr_trace_time

                bb.set("robot/enabled",self.robot_enabled)                
                if self.robot_enabled:
                    self.post_processing()
                    self.get_DCP_robot_data() # 여기엔 robot enabled 안 걸어야 함 
                    self._log_release_state_trace(loop_dt=trace_loop_dt, source="dcp_run")
                    self.control_power()     
                    self.recover_robot()       

                    if self.mimic_conty and self.conty_flag == False:
                        self.conty_client = ContySocketClient(self.config["nuri5s"]["ip"])
                        self.conty_client.LoginWithPassword(self.config["nuri5s"]["conty_password"])
                        self.conty_flag = True
                else:
                    self.check_connection()
                time.sleep(self.dt_dcp_run)

            except Exception as e:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [Control] Exception occurred:\n{tb_str}")
                # self.stop()
                
    def recover_robot(self):
        if bb.get("robot/do_recover"):
            self.control_client.Recover()
            bb.set("robot/do_recover",False)

    def control_power(self):
        if bb.get("robot/request/reboot")==True:
            bb.set("robot/request/reboot",False)
            self.device_client.SetServoAll(False)
            time.sleep(3)
            self._reboot_system()

        if bb.get("robot/request/power_off")==True:
            bb.set("robot/request/power_off",False)
            self.device_client.SetServoAll(False)
            time.sleep(3)
            self._shutdown_system()

    def _reboot_system(self):
        try:
            Logger.info(f"{get_time()}: [Control] System reboot requested")
            subprocess.Popen(["sudo", "reboot"])
        except Exception:
            Logger.error(f"{get_time()}: [Control] Failed to execute system reboot:\n{traceback.format_exc()}")

    def _shutdown_system(self):
        try:
            Logger.info(f"{get_time()}: [Control] System shutdown requested")
            subprocess.Popen(["sudo", "shutdown", "-h", "now"])
        except Exception:
            Logger.error(f"{get_time()}: [Control] Failed to execute system shutdown:\n{traceback.format_exc()}")

    def move_tele(self,tpos = [0,0,0,0,0,0],vel_ratio = 0.5, acc_ratio = 10):
        if self.robot_state==RobotState.TELE_OP:
            self.control_client.MoveTeleLTCP(tpos=tpos,
                                        vel_ratio=vel_ratio, acc_ratio=acc_ratio)
            return True
        return False

    @staticmethod
    def _bb_float(key, default=0.0):
        try:
            return float(bb.get(key))
        except (TypeError, ValueError):
            return float(default)

    def _joystick_trace_snapshot(self, axis_deadzone=None, singularity=None):
        tilt_uv_gain = joystick_manager.get_teleop_gain("tilt_uv")
        tilt_w_gain = joystick_manager.get_teleop_gain("tilt_w")
        zoom_gain = joystick_manager.get_teleop_gain("zoom")
        return {
            "axis_deadzone": (
                joystick_manager.get_teleop_axis_deadzone()
                if axis_deadzone is None
                else axis_deadzone
            ),
            "axis_state": [
                self._bb_float("stick/left_right"),
                self._bb_float("stick/up_down"),
                self._bb_float("stick/CCW_CW"),
            ],
            "axis_init": [
                self._bb_float("stick/init/left_right"),
                self._bb_float("stick/init/up_down"),
                self._bb_float("stick/init/CCW_CW"),
            ],
            "axis_input": [
                self._bb_float("stick/teleop/left_right"),
                self._bb_float("stick/teleop/up_down"),
                self._bb_float("stick/teleop/CCW_CW"),
            ],
            "button_input": [
                self._bb_float("stick/teleop/zoom_in_active"),
                self._bb_float("stick/teleop/zoom_out_active"),
                self._bb_float("stick/teleop/tilt_cw_active"),
                self._bb_float("stick/teleop/tilt_ccw_active"),
            ],
            "gain": [tilt_uv_gain, tilt_uv_gain, tilt_w_gain, zoom_gain],
            "limit": [
                joystick_manager.get_teleop_limit("tilt_u"),
                joystick_manager.get_teleop_limit("tilt_v"),
                joystick_manager.get_teleop_limit("tilt_w"),
                joystick_manager.get_teleop_limit("zoom"),
            ],
            "previous_cumulative": [
                self.u_cumulative,
                self.v_cumulative,
                self.w_cumulative,
                self.z_cumulative,
            ],
            "cumulative": [
                self.u_cumulative,
                self.v_cumulative,
                self.w_cumulative,
                self.z_cumulative,
            ],
            "singularity": singularity or {},
        }

    @staticmethod
    def _joystick_command_from_cumulative(cumulative):
        u, v, w, z = cumulative
        return [0, 0, z, u, v, w]


    def _current_task_pose(self):
        current_pose = bb.get("robot/state/pdata")
        if isinstance(current_pose, (list, tuple)) and len(current_pose) >= 6:
            try:
                return [float(current_pose[i]) for i in range(6)]
            except (TypeError, ValueError):
                pass

        if isinstance(self.latest_control_state, dict):
            current_pose = self.latest_control_state.get("p")
            if isinstance(current_pose, (list, tuple)) and len(current_pose) >= 6:
                try:
                    return [float(current_pose[i]) for i in range(6)]
                except (TypeError, ValueError):
                    pass

        return [0, 0, 0, 0, 0, 0]

    def handle_voice_movel(self):
        if not bb.get("robot/request/voice_movel"):
            return

        bb.set("robot/request/voice_movel",False)
        tpos = bb.get("robot/request/voice_movel_tpos")
        label = bb.get("robot/request/voice_movel_label") or ""

        if not isinstance(tpos, (list, tuple)) or len(tpos) < 6:
            Logger.warn(f"{get_time()}: [Voice] Invalid MoveL request: {tpos}")
            return

        try:
            command = [float(tpos[i]) for i in range(6)]
        except (TypeError, ValueError):
            Logger.warn(f"{get_time()}: [Voice] Invalid MoveL values: {tpos}")
            return

        if self.robot_state == RobotState.OP_MOVING:
            Logger.warn(f"{get_time()}: [Voice] Ignore MoveL while robot is moving: {command}")
            return

        if self.robot_state == RobotState.TELE_OP:
            Logger.warn(f"{get_time()}: [Voice] Ignore MoveL while TeleOP is active: {command}")
            return

        tstart = self._current_task_pose()
        if self.control_client is None:
            Logger.warn(f"{get_time()}: [Voice] Ignore MoveL because control client is unavailable: {command}")
            return

        try:
            result = self.control_client.MoveL(
                tstart=tstart,
                ttarget=command,
                base_type=ControlSocketClient.RELATIVE_TASK,
                vel_ratio=self.voice_movel_vel_ratio,
                acc_ratio=self.voice_movel_acc_ratio,
                teaching_mode=self.voice_movel_teaching_mode,
            )
            Logger.info(f"{get_time()}: [Voice] MoveL relative {command} from {tstart} {label} -> {result}")
        except Exception:
            Logger.error(f"{get_time()}: [Voice] MoveL failed:\n{traceback.format_exc()}")



    def control_cockpit_tele(self, loop_dt=None):
        def slow_down_near_singularity(delta):
            def info(sigma_min="", condition_number="", speed_scale=1.0):
                return {
                    "sigma_min": sigma_min,
                    "condition_number": condition_number,
                    "speed_scale": speed_scale,
                }

            slowdown_config = self.fixed_constraint_teleop.config.get("singularity_slowdown", {})
            if not isinstance(slowdown_config, dict):
                slowdown_config = {}
            singular_sigma_stop = float(slowdown_config.get("sigma_stop", 0.01))
            singular_sigma_slow = float(slowdown_config.get("sigma_slow", 0.12))
            singular_condition_slow = float(slowdown_config.get("condition_slow", 40.0))
            singular_condition_stop = float(slowdown_config.get("condition_stop", 150.0))
            singular_min_scale = float(slowdown_config.get("min_scale", 0.2))
            min_command = 1e-9
            if singular_sigma_stop < 0.0:
                singular_sigma_stop = 0.0
            if singular_sigma_slow <= singular_sigma_stop:
                singular_sigma_slow = singular_sigma_stop + 1e-6
            if singular_condition_slow <= 0.0:
                singular_condition_slow = 1.0
            if singular_condition_stop <= singular_condition_slow:
                singular_condition_stop = singular_condition_slow + 1e-6
            if singular_min_scale < 0.0:
                singular_min_scale = 0.0
            if singular_min_scale > 1.0:
                singular_min_scale = 1.0

            if not self.use_teleop_singularity_slowdown:
                return delta, info()
            if not isinstance(delta, (list, tuple)) or len(delta) < 6:
                return delta, info()
            if all(abs(float(value)) <= min_command for value in delta[:6]):
                return delta, info()

            q_data = bb.get("robot/state/qdata")
            if not q_data or len(q_data) < 6:
                return delta, info()

            try:
                import numpy as np
            except ImportError:
                return delta, info()

            try:
                q_rad = self.fixed_constraint_teleop._q_rad_from_state({"q": q_data})
                if q_rad is None:
                    return delta, info()

                jacobian = self.fixed_constraint_teleop._end_effector_jacobian(q_rad)
                singular_values = np.linalg.svd(jacobian, compute_uv=False)
                if len(singular_values) == 0:
                    return delta, info()

                sigma_min = float(singular_values[-1])
                sigma_max = float(singular_values[0])
                if not math.isfinite(sigma_min) or not math.isfinite(sigma_max):
                    return delta, info()

                if sigma_min <= 1e-12:
                    condition_number = math.inf
                else:
                    condition_number = sigma_max / sigma_min
            except (ValueError, TypeError, np.linalg.LinAlgError, FloatingPointError):
                return delta, info()

            if sigma_min >= singular_sigma_slow:
                sigma_scale = 1.0
            elif sigma_min <= singular_sigma_stop:
                sigma_scale = singular_min_scale
            else:
                ratio = (sigma_min - singular_sigma_stop) / (singular_sigma_slow - singular_sigma_stop)
                sigma_scale = singular_min_scale + (1.0 - singular_min_scale) * ratio

            if condition_number <= singular_condition_slow:
                condition_scale = 1.0
            elif condition_number >= singular_condition_stop:
                condition_scale = singular_min_scale
            else:
                ratio = (singular_condition_stop - condition_number) / (
                    singular_condition_stop - singular_condition_slow
                )
                condition_scale = singular_min_scale + (1.0 - singular_min_scale) * ratio

            speed_scale = max(singular_min_scale, min(sigma_scale, condition_scale))
            return [float(value) * speed_scale for value in delta[:6]], info(
                sigma_min=sigma_min,
                condition_number=condition_number,
                speed_scale=speed_scale,
            )

        fsm_state = bb.get("robot/state/fsm")
        fixed_mode = self._fixed_constraint_state_mode(fsm_state)
        self.fixed_constraint_teleop.reload_config_if_changed()

        if fixed_mode == ControlMode.NONE:
            if self.fixed_constraint_teleop.active:
                self.fixed_constraint_teleop.exit_mode()
                self._log_control_trace(
                    record_type="fixed_exit",
                    source="control_cockpit_tele",
                    loop_dt=loop_dt,
                    skip_reason="fsm_not_fixed",
                    control_state=self.latest_control_state,
                    fixed_snapshot=self.fixed_constraint_teleop.snapshot(),
                )
            self._publish_fixed_teleop_snapshot()
            return

        if self.robot_state != RobotState.TELE_OP:
            if self.fixed_constraint_teleop.active:
                self.fixed_constraint_teleop.exit_mode()
            self._log_control_trace(
                record_type="fixed_skip",
                source="control_cockpit_tele",
                loop_dt=loop_dt,
                skip_reason="robot_not_tele_op",
                control_state=self.latest_control_state,
                fixed_snapshot=self.fixed_constraint_teleop.snapshot(),
            )
            self._publish_fixed_teleop_snapshot()
            return

        entered_fixed_mode = False
        if bb.get("fixed_constraint_teleop/reset"):
            self.fixed_constraint_teleop.enter_mode(fixed_mode)
            bb.set("fixed_constraint_teleop/reset", False)
            entered_fixed_mode = True
        elif self.fixed_constraint_teleop.mode != fixed_mode or not self.fixed_constraint_teleop.active:
            self.fixed_constraint_teleop.enter_mode(fixed_mode)
            entered_fixed_mode = True

        if entered_fixed_mode:
            self._publish_fixed_teleop_snapshot()
            self._log_control_trace(
                record_type="fixed_enter",
                source="control_cockpit_tele",
                loop_dt=loop_dt,
                control_state=self.latest_control_state,
                fixed_snapshot=self.fixed_constraint_teleop.snapshot(),
            )

        if self.latest_control_state is None:
            self._log_control_trace(
                record_type="fixed_skip",
                source="control_cockpit_tele",
                loop_dt=loop_dt,
                skip_reason="missing_control_state",
                control_state=None,
                fixed_snapshot=self.fixed_constraint_teleop.snapshot(),
            )
            self._publish_fixed_teleop_snapshot()
            return

        previous_command = list(self.fixed_constraint_teleop.cumulative_command)
        command = self.fixed_constraint_teleop.update(self.latest_control_state, loop_dt=loop_dt)
        fixed_snapshot = self._publish_fixed_teleop_snapshot()
        if command is None:
            applied_delta = fixed_snapshot.get("last_applied_delta", [0.0] * 6)
            self._log_control_trace(
                record_type="fixed_sample",
                source="control_cockpit_tele",
                loop_dt=loop_dt,
                skip_reason=fixed_snapshot.get("last_reason", "no_command"),
                control_state=self.latest_control_state,
                fixed_snapshot=fixed_snapshot,
                previous_command=previous_command,
                command_delta=applied_delta,
                scaled_delta=applied_delta,
                sent_command=None,
                move_sent=False,
            )
            return

        command_delta = [
            command[index] - previous_command[index]
            for index in range(6)
        ]
        scaled_delta, singularity = slow_down_near_singularity(command_delta)
        command = [
            previous_command[index] + scaled_delta[index]
            for index in range(6)
        ]
        self.fixed_constraint_teleop.cumulative_command = list(command)
        self.fixed_constraint_teleop.last_command = list(command)
        self.fixed_constraint_teleop.last_applied_delta = list(scaled_delta)
        fixed_snapshot = self._publish_fixed_teleop_snapshot()

        move_sent = False
        move_error = ""
        try:
            move_sent = self.move_tele(tpos=command, vel_ratio=self.vel_ratio, acc_ratio=self.acc_ratio)
        except Exception as exc:
            move_error = repr(exc)
            self._log_control_trace(
                record_type="fixed_sample",
                source="control_cockpit_tele",
                loop_dt=loop_dt,
                skip_reason="move_tele_error",
                control_state=self.latest_control_state,
                fixed_snapshot=fixed_snapshot,
                previous_command=previous_command,
                command_delta=command_delta,
                scaled_delta=scaled_delta,
                sent_command=command,
                move_sent=False,
                move_error=move_error,
                singularity=singularity,
            )
            raise

        self._log_control_trace(
            record_type="fixed_sample",
            source="control_cockpit_tele",
            loop_dt=loop_dt,
            control_state=self.latest_control_state,
            fixed_snapshot=fixed_snapshot,
            previous_command=previous_command,
            command_delta=command_delta,
            scaled_delta=scaled_delta,
            sent_command=command,
            move_sent=move_sent,
            move_error=move_error,
            singularity=singularity,
        )



    def control_joystick_tele(self, loop_dt=None):
        def slow_down_near_singularity(u_delta, v_delta, w_delta, z_delta):
            def info(sigma_min="", condition_number="", speed_scale=1.0):
                return {
                    "sigma_min": sigma_min,
                    "condition_number": condition_number,
                    "speed_scale": speed_scale,
                }

            slowdown = joystick_manager.get_teleop_singularity_slowdown()
            singular_sigma_stop = slowdown["sigma_stop"]
            singular_sigma_slow = slowdown["sigma_slow"]
            singular_condition_slow = slowdown["condition_slow"]
            singular_condition_stop = slowdown["condition_stop"]
            singular_min_scale = slowdown["min_scale"]
            min_command = slowdown["min_command"]

            delta = [u_delta, v_delta, w_delta, z_delta]
            if not self.use_teleop_singularity_slowdown:
                return (u_delta, v_delta, w_delta, z_delta), info()
            if all(abs(float(value)) <= min_command for value in delta):
                return (u_delta, v_delta, w_delta, z_delta), info()

            q_data = bb.get("robot/state/qdata")
            if not q_data or len(q_data) < 6:
                return (u_delta, v_delta, w_delta, z_delta), info()

            try:
                import numpy as np
            except ImportError:
                return (u_delta, v_delta, w_delta, z_delta), info()

            try:
                q_rad = self.fixed_constraint_teleop._q_rad_from_state({"q": q_data})
                if q_rad is None:
                    return (u_delta, v_delta, w_delta, z_delta), info()

                jacobian = self.fixed_constraint_teleop._end_effector_jacobian(q_rad)
                singular_values = np.linalg.svd(jacobian, compute_uv=False)
                if len(singular_values) == 0:
                    return (u_delta, v_delta, w_delta, z_delta), info()

                sigma_min = float(singular_values[-1])
                sigma_max = float(singular_values[0])
                if not math.isfinite(sigma_min) or not math.isfinite(sigma_max):
                    return (u_delta, v_delta, w_delta, z_delta), info()

                if sigma_min <= 1e-12:
                    condition_number = math.inf
                else:
                    condition_number = sigma_max / sigma_min
            except (ValueError, TypeError, np.linalg.LinAlgError, FloatingPointError):
                return (u_delta, v_delta, w_delta, z_delta), info()

            if sigma_min >= singular_sigma_slow:
                sigma_scale = 1.0
            elif sigma_min <= singular_sigma_stop:
                sigma_scale = singular_min_scale
            else:
                ratio = (sigma_min - singular_sigma_stop) / (singular_sigma_slow - singular_sigma_stop)
                sigma_scale = singular_min_scale + (1.0 - singular_min_scale) * ratio

            if condition_number <= singular_condition_slow:
                condition_scale = 1.0
            elif condition_number >= singular_condition_stop:
                condition_scale = singular_min_scale
            else:
                ratio = (singular_condition_stop - condition_number) / (
                    singular_condition_stop - singular_condition_slow
                )
                condition_scale = singular_min_scale + (1.0 - singular_min_scale) * ratio

            speed_scale = max(singular_min_scale, min(sigma_scale, condition_scale))
            return (
                (
                    u_delta * speed_scale,
                    v_delta * speed_scale,
                    w_delta * speed_scale,
                    z_delta * speed_scale,
                ),
                info(
                    sigma_min=sigma_min,
                    condition_number=condition_number,
                    speed_scale=speed_scale,
                ),
            )

        if bb.get("robot/state/fsm") == SystemFsmState.JOYSTICK_CONTROL:
            axis_deadzone = joystick_manager.get_teleop_axis_deadzone()
            joystick_trace = self._joystick_trace_snapshot(axis_deadzone=axis_deadzone)
            if self.robot_state==RobotState.TELE_OP:
                if not self.teleop_pose_initialized:
                    current_pose = bb.get("robot/state/pdata")
                    if isinstance(current_pose, (list, tuple)) and len(current_pose) >= 6:
                        self.teleop_entry_pose = [float(current_pose[i]) for i in range(6)]
                    else:
                        self.teleop_entry_pose = [0, 0, 0, 0, 0, 0]
                    self.teleop_pose_initialized = True

                previous_cumulative = [
                    self.u_cumulative,
                    self.v_cumulative,
                    self.w_cumulative,
                    self.z_cumulative,
                ]

                u_axis = self._bb_float("stick/teleop/left_right")
                v_axis = self._bb_float("stick/teleop/up_down")
                if abs(u_axis) < axis_deadzone:
                    u_axis = 0.0
                if abs(v_axis) < axis_deadzone:
                    v_axis = 0.0

                tilt_uv_gain = joystick_manager.get_teleop_gain("tilt_uv")
                u_raw = u_axis * tilt_uv_gain
                v_raw = v_axis * tilt_uv_gain
                w_raw = (
                    self._bb_float("stick/teleop/tilt_ccw_active")
                    - self._bb_float("stick/teleop/tilt_cw_active")
                ) * joystick_manager.get_teleop_gain("tilt_w")
                z_raw = (
                    self._bb_float("stick/teleop/zoom_in_active")
                    - self._bb_float("stick/teleop/zoom_out_active")
                ) * joystick_manager.get_teleop_gain("zoom")

                raw_delta = [u_raw, v_raw, w_raw, z_raw]
                scaled_delta, singularity = slow_down_near_singularity(u_raw, v_raw, w_raw, z_raw)
                u_scaled, v_scaled, w_scaled, z_scaled = scaled_delta
                self.u_cumulative = self.u_cumulative + u_scaled
                self.v_cumulative = self.v_cumulative + v_scaled
                self.w_cumulative = self.w_cumulative + w_scaled
                self.z_cumulative = self.z_cumulative + z_scaled

                self.u_cumulative = joystick_manager.clamp_teleop_delta("tilt_u", self.u_cumulative)
                self.v_cumulative = joystick_manager.clamp_teleop_delta("tilt_v", self.v_cumulative)
                self.w_cumulative = joystick_manager.clamp_teleop_delta("tilt_w", self.w_cumulative)
                self.z_cumulative = joystick_manager.clamp_teleop_delta("zoom", self.z_cumulative)

                cumulative = [
                    self.u_cumulative,
                    self.v_cumulative,
                    self.w_cumulative,
                    self.z_cumulative,
                ]
                applied_delta = [
                    cumulative[index] - previous_cumulative[index]
                    for index in range(4)
                ]
                previous_command = self._joystick_command_from_cumulative(previous_cumulative)
                command = self._joystick_command_from_cumulative(cumulative)
                command_delta = [0, 0, applied_delta[3], applied_delta[0], applied_delta[1], applied_delta[2]]
                scaled_command_delta = [0, 0, z_scaled, u_scaled, v_scaled, w_scaled]
                joystick_trace.update(
                    {
                        "raw_delta": raw_delta,
                        "scaled_delta": list(scaled_delta),
                        "applied_delta": applied_delta,
                        "previous_cumulative": previous_cumulative,
                        "cumulative": cumulative,
                        "singularity": singularity,
                    }
                )

                move_sent = False
                move_error = ""
                try:
                    move_sent = self.move_tele(tpos=command, vel_ratio=self.vel_ratio, acc_ratio=self.acc_ratio)
                except Exception as exc:
                    move_error = repr(exc)
                    self._log_control_trace(
                        record_type="joystick_sample",
                        source="control_joystick_tele",
                        loop_dt=loop_dt,
                        skip_reason="move_tele_error",
                        control_state=self.latest_control_state,
                        previous_command=previous_command,
                        command_delta=command_delta,
                        scaled_delta=scaled_command_delta,
                        sent_command=command,
                        move_sent=False,
                        move_error=move_error,
                        joystick_trace=joystick_trace,
                    )
                    raise

                self._log_control_trace(
                    record_type="joystick_sample",
                    source="control_joystick_tele",
                    loop_dt=loop_dt,
                    control_state=self.latest_control_state,
                    previous_command=previous_command,
                    command_delta=command_delta,
                    scaled_delta=scaled_command_delta,
                    sent_command=command,
                    move_sent=move_sent,
                    move_error=move_error,
                    joystick_trace=joystick_trace,
                )
                # x_target = self.teleop_entry_pose[0]
                # y_target = self.teleop_entry_pose[1]
                # z_target = self.teleop_entry_pose[2] + z
                # u_target = self.teleop_entry_pose[3] + u
                # v_target = self.teleop_entry_pose[4] + v
                # w_target = self.teleop_entry_pose[5] + w

                # self.move_custom_tele( # 이걸 다른 걸로 수정 필요
                #     tpos=[x_target, y_target, z_target, u_target, v_target, w_target],
                #     vel_ratio=self.vel_ratio,
                #     acc_ratio=self.acc_ratio,
                # )
                # print(f"raw=({u:.3f},{v:.3f},{w:.3f}, {z:.3f}) ")
            else:
                self.z_cumulative = 0 
                self.u_cumulative = 0 
                self.v_cumulative = 0 
                self.w_cumulative = 0 
                self.teleop_pose_initialized = False
                joystick_trace.update(
                    {
                        "raw_delta": [0.0, 0.0, 0.0, 0.0],
                        "scaled_delta": [0.0, 0.0, 0.0, 0.0],
                        "applied_delta": [0.0, 0.0, 0.0, 0.0],
                        "cumulative": [0.0, 0.0, 0.0, 0.0],
                    }
                )
                self._log_control_trace(
                    record_type="joystick_skip",
                    source="control_joystick_tele",
                    loop_dt=loop_dt,
                    skip_reason="robot_not_tele_op",
                    control_state=self.latest_control_state,
                    joystick_trace=joystick_trace,
                )
        else:
            self.z_cumulative = 0 
            self.u_cumulative = 0 
            self.v_cumulative = 0 
            self.w_cumulative = 0 
            self.teleop_pose_initialized = False

    def tele_run(self):
        prev_time = time.perf_counter()
        while self.running:
            try:
                if self.robot_enabled:
                    curr_time = time.perf_counter()
                    dt = curr_time - prev_time
                    if dt >= self.dt_tele_run: # 0.01로 했네
                        prev_time = curr_time
                        
                        self.bb_enable_teleop()
                        self.bb_diable_teleop()
                        
                        self.bb_enable_direct_teaching()
                        self.bb_disable_direct_teaching()

                        self.handle_fixed_teleop_tau_bias_update()

            except Exception as e:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [Control] Exception occurred:\n{tb_str}")
                # self.stop()

    def handle_cockpit(self):
        if bb.get("cockpit/simulated/enabled") == True:
            bb.set("cockpit/pressed", bool(bb.get("cockpit/simulated/pressed")))
            return

        if self.ecat_client is None:
            bb.set("cockpit/pressed", False)
            return

        cockpit_data = self.ecat_client.get_endtool_srkey_tx()['din']
        if cockpit_data ==4063:
            bb.set("cockpit/pressed",True)
        else:
            bb.set("cockpit/pressed",False)

        # print(bb.get("cockpit/pressed"))

    def handle_button_io_data(self):        
        di_data = self.device_client.GetEndDI() # di_data[0]['states'][0,1]
        # [{'port': 'B', 'states': [-2, 2]}]
        
        self.di_free_motion = get_di(di_data,self.di_adr_free_motion)
        self.di_handle = get_di(di_data,self.di_adr_rcm_motion)
        
        self.di_on_number = sum(
            1 for state in [
                self.di_free_motion,
                self.di_handle
            ] if state == DigitalState.ON
        )
        if self.di_on_number == 0:
            bb.set("button/mode",ControlMode.FIXED_JOINT)
        elif self.di_on_number == 1:
            if self.di_free_motion == DigitalState.ON:
                bb.set("button/mode",ControlMode.FREE_MOTION)
            elif self.di_handle == DigitalState.ON:
                bb.set("button/mode",self.get_desired_mode())
            else:
                bb.set("button/mode",ControlMode.NONE)                                                
        elif self.di_on_number == 2:
            bb.set("button/mode",ControlMode.NONE)
        bb.set("button/pressed",self.di_on_number)


    def get_desired_mode(self):
        desired_mode = bb.get("control/desired_mode")
        return desired_mode
    
    
    def user_input_run(self):
                
        if not self.use_button:
            bb.set("button/mode", ControlMode.FIXED_JOINT)
            bb.set("button/pressed", 0)

        prev_time = time.perf_counter()
        while self.running:
            try:
                if self.robot_enabled:
                    curr_time = time.perf_counter()
                    dt = curr_time - prev_time
                    if dt >= self.dt_user_input_run:
                        prev_time = curr_time


                        self.handle_cockpit()

                        if self.use_button:
                            self.handle_button_io_data()

                desired_mode = bb.get("control/desired_mode")
                if desired_mode != self.prev_desired_control_mode:
                    Logger.info(
                        f"{get_time()}: [Control] desired_mode changed: "
                        f"{self.prev_desired_control_mode} -> {desired_mode}"
                    )
                    self.prev_desired_control_mode = desired_mode



            except Exception as e:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [Control] Exception occurred:\n{tb_str}")
                # self.stop()


    def control_run(self):
        prev_time = time.perf_counter()
        while self.running:
            try:
                self._refresh_control_trace_logger()
                if self.robot_enabled:
                    curr_time = time.perf_counter()
                    dt = curr_time - prev_time
                    if dt >= self.dt_control_run:
                        prev_time = curr_time

                        self.handle_voice_movel()
                        self.control_cockpit_tele(loop_dt=dt)
                        self.control_joystick_tele(loop_dt=dt) 
                        self.manual_moving()
                        self.debug_motion()

            except Exception as e:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [Control] Exception occurred:\n{tb_str}")
                # self.stop()

    def conty_run(self):
        if not self.mimic_conty:
            return

        prev_time = time.perf_counter()
        while self.running:
            try:
                if self.robot_enabled:
                    curr_time = time.perf_counter()
                    dt = curr_time - prev_time
                    if dt >= self.dt_conty_run:
                        prev_time = curr_time
                if self.conty_flag and self.conty_client is not None:
                    self.conty_client.PingFromConty()

            except Exception as e:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [Control] Exception occurred:\n{tb_str}")
                # self.stop()


    def manual_moving(self):
        # 여기 조건 들어가야 함 
        if bb.get("robot/request/go_home")==True:
            if self.home_pos is not None:         
                self.control_client.MoveJ(
                    jstart=[0,0,0,0,0,0],
                    jtarget=self.home_pos,
                    vel_ratio = self.moveJ_vel,
                    acc_ratio = self.moveJ_acc,                         
                    teaching_mode=True
                )
        elif bb.get("robot/request/go_packaging")==True:
            if self.packaging_pos is not None:            
                self.control_client.MoveJ(
                    jstart=[0,0,0,0,0,0],
                    jtarget=self.packaging_pos,         
                    vel_ratio = self.moveJ_vel,
                    acc_ratio = self.moveJ_acc,                         
                    teaching_mode=True
                )
        elif bb.get("robot/request/go_setting")==True:
            if self.setting_pos is not None:            
                self.control_client.MoveJ(
                    jstart=[0,0,0,0,0,0],
                    jtarget=self.setting_pos,   
                    vel_ratio = self.moveJ_vel,
                    acc_ratio = self.moveJ_acc,                               
                    teaching_mode=True
                )

    def debug_motion(self):
        if bb.get("robot/request/motion_start")==True:
            bb.set("robot/request/motion_start",False)
            if bb.get("robot/state/fsm") in [SystemFsmState.PREP, SystemFsmState.IDLE]:
                bb.set("robot/request/activate_motion",True)
        

        if bb.get("robot/request/motion_stop")==True:
            bb.set("robot/request/motion_stop",False)
            bb.set("robot/request/deactivate_motion",True)

        if bb.get("robot/program/play"):
            while True:
                program_data = self.rtde_client.GetProgramData()
                if program_data["program_state"] == 1: 
                    break
                else:            
                    self.control_client.PlayProgram(prog_idx=1)
                    time.sleep(0.1)
                    Logger.debug(f"{get_time()}: [Robot] wait for play program...")        

            bb.set("robot/program/play",False)

        if bb.get("robot/program/stop"):
            while True:
                program_data = self.rtde_client.GetProgramData()
                if program_data["program_state"] != 1:  # 러닝이 아닐 때 바꾸게 
                    break
                else:            
                    self.control_client.StopProgram()
                    time.sleep(0.1)
                    Logger.debug(f"{get_time()}: [Robot] wait for stop program...")        
            
            while True:
                program_data = self.rtde_client.GetProgramData()
                if program_data["program_state"] == 0:  
                    break
                else:            

                    Logger.debug(f"{get_time()}: [Robot] wait for program set to be IDLE...")                
            bb.set("robot/program/stop",False)
