"""Beat / downbeat estimation with beat_this (CPU)."""
from __future__ import annotations

import numpy as np


def estimate_beats(path: str) -> tuple[np.ndarray, np.ndarray]:
    # torch import is slow; keep it out of module import
    from beat_this.inference import File2Beats

    beats, downbeats = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)(path)
    return np.asarray(beats, dtype=float), np.asarray(downbeats, dtype=float)
