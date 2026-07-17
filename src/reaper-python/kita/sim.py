"""Measure the mix without listening — offline synthesis + metrics.

なぜ "聴かずに測る" か: モデルは音を聴けないし、コワーキング/BTヘッドホン環境では
低域やバランスを耳で切り分けにくい。各トラックは one-shot サンプラなので、
sample + Event 列 + gain_db からミックスを Python で再構成すれば、REAPER
レンダリング無しでラウドネス・ピーク・帯域の食い合い・セクション別エネルギーを
数値化できる(reapy 接続も不要)。

Event 列は midi.py と同じ Clip.events() 由来 — パターン解釈の二重管理はしない。

注意: RS5k のエンベロープ/フィルタ等は再現しない(素のサンプル再生を仮定)。
トラック"間"の相対バランスと展開の形を見るのが目的で、絶対値は実機と一致しない。
"""
from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from kita.midi import track_events
from kita.model import Event, Sampler, Song, Synth, Track

SR = 44100
BALANCE_BARS = 4  # バランス計測はデフォルト clip の4小節ループで行う(セクション構成に非依存)
# suggest の目標: kick を基準に各トラックのピークを何 dB 下に置くか。
# トランス・ドラムの定番的な並び(kick最前 → bass → clap → hat が後ろ)。
TARGET_PEAK_UNDER_KICK = {"bass": -2.5, "clap": -4.0, "ohat": -6.0}


def load_mono(path: Path) -> np.ndarray:
    """wav を mono float(-1..1) で読み、SR へ素朴にリサンプルする。"""
    w = wave.open(str(path), "rb")
    sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
    raw = w.readframes(n)
    w.close()
    if sw == 2:
        a = np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        a = np.where(v & 0x800000, v - 0x1000000, v).astype(np.float64) / 8388608.0
    elif sw == 4:
        a = np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width: {sw} bytes ({path.name})")
    if ch == 2:
        a = a.reshape(-1, 2).mean(axis=1)
    if sr != SR:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * SR / sr)),
                      np.arange(len(a)), a)
    return a


# ---------- rendering ----------

def _render_events(events: list[Event], sample: np.ndarray, gain: float,
                   bpm: float, total_bars: int) -> np.ndarray:
    spb = 60.0 / bpm
    total = int(total_bars * 4 * spb * SR) + SR  # +1s でサンプル尻を収める
    buf = np.zeros(total)
    for ev in events:
        s = int(ev.beat * spb * SR)
        e = min(s + len(sample), total)
        buf[s:e] += sample[:e - s] * gain * (ev.velocity / 127.0)
    return buf


def _osc(freq: float, n: int, wave: str) -> np.ndarray:
    """n サンプルの単一オシレータ波形 (-1..1)。"""
    ph = np.arange(n) * (freq / SR)
    frac = ph - np.floor(ph)
    if wave == "square":
        return np.where(frac < 0.5, 1.0, -1.0)
    if wave == "triangle":
        return 2.0 * np.abs(2.0 * frac - 1.0) - 1.0
    if wave == "sine":
        return np.sin(2 * np.pi * ph)
    return 2.0 * frac - 1.0  # saw (既定)


def _render_synth(events: list[Event], wave: str, gain: float,
                  bpm: float, total_bars: int, sustain: float = 1.0) -> np.ndarray:
    """melody Event 列を wave のオシレータ + ADSR 風エンベロープでオフライン合成。

    sustain<1 なら decay で sustain レベルまで落とし、プラック(mid bass の転がり)を
    再現する。実機 ReaSynth と絶対値は一致しないが、他トラックとの相対バランス計測用。
    """
    spb = 60.0 / bpm
    total = int(total_bars * 4 * spb * SR) + SR
    buf = np.zeros(total)
    atk, dcy, rel = int(0.005 * SR), int(0.06 * SR), int(0.02 * SR)
    for ev in events:
        s = int(ev.beat * spb * SR)
        dur = max(1, int(ev.duration * spb * SR))
        e = min(s + dur, total)
        m = e - s
        if m <= 0:
            continue
        freq = 440.0 * 2 ** ((ev.pitch - 69) / 12.0)
        seg = _osc(freq, m, wave)
        env = np.full(m, float(sustain))  # ADSR: A立上げ→D減衰→S維持→R減衰
        a = min(atk, m)
        env[:a] = np.linspace(0, 1, a)
        d1 = min(a + dcy, m)
        if d1 > a:
            env[a:d1] = np.linspace(1.0, sustain, d1 - a)
        r = min(rel, m)
        env[m - r:] *= np.linspace(1, 0, r)
        buf[s:e] += seg * env * gain * (ev.velocity / 127.0)
    return buf


