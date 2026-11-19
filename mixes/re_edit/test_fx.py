"""Tests for fx.py with synthetic signals only.

run: uv run --project src/trackprep --with pytest pytest mixes/re_edit -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
import fx  # noqa: E402

SR = 48000
BAR = 4 * 60 / 142 * SR  # samples per bar at 142 BPM


def click(n: int) -> np.ndarray:
    x = np.zeros((n, 2))
    x[0] = 1.0
    x[-1] = 0.5
    return x


def test_position():
    assert fx.position(3, 2, BAR) == round((2 + 0.25) * BAR)
    assert fx.position(1, 1, BAR) == 0


def test_place_start_and_end():
    pos = fx.position(3, 2, BAR)
    dst = np.zeros((int(6 * BAR), 2))
    fx.place(dst, click(1000), pos, "start")
    assert dst[pos, 0] == 1.0 and dst[pos + 999, 0] == 0.5
    assert np.flatnonzero(dst[:, 0]).tolist() == [pos, pos + 999]

    dst = np.zeros((int(6 * BAR), 2))
    fx.place(dst, click(1000), pos, "end")
    assert dst[pos - 1, 0] == 0.5 and dst[pos - 1000, 0] == 1.0  # the last sample lands just before pos


def test_place_clips_at_edges():
    dst = np.zeros((100, 2))
    fx.place(dst, np.ones((50, 2)), 80, "start")
    assert dst[80:].sum() == 40
    fx.place(dst, np.ones((50, 2)), 20, "end")
    assert dst[:20].sum() == 40  # clipped at the edit start


@pytest.mark.parametrize("fs", [SR, 44100])
def test_load_oneshot_reverse_and_resample(tmp_path, fs):
    x = np.zeros(2000)
    x[0] = 1.0  # mono click
    sf.write(tmp_path / "c.wav", x, fs, subtype="FLOAT")
    y = fx.load_oneshot(tmp_path / "c.wav", SR)
    assert y.shape[1] == 2 and abs(len(y) - 2000 * SR / fs) <= 1 and y.argmax(axis=0)[0] <= 2
    r = fx.load_oneshot(tmp_path / "c.wav", SR, reverse=True)
    assert abs(int(r[:, 0].argmax()) - (len(r) - 1)) <= 2


@pytest.mark.parametrize("kind", ["riser", "downlifter"])
def test_synth(kind):
    n = SR * 2
    a = fx.synth(kind, n, SR, seed=0)
    assert np.array_equal(a, fx.synth(kind, n, SR, seed=0))
    assert not np.array_equal(a, fx.synth(kind, n, SR, seed=5))
    assert np.corrcoef(a[:, 0], a[:, 1])[0, 1] < 0.9
    assert abs(fx.peak_db(a) - fx.SYNTH_PEAK_DB) < 0.01
    head, tail = np.sum(a[: n // 10] ** 2), np.sum(a[-n // 10:] ** 2)
    assert (tail > head) if kind == "riser" else (head > tail)


def test_throw_has_no_dry():
    delay = 0.75 * 60 / 142
    x = np.zeros((SR // 4, 2))
    x[:] = np.random.default_rng(0).standard_normal((len(x), 2)) * 0.3
    wet = fx.throw_wet(x, SR, delay, 0.45, tail_sec=2.0)
    assert len(wet) == len(x) + 2 * SR
    d = int(delay * SR)
    assert np.abs(wet[:d - 2]).max() == 0  # nothing passes through before the first echo
    assert np.abs(wet[d:d + len(x)]).max() > 0.05
    assert np.abs(wet[d + len(x) + 100:]).max() > 0.001  # feedback repeats


def test_match_and_limit():
    rng = np.random.default_rng(1)
    base = rng.standard_normal((SR * 5, 2)) * 0.1
    wet = base.copy()
    wet[SR:SR + 200] += 3.0  # a hot transient plus a louder body
    wet *= 1.5
    b, w = fx.match_and_limit(base, wet, SR)
    assert abs(fx.lufs(b, SR) - fx.lufs(w, SR)) <= 0.2
    assert fx.peak_db(b) <= -1.0 + 1e-6 and fx.peak_db(w) <= -1.0 + 1e-6
