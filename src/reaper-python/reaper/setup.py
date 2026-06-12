"""Reconcile Reaper tracks to match arrangement.toml — idempotent.

Re-running is safe: tracks are matched by name (created only if missing) and
the ReaSamplomatic5000 sample is set only when it differs. This fixes the
known issue #1 bug where re-running duplicated tracks.

    uv run python reaper/setup.py          # reconcile
    uv run python reaper/setup.py --dry    # show planned actions only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import reapy
from reapy import reascript_api as RPR

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reaper._rea import SAMPLER_FX, find_track, get_file0, norm, sampler_index  # noqa: E402
from spec import Arrangement, TrackSpec, group_runs, load_spec  # noqa: E402


def build_layout(spec: Arrangement) -> list[dict]:
    """上から並べる Reaper トラック列を導出する。

    各エントリ: name / kind('bus'|'sample') / depth(I_FOLDERDEPTH) / spec。
    group ごとに親バス(depth=+1)を挿し、最後の子で folder を閉じる(depth=-1)。
    """
    layout: list[dict] = []
    for gname, ts in group_runs(spec.tracks):
        if gname is not None:
            layout.append(dict(name=gname, kind="bus", depth=1, spec=None))
            for i, t in enumerate(ts):
                layout.append(dict(name=t.name, kind="sample",
                                   depth=(-1 if i == len(ts) - 1 else 0), spec=t))
        else:
            for t in ts:
                layout.append(dict(name=t.name, kind="sample", depth=0, spec=t))
    return layout


def _reconcile_sample(track, spec_t: TrackSpec) -> str:
    """sample トラックの RS5k/FILE0/音量を spec に合わせ、状態文字列を返す。"""
    fx_idx = sampler_index(track)
    if fx_idx < 0:
        fx_idx = RPR.TrackFX_AddByName(track.id, SAMPLER_FX, False, -1)
        if fx_idx < 0:
            raise RuntimeError(f"could not add {SAMPLER_FX} to {spec_t.name}")
        fxstate = "fx+"
    else:
        fxstate = "fx="

    cur = get_file0(track, fx_idx)
    want = str(spec_t.sample)
    if norm(cur) == norm(want):
        sstate = "sample="
    else:
        RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "FILE0", want)
        RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "DONE", "")
        sstate = "sample+"

    want_vol = spec_t.volume_linear
    if abs(RPR.GetMediaTrackInfo_Value(track.id, "D_VOL") - want_vol) < 1e-3:
        vstate = "vol="
    else:
        RPR.SetMediaTrackInfo_Value(track.id, "D_VOL", want_vol)
        vstate = "vol+"
    return f"{fxstate} {sstate} {vstate}"


def reconcile(spec: Arrangement, dry: bool = False) -> None:
    for t in spec.tracks:
        if not t.sample.exists():
            raise FileNotFoundError(t.sample)

    p = reapy.Project()
    layout = build_layout(spec)
    known = {e["name"] for e in layout}

    if dry:
        for e in layout:
            tag = "exists" if find_track(p, e["name"]) is not None else "create"
            print(f"[dry] {e['name']:6s} {e['kind']:6s} depth={e['depth']:+d} ({tag})")
        print(f"[dry] order: {' > '.join(e['name'] for e in layout)}")
        extra = [t.name for t in p.tracks if t.name not in known]
        if extra:
            print(f"[dry] not in spec (untouched): {extra}")
        return

    # 1) 存在を担保しつつ各トラックを reconcile
    for e in layout:
        track = find_track(p, e["name"])
        tstate = "exists" if track is not None else "created"
        if track is None:
            track = p.add_track(name=e["name"])
        detail = _reconcile_sample(track, e["spec"]) if e["kind"] == "sample" else "bus"
        print(f"  {e['name']:6s} {tstate:7s} {detail}")

    # 2) layout 順へ並べ替え(左から確定。目的トラックを位置 idx へ引き上げる)
    for idx, e in enumerate(layout):
        track = find_track(p, e["name"])
        RPR.SetOnlyTrackSelected(track.id)
        RPR.ReorderSelectedTracks(idx, 0)

    # 3) folder 階層(I_FOLDERDEPTH)を設定。並べ替え後に行う
    for e in layout:
        track = find_track(p, e["name"])
        RPR.SetMediaTrackInfo_Value(track.id, "I_FOLDERDEPTH", float(e["depth"]))

    extra = [t.name for t in p.tracks if t.name not in known]
    if extra:
        print(f"note: {len(extra)} track(s) not in spec (left untouched): {extra}")
    print(f"done. reaper tracks: {p.n_tracks}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true",
                        help="show planned actions without modifying Reaper")
    args = parser.parse_args()
    reconcile(load_spec(), dry=args.dry)


if __name__ == "__main__":
    main()
