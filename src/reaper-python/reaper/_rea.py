"""Shared Reaper-side helpers (sampler detection, path compare).

setup.py and status.py must agree on "is the sampler present?", so that
logic lives here once. Imported as `from reaper._rea import ...` (reaper/ is
an implicit namespace package; scripts put the project root on sys.path).
"""
from __future__ import annotations

import os

from reapy import reascript_api as RPR

SAMPLER_FX = "ReaSamplomatic5000"
SYNTH_FX = "ReaSynth"


def norm(p: str | os.PathLike) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def find_track(project, name: str):
    for t in project.tracks:
        if t.name == name:
            return t
    return None


def _fx_name(track, idx: int) -> str:
    ret = RPR.TrackFX_GetFXName(track.id, idx, "", 256)
    if isinstance(ret, (tuple, list)) and len(ret) >= 4:
        return str(ret[3])
    return str(ret)


def get_file0(track, fx_idx: int) -> str:
    ret = RPR.TrackFX_GetNamedConfigParm(track.id, fx_idx, "FILE0", "", 4096)
    # reapy echoes the call args back; the value buffer is at index 4.
    if isinstance(ret, (tuple, list)) and len(ret) >= 5:
        return str(ret[4])
    return ""


def sampler_index(track) -> int:
    """Index of the ReaSamplomatic5000 instance, or -1.

    Reaper renames RS5000 instances to "<sample> (RS5K)", so the original
    FX name is gone. Detect by the "(RS5K)" tag, the original name, or — as
    a fallback — any FX exposing a non-empty FILE0.
    """
    n = track.n_fxs
    for i in range(n):
        nm = _fx_name(track, i).lower()
        if "(rs5k)" in nm or "reasamplomatic" in nm:
            return i
    for i in range(n):
        if get_file0(track, i):
            return i
    return -1


def synth_index(track) -> int:
    """Index of the ReaSynth instance, or -1."""
    n = track.n_fxs
    for i in range(n):
        if "reasynth" in _fx_name(track, i).lower():
            return i
    return -1
