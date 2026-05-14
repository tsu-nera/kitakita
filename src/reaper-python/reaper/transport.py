"""Reaper transport CLI (requires Reaper running + reapy bridge).

Usage:
    uv run python reaper/transport.py play
    uv run python reaper/transport.py stop
    uv run python reaper/transport.py panic         # all notes off
    uv run python reaper/transport.py bpm 138
    uv run python reaper/transport.py loop 4        # loop range = N beats from 0
    uv run python reaper/transport.py loop off
    uv run python reaper/transport.py status
"""
from __future__ import annotations

import argparse

import reapy
from reapy import reascript_api as RPR


def _project():
    return reapy.Project()


def play() -> None:
    p = _project()
    RPR.SetEditCurPos(0, False, False)
    p.play()
    print("playing")


def stop() -> None:
    p = _project()
    p.stop()
    RPR.Main_OnCommand(40345, 0)  # all notes off
    print("stopped")


def panic() -> None:
    RPR.Main_OnCommand(40345, 0)
    print("all notes off")


def set_bpm(bpm: float) -> None:
    p = _project()
    p.bpm = bpm
    print(f"bpm = {bpm}")


def set_loop(beats: float | None) -> None:
    p = _project()
    if beats is None:
        RPR.GetSetRepeat(0)
        print("loop off")
        return
    spb = 60.0 / p.bpm
    end_sec = spb * beats
    RPR.GetSet_LoopTimeRange(True, True, 0.0, end_sec, False)
    RPR.GetSetRepeat(1)
    print(f"loop on: 0 to {end_sec:.3f}s ({beats} beats @ {p.bpm} bpm)")


def status() -> None:
    p = _project()
    is_playing = bool(RPR.GetPlayState() & 1)
    repeat = bool(RPR.GetSetRepeat(-1))
    print(f"bpm     : {p.bpm}")
    print(f"playing : {is_playing}")
    print(f"repeat  : {repeat}")
    print(f"tracks  : {p.n_tracks}")
    for i, t in enumerate(p.tracks):
        print(f"  [{i}] {t.name!r}  fx={t.n_fxs}  items={t.n_items}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("play")
    sub.add_parser("stop")
    sub.add_parser("panic")
    p_bpm = sub.add_parser("bpm"); p_bpm.add_argument("value", type=float)
    p_loop = sub.add_parser("loop"); p_loop.add_argument("beats")  # number or "off"
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "play":
        play()
    elif args.cmd == "stop":
        stop()
    elif args.cmd == "panic":
        panic()
    elif args.cmd == "bpm":
        set_bpm(args.value)
    elif args.cmd == "loop":
        set_loop(None if args.beats.lower() == "off" else float(args.beats))
    elif args.cmd == "status":
        status()


if __name__ == "__main__":
    main()
