"""Data model — the stable interface between song.py (the DSL) and every backend.

song.py constructs a Song; midi / sim / reaper.* only ever consume Song and
Event. Extending the musical vocabulary means adding Clip builders
(patterns.py) or Instrument kinds here — the pipeline modules stay unchanged.
"""
from __future__ import annotations

import importlib.util
import wave
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
    sustain は ReaSynth の sustain(正規化 0..1)。1.0=持続音(lead 既定)、0.0=
    プラッキーな短い減衰(mid bass の転がり)。reconcile と sim の両方が読む。
    cutoff は JSFX "Resonant Lowpass Filter" のカットオフ(Hz)。None=フィルタ無し。
    ReaSynth はフィルタを持たないため、cutoff 指定時に reconcile が JSFX を後段へ
    挿す(トランスの「レゾナンスLPF」担当)。resonance は 0..1。sim は未モデル
    (オフライン計測はフィルタ前の生 saw を測る)。
    detune はピッチのずれ(cent, ±1200)。ReaSynth "Global detune" に対応し、
    正規化 0..1 が -1200..+1200 cent に線形対応する(実機で確認)。デチューンした
    トラックを複数重ねて厚みを作るため(#2 黎明期レイヤー方式)の席。MIDI は
    ノート番号しか運べないので、この値は reconcile(実機)と sim(オフライン合成)
    だけが読む — compose の出力は detune で変わらない。
    note は Clip プロトコル (events(bars, note)) を満たすためだけの席で、melodic
    clip は無視する (自前で degree→pitch を解決する)。
    """
    wave: str = "saw"
    note: int = 60
    sustain: float = 1.0
    cutoff: float | None = None
    resonance: float = 0.2
    detune: float = 0.0  # cent。0=無変化(ReaSynth の正規化 0.5)

    def __post_init__(self):
        if not -1200 <= self.detune <= 1200:
            raise ValueError(
                f"Synth.detune は ±1200 cent の範囲 (got {self.detune})")


Instrument = Sampler | Synth


@dataclass(frozen=True)
class Duck:
    """拍グリッド駆動の ducking (ADR-001: sidechain 非採用)。

    source トラックのノート拍を引き金に、このトラックを一時的に凹ませる。
    信号キーの sidechain compression だと sim(オフライン計測)が実信号追従を
    モデル化せねばならず重い上に実機と一致する保証も無い。拍グリッドなら
    点列は決定的に1つに決まり、sim と reaper reconcile が同じ点列を使えるので
    「sim で検証できる = 実機と一致する」が構造的に保証される(kita/duck.py 参照)。
    """
    source: str      # 引き金となるトラック名(このトラックのノート拍で沈む)
    depth_db: float  # 最も沈んだ点のゲイン
    attack: float    # 秒。source の拍の attack 秒前から落ち始める
    release: float   # 秒。拍から release 秒かけて 1.0 へ戻る


@dataclass(frozen=True)
class Reverb:
    """オフライン send リバーブ (#4)。実装は kita/fx.py (pedalboard = JUCE Freeverb)。

    REAPER には反映されない — sim(オフライン合成)の中だけで完結する。実機に FX を
    挿すと kita check から見えなくなり「測れる音」と「作る音」が分岐するため
    (fx.py 冒頭の理由づけを参照)。実機は dry のまま鳴る。

    room_size が残響長を決め(実測 0.70→T60 1.9s, 0.80→2.4s, 0.95→5.5s)、
    damping は長さでなく高域の減り方(音色)を決める。send_db は dry と同エネルギーの
    残響を 0dB とした相対量で、素材に依存しない(fx.py の energy_gain)。
    hpf は残響へ送る前のハイパス(Hz)。低域を残響へ回すとミックスの土台が濁るので、
    ベース系に掛けるときは必須。lead(<120Hz が 0.01%)では実測差が出ない。
    width は 0..1 のステレオ幅。sim の計測はモノラル(左右平均)だが、リバーブは
    唯一のステレオ源なので kita render の wav だけステレオで書き出す。
    """
    room_size: float = 0.8
    damping: float = 0.4
    send_db: float = -9.0
    hpf: float | None = 300.0
    width: float = 1.0

    def __post_init__(self):
        for name in ("room_size", "damping", "width"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"Reverb.{name} は 0..1 の範囲 (got {v})")
        if self.send_db > 0:
            raise ValueError(
                f"Reverb.send_db は dry 以下 (<=0dB) を想定 (got {self.send_db})")


@dataclass(frozen=True)
class Track:
    name: str
    instrument: Instrument
    clip: Clip                # デフォルトパターン。section が差し替えない限りこれ
    gain_db: float = 0.0
    group: str | None = None  # Reaper folder(バス)。同一 group は連続して並べること
    duck: Duck | None = None  # 拍ドリブン ducking(#16)。None なら適用しない
    reverb: Reverb | None = None  # オフライン send リバーブ(#4)。sim 内で完結

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
class Hit:
    """セクション境界を跨ぐ位置指定 one-shot(#32)。

    section() のトラックセットとは独立した層で、「この小節のこの拍で1回だけ」
    鳴る transition FX (crash / impact / riser / reverse cymbal / fill) の席。
    at は "<section>:<bar>.<beat>" (bar/beat とも1始まり) でセクション相対位置を表す。
    align="start" はその位置から鳴り始め、align="end" は素材の尺だけ手前から
    鳴り始めてその位置で鳴り終わる(reverse cymbal / riser のように前セクションへ
    食い込んで境界で消える音のため)。尺は wav ヘッダから算出するので、
    align="end" を使う track の素材は実在している必要がある。
    """
    track: str
    at: str
    align: str = "start"
    velocity: int = 100


@dataclass(frozen=True)
class Song:
    bpm: float
    sample_root: Path
    tracks: list[Track]
    sections: list[Section] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
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
        for t in self.tracks:
            if t.duck is None:
                continue
            if t.duck.source not in names:
                raise ValueError(
                    f"track {t.name!r}: duck.source {t.duck.source!r} not in song")
            if t.duck.attack <= 0:
                raise ValueError(f"track {t.name!r}: duck.attack must be positive")
            if t.duck.release <= 0:
                raise ValueError(f"track {t.name!r}: duck.release must be positive")
            if t.duck.depth_db >= 0:
                raise ValueError(f"track {t.name!r}: duck.depth_db must be negative")
        section_names = {s.name for s in self.effective_sections}
        for h in self.hits:
            if h.track not in names:
                raise ValueError(f"hit: unknown track {h.track!r}")
            if not isinstance(self.track(h.track).instrument, Sampler):
                raise ValueError(
                    f"hit: track {h.track!r} must be a Sampler (one-shot 専用の席)")
            if h.align not in ("start", "end"):
                raise ValueError(f"hit: align must be 'start' or 'end' (got {h.align!r})")
            sec_name, _, _ = h.at.partition(":")
            if sec_name not in section_names:
                raise ValueError(f"hit: unknown section {sec_name!r} in at={h.at!r}")
            if self._hit_abs_beat(h) < 0:
                raise ValueError(
                    f"hit {h.track!r} at={h.at!r} align={h.align!r}: "
                    f"resolves before song start")

    def _hit_abs_beat(self, hit: Hit) -> float:
        sec_name, _, pos = hit.at.partition(":")
        bar_s, _, beat_s = pos.partition(".")
        bar, beat = int(bar_s), int(beat_s)
        for sec, start_bar, _ in self.section_bounds():
            if sec.name == sec_name:
                abs_beat = (start_bar + (bar - 1)) * BEATS_PER_BAR + (beat - 1)
                if hit.align == "end":
                    abs_beat -= self.sample_beats(self.track(hit.track))
                return abs_beat
        raise ValueError(f"hit: unknown section {sec_name!r} in at={hit.at!r}")

    def sample_beats(self, track: Track) -> float:
        """track の素材の尺を拍換算で返す(wav ヘッダのみ読む)。"""
        with wave.open(str(self.sample_path(track)), "rb") as w:
            frames, sr = w.getnframes(), w.getframerate()
        seconds = frames / sr
        return seconds * self.bpm / 60.0

    def hit_events(self, track: Track) -> list[Event]:
        """この track を対象にした hits を song 絶対拍の Event 列にして返す。"""
        events = []
        for h in self.hits:
            if h.track != track.name:
                continue
            events.append(Event(
                beat=self._hit_abs_beat(h),
                pitch=track.instrument.note,
                velocity=h.velocity,
                duration=self.sample_beats(track),
            ))
        return events

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
