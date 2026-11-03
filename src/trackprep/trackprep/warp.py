"""Warp a track to a constant tempo, bar by bar (4/4 assumed), via rubberband."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from trackprep import store
from trackprep.analyze import find_anomalies

SR = 44100
MAX_NEIGHBOURS = 8
PARTIAL_BAR = 0.75


def correct_downbeats(beats, downbeats) -> tuple[np.ndarray, list[int]]:
    """Replace downbeats inside beat anomalies by evenly spaced ones.

    Returns (corrected downbeats in seconds, 1-based numbers of synthesized bars).
    """
    beats = np.asarray(beats, float)
    downbeats = np.asarray(downbeats, float)
    _, runs = find_anomalies(beats, downbeats)
    if not runs or len(downbeats) < 2:
        return downbeats, []
    spans = [(beats[a], beats[min(b + 1, len(beats) - 1)]) for a, b in runs]
    # endpoints count: a spurious downbeat sits exactly on a beat that bounds the bad interval
    inside = np.array([any(t0 <= d <= t1 for t0, t1 in spans) for d in downbeats])
    kept = downbeats[~inside]
    dropped = downbeats[inside]
    if len(kept) < 2:
        return downbeats, []

    # kept-to-kept intervals overlapping a run are not "normal" bars
    suspect = np.array([
        any(t0 < kept[i + 1] and t1 > kept[i] for t0, t1 in spans) for i in range(len(kept) - 1)
    ])
    lens = np.diff(kept)
    normal = np.flatnonzero(~suspect)
    if len(normal) == 0:
        return downbeats, []

    def bar_len(center: float) -> float:
        mids = (kept[normal] + kept[normal + 1]) / 2
        near = normal[np.argsort(np.abs(mids - center))[:MAX_NEIGHBOURS]]
        return float(np.median(lens[near]))

    out: list[tuple[float, bool]] = []
    head = dropped[dropped < kept[0]]
    if len(head):  # anomaly touches the start: extrapolate backwards
        L = bar_len(kept[0])
        n = int(round((kept[0] - head[0]) / L))
        out += [(kept[0] - j * L, True) for j in range(n, 0, -1)]
    for i, d in enumerate(kept):
        out.append((float(d), False))
        if i < len(kept) - 1 and suspect[i]:
            L = bar_len((d + kept[i + 1]) / 2)
            n = max(1, int(round(lens[i] / L)))
            out += [(d + lens[i] * j / n, True) for j in range(1, n)]
    tail = dropped[dropped > kept[-1]]
    if len(tail):  # anomaly touches the end: extrapolate forwards
        L = bar_len(kept[-1])
        n = int(round((tail[-1] - kept[-1]) / L))
        out += [(kept[-1] + j * L, True) for j in range(1, n + 1)]
    times = np.array([t for t, _ in out])
    interp = [i + 1 for i, (_, f) in enumerate(out) if f]
    return times, interp


def trim_partial_bars(times, interp: list[int], ratio: float = PARTIAL_BAR) -> tuple[np.ndarray, list[int]]:
    """Drop the first/last downbeat if its bar is < `ratio` of the median neighbouring bar length."""
    times = np.asarray(times, float)
    interp = list(interp)
    if len(times) >= 4:
        lens = np.diff(times)
        if lens[-1] < ratio * np.median(lens[-1 - MAX_NEIGHBOURS:-1]):
            times, interp = times[:-1], [i for i in interp if i <= len(times) - 1]
    if len(times) >= 4:
        lens = np.diff(times)
        if lens[0] < ratio * np.median(lens[1:1 + MAX_NEIGHBOURS]):
            times, interp = times[1:], [i - 1 for i in interp if i > 1]
    return times, interp


def build_time_map(downbeats_sec, bpm: float, n_samples: int, sr: int = SR):
    """Return (time_map [(src, dst)] in samples, downbeats in samples, per-bar stretch ratios).

    Downbeat k maps to d[0] + k * BAR; before d[0] nothing is stretched, after the
    last downbeat the last bar's ratio continues.
    """
    bar = 4 * 60 / bpm * sr
    d = np.unique(np.round(np.asarray(downbeats_sec) * sr).astype(np.int64))
    d = d[(d >= 0) & (d < n_samples)]
    if len(d) < 2:
        raise ValueError("need at least 2 downbeats")
    out = np.round(d[0] + np.arange(len(d)) * bar).astype(np.int64)
    ratios = bar / np.diff(d)
    end_out = int(round(out[-1] + (n_samples - d[-1]) * ratios[-1]))
    tmap = [(int(i), int(o)) for i, o in zip(d, out)]
    if d[0] > 0:
        tmap.insert(0, (0, 0))
    tmap.append((n_samples, max(end_out, tmap[-1][1] + 1)))
    return tmap, d, ratios


def stretch(x: np.ndarray, tmap: list, sr: int = SR) -> np.ndarray:
    import pyrubberband as prb

    return prb.timemap_stretch(x, sr, tmap, rbargs={"--crisp": "5"})


def _load_stereo(path: str) -> np.ndarray:
    import librosa

    y, _ = librosa.load(path, sr=SR, mono=False)
    y = np.atleast_2d(y)
    if y.shape[0] == 1:
        y = np.repeat(y, 2, axis=0)
    return y[:2].T.astype(np.float64)


def warp_dir(tid: str, bpm: float) -> Path:
    return store.track_dir(tid) / "warp" / f"{bpm:.1f}"


def have_rubberband() -> bool:
    return shutil.which("rubberband") is not None


def run(path: str, data: dict, bpm: float, stems: dict[str, str] | None, force: bool = False) -> dict:
    """Warp the mix (and stems) to `bpm`; return the result dict (also saved as warp.json)."""
    import soundfile as sf

    tid = data["track_id"]
    out_dir = warp_dir(tid, bpm)
    sidecar = out_dir / "warp.json"
    wanted = ["mix.wav"] + ([f"{n}.wav" for n in stems] if stems else [])
    if not force and sidecar.is_file() and all((out_dir / w).is_file() for w in wanted):
        res = json.loads(sidecar.read_text())
        res["stems"] = {n: str(out_dir / f"{n}.wav") for n in (stems or {})}
        return res

    corrected, interp = trim_partial_bars(*correct_downbeats(data["beats"], data["downbeats"]))
    x = _load_stereo(path)
    tmap, d, ratios = build_time_map(corrected, bpm, len(x))
    out_dir.mkdir(parents=True, exist_ok=True)
    sf.write(out_dir / "mix.wav", stretch(x, tmap), SR, subtype="PCM_16")
    paths = {}
    for name, p in (stems or {}).items():
        s, sr = sf.read(p, always_2d=True)
        if sr != SR:
            import librosa

            s = librosa.resample(s.T, orig_sr=sr, target_sr=SR).T
        if len(s) != len(x):  # the same time map must stay valid
            s = s[: len(x)] if len(s) > len(x) else np.pad(s, ((0, len(x) - len(s)), (0, 0)))
        sf.write(out_dir / f"{name}.wav", stretch(s, tmap), SR, subtype="PCM_16")
        paths[name] = str(out_dir / f"{name}.wav")
    res = {
        "track_id": tid,
        "bpm": bpm,
        "bar_sec": 4 * 60 / bpm,
        "first_downbeat_sec": float(d[0]) / SR,
        "max_stretch": round(float(np.max(np.abs(ratios - 1))), 4),
        "interpolated_bars": interp,
        "downbeats_src": [round(float(v) / SR, 4) for v in d],
        "mix": str(out_dir / "mix.wav"),
        "stems": paths,
    }
    sidecar.write_text(json.dumps(res, ensure_ascii=False))
    return res
