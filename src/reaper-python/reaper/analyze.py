"""Measure the mix without listening — offline analysis driven by arrangement.toml.

なぜ "聴かずに測る" か: コワーキング/BTヘッドホン環境では低域やバランスを耳で
切り分けにくい。各トラックは同一トリガノートの one-shot サンプラなので、サンプル
+ MIDIリズム + volume_db からループを Python で再構成すれば、REAPER レンダリング
無しで実効ラウドネス・ピーク・帯域の食い合いを数値化できる(reapy 接続も不要)。

    uv run python reaper/analyze.py mix            # 各トラックのラウドネス/ピーク + 食い合い
    uv run python reaper/analyze.py bands bass     # 1サンプルの帯域スペクトル(track名 or パス)
    uv run python reaper/analyze.py suggest        # 目標バランスへ寄せる volume_db を提案
    uv run python reaper/analyze.py render mix.wav  # 現在のミックスを wav 書き出し(A/B用)

注意: RS5k のエンベロープ/フィルタ等は再現しない(素のサンプル再生を仮定)。トラック
"間" の相対バランスと帯域の住み分けを見るのが目的で、絶対値は REAPER 実機と一致しない。
"""
from __future__ import annotations

import argparse
import math
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spec import Arrangement, TrackSpec, load_spec  # noqa: E402

SR = 44100
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


