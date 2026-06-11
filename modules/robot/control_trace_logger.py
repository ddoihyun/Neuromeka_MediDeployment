from __future__ import annotations

import atexit
import csv
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ControlTraceLogger:
    """Low-overhead CSV logger for real-time robot control traces."""

    SCALAR_FIELDS: List[str] = [
        "timestamp",
        "elapsed_sec",
        "perf_counter_sec",
        "record_type",
        "source",
        "skip_reason",
        "last_reason",
        "loop_dt_sec",
        "robot_enabled",
        "robot_state",
        "robot_state_name",
        "fsm_state",
        "fsm_state_name",
        "desired_mode",
        "desired_mode_name",
        "control_mode",
        "control_mode_name",
        "button_pressed",
        "button_mode",
        "button_mode_name",
        "cockpit_pressed",
        "joystick_connected",
        "joystick_enabled",
        "joystick_active_model",
        "joystick_event_queue_len",
        "joystick_axis_deadzone",
        "joystick_singularity_sigma_min",
        "joystick_singularity_condition_number",
        "joystick_singularity_speed_scale",
        "fixed_active",
        "fixed_controller_state",
        "fixed_mode",
        "fixed_mode_name",
        "fixed_reset_requested",
        "restore_enabled",
        "restore_saturation",
        "tangent_velocity_saturation",
        "reference_valid",
        "constraint_error_norm",
        "constraint_frame",
        "pose_source",
        "control_state_ok",
        "move_sent",
        "move_error",
        "vel_ratio",
        "acc_ratio",
        "integration_dt_sec",
        "rate_limit_mode",
        "task_input_source",
        "singularity_sigma_min",
        "singularity_condition_number",
        "singularity_speed_scale",
        "queue_dropped_records",
    ]

    VECTOR_FIELDS: List[Tuple[str, int]] = [
        ("q", 6),
        ("qdot", 6),
        ("p", 6),
        ("pdot", 6),
        ("tau", 6),
        ("tau_ext", 6),
        ("tau_bias", 6),
        ("tau_deadzone", 6),
        ("task_gain", 6),
        ("tau_processed", 6),
        ("task_wrench", 6),
        ("raw_velocity", 6),
        ("tangent_velocity", 6),
        ("restore_velocity", 6),
        ("restore_limited_velocity", 6),
        ("constrained_velocity", 6),
        ("limited_velocity", 6),
        ("raw_delta", 6),
        ("constrained_delta", 6),
        ("clamped_delta", 6),
        ("last_applied_delta", 6),
        ("previous_command", 6),
        ("controller_command", 6),
        ("command_delta", 6),
        ("scaled_delta", 6),
        ("sent_command", 6),
        ("joystick_axis_state", 3),
        ("joystick_axis_init", 3),
        ("joystick_axis_input", 3),
        ("joystick_button_input", 4),
        ("joystick_gain", 4),
        ("joystick_limit", 4),
        ("joystick_raw_delta", 4),
        ("joystick_scaled_delta", 4),
        ("joystick_applied_delta", 4),
        ("joystick_previous_cumulative", 4),
        ("joystick_cumulative", 4),
        ("axis_mask", 6),
        ("user_axis_mask", 6),
        ("constraint_vector", 3),
        ("reference_point", 3),
        ("reference_line_origin", 3),
        ("reference_line_axis", 3),
        ("reference_plane_point", 3),
        ("reference_plane_normal", 3),
        ("reference_rcm_point", 3),
        ("constraint_error", 3),
        ("constraint_error_velocity", 3),
        ("rate_limit", 6),
        ("delta_limit", 6),
        ("clip_delta_per_tick", 6),
        ("clip_cumulative", 6),
    ]

    def __init__(
        self,
        enabled: bool = False,
        directory: str = "LOG",
        flush_interval_s: float = 0.05,
        max_file_size_mb: float = 256.0,
        max_queue_size: int = 10000,
    ):
        self.directory = self._resolve_directory(directory)
        self.flush_interval_s = max(0.001, float(flush_interval_s))
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=max_queue_size)
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.enabled = False
        self.file_path: Optional[Path] = None
        self.file = None
        self.writer = None
        self.started_perf = time.perf_counter()
        self.last_flush_perf = self.started_perf
        self.file_index = 0
        self.base_stamp = ""
        self.last_error = ""
        self._dropped_records = 0
        self._dropped_lock = threading.Lock()
        atexit.register(self.stop)

        if enabled:
            self.start()

    @classmethod
    def header(cls) -> List[str]:
        columns = list(cls.SCALAR_FIELDS)
        for name, length in cls.VECTOR_FIELDS:
            columns.extend(f"{name}_{index}" for index in range(length))
        return columns

    @staticmethod
    def _resolve_directory(directory: str) -> Path:
        requested = Path(directory)
        if requested.is_absolute():
            return requested
        project_root = Path(__file__).resolve().parents[2]
        return project_root / requested

    def start(self) -> None:
        if self.enabled:
            return
        if self.thread is not None and self.thread.is_alive():
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.last_error = repr(exc)
            return
        self.stop_event.clear()
        self.started_perf = time.perf_counter()
        self.last_flush_perf = self.started_perf
        self.file_index = 0
        self.base_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        try:
            self._open_file()
        except OSError as exc:
            self.last_error = repr(exc)
            self._close_file()
            return
        self.enabled = True
        self.thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        if not self.enabled and self.thread is None:
            return
        self.enabled = False
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive() and threading.current_thread() != self.thread:
            self.thread.join(timeout=timeout)
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = None
        self._close_file()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    def log(self, record: Dict[str, Any]) -> None:
        if not self.enabled:
            return

        now_perf = time.perf_counter()
        payload = dict(record)
        payload.setdefault("timestamp", datetime.now().isoformat(timespec="milliseconds"))
        payload.setdefault("perf_counter_sec", now_perf)
        payload.setdefault("elapsed_sec", now_perf - self.started_perf)
        payload["queue_dropped_records"] = self._consume_dropped_records()

        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            self._mark_dropped_record()

    def _writer_loop(self) -> None:
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                record = self.queue.get(timeout=0.02)
            except queue.Empty:
                self._flush_if_needed()
                continue

            try:
                self._write_record(record)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                self.last_error = repr(exc)
                self.stop_event.set()
                break

        self._flush()
        self._close_file()

    def _open_file(self) -> None:
        if self.file is not None:
            self._close_file()

        self.file_path = self.directory / f"control_trace_{self.base_stamp}_{self.file_index}.csv"
        self.file = self.file_path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file, lineterminator="\n")
        self.writer.writerow(self.header())
        self.file.flush()

    def _close_file(self) -> None:
        if self.file is None:
            return
        try:
            self.file.flush()
            self.file.close()
        finally:
            self.file = None
            self.writer = None

    def _rollover_if_needed(self) -> None:
        if self.file is None:
            return
        if self.max_file_size_bytes <= 0:
            return
        if self.file.tell() < self.max_file_size_bytes:
            return

        self.file_index += 1
        self._open_file()

    def _write_record(self, record: Dict[str, Any]) -> None:
        if self.writer is None:
            return
        self.writer.writerow(self._row(record))
        self._rollover_if_needed()
        self._flush_if_needed()

    def _flush_if_needed(self) -> None:
        now_perf = time.perf_counter()
        if now_perf - self.last_flush_perf >= self.flush_interval_s:
            self._flush()
            self.last_flush_perf = now_perf

    def _flush(self) -> None:
        if self.file is not None:
            self.file.flush()

    def _row(self, record: Dict[str, Any]) -> List[Any]:
        row = [self._scalar(record.get(field)) for field in self.SCALAR_FIELDS]
        for name, length in self.VECTOR_FIELDS:
            row.extend(self._vector(record.get(name), length))
        return row

    @staticmethod
    def _scalar(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, bool):
            return int(value)
        try:
            if hasattr(value, "name") and hasattr(value, "value"):
                return value.value
        except Exception:
            pass
        return value

    @staticmethod
    def _vector(values: Any, length: int) -> List[Any]:
        if values is None:
            return [""] * length
        if not isinstance(values, (list, tuple)):
            try:
                values = list(values)
            except TypeError:
                return [""] * length

        output: List[Any] = []
        for index in range(length):
            try:
                output.append(values[index])
            except IndexError:
                output.append("")
        return output

    def _mark_dropped_record(self) -> None:
        with self._dropped_lock:
            self._dropped_records += 1

    def _consume_dropped_records(self) -> int:
        with self._dropped_lock:
            dropped = self._dropped_records
            self._dropped_records = 0
        return dropped
