"""Transition FX for re_edit/render.py: placement, synthesized riser/downlifter, delay throw, loudness-matched A/B.

All functions work on (n, 2) float arrays so they are testable without a plan file.
"""
from pathlib import Path

import numpy as np
import pedalboard as pb
import pyloudnorm as pyln
import soundfile as sf
import soxr

BLOCK = 512  # samples per static-cutoff block of the swept filter
SYNTH_PEAK_DB = -6  # synth FX are normalized here before gain_db, so gain_db is predictable
CEILING_DB = -1.0  # peak ceiling of the rendered A/B pair
DEFAULT_SWEEP = {"riser": (300.0, 12000.0), "downlifter": (12000.0, 300.0)}


def position(bar: float, beat: float, bar_samples: float) -> int:
    """1-based edit bar and beat (4/4) -> sample index."""
    return int(round((bar - 1 + (beat - 1) / 4) * bar_samples))


def place(dst: np.ndarray, x: np.ndarray, pos: int, align: str = "start") -> None:
    """Add x into dst; align 'start' puts x[0] at pos, 'end' puts x[-1] at pos - 1 (the material ends on pos)."""
    assert align in ("start", "end"), f"align must be start|end, got {align}"
    s = pos if align == "start" else pos - len(x)
    a, b = max(s, 0), min(s + len(x), len(dst))
    if (a, b) != (s, s + len(x)):
        print(f"  warning: FX clipped by the edit boundary ({s} .. {s + len(x)} of {len(dst)})")
    if b > a:
        dst[a:b] += x[a - s:b - s]


def load_oneshot(path: str | Path, sr: int, reverse: bool = False) -> np.ndarray:
    x, fs = sf.read(Path(path).expanduser(), always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if fs != sr:
        x = soxr.resample(x, fs, sr)
    return x[::-1].copy() if reverse else x


def synth(kind: str, n: int, sr: int, f0: float | None = None, f1: float | None = None, seed: int = 0) -> np.ndarray:
    """Stereo noise sweep. L and R use independent noise (mono would lose the width). Deterministic for a given seed."""
    d0, d1 = DEFAULT_SWEEP[kind]
    f0, f1 = f0 or d0, f1 or d1
    noise = np.stack([np.random.default_rng(seed).standard_normal(n), np.random.default_rng(seed + 1).standard_normal(n)])
    lpf = pb.LadderFilter(mode=pb.LadderFilter.Mode.LPF24, cutoff_hz=f0, resonance=0.2)
    y = np.empty_like(noise, dtype=np.float32)
    for i in range(0, n, BLOCK):
        t = (i + min(BLOCK, n - i) / 2) / n
        lpf.cutoff_hz = f0 * (f1 / f0) ** t  # log-frequency sweep
        y[:, i:i + BLOCK] = lpf(noise[:, i:i + BLOCK].astype(np.float32), sr, reset=False)
    db = np.linspace(-40, 0, n) if kind == "riser" else np.linspace(0, -60, n)
    y = y.T.astype(np.float64) * (10 ** (db / 20))[:, None]
    f = min(int(0.005 * sr), n // 2)
    y[:f] *= np.linspace(0, 1, f)[:, None]
    y[n - f:] *= np.linspace(1, 0, f)[:, None]
    return y * (10 ** (SYNTH_PEAK_DB / 20) / np.abs(y).max())


def throw_wet(x: np.ndarray, sr: int, delay_sec: float, feedback: float, tail_sec: float,
              reverb: dict | None = None) -> np.ndarray:
    """Wet-only delay (+ optional reverb) of x, zero-padded by tail_sec. The dry note is not in the output."""
    x = np.concatenate([x, np.zeros((int(tail_sec * sr), x.shape[1]))])
    board = pb.Pedalboard([pb.Delay(delay_seconds=delay_sec, feedback=feedback, mix=1.0)]
                          + ([pb.Reverb(dry_level=0.0, **reverb)] if reverb else []))
    return board(x.T.astype(np.float32), sr).T.astype(np.float64)


def lufs(x: np.ndarray, sr: int) -> float:
    return pyln.Meter(sr).integrated_loudness(x)


def peak_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.abs(x).max())


def match_and_limit(base: np.ndarray, wet: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Match wet's integrated loudness to base, then lower both by one common gain so both peaks stay <= CEILING_DB."""
    wet = wet * 10 ** ((lufs(base, sr) - lufs(wet, sr)) / 20)
    g = min(1.0, 10 ** (CEILING_DB / 20) / max(np.abs(base).max(), np.abs(wet).max()))
    return base * g, wet * g
