"""FastAPI application exposing the backend API for the Surgical UI."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from threading import Lock
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from modules.backend.variable_manager import variable_manager
from modules.global_data import JoystickCommand
from modules.global_vars import backend_vars, joystick_manager
from pkg.utils.blackboard import GlobalBlackboard


logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:3190",
    "http://127.0.0.1:3190",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

_cb_state_lock = Lock()
_cb_state: Dict[str, Any] = {
    "reboot_requested": False,
    "reboot_requested_at": None,
    "reboot_acknowledged": False,
    "reboot_acknowledged_at": None,
    "reboot_response_text": None,
    "shutdown_requested": False,
    "shutdown_requested_at": None,
    "shutdown_acknowledged": False,
    "shutdown_acknowledged_at": None,
    "shutdown_response_text": None,
    "motion_request": None,
    "motion_start_requested": False,
    "motion_start_requested_at": None,
    "motion_start_acknowledged": False,
    "motion_start_acknowledged_at": None,
    "motion_start_response_text": None,
    "motion_stop_requested": False,
    "motion_stop_requested_at": None,
    "motion_stop_acknowledged": False,
    "motion_stop_acknowledged_at": None,
    "motion_stop_response_text": None,
    "power_request": backend_vars.read("POWER_REQUEST", "대기 중"),
    "last_backend_event": None,
}

_position_state_lock = Lock()
_position_state: Dict[str, Any] = {
    "is_moving": False,
    "last_moved_at": None,
}

_voice_state_lock = Lock()
_voice_state: Dict[str, Any] = {
    "is_listening": False,
    "last_started_at": None,
    "last_stopped_at": None,
    "selected_device_id": None,
    "selected_device_name": "기본 입력 장치",
    "devices_error": None,
}

_mode_state_lock = Lock()
_mode_state: Dict[str, Any] = {
    "active_mode": "release",
    "last_triggered_at": None,
    "current_mode": backend_vars.read("CURRENT_MODE", "RELEASE"),
    "last_backend_event": None,
}

MODE_CONTROL_ALIASES: Dict[str, str] = {
    "rcm": "fixed_plane",
}

MODE_CONTROL_LABELS: Dict[str, str] = {
    "fixed_joint": "FIXED JOINT",
    "release": "RELEASE",
    "fixed_point": "FIXED POINT",
    "fixed_line": "FIXED LINE",
    "fixed_plane": "FIXED PLANE",
    "update_jts": "UPDATE JTS",
    # Legacy value kept so old cached UI state does not surface stale labels.
    "rcm": "FIXED PLANE",
}

JOYSTICK_SIM_ACTIONS: Dict[str, int] = {
    "enable": JoystickCommand.ENABLE,
    "tilt_u": JoystickCommand.TILT_U,
    "tilt_v": JoystickCommand.TILT_V,
    "tilt_w": JoystickCommand.TILT_W,
    "zoom_in": JoystickCommand.ZOOM_IN,
    "zoom_out": JoystickCommand.ZOOM_OUT,
    "tilt_w_cw": JoystickCommand.TILT_W_CW,
    "tilt_w_ccw": JoystickCommand.TILT_W_CCW,
}

JOYSTICK_SIM_BOOL_ACTIONS = {
    JoystickCommand.ENABLE,
    JoystickCommand.ZOOM_IN,
    JoystickCommand.ZOOM_OUT,
    JoystickCommand.TILT_W_CW,
    JoystickCommand.TILT_W_CCW,
}

_backend_seed = backend_vars.read("SYSTEM_STATUS", {})
_DEFAULT_SYSTEM_STATUS: Dict[str, Any] = deepcopy(_backend_seed) if isinstance(_backend_seed, dict) else {}

_blackboard = GlobalBlackboard()


def _bb_get(path: str, default: Any = None) -> Any:
    try:
        return _blackboard.get(path)
    except Exception:
        return default


def _bb_set(path: str, value: Any) -> None:
    try:
        _blackboard.set(path, value)
    except Exception:
        logger.debug("Failed to write blackboard value %s", path, exc_info=True)


def _bb_set_voice_progress(stage: str, message: str, timestamp: Optional[str] = None) -> None:
    timestamp = timestamp or _utc_timestamp()
    events = _bb_get("voice/progress_events", [])
    if not isinstance(events, list):
        events = []
    _bb_set("voice/progress_events", [*events[-11:], {"at": timestamp, "stage": stage, "message": message}])
    _bb_set("voice/progress_stage", stage)
    _bb_set("voice/progress_message", message)
    _bb_set("voice/progress_updated_at", timestamp)
    _bb_set("voice/status_text", message)


def _queue_joystick_event(action_id: int, value: Any) -> int:
    if hasattr(joystick_manager, "inject_event"):
        joystick_manager.inject_event(action_id, value)
    else:
        joystick_manager.event_list.append((action_id, value))
    return len(getattr(joystick_manager, "event_list", []))


def _utc_timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _mode_action_id(mode: Any) -> Any:
    if not isinstance(mode, str):
        return mode
    return MODE_CONTROL_ALIASES.get(mode, mode)


def _mode_display_label(mode: Any) -> Any:
    if not isinstance(mode, str):
        return mode
    action_id = _mode_action_id(mode)
    return MODE_CONTROL_LABELS.get(action_id, MODE_CONTROL_LABELS.get(mode, mode))


def _normalize_status_color(value: Any) -> Optional[str]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"black", "red", "green"}:
            return normalized
    return None


def _connection_status_color(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return "green" if value else "red"
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower().replace(" ", "")
    if not normalized:
        return None
    if any(keyword in normalized for keyword in ("연결안됨", "disconnected", "offline")):
        return "red"
    if any(keyword in normalized for keyword in ("연결됨", "connected", "online")):
        return "green"
    return None


def _coerce_numeric_list(raw: Any, *, length: int = 6) -> List[float]:
    values: List[float] = []
    if isinstance(raw, (list, tuple)):
        for index in range(length):
            try:
                values.append(float(raw[index]))
            except (TypeError, ValueError, IndexError):
                values.append(0.0)
    if len(values) < length:
        values.extend([0.0] * (length - len(values)))
    return values


def _get_robot_telemetry() -> Dict[str, Any]:
    q_values = _coerce_numeric_list(_blackboard.get("robot/state/qdata"))
    p_values = _coerce_numeric_list(_blackboard.get("robot/state/pdata"))
    tau_ext_values = _coerce_numeric_list(_blackboard.get("robot/state/tau_ext"))
    fixed_snapshot = _bb_get("fixed_constraint_teleop/snapshot", {})
    fixed_teleop = deepcopy(fixed_snapshot) if isinstance(fixed_snapshot, dict) else {}
    if fixed_teleop:
        controller_state = fixed_teleop.get("state")
        if isinstance(controller_state, str) and controller_state:
            fixed_teleop["state"] = controller_state
        else:
            fixed_teleop["state"] = "active" if fixed_teleop.get("active") else "inactive"

    telemetry = {
        "q": q_values,
        "p": {
            "px": p_values[0],
            "py": p_values[1],
            "pz": p_values[2],
            "u": p_values[3],
            "v": p_values[4],
            "w": p_values[5],
        },
        "tau_ext": tau_ext_values,
        "sim_mode": bool(_blackboard.get("robot/state/sim_mode")),
        "fixed_constraint_teleop": fixed_teleop,
        "last_updated": _utc_timestamp(),
    }

    return telemetry


def _get_cb_state() -> Dict[str, Any]:
    with _cb_state_lock:
        state = deepcopy(_cb_state)
        power_request = backend_vars.read("POWER_REQUEST", state.get("power_request"))
        state["power_request"] = power_request if isinstance(power_request, str) else "대기 중"
        return state


def _mark_cb_event(event_type: str) -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    power_request_text: Optional[str] = None
    with _cb_state_lock:
        if event_type == "reboot":
            _cb_state.update(
                {
                    "reboot_requested": True,
                    "reboot_requested_at": timestamp,
                    "reboot_acknowledged": True,
                    "reboot_acknowledged_at": timestamp,
                    "reboot_response_text": "리부트 요청이 백엔드에서 확인되었습니다.",
                    "shutdown_response_text": _cb_state.get("shutdown_response_text"),
                }
            )
            power_request_text = "리부트"
        elif event_type == "shutdown":
            _cb_state.update(
                {
                    "shutdown_requested": True,
                    "shutdown_requested_at": timestamp,
                    "shutdown_acknowledged": True,
                    "shutdown_acknowledged_at": timestamp,
                    "shutdown_response_text": "종료 요청이 백엔드에서 확인되었습니다.",
                    "reboot_response_text": _cb_state.get("reboot_response_text"),
                }
            )
            power_request_text = "종료"
        elif event_type == "motion_start":
            _cb_state.update(
                {
                    "motion_request": "start",
                    "motion_start_requested": True,
                    "motion_start_requested_at": timestamp,
                    "motion_start_acknowledged": True,
                    "motion_start_acknowledged_at": timestamp,
                    "motion_start_response_text": "모션 시작 요청이 백엔드에서 확인되었습니다.",
                    "motion_stop_response_text": _cb_state.get("motion_stop_response_text"),
                }
            )
        elif event_type == "motion_stop":
            _cb_state.update(
                {
                    "motion_request": "stop",
                    "motion_stop_requested": True,
                    "motion_stop_requested_at": timestamp,
                    "motion_stop_acknowledged": True,
                    "motion_stop_acknowledged_at": timestamp,
                    "motion_stop_response_text": "모션 종료 요청이 백엔드에서 확인되었습니다.",
                    "motion_start_response_text": _cb_state.get("motion_start_response_text"),
                }
            )
        else:  # pragma: no cover - defensive programming
            raise ValueError(f"Unsupported CB control event: {event_type}")
        if power_request_text:
            _cb_state["power_request"] = power_request_text
        _cb_state["last_backend_event"] = {"type": event_type, "at": timestamp}
        if power_request_text:
            backend_vars.write("POWER_REQUEST", power_request_text)
        return deepcopy(_cb_state)


def _get_position_state(base_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(base_state, dict):
        base_state = variable_manager.read().get("position_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _position_state_lock:
        return _merge_position_state(base_state, _position_state)


def _merge_position_state(base_state: Dict[str, Any], position_state: Dict[str, Any]) -> Dict[str, Any]:
    merged_state = deepcopy(base_state)
    merged_state.update(deepcopy(position_state))
    merged_state.pop("motion_hint", None)
    return merged_state


def _merge_voice_state(base_state: Dict[str, Any], voice_state: Dict[str, Any]) -> Dict[str, Any]:
    merged_state = deepcopy(base_state)
    merged_state.update(deepcopy(voice_state))
    merged_state["is_listening"] = bool(
        backend_vars.read("VOICE_CONTROL_ACTIVE", merged_state.get("is_listening", False))
    )
    action_json = _bb_get("voice/action_json", {})
    if not isinstance(action_json, dict):
        action_json = {}
    stt_text = _bb_get("voice/stt_text", "")
    last_audio_path = _bb_get("voice/last_audio_path", "")
    last_result_at = _bb_get("voice/last_result_at", None)
    last_error = _bb_get("voice/last_error", "")
    progress_stage = _bb_get("voice/progress_stage", "")
    progress_message = _bb_get("voice/progress_message", "")
    progress_updated_at = _bb_get("voice/progress_updated_at", None)
    progress_events = _bb_get("voice/progress_events", [])
    llm_raw_response = _bb_get("voice/llm_raw_response", "")
    request_control = bool(_bb_get("voice/request_control", False))
    cancel_requested = bool(_bb_get("voice/cancel_requested", False))
    if not isinstance(progress_events, list):
        progress_events = []
    if isinstance(progress_message, str) and progress_message.strip():
        merged_state["status_text"] = progress_message
    merged_state["result_json"] = {
        "stage": progress_stage if isinstance(progress_stage, str) else str(progress_stage),
        "message": progress_message if isinstance(progress_message, str) else str(progress_message),
        "progress_updated_at": progress_updated_at,
        "events": progress_events[-12:],
        "stt_text": stt_text if isinstance(stt_text, str) else str(stt_text),
        "llm_raw_response": llm_raw_response if isinstance(llm_raw_response, str) else str(llm_raw_response),
        "action_json": action_json,
        "request_control": request_control,
        "cancel_requested": cancel_requested,
        "last_audio_path": last_audio_path if isinstance(last_audio_path, str) else "",
        "last_result_at": last_result_at,
        "last_error": last_error if isinstance(last_error, str) else str(last_error),
    }
    selected_device = _bb_get("voice/input_device", merged_state.get("selected_device_id"))
    if selected_device is None or selected_device == "":
        merged_state["selected_device_id"] = None
    else:
        try:
            merged_state["selected_device_id"] = int(selected_device)
        except (TypeError, ValueError):
            merged_state["selected_device_id"] = None
    selected_name = _bb_get("voice/input_device_name", merged_state.get("selected_device_name"))
    if isinstance(selected_name, str) and selected_name.strip():
        merged_state["selected_device_name"] = selected_name
    else:
        merged_state["selected_device_name"] = "기본 입력 장치"
    merged_state.pop("status_text", None)
    return merged_state


def _merge_mode_state(base_state: Dict[str, Any], mode_state: Dict[str, Any]) -> Dict[str, Any]:
    merged_state = deepcopy(base_state)
    merged_state.update(deepcopy(mode_state))
    return merged_state


def _get_voice_state(base_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(base_state, dict):
        base_state = variable_manager.read().get("voice_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _voice_state_lock:
        return _merge_voice_state(base_state, _voice_state)


def _normalize_voice_device_id(value: Any) -> Optional[int]:
    if value is None or value == "" or value == "default":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="device_id must be an integer or null") from exc


def _query_input_devices() -> Dict[str, Any]:
    try:
        import sounddevice as sd  # noqa: WPS433
    except Exception as exc:  # pragma: no cover - depends on host audio setup
        return {
            "devices": [],
            "default_device_id": None,
            "error": f"sounddevice import failed: {exc}",
        }

    try:
        raw_devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_devices = sd.default.device
    except Exception as exc:  # pragma: no cover - depends on host audio setup
        return {
            "devices": [],
            "default_device_id": None,
            "error": f"audio device query failed: {exc}",
        }

    try:
        default_input_id = default_devices[0]
    except (TypeError, IndexError):
        default_input_id = None

    if default_input_id is not None:
        try:
            default_input_id = int(default_input_id)
            if default_input_id < 0:
                default_input_id = None
        except (TypeError, ValueError):
            default_input_id = None

    devices: List[Dict[str, Any]] = []
    for index, device in enumerate(raw_devices):
        max_input_channels = int(device.get("max_input_channels", 0) or 0)
        if max_input_channels <= 0:
            continue
        hostapi_name = ""
        hostapi_index = device.get("hostapi")
        try:
            hostapi_index = int(hostapi_index)
        except (TypeError, ValueError):
            hostapi_index = None
        if hostapi_index is not None and 0 <= hostapi_index < len(hostapis):
            hostapi_name = str(hostapis[hostapi_index].get("name", ""))
        devices.append(
            {
                "id": index,
                "name": str(device.get("name", f"Input {index}")),
                "hostapi": hostapi_name,
                "max_input_channels": max_input_channels,
                "default_samplerate": device.get("default_samplerate"),
                "is_default": index == default_input_id,
            }
        )

    return {
        "devices": devices,
        "default_device_id": default_input_id,
        "error": None,
    }


def _set_voice_input_device(device_id: Optional[int]) -> Dict[str, Any]:
    device_info = _query_input_devices()
    devices = device_info["devices"]
    selected_name = "기본 입력 장치"

    if device_id is not None:
        selected_device = next((device for device in devices if device["id"] == device_id), None)
        if selected_device is None:
            raise HTTPException(status_code=400, detail="Selected microphone is not available")
        selected_name = selected_device["name"]

    _bb_set("voice/input_device", device_id)
    _bb_set("voice/input_device_name", selected_name)

    with _voice_state_lock:
        _voice_state["selected_device_id"] = device_id
        _voice_state["selected_device_name"] = selected_name
        _voice_state["devices_error"] = device_info["error"]
        merged = _merge_voice_state(variable_manager.read().get("voice_control", {}), _voice_state)

    return merged


def _get_mode_state(base_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(base_state, dict):
        base_state = variable_manager.read().get("mode_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    active_mode = backend_vars.read("MODE_CONTROL_MODE", base_state.get("active_mode"))
    current_mode = backend_vars.read("CURRENT_MODE", base_state.get("current_mode"))
    if isinstance(active_mode, str):
        action_id = _mode_action_id(active_mode)
        _mode_state["active_mode"] = action_id
        base_state["active_mode"] = action_id
    if isinstance(current_mode, str):
        display_mode = _mode_display_label(current_mode)
        _mode_state["current_mode"] = display_mode
        base_state["current_mode"] = display_mode
    with _mode_state_lock:
        return _merge_mode_state(base_state, _mode_state)


def _start_position_move() -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    base_state = variable_manager.read().get("position_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _position_state_lock:
        _position_state["is_moving"] = True
        _position_state.update(
            {
                "last_moved_at": timestamp,
            }
        )
        return _merge_position_state(base_state, _position_state)


def _stop_position_move() -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    base_state = variable_manager.read().get("position_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _position_state_lock:
        _position_state.update(
            {
                "is_moving": False,
                "last_moved_at": timestamp,
            }
        )
        return _merge_position_state(base_state, _position_state)


def _start_voice_control() -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    base_state = variable_manager.read().get("voice_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _voice_state_lock:
        _voice_state.update(
            {
                "is_listening": True,
                "last_started_at": timestamp,
                "status_text": "음성 녹음 중...",
            }
        )
        _bb_set("voice/status_text", "음성 녹음 중...")
        _bb_set("voice/progress_stage", "recording")
        _bb_set("voice/progress_message", "음성 녹음 중...")
        _bb_set("voice/progress_updated_at", timestamp)
        _bb_set("voice/progress_events", [{"at": timestamp, "stage": "recording", "message": "음성 녹음 중..."}])
        _bb_set("voice/stt_text", "")
        _bb_set("voice/action_json", {})
        _bb_set("voice/llm_raw_response", "")
        _bb_set("voice/last_error", "")
        _bb_set("voice/request_control", False)
        _bb_set("voice/cancel_requested", False)
        _bb_set("voice/recording/stop", False)
        backend_vars.write("VOICE_CONTROL_ACTIVE", True)
        backend_vars.write("VOICE_CONTROL_FLAG", True)
        # backend_vars.write("VOICE_CONTROL_LAST_AUDIO", None)
    return _merge_voice_state(base_state, _voice_state)


def _stop_voice_control() -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    base_state = variable_manager.read().get("voice_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _voice_state_lock:
        _voice_state.update(
            {
                "is_listening": False,
                "last_stopped_at": timestamp,
                "status_text": "녹음을 종료하고 처리 중...",
            }
        )
        _bb_set("voice/status_text", "녹음을 종료하고 처리 중...")
        _bb_set("voice/progress_stage", "recording_stopping")
        _bb_set("voice/progress_message", "녹음을 종료하고 처리 중...")
        _bb_set("voice/progress_updated_at", timestamp)
        logger.debug("Voice control stop flag set")
        backend_vars.write("VOICE_CONTROL_ACTIVE", False)
        backend_vars.write("VOICE_CONTROL_FLAG", True)
    return _merge_voice_state(base_state, _voice_state)


def _cancel_voice_control() -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    message = "음성교시를 정지했습니다."
    base_state = variable_manager.read().get("voice_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _voice_state_lock:
        _voice_state.update(
            {
                "is_listening": False,
                "last_stopped_at": timestamp,
                "status_text": message,
            }
        )
        _bb_set("voice/cancel_requested", True)
        _bb_set("voice/recording/stop", True)
        _bb_set("voice/request_control", False)
        _bb_set("voice/action_json", {})
        _bb_set("voice/stt_text", "")
        _bb_set("voice/llm_raw_response", "")
        _bb_set("voice/last_error", "")
        _bb_set("voice/last_result_at", timestamp)
        _bb_set_voice_progress("cancelled", message, timestamp)
        backend_vars.write("VOICE_CONTROL_ACTIVE", False)
        backend_vars.write("VOICE_CONTROL_FLAG", False)
    return _merge_voice_state(base_state, _voice_state)


def _execute_mode_control(mode: str) -> Dict[str, Any]:
    timestamp = _utc_timestamp()
    action_id = _mode_action_id(mode)
    if action_id not in MODE_CONTROL_LABELS:
        raise HTTPException(status_code=400, detail=f"unsupported mode: {mode}")
    previous_mode = _mode_action_id(
        backend_vars.read("MODE_CONTROL_MODE", _mode_state.get("active_mode", "release"))
    )
    if action_id == "update_jts":
        if previous_mode == "update_jts":
            previous_mode = _mode_action_id(
                backend_vars.read(
                    "MODE_CONTROL_RETURN_MODE",
                    backend_vars.read("MODE_CONTROL_LAST_ACTIVE_MODE", "release"),
                )
            )
        backend_vars.write("MODE_CONTROL_RETURN_MODE", previous_mode)
    else:
        backend_vars.write("MODE_CONTROL_LAST_ACTIVE_MODE", action_id)

    base_state = variable_manager.read().get("mode_control", {})
    if not isinstance(base_state, dict):
        base_state = {}
    with _mode_state_lock:
        _mode_state.update(
            {
                "active_mode": action_id,
                "last_triggered_at": timestamp,
                "current_mode": _mode_display_label(action_id),
                "last_backend_event": {"type": "execute", "mode": action_id, "at": timestamp},
            }
        )
        backend_vars.write("MODE_CONTROL_MODE", action_id)
        backend_vars.write("CURRENT_MODE", _mode_display_label(action_id))
        backend_vars.write("MODE_CONTROL_FLAG", True)

        return _merge_mode_state(base_state, _mode_state)


backend_app = FastAPI(title="Surgical UI Backend", version="1.0")

backend_app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https?://localhost:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@backend_app.get("/health", tags=["system"])
def health() -> Dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}


@backend_app.get("/api/state", tags=["state"])
def get_state() -> Dict[str, Any]:
    """Return the current UI state snapshot enriched with backend values."""

    snapshot = variable_manager.read()

    # Always merge in the latest backend-observed states so the frontend poller
    # can reflect changes that originate outside the UI (e.g., controller
    # metrics or long-press motion commands).
    snapshot["system"] = _apply_backend_system_status(_get_backend_system_status(), snapshot)
    snapshot["position_control"] = _get_position_state(snapshot.get("position_control"))
    snapshot["cb_control"] = _get_cb_state()
    snapshot["voice_control"] = _get_voice_state(snapshot.get("voice_control"))
    snapshot["mode_control"] = _get_mode_state(snapshot.get("mode_control"))
    snapshot["telemetry"] = _get_robot_telemetry()
    return snapshot


@backend_app.get("/api/system/state", tags=["system"])
def get_system_state() -> Dict[str, Any]:
    """Return system status values observed by the backend."""
    backend_state = _get_backend_system_status()
    system_state = _apply_backend_system_status(backend_state)
    return {"system": system_state}


@backend_app.get("/api/robot/telemetry", tags=["telemetry"])
def get_robot_telemetry() -> Dict[str, Any]:
    """Expose the latest robot joint and tool telemetry."""

    telemetry = _get_robot_telemetry()
    return telemetry


@backend_app.post("/api/robot/simulated-tau", tags=["telemetry"])
def post_robot_simulated_tau(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Inject a tau_ext sample for simulation/testing."""

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    enabled = bool(payload.get("enabled", True))
    tau_ext = _coerce_numeric_list(payload.get("tau_ext"))

    _bb_set("robot/simulated_tau/enabled", enabled)
    _bb_set("robot/simulated_tau/tau_ext", tau_ext)
    if enabled:
        _bb_set("robot/state/tau_ext", tau_ext)
        _bb_set("robot/state/sim_mode", True)
    else:
        _bb_set("robot/state/sim_mode", False)

    return {
        "status": "ok",
        "enabled": enabled,
        "tau_ext": tau_ext,
        "telemetry": _get_robot_telemetry(),
    }


