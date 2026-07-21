"""拍グリッド駆動 ducking の点列 — 唯一の正本。

sim(kita/sim.py)と reaper reconcile(kita/reaper/reconcile.py)が同じ点列を
使うことが #16 の根幹。決める関数をここに1つだけ置き、両者はこれを呼ぶだけに
する(numpy / reapy への依存はしない — pure python)。
"""
from __future__ import annotations

from kita.midi import track_events
from kita.model import Duck, Song, Track


def duck_points(duck: Duck, beats: list[float], bpm: float) -> list[tuple[float, float]]:
    """(time_sec, gain_linear) の点列。gain は 1.0 基準の相対倍率。

    各 beat ごとに 3点 linear (t-attack, 1.0) / (t, depth) / (t+release, 1.0) を
    打つ。ただし:
      - t=0 付近で t-attack が負になる拍は先頭点を落とし、t=0 が depth になる
      - 隣接拍が近いと release が次の attack を追い越すので
        release_end = min(t+release, next_t-attack) にクランプする。
        クランプ結果が t 以下なら release 点は打たない
    """
    spb = 60.0 / bpm
    depth = 10 ** (duck.depth_db / 20)
    times = sorted({b * spb for b in beats})
    n = len(times)
    points: list[tuple[float, float]] = []
    for i, t in enumerate(times):
        next_t = times[i + 1] if i + 1 < n else None
        start = t - duck.attack
        if start < 0:
            points.append((0.0, depth))
        else:
            points.append((start, 1.0))
            points.append((t, depth))
        release_end = t + duck.release
        if next_t is not None:
            release_end = min(release_end, next_t - duck.attack)
        if release_end > t:
            points.append((release_end, 1.0))
    # time 昇順・同一 time の重複を除去(先着優先)して返す
    dedup: list[tuple[float, float]] = []
    for p in points:
        if dedup and abs(p[0] - dedup[-1][0]) < 1e-9:
            continue
        dedup.append(p)
    return dedup


def duck_points_song(song: Song, track: Track) -> list[tuple[float, float]]:
    """全曲通しの点列。track.duck.source の全セクション beat 列から求める。"""
    duck = track.duck
    source = song.track(duck.source)
    beats = sorted({e.beat for e in track_events(song, source)})
    return duck_points(duck, beats, song.bpm)


def duck_points_loop(song: Song, track: Track, bars: int) -> list[tuple[float, float]]:
    """デフォルト clip の bars 小節ループの点列(render_clip_loop 用)。

    全曲の点列を流用せず、必ずそのループ長の beat 列から作る。
    """
    duck = track.duck
    source = song.track(duck.source)
    beats = sorted({e.beat for e in source.clip.events(bars, source.instrument.note)})
    return duck_points(duck, beats, song.bpm)
