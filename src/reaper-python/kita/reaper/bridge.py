"""Shared Reaper-side helpers (sampler detection, path compare, region enum).

reconcile と status は「サンプラは在るか」「リージョンはどう並んでいるか」の
判定を共有する必要があるので、その解釈はここに一度だけ置く。
"""
from __future__ import annotations

import os

from reapy import reascript_api as RPR

SAMPLER_FX = "ReaSamplomatic5000"
SYNTH_FX = "ReaSynth"
FILTER_FX = "filters/resonantlowpass"  # 同梱 JSFX "Resonant Lowpass Filter"
FILTER_FX_TAG = "resonant lowpass"     # FX 名からの検出タグ


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
    for i in range(track.n_fxs):
        if "reasynth" in _fx_name(track, i).lower():
            return i
    return -1


def filter_index(track) -> int:
    """Index of the JSFX Resonant Lowpass Filter instance, or -1."""
    for i in range(track.n_fxs):
        if FILTER_FX_TAG in _fx_name(track, i).lower():
            return i
    return -1


def synth_param_indices(track, fx_idx: int) -> dict[str, int]:
    """ReaSynth のパラメータ名 → index。波形 mix を名前で引くため(index はビルド差あり)。"""
    out: dict[str, int] = {}
    for i in range(int(RPR.TrackFX_GetNumParams(track.id, fx_idx))):
        ret = RPR.TrackFX_GetParamName(track.id, fx_idx, i, "", 256)
        name = str(ret[4]) if isinstance(ret, (tuple, list)) and len(ret) >= 5 else str(ret)
        out[name.lower()] = i
    return out


def list_regions(project) -> list[tuple[str, float, float, int]]:
    """(name, start_sec, end_sec, displayed_number) の列。マーカーは含まない。

    EnumProjectMarkers 系は nameOut が char** のため dist API 越しに名前が
    取れない。GetRegionOrMarker 系(REAPER 7+)を使うこと。
    """
    regions = []
    for i in range(int(RPR.GetNumRegionsOrMarkers(project.id))):
        pm = RPR.GetRegionOrMarker(project.id, i, "")
        if not RPR.GetRegionOrMarkerInfo_Value(project.id, pm, "B_ISREGION"):
            continue
        start = RPR.GetRegionOrMarkerInfo_Value(project.id, pm, "D_STARTPOS")
        end = RPR.GetRegionOrMarkerInfo_Value(project.id, pm, "D_ENDPOS")
        num = RPR.GetRegionOrMarkerInfo_Value(project.id, pm, "I_NUMBER")
        ret = RPR.GetSetRegionOrMarkerInfo_String(project.id, pm, "P_NAME", "", False)
        name = str(ret[4]) if isinstance(ret, (tuple, list)) and len(ret) >= 5 else ""
        regions.append((name, float(start), float(end), int(num)))
    return regions
