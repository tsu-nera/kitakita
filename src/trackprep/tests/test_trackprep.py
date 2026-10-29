"""Synthetic-audio tests. Beats are given as ground truth; beat_this is never run."""
import shutil

import numpy as np
import pytest
import soundfile as sf

from trackprep import cli, store
from trackprep.analyze import SR, analyze_signal

rng = np.random.default_rng(0)


def beat_times(segments):
    """segments: [(bpm, n_bars)] -> beat times (4/4), downbeat times."""
    t, beats = 0.5, []
    for bpm, bars in segments:
        for _ in range(bars * 4):
            beats.append(t)
            t += 60 / bpm
    beats = np.array(beats)
    return beats, beats[::4]


def render(beats, kick_beats, tail=1.0, sr=SR):
    """4-on-the-floor: 55 Hz decaying sine on kick beats, quiet hi-hat noise on offbeats."""
    n = int((beats[-1] + 60 / 140 + tail) * sr)
    y = np.zeros(n)
    k = np.arange(int(0.25 * sr)) / sr
    kick = 0.8 * np.sin(2 * np.pi * 55 * k) * np.exp(-k * 18)
    hat = 0.03 * rng.standard_normal(int(0.03 * sr)) * np.exp(-np.arange(int(0.03 * sr)) / (0.008 * sr))
    for i, b in enumerate(beats):
        s = int(b * sr)
        if kick_beats[i]:
            y[s:s + len(kick)] += kick
        h = int((b + 0.21) * sr)
        y[h:h + len(hat)] += hat[: n - h]
    return y


def test_breakdown_and_constant_tempo():
    beats, downbeats = beat_times([(140, 40)])
    bar = np.arange(len(beats)) // 4
    kick = ~((bar >= 16) & (bar < 24))
    res = analyze_signal(render(beats, kick), SR, beats, downbeats)
    for seg in res["tempo_segments"]:
        assert abs(seg["bpm_start"] - 140) < 0.5 and abs(seg["bpm_end"] - 140) < 0.5
    bd = [s for s in res["sections"] if s["label"] == "breakdown"]
    assert len(bd) == 1
    assert abs(bd[0]["from_bar"] - 17) <= 1 and abs(bd[0]["to_bar"] - 24) <= 1
    assert res["phrase_offset_bar"] == 1


def test_tempo_step_splits():
    beats, downbeats = beat_times([(138, 32), (142, 32)])
    res = analyze_signal(render(beats, np.ones(len(beats), bool)), SR, beats, downbeats)
    segs = res["tempo_segments"]
    assert len(segs) >= 2
    assert abs(segs[0]["bpm_start"] - 138) < 0.5
    assert abs(segs[-1]["bpm_end"] - 142) < 0.5


def test_gradual_drift_is_one_segment():
    # 138 -> 140.4 BPM over 8 windows (0.3 BPM per window)
    t, beats = 0.5, []
    for i in range(256):
        beats.append(t)
        t += 60 / (138 + 2.4 * i / 255)
    beats = np.array(beats)
    res = analyze_signal(render(beats, np.ones(len(beats), bool)), SR, beats, beats[::4])
    assert len(res["tempo_segments"]) == 1


def test_beat_irregular_splits_segments():
    beats, downbeats = beat_times([(140, 32)])
    beats = beats.copy()
    beats[60] = beats[59] + 0.08  # squeeze one interval
    res = analyze_signal(render(beats, np.ones(len(beats), bool)), SR, beats, downbeats)
    assert [a["kind"] for a in res["anomalies"]] == ["beat_irregular"]
    assert len(res["tempo_segments"]) == 2


def test_abrupt_ending():
    beats, downbeats = beat_times([(140, 16)])
    y = render(beats, np.ones(len(beats), bool), tail=0.0)
    y[int(len(y) - 1.0 * SR):] = 0.0
    y = np.concatenate([y, np.zeros(SR * 3)])
    res = analyze_signal(y, SR, beats, downbeats)
    assert res["ending"]["kind"] == "abrupt"


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


@pytest.fixture
def wav(cache):
    beats, downbeats = beat_times([(140, 16)])
    y = render(beats, np.ones(len(beats), bool))
    p = cache / "a.wav"
    sf.write(p, y, SR)
    return p, beats, downbeats


def test_analyze_skips_cached_and_force_reruns(wav, monkeypatch, capsys):
    p, beats, downbeats = wav
    calls = []

    def fake(path):
        calls.append(path)
        return beats, downbeats

    monkeypatch.setattr("trackprep.analyze.estimate_beats", fake)
    with pytest.raises(SystemExit) as e:
        cli.main(["analyze", str(p)])
    assert e.value.code == 0
    with pytest.raises(SystemExit):
        cli.main(["analyze", str(p)])
    assert len(calls) == 1
    with pytest.raises(SystemExit):
        cli.main(["analyze", str(p), "--force"])
    assert len(calls) == 2
    data = store.load(store.track_id(p))
    assert data["schema"] == 1 and data["title"] == "a" and data["source"] == {}
    with pytest.raises(SystemExit) as e:
        cli.main(["show", str(p)])
    assert e.value.code == 0
    assert "sections" in capsys.readouterr().out


def test_show_unanalyzed_fails(wav, capsys):
    p, _, _ = wav
    with pytest.raises(SystemExit) as e:
        cli.main(["show", str(p)])
    assert e.value.code != 0
    assert "trackprep analyze" in capsys.readouterr().err


def test_track_id_ignores_filename(wav):
    p, _, _ = wav
    q = p.parent / "renamed.wav"
    shutil.copy(p, q)
    assert store.track_id(p) == store.track_id(q)
    assert len(store.track_id(p)) == 16


def test_suno_metadata(cache):
    from mutagen.id3 import COMM, TIT2
    from mutagen.wave import WAVE

    p = cache / "s.wav"
    sf.write(p, np.zeros(SR), SR)
    w = WAVE(p)
    w.add_tags()
    w.tags.add(TIT2(encoding=3, text="Song"))
    w.tags.add(COMM(encoding=3, lang="eng", desc="", text="made with suno; created=x; id=b43d77b6-6fcf-4b4c-9245-abd4440b27eb"))
    w.save()
    assert store.read_metadata(p) == ("Song", {"suno_id": "b43d77b6-6fcf-4b4c-9245-abd4440b27eb"})
