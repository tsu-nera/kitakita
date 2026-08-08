"""Clip builders — the ONLY place that knows what a rhythm notation means.

midi (MIDI出力) と sim (オフライン計測) は同じ events() を消費するので、
パターンの解釈がここ以外に存在してはならない。

velocity 配列は「ヒットごと」に循環する(アクセントパターン)。
"""
from __future__ import annotations

from dataclasses import dataclass

from kita.model import BEATS_PER_BAR, Clip, Event

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
class ChordTone:
    """「その小節のルートから数えたスケール度数」を表す相対度数 (#2)。

    絶対度数 (int) と混ぜて degrees に置ける。進行を持つ clip (Progression 由来)
    でのみ解決でき、roots を持たない clip に混ぜると events() で早期エラーになる。
    ROOT/THIRD/FIFTH は degree ベースなので、スケールが変わればそのスケールの
    3度/5度に自動で追従する (phrygian なら短3度、major なら長3度)。
    """
    offset: int = 0


ROOT = ChordTone(0)
THIRD = ChordTone(2)
FIFTH = ChordTone(4)
SEVENTH = ChordTone(6)

# 和音の既定 voicing (Progression.chords)。度数ベースなのでスケールに追従する。
TRIAD = (ROOT, THIRD, FIFTH)
SEVENTH_CHORD = (ROOT, THIRD, FIFTH, SEVENTH)

# degrees に置けるもの: 絶対度数 / 休符 / 進行相対の度数
Degree = int | None | ChordTone


