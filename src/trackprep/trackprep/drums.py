"""Per-bar kick detection from the Demucs drums stem (four-on-the-floor judgement)."""
from __future__ import annotations

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

KICK_BAND = (40, 120)  # Hz
WIN = (-0.015, 0.050)  # s around each beat
REF_PERCENTILE = 90  # reference level = this percentile of per-beat peaks over the whole track
KICK_DROP_DB = 15.0  # a beat has a kick if within this many dB of the reference
_EPS = 1e-9
_TOL = 0.01  # beat-membership tolerance, same as analyze.bar_features


def bar_kicks(y: np.ndarray, sr: int, beats: np.ndarray, downbeats: np.ndarray) -> list[dict]:
    """One {"drum_kicks", "four_on_floor"} per downbeat, aligned with analyze.bar_features bars."""
    beats, downbeats = np.asarray(beats, float), np.asarray(downbeats, float)
    y = np.asarray(y, float)
    if y.ndim == 2:
        y = y.mean(axis=1)
    sos = butter(4, KICK_BAND, btype="bandpass", fs=sr, output="sos")
    env = np.abs(sosfilt(sos, y))
    peaks = np.empty(len(beats))
    for i, b in enumerate(beats):
        s = max(int(round((b + WIN[0]) * sr)), 0)
        e = min(int(round((b + WIN[1]) * sr)) + 1, len(env))
        peaks[i] = env[s:e].max() if e > s else 0.0
    db = 20 * np.log10(peaks + _EPS)
    has_kick = db >= np.percentile(db, REF_PERCENTILE) - KICK_DROP_DB

    bounds = list(downbeats) + [beats[-1] + float(np.diff(beats).mean())]
    rows = []
    for k in range(len(downbeats)):
        inbar = (beats >= bounds[k] - _TOL) & (beats < bounds[k + 1] - _TOL)
        kicks = int(has_kick[inbar].sum())
        rows.append({"drum_kicks": kicks, "four_on_floor": bool(inbar.sum() == 4 and kicks == 4)})
    return rows


def add_drum_kicks(data: dict, drums_wav: str) -> None:
    """Write drum_kicks / four_on_floor into each data["bars"] entry in place."""
    y, sr = sf.read(drums_wav, dtype="float32")
    rows = bar_kicks(y, sr, np.array(data["beats"]), np.array(data["downbeats"]))
    for bar, row in zip(data["bars"], rows, strict=True):
        bar.update(row)
