"""Demucs stem separation with a per-track cache."""
from __future__ import annotations

from pathlib import Path

import soundfile as sf

from trackprep import store

MODEL = "htdemucs"
STEM_NAMES = ("drums", "bass", "other", "vocals")


def stems_dir(tid: str) -> Path:
    return store.track_dir(tid) / "stems"


def cached_stems(tid: str) -> dict[str, str] | None:
    d = stems_dir(tid)
    paths = {n: d / f"{n}.wav" for n in STEM_NAMES}
    return {n: str(p) for n, p in paths.items()} if all(p.is_file() for p in paths.values()) else None


def separate(path: str) -> dict[str, tuple]:
    """Run htdemucs on CPU. Returns {name: (samples [channels, n], sr)}."""
    import librosa
    import numpy as np
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model(MODEL)
    model.eval()
    y, _ = librosa.load(path, sr=model.samplerate, mono=False)
    wav = torch.from_numpy(np.atleast_2d(y)).float()
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / ref.std()
    with torch.no_grad():
        out = apply_model(model, wav[None], device="cpu", progress=False)[0]
    out = out * ref.std() + ref.mean()
    return {name: (out[i].numpy(), model.samplerate) for i, name in enumerate(model.sources)}


def ensure_stems(path: str, tid: str, force: bool = False) -> dict[str, str]:
    """Return stem paths, separating (and writing PCM_16 WAVs) unless cached."""
    if not force:
        hit = cached_stems(tid)
        if hit:
            return hit
    d = stems_dir(tid)
    d.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (data, sr) in separate(path).items():
        p = d / f"{name}.wav"
        sf.write(p, data.T, sr, subtype="PCM_16")
        paths[name] = str(p)
    return paths
