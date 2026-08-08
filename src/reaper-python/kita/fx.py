"""Offline FX — pedalboard(JUCE) をオフライン合成の後段に掛ける層 (#4)。

なぜ REAPER 側の FX(ReaVerbate)ではないか: 実機に挿した FX は sim(kita check)
から見えない。「測れる音」と「作る音」が分岐し、候補 wav に「リバーブは掛かって
いない」という注記が必要になる。pedalboard なら同じパラメータで sim の中で完結し、
書き出した wav がそのまま完成形になる — ADR-001 の synth-first と同じ理由づけ。
その代わり REAPER 側にリバーブは反映されない(実機は dry のまま鳴る)。

send 量の定義: JUCE Freeverb の wet_level は正規化ミックスではない(コムフィルタ
8本が持続音でエネルギーを積むため、wet_level=0.2 でも実測 +4.7dB 増えた)。
そこで wet だけを生成し、インパルス応答のエネルギーゲイン k で割ってから
10**(send_db/20) を掛ける。k は (room, damping, hpf) だけで決まるので、
send_db は「dry と同エネルギーの残響を 0dB としたときの相対量」という
素材非依存の量になる — 編曲(セクションの無音)で残響量が動かない。
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from kita.model import Reverb

SR = 44100
_IR_LEN = 10  # 秒。T60 5.5s(room0.95)でも収まる長さ


def _board(spec: Reverb):
    from pedalboard import HighpassFilter, Pedalboard, Reverb as PbReverb
    fx = []
    if spec.hpf is not None:  # 低域を残響へ送らない(土台を濁さないための定石)
        fx.append(HighpassFilter(cutoff_frequency_hz=spec.hpf))
    fx.append(PbReverb(room_size=spec.room_size, damping=spec.damping,
                       wet_level=1.0, dry_level=0.0, width=spec.width))
    return Pedalboard(fx)


@lru_cache(maxsize=32)
def _impulse_response(room_size: float, damping: float, hpf: float | None,
                      width: float) -> np.ndarray:
    """wet 経路のステレオ・インパルス応答 (2, _IR_LEN*SR)。"""
    imp = np.zeros((2, _IR_LEN * SR), dtype=np.float32)
    imp[:, 0] = 1.0
    spec = Reverb(room_size=room_size, damping=damping, hpf=hpf, width=width)
    return _board(spec)(imp, SR).astype(np.float64)


def energy_gain(spec: Reverb) -> float:
    """インパルス応答の RMS ゲイン k。定常入力なら RMS_wet ≈ k * RMS_dry。"""
    ir = _impulse_response(spec.room_size, spec.damping, spec.hpf, spec.width)
    return math.sqrt(float(np.sum(ir ** 2)) / 2)


def t60(spec: Reverb) -> float:
    """残響長(秒)。IR の 100ms 移動平均パワーがピークから -60dB を切る時刻。"""
    ir = _impulse_response(spec.room_size, spec.damping, spec.hpf, spec.width)
    e = np.mean(ir ** 2, axis=0)
    w = int(0.1 * SR)
    p = np.convolve(e, np.ones(w) / w, "same")
    above = np.where(p > p.max() * 1e-6)[0]
    return float(above[-1]) / SR if len(above) else 0.0


def to_stereo(mono: np.ndarray) -> np.ndarray:
    return np.stack([mono, mono])


def apply_reverb(dry: np.ndarray, spec: Reverb) -> np.ndarray:
    """dry (2,N) へ send_db ぶんの wet を足した (2,N) を返す。

    リバーブは唯一のステレオ源なので、sim がモノラルでも FX 層は常にステレオで
    処理する。計測側はこの結果を M 成分(左右平均)へ畳んで従来の 1D metrics へ通す。
    """
    wet = _board(spec)(dry.astype(np.float32), SR).astype(np.float64)
    return dry + wet * (10 ** (spec.send_db / 20) / energy_gain(spec))
