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
from spec import Arrangement, load_spec  # noqa: E402


def reconcile(spec: Arrangement, dry: bool = False) -> None:
    p = reapy.Project()
    existing_names = [t.name for t in p.tracks]
    spec_names = {t.name for t in spec.tracks}

    for spec_t in spec.tracks:
        if not spec_t.sample.exists():
            raise FileNotFoundError(spec_t.sample)

        track = find_track(p, spec_t.name)
        if track is None:
            if dry:
                print(f"[dry] create track {spec_t.name!r} + {SAMPLER_FX}"
                      f" -> {spec_t.sample.name}")
                continue
            track = p.add_track(name=spec_t.name)
            tstate = "created"
        else:
            tstate = "exists"

        fx_idx = sampler_index(track)
        if fx_idx < 0:
            if dry:
                print(f"[dry] {spec_t.name}: add {SAMPLER_FX}"
                      f" -> {spec_t.sample.name}")
                continue
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
        elif dry:
            print(f"[dry] {spec_t.name}: set sample -> {spec_t.sample.name}")
            continue
        else:
            RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "FILE0", want)
            RPR.TrackFX_SetNamedConfigParm(track.id, fx_idx, "DONE", "")
            sstate = "sample+"

        print(f"  {spec_t.name:5s} {tstate:7s} {fxstate} {sstate}"
              f"  {spec_t.sample.name}")

    extra = [n for n in existing_names if n not in spec_names]
    if extra:
        print(f"note: {len(extra)} track(s) not in spec (left untouched): {extra}")
    if not dry:
        print(f"done. reaper tracks: {p.n_tracks}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true",
                        help="show planned actions without modifying Reaper")
    args = parser.parse_args()
    reconcile(load_spec(), dry=args.dry)


if __name__ == "__main__":
    main()
