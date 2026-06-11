from pathlib import Path
from typing import Any, Dict, Optional

from pkg.utils.file_io import load_json


JOYSTICK_INFO_PATH = Path(__file__).resolve().with_name("joystick_info.json")

DEFAULT_INPUT = {
    "deadzone": 0.2,
    "axis_gain": 1.0,
    "round_digit": 2,
    "poll_interval_sec": 1.0,
}

DEFAULT_TELEOP_GAIN = {
    "zoom": 0.05,
    "tilt_w": 0.05,
    "tilt_uv": 0.05,
}

DEFAULT_TELEOP_LIMIT = {
    "zoom": 100.0,
    "tilt_w": 30.0,
    "tilt_u": 15.0,
    "tilt_v": 15.0,
}

DEFAULT_TELEOP_AXIS_DEADZONE = 0.1

DEFAULT_TELEOP_SINGULARITY_SLOWDOWN = {
    "sigma_stop": 0.01,
    "sigma_slow": 0.12,
    "condition_slow": 40.0,
    "condition_stop": 150.0,
    "min_scale": 0.2,
    "min_command": 1e-9,
}


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class JoystickSettings:
    def __init__(self, joystick_info: Optional[Dict[str, Any]] = None):
        self.joystick_info = joystick_info or {}

    @classmethod
    def load(cls, path: Path = JOYSTICK_INFO_PATH) -> "JoystickSettings":
        try:
            return cls(load_json(str(path)))
        except OSError:
            return cls({})

    def supported_names(self):
        names = self.joystick_info.get("supported_names", [])
        return names if isinstance(names, list) else []

    def controllers(self):
        controllers = self.joystick_info.get("controllers", {})
        return controllers if isinstance(controllers, dict) else {}

    def input_deadzone(self) -> float:
        return _as_float(self._input_config().get("deadzone"), DEFAULT_INPUT["deadzone"])

    def axis_gain(self) -> float:
        return _as_float(self._input_config().get("axis_gain"), DEFAULT_INPUT["axis_gain"])

    def round_digit(self) -> int:
        return max(0, _as_int(self._input_config().get("round_digit"), DEFAULT_INPUT["round_digit"]))

    def poll_interval_sec(self) -> float:
        interval = _as_float(
            self._input_config().get("poll_interval_sec"),
            DEFAULT_INPUT["poll_interval_sec"],
        )
        return max(0.001, interval)

    def teleop_axis_deadzone(self) -> float:
        return _as_float(self._teleop_config().get("axis_deadzone"), DEFAULT_TELEOP_AXIS_DEADZONE)

    def teleop_gain(self, key: str) -> float:
        default = DEFAULT_TELEOP_GAIN.get(key, 0.0)
        return _as_float(self._teleop_gain_config().get(key), default)

    def teleop_limit(self, key: str) -> Optional[float]:
        config = self._teleop_limit_config()
        if key not in config:
            return DEFAULT_TELEOP_LIMIT.get(key)

        value = config.get(key)
        if value is None:
            return None
        return _as_float(value, DEFAULT_TELEOP_LIMIT.get(key, 0.0))

    def teleop_singularity_slowdown(self) -> Dict[str, float]:
        raw = self._teleop_config().get("singularity_slowdown", {})
        config = raw if isinstance(raw, dict) else {}
        return {
            key: _as_float(config.get(key), default)
            for key, default in DEFAULT_TELEOP_SINGULARITY_SLOWDOWN.items()
        }

    def clamp_teleop_delta(self, key: str, value: float) -> float:
        limit = self.teleop_limit(key)
        if limit is None:
            return value
        return max(-limit, min(limit, value))

    def _input_config(self) -> Dict[str, Any]:
        config = self.joystick_info.get("input", {})
        return config if isinstance(config, dict) else {}

    def _teleop_config(self) -> Dict[str, Any]:
        config = self.joystick_info.get("teleop", {})
        return config if isinstance(config, dict) else {}

    def _teleop_gain_config(self) -> Dict[str, Any]:
        teleop_gain = self._teleop_config().get("gain")
        if isinstance(teleop_gain, dict):
            return teleop_gain

        legacy_gain = self.joystick_info.get("control_gain", {})
        return legacy_gain if isinstance(legacy_gain, dict) else {}

    def _teleop_limit_config(self) -> Dict[str, Any]:
        teleop_limit = self._teleop_config().get("limit")
        if isinstance(teleop_limit, dict):
            return teleop_limit

        legacy_limit = self.joystick_info.get("max_delta", {})
        return legacy_limit if isinstance(legacy_limit, dict) else {}