@backend_app.post("/api/robot/simulated-cockpit", tags=["telemetry"])
def post_robot_simulated_cockpit(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Override cockpit pressed state for simulation/testing."""

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    enabled = bool(payload.get("enabled", True))
    pressed = bool(payload.get("pressed", False))
    _bb_set("cockpit/simulated/enabled", enabled)
    _bb_set("cockpit/simulated/pressed", pressed)
    if enabled:
        _bb_set("cockpit/pressed", pressed)
    elif not pressed:
        _bb_set("cockpit/pressed", False)

    return {
        "status": "ok",
        "enabled": enabled,
        "pressed": pressed,
        "telemetry": _get_robot_telemetry(),
    }


@backend_app.post("/api/joystick/simulated-event", tags=["telemetry"])
def post_joystick_simulated_event(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Queue one or more virtual joystick events for simulation/testing."""

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    raw_events = payload.get("events")
    events = raw_events if isinstance(raw_events, list) else [payload]
    queued = []
    _bb_set("joystick/state/connect", True)

    for event in events:
        if not isinstance(event, dict):
            raise HTTPException(status_code=400, detail="each event must be an object")

        action_name = str(event.get("action", "")).strip().lower().replace("-", "_")
        action_id = JOYSTICK_SIM_ACTIONS.get(action_name)
        if action_id is None:
            raise HTTPException(status_code=400, detail=f"unsupported joystick action: {action_name}")

        if action_id in JOYSTICK_SIM_BOOL_ACTIONS:
            value = bool(event.get("value", True))
        else:
            try:
                value = float(event.get("value", 0.0))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="joystick axis value must be numeric") from exc

        queue_length = _queue_joystick_event(action_id, value)
        if action_id == JoystickCommand.ENABLE:
            _bb_set("joystick/enabled", bool(value))
        queued.append({"action": action_name, "value": value, "queue_length": queue_length})

    return {
        "status": "ok",
        "queued": queued,
    }


