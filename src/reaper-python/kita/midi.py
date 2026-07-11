"""Song → output/*.mid — 1トラック1ファイル、セクションを beat オフセットで連結。"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from kita.model import BEATS_PER_BAR, Event, Song, Track

TICKS_PER_BEAT = 480
OUT_DIR = Path(__file__).resolve().parents[1] / "output"


def track_events(song: Song, track: Track) -> list[Event]:
    """全セクションを通した song 絶対時間の Event 列。無音セクションは単に飛ぶ。"""
    events: list[Event] = []
    bar = 0
    for sec in song.effective_sections:
        clip = sec.play.get(track.name)
        if clip is not None:
            offset = bar * BEATS_PER_BAR
            events += [replace(e, beat=e.beat + offset)
                       for e in clip.events(sec.bars, track.instrument.note)]
        bar += sec.bars
    return events


def events_to_midi(events: list[Event], bpm: float, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    mtrack = MidiTrack()
    mid.tracks.append(mtrack)
    mtrack.append(MetaMessage("set_tempo", tempo=bpm2tempo(bpm), time=0))

    # mido uses delta times in ticks; absolute -> delta
    timed: list[tuple[int, Message]] = []
    for ev in events:
        on = int(ev.beat * TICKS_PER_BEAT)
        off = int((ev.beat + ev.duration) * TICKS_PER_BEAT)
        timed.append((on, Message("note_on", note=ev.pitch, velocity=ev.velocity)))
        timed.append((off, Message("note_off", note=ev.pitch, velocity=0)))
    timed.sort(key=lambda x: x[0])

    prev = 0
    for abs_tick, msg in timed:
        msg.time = abs_tick - prev
        mtrack.append(msg)
        prev = abs_tick
    mid.save(path)


def compose_all(song: Song) -> dict[str, Path]:
    """Write one MIDI file per track. Returns track name -> output path."""
    paths: dict[str, Path] = {}
    for track in song.tracks:
        events = track_events(song, track)
        path = OUT_DIR / f"{track.name}.mid"
        events_to_midi(events, song.bpm, path)
        paths[track.name] = path
        print(f"+ {track.name}: {path.name} ({len(events)} notes, {song.total_bars} bars)")
    return paths