def _rhythm_seq(track: TrackSpec) -> list[int]:
    """1小節ぶんの 1/0 列(以降ループ)。"""
    r = track.rhythm
    if r.type == "steps":
        return [0 if c == "." else 1 for c in r.pattern if not c.isspace()]
    if r.type == "euclidean":
        h, s = r.hits, r.steps
        return [1 if (i * h) // s != ((i - 1) * h) // s else 0 for i in range(s)]
    raise ValueError(f"unsupported rhythm type: {r.type!r}")


def track_hits(track: TrackSpec, bars: int) -> list[tuple[float, int]]:
    """(beat, velocity) のリスト。velocity 配列はヒットごとに循環。"""
    seq = _rhythm_seq(track)
    steps_per_bar = int(4 / track.step)
    vels = track.velocity if isinstance(track.velocity, list) else None
    hits: list[tuple[float, int]] = []
    vi = 0
    for b in range(bars):
        for i in range(steps_per_bar):
            if seq[i % len(seq)]:
                v = vels[vi % len(vels)] if vels else int(track.velocity)
                hits.append((b * 4 + i * track.step, v))
                vi += 1
    return hits


def render_track(track: TrackSpec, spec: Arrangement, vol_db: float | None = None) -> np.ndarray:
    """4小節ループを 1 トラックぶん合成する。vol_db で spec の音量を上書き可。"""
    smp = load_mono(track.sample)
    vdb = track.volume_db if vol_db is None else vol_db
    gain = 10 ** (vdb / 20) * 1.0  # velocity はヒットごとに掛ける
    spb = 60.0 / spec.bpm
    total = int(spec.bars * 4 * spb * SR) + SR
    buf = np.zeros(total)
    for beat, vel in track_hits(track, spec.bars):
        s = int(beat * spb * SR)
        e = min(s + len(smp), total)
        buf[s:e] += smp[:e - s] * gain * (vel / 127.0)
    return buf


def render_mix(spec: Arrangement, vols: dict[str, float] | None = None
               ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    vols = vols or {}
    stems = {t.name: render_track(t, spec, vols.get(t.name)) for t in spec.tracks}
    n = max(len(s) for s in stems.values())
    mix = np.zeros(n)
    for s in stems.values():
        mix[:len(s)] += s
    return mix, stems


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


# ---------- subcommands ----------

def cmd_mix(spec: Arrangement) -> None:
    mix, stems = render_mix(spec)
    kick_rms = rms_db(stems["kick"]) if "kick" in stems else None
    print(f"=== per-track ({spec.bars}-bar loop @ {spec.bpm}bpm) ===")
    head = f"{'track':6s}{'vol_db':>8s}{'RMS':>8s}{'ST':>8s}{'peak':>8s}"
    if kick_rms is not None:
        head += f"{'vs kick':>9s}"
    print(head)
    for t in spec.tracks:
        b = stems[t.name]
        row = f"{t.name:6s}{t.volume_db:>8.1f}{rms_db(b):>8.1f}{short_term_db(b):>8.1f}{peak_db(b):>8.1f}"
        if kick_rms is not None:
            row += f"{rms_db(b) - kick_rms:>+9.1f}"
        print(row)
    clip = "CLIP!" if peak_db(mix) > 0 else "headroom ok"
    print(f"\nmix: RMS {rms_db(mix):.1f} dBFS  peak {peak_db(mix):.1f} dBFS  {clip}")
    if "kick" in stems and "bass" in stems:
        print("\n=== kick vs bass low-end (30-120Hz) ===")
        for n in ("kick", "bass"):
            print(f"  {n:6s} low-share {100 * band_share(stems[n], 30, 120):.0f}%")
        c = overlap_corr(stems["kick"], stems["bass"])
        verdict = "食い合い" if c > 0.4 else ("やや重なり" if c > 0.15 else "住み分けOK")
        print(f"  low-band overlap corr = {c:+.2f}  ({verdict})")


def cmd_bands(spec: Arrangement, target: str) -> None:
    # track名 ならそのサンプル、それ以外はパス(sample_root 相対 or 絶対)
    try:
        path = spec.track(target).sample
    except KeyError:
        p = Path(target)
        path = p if p.is_absolute() else (spec.tracks[0].sample.parents[1] / target)
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
    print(f"{path.name}  RMS={rms_db(a):.1f}dBFS  dur={len(a)/SR:.2f}s")
    for f, m in zip(freqs, mags):
        print(f"  {f:5d}Hz | {'#' * int(40 * m / mx)}")


def cmd_suggest(spec: Arrangement) -> None:
    _, stems = render_mix(spec)
    if "kick" not in stems:
        print("no 'kick' track — suggest needs a kick as the reference"); return
    kick_pk = peak_db(stems["kick"])
    print(f"{'track':6s}{'cur':>7s}{'new':>7s}{'Δdb':>6s}  (target peak vs kick)")
    new_vols: dict[str, float] = {}
    for t in spec.tracks:
        tgt = TARGET_PEAK_UNDER_KICK.get(t.name)
        if tgt is None or t.name == "kick":
            new_vols[t.name] = t.volume_db
            print(f"{t.name:6s}{t.volume_db:>7.1f}{t.volume_db:>7.1f}{0.0:>6.1f}  (keep)")
            continue
        delta = (kick_pk + tgt) - peak_db(stems[t.name])
        nv = round(t.volume_db + delta, 1)
        new_vols[t.name] = nv
        print(f"{t.name:6s}{t.volume_db:>7.1f}{nv:>7.1f}{delta:>+6.1f}  ({tgt:+.1f})")
    mix, _ = render_mix(spec, new_vols)
    clip = "CLIP!" if peak_db(mix) > 0 else "headroom ok"
    print(f"\napplied → mix peak {peak_db(mix):.1f} dBFS  {clip}")
    print("反映するには arrangement.toml の volume_db を上の new 値へ。")


def cmd_render(spec: Arrangement, out: Path) -> None:
    mix, _ = render_mix(spec)
    loop = int(spec.bars * 4 * (60.0 / spec.bpm) * SR)
    x = np.tile(mix[:loop], 2)  # 2周ぶんで聴きやすく
    x16 = (np.clip(x, -1, 1) * 32767).astype("<i2")
    out.parent.mkdir(parents=True, exist_ok=True)
    w = wave.open(str(out), "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(x16.tobytes())
    w.close()
    print(f"wrote {out}  peak {peak_db(mix):.1f} dBFS  ({len(x)/SR:.1f}s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mix")
    p_bands = sub.add_parser("bands"); p_bands.add_argument("target")
    sub.add_parser("suggest")
    p_render = sub.add_parser("render"); p_render.add_argument("out")
    args = parser.parse_args()

    spec = load_spec()
    if args.cmd == "mix":
        cmd_mix(spec)
    elif args.cmd == "bands":
        cmd_bands(spec, args.target)
    elif args.cmd == "suggest":
        cmd_suggest(spec)
    elif args.cmd == "render":
        cmd_render(spec, Path(args.out))


if __name__ == "__main__":
    main()
