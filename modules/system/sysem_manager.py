import threading
import json
import traceback
import shutil
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

from modules.constants import DigitalState, SystemFsmState
from modules.global_data import *
from modules.global_func import get_time
from pkg.utils.blackboard import GlobalBlackboard

from pkg.utils.file_io import load_json, save_json

from pkg.utils.logging import Logger

from modules.global_vars import backend_vars


bb = GlobalBlackboard()


class SystemManager:
    _SEVERITY_ORDER = {"error": 0, "resolved": 1, "info": 2}
    _KOREAN_KEY_MAP = {
        "시간": "time",
        "종류": "code",
        "내용": "message",
        "조치": "action",
        "조치시간": "action_time",
        "id": "id",
        "severity": "severity",
    }
    _SEVERITY_ALIASES = {
        "에러": "error",
        "error": "error",
        "조치완료": "resolved",
        "resolved": "resolved",
        "정보": "info",
        "info": "info",
    }
    _ALARM_TEMPLATE_MAP = {template["code"]: template for template in ALARM_TEMPLATES}

    def __init__(self):
        pass
        """ Thread related """

        self.running = False
        self.thread = None
        self.alarm_thread = None
       
        """ Variables """
        self.start()

    def _current_alarms(self) -> List[Dict]:
        alarms = backend_vars.read("ALARMS", {})
        if not isinstance(alarms, dict):
            return []

        entries = []
        for entry in alarms.values():
            if isinstance(entry, dict):
                entries.append(self._normalize_entry(dict(entry)))
        return entries

    def _parse_time_value(self, value: str) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
            try:
                parsed = datetime.strptime(value, fmt)
                if fmt == "%H:%M:%S":
                    parsed = datetime.combine(datetime.now().date(), parsed.time())
                return parsed.timestamp()
            except (ValueError, OSError):
                continue
        return 0.0

    def _sorted_alarms(self, entries: List[Dict]) -> List[Dict]:
        def sort_key(entry: Dict) -> tuple:
            severity = self._entry_severity(entry)
            priority = self._SEVERITY_ORDER.get(str(severity), len(self._SEVERITY_ORDER))
            timestamp_value = -self._parse_time_value(entry.get("time"))
            return (priority, timestamp_value, str(entry.get("message", "")))

        return sorted(entries, key=sort_key)

    def _entry_severity(self, entry: Dict) -> str:
        severity = entry.get("severity")
        if severity:
            return self._SEVERITY_ALIASES.get(str(severity), str(severity))

        legacy_type = str(entry.get("code", ""))
        if legacy_type in self._SEVERITY_ALIASES:
            return self._SEVERITY_ALIASES[legacy_type]

        return "info"

    def _normalize_entry(self, entry: Dict) -> Dict:
        normalized: Dict[str, Optional[str]] = {}
        for key, value in entry.items():
            mapped_key = self._KOREAN_KEY_MAP.get(key, key)
            normalized[mapped_key] = value

        severity = normalized.get("severity")
        if severity:
            normalized["severity"] = self._SEVERITY_ALIASES.get(str(severity), str(severity))

        self._apply_template(normalized)
        return normalized

    def _apply_template(self, entry: Dict) -> None:
        code = entry.get("code")
        if not code:
            return

        template = self._ALARM_TEMPLATE_MAP.get(code)
        if not template:
            return

        entry["message"] = template.get("message")
        entry["action"] = template.get("action")
        current_severity = self._SEVERITY_ALIASES.get(str(entry.get("severity", "")), "")
        if current_severity != "resolved":
            entry["severity"] = self._SEVERITY_ALIASES.get(template.get("severity", "info"), "info")

    def _save_alarms(self, entries: List[Dict]) -> Dict:
        ordered_entries = self._sorted_alarms(entries)
        reordered: Dict[str, Dict] = {}
        for index, entry in enumerate(ordered_entries, start=1):
            reordered[f"list_{index}"] = entry

        backend_vars.update(
            {
                "ALARMS": reordered,
                "ALARMS_LAST_UPDATED": datetime.utcnow().isoformat() + "Z",
            }
        )

        return reordered

    def append_alarm(
        self,
        code: str,
        message: Optional[str] = None,
        action: Optional[str] = None,
        alarm_id: int = 0,
        timestamp: Optional[str] = None,
        severity: str = "info",
    ) -> Dict:
        timestamp = timestamp or time.strftime("%H:%M:%S")
        entries = self._current_alarms()
        normalized_severity = self._SEVERITY_ALIASES.get(str(severity), str(severity))
        entry = {
            "time": timestamp,
            "code": code,
            "message": message,
            "action": action,
            "id": alarm_id,
            "severity": normalized_severity,
        }
        self._apply_template(entry)

        if entry["severity"] == "error":
            if any(
                existing.get("code") == code and self._entry_severity(existing) == "error"
                for existing in entries
            ):
                return {"ignored": True, "alarms": self._save_alarms(entries)}

        entries.append(entry)
        return {"alarms": self._save_alarms(entries)}

    def modify_alarm(
        self,
        alarm_id: int,
        code: Optional[str] = None,
        message: Optional[str] = None,
        action: Optional[str] = None,
        timestamp: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> Dict:
        entries = self._current_alarms()
        updated = False

        for entry in entries:
            if entry.get("id") == alarm_id:
                if code:
                    entry["code"] = code
                if message:
                    entry["message"] = message
                if action:
                    entry["action"] = action
                if severity:
                    entry["severity"] = self._SEVERITY_ALIASES.get(str(severity), str(severity))
                entry["time"] = timestamp or entry.get("time") or time.strftime("%H:%M:%S")
                self._apply_template(entry)
                updated = True
                break

        if not updated:
            return {"updated": False, "alarms": self._save_alarms(entries)}

        return {"updated": True, "alarms": self._save_alarms(entries)}

    def resolve_alarm(
        self,
        code: str,
        action: Optional[str] = None,
        action_time: Optional[str] = None,
    ) -> Dict:
        entries = self._current_alarms()
        updated = False
        action_time = action_time or time.strftime("%H:%M:%S")

        for entry in entries:
            if entry.get("code") == code and self._entry_severity(entry) == "error":
                entry["severity"] = "resolved"
                entry["action_time"] = action_time
                if action:
                    entry["action"] = action
                updated = True

        if not updated:
            return {"updated": False, "alarms": self._save_alarms(entries)}

        return {"updated": True, "alarms": self._save_alarms(entries)}

    def delete_alarm(self, alarm_id: int) -> Dict:
        entries = self._current_alarms()
        filtered = [entry for entry in entries if entry.get("id") != alarm_id]
        return {"alarms": self._save_alarms(filtered)}

    def load_info(self):
        pass

    def start(self):
        """ Start the robot communication thread """
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.alarm_thread = threading.Thread(
                target=self.handle_alarm_monitoring, daemon=True
            )
            self.alarm_thread.start()

    def stop(self):
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
            if self.alarm_thread:
                self.alarm_thread.join()

    def run(self):
        while self.running:
            try:
                self.print_status()
                self.get_user_mode()
                self.handle_recovery()
                self.handle_voice_control()
                self.check_reboot_or_power_off()
                self.check_robot_motion()
                time.sleep(0.1)

            except Exception as e:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [System] Exception occurred:\n{tb_str}")
                self.stop()

    def handle_voice_control(self):
        # VOICE_CONTROL_ACTIVE
        voice_flag = backend_vars.read("VOICE_CONTROL_FLAG", False)
        # print("catch voice flag")
        voice_start_stop = backend_vars.read("VOICE_CONTROL_ACTIVE", False) # start stop
        if voice_flag == True: # 활성화됨
            backend_vars.write("VOICE_CONTROL_FLAG", False)
            if voice_start_stop==True:
                print("start recording")
                bb.set("voice/recording/start",True)
            else:
                print("stop recording")
                bb.set("voice/recording/stop",True)
        # wants_listening = backend_vars.read("VOICE_CONTROL_ACTIVE", False)

        pass

    def handle_alarm_monitoring(self):
        while self.running:
            try:

                if bb.get("joystick/state/connect")== False:
                    self.append_alarm(code="ER-CON-001")
                else:
                    self.resolve_alarm(code="ER-CON-001")
                
                if bb.get("robot/enabled") == False:
                    self.append_alarm(code="ER-FW-001")
                else:
                    self.resolve_alarm(code="ER-FW-001")
                
                if bb.get("robot/violation/collision"):                    
                    self.append_alarm(code="ER-RB-001")
                else:
                    self.resolve_alarm(code="ER-RB-001")

                if bb.get("robot/violation/limit"):
                    self.append_alarm(code="ER-RB-002")
                else:
                    self.resolve_alarm(code="ER-RB-002")
                
                if bb.get("robot/violation/emg"):
                    self.append_alarm(code="ER-EMG-001")
                else:
                    self.resolve_alarm(code="ER-EMG-001")

                time.sleep(0.2)
            except Exception:
                tb_str = traceback.format_exc()
                Logger.error(f"{get_time()}: [System] Alarm monitoring exception:\n{tb_str}")
                time.sleep(0.5)

    def print_status(self):
        system_status = backend_vars.read("SYSTEM_STATUS")
        fsm_mode = bb.get("robot/state/fsm")
        if fsm_mode == SystemFsmState.NONE:
            system_fsm_mode = "정지"
        elif fsm_mode == SystemFsmState.NOT_READY:
            system_fsm_mode = "준비 안 됨"
        elif fsm_mode == SystemFsmState.IDLE:
            system_fsm_mode = "대기"
        elif fsm_mode == SystemFsmState.PREP:
            system_fsm_mode = "준비"
        elif fsm_mode == SystemFsmState.ERROR:
            system_fsm_mode = "에러 발생"
        elif fsm_mode == SystemFsmState.RECOVER:
            system_fsm_mode = "복구 중"
        elif fsm_mode == SystemFsmState.VOICE_CONTROL:
            system_fsm_mode = "음성 제어"
        elif fsm_mode == SystemFsmState.VOICE_DIRECT_TEACHING:
            system_fsm_mode = "Voice direct teaching"
        elif fsm_mode == SystemFsmState.VOICE_FIXED_POINT_CONTROL:
            system_fsm_mode = "Voice fixed point teleop"
        elif fsm_mode == SystemFsmState.VOICE_FIXED_LINE_CONTROL:
            system_fsm_mode = "Voice fixed line teleop"
        elif fsm_mode == SystemFsmState.VOICE_FIXED_PLANE_CONTROL:
            system_fsm_mode = "Voice fixed plane teleop"
        elif fsm_mode == SystemFsmState.JOYSTICK_CONTROL:
            system_fsm_mode = "컨트롤러 제어"
        elif fsm_mode == SystemFsmState.BUTTON_CONTROL:
            if bb.get("button/mode") ==ControlMode.FREE_MOTION:
                button_mode = "자유 이동"
            elif bb.get("button/mode") ==ControlMode.FIXED_PLANE:
                button_mode = "고정 면"
            elif bb.get("button/mode") ==ControlMode.FIXED_POINT:
                button_mode = "고정 점"
            elif bb.get("button/mode") ==ControlMode.FIXED_LINE:
                button_mode = "고정 선"
            elif bb.get("button/mode") ==ControlMode.FIXED_JOINT:
                button_mode = "고정 위치"
            else:
                button_mode = "Unknown"
            system_fsm_mode = "버튼 제어 - " + button_mode
        elif fsm_mode == SystemFsmState.FIXED_POINT_CONTROL:
            system_fsm_mode = "Fixed point teleop"
        elif fsm_mode == SystemFsmState.FIXED_LINE_CONTROL:
            system_fsm_mode = "Fixed line teleop"
        elif fsm_mode == SystemFsmState.FIXED_PLANE_CONTROL:
            system_fsm_mode = "Fixed plane teleop"
        elif fsm_mode == SystemFsmState.UPDATE_GAIN:
            system_fsm_mode = "게인 업데이트 중"
        elif fsm_mode == SystemFsmState.MANUAL_CONTROL:
            system_fsm_mode = "수동 제어"
        elif fsm_mode == SystemFsmState.DIRECT_TEACHING:
            system_fsm_mode = "직접 교시"
        else:
            system_fsm_mode = "알려지지 않은 모드"
        system_status["operating_mode"] = str(system_fsm_mode)
        if fsm_mode in [SystemFsmState.NONE, SystemFsmState.NOT_READY, SystemFsmState.ERROR, SystemFsmState.RECOVER]:
            system_status["operating_mode_color"] = "red"
        elif fsm_mode in [SystemFsmState.IDLE, SystemFsmState.PREP]:
            system_status["operating_mode_color"] = "black"
        else:
            system_status["operating_mode_color"] = "green"

        ## 
        joystick_connected = bool(bb.get("joystick/state/connect"))
        if joystick_connected:
            joysticK_connection = "연결됨"
        else:
            joysticK_connection = "연결 안 됨"
        system_status["controller_connection"] = str(joysticK_connection)
        system_status["controller_connection_color"] = "green" if joystick_connected else "red"

        robot_connected = bool(bb.get("robot/enabled"))
        if robot_connected:
            robot_connection = "연결됨"
        else:
            robot_connection = "연결 안 됨"
        # robot_connection = "연결됨"
        system_status["robot_drive"] = str(robot_connection)
        system_status["robot_drive_color"] = "green" if robot_connected else "red"

        ##
        current_mode = bb.get("control/mode")
        if current_mode == ControlMode.FIXED_JOINT:
            disp_mode = "Fixed joint"
        elif current_mode == ControlMode.FREE_MOTION:
            disp_mode = "Free motion"
        elif current_mode == ControlMode.FIXED_POINT:
            disp_mode = "Fixed point"
        elif current_mode == ControlMode.FIXED_LINE:
            disp_mode = "Fixed line"
        elif current_mode == ControlMode.UPDATE_JTS:
            disp_mode = "Update JTS"
        elif current_mode == ControlMode.FIXED_PLANE:
            disp_mode = "Fixed plane"
        else:
            disp_mode = "Unknown"
        backend_vars.write("CURRENT_MODE",str(disp_mode))
        # print("fsm_mode : ",fsm_mode)
        fsm_available = fsm_mode not in [
            SystemFsmState.NONE,
            SystemFsmState.NOT_READY,
            SystemFsmState.ERROR,
            SystemFsmState.RECOVER,
        ]
        if fsm_available and robot_connected:
            system_status["status"] = str("정상 가동")
            system_status["status_color"] = "green"            
        else:
            system_status["status"] = str("비정상 가동")
            system_status["status_color"] = "red"

        backend_vars.write("SYSTEM_STATUS", system_status)

    def handle_recovery(self):
        recovery_flag = backend_vars.read("RECOVER_FLAG", False)
        if recovery_flag == True:
            if bb.get("robot/state/fsm")==SystemFsmState.ERROR:
                bb.set("robot/request_recover",True)            
    
    def get_user_mode(self):
        mode_flag = backend_vars.read("MODE_CONTROL_FLAG",False)
        if mode_flag == True:
            target_mode = backend_vars.read("MODE_CONTROL_MODE")
            print(target_mode)
            if target_mode in ["fixed_plane", "rcm"]:
                bb.set("control/desired_mode",ControlMode.FIXED_PLANE)

            elif target_mode == "fixed_joint":
                bb.set("control/desired_mode",ControlMode.FIXED_JOINT)

            elif target_mode =="fixed_point":
                bb.set("control/desired_mode",ControlMode.FIXED_POINT)

            elif target_mode =="fixed_line":
                bb.set("control/desired_mode",ControlMode.FIXED_LINE)

            elif target_mode =="release":
                bb.set("control/desired_mode",ControlMode.FREE_MOTION)

            elif target_mode =="update_jts":
                bb.set("control/request_jts_update",True)
                
            backend_vars.write("MODE_CONTROL_FLAG",False)
    def check_reboot_or_power_off(self):
        if backend_vars.read("REBOOT_FLAG") == True:
            backend_vars.write("REBOOT_FLAG",False)
            bb.set("robot/request/reboot", True)
    
        if backend_vars.read("POWER_OFF_FLAG") == True:
            backend_vars.write("POWER_OFF_FLAG",False)
            bb.set("robot/request/power_off", True)

    def check_robot_motion(self):
        if backend_vars.read("MOTION_START_FLAG") == True:
            backend_vars.write("MOTION_START_FLAG",False)
            bb.set("robot/request/motion_start", True)
    
        if backend_vars.read("MOTION_STOP_FLAG") == True:
            backend_vars.write("MOTION_STOP_FLAG",False)
            bb.set("robot/request/motion_stop", True)
