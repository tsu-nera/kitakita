"""kita — song.py(正本) を REAPER と計測系へ届けるライブラリ。

song.py が書きやすいよう DSL の語彙をトップレベルへ再輸出する。
"""
from kita.model import (  # noqa: F401
    Duck,
    Event,
    Reverb,
    Sampler,
    Section,
    Song,
    Synth,
    Track,
    load_song,
    section,
)
from kita.patterns import (  # noqa: F401
    FIFTH,
    ROOT,
    SEVENTH,
    THIRD,
    ChordTone,
    Phrase,
    Progression,
    arped,
    euclid,
    gated,
    melody,
    motif,
    octave,
    progression,
    repeat,
    repeat_vary,
    rhythm,
    steps,
    transpose,
    vary_tail,
)
