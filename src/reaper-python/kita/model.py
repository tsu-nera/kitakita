"""Data model — the stable interface between song.py (the DSL) and every backend.

song.py constructs a Song; midi / sim / reaper.* only ever consume Song and
Event. Extending the musical vocabulary means adding Clip builders
(patterns.py) or Instrument kinds here — the pipeline modules stay unchanged.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

BEATS_PER_BAR = 4
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SONG = ROOT / "song.py"


@dataclass(frozen=True)
class Event:
    beat: float       # start time in beats (song-absolute after arrangement)
    pitch: int
    velocity: int
    duration: float   # beats


class Clip(Protocol):
    """Anything that can render `bars` bars of events.

    `note` is the track's trigger note (Sampler.note); rhythm clips emit it,
    melodic clips are free to ignore it.
    """

    def events(self, bars: int, note: int) -> list[Event]: ...


@dataclass(frozen=True)
class Sampler:
    """RS5k one-shot instrument. `sample` is relative to Song.sample_root."""
    sample: str
    note: int = 60


@dataclass(frozen=True)
class Synth:
    """ReaSynth 音源 (leads #2)。RS5k は C4 固定でメロディ不可のため、ピッチ可変の
    ReaSynth を使う。melodic な Clip (patterns.melody) と組で使う想定。

    wave は主オシレータ波形 ("saw"|"square"|"triangle"|"sine")。reconcile は
    対応する "* mix" パラメータを 1.0 にし他を 0 にする。sim は同じ波形を
    オフライン合成してバランス計測へ乗せる。
    note は Clip プロトコル (events(bars, note)) を満たすためだけの席で、melodic
    clip は無視する (自前で degree→pitch を解決する)。
    """
    wave: str = "saw"
    note: int = 60


Instrument = Sampler | Synth


@dataclass(frozen=True)
class Track:
    name: str
    instrument: Instrument
    clip: Clip                # デフォルトパターン。section が差し替えない限りこれ
    gain_db: float = 0.0
    group: str | None = None  # Reaper folder(バス)。同一 group は連続して並べること
    # 将来の席: fx: tuple = ()  — FX #4 (sidechain/reverb) の reconcile 対象

    @property
    def gain_linear(self) -> float:
        return 10 ** (self.gain_db / 20)


@dataclass(frozen=True)
class Section:
    name: str
    bars: int
    play: dict[str, Clip]  # track名 → clip。載っていない track はこの区間無音


def section(name: str, bars: int, tracks: list[Track],
            override: dict[Track | str, Clip] | None = None) -> Section:
    """Section shorthand: 各 Track のデフォルト clip を使い、override で差し替える。"""
    ov = {(k.name if isinstance(k, Track) else k): v for k, v in (override or {}).items()}
    play = {t.name: ov.pop(t.name, t.clip) for t in tracks}
    if ov:
        raise ValueError(f"override for tracks not in section {name!r}: {sorted(ov)}")
    return Section(name, bars, play)


@dataclass(frozen=True)
class Song:
    bpm: float
    sample_root: Path
    tracks: list[Track]
    sections: list[Section] = field(default_factory=list)
    loop_bars: int = 4  # sections が空のとき(ジャム時)の暗黙ループ長

    def __post_init__(self):
        object.__setattr__(self, "sample_root", Path(self.sample_root))
        names = [t.name for t in self.tracks]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise ValueError(f"duplicate track names: {dup}")
        group_runs(self.tracks)  # 非連続 group を正本側で早期エラー
        for s in self.sections:
            if s.bars <= 0:
                raise ValueError(f"section {s.name!r}: bars must be positive")
            unknown = sorted(set(s.play) - set(names))
            if unknown:
                raise ValueError(f"section {s.name!r} plays unknown tracks: {unknown}")

    def track(self, name: str) -> Track:
        for t in self.tracks:
            if t.name == name:
                return t
        raise KeyError(f"no such track in song: {name}")

    @property
    def effective_sections(self) -> list[Section]:
        """sections が空なら全トラックのデフォルト clip を鳴らす暗黙1セクション。"""
        if self.sections:
            return list(self.sections)
        return [Section("loop", self.loop_bars, {t.name: t.clip for t in self.tracks})]

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.effective_sections)

    def section_bounds(self) -> list[tuple[Section, int, int]]:
        """(section, start_bar, end_bar) の列。"""
        bounds, bar = [], 0
        for s in self.effective_sections:
            bounds.append((s, bar, bar + s.bars))
            bar += s.bars
        return bounds

    def bar_to_sec(self, bar: float) -> float:
        return bar * BEATS_PER_BAR * 60.0 / self.bpm

    def sample_path(self, track: Track) -> Path:
        return (self.sample_root / track.instrument.sample).resolve()

    @property
    def bus_names(self) -> list[str]:
        return [g for g, _ in group_runs(self.tracks) if g is not None]


def group_runs(tracks: list[Track]) -> list[tuple[str | None, list[Track]]]:
    """連続する同一 group を (group名|None, [Track,...]) のランにまとめる。

    Reaper folder は並び順で表現されるため、同じ group が離れて現れると
    階層が壊れる。非連続な group はここで弾く(正本側の早期エラー)。
    """
    runs: list[tuple[str | None, list[Track]]] = []
    seen: set[str] = set()
    for t in tracks:
        if runs and runs[-1][0] == t.group:
            runs[-1][1].append(t)
            continue
        if t.group is not None and t.group in seen:
            raise ValueError(
                f"group {t.group!r} is not contiguous "
                f"(同一グループの track は連続して並べること)")
        runs.append((t.group, [t]))
        if t.group is not None:
            seen.add(t.group)
    return runs


def load_song(path: str | Path | None = None) -> Song:
    """song.py を実行して `song: Song` を取り出す。全コマンドの唯一の入口。

    相対 sample_root は song.py の場所基準に解決する(CWD 非依存)。
    """
    path = Path(path) if path else DEFAULT_SONG
    spec = importlib.util.spec_from_file_location("_kita_song", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    song = getattr(mod, "song", None)
    if not isinstance(song, Song):
        raise TypeError(f"{path} must define a module-level `song: Song`")
    if not song.sample_root.is_absolute():
        song = replace(song, sample_root=path.parent / song.sample_root)
    return song
