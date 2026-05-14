"""Set up Reaper tracks with ReaSamplomatic5000 + sample files."""
from __future__ import annotations

from pathlib import Path

import reapy
from reapy import reascript_api as RPR

SAMPLE_ROOT = Path(r"C:\Users\fox10\Music\Samples\Black Octopus\Trance Vision")

TRACKS = [
    {
        "name": "kick",
        "sample": SAMPLE_ROOT / "Drum - Kick - One Shots" / "DPT_Kick_One_Shot_Acidtech.wav",
        "midi_note": 60,  # C4 — Sampler triggers on C4 by default
    },
    {
        "name": "hat",
        "sample": SAMPLE_ROOT / "Drum - Hat Closed - One Shot" / "DPT_Hat_Closed_One_Shot_Accent.wav",
        "midi_note": 60,
    },
    {
        "name": "bass",
        "sample": SAMPLE_ROOT / "Bass - One Shot" / "DPT_A_Bass_One_Shot_Lowsub.wav",
        "midi_note": 60,
    },
]


def load_sampler(track, sample_path: Path):
    fx_idx = RPR.TrackFX_AddByName(track.id, "ReaSamplomatic5000", False, -1)
    if fx_idx < 0:
        raise RuntimeError("Could not add ReaSamplomatic5000")
    RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "FILE0", str(sample_path))
    RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "DONE", "")
    return fx_idx


def setup():
    p = reapy.Project()
    for spec in TRACKS:
        if not spec["sample"].exists():
            raise FileNotFoundError(spec["sample"])
        t = p.add_track(name=spec["name"])
        load_sampler(t, spec["sample"])
        print(f"+ track {spec['name']}: {spec['sample'].name}")
    print(f"done. tracks: {p.n_tracks}")


if __name__ == "__main__":
    setup()
