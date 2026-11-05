"""Per-bar kick detection from the drums stem (reuses synthetic helpers and fixtures of test_trackprep)."""
import json

import numpy as np
import soundfile as sf
from test_trackprep import (  # noqa: F401  (fixtures are used by name)
    _run,
    beat_times,
    cache,
    fake_beats,
    render,
    wav,
)

from trackprep import drums as drums_mod
from trackprep import stems as stems_mod
from trackprep import store
from trackprep.analyze import SR


def test_bar_kicks_removed_kicks_and_single_hit():
    beats, downbeats = beat_times([(140, 12)])
    idx = np.arange(len(beats))
    bar = idx // 4
    kick = ~np.isin(bar, [3, 4])  # bars 4-5 (1-based) without kicks
    kick &= ~((bar == 7) & (idx % 4 != 2))  # bar 8: a single hit on beat 3
    rows = drums_mod.bar_kicks(render(beats, kick), SR, beats, downbeats)
    assert len(rows) == 12
    for k, r in enumerate(rows):
        if k in (3, 4):
            assert r == {"drum_kicks": 0, "four_on_floor": False}
        elif k == 7:
            assert r == {"drum_kicks": 1, "four_on_floor": False}
        else:
            assert r == {"drum_kicks": 4, "four_on_floor": True}


def test_bar_kicks_incomplete_bars_are_not_four_on_floor():
    beats, _ = beat_times([(140, 6)])
    beats = beats[:20]
    downbeats = np.concatenate([[beats[0]], beats[2::4]])  # first and last bars have 2 beats
    rows = drums_mod.bar_kicks(render(beats, np.ones(len(beats), bool)), SR, beats, downbeats)
    assert [r["drum_kicks"] for r in rows] == [2, 4, 4, 4, 4, 2]
    assert [r["four_on_floor"] for r in rows] == [False, True, True, True, True, False]


def _put_drums(p, y):
    d = stems_mod.stems_dir(store.track_id(p))
    d.mkdir(parents=True, exist_ok=True)
    for n in stems_mod.STEM_NAMES:
        sf.write(d / f"{n}.wav", y if n == "drums" else np.zeros_like(y), SR, subtype="PCM_16")


def test_cmd_stems_adds_drum_kicks_to_analysis(fake_beats, wav, capsys):
    p, _ = fake_beats
    _, beats, _ = wav
    _run(["analyze", str(p)], capsys)
    kick = (np.arange(len(beats)) // 4) != 5
    _put_drums(p, render(beats, kick))
    code, out, _ = _run(["stems", str(p)], capsys)
    assert code == 0 and json.loads(out)["track_id"] == store.track_id(p)
    bars = store.load(store.track_id(p))["bars"]
    assert len(bars) == 16 and all("drum_kicks" in b and "four_on_floor" in b for b in bars)
    assert [b["four_on_floor"] for b in bars] == [k != 5 for k in range(16)]
    _, out, _ = _run(["show", str(p)], capsys)
    assert "dkick" in out and "4otf" in out


def test_analyze_adds_drum_kicks_when_stems_cached(fake_beats, wav, capsys):
    p, _ = fake_beats
    _, beats, _ = wav
    _put_drums(p, render(beats, np.ones(len(beats), bool)))
    _run(["analyze", str(p)], capsys)
    assert all(b["four_on_floor"] for b in store.load(store.track_id(p))["bars"])
    _run(["analyze", str(p), "--force"], capsys)
    assert all("drum_kicks" in b for b in store.load(store.track_id(p))["bars"])


def test_cmd_stems_without_analysis_hints_and_succeeds(wav, capsys):
    p, beats, _ = wav
    _put_drums(p, render(beats, np.ones(len(beats), bool)))
    code, out, err = _run(["stems", str(p)], capsys)
    assert code == 0 and json.loads(out)["track_id"] == store.track_id(p)
    assert f"no analysis for {p}; run first: trackprep analyze {p}" in err
    assert store.load(store.track_id(p)) is None
