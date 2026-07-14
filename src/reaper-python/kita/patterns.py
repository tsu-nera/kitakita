"""Clip builders — the ONLY place that knows what a rhythm notation means.

midi (MIDI出力) と sim (オフライン計測) は同じ events() を消費するので、
パターンの解釈がここ以外に存在してはならない。

velocity 配列は「ヒットごと」に循環する(アクセントパターン)。
"""
from __future__ import annotations

from dataclasses import dataclass

from kita.model import BEATS_PER_BAR, Event

GATE = 0.9  # ノート長 = step * GATE


def _render_steps(seq: list[int], bars: int, note: int,
                  velocity: int | tuple[int, ...], step: float) -> list[Event]:
    """1小節ぶんの 1/0 列 seq を bars ぶんループ展開して Event 列にする。"""
    steps_per_bar = round(BEATS_PER_BAR / step)
    events: list[Event] = []
    hit_i = 0
    for s in range(bars * steps_per_bar):
        if not seq[s % len(seq)]:
            continue
        v = velocity if isinstance(velocity, int) else velocity[hit_i % len(velocity)]
        events.append(Event(beat=s * step, pitch=note,
                            velocity=int(v), duration=step * GATE))
        hit_i += 1
    return events


@dataclass(frozen=True)
class StepClip:
    pattern: str  # "x...x..." (非'.'=ヒット)。1小節ぶん、以降ループ
    velocity: int | tuple[int, ...] = 100
    step: float = 0.25  # 1ステップの拍数 (0.25=16分)

    def events(self, bars: int, note: int) -> list[Event]:
        seq = [0 if c == "." else 1 for c in self.pattern if not c.isspace()]
        return _render_steps(seq, bars, note, self.velocity, self.step)


@dataclass(frozen=True)
class EuclidClip:
    hits: int
    steps: int
    velocity: int | tuple[int, ...] = 100
    step: float = 0.25

    def events(self, bars: int, note: int) -> list[Event]:
        h, s = self.hits, self.steps
        seq = [1 if (i * h) // s != ((i - 1) * h) // s else 0 for i in range(s)]
        return _render_steps(seq, bars, note, self.velocity, self.step)


def steps(pattern: str, vel: int | list[int] = 100, step: float = 0.25) -> StepClip:
    return StepClip(pattern, vel if isinstance(vel, int) else tuple(vel), step)


def euclid(hits: int, steps_: int, vel: int | list[int] = 100,
           step: float = 0.25) -> EuclidClip:
    return EuclidClip(hits, steps_, vel if isinstance(vel, int) else tuple(vel), step)


# --- melodic clips (leads #2) -------------------------------------------------

# スケール = root からの半音インターバル。degree はこの並びのインデックスで、
# len を超えると自動でオクターブ上へ回る (degree 7 = root の1オクターブ上)。
SCALES: dict[str, tuple[int, ...]] = {
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "minor":    (0, 2, 3, 5, 7, 8, 10),
    "major":    (0, 2, 4, 5, 7, 9, 11),
}
# 音名 → ピッチクラス (0..11)。C=0。
NOTE_PC: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def _degree_to_semitone(degree: int, intervals: tuple[int, ...]) -> int:
    """スケール度数 → root からの半音。度数がスケール長を超えたらオクターブ上へ。"""
    octave, i = divmod(degree, len(intervals))
    return 12 * octave + intervals[i]


@dataclass(frozen=True)
class MelodyClip:
    """スケール度数 + 音価の並びからピッチ付き Event を生む(RS5k でなく synth 用)。

    events(bars, note): note は無視し、root+octave を基準に degree→pitch を解決する。
    degrees/durations は 1フレーズぶん。bars*4 拍に満たなければ先頭からループする。
    """
    root: str
    scale: str
    degrees: tuple[int, ...]
    durations: tuple[float, ...]
    octave: int = 4      # root の基準オクターブ (4 → A4=69)
    velocity: int = 100
    gate: float = 0.9    # ノート長 = duration * gate

    def events(self, bars: int, note: int) -> list[Event]:
        intervals = SCALES[self.scale]
        base = 12 * (self.octave + 1) + NOTE_PC[self.root]  # octave4,A → 69
        total_beats = bars * BEATS_PER_BAR
        events: list[Event] = []
        beat = 0.0
        i = 0
        n = len(self.degrees)
        while beat < total_beats - 1e-9:
            dur = self.durations[i % n]
            pitch = base + _degree_to_semitone(self.degrees[i % n], intervals)
            events.append(Event(beat=beat, pitch=pitch, velocity=self.velocity,
                                duration=dur * self.gate))
            beat += dur
            i += 1
        return events


def melody(root: str, scale: str, degrees: list[int], durations: list[float],
           octave: int = 4, vel: int = 100, gate: float = 0.9) -> MelodyClip:
    if len(degrees) != len(durations):
        raise ValueError(
            f"melody: degrees と durations は同数必須 "
            f"({len(degrees)} != {len(durations)})")
    if scale not in SCALES:
        raise ValueError(f"melody: unknown scale {scale!r} (known: {sorted(SCALES)})")
    if root not in NOTE_PC:
        raise ValueError(f"melody: unknown root {root!r}")
    return MelodyClip(root, scale, tuple(degrees), tuple(durations), octave, vel, gate)
