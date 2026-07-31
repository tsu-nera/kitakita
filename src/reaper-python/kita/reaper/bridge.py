"""Shared Reaper-side helpers (sampler detection, path compare, region enum).

reconcile と status は「サンプラは在るか」「リージョンはどう並んでいるか」の
判定を共有する必要があるので、その解釈はここに一度だけ置く。
"""
from __future__ import annotations

import os
from functools import lru_cache

from reapy import reascript_api as RPR

SAMPLER_FX = "ReaSamplomatic5000"
SYNTH_FX = "ReaSynth"
FILTER_FX = "filters/resonantlowpass"  # 同梱 JSFX "Resonant Lowpass Filter"
FILTER_FX_TAG = "resonant lowpass"     # FX 名からの検出タグ

# envelope point 読み出し用のバッファサイズ(GetEnvelopeStateChunk)。
# 383点で約11KB。フル尺(6分)×複数トラックでも余裕を見て 1MB を確保する。
_CHUNK_BUFSIZE = 1 << 20


@lru_cache(maxsize=None)
def _scale_to(mode: int, value: float) -> float:
    """ScaleToEnvelopeMode(mode, value) のメモ化ラッパ。

    (mode, value) だけで決まる純関数(REAPER 側に副作用/内部状態の依存が無い)
    なのでプロセス内でキャッシュしてよい。duck の点列に現れる gain 値は
    高々数種類(gain_linear と gain_linear*depth)なので、キャッシュにより
    RPR 呼び出し回数が点数ではなく「相異なる値の数」になる。

    変換式そのものを Python で再実装しないこと — PR #17 で踏んだ
    fader-scaling(mode=1)の無音バグと同種の不一致リスクが戻る。REAPER に
    「聞く」のは変えず、聞く回数だけを削減する。
    """
    return float(RPR.ScaleToEnvelopeMode(mode, value))


@lru_cache(maxsize=None)
def _scale_from(mode: int, value: float) -> float:
    """ScaleFromEnvelopeMode(mode, value) のメモ化ラッパ。_scale_to 参照。"""
    return float(RPR.ScaleFromEnvelopeMode(mode, value))


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


TOGGLE_VOLUME_ENVELOPE = 40406  # Track: Toggle track volume envelope visible


def get_volume_envelope(track):
    """Volume エンベロープを返す(無ければ None)。作りたい場合は
    ensure_volume_envelope を使うこと(表示トグルで生成)。

    reapy の dist API は無い場合も NULL ポインタの文字列表現
    "(TrackEnvelope*)0x0000000000000000" を返す(空文字/0 ではない)ので、
    reapy.core.reapy_object の判定パターンに合わせて末尾で見る。
    """
    env = RPR.GetTrackEnvelopeByName(track.id, "Volume")
    if not env or str(env).endswith("0x0000000000000000"):
        return None
    return env


def ensure_volume_envelope(track):
    """Volume エンベロープを取得し、無ければ action 40406 で作ってから返す。"""
    env = get_volume_envelope(track)
    if env is not None:
        return env
    RPR.SetOnlyTrackSelected(track.id)
    RPR.Main_OnCommand(TOGGLE_VOLUME_ENVELOPE, 0)
    env = get_volume_envelope(track)
    if env is None:
        raise RuntimeError(f"could not create volume envelope on {track.name}")
    return env


def _envelope_chunk(env) -> str:
    """GetEnvelopeStateChunk を 1 コールで取得し、末尾までそろっていることを検証する。

    reapy dist API は 1 コール一律 ~33ms かかるため、点ごとに GetEnvelopePoint
    を呼ぶと点数に比例して往復コストが積み上がる(Issue #19)。chunk 1コールへ
    まとめることで点数への依存を消す。

    切り詰め検出は必須。バッファ不足で chunk が途中で切れると PT 行が欠け、
    「点が足りない」と誤判定されて毎回全点の再書き込みが走る(静かな無限
    書き直し)。rstrip 後の末尾が ">" でなければ即座に失敗させる。
    """
    ret = RPR.GetEnvelopeStateChunk(env, "", _CHUNK_BUFSIZE, False)
    chunk = ret[2] if isinstance(ret, (tuple, list)) and len(ret) >= 3 else str(ret)
    stripped = chunk.rstrip()
    if not stripped.endswith(">"):
        raise RuntimeError(
            "envelope chunk looks truncated (buffer size "
            f"{_CHUNK_BUFSIZE} bytes may be insufficient): "
            f"{stripped[-80:]!r}"
        )
    return chunk


def _parse_toplevel_pt_lines(chunk: str) -> list[tuple[float, float]]:
    """chunk から深さ1(トップレベル)の `PT <pos> <val> ...` 行だけを (pos, val) で返す。

    オートメーションアイテムは `<POOLEDENV ...>` のようなネストブロックとして
    現れ、その中の PT 行を拾うと誤動作する。ネスト深さは「`<` で始まる行で
    +1、`>` だけの行で -1」で数えれば十分(現状このプロジェクトはアイテムを
    作らないが、人間が REAPER 上で作った場合に静かに壊れるのを防ぐ)。
    """
    points: list[tuple[float, float]] = []
    depth = 0
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<"):
            depth += 1
            continue
        if stripped == ">":
            depth -= 1
            continue
        if depth == 1 and stripped.startswith("PT "):
            tokens = stripped.split()
            points.append((float(tokens[1]), float(tokens[2])))
    return points


def envelope_points(env) -> list[tuple[float, float]]:
    """(time, gain_linear) の列。chunk 内の PT 行は時間順に格納されている
    (書き込み時に Envelope_SortPoints を呼んでいるため)。

    格納値は envelope の scaling mode 依存なので linear gain へ戻して返す
    (set_envelope_points と対の変換。呼び出し側は linear 前提)。
    """
    mode = int(RPR.GetEnvelopeScalingMode(env))
    chunk = _envelope_chunk(env)
    return [
        (t, _scale_from(mode, v))
        for t, v in _parse_toplevel_pt_lines(chunk)
    ]


def set_envelope_points(env, points: list[tuple[float, float]]) -> None:
    """既存点を全消しして points(linear gain / shape 固定)を書き直す。

    Volume envelope は既定で fader-scaling(mode=1)。生の linear をそのまま書くと
    REAPER が ScaleFromEnvelopeMode で解釈し直し、実効ゲインが無音付近まで沈む。
    ScaleToEnvelopeMode で envelope の scaling domain へ変換してから格納する。
    """
    mode = int(RPR.GetEnvelopeScalingMode(env))
    RPR.DeleteEnvelopePointRange(env, -1e9, 1e9)
    for t, v in points:
        RPR.InsertEnvelopePoint(env, t, _scale_to(mode, v),
                                0, 0.0, False, True)
    RPR.Envelope_SortPoints(env)


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
