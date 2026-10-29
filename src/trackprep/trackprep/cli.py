"""trackprep — CLI entry point (`uv run trackprep <cmd>`).

analyze: 音源を解析して ~/.cache/trackprep/<track_id>.json に保存する。
show: 保存済みの解析結果を表示する (--plot で PNG)。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trackprep import store


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m}:{s:02d}"


def cmd_analyze(args) -> int:
    from trackprep.analyze import analyze_file

    rc = 0
    for p in args.audio:
        if not Path(p).is_file():
            print(f"not found: {p}", file=sys.stderr)
            rc = 1
            continue
        tid = store.track_id(p)
        if store.load(tid) and not args.force:
            print(f"skip (cached) {tid}  {p}")
            continue
        print(f"analyzing {p} ...")
        out = store.save(analyze_file(p))
        print(f"saved {out}")
    return rc


def _resolve(arg: str) -> dict | None:
    tid = store.track_id(arg) if Path(arg).is_file() else arg
    return store.load(tid)


def _bar_time(data: dict, bar: int) -> float:
    return data["bars"][bar - 1]["time"]


def _print_show(data: dict) -> None:
    print(f"title      {data['title']}")
    print(f"duration   {_mmss(data['duration'])}")
    if data["source"].get("suno_id"):
        print(f"suno_id    {data['source']['suno_id']}")
    print("tempo")
    for s in data["tempo_segments"]:
        print(f"  bar {s['from_bar']:3d}-{s['to_bar']:3d}  {s['bpm_start']:.2f} -> {s['bpm_end']:.2f} BPM")
    print("anomalies")
    for a in data["anomalies"]:
        print(f"  bar {a['bar']:3d}  {a['time']:.2f}s  {a['kind']}")
    if not data["anomalies"]:
        print("  none")
    print(f"phrase_offset_bar  {data['phrase_offset_bar']}")
    e = data["ending"]
    print(f"ending     {e['kind']} (decay {e['decay_sec']:.1f}s)")
    print(f"key        {data['key']['estimate']} (confidence {data['key']['confidence']})")
    print("\nsections (estimate)")
    print(" label       bars        time")
    for s in data["sections"]:
        t0 = _bar_time(data, s["from_bar"])
        last = s["to_bar"]
        t1 = _bar_time(data, last + 1) if last < len(data["bars"]) else data["duration"]
        print(f" {s['label']:<10} {s['from_bar']:3d}-{s['to_bar']:3d}  {_mmss(t0)}-{_mmss(t1)}")
    print("\nbar  time    rms   low  high  kick")
    for b in data["bars"]:
        print(f"{b['bar']:3d} {b['time']:7.2f}  {b['rms']:.2f}  {b['low']:.2f}  {b['high']:.2f} {b['kick']:5.1f}")


def _plot(data: dict, out: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    bars = data["bars"]
    x = [b["bar"] for b in bars]
    beats = np.array(data["beats"])
    idx = np.arange(len(beats))
    slope, icpt = np.polyfit(idx, beats, 1)
    resid = (beats - (slope * idx + icpt)) * 1000
    fig, ax = plt.subplots(3, 1, figsize=(16, 9), sharex=True)
    for key, label in (("rms", "rms"), ("low", "low 40-100Hz"), ("high", "high>6k")):
        ax[0].plot(x, [r[key] for r in bars], label=label)
    ax[0].legend()
    ax[0].set_title("per-bar energy (normalized, downbeat-aligned)")
    ax[1].plot(x, [r["kick"] for r in bars], drawstyle="steps-post")
    ax[1].set_title("kick ratio (median per bar)")
    ax[2].plot(idx / 4 + 1, resid)
    ax[2].set_title(f"beat residual from constant-tempo grid ({60 / slope:.2f} BPM, ms)")
    ax[2].set_xlabel("bar")
    for a in ax:
        for v in range(data["phrase_offset_bar"], len(bars) + 1, 8):
            a.axvline(v, color="gray", lw=0.4)
    fig.tight_layout()
    fig.savefig(out, dpi=80)


def cmd_show(args) -> int:
    data = _resolve(args.target)
    if data is None:
        print(f"not analyzed: {args.target}\nrun: trackprep analyze <audio>", file=sys.stderr)
        return 1
    _print_show(data)
    if args.plot:
        _plot(data, args.plot)
        print(f"\nplot: {args.plot}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="trackprep")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_an = sub.add_parser("analyze", help="音源を解析してキャッシュに保存")
    p_an.add_argument("audio", nargs="+")
    p_an.add_argument("--force", action="store_true", help="解析済みでも作り直す")
    p_show = sub.add_parser("show", help="解析結果を表示")
    p_show.add_argument("target", help="音源ファイル or track_id")
    p_show.add_argument("--plot", metavar="PNG", help="3段グラフを PNG で出力")
    args = parser.parse_args(argv)
    sys.exit({"analyze": cmd_analyze, "show": cmd_show}[args.cmd](args))
