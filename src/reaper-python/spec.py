"""Single loader for arrangement.toml — the source of truth.

Every module (compose / setup / load / status) reads the arrangement through
this, so there is exactly one place that knows the schema. Reaper is a render
target; this file (via the .toml) is authoritative.

Scripts live in subdirs and are run as `uv run python isobar/compose.py`, so
they bootstrap the import path with:

    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from spec import load_spec
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SPEC = ROOT / "arrangement.toml"


@dataclass(frozen=True)
class Rhythm:
    type: str
    hits: int
    steps: int


@dataclass(frozen=True)
class TrackSpec:
    name: str
    sample: Path          # absolute, resolved against sample_root
    step: float           # beats per step (0.25 = 16th)
    velocity: int | list[int]
    rhythm: Rhythm


@dataclass(frozen=True)
class Arrangement:
    bpm: float
    bars: int
    sampler_note: int
    scale_root: str
    scale_name: str
    tracks: list[TrackSpec]

    def track(self, name: str) -> TrackSpec:
        for t in self.tracks:
            if t.name == name:
                return t
        raise KeyError(f"no such track in arrangement: {name}")


def load_spec(path: str | Path | None = None) -> Arrangement:
    path = Path(path) if path else DEFAULT_SPEC
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # 相対 sample_root は arrangement.toml の場所基準に解決（CWD 非依存）
    sample_root = Path(raw["sample_root"])
    if not sample_root.is_absolute():
        sample_root = path.parent / sample_root
    scale = raw.get("scale", {})

    tracks: list[TrackSpec] = []
    for t in raw["tracks"]:
        r = t["rhythm"]
        if r["type"] != "euclidean":
            raise ValueError(f"unsupported rhythm type: {r['type']!r}")
        tracks.append(TrackSpec(
            name=t["name"],
            sample=(sample_root / t["sample"]).resolve(),
            step=float(t["step"]),
            velocity=t["velocity"],
            rhythm=Rhythm(type=r["type"], hits=int(r["hits"]), steps=int(r["steps"])),
        ))

    return Arrangement(
        bpm=float(raw["bpm"]),
        bars=int(raw["bars"]),
        sampler_note=int(raw["sampler_note"]),
        scale_root=scale.get("root", "C"),
        scale_name=scale.get("name", "major"),
        tracks=tracks,
    )


if __name__ == "__main__":
    a = load_spec()
    print(f"bpm={a.bpm} bars={a.bars} scale={a.scale_root} {a.scale_name}")
    for t in a.tracks:
        exists = "ok" if t.sample.exists() else "MISSING"
        print(f"  {t.name:5s} euclid({t.rhythm.hits},{t.rhythm.steps}) "
              f"step={t.step} vel={t.velocity}  [{exists}] {t.sample.name}")