@dataclass(frozen=True)
class MelodyClip:
    """スケール度数 + 音価の並びからピッチ付き Event を生む(RS5k でなく synth 用)。

    events(bars, note): note は無視し、root+octave を基準に degree→pitch を解決する。
    degrees/durations は 1フレーズぶん。bars*4 拍に満たなければ先頭からループする。
    roots は bar ごとのルート度数(進行)。ChordTone を解決するためだけに使い、
    音が始まる小節のルートを引く。None なら ChordTone は使えない。
    """
    root: str
    scale: str
    degrees: tuple[Degree, ...]  # None = 休符(rest): その音価ぶん進めて発音しない
    durations: tuple[float, ...]
    octave: int = 4      # root の基準オクターブ (4 → A4=69)
    velocity: int = 100
    gate: float = 0.9    # ノート長 = duration * gate
    roots: tuple[int, ...] | None = None  # bar ごとのルート度数(progression 由来)

    def _resolve(self, deg: Degree, beat: float) -> int | None:
        if not isinstance(deg, ChordTone):
            return deg
        if self.roots is None:
            raise ValueError(
                "ChordTone (ROOT/THIRD/...) は progression 由来の clip でのみ使える "
                "— melody() でなく progression(...).melody() を使うこと")
        bar = int(beat // BEATS_PER_BAR)
        return self.roots[bar % len(self.roots)] + deg.offset

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
            deg = self._resolve(self.degrees[i % n], beat)
            if deg is not None:  # None は休符 → beat だけ進める
                pitch = base + _degree_to_semitone(deg, intervals)
                events.append(Event(beat=beat, pitch=pitch, velocity=self.velocity,
                                    duration=dur * self.gate))
            beat += dur
            i += 1
        return events


def melody(root: str, scale: str, degrees: list[Degree], durations: list[float],
           octave: int = 4, vel: int = 100, gate: float = 0.9) -> MelodyClip:
    _check_key(root, scale)
    degrees, durations = _pair(degrees, durations)
    return MelodyClip(root, scale, degrees, durations, octave, vel, gate)


def _check_key(root: str, scale: str) -> None:
    if scale not in SCALES:
        raise ValueError(f"unknown scale {scale!r} (known: {sorted(SCALES)})")
    if root not in NOTE_PC:
        raise ValueError(f"unknown root {root!r}")


def _pair(degrees, durations) -> tuple[tuple[Degree, ...], tuple[float, ...]]:
    """(Phrase | degrees+durations) を正規化して同数を保証する。"""
    if isinstance(degrees, Phrase):
        if durations is not None:
            raise ValueError("Phrase を渡すときに durations は指定できない")
        return degrees.degrees, degrees.durations
    if durations is None or len(degrees) != len(durations):
        raise ValueError(
            f"degrees と durations は同数必須 "
            f"({len(degrees)} != {len(durations) if durations is not None else 'None'})")
    return tuple(degrees), tuple(durations)


# --- motif combinators (#2) ---------------------------------------------------
#
# 黎明期トランスの作り方は「1〜2小節の短いモチーフを反復し、8小節ごとに末尾だけ
# 変える」だった。degrees/durations の生の羅列ではその構造が読めないので、
# 反復・変奏を式として書けるようにする。Phrase は clip ではなく素材で、
# 鳴らすには progression(...).melody(phrase) へ渡す。

@dataclass(frozen=True)
class Phrase:
    """度数と音価の並び(モチーフ素材)。`+` で連結、`*` で反復できる。"""
    degrees: tuple[Degree, ...]
    durations: tuple[float, ...]

    @property
    def beats(self) -> float:
        return sum(self.durations)

    def __add__(self, other: Phrase) -> Phrase:
        return Phrase(self.degrees + other.degrees, self.durations + other.durations)

    def __mul__(self, n: int) -> Phrase:
        return Phrase(self.degrees * n, self.durations * n)

    def __len__(self) -> int:
        return len(self.degrees)


def motif(degrees: list[Degree], durations: list[float] | float) -> Phrase:
    """モチーフを作る。durations にスカラーを渡すと全音符その長さ(等間隔)。"""
    if not isinstance(durations, (list, tuple)):
        durations = [durations] * len(degrees)
    return Phrase(*_pair(degrees, durations))


def rhythm(pattern: str, degrees: Degree | list[Degree] = ROOT,
           step: float = 0.25) -> Phrase:
    """"x.xx x..x" 表記からモチーフを作る(16分ゲート/刻み用)。

    '.' は休符、それ以外は発音。空白は無視。degrees にリストを渡すと発音ごとに
    循環する(steps() の velocity 循環と同じ規約)。step は1文字ぶんの拍数。
    """
    seq = [c for c in pattern if not c.isspace()]
    ds = degrees if isinstance(degrees, list) else [degrees]
    out: list[Degree] = []
    hit = 0
    for c in seq:
        if c == ".":
            out.append(None)
            continue
        out.append(ds[hit % len(ds)])
        hit += 1
    return Phrase(tuple(out), (step,) * len(out))


def repeat(phrase: Phrase, n: int) -> Phrase:
    return phrase * n


def _shift(deg: Degree, n: int) -> Degree:
    """度数を n ずらす。休符(None)と ChordTone の相対性を保つ。"""
    if deg is None:
        return None
    if isinstance(deg, ChordTone):
        return ChordTone(deg.offset + n)
    return deg + n


def transpose(phrase: Phrase, n: int) -> Phrase:
    """度数を n だけずらす(スケール内の平行移動)。休符はそのまま。"""
    return Phrase(tuple(_shift(d, n) for d in phrase.degrees), phrase.durations)


def octave(phrase: Phrase, n: int = 1) -> Phrase:
    """n オクターブ上げ下げする(スケール長 = 7度ぶんの平行移動)。"""
    return transpose(phrase, 7 * n)


# --- articulation (#2): 旋律はそのまま、処理だけ差し替える ---------------------
#
# 展開の作り方として、セクションごとに別の旋律を置くのではなく「1本の素材へ
# 別の処理を適用する」形を取る。同じフックが形を変えて戻るので聴き手が覚えられ、
# 素材 N 本 × 処理 M 種の候補が N+M 個の記述で出せる。
# 音の長さ(プラッキーか持続か)は clip の gate と Synth.sustain の担当なので、
# ここでは音程とリズムだけを扱う。

def _grid(phrase: Phrase, step: float) -> list[Degree]:
    """phrase を step 刻みのグリッドへサンプルし、各スロットで鳴っている度数を返す。

    元が休符の区間は None。音価の途中(タイの内側)も同じ度数で埋まるので、
    レガートの旋律をゲートで刻み直しても音程の輪郭が保たれる。
    """
    slots = round(phrase.beats / step)
    out: list[Degree] = []
    for i in range(slots):
        t = i * step
        beat = 0.0
        cur: Degree = None
        for deg, dur in zip(phrase.degrees, phrase.durations):
            if beat - 1e-9 <= t < beat + dur - 1e-9:
                cur = deg
                break
            beat += dur
        out.append(cur)
    return out


def gated(phrase: Phrase, pattern: str, step: float = 0.25) -> Phrase:
    """旋律を pattern のゲートで刻み直す(トランスゲート)。音程は保持する。

    pattern は rhythm() と同じ表記('.'=休符)で、phrase 全体にループして掛かる。
    元が休符のスロットは pattern が発音でも鳴らさない(旋律の休符が優先)。
    """
    seq = [c for c in pattern if not c.isspace()]
    grid = _grid(phrase, step)
    degs = [d if seq[i % len(seq)] != "." else None for i, d in enumerate(grid)]
    return Phrase(tuple(degs), (step,) * len(degs))


def arped(phrase: Phrase, shape: tuple[int, ...] = (0, 2, 4),
          step: float = 0.25) -> Phrase:
    """各音を shape(度数オフセット)の並びへ展開する(コードトーンのアルペジオ)。

    shape 既定の (0,2,4) は root/3度/5度。旋律の音を基準にするので、和音そのもの
    ではなく「その音を起点にした上行」になる。休符はその音価ぶん休符のまま。
    """
    degs: list[Degree] = []
    for deg, dur in zip(phrase.degrees, phrase.durations):
        n = max(1, round(dur / step))
        for k in range(n):
            degs.append(None if deg is None else _shift(deg, shape[k % len(shape)]))
    return Phrase(tuple(degs), (step,) * len(degs))


def vary_tail(phrase: Phrase, tail: Phrase) -> Phrase:
    """末尾 len(tail) 音を tail で差し替える(フレーズ末だけ変える定石)。"""
    if len(tail) > len(phrase):
        raise ValueError(f"vary_tail: tail が長すぎる ({len(tail)} > {len(phrase)})")
    keep = len(phrase) - len(tail)
    return Phrase(phrase.degrees[:keep], phrase.durations[:keep]) + tail


def repeat_vary(phrase: Phrase, n: int, tail: Phrase) -> Phrase:
    """phrase を n 回反復し、最後の1回だけ末尾を tail に差し替える。"""
    return repeat(phrase, n - 1) + vary_tail(phrase, tail)


# --- polyphony (#3) -----------------------------------------------------------

@dataclass(frozen=True)
class StackClip:
    """複数の clip を同時に鳴らす(和音 = ポリフォニー)。

    MelodyClip は単声(度数を順に鳴らすだけ)なので、パッドのように複数の声部が
    同時に鳴るものは表現できない。ここで events をマージするだけで済むのは、
    midi が同時 note_on を素直に書け、sim がトラックのバッファを加算するため
    — 下流(midi/sim/reconcile)は無改造で和音を通せる。
    """
    clips: tuple[Clip, ...]

    def events(self, bars: int, note: int) -> list[Event]:
        evs = [e for c in self.clips for e in c.events(bars, note)]
        return sorted(evs, key=lambda e: (e.beat, e.pitch))


def stack(*clips: Clip) -> StackClip:
    """clip を重ねて同時発音にする。"""
    if not clips:
        raise ValueError("stack: clip が空")
    return StackClip(tuple(clips))


# --- progression (#2) ---------------------------------------------------------

@dataclass(frozen=True)
class Progression:
    """キー + スケール + 小節ごとのルート度数。曲の調性の唯一の定義。

    subbass / midbass / lead / pads がこれを共有することで、ルートの不一致が
    構造的に起きなくなり、キーやスケールの変更が1行で済む。
    """
    root: str
    scale: str
    roots: tuple[int, ...]  # bar ごとのルート度数。小節数を超えたら先頭へ回る

    def melody(self, degrees: Phrase | list[Degree],
               durations: list[float] | None = None,
               octave: int = 4, vel: int = 100, gate: float = 0.9) -> MelodyClip:
        """この進行に束ねた MelodyClip。Phrase をそのまま渡せる。"""
        degs, durs = _pair(degrees, durations)
        return MelodyClip(self.root, self.scale, degs, durs,
                          octave, vel, gate, roots=self.roots)

    def chords(self, phrase: Phrase, voicing: tuple[ChordTone, ...] = TRIAD,
               octave: int = 3, vel: int = 100, gate: float = 0.98,
               fold: bool = True) -> StackClip:
        """進行を和音として鳴らす(パッド #3)。phrase はリズムの骨格。

        phrase の各音を voicing のぶんだけ複製し、その小節のルートから数えた
        和音構成音へ解決して重ねる。phrase は進行の全長(len(roots) 小節)へ
        展開されるので、`motif([ROOT], [4])` なら全音符パッド、
        `rhythm("x..x ..x.")` なら同じ和音のリズム刻みになる。

        fold=True は各声部を base オクターブ内(度数 0..scale長-1)へ畳む。
        root position のままだと F4-A4-C5 のように和音が上へ流れて lead の
        音域へ突き刺さるが、畳むと自動的に転回形になり、上端が固定されて
        声部進行も滑らかになる (Am:A-C-E → F:A-C-F → C:C-E-G → G:B-D-G)。
        """
        n_scale = len(SCALES[self.scale])
        total = len(self.roots) * BEATS_PER_BAR
        reps = round(total / phrase.beats)
        if abs(reps * phrase.beats - total) > 1e-9:
            raise ValueError(
                f"chords: phrase({phrase.beats}拍)が進行の全長({total}拍)を"
                f"割り切れない — 小節数の約数になる長さにすること")
        full = phrase * reps
        voices = []
        for tone in voicing:
            degs: list[Degree] = []
            beat = 0.0
            for deg, dur in zip(full.degrees, full.durations):
                degs.append(self._voice(deg, tone, beat, n_scale, fold))
                beat += dur
            voices.append(MelodyClip(self.root, self.scale, tuple(degs),
                                     full.durations, octave, vel, gate))
        return StackClip(tuple(voices))

    def _voice(self, deg: Degree, tone: ChordTone, beat: float,
               n_scale: int, fold: bool) -> Degree:
        """1音を1声部ぶんずらして絶対度数へ解決する(休符はそのまま)。"""
        if deg is None:
            return None
        shifted = _shift(deg, tone.offset)
        if isinstance(shifted, ChordTone):  # その音が始まる小節のルートを引く
            bar = int(beat // BEATS_PER_BAR)
            shifted = self.roots[bar % len(self.roots)] + shifted.offset
        return shifted % n_scale if fold else shifted


def progression(root: str, scale: str, roots: list[int]) -> Progression:
    _check_key(root, scale)
    if not roots:
        raise ValueError("progression: roots が空")
    return Progression(root, scale, tuple(roots))
