"""Track analysis: tempo segments, per-bar features, phrase grid, sections, ending, key."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import librosa
import numpy as np

from trackprep import store
from trackprep.beats import estimate_beats

SR = 22050
N_FFT = 2048
HOP = 256
WINDOW_BEATS = 32
SPLIT_BPM = 1.0

_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _package_version() -> str:
    try:
        return version("trackprep")
    except PackageNotFoundError:
        return "0"


def _bar_of(downbeats: np.ndarray, t: float) -> int:
    return max(int(np.searchsorted(downbeats, t, side="right")), 1)


def _bpm(beats: np.ndarray, s: int, e: int) -> float:
    slope = np.polyfit(np.arange(s, e), beats[s:e], 1)[0]
    return 60.0 / slope


def find_anomalies(beats: np.ndarray, downbeats: np.ndarray) -> tuple[list[dict], list[tuple[int, int]]]:
    """Return anomaly entries and the (first, last) inter-beat interval index of each run."""
    ibi = np.diff(beats)
    med = np.median(ibi)
    bad = np.flatnonzero((ibi < 0.5 * med) | (ibi > 1.5 * med))
    runs: list[tuple[int, int]] = []
    for i in bad:
        if runs and i == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], int(i))
        else:
            runs.append((int(i), int(i)))
    entries = [
        {"bar": _bar_of(downbeats, beats[a]), "time": float(beats[a]), "kind": "beat_irregular"}
        for a, _ in runs
    ]
    return entries, runs


def tempo_segments(beats: np.ndarray, downbeats: np.ndarray, runs: list[tuple[int, int]]) -> list[dict]:
    # pieces of beat indices between anomaly runs
    pieces, start = [], 0
    for a, b in runs:
        pieces.append((start, a + 1))
        start = b + 1
    pieces.append((start, len(beats)))

    segments = []
    for ps, pe in pieces:
        if pe - ps < 4:
            continue
        starts = list(range(ps, pe - WINDOW_BEATS + 1, WINDOW_BEATS)) or [ps]
        ends = [s + WINDOW_BEATS for s in starts]
        ends[-1] = pe  # last partial window merges into the previous one
        wins = [(s, e, _bpm(beats, s, e)) for s, e in zip(starts, ends)]
        group = [wins[0]]
        groups = []
        for w in wins[1:]:
            if abs(w[2] - group[-1][2]) > SPLIT_BPM:
                groups.append(group)
                group = []
            group.append(w)
        groups.append(group)
        for g in groups:
            segments.append({
                "from_bar": _bar_of(downbeats, beats[g[0][0]]),
                "to_bar": _bar_of(downbeats, beats[g[-1][1] - 1]),
                "bpm_start": round(g[0][2], 2),
                "bpm_end": round(g[-1][2], 2),
            })
    return segments


def bar_features(y: np.ndarray, sr: int, beats: np.ndarray, downbeats: np.ndarray) -> list[dict]:
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    times = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=HOP)
    low = S[(freqs >= 40) & (freqs < 100)].sum(axis=0)
    high = S[freqs >= 6000].sum(axis=0)
    rms = librosa.feature.rms(S=S)[0]

    def at(t):
        return min(int(np.searchsorted(times, t)), len(times) - 1)

    def kick_ratio(t0, t1):
        on = low[at(t0 - 0.015):at(t0 + 0.05) + 1].max()
        m = (t0 + t1) / 2
        off = low[at(m - 0.03):at(m + 0.03) + 1].mean()
        return on / (off + 1e-9)

    ibi_mean = float(np.diff(beats).mean())
    kicks = np.array([kick_ratio(beats[i], beats[i + 1]) for i in range(len(beats) - 1)])
    bounds = list(downbeats) + [beats[-1] + ibi_mean]
    rows, counts = [], []
    for k in range(len(downbeats)):
        t0, t1 = bounds[k], bounds[k + 1]
        sl = slice(at(t0), max(at(t1), at(t0) + 1))
        kb = kicks[(beats[:-1] >= t0 - 0.01) & (beats[:-1] < t1 - 0.01)]
        counts.append(int(((beats >= t0 - 0.01) & (beats < t1 - 0.01)).sum()))
        rows.append([rms[sl].mean(), low[sl].mean(), high[sl].mean(), np.median(kb) if len(kb) else 0.0])
    a = np.array(rows)
    # reference = p95 over complete bars (modal beat count); partial bars must not define it
    counts = np.array(counts)
    full = counts == np.bincount(counts).argmax()
    for c in range(3):
        a[:, c] = np.clip(a[:, c] / max(np.percentile(a[full, c], 95), 1e-12), 0, 1)
    return [
        {"bar": k + 1, "time": float(downbeats[k]), "rms": r[0], "low": r[1], "high": r[2], "kick": r[3]}
        for k, r in enumerate(a.tolist())
    ]


def phrase_offset(low: np.ndarray) -> int:
    """Offset (1..8) whose 8-bar grid best aligns with large changes of low-band energy."""
    scores = []
    for o in range(1, 9):
        scores.append(sum(abs(low[b - 1] - low[b - 2]) for b in range(o, len(low) + 1, 8) if b > 1))
    return int(np.argmax(scores)) + 1


def estimate_sections(bars: list[dict], offset: int) -> list[dict]:
    n = len(bars)
    starts = list(range(offset, n + 1, 8))
    if not starts:
        starts = [1]
    starts[0] = 1  # bars before the first phrase start join the first phrase
    phrases = []
    for i, s in enumerate(starts):
        e = (starts[i + 1] - 1) if i + 1 < len(starts) else n
        sel = bars[s - 1:e]
        phrases.append((s, e, np.median([b["low"] for b in sel]), np.median([b["rms"] for b in sel])))

    seen_kick = False
    out: list[dict] = []
    for s, e, low, rms in phrases:
        if low < 0.15:
            label = "breakdown" if seen_kick else "intro"
        else:
            seen_kick = True
            if low < 0.4:
                label = "break"
            else:
                label = "drop" if rms >= 0.8 else "groove"
        if out and out[-1]["label"] == label:
            out[-1]["to_bar"] = e
        else:
            out.append({"label": label, "from_bar": s, "to_bar": e})
    return out


def estimate_ending(y: np.ndarray, sr: int) -> dict:
    win = int(0.5 * sr)
    n = len(y) // win
    if n < 2:
        return {"kind": "abrupt", "decay_sec": 0.0}
    r = np.sqrt((y[:n * win].reshape(n, win) ** 2).mean(axis=1))
    db = 20 * np.log10(r + 1e-10)
    ref = np.percentile(db, 90)
    last = int(np.flatnonzero(db >= ref - 6)[-1])
    end = (last + 1) * 0.5
    below = np.flatnonzero(db[last + 1:] < ref - 40)
    stop = (last + 1 + int(below[0])) * 0.5 if len(below) else len(y) / sr
    decay = max(stop - end, 0.0)
    return {"kind": "abrupt" if decay < 5 else "fade", "decay_sec": float(decay)}


def estimate_key(y: np.ndarray, sr: int) -> dict:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best, name = -2.0, ""
    for mode, prof in (("major", _KS_MAJOR), ("minor", _KS_MINOR)):
        for k in range(12):
            c = np.corrcoef(chroma, np.roll(prof, k))[0, 1]
            if c > best:
                best, name = c, f"{_NOTES[k]} {mode}"
    return {"estimate": name, "confidence": "low"}


def _round(o):
    if isinstance(o, float):
        return round(o, 3)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v) for v in o]
    return o


def analyze_signal(y: np.ndarray, sr: int, beats, downbeats) -> dict:
    beats = np.asarray(beats, dtype=float)
    downbeats = np.asarray(downbeats, dtype=float)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        sr = SR
    anomalies, runs = find_anomalies(beats, downbeats)
    bars = bar_features(y, sr, beats, downbeats)
    offset = phrase_offset(np.array([b["low"] for b in bars]))
    return _round({
        "beats": [float(t) for t in beats],
        "downbeats": [float(t) for t in downbeats],
        "tempo_segments": tempo_segments(beats, downbeats, runs),
        "anomalies": anomalies,
        "bars": bars,
        "phrase_offset_bar": offset,
        "sections": estimate_sections(bars, offset),
        "ending": estimate_ending(y, sr),
        "key": estimate_key(y, sr),
    })


def analyze_file(path: str | Path) -> dict:
    path = Path(path)
    y, _ = librosa.load(path, sr=SR, mono=True)
    beats, downbeats = estimate_beats(str(path))
    title, source = store.read_metadata(path)
    result = analyze_signal(y, SR, beats, downbeats)
    return {
        "schema": 1,
        "track_id": store.track_id(path),
        "path": str(path.resolve()),
        "title": title,
        "duration": round(len(y) / SR, 3),
        "source": source,
        "analyzer": {"beats": "beat_this final0", "version": _package_version()},
        **result,
    }
