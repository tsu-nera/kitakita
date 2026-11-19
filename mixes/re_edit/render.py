"""Render a re-edit plan (YAML) from a track's 142 BPM warp output (trackprep warp --stems).

usage: uv run --project src/trackprep python mixes/re_edit/render.py <plan.yaml>
Writes the edit WAV, <edit>.arrangement.md (edit-bar -> source-bar map), <edit>.cues.json (for the mixxx skill's write_cues --json) and <edit>.drums.wav
(the same plan rendered from drums stems only), then prints per-bar four_on_floor of the edit.
"""
import json
from datetime import datetime
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from trackprep import drums as drums_mod
from trackprep import store

FADE = 0.005  # s, de-click at every layer edge


def main(plan_path: str) -> None:
    plan = yaml.safe_load(Path(plan_path).read_text())
    raw = Path(plan["track"]).expanduser()
    tid = store.track_id(raw)
    a = store.load(tid)
    w = json.loads((store.track_dir(tid) / f"warp/{float(plan['bpm']):.1f}/warp.json").read_text())
    paths = {"mix": w["mix"], **w["stems"]}
    audio = {}
    for k, p in paths.items():
        audio[k], sr = sf.read(p, always_2d=True)
    src = np.array(w["downbeats_src"])
    bar = w["bar_sec"] * sr
    d0 = w["first_downbeat_sec"] * sr

    def k_of(n: int) -> int:  # analyze bar n -> warped bar index (0-based)
        k = int(np.argmin(np.abs(src - a["bars"][n - 1]["time"])))
        assert abs(src[k] - a["bars"][n - 1]["time"]) < 0.02, f"bar {n} has no warped downbeat"
        return k

    def seg(stem: str, b0: int, b1: int, gain_db: list | None = None) -> np.ndarray:
        s, e = int(round(d0 + k_of(b0) * bar)), int(round(d0 + (k_of(b1) + 1) * bar))
        x = audio[stem][s:e].copy()
        f = int(FADE * sr)
        x[:f] *= np.linspace(0, 1, f)[:, None]
        x[-f:] *= np.linspace(1, 0, f)[:, None]
        if gain_db:  # linear-in-dB ramp over the layer
            x *= (10 ** (np.linspace(gain_db[0], gain_db[1], len(x)) / 20))[:, None]
        return x

    total = sum(s["bars"] for s in plan["sections"])
    n = int(round(total * bar))
    out, drm = np.zeros((n, 2)), np.zeros((n, 2))
    starts, at = {}, 0
    for s in plan["sections"]:
        starts[s["label"]] = at
        for L in s["layers"]:
            nb = L["to"] - L["from"] + 1
            off = L.get("at", 0)
            if off >= 0:
                assert off + nb <= s["bars"], f"{s['label']}: layer {L} overruns the {s['bars']}-bar section"
            p = int(round((at + off) * bar))
            assert p >= 0, f"{s['label']}: layer starts before the edit"
            x = seg(L["stem"], L["from"], L["to"], L.get("gain_db"))
            m = min(len(x), n - p)
            out[p:p + m] += x[:m]
            dx = x if L["stem"] == "drums" else seg("drums", L["from"], L["to"], L.get("gain_db")) if L["stem"] == "mix" else None
            if dx is not None:
                drm[p:p + m] += dx[:m]
        at += s["bars"]
    starts["end"] = total

    peak = np.abs(out).max()
    if peak > 0.99:
        out *= 0.99 / peak
    dst = Path(plan["out"]).expanduser()
    sf.write(dst, out, sr, subtype="PCM_16")
    sf.write(dst.with_suffix(".drums.wav"), drm, sr, subtype="PCM_16")

    sec = lambda b: b * bar / sr  # noqa: E731
    order = pad_order(plan)  # Mixxx assigns hotcues in list order: pads 1-8 first
    cues = [[sec(starts[label]), label] for label in order]
    mk = {k: [sec(starts[v[0]]), sec(starts[v[1]])] for k, v in plan.get("markers", {}).items()}
    dst.with_suffix(".cues.json").write_text(json.dumps({"wav": str(dst), "cues": cues, **mk}, ensure_ascii=False, indent=1))

    dst.with_suffix(".yaml").write_text(Path(plan_path).read_text())  # the plan this WAV was rendered from
    dst.with_suffix(".arrangement.md").write_text(arrangement_md(plan, plan_path, starts, sec, len(a["bars"])))

    beats = np.arange(total * 4) * (bar / sr / 4)
    rows = drums_mod.bar_kicks(drm, sr, beats, beats[::4])
    print(f"{dst.name}: {total} bars, {n / sr:.1f}s, peak scale {min(1, 0.99 / peak):.2f}")
    for s in plan["sections"]:
        b0 = starts[s["label"]]
        flags = "".join("x" if r["four_on_floor"] else "." for r in rows[b0:b0 + s["bars"]])
        print(f"  bar {b0 + 1:3d}-{b0 + s['bars']:3d}  {sec(b0):6.1f}s  {s['label']:<14} 4otf {flags}")


