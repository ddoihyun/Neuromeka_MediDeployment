"""Shared global singletons separated from configuration constants."""

from modules.global_data import Use_Joystick, Use_Voice
from modules.backend.backend_vars import BackendVars

if Use_Voice:
    from modules.voice.voice_manager import VoiceManager  # noqa: WPS433

    voice_manager = VoiceManager()
else:
    voice_manager = None

if Use_Joystick:
    from modules.joystick.joystick_manager import JoystickManager  # noqa: WPS433

    joystick_manager = JoystickManager()
else:
    from pkg.utils.blackboard import GlobalBlackboard
    from modules.joystick.joystick_settings import JoystickSettings

    class DummyJoystickManager:
        """Fallback joystick manager used when joystick is disabled."""

        def __init__(self):
            self.settings = JoystickSettings.load()
            self.event_list = []
            self._bb = GlobalBlackboard()
            self._bb.set("joystick/state/connect", True)

        def start(self):
            self._bb.set("joystick/state/connect", True)

        def stop(self):
            """Maintain interface parity with real manager."""
            return None

        def handle_event(self, event):
            return None, None

        def poll_inputs(self):
            self._bb.set("joystick/state/connect", True)

        def inject_event(self, action, value):
            self.event_list.append((action, value))

        def get_teleop_gain(self, key):
            return self.settings.teleop_gain(key)

        def get_teleop_limit(self, key):
            return self.settings.teleop_limit(key)

        def get_teleop_axis_deadzone(self):
            return self.settings.teleop_axis_deadzone()

        def get_teleop_singularity_slowdown(self):
            return self.settings.teleop_singularity_slowdown()

        def clamp_teleop_delta(self, key, value):
            return self.settings.clamp_teleop_delta(key, value)

    joystick_manager = DummyJoystickManager()

backend_vars = BackendVars(
    {
        "MOVE_MODE": 0,
        "MOVE_FLAG": False,
        "RECOVER_FLAG": False,
        "REBOOT_FLAG": False,
        "POWER_OFF_FLAG": False,
        "MODE_CONTROL_FLAG": False,
        "MODE_CONTROL_MODE": "release",
        "MODE_CONTROL_LAST_ACTIVE_MODE": "release",
        "MODE_CONTROL_RETURN_MODE": "release",
        "POWER_REQUEST": "-",
        "CURRENT_MODE": "RELEASE",
        "VOICE_CONTROL_ACTIVE": False,
        "VOICE_CONTROL_FLAG": False,
        "ALARMS": {},
        "ALARMS_LAST_UPDATED": None,
        "MOTION_START_FLAG": False,
        "MOTION_STOP_FLAG": False,
        
        # "VOICE_CONTROL_LAST_AUDIO": None,
        # "VOICE_CONTROL_LAST_RESULT": None,
        "SYSTEM_STATUS": {
            "status": "비정상 가동",
            "status_color": "red",
            "operating_mode": "대기",
            "operating_mode_color": "black",
            "robot_drive": "연결 안 됨",
            "robot_drive_color": "red",
            "controller_connection": "연결 안 됨",
            "controller_connection_color": "red",
            "version": "1.0",
            "version_color": "black",
            "last_updated": None,
        },
    }
)
