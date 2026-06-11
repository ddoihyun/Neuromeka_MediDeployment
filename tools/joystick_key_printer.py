"""Print connected joystick names and live joystick input events.

This is a standalone diagnostic tool based on modules/joystick/joystick_manager.py.
It uses the same pygame backend and joystick_info.json button/axis mapping, but it
does not touch the robot control loop or the global blackboard.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TextIO, Tuple

import pygame


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.joystick.joystick_settings import JoystickSettings

JOYSTICK_INFO_PATH = REPO_ROOT / "modules" / "joystick" / "joystick_info.json"
DEFAULT_LOG_DIR = REPO_ROOT / "LOG"
DEFAULT_POLL_INTERVAL = 0.01
DEFAULT_SCAN_INTERVAL = 1.0

BUTTON_ACTIONS = {
    "x1": "TILT_W_CW",
    "x2": "ZOOM_OUT",
    "x3": "ZOOM_IN",
    "x4": "TILT_W_CCW",
    "x5": "ENABLE",
}

AXIS_ACTIONS = {
    "left_right": "TILT_U",
    "up_down": "TILT_V",
}


@dataclass(frozen=True)
class ControllerMapping:
    model_name: Optional[str]
    button_labels: Dict[int, str]
    axis_labels: Dict[int, str]
    button_actions: Dict[int, str]
    axis_actions: Dict[int, str]


def load_joystick_info(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"supported_names": [], "controllers": {}}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_mapping(joystick_name: str, joystick_info: Dict[str, Any]) -> ControllerMapping:
    controllers = joystick_info.get("controllers", {})
    model_name = joystick_name if joystick_name in controllers else None

    if model_name is None:
        return ControllerMapping(
            model_name=None,
            button_labels={},
            axis_labels={},
            button_actions={},
            axis_actions={},
        )

    controller = controllers[model_name]
    button_labels = {int(index): label for label, index in controller.get("buttons", {}).items()}
    axis_labels = {int(index): label for label, index in controller.get("axes", {}).items()}

    return ControllerMapping(
        model_name=model_name,
        button_labels=button_labels,
        axis_labels=axis_labels,
        button_actions={
            index: BUTTON_ACTIONS.get(label, label.upper())
            for index, label in button_labels.items()
        },
        axis_actions={
            index: AXIS_ACTIONS.get(label, label.upper())
            for index, label in axis_labels.items()
        },
    )


def init_pygame() -> None:
    pygame.init()
    pygame.joystick.quit()
    pygame.joystick.init()
    pygame.event.set_blocked(None)


def scan_joysticks(
    joystick_info: Dict[str, Any],
    announce: bool = True,
    log_file: Optional[TextIO] = None,
) -> Dict[int, pygame.joystick.Joystick]:
    joysticks: Dict[int, pygame.joystick.Joystick] = {}
    supported_names = set(joystick_info.get("supported_names", []))

    count = pygame.joystick.get_count()
    if announce:
        emit(f"Detected joystick count: {count}", log_file)
    if count == 0:
        if announce:
            emit("No joystick is connected. Connect a joystick and keep this script running.", log_file)
        return joysticks

    for index in range(count):
        joystick = pygame.joystick.Joystick(index)
        joystick.init()
        joysticks[joystick.get_instance_id()] = joystick

        name = joystick.get_name()
        supported = "supported" if name in supported_names else "unmapped"
        if announce:
            emit(
                f"[{index}] name={name!r}, instance_id={joystick.get_instance_id()}, "
                f"buttons={joystick.get_numbuttons()}, axes={joystick.get_numaxes()}, "
                f"hats={joystick.get_numhats()} ({supported})",
                log_file,
            )

    return joysticks


def format_time() -> str:
    return time.strftime("%H:%M:%S")


def default_log_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_LOG_DIR / f"joystick_key_printer_{timestamp}.log"


def emit(line: str, log_file: Optional[TextIO] = None) -> None:
    print(line)
    if log_file:
        log_file.write(f"{line}\n")
        log_file.flush()


def describe_button(
    mapping: ControllerMapping,
    button_index: int,
    is_down: bool,
) -> str:
    label = mapping.button_labels.get(button_index, f"button_{button_index}")
    action = mapping.button_actions.get(button_index, "UNMAPPED")
    state = "PRESS" if is_down else "RELEASE"
    return f"{state} button={button_index} label={label} action={action}"


def normalize_axis_value(value: float, deadzone: float, round_digit: int) -> float:
    rounded_value = round(float(value), round_digit)
    if abs(rounded_value) < deadzone:
        return 0.0
    return rounded_value


def describe_axis(
    mapping: ControllerMapping,
    axis_index: int,
    value: float,
    deadzone: float,
    round_digit: int,
) -> Optional[str]:
    rounded_value = normalize_axis_value(value, deadzone, round_digit)
    label = mapping.axis_labels.get(axis_index, f"axis_{axis_index}")
    action = mapping.axis_actions.get(axis_index, "UNMAPPED")
    return f"AXIS axis={axis_index} label={label} action={action} value={rounded_value:+.3f}"


def emit_mapping_status(
    instance_id: int,
    mapping: ControllerMapping,
    log_file: Optional[TextIO] = None,
) -> None:
    if mapping.model_name:
        emit(f"Using mapping for instance_id={instance_id}: {mapping.model_name!r}", log_file)
    else:
        emit(f"No mapping for instance_id={instance_id}; raw buttons/axes will still print.", log_file)


def seed_joystick_state(
    joystick: pygame.joystick.Joystick,
    deadzone: float,
    round_digit: int,
    button_state: Dict[Tuple[int, int], bool],
    axis_state: Dict[Tuple[int, int], float],
    hat_state: Dict[Tuple[int, int], Tuple[int, int]],
) -> None:
    try:
        instance_id = joystick.get_instance_id()
        for button_index in range(joystick.get_numbuttons()):
            button_state[(instance_id, button_index)] = bool(joystick.get_button(button_index))
        for axis_index in range(joystick.get_numaxes()):
            axis_state[(instance_id, axis_index)] = normalize_axis_value(
                joystick.get_axis(axis_index),
                deadzone,
                round_digit,
            )
        for hat_index in range(joystick.get_numhats()):
            hat_state[(instance_id, hat_index)] = tuple(joystick.get_hat(hat_index))
    except pygame.error:
        return


def clear_instance_state(
    instance_id: int,
    button_state: Dict[Tuple[int, int], bool],
    axis_state: Dict[Tuple[int, int], float],
    hat_state: Dict[Tuple[int, int], Tuple[int, int]],
) -> None:
    for state in (button_state, axis_state, hat_state):
        for key in list(state):
            if key[0] == instance_id:
                state.pop(key, None)


def sync_joysticks(
    joysticks: Dict[int, pygame.joystick.Joystick],
    mappings: Dict[int, ControllerMapping],
    joystick_info: Dict[str, Any],
    deadzone: float,
    round_digit: int,
    button_state: Dict[Tuple[int, int], bool],
    axis_state: Dict[Tuple[int, int], float],
    hat_state: Dict[Tuple[int, int], Tuple[int, int]],
    log_file: Optional[TextIO] = None,
) -> None:
    current = scan_joysticks(joystick_info, announce=False)

    for instance_id in list(joysticks):
        if instance_id not in current:
            joystick = joysticks.pop(instance_id, None)
            mappings.pop(instance_id, None)
            clear_instance_state(instance_id, button_state, axis_state, hat_state)
            name = joystick.get_name() if joystick else "unknown"
            emit(f"{format_time()} DISCONNECT name={name!r} instance_id={instance_id}", log_file)

    for instance_id, joystick in current.items():
        is_new = instance_id not in joysticks
        joysticks[instance_id] = joystick
        if is_new:
            mapping = build_mapping(joystick.get_name(), joystick_info)
            mappings[instance_id] = mapping
            seed_joystick_state(
                joystick,
                deadzone,
                round_digit,
                button_state,
                axis_state,
                hat_state,
            )
            emit(f"{format_time()} CONNECT name={joystick.get_name()!r} instance_id={instance_id}", log_file)
            emit_mapping_status(instance_id, mapping, log_file)


def poll_joystick_state(
    joysticks: Dict[int, pygame.joystick.Joystick],
    mappings: Dict[int, ControllerMapping],
    deadzone: float,
    round_digit: int,
    button_state: Dict[Tuple[int, int], bool],
    axis_state: Dict[Tuple[int, int], float],
    hat_state: Dict[Tuple[int, int], Tuple[int, int]],
    log_file: Optional[TextIO] = None,
) -> None:
    pygame.event.pump()

    for instance_id, joystick in list(joysticks.items()):
        try:
            name = joystick.get_name()
            mapping = mappings.get(instance_id) or ControllerMapping(None, {}, {}, {}, {})

            for button_index in range(joystick.get_numbuttons()):
                key = (instance_id, button_index)
                is_down = bool(joystick.get_button(button_index))
                previous = button_state.get(key)
                button_state[key] = is_down
                if previous is not None and previous != is_down:
                    detail = describe_button(mapping, button_index, is_down)
                    emit(f"{format_time()} name={name!r} instance_id={instance_id} {detail}", log_file)

            for axis_index in range(joystick.get_numaxes()):
                key = (instance_id, axis_index)
                value = normalize_axis_value(joystick.get_axis(axis_index), deadzone, round_digit)
                previous = axis_state.get(key)
                axis_state[key] = value
                if previous is not None and previous != value:
                    detail = describe_axis(mapping, axis_index, value, deadzone, round_digit)
                    emit(f"{format_time()} name={name!r} instance_id={instance_id} {detail}", log_file)

            for hat_index in range(joystick.get_numhats()):
                key = (instance_id, hat_index)
                value = tuple(joystick.get_hat(hat_index))
                previous = hat_state.get(key)
                hat_state[key] = value
                if previous is not None and previous != value:
                    emit(
                        f"{format_time()} name={name!r} instance_id={instance_id} "
                        f"HAT hat={hat_index} value={value}",
                        log_file,
                    )
        except pygame.error:
            continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect joysticks and print live button/axis input events."
    )
    parser.add_argument(
        "--deadzone",
        type=float,
        default=None,
        help="Axis values with absolute value below this are printed as zero. Defaults to joystick_info input.deadzone.",
    )
    parser.add_argument(
        "--round-digit",
        type=int,
        default=None,
        help="Axis rounding precision. Defaults to joystick_info input.round_digit.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Only list connected joysticks and exit.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Path to save printed input events. Defaults to LOG/joystick_key_printer_*.log.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Print events without saving a log file.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Seconds between joystick state polls.",
    )
    parser.add_argument(
        "--scan-interval",
        type=float,
        default=DEFAULT_SCAN_INTERVAL,
        help="Seconds between connection rescans.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    joystick_info = load_joystick_info(JOYSTICK_INFO_PATH)
    settings = JoystickSettings(joystick_info)
    deadzone = args.deadzone if args.deadzone is not None else settings.input_deadzone()
    round_digit = args.round_digit if args.round_digit is not None else settings.round_digit()
    log_path = None if args.no_log or args.list else args.log_file or default_log_path()
    log_file: Optional[TextIO] = None

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")
        emit(f"Saving joystick input log to: {log_path}", log_file)

    init_pygame()
    joysticks = scan_joysticks(joystick_info, log_file=log_file)
    mappings = {
        instance_id: build_mapping(joystick.get_name(), joystick_info)
        for instance_id, joystick in joysticks.items()
    }

    for instance_id, mapping in mappings.items():
        emit_mapping_status(instance_id, mapping, log_file)

    if args.list:
        pygame.quit()
        if log_file:
            log_file.close()
        return 0

    emit("Listening for joystick input. Press Ctrl+C to stop.", log_file)
    button_state: Dict[Tuple[int, int], bool] = {}
    axis_state: Dict[Tuple[int, int], float] = {}
    hat_state: Dict[Tuple[int, int], Tuple[int, int]] = {}

    for joystick in joysticks.values():
        seed_joystick_state(joystick, deadzone, round_digit, button_state, axis_state, hat_state)

    try:
        last_scan = time.monotonic()
        while True:
            poll_joystick_state(
                joysticks=joysticks,
                mappings=mappings,
                deadzone=deadzone,
                round_digit=round_digit,
                button_state=button_state,
                axis_state=axis_state,
                hat_state=hat_state,
                log_file=log_file,
            )

            now = time.monotonic()
            if now - last_scan >= args.scan_interval:
                sync_joysticks(
                    joysticks=joysticks,
                    mappings=mappings,
                    joystick_info=joystick_info,
                    deadzone=deadzone,
                    round_digit=round_digit,
                    button_state=button_state,
                    axis_state=axis_state,
                    hat_state=hat_state,
                    log_file=log_file,
                )
                last_scan = now

            time.sleep(max(args.poll_interval, 0.001))
    except KeyboardInterrupt:
        emit("\nStopped.", log_file)
    finally:
        if log_file:
            log_file.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
