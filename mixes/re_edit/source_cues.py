"""Hotcues on the ORIGINAL that mirror an edit's pads, so pad N jumps to the same material on both decks.

usage: uv run --project src/trackprep python -I mixes/re_edit/source_cues.py <track folder>/re-edit.yaml
Writes <track folder>/measure/source.cues.json (for the mixxx skill's write_cues --json). For each edit section the
cue is the original bar where its lead layer (mix if any, else the first stem) starts; times are original seconds.
"""
import csv
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from render import pad_order  # noqa: E402


def main(plan_path: str) -> None:
    p = Path(plan_path).expanduser().resolve()
    plan = yaml.safe_load(p.read_text())
    folder = p.parent
    t = {int(r["bar"]): float(r["time"]) for r in csv.DictReader((folder / "measure/bars.csv").open())}
    sec = {s["label"]: s for s in plan["sections"]}
    cues = []
    for label in pad_order(plan):
        layers = [L for L in sec[label]["layers"] if L.get("at", 0) == 0]
        lead = next((L for L in layers if L["stem"] == "mix"), layers[0])
        cues.append([t[lead["from"]], f"{label} ({lead['stem']} {lead['from']})"])
    src = Path(plan["track"]).expanduser()
    out = folder / "measure/source.cues.json"
    out.write_text(json.dumps({"wav": str(src), "cues": cues}, ensure_ascii=False, indent=1))
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
