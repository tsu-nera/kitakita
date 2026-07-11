"""Reaper transport (requires Reaper running + reapy bridge)."""
from __future__ import annotations

import reapy
from reapy import reascript_api as RPR

from kita.model import Song


def play() -> None:
    p = reapy.Project()
    RPR.SetEditCurPos(0, False, False)
    p.play()
    print("playing")


def stop() -> None:
    p = reapy.Project()
    p.stop()
    RPR.Main_OnCommand(40345, 0)  # all notes off
    print("stopped")


def panic() -> None:
    RPR.Main_OnCommand(40345, 0)
    print("all notes off")


def set_bpm(bpm: float) -> None:
    reapy.Project().bpm = bpm
    print(f"bpm = {bpm}")


def loop_off() -> None:
    RPR.GetSetRepeat(0)
    print("loop off")


def loop_range(start_sec: float, end_sec: float, label: str = "") -> None:
    RPR.GetSet_LoopTimeRange(True, True, start_sec, end_sec, False)
    RPR.GetSetRepeat(1)
    print(f"loop on: {start_sec:.3f}s to {end_sec:.3f}s {label}".rstrip())


def loop(song: Song, arg: str) -> None:
    """`off` / 拍数 / セクション名 のいずれかでループ範囲を設定する。"""
    if arg.lower() == "off":
        loop_off()
        return
    try:
        beats = float(arg)
    except ValueError:
        for sec, b0, b1 in song.section_bounds():
            if sec.name == arg:
                loop_range(song.bar_to_sec(b0), song.bar_to_sec(b1),
                           f"(section {arg}: bars {b0}-{b1})")
                return
        names = [s.name for s in song.effective_sections]
        raise SystemExit(f"no such section: {arg} (sections: {names})")
    loop_range(0.0, beats * 60.0 / song.bpm, f"({beats} beats @ {song.bpm} bpm)")


def transport_status() -> None:
    p = reapy.Project()
    is_playing = bool(RPR.GetPlayState() & 1)
    repeat = bool(RPR.GetSetRepeat(-1))
    print(f"bpm     : {p.bpm}")
    print(f"playing : {is_playing}")
    print(f"repeat  : {repeat}")
    print(f"tracks  : {p.n_tracks}")
    for i, t in enumerate(p.tracks):
        print(f"  [{i}] {t.name!r}  fx={t.n_fxs}  items={t.n_items}")
