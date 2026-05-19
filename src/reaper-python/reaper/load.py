"""Load generated MIDI into Reaper tracks. Track list comes from the spec.

Each spec track <name> is filled from output/<name>.mid (existing items on
that track are cleared first).

    uv run python reaper/load.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import reapy
from reapy import reascript_api as RPR

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spec import Arrangement, load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output"


def _find_track(p, name: str):
    for t in p.tracks:
        if t.name == name:
            return t
    raise KeyError(f"track not found in Reaper: {name} (run setup.py first)")


def load(spec: Arrangement) -> None:
    p = reapy.Project()
    for spec_t in spec.tracks:
        path = (OUT_DIR / f"{spec_t.name}.mid").resolve()
        if not path.exists():
            raise FileNotFoundError(f"{path} (run compose.py first)")
        track = _find_track(p, spec_t.name)
        for it in list(track.items):
            it.delete()
        RPR.SetOnlyTrackSelected(track.id)
        RPR.SetEditCurPos(0, False, False)
        RPR.InsertMedia(str(path), 0)  # 0 = insert on selected track at cursor
        print(f"loaded {path.name} -> {spec_t.name}")


def main() -> None:
    load(load_spec())


if __name__ == "__main__":
    main()
