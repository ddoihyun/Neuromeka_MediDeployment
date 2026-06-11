from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from modules.global_data import ControlMode


class FixedConstraintTeleopController:
    """Fixed point/line/plane TeleOP command generator driven by tau_ext."""

    MODE_NAMES = {
        ControlMode.FIXED_POINT: "fixed_point",
        ControlMode.FIXED_LINE: "fixed_line",
        ControlMode.FIXED_PLANE: "fixed_plane",
    }

    def __init__(self, config_path: Optional[str] = None, tool_pos: Optional[Iterable[float]] = None):
        default_path = Path(__file__).resolve().parents[2] / "configs" / "fixed_constraint_teleop_config.json"
        self.config_path = Path(config_path) if config_path else default_path
        self.config = self._load_config(self.config_path)
        self._config_mtime = self._config_file_mtime()
        self._last_config_reload_check_perf = 0.0

        self.active = False
        self.mode = ControlMode.NONE
        self.mode_name = "inactive"
        self.cumulative_command = [0.0] * 6
        self._reset_trace_fields()

        self._apply_config_vectors()
        self.tool_pos = [0.0] * 6
        self.tool_transform = np.eye(4, dtype=float)
        self.set_tool_pos(tool_pos if tool_pos is not None else self._default_tool_pos())

    @property
    def is_active(self) -> bool:
        return self.active

    def enter_mode(self, mode: Any) -> None:
        mode = self._coerce_mode(mode)
        if mode not in self.MODE_NAMES:
            self.exit_mode()
            return

        self.mode = mode
        self.mode_name = self.MODE_NAMES[mode]
        self.reset_command()
        self._reset_trace_fields()
        self.last_reason = "enter_mode"

        self.active = True

    def exit_mode(self) -> None:
        self.active = False
        self.mode = ControlMode.NONE
        self.mode_name = "inactive"
        self.reset_command()
        self._reset_trace_fields()
        self.last_reason = "exit_mode"

    def reset_command(self) -> None:
        self.cumulative_command = [0.0] * 6

    def set_tool_pos(self, tool_pos: Optional[Iterable[float]]) -> None:
        values = self._vec(tool_pos, 6)
        if not self._finite_values(values):
            values = [0.0] * 6
        self.tool_pos = values
        self.tool_transform = self._pose_to_transform(values)

    def update_tau_bias(self, tau_ext: Iterable[float]) -> List[float]:
        values = self._required_vec(tau_ext, 6, "tau_ext")
        self.config["tau_bias"] = list(values)
        self._save_config()
        return list(values)

    def reload_config_if_changed(self, force: bool = False) -> bool:
        if not force:
            now = time.perf_counter()
            if now - self._last_config_reload_check_perf < 1.0:
                return False
            self._last_config_reload_check_perf = now

        current_mtime = self._config_file_mtime()
        if not force and current_mtime == self._config_mtime:
            return False
        if current_mtime is None and not force:
            return False

        previous_config = self.config
        try:
            self.config = self._load_config(self.config_path)
            self._apply_config_vectors()
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            self.config = previous_config
            self._apply_config_vectors()
            return False

        self._config_mtime = current_mtime
        return True

    def update(self, control_state: Optional[Dict[str, Any]], loop_dt: Optional[float] = None) -> Optional[List[float]]:
        if not self.is_active:
            self.last_reason = "inactive"
            return None

        control_state = control_state or {}
        self.last_reason = ""
        self.last_integration_dt = self._safe_loop_dt(loop_dt)
        raw_delta = self._tau_ext_to_task_delta(control_state, self.last_integration_dt)
        if self._restore_enabled():
            constrained_delta = self._restore_constraint_delta(
                control_state,
                raw_delta,
                self.last_integration_dt,
            )
        else:
            constrained_delta = self._apply_constraint(raw_delta)
            self.last_tangent_velocity = self._delta_to_velocity(constrained_delta, self.last_integration_dt)
            self.last_restore_velocity = [0.0] * 6
            self.last_restore_limited_velocity = [0.0] * 6
            self.last_restore_saturation = False

        clamped_delta = self._clamp_delta(constrained_delta, self.last_integration_dt)
        self.last_constrained_delta = list(constrained_delta)
        self.last_clamped_delta = list(clamped_delta)
        self.last_constrained_velocity = self._delta_to_velocity(constrained_delta, self.last_integration_dt)
        self.last_limited_velocity = self._delta_to_velocity(clamped_delta, self.last_integration_dt)

        if not self._finite_values(clamped_delta):
            self.reset_command()
            self.last_command = [0.0] * 6
            self.last_applied_delta = [0.0] * 6
            self.last_reason = "non_finite_command"
            return [0.0] * 6

        previous_cumulative = list(self.cumulative_command)
        next_cumulative = self._clamp_cumulative(
            [previous_cumulative[index] + clamped_delta[index] for index in range(6)]
        )
        if self._restore_enabled():
            self.cumulative_command = list(next_cumulative)
        else:
            self.cumulative_command = self._apply_constraint(next_cumulative)
        applied_delta = [
            self.cumulative_command[index] - previous_cumulative[index]
            for index in range(6)
        ]

        command = list(self.cumulative_command)
        self.last_applied_delta = list(applied_delta)
        self.last_command = list(command)

        if self._is_zero(command) and self._is_zero(applied_delta):
            if not self.last_reason:
                self.last_reason = "zero_command"
            return None

        if not self.last_reason:
            self.last_reason = "ok"
        return command

    def _tau_ext_to_task_delta(self, control_state: Dict[str, Any], loop_dt: float) -> List[float]:
        self.last_tau_ext = self._vec(control_state.get("tau_ext"), 6)
        self.last_task_wrench = [0.0] * 6
        self.last_raw_delta = [0.0] * 6
        self.last_raw_velocity = [0.0] * 6
        tau_ext = self._processed_tau_ext(control_state)
        self.last_tau_processed = list(tau_ext)
        if not self._finite_values(tau_ext):
            self.last_reason = "non_finite_tau_ext"
            return [0.0] * 6

        q_rad = self._q_rad_from_state(control_state)
        if q_rad is None:
            self.last_reason = "missing_q"
            return [0.0] * 6

        try:
            jacobian = self._end_effector_jacobian(q_rad)
            wrench = self._joint_tau_to_task_wrench(tau_ext, jacobian)
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            self.last_reason = "jacobian_failed"
            return [0.0] * 6

        task_wrench = [float(value) for value in wrench]
        if not self._finite_values(task_wrench):
            self.last_reason = "non_finite_task_wrench"
            return [0.0] * 6
        self.last_task_wrench = list(task_wrench)
        gains = self._task_gain()
        signs = self._config_vec("task_wrench_sign", 6)
        velocity = self._task_wrench_to_velocity(task_wrench, tau_ext, jacobian, gains, signs)
        delta = [velocity[index] * loop_dt for index in range(6)]
        self.last_raw_velocity = list(velocity)
        self.last_raw_delta = list(delta)
        return delta

    def _processed_tau_ext(self, control_state: Dict[str, Any]) -> List[float]:
        tau_ext = self._vec(control_state.get("tau_ext"), 6)
        tau_bias = self._config_vec("tau_bias", 6)
        tau_deadzone = self._config_vec("tau_deadzone", 6)

        processed = []
        for index, raw_value in enumerate(tau_ext):
            value = raw_value - tau_bias[index]
            if abs(value) < tau_deadzone[index]:
                value = 0.0
            processed.append(value)
        return processed

    def snapshot(self) -> Dict[str, Any]:
        mode_config = self._mode_config()

        constraint_vector = [0.0, 0.0, 0.0]
        if self.mode == ControlMode.FIXED_LINE:
            constraint_vector = (
                list(self.reference_line_axis)
                if self.reference_valid
                else self._normalize3(
                    self._mode_constraint_vec(mode_config, "line_axis", [0.0, 0.0, 1.0])
                )
            )
        elif self.mode == ControlMode.FIXED_PLANE:
            constraint_vector = (
                list(self.reference_plane_normal)
                if self.reference_valid
                else self._normalize3(
                    self._mode_constraint_vec(mode_config, "plane_normal", [0.0, 0.0, 1.0])
                )
            )

        return {
            "active": self.active,
            "state": self.controller_state(),
            "mode": int(self.mode),
            "mode_name": self.mode_name,
            "last_reason": self.last_reason,
            "tau_ext": list(self.last_tau_ext),
            "tau_bias": self._config_vec("tau_bias", 6),
            "tau_deadzone": self._config_vec("tau_deadzone", 6),
            "tau_processed": list(self.last_tau_processed),
            "task_wrench": list(self.last_task_wrench),
            "task_gain": self._task_gain(),
            "task_input_source": self._task_input_source(),
            "integration_dt": self.last_integration_dt,
            "rate_limit_mode": self._rate_limit_mode(),
            "raw_velocity": list(self.last_raw_velocity),
            "tangent_velocity": list(self.last_tangent_velocity),
            "tangent_velocity_saturation": self.last_tangent_velocity_saturation,
            "restore_velocity": list(self.last_restore_velocity),
            "restore_limited_velocity": list(self.last_restore_limited_velocity),
            "constrained_velocity": list(self.last_constrained_velocity),
            "limited_velocity": list(self.last_limited_velocity),
            "raw_delta": list(self.last_raw_delta),
            "constrained_delta": list(self.last_constrained_delta),
            "clamped_delta": list(self.last_clamped_delta),
            "last_applied_delta": list(self.last_applied_delta),
            "last_command": list(self.last_command),
            "cumulative_command": list(self.cumulative_command),
            "axis_mask": self._axis_mask(),
            "user_axis_mask": self._user_axis_mask(),
            "constraint_vector": constraint_vector,
            "restore_enabled": self._restore_enabled(),
            "reference_valid": self.reference_valid,
            "reference_pose": list(self.reference_pose),
            "reference_point": list(self.reference_point),
            "reference_line_origin": list(self.reference_line_origin),
            "reference_line_axis": list(self.reference_line_axis),
            "reference_plane_point": list(self.reference_plane_point),
            "reference_plane_normal": list(self.reference_plane_normal),
            "reference_rcm_point": list(self.reference_rcm_point),
            "constraint_error": list(self.last_constraint_error),
            "constraint_error_norm": self.last_constraint_error_norm,
            "constraint_error_velocity": list(self.last_constraint_error_velocity),
            "restore_saturation": self.last_restore_saturation,
            "constraint_frame": self.last_constraint_frame,
            "pose_source": self.last_pose_source,
            "rate_limit": self._rate_limit_per_sec(),
            "delta_limit": list(self.last_delta_limit),
            "clip_delta_per_tick": list(self.last_delta_limit),
            "clip_cumulative": self._cumulative_limit(),
        }

    def controller_state(self) -> str:
        if not self.active:
            return "inactive"
        if self.last_reason == "constraint_error_too_large":
            return "safety_blocked"
        if self.last_reason in ("missing_pose", "missing_reference"):
            return "hold"
        return "active"

    def _reset_trace_fields(self) -> None:
        self.last_reason = ""
        self.last_tau_ext = [0.0] * 6
        self.last_tau_processed = [0.0] * 6
        self.last_task_wrench = [0.0] * 6
        self.last_integration_dt = 0.0
        self.last_raw_velocity = [0.0] * 6
        self.last_tangent_velocity = [0.0] * 6
        self.last_tangent_velocity_saturation = False
        self.last_restore_velocity = [0.0] * 6
        self.last_restore_limited_velocity = [0.0] * 6
        self.last_constrained_velocity = [0.0] * 6
        self.last_limited_velocity = [0.0] * 6
        self.last_filtered_velocity = [0.0] * 6
        self.last_raw_delta = [0.0] * 6
        self.last_constrained_delta = [0.0] * 6
        self.last_clamped_delta = [0.0] * 6
        self.last_delta_limit = [0.0] * 6
        self.last_applied_delta = [0.0] * 6
        self.last_command = [0.0] * 6
        self.reference_valid = False
        self.reference_pose = [0.0] * 6
        self.reference_point = [0.0] * 3
        self.reference_line_origin = [0.0] * 3
        self.reference_line_axis = [0.0, 0.0, 1.0]
        self.reference_plane_point = [0.0] * 3
        self.reference_plane_normal = [0.0, 0.0, 1.0]
        self.reference_rcm_point = [0.0] * 3
        self.last_constraint_error = [0.0] * 3
        self.last_constraint_error_norm = 0.0
        self.last_constraint_error_velocity = [0.0] * 3
        self.last_restore_saturation = False
        self.last_pose_source = ""
        self.last_constraint_frame = ""
        self._has_last_constraint_error = False

    def _q_rad_from_state(self, control_state: Dict[str, Any]) -> Optional[np.ndarray]:
        if "q" not in control_state:
            return None

        q_values = self._vec(control_state.get("q"), 6)
        return np.array([math.radians(value) for value in q_values], dtype=float)

    def _end_effector_jacobian(self, q_rad: np.ndarray) -> np.ndarray:
        eps = self._config_float("jacobian_eps_rad")
        if eps <= 0.0:
            raise ValueError("jacobian_eps_rad must be positive")

        base_jacobian = np.zeros((6, 6), dtype=float)
        for joint_index in range(6):
            q_plus = q_rad.copy()
            q_minus = q_rad.copy()
            q_plus[joint_index] += eps
            q_minus[joint_index] -= eps

            t_plus = self._fk_mdh(q_plus)
            t_minus = self._fk_mdh(q_minus)
            base_jacobian[:3, joint_index] = (t_plus[:3, 3] - t_minus[:3, 3]) / (2.0 * eps)
            rotation_delta = t_plus[:3, :3] @ t_minus[:3, :3].T
            base_jacobian[3:, joint_index] = self._rotation_vector(rotation_delta) / (2.0 * eps)

        # MoveTeleLTCP consumes TCP-frame deltas, so project the TCP Jacobian into that frame.
        tcp_rotation = self._fk_mdh(q_rad)[:3, :3]
        base_to_tcp = tcp_rotation.T
        jacobian = np.zeros((6, 6), dtype=float)
        jacobian[:3, :] = base_to_tcp @ base_jacobian[:3, :]
        jacobian[3:, :] = base_to_tcp @ base_jacobian[3:, :]
        return jacobian

    def _fk_mdh(self, q_rad: np.ndarray) -> np.ndarray:
        transform = np.eye(4, dtype=float)
        theta = self.mdh_theta0_rad + q_rad
        for index in range(6):
            transform = transform @ self._mdh_transform(
                self.mdh_a_m[index],
                self.mdh_alpha_rad[index],
                self.mdh_d_m[index],
                theta[index],
            )
        return transform @ self.tool_transform

    def _joint_tau_to_task_wrench(self, tau_ext: List[float], jacobian: np.ndarray) -> np.ndarray:
        tau_vector = np.array(tau_ext, dtype=float)
        damping = self._task_wrench_damping()
        if damping > 0.0:
            task_jacobian = jacobian.T
            u_matrix, singular_values, vh_matrix = np.linalg.svd(task_jacobian, full_matrices=False)
            damped_inverse = singular_values / (singular_values * singular_values + damping * damping)
            wrench = vh_matrix.T @ (damped_inverse * (u_matrix.T @ tau_vector))
        else:
            rcond = self._config_float("jacobian_rcond")
            wrench = np.linalg.pinv(jacobian.T, rcond=rcond) @ tau_vector
        return self._limit_task_wrench(wrench)

    def _task_wrench_damping(self) -> float:
        mode_config = self._mode_config()
        if "task_wrench_damping" in mode_config:
            return max(0.0, self._optional_float(mode_config.get("task_wrench_damping"), 0.0))
        task_wrench_config = self.config.get("task_wrench", {})
        if isinstance(task_wrench_config, dict) and "damping" in task_wrench_config:
            return max(0.0, self._optional_float(task_wrench_config.get("damping"), 0.0))
        return max(0.0, self._optional_float(self.config.get("jacobian_damping"), 0.0))

    def _task_wrench_norm_limit(self) -> float:
        mode_config = self._mode_config()
        if "task_wrench_norm_limit" in mode_config:
            return max(0.0, self._optional_float(mode_config.get("task_wrench_norm_limit"), 0.0))
        task_wrench_config = self.config.get("task_wrench", {})
        if isinstance(task_wrench_config, dict) and "norm_limit" in task_wrench_config:
            return max(0.0, self._optional_float(task_wrench_config.get("norm_limit"), 0.0))
        return max(0.0, self._optional_float(self.config.get("task_wrench_norm_limit"), 0.0))

    def _limit_task_wrench(self, wrench: np.ndarray) -> np.ndarray:
        return self._limit_vector_norm(wrench, self._task_wrench_norm_limit())


    def _apply_constraint(self, command: List[float]) -> List[float]:
        mode_config = self._mode_config()
        output = list(command)

        if self.mode == ControlMode.FIXED_POINT:
            output[0:3] = [0.0, 0.0, 0.0]
        elif self.mode == ControlMode.FIXED_LINE:
            axis = self._normalize3(
                self._mode_constraint_vec(mode_config, "line_axis", [0.0, 0.0, 1.0])
            )
            output[0:3] = self._project_on_axis(output[0:3], axis)
        elif self.mode == ControlMode.FIXED_PLANE:
            normal = self._normalize3(
                self._mode_constraint_vec(mode_config, "plane_normal", [0.0, 0.0, 1.0])
            )
            output[0:3] = self._project_on_plane(output[0:3], normal)

        axis_mask = self._axis_mask()
        return [output[index] * axis_mask[index] for index in range(6)]

    def _restore_constraint_delta(
        self,
        control_state: Dict[str, Any],
        raw_delta: List[float],
        loop_dt: float,
    ) -> List[float]:
        pose = self._current_tcp_pose(control_state)
        if pose is None:
            self.last_pose_source = ""
            self.last_tangent_velocity = [0.0] * 6
            self.last_restore_velocity = [0.0] * 6
            self.last_restore_limited_velocity = [0.0] * 6
            self.last_reason = "missing_pose"
            return [0.0] * 6

        if not self.reference_valid:
            self._capture_constraint_reference(pose)

        if not self.reference_valid:
            self.last_reason = "missing_reference"
            return [0.0] * 6

        user_velocity = self._delta_to_velocity(raw_delta, loop_dt)
        tangent_velocity = self._project_user_velocity_to_tangent(user_velocity, pose)
        tangent_velocity = self._limit_tangent_velocity(tangent_velocity)
        error = self._constraint_error(pose)
        restore_velocity, blocked = self._restore_velocity(error, pose, loop_dt)

        self.last_tangent_velocity = list(tangent_velocity)
        if blocked:
            return [0.0] * 6

        if self._restore_shadow_mode():
            restore_velocity = [0.0] * 6

        command_velocity = [
            tangent_velocity[index] + restore_velocity[index]
            for index in range(6)
        ]
        return [command_velocity[index] * loop_dt for index in range(6)]

    def _current_tcp_pose(self, control_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raw_pose = control_state.get("p")
        pose = self._vec(raw_pose, 6)
        if isinstance(raw_pose, (list, tuple)) and len(raw_pose) >= 6 and self._finite_values(pose):
            self.last_pose_source = "control_state.p"
            return {
                "pose": list(pose),
                "position_mm": np.array(pose[:3], dtype=float),
                "rotation": self._rpy_deg_to_rotation(pose[3], pose[4], pose[5]),
                "source": self.last_pose_source,
            }

        q_rad = self._q_rad_from_state(control_state)
        if q_rad is None:
            return None
        try:
            transform = self._fk_mdh(q_rad)
        except (ValueError, FloatingPointError):
            return None
        position_mm = transform[:3, 3] * 1000.0
        rotation = transform[:3, :3]
        if not self._finite_values(position_mm.tolist() + rotation.reshape(-1).tolist()):
            return None
        self.last_pose_source = "fk_mdh"
        return {
            "pose": position_mm.tolist() + [0.0, 0.0, 0.0],
            "position_mm": position_mm,
            "rotation": rotation,
            "source": self.last_pose_source,
        }

    def _capture_constraint_reference(self, pose: Dict[str, Any]) -> None:
        position = pose["position_mm"]
        rotation = pose["rotation"]
        mode_config = self._mode_config()
        constraint = self._constraint_config()
        reference_source = str(constraint.get("reference_source", "entry_pose")).lower()

        self.reference_pose = list(pose.get("pose", [0.0] * 6))[:6]
        self.reference_point = position.tolist()
        self.reference_line_origin = position.tolist()
        self.reference_plane_point = position.tolist()
        self.reference_rcm_point = position.tolist()

        if self.mode == ControlMode.FIXED_LINE:
            axis = self._constraint_vec(constraint, mode_config, "line_axis", [0.0, 0.0, 1.0])
            frame = self._constraint_axis_frame(constraint, default="tcp")
            axis_base = self._direction_to_base(axis, rotation, frame)
            self.reference_line_axis = axis_base
            if reference_source == "config" and isinstance(constraint.get("line_origin"), (list, tuple)):
                self.reference_line_origin = self._required_vec(
                    constraint.get("line_origin"),
                    3,
                    self._mode_key("constraint.line_origin"),
                )
            self.last_constraint_frame = f"base_from_{frame}"
        elif self.mode == ControlMode.FIXED_PLANE:
            normal = self._constraint_vec(constraint, mode_config, "plane_normal", [0.0, 0.0, 1.0])
            frame = self._constraint_axis_frame(constraint, default="tcp")
            normal_base = self._direction_to_base(normal, rotation, frame)
            self.reference_plane_normal = normal_base
            if reference_source == "config" and isinstance(constraint.get("plane_point"), (list, tuple)):
                self.reference_plane_point = self._required_vec(
                    constraint.get("plane_point"),
                    3,
                    self._mode_key("constraint.plane_point"),
                )
            self.last_constraint_frame = f"base_from_{frame}"
        elif self.mode == ControlMode.FIXED_POINT:
            if self._constraint_type() == "rcm_point":
                axis = self._constraint_vec(constraint, mode_config, "tool_axis", [0.0, 0.0, 1.0])
                frame = str(constraint.get("tool_axis_frame", "tcp")).lower()
                axis_base = np.array(self._direction_to_base(axis, rotation, frame), dtype=float)
                offset_mm = self._optional_float(constraint.get("rcm_offset_mm"), 0.0)
                self.reference_rcm_point = (position + axis_base * offset_mm).tolist()
                self.last_constraint_frame = f"base_from_{frame}"
            else:
                if reference_source == "config" and isinstance(constraint.get("reference_point"), (list, tuple)):
                    self.reference_point = self._required_vec(
                        constraint.get("reference_point"),
                        3,
                        self._mode_key("constraint.reference_point"),
                    )
                self.last_constraint_frame = "base"

        self.reference_valid = True
        self._has_last_constraint_error = False
        self.last_constraint_error = [0.0] * 3
        self.last_constraint_error_velocity = [0.0] * 3
        if not self.last_reason:
            self.last_reason = "reference_captured"

    def _constraint_error(self, pose: Dict[str, Any]) -> List[float]:
        position = pose["position_mm"]

        if self.mode == ControlMode.FIXED_POINT:
            if self._constraint_type() == "rcm_point":
                axis_base = np.array(self._current_tool_axis_base(pose), dtype=float)
                reference = np.array(self.reference_rcm_point, dtype=float)
                shaft_scale = float(np.dot(reference - position, axis_base))
                closest_on_shaft = position + shaft_scale * axis_base
                error = closest_on_shaft - reference
            else:
                error = position - np.array(self.reference_point, dtype=float)
        elif self.mode == ControlMode.FIXED_LINE:
            origin = np.array(self.reference_line_origin, dtype=float)
            axis = np.array(self.reference_line_axis, dtype=float)
            projected = origin + np.dot(position - origin, axis) * axis
            error = position - projected
        elif self.mode == ControlMode.FIXED_PLANE:
            point = np.array(self.reference_plane_point, dtype=float)
            normal = np.array(self.reference_plane_normal, dtype=float)
            error = np.dot(position - point, normal) * normal
        else:
            error = np.zeros(3, dtype=float)

        values = [float(value) for value in error.tolist()]
        return values

    def _project_user_velocity_to_tangent(self, velocity: List[float], pose: Dict[str, Any]) -> List[float]:
        mask = self._user_axis_mask()
        output = [float(velocity[index]) * mask[index] for index in range(6)]

        if self.mode == ControlMode.FIXED_POINT:
            output[0:3] = [0.0, 0.0, 0.0]
        elif self.mode == ControlMode.FIXED_LINE:
            axis_tcp = self._base_direction_to_tcp(self.reference_line_axis, pose["rotation"])
            output[0:3] = self._project_on_axis(output[0:3], axis_tcp)
        elif self.mode == ControlMode.FIXED_PLANE:
            normal_tcp = self._base_direction_to_tcp(self.reference_plane_normal, pose["rotation"])
            output[0:3] = self._project_on_plane(output[0:3], normal_tcp)

        return output

    def _limit_tangent_velocity(self, velocity: List[float]) -> List[float]:
        limited = self._limit_velocity_components(
            velocity,
            self._optional_mode_vec("tangent_velocity_limit", 6),
        )
        norm_limit = self._optional_float(
            self._mode_config().get("tangent_velocity_norm_limit"),
            0.0,
        )
        if norm_limit > 0.0:
            limited_array = self._limit_vector_norm(np.array(limited[:6], dtype=float), norm_limit)
            limited = [float(value) for value in limited_array.tolist()]

        self.last_tangent_velocity_saturation = any(
            abs(float(limited[index]) - float(velocity[index])) > 1e-9
            for index in range(6)
        )
        return limited

    def _restore_velocity(
        self,
        error: List[float],
        pose: Dict[str, Any],
        loop_dt: float,
    ) -> Tuple[List[float], bool]:
        restore = self._restore_config()
        if not bool(restore.get("enabled", False)):
            self.last_restore_velocity = [0.0] * 6
            self.last_restore_limited_velocity = [0.0] * 6
            self.last_restore_saturation = False
            return [0.0] * 6, False

        error_velocity = [0.0] * 3
        previous_error = list(self.last_constraint_error)
        if self._has_last_constraint_error and loop_dt > 0.0:
            error_velocity = [
                (error[index] - previous_error[index]) / loop_dt
                for index in range(3)
            ]
        self._has_last_constraint_error = True
        self.last_constraint_error = list(error)
        self.last_constraint_error_norm = self._norm3(error)
        self.last_constraint_error_velocity = list(error_velocity)

        error_norm = self._norm3(error)
        max_error_mm = self._optional_float(restore.get("max_error_mm"), 0.0)
        if max_error_mm > 0.0 and error_norm > max_error_mm:
            self.last_restore_velocity = [0.0] * 6
            self.last_restore_limited_velocity = [0.0] * 6
            self.last_restore_saturation = False
            self.last_reason = "constraint_error_too_large"
            return [0.0] * 6, True

        deadband_mm = max(0.0, self._optional_float(restore.get("deadband_mm"), 0.0))
        if error_norm <= deadband_mm:
            target_tcp = [0.0] * 6
            self.last_restore_velocity = list(target_tcp)
            self.last_restore_limited_velocity = self._blend_restore_velocity(target_tcp, loop_dt)
            self.last_restore_saturation = False
            return list(self.last_restore_limited_velocity), False

        kp = self._restore_gain_vec(restore, "kp", [0.0, 0.0, 0.0])
        kd = self._restore_gain_vec(restore, "kd", [0.0, 0.0, 0.0])
        restore_base = np.array(
            [
                -kp[index] * error[index] - kd[index] * error_velocity[index]
                for index in range(3)
            ],
            dtype=float,
        )
        restore_base = self._limit_vector_norm(
            restore_base,
            self._optional_float(restore.get("max_velocity_mm_s"), 0.0),
        )
        target_tcp = (pose["rotation"].T @ restore_base).tolist() + [0.0, 0.0, 0.0]
        self.last_restore_velocity = [float(value) for value in target_tcp]
        self.last_restore_limited_velocity = self._blend_restore_velocity(self.last_restore_velocity, loop_dt)
        self.last_restore_saturation = (
            self._norm3(restore_base.tolist())
            >= max(0.0, self._optional_float(restore.get("max_velocity_mm_s"), 0.0)) - 1e-9
            if self._optional_float(restore.get("max_velocity_mm_s"), 0.0) > 0.0
            else False
        )
        return list(self.last_restore_limited_velocity), False

    def _blend_restore_velocity(self, velocity: List[float], loop_dt: float) -> List[float]:
        restore = self._restore_config()
        time_constant = self._optional_float(restore.get("blend_time_constant_sec"), 0.0)
        if time_constant <= 0.0:
            return list(velocity[:6])
        alpha = self._clamp(loop_dt / (time_constant + loop_dt), 0.0, 1.0)
        return [
            self.last_restore_limited_velocity[index]
            + alpha * (float(velocity[index]) - self.last_restore_limited_velocity[index])
            for index in range(6)
        ]

    def _restore_enabled(self) -> bool:
        restore = self._restore_config()
        return bool(restore.get("enabled", False))

    def _restore_shadow_mode(self) -> bool:
        restore = self._restore_config()
        return bool(restore.get("shadow_mode", False))

    def _restore_config(self) -> Dict[str, Any]:
        restore = self._mode_config().get("restore", {})
        return restore if isinstance(restore, dict) else {}

    def _constraint_config(self) -> Dict[str, Any]:
        constraint = self._mode_config().get("constraint", {})
        return constraint if isinstance(constraint, dict) else {}

    def _constraint_type(self) -> str:
        constraint_type = str(self._constraint_config().get("type", "")).strip().lower()
        if constraint_type:
            return constraint_type
        if self.mode == ControlMode.FIXED_POINT:
            return "tcp_point"
        if self.mode == ControlMode.FIXED_LINE:
            return "line"
        if self.mode == ControlMode.FIXED_PLANE:
            return "plane"
        return ""

    def _constraint_axis_frame(self, constraint: Dict[str, Any], default: str = "tcp") -> str:
        frame = constraint.get("axis_frame", constraint.get("normal_frame", constraint.get("constraint_frame", default)))
        frame = str(frame).strip().lower()
        return frame if frame in ("base", "tcp") else default

    def _constraint_vec(
        self,
        constraint: Dict[str, Any],
        mode_config: Dict[str, Any],
        key: str,
        default: List[float],
    ) -> List[float]:
        if isinstance(constraint, dict) and key in constraint:
            return self._required_vec(constraint.get(key), 3, self._mode_key(f"constraint.{key}"))
        if isinstance(mode_config, dict) and key in mode_config:
            return self._required_vec(mode_config.get(key), 3, self._mode_key(key))
        return list(default)

    def _mode_constraint_vec(
        self,
        mode_config: Dict[str, Any],
        key: str,
        default: List[float],
    ) -> List[float]:
        constraint = mode_config.get("constraint", {}) if isinstance(mode_config, dict) else {}
        return self._constraint_vec(
            constraint if isinstance(constraint, dict) else {},
            mode_config,
            key,
            default,
        )

    def _direction_to_base(self, direction: List[float], rotation: np.ndarray, frame: str) -> List[float]:
        vector = np.array(self._normalize3(direction), dtype=float)
        if frame == "tcp":
            vector = rotation @ vector
        return self._normalize3(vector.tolist())

    def _base_direction_to_tcp(self, direction: List[float], rotation: np.ndarray) -> List[float]:
        vector = rotation.T @ np.array(self._normalize3(direction), dtype=float)
        return self._normalize3(vector.tolist())

    def _current_tool_axis_base(self, pose: Dict[str, Any]) -> List[float]:
        constraint = self._constraint_config()
        axis = self._constraint_vec(constraint, self._mode_config(), "tool_axis", [0.0, 0.0, 1.0])
        frame = str(constraint.get("tool_axis_frame", "tcp")).strip().lower()
        if frame not in ("base", "tcp"):
            frame = "tcp"
        return self._direction_to_base(axis, pose["rotation"], frame)


    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        with config_path.open("r", encoding="utf-8") as config_file:
            loaded = json.load(config_file)
        if not isinstance(loaded, dict):
            raise ValueError(f"Fixed teleop config must be a JSON object: {config_path}")
        return loaded

    def _save_config(self) -> None:
        tmp_path = self.config_path.with_name(f"{self.config_path.name}.tmp")
        with tmp_path.open("w", encoding="utf-8", newline="\n") as config_file:
            json.dump(self.config, config_file, ensure_ascii=False, indent=2)
            config_file.write("\n")
        tmp_path.replace(self.config_path)
        self._config_mtime = self._config_file_mtime()

    def _default_tool_pos(self) -> List[float]:
        if "tool_pos" in self.config:
            return self._vec(self.config.get("tool_pos"), 6)

        robot_info_path = Path(__file__).resolve().with_name("robot_info.json")
        try:
            with robot_info_path.open("r", encoding="utf-8") as robot_info_file:
                robot_info = json.load(robot_info_file)
        except (OSError, json.JSONDecodeError):
            return [0.0] * 6
        if not isinstance(robot_info, dict):
            return [0.0] * 6
        return self._vec(robot_info.get("tool_pos"), 6)

    def _config_file_mtime(self) -> Optional[float]:
        try:
            return self.config_path.stat().st_mtime
        except OSError:
            return None

    def _apply_config_vectors(self) -> None:
        self.mdh_a_m = self._mdh_vec("a_m")
        self.mdh_alpha_rad = self._mdh_vec("alpha_rad")
        self.mdh_d_m = self._mdh_vec("d_m")
        self.mdh_theta0_rad = self._mdh_vec("theta0_rad")

    def _coerce_mode(self, mode: Any) -> ControlMode:
        try:
            return ControlMode(int(mode))
        except (TypeError, ValueError):
            return ControlMode.NONE

    def _task_gain(self) -> List[float]:
        mode_config = self._mode_config()
        rotation_input = self._rotation_input_config(mode_config)
        if self.mode == ControlMode.FIXED_POINT:
            if bool(rotation_input.get("enabled", False)):
                if self._task_input_source() in ("joint_admittance", "joint_twist"):
                    return [0.0] * 6
                point_gain = self._dict_float(
                    rotation_input,
                    "gain",
                    self._mode_key("rotation_input.gain"),
                )
                axis_mask = self._axis_mask()
                return [0.0, 0.0, 0.0] + [
                    point_gain * axis_mask[index]
                    for index in range(3, 6)
                ]

        force_to_line = mode_config.get("force_to_line", {})
        if self.mode == ControlMode.FIXED_LINE and isinstance(force_to_line, dict):
            if bool(force_to_line.get("enabled", False)):
                axis = self._normalize3(
                    self._mode_constraint_vec(mode_config, "line_axis", [0.0, 0.0, 1.0])
                )
                line_gain = self._dict_float(
                    force_to_line,
                    "gain",
                    self._mode_key("force_to_line.gain"),
                )
                return [axis[index] * line_gain for index in range(3)] + [0.0, 0.0, 0.0]

        if self.mode in self.MODE_NAMES:
            return self._dict_vec(mode_config, "task_gain", 6, self._mode_key("task_gain"))

        return [0.0] * 6

    def _task_wrench_to_velocity(
        self,
        task_wrench: List[float],
        tau_ext: List[float],
        jacobian: np.ndarray,
        gains: List[float],
        signs: List[float],
    ) -> List[float]:
        mode_config = self._mode_config()
        rotation_input = self._rotation_input_config(mode_config)
        if self.mode == ControlMode.FIXED_POINT:
            if bool(rotation_input.get("enabled", False)):
                source = self._task_input_source()
                if source in ("joint_admittance", "joint_twist"):
                    gain = self._dict_float(
                        rotation_input,
                        "joint_admittance_gain",
                        self._mode_key("rotation_input.joint_admittance_gain"),
                    )
                    twist = jacobian @ np.array(tau_ext, dtype=float)
                    angular_deg = np.degrees(twist[3:6]).tolist()
                    velocity = [0.0] * 6
                    for rotation_index in range(3):
                        velocity[rotation_index + 3] = (
                            gain
                            * angular_deg[rotation_index]
                            * signs[rotation_index + 3]
                        )
                    return velocity

                point_gain = self._dict_float(
                    rotation_input,
                    "gain",
                    self._mode_key("rotation_input.gain"),
                )
                weights = self._dict_matrix(
                    rotation_input,
                    "weights",
                    3,
                    6,
                    self._mode_key("rotation_input.weights"),
                )
                velocity = [0.0] * 6
                for rotation_index in range(3):
                    velocity[rotation_index + 3] = (
                        point_gain
                        * self._dot(task_wrench, weights[rotation_index])
                        * signs[rotation_index + 3]
                    )
                return velocity

        force_to_line = mode_config.get("force_to_line", {})
        if self.mode == ControlMode.FIXED_LINE and isinstance(force_to_line, dict):
            if bool(force_to_line.get("enabled", False)):
                axis = self._normalize3(
                    self._mode_constraint_vec(mode_config, "line_axis", [0.0, 0.0, 1.0])
                )
                force_direction = self._normalize3(
                    self._dict_vec(
                        force_to_line,
                        "force_direction",
                        3,
                        self._mode_key("force_to_line.force_direction"),
                    )
                )
                line_gain = self._dict_float(
                    force_to_line,
                    "gain",
                    self._mode_key("force_to_line.gain"),
                )
                line_velocity = line_gain * self._dot3(task_wrench[0:3], force_direction)
                velocity = [0.0] * 6
                for index in range(3):
                    velocity[index] = axis[index] * line_velocity * signs[index]
                return velocity

        return [task_wrench[index] * gains[index] * signs[index] for index in range(6)]

    def _task_input_source(self) -> str:
        mode_config = self._mode_config()
        if self.mode == ControlMode.FIXED_POINT:
            source = str(self._rotation_input_config(mode_config).get("source", "task_wrench")).strip().lower()
            if source:
                return source
        return "task_wrench"

    @staticmethod
    def _rotation_input_config(mode_config: Dict[str, Any]) -> Dict[str, Any]:
        rotation_input = mode_config.get("rotation_input", {})
        return rotation_input if isinstance(rotation_input, dict) else {}

    def _clamp_delta(self, command: List[float], loop_dt: float) -> List[float]:
        limits = [rate * loop_dt for rate in self._rate_limit_per_sec()]
        self.last_delta_limit = list(limits)
        if self._use_soft_limit():
            limited_delta = [
                self._soft_limit_with_limit(command[index], limits[index])
                for index in range(6)
            ]
        else:
            limited_delta = [self._clamp_with_limit(command[index], limits[index]) for index in range(6)]

        limited_velocity = self._delta_to_velocity(limited_delta, loop_dt)
        filtered_velocity = self._filtered_velocity(limited_velocity, loop_dt)
        return [filtered_velocity[index] * loop_dt for index in range(6)]

    def _clamp_cumulative(self, command: List[float]) -> List[float]:
        limits = self._cumulative_limit()
        return [self._clamp_with_limit(command[index], limits[index]) for index in range(6)]

    def _cumulative_limit(self) -> List[float]:
        if self.mode in self.MODE_NAMES:
            mode_config = self._mode_config()
            if "cumulative" in mode_config:
                return self._dict_vec(mode_config, "cumulative", 6, self._mode_key("cumulative"))
        return self._section_vec("clip", "cumulative", None, 6)

    def _safe_loop_dt(self, loop_dt: Optional[float]) -> float:
        timing = self.config.get("timing", {})
        if not isinstance(timing, dict):
            raise ValueError("Missing fixed teleop config section: timing")
        default_dt = self._dict_float(
            timing,
            "default_loop_dt_sec",
            "timing.default_loop_dt_sec",
        )
        min_dt = self._dict_float(timing, "min_loop_dt_sec", "timing.min_loop_dt_sec")
        max_dt = self._dict_float(timing, "max_loop_dt_sec", "timing.max_loop_dt_sec")
        if min_dt <= 0.0:
            min_dt = 0.001
        if max_dt < min_dt:
            max_dt = min_dt
        try:
            dt = float(loop_dt)
        except (TypeError, ValueError):
            dt = default_dt
        if not math.isfinite(dt) or dt <= 0.0:
            dt = default_dt
        return self._clamp(dt, min_dt, max_dt)

    def _rate_limit_per_sec(self) -> List[float]:
        if self.mode not in self.MODE_NAMES:
            return [0.0] * 6

        mode_rate = self._mode_config().get("rate")
        if mode_rate is not None:
            return self._required_vec(mode_rate, 6, self._mode_key("rate"))

        raise ValueError(f"Missing fixed teleop config key: {self._mode_key('rate')}")

    def _use_soft_limit(self) -> bool:
        clip_config = self.config.get("clip", {})
        if not isinstance(clip_config, dict):
            raise ValueError("Missing fixed teleop config section: clip")
        if "soft_limit" not in clip_config:
            raise ValueError("Missing fixed teleop config key: clip.soft_limit")
        return bool(clip_config.get("soft_limit"))

    def _rate_limit_mode(self) -> str:
        return "soft_rate" if self._use_soft_limit() else "hard_rate"

    @staticmethod
    def _delta_to_velocity(delta: List[float], loop_dt: float) -> List[float]:
        if loop_dt <= 0.0:
            return [0.0] * 6
        return [float(value) / loop_dt for value in delta[:6]]

    def _filtered_velocity(self, velocity: List[float], loop_dt: float) -> List[float]:
        time_constant = self._velocity_filter_time_constant()
        if time_constant <= 0.0:
            filtered_velocity = list(velocity[:6])
            self.last_filtered_velocity = list(filtered_velocity)
            return list(filtered_velocity)

        alpha = loop_dt / (time_constant + loop_dt)
        alpha = self._clamp(alpha, 0.0, 1.0)
        reset_on_sign_change = self._velocity_filter_reset_on_sign_change()
        previous_velocity = list(self.last_filtered_velocity[:6])
        if reset_on_sign_change:
            previous_velocity = [
                0.0
                if float(velocity[index]) * previous_velocity[index] < 0.0
                else previous_velocity[index]
                for index in range(6)
            ]
        filtered = [
            previous_velocity[index]
            + alpha * (float(velocity[index]) - previous_velocity[index])
            for index in range(6)
        ]
        self.last_filtered_velocity = list(filtered)
        return filtered

    def _velocity_filter_time_constant(self) -> float:
        mode_filter_config = self._mode_config().get("filter", {})
        if (
            isinstance(mode_filter_config, dict)
            and mode_filter_config.get("velocity_time_constant_sec") is not None
        ):
            filter_config = mode_filter_config
            path = self._mode_key("filter.velocity_time_constant_sec")
        else:
            filter_config = self.config.get("filter", {})
            path = "filter.velocity_time_constant_sec"
        if not isinstance(filter_config, dict):
            raise ValueError("Missing fixed teleop config section: filter")
        value = self._dict_float(filter_config, "velocity_time_constant_sec", path)
        if not math.isfinite(value):
            raise ValueError("Fixed teleop config key filter.velocity_time_constant_sec contains non-finite value")
        return max(0.0, value)

    def _velocity_filter_reset_on_sign_change(self) -> bool:
        mode_filter_config = self._mode_config().get("filter", {})
        if isinstance(mode_filter_config, dict) and "reset_on_sign_change" in mode_filter_config:
            return bool(mode_filter_config.get("reset_on_sign_change"))
        filter_config = self.config.get("filter", {})
        if isinstance(filter_config, dict) and "reset_on_sign_change" in filter_config:
            return bool(filter_config.get("reset_on_sign_change"))
        return False

    def _mode_config(self) -> Dict[str, Any]:
        modes = self.config.get("modes", {})
        if not isinstance(modes, dict):
            return {}
        mode_config = modes.get(self.mode_name, {})
        if not isinstance(mode_config, dict):
            return {}
        return self._mode_config_with_profile(self.mode_name, mode_config)

    def _mode_config_with_profile(self, mode_name: str, mode_config: Dict[str, Any]) -> Dict[str, Any]:
        output = dict(mode_config)
        profiles = self.config.get("mode_profiles", {})
        profile = profiles.get(mode_name, {}) if isinstance(profiles, dict) else {}
        if not isinstance(profile, dict):
            return output

        filter_config = dict(output.get("filter", {})) if isinstance(output.get("filter"), dict) else {}
        filter_time = profile.get("filter_time_constant_sec")
        if filter_time is not None:
            filter_config["velocity_time_constant_sec"] = filter_time
        if filter_config:
            output["filter"] = filter_config

        if mode_name == "fixed_point":
            self._apply_profile_fixed_point(output, profile)
        elif mode_name == "fixed_line":
            self._apply_profile_fixed_line(output, profile)
        elif mode_name == "fixed_plane":
            self._apply_profile_fixed_plane(output, profile)

        return output

    def _apply_profile_fixed_point(self, mode_config: Dict[str, Any], profile: Dict[str, Any]) -> None:
        restore_config = mode_config.get("restore", {}) if isinstance(mode_config.get("restore"), dict) else {}
        restore_rate = self._optional_float(restore_config.get("command_velocity_limit_mm_s"), 0.0)
        rotation_velocity = self._profile_float(
            profile,
            "velocity_limit_deg_s",
            0.0,
        )
        rotation_rate = self._profile_float(
            profile,
            "rate_limit_deg_s",
            rotation_velocity,
        )
        restore_limit = self._optional_float(restore_config.get("command_cumulative_limit_mm"), 0.0)
        rotation_limit = self._profile_float(
            profile,
            "cumulative_limit_deg",
            0.0,
        )
        mode_config["rate"] = [restore_rate, restore_rate, restore_rate, rotation_rate, rotation_rate, 0.0]
        mode_config["cumulative"] = [
            restore_limit,
            restore_limit,
            restore_limit,
            rotation_limit,
            rotation_limit,
            0.0,
        ]
        mode_config["tangent_velocity_limit"] = [0.0, 0.0, 0.0, rotation_velocity, rotation_velocity, 0.0]
        mode_config["tangent_velocity_norm_limit"] = self._profile_float(
            profile,
            "velocity_norm_limit_deg_s",
            rotation_velocity,
        )

        rotation_input = dict(mode_config.get("rotation_input", {}))
        if "gain" in profile:
            rotation_input["joint_admittance_gain"] = profile.get("gain")
        mode_config["rotation_input"] = rotation_input

    def _apply_profile_fixed_line(self, mode_config: Dict[str, Any], profile: Dict[str, Any]) -> None:
        velocity_limit = self._profile_float(
            profile,
            "velocity_limit_mm_s",
            0.0,
        )
        translation_rate = self._profile_float(
            profile,
            "rate_limit_mm_s",
            velocity_limit,
        )
        translation_limit = self._profile_float(
            profile,
            "cumulative_limit_mm",
            0.0,
        )
        mode_config["rate"] = [translation_rate, translation_rate, translation_rate, 0.0, 0.0, 0.0]
        mode_config["cumulative"] = [translation_limit, translation_limit, translation_limit, 0.0, 0.0, 0.0]
        mode_config["tangent_velocity_limit"] = [velocity_limit, velocity_limit, velocity_limit, 0.0, 0.0, 0.0]
        mode_config["tangent_velocity_norm_limit"] = self._profile_float(
            profile,
            "velocity_norm_limit_mm_s",
            velocity_limit,
        )

        force_to_line = dict(mode_config.get("force_to_line", {}))
        if "gain" in profile:
            force_to_line["gain"] = profile.get("gain")
        mode_config["force_to_line"] = force_to_line

    def _apply_profile_fixed_plane(self, mode_config: Dict[str, Any], profile: Dict[str, Any]) -> None:
        velocity_limit = self._profile_float(
            profile,
            "velocity_limit_mm_s",
            0.0,
        )
        translation_rate = self._profile_float(
            profile,
            "rate_limit_mm_s",
            velocity_limit,
        )
        translation_limit = self._profile_float(
            profile,
            "cumulative_limit_mm",
            0.0,
        )
        mode_config["rate"] = [translation_rate, translation_rate, translation_rate, 0.0, 0.0, 0.0]
        mode_config["cumulative"] = [translation_limit, translation_limit, translation_limit, 0.0, 0.0, 0.0]
        mode_config["tangent_velocity_limit"] = [velocity_limit, velocity_limit, velocity_limit, 0.0, 0.0, 0.0]
        mode_config["tangent_velocity_norm_limit"] = self._profile_float(
            profile,
            "velocity_norm_limit_mm_s",
            velocity_limit,
        )
        mode_gain = self._optional_float(profile.get("gain"), 0.0)
        mode_config["task_gain"] = [mode_gain, mode_gain, mode_gain, 0.0, 0.0, 0.0]

    def _profile_float(
        self,
        profile: Dict[str, Any],
        key: str,
        default: float,
    ) -> float:
        if key in profile:
            return self._optional_float(profile.get(key), default)
        return float(default)

    def _axis_mask(self) -> List[float]:
        if self.mode not in self.MODE_NAMES:
            return [0.0] * 6
        return self._dict_vec(self._mode_config(), "axis_mask", 6, self._mode_key("axis_mask"))

    def _user_axis_mask(self) -> List[float]:
        if self.mode not in self.MODE_NAMES:
            return [0.0] * 6
        mode_config = self._mode_config()
        if "user_axis_mask" in mode_config:
            return self._dict_vec(mode_config, "user_axis_mask", 6, self._mode_key("user_axis_mask"))
        if self._restore_enabled() and self.mode in (ControlMode.FIXED_LINE, ControlMode.FIXED_PLANE):
            return [1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
        return self._axis_mask()

    def _mode_key(self, key: str) -> str:
        return f"modes.{self.mode_name}.{key}"

    def _config_vec(self, key: str, length: int) -> List[float]:
        return self._required_vec(self.config.get(key), length, key)

    def _config_float(self, key: str) -> float:
        return self._required_float(self.config.get(key), key)

    def _dict_vec(self, values: Dict[str, Any], key: str, length: int, path: str) -> List[float]:
        if not isinstance(values, dict) or key not in values:
            raise ValueError(f"Missing fixed teleop config key: {path}")
        return self._required_vec(values.get(key), length, path)

    def _dict_float(self, values: Dict[str, Any], key: str, path: str) -> float:
        if not isinstance(values, dict) or key not in values:
            raise ValueError(f"Missing fixed teleop config key: {path}")
        return self._required_float(values.get(key), path)

    def _dict_matrix(
        self,
        values: Dict[str, Any],
        key: str,
        rows: int,
        columns: int,
        path: str,
    ) -> List[List[float]]:
        if not isinstance(values, dict) or key not in values:
            raise ValueError(f"Missing fixed teleop config key: {path}")
        raw = values.get(key)
        if not isinstance(raw, (list, tuple)) or len(raw) < rows:
            raise ValueError(f"Fixed teleop config key {path} must contain {rows} rows")
        return [
            self._required_vec(raw[row_index], columns, f"{path}[{row_index}]")
            for row_index in range(rows)
        ]

    def _section_vec(
        self,
        section: str,
        key: str,
        default: Optional[Iterable[float]],
        length: int,
    ) -> List[float]:
        section_config = self.config.get(section)
        if isinstance(section_config, dict) and key in section_config:
            raw = section_config.get(key)
        elif default is not None:
            raw = default
        else:
            raise ValueError(f"Missing fixed teleop config key: {section}.{key}")
        return self._required_vec(raw, length, f"{section}.{key}")

    def _optional_mode_vec(self, key: str, length: int) -> Optional[List[float]]:
        mode_config = self._mode_config()
        if not isinstance(mode_config, dict) or key not in mode_config:
            return None
        return self._required_vec(mode_config.get(key), length, self._mode_key(key))

    def _required_vec(self, raw: Any, length: int, path: str) -> List[float]:
        if not isinstance(raw, (list, tuple)) or len(raw) < length:
            raise ValueError(f"Fixed teleop config key {path} must contain {length} numbers")
        try:
            values = [float(raw[index]) for index in range(length)]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Fixed teleop config key {path} must contain {length} numbers") from exc
        if not self._finite_values(values):
            raise ValueError(f"Fixed teleop config key {path} contains non-finite values")
        return values

    def _required_float(self, raw: Any, path: str) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Fixed teleop config key {path} must be a number") from exc
        if not math.isfinite(value):
            raise ValueError(f"Fixed teleop config key {path} contains non-finite value")
        return value

    @staticmethod
    def _optional_float(raw: Any, default: float) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return float(default)
        return value if math.isfinite(value) else float(default)

    def _restore_gain_vec(self, restore: Dict[str, Any], key: str, default: List[float]) -> List[float]:
        if isinstance(restore, dict) and key in restore:
            return self._required_vec(restore.get(key), 3, self._mode_key(f"restore.{key}"))
        return list(default)

    def _mdh_vec(self, key: str) -> np.ndarray:
        mdh_config = self.config.get("mdh")
        if not isinstance(mdh_config, dict) or key not in mdh_config:
            raise ValueError(f"Missing fixed teleop config key: mdh.{key}")
        return np.array(
            self._required_vec(mdh_config.get(key), 6, f"mdh.{key}"),
            dtype=float,
        )

    def _is_zero(self, values: Iterable[float]) -> bool:
        min_command = self._config_float("min_command")
        return all(abs(float(value)) <= min_command for value in values)

    @staticmethod
    def _mdh_transform(a_m: float, alpha_rad: float, d_m: float, theta_rad: float) -> np.ndarray:
        ca = math.cos(alpha_rad)
        sa = math.sin(alpha_rad)
        ct = math.cos(theta_rad)
        st = math.sin(theta_rad)
        return np.array(
            [
                [ct, -st, 0.0, a_m],
                [ca * st, ca * ct, -sa, -sa * d_m],
                [sa * st, sa * ct, ca, ca * d_m],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

    @classmethod
    def _pose_to_transform(cls, pose: List[float]) -> np.ndarray:
        transform = np.eye(4, dtype=float)
        transform[:3, :3] = cls._rpy_deg_to_rotation(pose[3], pose[4], pose[5])
        transform[:3, 3] = np.array(pose[:3], dtype=float) * 0.001
        return transform

    @staticmethod
    def _rpy_deg_to_rotation(u_deg: float, v_deg: float, w_deg: float) -> np.ndarray:
        u_rad = math.radians(u_deg)
        v_rad = math.radians(v_deg)
        w_rad = math.radians(w_deg)
        cu = math.cos(u_rad)
        su = math.sin(u_rad)
        cv = math.cos(v_rad)
        sv = math.sin(v_rad)
        cw = math.cos(w_rad)
        sw = math.sin(w_rad)
        rx = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, cu, -su],
                [0.0, su, cu],
            ],
            dtype=float,
        )
        ry = np.array(
            [
                [cv, 0.0, sv],
                [0.0, 1.0, 0.0],
                [-sv, 0.0, cv],
            ],
            dtype=float,
        )
        rz = np.array(
            [
                [cw, -sw, 0.0],
                [sw, cw, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        return rz @ ry @ rx

    @staticmethod
    def _rotation_vector(rotation: np.ndarray) -> np.ndarray:
        cos_angle = (float(np.trace(rotation)) - 1.0) * 0.5
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle = math.acos(cos_angle)
        vee = np.array(
            [
                rotation[2, 1] - rotation[1, 2],
                rotation[0, 2] - rotation[2, 0],
                rotation[1, 0] - rotation[0, 1],
            ],
            dtype=float,
        )
        if angle < 1e-9:
            return 0.5 * vee
        return angle / (2.0 * math.sin(angle)) * vee

    @classmethod
    def _finite_values(cls, values: Iterable[Any]) -> bool:
        try:
            return all(math.isfinite(float(value)) for value in values)
        except (TypeError, ValueError):
            return False

    @classmethod
    def _vec(cls, raw: Any, length: int) -> List[float]:
        values: List[float] = []
        if isinstance(raw, (list, tuple)):
            for index in range(length):
                try:
                    values.append(float(raw[index]))
                except (TypeError, ValueError, IndexError):
                    values.append(0.0)
        else:
            values = [0.0] * length
        if len(values) < length:
            values.extend([0.0] * (length - len(values)))
        return values[:length]

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @classmethod
    def _clamp_with_limit(cls, value: float, limit: float) -> float:
        if limit <= 0.0:
            return value
        return cls._clamp(value, -limit, limit)

    @classmethod
    def _limit_velocity_components(
        cls,
        velocity: List[float],
        limits: Optional[List[float]],
    ) -> List[float]:
        output = list(velocity[:6])
        if limits is None:
            return output
        return [
            cls._clamp_with_limit(output[index], float(limits[index]))
            for index in range(6)
        ]

    @staticmethod
    def _soft_limit_with_limit(value: float, limit: float) -> float:
        if limit <= 0.0:
            return value
        ratio = float(value) / limit
        if ratio > 20.0:
            return limit
        if ratio < -20.0:
            return -limit
        return limit * math.tanh(ratio)

    @staticmethod
    def _dot3(left: List[float], right: List[float]) -> float:
        return sum(left[index] * right[index] for index in range(3))

    @classmethod
    def _norm3(cls, values: List[float]) -> float:
        return math.sqrt(cls._dot3(values, values))

    @staticmethod
    def _dot(left: List[float], right: List[float]) -> float:
        return sum(
            left[index] * right[index]
            for index in range(min(len(left), len(right)))
        )

    @classmethod
    def _normalize3(cls, vector: List[float]) -> List[float]:
        norm = math.sqrt(cls._dot3(vector, vector))
        if norm <= 1e-12:
            return [0.0, 0.0, 1.0]
        return [value / norm for value in vector]

    @classmethod
    def _project_on_axis(cls, vector: List[float], axis: List[float]) -> List[float]:
        scale = cls._dot3(vector, axis)
        return [scale * axis[index] for index in range(3)]

    @classmethod
    def _project_on_plane(cls, vector: List[float], normal: List[float]) -> List[float]:
        normal_component = cls._project_on_axis(vector, normal)
        return [vector[index] - normal_component[index] for index in range(3)]

    @staticmethod
    def _limit_vector_norm(vector: np.ndarray, limit: float) -> np.ndarray:
        if limit <= 0.0:
            return vector
        norm = float(np.linalg.norm(vector))
        if not math.isfinite(norm) or norm <= limit or norm <= 1e-12:
            return vector
        return vector * (limit / norm)

