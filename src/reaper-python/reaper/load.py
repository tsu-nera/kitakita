"""Load generated MIDI files into Reaper tracks by name."""
from __future__ import annotations

import argparse
from pathlib import Path

import reapy
from reapy import reascript_api as RPR

DEFAULT_MAPPING = {
    "kick": "output/kick.mid",
    "hat":  "output/hat.mid",
    "bass": "output/bass.mid",
}

ROOT = Path(__file__).resolve().parents[1]


def _find_track(p, name: str):
    for t in p.tracks:
        if t.name == name:
            return t
    raise KeyError(f"track not found: {name}")


def load(mapping: dict[str, str]) -> None:
    p = reapy.Project()
    for name, rel in mapping.items():
        path = (ROOT / rel).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        track = _find_track(p, name)
        for it in list(track.items):
            it.delete()
        RPR.SetOnlyTrackSelected(track.id)
        RPR.SetEditCurPos(0, False, False)
        RPR.InsertMedia(str(path), 0)  # 0 = insert on selected track at cursor
        print(f"loaded {path.name} -> {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", nargs="*", default=None,
                        help="Pairs like kick=output/kick.mid (overrides default)")
    args = parser.parse_args()

    if args.mapping:
        mapping = dict(s.split("=", 1) for s in args.mapping)
    else:
        mapping = DEFAULT_MAPPING
    load(mapping)


if __name__ == "__main__":
    main()
