from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List


TARGETS = ("run_fsm.py", "run_front.py", "run_fsm", "run_front")


@dataclass
class ProcessInfo:
    pid: int
    name: str
    command_line: str


def _windows_processes() -> List[ProcessInfo]:
    target_array = "@(" + ",".join(repr(target) for target in TARGETS) + ")"
    command = rf"""
$targets = {target_array}
Get-CimInstance Win32_Process |
  Where-Object {{
    $cmd = $_.CommandLine
    $name = $_.Name
    $cmd -and
      ($name -match '^(python|pythonw|py)([0-9.]+)?\.exe$') -and
      (($targets | Where-Object {{ $cmd -like "*$_*" }}).Count -gt 0)
  }} |
  Select-Object ProcessId,Name,CommandLine |
  ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    items = raw if isinstance(raw, list) else [raw]
    processes: List[ProcessInfo] = []
    for item in items:
        try:
            pid = int(item["ProcessId"])
        except (KeyError, TypeError, ValueError):
            continue
        if pid == os.getpid():
            continue
        processes.append(
            ProcessInfo(
                pid=pid,
                name=str(item.get("Name", "")),
                command_line=str(item.get("CommandLine", "")),
            )
        )
    return processes


def _posix_processes() -> List[ProcessInfo]:
    result = subprocess.run(
        ["ps", "-eo", "pid=,comm=,args="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    processes: List[ProcessInfo] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        name = parts[1]
        command_line = parts[2]
        if any(target in command_line for target in TARGETS):
            processes.append(ProcessInfo(pid=pid, name=name, command_line=command_line))
    return processes


def find_processes() -> List[ProcessInfo]:
    if platform.system().lower() == "windows":
        return _windows_processes()
    return _posix_processes()


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_process(process: ProcessInfo, *, force: bool, timeout_sec: float) -> bool:
    if platform.system().lower() == "windows":
        args = ["taskkill", "/PID", str(process.pid), "/T"]
        if force:
            args.append("/F")
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        return result.returncode == 0 or not is_running(process.pid)

    os.kill(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not is_running(process.pid):
            return True
        time.sleep(0.05)
    if force and is_running(process.pid):
        os.kill(process.pid, signal.SIGKILL)
    return not is_running(process.pid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop run_fsm.py and run_front.py processes.")
    parser.add_argument("--dry-run", action="store_true", help="Only print matching processes.")
    parser.add_argument("--force", action="store_true", help="Force termination if supported.")
    parser.add_argument("--timeout-sec", type=float, default=2.0)
    args = parser.parse_args()

    processes = find_processes()
    if not processes:
        print("No run_fsm.py or run_front.py processes found.")
        return 0

    for process in processes:
        print(f"{process.pid}\t{process.name}\t{process.command_line}")

    if args.dry_run:
        return 0

    failures = []
    for process in processes:
        try:
            if not stop_process(process, force=args.force, timeout_sec=max(0.1, args.timeout_sec)):
                failures.append(process.pid)
        except OSError:
            if is_running(process.pid):
                failures.append(process.pid)

    if failures:
        print(f"Failed to stop: {failures}", file=sys.stderr)
        return 1
    print(f"Stopped {len(processes)} process(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
