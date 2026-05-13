"""Reaper process control: start / stop / restart / status.

Usage:
    uv run python reaper/control.py start [project.rpp]
    uv run python reaper/control.py stop
    uv run python reaper/control.py restart [project.rpp]
    uv run python reaper/control.py status
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REAPER_EXE = Path(r"C:\Program Files\REAPER (x64)\reaper.exe")
PROCESS_NAME = "reaper.exe"


def _running_pids() -> list[int]:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROCESS_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=False,
    ).stdout
    pids: list[int] = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split(",")]
        if len(parts) >= 2 and parts[0].lower() == PROCESS_NAME:
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def is_running() -> bool:
    return bool(_running_pids())


def start(project: str | None = None) -> None:
    if is_running():
        print(f"already running (pids={_running_pids()})")
        return
    if not REAPER_EXE.exists():
        sys.exit(f"reaper.exe not found at {REAPER_EXE}")
    args = [str(REAPER_EXE)]
    if project:
        args.append(str(Path(project).resolve()))
    subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
    print(f"started: {' '.join(args)}")


def stop(timeout: float = 5.0) -> None:
    pids = _running_pids()
    if not pids:
        print("not running")
        return
    subprocess.run(["taskkill", "/IM", PROCESS_NAME], check=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running():
            print(f"stopped (was pids={pids})")
            return
        time.sleep(0.2)
    subprocess.run(["taskkill", "/F", "/IM", PROCESS_NAME], check=False)
    print(f"force-killed (was pids={pids})")


def restart(project: str | None = None) -> None:
    stop()
    time.sleep(0.5)
    start(project)


def status() -> None:
    pids = _running_pids()
    print(f"running pids: {pids}" if pids else "not running")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start"); p_start.add_argument("project", nargs="?")
    sub.add_parser("stop")
    p_restart = sub.add_parser("restart"); p_restart.add_argument("project", nargs="?")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "start":
        start(args.project)
    elif args.cmd == "stop":
        stop()
    elif args.cmd == "restart":
        restart(args.project)
    elif args.cmd == "status":
        status()


if __name__ == "__main__":
    main()
