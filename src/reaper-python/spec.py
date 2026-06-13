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
    type: str                 # "steps" | "euclidean"
    hits: int = 0             # euclidean: ヒット数
    steps: int = 0            # euclidean: 総ステップ数
    pattern: str | None = None  # steps: "x...x..." (非'.'=ヒット) 1小節ぶん、以降ループ


@dataclass(frozen=True)
class TrackSpec:
    name: str
    sample: Path          # absolute, resolved against sample_root
    step: float           # beats per step (0.25 = 16th)
    velocity: int | list[int]
    rhythm: Rhythm
    volume_db: float = 0.0   # トラック音量 (dB, 0=ユニティ)。setup.py が D_VOL に反映
    group: str | None = None  # Reaper folder(バス)名。None=トップレベル

    @property
    def volume_linear(self) -> float:
        return 10 ** (self.volume_db / 20)


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

    @property
    def bus_names(self) -> list[str]:
        """Folder(バス)親の名前一覧。group_runs から導出。"""
        return [g for g, _ in group_runs(self.tracks) if g is not None]


def group_runs(tracks: list[TrackSpec]) -> list[tuple[str | None, list[TrackSpec]]]:
    """連続する同一 group を (group名|None, [TrackSpec,...]) のランにまとめる。

    Reaper folder は並び順で表現されるため、同じ group が離れて現れると
    階層が壊れる。非連続な group はここで弾く(正本側の早期エラー)。
    """
    runs: list[tuple[str | None, list[TrackSpec]]] = []
    seen: set[str] = set()
    for t in tracks:
        if runs and runs[-1][0] == t.group:
            runs[-1][1].append(t)
            continue
        if t.group is not None and t.group in seen:
            raise ValueError(
                f"group {t.group!r} is not contiguous in arrangement.toml "
                f"(同一グループの track は連続して並べること)")
        runs.append((t.group, [t]))
        if t.group is not None:
            seen.add(t.group)
    return runs


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
        if r["type"] == "euclidean":
            rhythm = Rhythm(type="euclidean", hits=int(r["hits"]), steps=int(r["steps"]))
        elif r["type"] == "steps":
            rhythm = Rhythm(type="steps", pattern=str(r["pattern"]))
        else:
            raise ValueError(f"unsupported rhythm type: {r['type']!r}")
        tracks.append(TrackSpec(
            name=t["name"],
            sample=(sample_root / t["sample"]).resolve(),
            step=float(t["step"]),
            velocity=t["velocity"],
            rhythm=rhythm,
            volume_db=float(t.get("volume_db", 0.0)),
            group=t.get("group"),
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
