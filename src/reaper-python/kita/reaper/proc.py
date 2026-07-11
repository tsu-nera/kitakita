"""Reaper process control (Linux): start / stop / restart / status."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

PROCESS_NAME = "reaper"


def _pids() -> list[int]:
    out = subprocess.run(["pgrep", "-x", PROCESS_NAME],
                         capture_output=True, text=True, check=False).stdout
    return [int(p) for p in out.split()]


def start(project: str | None = None) -> None:
    if _pids():
        print(f"already running (pids={_pids()})")
        return
    args = [PROCESS_NAME]
    if project:
        args.append(str(Path(project).resolve()))
    subprocess.Popen(args, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"started: {' '.join(args)}")


def stop(timeout: float = 5.0) -> None:
    pids = _pids()
    if not pids:
        print("not running")
        return
    subprocess.run(["pkill", "-x", PROCESS_NAME], check=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pids():
            print(f"stopped (was pids={pids})")
            return
        time.sleep(0.2)
    subprocess.run(["pkill", "-9", "-x", PROCESS_NAME], check=False)
    print(f"force-killed (was pids={pids})")


def restart(project: str | None = None) -> None:
    stop()
    time.sleep(0.5)
    start(project)


def status() -> None:
    pids = _pids()
    print(f"running pids: {pids}" if pids else "not running")


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "status"
    if cmd == "start":
        start(argv[1] if len(argv) > 1 else None)
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart(argv[1] if len(argv) > 1 else None)
    elif cmd == "status":
        status()
    else:
        sys.exit(f"unknown reaper subcommand: {cmd} (start|stop|restart|status)")
