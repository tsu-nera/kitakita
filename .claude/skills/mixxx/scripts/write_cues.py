"""Write trackprep `sections` into Mixxx as labelled hotcues (one per section start). Mixxx must be closed.

usage:
  python -I write_cues.py [--db <path>] <audio>...                      # sections of each file's own analysis
  python -I write_cues.py [--db <path>] --warp <orig> <bpm> <warped>    # orig's sections mapped onto its warp output
  python -I write_cues.py [--db <path>] --json <x.cues.json>...         # {"wav": path, "cues": [[sec, label], ...],
                                                                       #  optional "intro"/"outro": [start_sec, end_sec]}
--db defaults to ~/.mixxx/mixxxdb.sqlite. The "Mixxx is running" check applies only to that default DB;
a copy given via --db may be written while Mixxx runs.
Replaces all existing hotcues (type 1) of each track; main cue / N60dB rows are left to Mixxx.
intro / outro markers (type 6 / 7) are replaced only when the JSON gives them (position = start, length = end - start).
position unit = interleaved stereo samples (frames * 2) at library.samplerate (see memory mixxx-cue-db-format).
"""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DB = Path.home() / ".mixxx/mixxxdb.sqlite"  # default (real) DB
CACHE = Path.home() / ".cache/trackprep"
HOTCUE = 1
MARKER_TYPES = {"intro": 6, "outro": 7}
COLORS = {"intro": 0x0088FF, "groove": 0x32BE44, "break": 0xF8D200, "breakdown": 0xAF00CC, "drop": 0xE10000}


def track_id(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def own_cues(path: Path) -> list[tuple[float, str]]:
    a = json.loads((CACHE / f"{track_id(path)}.json").read_text())
    return [(a["bars"][s["from_bar"] - 1]["time"], f"{s['label']} {s['from_bar']}") for s in a["sections"]]


def warp_cues(orig: Path, bpm: float) -> list[tuple[float, str]]:
    """Map orig's section starts to the warped timeline: nearest downbeats_src index k -> first + k * bar_sec."""
    tid = track_id(orig)
    a = json.loads((CACHE / f"{tid}.json").read_text())
    w = json.loads((CACHE / tid / f"warp/{bpm:.1f}/warp.json").read_text())
    src = w["downbeats_src"]
    out = []
    for s in a["sections"]:
        t = a["bars"][s["from_bar"] - 1]["time"]
        k = min(range(len(src)), key=lambda i: abs(src[i] - t))
        out.append((w["first_downbeat_sec"] + k * w["bar_sec"], f"{s['label']} {s['from_bar']}"))
    return out


def write(con, path: Path, cues: list[tuple[float, str]], markers: dict | None = None) -> None:
    row = con.execute(
        "select li.id, li.samplerate from library li join track_locations l on l.id = li.location where l.location = ?",
        (str(path),),
    ).fetchone()
    if row is None:
        print(f"not in Mixxx library (load it in Mixxx once first): {path}", file=sys.stderr)
        return
    lib_id, sr = row
    n = con.execute("delete from cues where track_id = ? and type = ?", (lib_id, HOTCUE)).rowcount
    for i, (t, label) in enumerate(cues):
        color = COLORS.get(label.split()[0], 0xFFFFFF)
        con.execute(
            "insert into cues (track_id, type, position, length, hotcue, label, color) values (?, ?, ?, 0, ?, ?, ?)",
            (lib_id, HOTCUE, t * sr * 2, i, label, color),
        )
        print(f"  {path.name}: hotcue {i + 1:2d} {t:7.2f}s  {label}")
    print(f"{path.name}: removed {n} hotcues, wrote {len(cues)}")
    for name, (start, end) in (markers or {}).items():
        typ = MARKER_TYPES[name]
        con.execute("delete from cues where track_id = ? and type = ?", (lib_id, typ))
        con.execute(
            "insert into cues (track_id, type, position, length, hotcue, label) values (?, ?, ?, ?, -1, '')",
            (lib_id, typ, start * sr * 2, (end - start) * sr * 2),
        )
        print(f"  {path.name}: {name} marker {start:7.2f}s - {end:7.2f}s")


def mixxx_running() -> bool:
    return subprocess.run(["pgrep", "-x", "mixxx"], capture_output=True).returncode == 0


def open_db(db: Path) -> sqlite3.Connection:
    """Refuse the real DB while Mixxx runs; otherwise back up next to `db` and connect."""
    db = db.resolve()
    if db == DB.resolve() and mixxx_running():
        sys.exit("Mixxx is running; close it first (it overwrites cues on exit)")
    backup = db.with_name(f"{db.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(db, backup)
    print(f"backup: {backup}")
    return sqlite3.connect(db)


def main(argv: list[str]) -> None:
    db = DB
    if argv[:1] == ["--db"]:
        db, argv = Path(argv[1]), argv[2:]
    if argv[:1] == ["--warp"]:
        orig, bpm, target = Path(argv[1]).resolve(), float(argv[2]), Path(argv[3]).resolve()
        jobs = [(target, warp_cues(orig, bpm), None)]
    elif argv[:1] == ["--json"]:
        jobs = []
        for p in argv[1:]:
            j = json.loads(Path(p).read_text())
            markers = {k: (float(j[k][0]), float(j[k][1])) for k in MARKER_TYPES if k in j}
            jobs.append((Path(j["wav"]).resolve(), [(float(t), label) for t, label in j["cues"]], markers))
    else:
        jobs = [(Path(p).resolve(), own_cues(Path(p).resolve()), None) for p in argv]
    con = open_db(db)
    with con:
        for path, cues, markers in jobs:
            write(con, path, cues, markers)


if __name__ == "__main__":
    main(sys.argv[1:])