def arrangement_md(plan: dict, plan_path: str, starts: dict, sec, n_src: int) -> str:
    """Edit-bar -> source-bar map, and the joints where the original order is broken."""
    mmss = lambda s: f"{int(s // 60)}:{int(s % 60):02d}"  # noqa: E731
    sp = Path(plan_path).resolve().parent / "structure.yaml"  # the track folder holds both
    secs = yaml.safe_load(sp.read_text())["sections"] if sp.exists() else []

    def roles(b0: int, b1: int) -> str:
        hit = [f"{x['role']} {x['from']}–{x['to']}" for x in secs if x["from"] <= b1 and x["to"] >= b0]
        return ", ".join(hit) or "?"
    layer_txt = lambda L: (f"{L['stem']} {L['from']}–{L['to']}" + (f" (at {L['at']})" if L.get("at") else "")  # noqa: E731
                           + (f" ({L['gain_db'][0]}→{L['gain_db'][1]} dB)" if L.get("gain_db") else ""))
    lines = [
        f"# {Path(plan['out']).expanduser().stem} — arrangement",
        "",
        f"- plan: `{Path(plan_path).resolve()}`",
        f"- source: `{plan['track']}`（小節番号は原曲の trackprep analyze の bar）",
        f"- rendered: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "| pad | edit bars | time | label | layers (stem source bars) | 原曲での役割 |",
        "|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(plan["sections"]):
        b0 = starts[s["label"]]
        k = pad_order(plan).index(s["label"])
        pad = str(k + 1) if k < 8 else "-"
        lines.append(f"| {pad} | {b0 + 1}–{b0 + s['bars']} | {mmss(sec(b0))} | {s['label']} | "
                     + " + ".join(layer_txt(L) for L in s["layers"]) + " | "
                     + "; ".join(dict.fromkeys(f"{L['stem']}: {roles(L['from'], L['to'])}" if L["stem"] != "mix" else roles(L["from"], L["to"])
                                               for L in s["layers"] if L.get("at", 0) >= 0)) + " |")

    used = sorted({b for s in plan["sections"] for L in s["layers"] for b in range(L["from"], L["to"] + 1)})
    # walk the edit bar by bar along its "lead" layer (mix if present, else the first stem) and report every jump
    seq = []  # (edit bar, source bar, section label, layer)
    at = 0
    for s in plan["sections"]:
        for b in range(s["bars"]):
            cover = [L for L in s["layers"] if L.get("at", 0) >= 0 and L.get("at", 0) <= b < L.get("at", 0) + L["to"] - L["from"] + 1]
            if cover:
                L = next((c for c in cover if c["stem"] == "mix"), cover[0])
                seq.append((at + b, L["from"] + b - L.get("at", 0), s["label"], L))
        at += s["bars"]
    joints = []
    for (e0, b0, s0, L0), (e1, b1, s1, L1) in zip(seq, seq[1:]):
        if b1 != b0 + 1:
            where = f"{s0} → {s1}" if s0 != s1 else f"{s0} の中"
            joints.append(f"- edit {e1 + 1} 小節目（{where}）: 原曲 {b0} の後に {b1}（{L0['stem']} → {L1['stem']}）")
    lines += ["", "## 原曲の順番どおりでないつなぎ目", "", *(joints or ["- なし"])]
    unused = [b for b in range(1, n_src + 1) if b not in used]
    lines += ["", "## 使っていない原曲の小節", "", f"- {ranges(unused) or 'なし'}（原曲は {n_src} 小節）",
              *(f"  - {r}: {roles(*map(int, r.split('–')) if '–' in r else (int(r), int(r)))}" for r in ranges(unused).split(", ") if r), ""]
    return "\n".join(lines)


def pad_order(plan: dict) -> list[str]:
    """Section labels in hotcue order: plan['pads'] (up to 8, in time order) first, then the rest in time order."""
    labels = [s["label"] for s in plan["sections"]]
    pads = [lb for lb in labels if lb in plan.get("pads", labels[:8])]
    assert len(pads) <= 8, "at most 8 pads"
    return pads + [lb for lb in labels if lb not in pads]


def ranges(xs: list[int]) -> str:
    out, i = [], 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
            j += 1
        out.append(f"{xs[i]}–{xs[j]}" if j > i else str(xs[i]))
        i = j + 1
    return ", ".join(out)


if __name__ == "__main__":
    main(sys.argv[1])
