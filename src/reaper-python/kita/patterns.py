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
