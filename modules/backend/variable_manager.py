"""Simple in-memory state store for the surgical UI demo."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List


def _utc_timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


class VariableManager:
    """Minimal thread-safe container for nested UI state values."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = self._initial_state()

    def read(self) -> Dict[str, Any]:
        """Return a snapshot of the stored UI state."""

        with self._lock:
            return deepcopy(self._state)

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Deep-merge ``updates`` into the stored state and return the snapshot."""

        if not isinstance(updates, dict):
            raise TypeError("Updates must be provided as a dictionary")

        with self._lock:
            self._merge(self._state, updates)
            return deepcopy(self._state)

    def touch(self, path: str) -> Dict[str, Any]:
        """Set the value at ``path`` to the current UTC timestamp."""

        if not path:
            raise ValueError("A path must be provided")

        with self._lock:
            self._assign_path(path.split("."), _utc_timestamp())
            return deepcopy(self._state)

    def _initial_state(self) -> Dict[str, Any]:
        timestamp = _utc_timestamp()
        return {
            "system": {
                "status": "비정상 가동",
                "status_color": "red",
                "operating_mode": "대기",
                "operating_mode_color": "black",
                "location": "-",
                "version": "1.0",
                "version_color": "black",
                "last_updated": timestamp,
                "alarms_last_updated": timestamp,
                "last_backend_event": None,
                "metrics": {
                    "power": "안정",
                    "motor": "연결 안 됨",
                    "motor_color": "red",
                    "sensor_feedback": "정상",
                    "network": "연결 안 됨",
                    "network_color": "red",
                },
                "alarms": {
                    # "list_1": {
                    #     # "시간": "-:-:-",
                    #     # "종류": "정보",
                    #     # "내용": "-",
                    #     # "조치": "-",
                    #     # "id": 1,
                    #     "시간": "12:34:56",
                    #     "종류": "에러",
                    #     "내용": "충돌 감지: 로봇 팔이 외부 물체와 접촉이 감지되었습니다.",
                    #     "조치": "로봇 주변 확인 후 상태 업데이트 버튼 터치",
                    #     "id": 1,
                    # },
                    # "list_2": {"시간": "-:-:-", "종류": "조치완료", "내용": "-", "조치": "-", "id": 1},
                    # "list_3": {"시간": "-:-:-", "종류": "정보", "내용": "-", "조치": "-", "id": 0},
                },
            },
            "position_control": {
                "target_position": "home",
                "target_position_index": 0,
                "available_positions": [
                    {"id": "home", "label": "홈 위치"},
                    {"id": "ready", "label": "준비 위치"},
                    {"id": "packaging", "label": "패키징 위치"},
                ],
                "is_moving": False,
                "last_moved_at": None,
                "motion_hint": "버튼을 누르고 있는 동안 선택한 위치로 이동합니다.",
            },
            "cb_control": {
                "robot_model": "NURI 5S",
                "firmware_version": "3.4.0-FR (2025.07.30)",
                "robot_version": "3.4.0-FR-hotfix8 (2025.09.22)",
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
                "power_request": "대기 중",
                "last_backend_event": None,
            },
            "voice_control": {
                "is_listening": False,
                "last_started_at": None,
                "last_stopped_at": None,
                "selected_device_id": None,
                "selected_device_name": "기본 입력 장치",
                "devices_error": None,
                "result_json": {
                    "stt_text": "",
                    "action_json": {},
                    "request_control": False,
                    "last_audio_path": "",
                    "last_result_at": None,
                    "last_error": "",
                },
                "status_text": "버튼을 누르면 음성을 녹음합니다.",
            },
            "mode_control": {
                "active_mode": "release",
                "last_triggered_at": None,
                "last_backend_event": None,
                "current_mode": "RELEASE",
            },
            "telemetry": {
                "q": [0, 0, 0, 0, 0, 0],
                "p": {"px": 0, "py": 0, "pz": 0, "u": 0, "v": 0, "w": 0},
                "tau_ext": [0, 0, 0, 0, 0, 0],
                "sim_mode": False,
                "last_updated": timestamp,
            },
        }

    def _assign_path(self, path: List[str], value: Any) -> None:
        current = self._state
        for key in path[:-1]:
            next_node = current.get(key)
            if not isinstance(next_node, dict):
                next_node = {}
            current[key] = next_node
            current = next_node
        current[path[-1]] = deepcopy(value)

    def _merge(self, target: Dict[str, Any], updates: Dict[str, Any]) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._merge(target[key], value)
            else:
                target[key] = deepcopy(value)


variable_manager = VariableManager()