@backend_app.post("/api/voice-control/simulated-stt", tags=["voice_control"])
def post_voice_control_simulated_stt(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Inject an STT transcript through the normal voice-command parser."""

    from modules.voice.voice_manager import VOICE_CONTROL_ACTIONS, fetch_voice_command

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    stt_text = payload.get("stt_text")
    if not isinstance(stt_text, str) or not stt_text.strip():
        raise HTTPException(status_code=400, detail="stt_text must be provided")

    stt_text = stt_text.strip()
    try:
        command = fetch_voice_command(stt_text)
    except Exception as exc:
        logger.exception("Simulated STT parsing failed")
        raise HTTPException(status_code=500, detail="failed to parse stt_text") from exc

    if command is None:
        command = {}

    _bb_set("voice/stt_text", stt_text)
    _bb_set("voice/action_json", command)
    _bb_set("voice/request_control", command.get("action") in VOICE_CONTROL_ACTIONS)
    _bb_set("voice/last_result_at", _utc_timestamp())
    _bb_set("voice/last_error", "" if command else "LLM returned no command")

    if command.get("action") != "mode" and command.get("aux1"):
        _bb_set("voice/speak_contents", command["aux1"])
        _bb_set("voice/speak_flag", True)

    return {
        "status": "ok",
        "stt_text": stt_text,
        "command": command,
        "request_control": bool(command.get("action") in VOICE_CONTROL_ACTIONS),
    }

def _get_backend_system_status() -> Dict[str, Any]:
    """Read the latest system status values tracked by the backend."""

    backend_state = backend_vars.read("SYSTEM_STATUS", None)
    if not isinstance(backend_state, dict):
        backend_state = {}

    if not backend_state:
        backend_state = deepcopy(_DEFAULT_SYSTEM_STATUS)

    if not backend_state.get("last_updated"):
        backend_state["last_updated"] = _utc_timestamp()

    backend_vars.write("SYSTEM_STATUS", backend_state)
    return deepcopy(backend_state)


def _apply_backend_system_status(backend_state: Dict[str, Any], snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge backend-provided system values into the shared UI state."""

    if not isinstance(snapshot, dict):
        snapshot = variable_manager.read()
    system_state: Dict[str, Any] = deepcopy(snapshot.get("system", {}))
    metrics: Dict[str, Any] = deepcopy(system_state.get("metrics", {}))

    status = backend_state.get("status")
    if isinstance(status, str) and status.strip():
        system_state["status"] = status.strip()

    status_color = _normalize_status_color(backend_state.get("status_color"))
    if status_color:
        system_state["status_color"] = status_color

    operating_mode = backend_state.get("operating_mode")
    if isinstance(operating_mode, str) and operating_mode.strip():
        system_state["operating_mode"] = operating_mode.strip()

    operating_mode_color = _normalize_status_color(backend_state.get("operating_mode_color"))
    if operating_mode_color:
        system_state["operating_mode_color"] = operating_mode_color

    version = backend_state.get("version") or backend_state.get("system_version")
    if isinstance(version, str) and version.strip():
        system_state["version"] = version.strip()

    version_color = _normalize_status_color(backend_state.get("version_color"))
    if version_color:
        system_state["version_color"] = version_color

    metrics_payload = backend_state.get("metrics") if isinstance(backend_state.get("metrics"), dict) else {}
    robot_drive = backend_state.get("robot_drive", metrics_payload.get("motor"))
    controller_connection = backend_state.get("controller_connection", metrics_payload.get("network"))

    robot_drive_color = _normalize_status_color(
        backend_state.get("robot_drive_color", metrics_payload.get("motor_color"))
    )
    controller_connection_color = _normalize_status_color(
        backend_state.get("controller_connection_color", metrics_payload.get("network_color"))
    )
    if not robot_drive_color or robot_drive_color == "black":
        robot_drive_color = _connection_status_color(robot_drive) or robot_drive_color
    if not controller_connection_color or controller_connection_color == "black":
        controller_connection_color = _connection_status_color(controller_connection) or controller_connection_color

    if isinstance(robot_drive, str) and robot_drive:
        metrics["motor"] = robot_drive
    if isinstance(controller_connection, str) and controller_connection:
        metrics["network"] = controller_connection
    if robot_drive_color:
        metrics["motor_color"] = robot_drive_color
    if controller_connection_color:
        metrics["network_color"] = controller_connection_color

    system_state["metrics"] = metrics

    last_updated = backend_state.get("last_updated") or _utc_timestamp()
    system_state["last_updated"] = last_updated
    system_state["last_backend_event"] = {"type": "system_poll", "at": last_updated}

    return system_state


@backend_app.post("/api/system/update", tags=["system"])
def post_system_update(payload: Dict[str, Any] = Body({}, embed=False)) -> Dict[str, Any]:
    """Record a manual status update trigger and return the latest system state."""
    backend_vars.write("RECOVER_FLAG", True)
    # print("recovery")
    backend_state = _get_backend_system_status()
    requested_status = payload.get("status") if isinstance(payload, dict) else None
    next_status: Optional[str]
    if isinstance(requested_status, str) and requested_status.strip():
        next_status = requested_status.strip()
    else:
        next_status = backend_state.get("status") or "알 수 없음"
    timestamp = _utc_timestamp()
    backend_state.update(
        {
            "status": next_status,
            "last_updated": timestamp,
            "last_backend_event": {"type": "status_update", "at": timestamp},
        }
    )
    backend_vars.write("SYSTEM_STATUS", backend_state)

    system_state = _apply_backend_system_status(backend_state)
    return {"system": system_state}

@backend_app.patch("/api/system/state", tags=["system"])
def patch_system_state(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Update backend-tracked system values so the UI can reflect them."""

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    backend_state = _get_backend_system_status()
    updates: Dict[str, Any] = {}

    for key in ("status", "operating_mode", "robot_drive", "controller_connection", "version"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            updates[key] = value.strip()

    color_fields = {
        "status_color": "status_color",
        "operating_mode_color": "operating_mode_color",
        "robot_drive_color": "robot_drive_color",
        "controller_connection_color": "controller_connection_color",
        "version_color": "version_color",
    }

    for payload_key, update_key in color_fields.items():
        if payload_key not in payload:
            continue
        normalized = _normalize_status_color(payload.get(payload_key))
        if not normalized:
            raise HTTPException(status_code=400, detail=f"{payload_key} must be one of black, red, or green")
        updates[update_key] = normalized

    if not updates:
        raise HTTPException(status_code=400, detail="at least one field must be provided")

    timestamp = _utc_timestamp()
    backend_state.update(updates)
    backend_state["last_updated"] = timestamp
    backend_state["last_backend_event"] = {"type": "system_state_update", "at": timestamp}
    backend_vars.write("SYSTEM_STATUS", backend_state)

    system_state = _apply_backend_system_status(backend_state)
    return {"system": system_state}


@backend_app.post("/api/state", tags=["state"])
@backend_app.patch("/api/state", tags=["state"])
def update_state(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Merge the provided payload into the UI state."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Updates must be provided as a JSON object")
    try:
        return variable_manager.update(payload)
    except TypeError as exc:  # pragma: no cover - defensive programming
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@backend_app.post("/api/state/touch/{path:path}", tags=["state"])
def touch_state(path: str) -> Dict[str, Any]:
    """Update the timestamp at ``path`` to the current UTC time."""
    try:
        return variable_manager.touch(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@backend_app.get("/api/position-control/state", tags=["position_control"])
def get_position_control_state() -> Dict[str, Any]:
    """Return the backend-observed position control state."""
    return {"position_control": _get_position_state()}

@backend_app.get("/api/alarms", tags=["alarms"])
def get_alarm_log() -> Dict[str, Any]:
    """Return alarm/error logs as-is for the UI to render."""

    alarms = backend_vars.read("ALARMS", {})
    if not isinstance(alarms, dict):
        alarms = {}
    last_updated = backend_vars.read("ALARMS_LAST_UPDATED", _utc_timestamp())
    return {"alarms": alarms, "last_updated": last_updated}


@backend_app.get("/api/cb-control/state", tags=["cb_control"])
def get_cb_control_state() -> Dict[str, Any]:
    """Return the backend-observed CB control state."""
    return {"cb_control": _get_cb_state()}


@backend_app.get("/api/voice-control/state", tags=["voice_control"])
def get_voice_control_state() -> Dict[str, Any]:
    """Return the backend-observed voice control state."""
    return {"voice_control": _get_voice_state()}


@backend_app.get("/api/voice-control/devices", tags=["voice_control"])
def get_voice_control_devices() -> Dict[str, Any]:
    """Return the available audio input devices for voice recording."""
    device_info = _query_input_devices()
    with _voice_state_lock:
        _voice_state["devices_error"] = device_info["error"]
        voice_state = _merge_voice_state(variable_manager.read().get("voice_control", {}), _voice_state)
    return {
        "devices": device_info["devices"],
        "default_device_id": device_info["default_device_id"],
        "error": device_info["error"],
        "voice_control": voice_state,
    }


@backend_app.post("/api/voice-control/device", tags=["voice_control"])
def post_voice_control_device(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    """Set the audio input device used by voice recording."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Device selection must be provided as JSON")
    device_id = _normalize_voice_device_id(payload.get("device_id"))
    voice_state = _set_voice_input_device(device_id)
    device_info = _query_input_devices()
    return {
        "devices": device_info["devices"],
        "default_device_id": device_info["default_device_id"],
        "error": device_info["error"],
        "voice_control": voice_state,
    }


@backend_app.get("/api/mode-control/state", tags=["mode_control"])
def get_mode_control_state() -> Dict[str, Any]:
    """Return the backend-observed mode control state."""

    return {"mode_control": _get_mode_state()}


@backend_app.post("/api/cb-control/reboot", tags=["cb_control"])
def post_cb_reboot() -> Dict[str, Any]:
    updated_state = _mark_cb_event("reboot")
    logger.info("CB reboot requested")
    backend_vars.write("REBOOT_FLAG", True)
    return {"cb_control": updated_state}


@backend_app.post("/api/cb-control/shutdown", tags=["cb_control"])
def post_cb_shutdown() -> Dict[str, Any]:
    """Record a shutdown request and acknowledge it immediately."""
    updated_state = _mark_cb_event("shutdown")
    logger.info("CB shutdown requested")
    backend_vars.write("POWER_OFF_FLAG", True)
    return {"cb_control": updated_state}


@backend_app.post("/api/cb-control/motion-start", tags=["cb_control"])
def post_cb_motion_start() -> Dict[str, Any]:
    updated_state = _mark_cb_event("motion_start")
    logger.info("CB motion start requested")
    backend_vars.write("MOTION_REQUEST", "start")
    backend_vars.write("MOTION_START_FLAG", True)
    return {"cb_control": updated_state}


@backend_app.post("/api/cb-control/motion-stop", tags=["cb_control"])
def post_cb_motion_stop() -> Dict[str, Any]:
    updated_state = _mark_cb_event("motion_stop")
    logger.info("CB motion stop requested")
    backend_vars.write("MOTION_REQUEST", "stop")
    backend_vars.write("MOTION_STOP_FLAG", True)
    return {"cb_control": updated_state}


@backend_app.post("/api/position-control/move/start", tags=["position_control"])  # Start move
def post_position_control_start(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    target_position = payload.get("target_position")

    if not isinstance(target_position, str) or not target_position.strip():
        raise HTTPException(status_code=400, detail="target_position must be provided")

    target_position = target_position.strip()
    target_index_raw = payload.get("target_position_index")
    target_index: Optional[int] = None
    if target_index_raw is not None:
        try:
            target_index = int(target_index_raw)
            # backend_vars.update({"MOVE_FLAG": True, "MOVE_MODE": target_index})
            backend_vars.write("MOVE_MODE", target_index)
            backend_vars.write("MOVE_FLAG", True)

        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive programming
            raise HTTPException(status_code=400, detail="target_position_index must be an integer") from exc

    _start_position_move()
    return {"status": "ok"}


@backend_app.post("/api/position-control/move/stop", tags=["position_control"])
def post_position_control_stop(payload: Dict[str, Any] = Body({}, embed=False)) -> Dict[str, Any]:
    target_position = payload.get("target_position")
    if isinstance(target_position, str):
        target_position = target_position.strip() or None
    else:
        target_position = None

    target_index_raw = payload.get("target_position_index")
    target_index: Optional[int] = None
    if target_index_raw is not None:
        try:
            target_index = int(target_index_raw)
            # backend_vars.update({"MOVE_FLAG": False, "MOVE_MODE": target_index})
            backend_vars.write("MOVE_FLAG", False)
            backend_vars.write("MOVE_MODE", target_index)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive programming
            raise HTTPException(status_code=400, detail="target_position_index must be an integer") from exc
    _stop_position_move()
    return {"status": "ok"}


@backend_app.post("/api/voice-control/move/start", tags=["voice_control"])  # Start voice command
def post_voice_control_start() -> Dict[str, Any]:
    _start_voice_control()
    logger.info("Voice control start requested")

    return {"status": "ok"}


@backend_app.post("/api/voice-control/move/stop", tags=["voice_control"])  # Stop voice command
def post_voice_control_stop() -> Dict[str, Any]:
    _stop_voice_control()
    logger.info("Voice control stop requested")
    return {"status": "ok"}


@backend_app.post("/api/voice-control/move/cancel", tags=["voice_control"])  # Cancel voice command processing
def post_voice_control_cancel() -> Dict[str, Any]:
    voice_state = _cancel_voice_control()
    logger.info("Voice control cancel requested")
    return {"status": "ok", "voice_control": voice_state}


@backend_app.post("/api/mode-control/execute", tags=["mode_control"])  # Single-shot mode control command
def post_mode_control_execute(payload: Dict[str, Any] = Body(..., embed=False)) -> Dict[str, Any]:
    mode = payload.get("mode") if isinstance(payload, dict) else None

    if not isinstance(mode, str) or not mode.strip():
        raise HTTPException(status_code=400, detail="mode must be provided")

    mode = mode.strip()
    updated_state = _execute_mode_control(mode)
    logger.info("Mode control execute requested: %s", mode)
    return {"mode_control": updated_state}
