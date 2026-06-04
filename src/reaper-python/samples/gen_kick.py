"""合成キック one-shot を生成する（Windows の本サンプルが無い Linux 環境の代替）。

ピッチ・エンベロープ（高→低へ急速降下）+ 振幅減衰 + 立ち上がりクリックで、
テクノ/トランス向けの素直なキックを作る。

    uv run python samples/gen_kick.py        # samples/kick.wav を生成
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
DUR = 0.35                       # 秒
OUT = Path(__file__).resolve().parent / "kick.wav"


def render() -> np.ndarray:
    t = np.linspace(0, DUR, int(SR * DUR), endpoint=False)

    # ピッチ・エンベロープ: 150Hz から 45Hz へ指数的に降下（パンチ→サブ）
    f_start, f_end, decay = 150.0, 45.0, 40.0
    freq = f_end + (f_start - f_end) * np.exp(-t * decay)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * np.exp(-t * 18.0)

    # 立ち上がりのクリック（アタック感）
    click = np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 200.0) * 0.3

    x = body + click
    x /= np.max(np.abs(x))       # ノーマライズ
    return (x * 0.9).astype(np.float32)


def main() -> None:
    x = render()
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(OUT), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {OUT}  ({len(pcm)} samples, {DUR}s, {SR}Hz mono)")


if __name__ == "__main__":
    main()