def render_track_full(song: Song, track: Track, gain_db: float | None = None) -> np.ndarray:
    """全セクション通しの1トラック。gain_db で song の音量を上書き可。"""
    gain = 10 ** ((track.gain_db if gain_db is None else gain_db) / 20)
    events = track_events(song, track)
    if isinstance(track.instrument, Synth):
        return _render_synth(events, track.instrument.wave, gain, song.bpm,
                             song.total_bars, track.instrument.sustain)
    return _render_events(events, load_mono(song.sample_path(track)),
                          gain, song.bpm, song.total_bars)


def render_clip_loop(song: Song, track: Track, bars: int = BALANCE_BARS,
                     gain_db: float | None = None) -> np.ndarray:
    """デフォルト clip の bars 小節ループ。バランス計測用(セクションの無音に汚されない)。"""
    gain = 10 ** ((track.gain_db if gain_db is None else gain_db) / 20)
    events = track.clip.events(bars, track.instrument.note)
    if isinstance(track.instrument, Synth):
        return _render_synth(events, track.instrument.wave, gain, song.bpm, bars,
                             track.instrument.sustain)
    return _render_events(events, load_mono(song.sample_path(track)),
                          gain, song.bpm, bars)


def _mix(stems: dict[str, np.ndarray]) -> np.ndarray:
    n = max(len(s) for s in stems.values())
    mix = np.zeros(n)
    for s in stems.values():
        mix[:len(s)] += s
    return mix


def render_loop_mix(song: Song, vols: dict[str, float] | None = None
                    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    vols = vols or {}
    stems = {t.name: render_clip_loop(song, t, gain_db=vols.get(t.name))
             for t in song.tracks}
    return _mix(stems), stems


def render_full_mix(song: Song) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    stems = {t.name: render_track_full(song, t) for t in song.tracks}
    return _mix(stems), stems


# ---------- metrics ----------

def rms_db(x: np.ndarray) -> float:
    return 20 * math.log10(math.sqrt(float(np.mean(x ** 2))) + 1e-12)


def peak_db(x: np.ndarray) -> float:
    return 20 * math.log10(float(np.max(np.abs(x))) + 1e-12)


def short_term_db(x: np.ndarray, win: float = 0.4) -> float:
    """最も大きい win 秒窓のパワー(短時間ラウドネスの簡易版)。"""
    w = max(1, int(win * SR))
    power = np.convolve(x ** 2, np.ones(w) / w, "same")
    return 10 * math.log10(float(np.max(power)) + 1e-12)


def band_share(x: np.ndarray, lo: float, hi: float) -> float:
    X = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    total = float(np.sum(X[(f >= 30) & (f < 16000)]))
    return float(np.sum(X[(f >= lo) & (f < hi)])) / (total + 1e-12)


def lowband(x: np.ndarray, lo: float = 30, hi: float = 120) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f >= hi)] = 0
    return np.fft.irfft(X, len(x))


def overlap_corr(a: np.ndarray, b: np.ndarray) -> float:
    """低域時間波形の相関。high=同時に鳴って食い合い, ~0=拍で住み分け。"""
    al, bl = lowband(a), lowband(b[:len(a)] if len(b) >= len(a) else
                                 np.pad(b, (0, len(a) - len(b))))
    return float(np.sum(al * bl) / (math.sqrt(np.sum(al ** 2) * np.sum(bl ** 2)) + 1e-12))


# ---------- commands ----------

