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
class Melody:
    degrees: list[int]     # [scale] のスケール度数の並び (0=root)
    durations: list[float]  # 各音の拍数。len は degrees と一致必須
    octave: int = 4         # スケール root の基準オクターブ (4 -> A4=69)
    gate: float = 0.9       # ノート長 = duration * gate


@dataclass(frozen=True)
class TrackSpec:
    name: str
    instrument: str = "sampler"  # "sampler" (RS5k) | "synth" (ReaSynth)
    sample: Path | None = None   # sampler のみ。absolute, resolved against sample_root
    step: float = 0.25           # beats per step (0.25 = 16th)。sampler のみ使用
    velocity: int | list[int] = 100
    rhythm: Rhythm | None = None  # sampler のみ必須
    melody: Melody | None = None  # synth のみ必須
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
        instrument = t.get("instrument", "sampler")

        rhythm: Rhythm | None = None
        sample: Path | None = None
        melody: Melody | None = None

        if instrument == "sampler":
            if "sample" not in t or "rhythm" not in t:
                raise ValueError(
                    f"track {t.get('name')!r}: instrument=sampler requires "
                    f"'sample' and 'rhythm'")
            r = t["rhythm"]
            if r["type"] == "euclidean":
                rhythm = Rhythm(type="euclidean", hits=int(r["hits"]), steps=int(r["steps"]))
            elif r["type"] == "steps":
                rhythm = Rhythm(type="steps", pattern=str(r["pattern"]))
            else:
                raise ValueError(f"unsupported rhythm type: {r['type']!r}")
            sample = (sample_root / t["sample"]).resolve()
        elif instrument == "synth":
            if "melody" not in t:
                raise ValueError(
                    f"track {t.get('name')!r}: instrument=synth requires 'melody'")
            m = t["melody"]
            degrees = [int(d) for d in m["degrees"]]
            durations = [float(d) for d in m["durations"]]
            if len(degrees) != len(durations):
                raise ValueError(
                    f"track {t.get('name')!r}: melody.degrees and melody.durations "
                    f"must have equal length ({len(degrees)} != {len(durations)})")
            melody = Melody(
                degrees=degrees,
                durations=durations,
                octave=int(m.get("octave", 4)),
                gate=float(m.get("gate", 0.9)),
            )
        else:
            raise ValueError(f"unsupported instrument: {instrument!r}")

        tracks.append(TrackSpec(
            name=t["name"],
            instrument=instrument,
            sample=sample,
            step=float(t.get("step", 0.25)),
            velocity=t.get("velocity", 100),
            rhythm=rhythm,
            melody=melody,
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
        if t.instrument == "synth":
            n = len(t.melody.degrees)
            print(f"  {t.name:5s} synth  melody(notes={n}) "
                  f"octave={t.melody.octave} gate={t.melody.gate} vel={t.velocity}")
        else:
            exists = "ok" if t.sample.exists() else "MISSING"
            print(f"  {t.name:5s} sampler euclid({t.rhythm.hits},{t.rhythm.steps}) "
                  f"step={t.step} vel={t.velocity}  [{exists}] {t.sample.name}")
