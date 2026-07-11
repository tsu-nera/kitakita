"""Load generated MIDI into Reaper tracks. Track list comes from the song.

Each track <name> is filled from output/<name>.mid (existing items on that
track are cleared first).
"""
from __future__ import annotations

import reapy
from reapy import reascript_api as RPR

from kita.midi import OUT_DIR
from kita.model import Song
from kita.reaper.bridge import find_track


def load(song: Song) -> None:
    p = reapy.Project()
    for st in song.tracks:
        path = (OUT_DIR / f"{st.name}.mid").resolve()
        if not path.exists():
            raise FileNotFoundError(f"{path} (run `kita compose` first)")
        track = find_track(p, st.name)
        if track is None:
            raise KeyError(f"track not found in Reaper: {st.name} (run `kita sync` first)")
        for it in list(track.items):
            it.delete()
        RPR.SetOnlyTrackSelected(track.id)
        RPR.SetEditCurPos(0, False, False)
        RPR.InsertMedia(str(path), 0)  # 0 = insert on selected track at cursor
        print(f"loaded {path.name} -> {st.name}")