def check(song: Song) -> None:
    """バランス(ループ) + 低域の食い合い + セクション別エネルギーカーブ。"""
    mix, stems = render_loop_mix(song)
    kick_rms = rms_db(stems["kick"]) if "kick" in stems else None
    print(f"=== per-track balance ({BALANCE_BARS}-bar default-clip loop @ {song.bpm}bpm) ===")
    head = f"{'track':6s}{'gain_db':>8s}{'RMS':>8s}{'ST':>8s}{'peak':>8s}"
    if kick_rms is not None:
        head += f"{'vs kick':>9s}"
    print(head)
    for t in song.tracks:
        b = stems[t.name]
        row = f"{t.name:6s}{t.gain_db:>8.1f}{rms_db(b):>8.1f}{short_term_db(b):>8.1f}{peak_db(b):>8.1f}"
        if kick_rms is not None:
            row += f"{rms_db(b) - kick_rms:>+9.1f}"
        print(row)
    clip = "CLIP!" if peak_db(mix) > 0 else "headroom ok"
    print(f"loop mix: RMS {rms_db(mix):.1f} dBFS  peak {peak_db(mix):.1f} dBFS  {clip}")

    if "kick" in stems and "bass" in stems:
        print("\n=== kick vs bass low-end (30-120Hz) ===")
        for n in ("kick", "bass"):
            print(f"  {n:6s} low-share {100 * band_share(stems[n], 30, 120):.0f}%")
        c = overlap_corr(stems["kick"], stems["bass"])
        verdict = "食い合い" if c > 0.4 else ("やや重なり" if c > 0.15 else "住み分けOK")
        print(f"  low-band overlap corr = {c:+.2f}  ({verdict})")

    bass_tracks = [t.name for t in song.tracks if "bass" in t.name]
    if bass_tracks:
        print("\n=== bass 帯域配分 (自スペクトル内シェア) ===")
        print(f"{'track':8s}{'低域<120':>10s}{'中域250-800':>12s}")
        for n in bass_tracks:
            lo = 100 * band_share(stems[n], 30, 120)
            mid = 100 * band_share(stems[n], 250, 800)
            print(f"{n:8s}{lo:>9.0f}%{mid:>11.0f}%")

    if song.sections:
        full_mix, _ = render_full_mix(song)
        print(f"\n=== sections (energy curve, total {song.total_bars} bars) ===")
        print(f"{'section':12s}{'bars':>10s}{'tracks':>7s}{'RMS':>8s}{'peak':>8s}  active")
        for sec, b0, b1 in song.section_bounds():
            s0, s1 = int(song.bar_to_sec(b0) * SR), int(song.bar_to_sec(b1) * SR)
            seg = full_mix[s0:s1]
            active = [n for n in sec.play]
            print(f"{sec.name:12s}{f'{b0}-{b1}':>10s}{len(active):>7d}"
                  f"{rms_db(seg):>8.1f}{peak_db(seg):>8.1f}  {','.join(active)}")
        print(f"full mix: RMS {rms_db(full_mix):.1f} dBFS  peak {peak_db(full_mix):.1f} dBFS")


def suggest(song: Song) -> None:
    _, stems = render_loop_mix(song)
    if "kick" not in stems:
        print("no 'kick' track — suggest needs a kick as the reference")
        return
    kick_pk = peak_db(stems["kick"])
    print(f"{'track':6s}{'cur':>7s}{'new':>7s}{'Δdb':>6s}  (target peak vs kick)")
    new_vols: dict[str, float] = {}
    for t in song.tracks:
        tgt = TARGET_PEAK_UNDER_KICK.get(t.name)
        if tgt is None or t.name == "kick":
            new_vols[t.name] = t.gain_db
            print(f"{t.name:6s}{t.gain_db:>7.1f}{t.gain_db:>7.1f}{0.0:>6.1f}  (keep)")
            continue
        delta = (kick_pk + tgt) - peak_db(stems[t.name])
        nv = round(t.gain_db + delta, 1)
        new_vols[t.name] = nv
        print(f"{t.name:6s}{t.gain_db:>7.1f}{nv:>7.1f}{delta:>+6.1f}  ({tgt:+.1f})")
    mix, _ = render_loop_mix(song, new_vols)
    clip = "CLIP!" if peak_db(mix) > 0 else "headroom ok"
    print(f"\napplied → loop mix peak {peak_db(mix):.1f} dBFS  {clip}")
    print("反映するには song.py の gain_db を上の new 値へ。")


def render(song: Song, out: Path) -> None:
    """全セクション通しのミックスを wav 書き出し(A/B・試聴用)。"""
    mix, _ = render_full_mix(song)
    x16 = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    out.parent.mkdir(parents=True, exist_ok=True)
    w = wave.open(str(out), "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(x16.tobytes())
    w.close()
    print(f"wrote {out}  peak {peak_db(mix):.1f} dBFS  ({len(mix) / SR:.1f}s, "
          f"{song.total_bars} bars)")


def bands(song: Song, target: str) -> None:
    """1サンプルの帯域スペクトル。target は track名 or パス(sample_root 相対/絶対)。"""
    try:
        tr = song.track(target)
        if isinstance(tr.instrument, Synth):
            print(f"'{target}' は synth トラック(サンプル無し)。bands はサンプル専用。")
            return
        path = song.sample_path(tr)
    except KeyError:
        p = Path(target)
        path = p if p.is_absolute() else song.sample_root / target
    a = load_mono(path)
    freqs = [31, 40, 55, 80, 110, 160, 220, 320, 440, 640, 880, 1300, 2000]
    seg = a[:min(len(a), 16384)]
    mags = []
    for f in freqs:  # Goertzel: scipy 不要で特定周波数だけ測れる
        w0 = 2 * math.pi * f / SR
        cw = 2 * math.cos(w0)
        s1 = s2 = 0.0
        for x in seg:
            s0 = x + cw * s1 - s2
            s2, s1 = s1, s0
        mags.append(math.sqrt(s1 * s1 + s2 * s2 - cw * s1 * s2) / len(seg))
    mx = max(mags) or 1
    print(f"{path.name}  RMS={rms_db(a):.1f}dBFS  dur={len(a) / SR:.2f}s")
    for f, m in zip(freqs, mags):
        print(f"  {f:5d}Hz | {'#' * int(40 * m / mx)}")
