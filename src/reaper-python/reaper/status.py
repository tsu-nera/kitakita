"""Diff the running Reaper against arrangement.toml — drift report.

Shows, per spec track, whether it exists, whether the sampler/sample match,
and how many MIDI items it holds; plus bpm drift and tracks not in the spec.
Requires Reaper running with the reapy bridge.

    uv run python reaper/status.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import reapy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reaper._rea import SAMPLER_FX, get_file0, norm, sampler_index  # noqa: E402
from spec import Arrangement, load_spec  # noqa: E402


def status(spec: Arrangement) -> bool:
    """Print the report. Returns True if Reaper matches the spec."""
    p = reapy.Project()
    by_name = {t.name: t for t in p.tracks}
    ok = True

    if abs(p.bpm - spec.bpm) > 1e-6:
        print(f"bpm     : {p.bpm} (spec {spec.bpm})  DRIFT")
        ok = False
    else:
        print(f"bpm     : {p.bpm}  ok")
    bus_names = spec.bus_names
    print(f"tracks  : reaper={p.n_tracks} spec={len(spec.tracks)} "
          f"bus={len(bus_names)}")

    for b in bus_names:
        present = "ok" if b in by_name else "MISSING"
        if b not in by_name:
            ok = False
        print(f"  {b:5s} bus (folder) {present}")

    for st in spec.tracks:
        t = by_name.get(st.name)
        if t is None:
            print(f"  {st.name:5s} MISSING (not in Reaper)")
            ok = False
            continue
        fx_idx = sampler_index(t)
        if fx_idx < 0:
            print(f"  {st.name:5s} no {SAMPLER_FX}")
            ok = False
            continue
        cur = get_file0(t, fx_idx)
        sample_ok = norm(cur) == norm(str(st.sample))
        flag = "ok" if sample_ok else "SAMPLE-DRIFT"
        if not sample_ok:
            ok = False
        print(f"  {st.name:5s} fx=ok items={t.n_items} sample={flag}"
              f"  ({st.sample.name})")
        if not sample_ok:
            print(f"        reaper: {cur or '(empty)'}")

    known = {t.name for t in spec.tracks} | set(bus_names)
    extra = [n for n in by_name if n not in known]
    if extra:
        print(f"extra   : not in spec: {extra}")

    print("=> in sync" if ok else "=> drift detected")
    return ok


def main() -> None:
    sys.exit(0 if status(load_spec()) else 1)


if __name__ == "__main__":
    main()
