"""Compose techno patterns with isobar's pattern language, write MIDI files via mido.

Why this design:
- isobar's Timeline.run() insists on realtime playback even for file output.
- PatternWriterMIDI is too limited (no velocity, no Euclidean rests).
- So we use isobar's Pattern classes as generators and write events ourselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import isobar as iso
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

TICKS_PER_BEAT = 480
OUT_DIR = Path(__file__).resolve().parents[1] / "output"

# Sampler trigger note (ReaSamplomatic5000 default)
SAMPLER_NOTE = 60


@dataclass
class Event:
    beat: float       # start time in beats
    pitch: int
    velocity: int
    duration: float   # in beats


def pattern_to_events(
    *,
    rhythm: Iterable[int],          # 1/0 sequence per step (Euclidean etc.)
    pitch: Iterable[int] | int,     # int or pattern of MIDI pitches
    velocity: Iterable[int] | int,  # int or pattern of velocities
    step_beats: float,              # beats per step (e.g., 0.25 = 16th)
    bars: int,
    beats_per_bar: int = 4,
) -> list[Event]:
    """Iterate isobar patterns over `bars` and emit Events for each active step."""
    steps_per_bar = int(beats_per_bar / step_beats)
    total_steps = bars * steps_per_bar
    r_iter = iter(rhythm)
    p_iter = iter(pitch) if not isinstance(pitch, int) else None
    v_iter = iter(velocity) if not isinstance(velocity, int) else None

    events: list[Event] = []
    for step in range(total_steps):
        hit = next(r_iter)
        cur_pitch = next(p_iter) if p_iter is not None else pitch
        cur_vel = next(v_iter) if v_iter is not None else velocity
        if hit and cur_pitch is not None:
            events.append(Event(
                beat=step * step_beats,
                pitch=int(cur_pitch),
                velocity=int(cur_vel),
                duration=step_beats * 0.9,
            ))
    return events


def events_to_midi(events: list[Event], bpm: float, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    track = MidiTrack()
    mid.tracks.append(track)
    track.append(MetaMessage("set_tempo", tempo=bpm2tempo(bpm), time=0))

    # mido uses delta times in ticks; absolute -> delta
    timed: list[tuple[int, Message]] = []
    for ev in events:
        on_tick = int(ev.beat * TICKS_PER_BEAT)
        off_tick = int((ev.beat + ev.duration) * TICKS_PER_BEAT)
        timed.append((on_tick, Message("note_on", note=ev.pitch, velocity=ev.velocity)))
        timed.append((off_tick, Message("note_off", note=ev.pitch, velocity=0)))
    timed.sort(key=lambda x: x[0])

    prev = 0
    for abs_tick, msg in timed:
        msg.time = abs_tick - prev
        track.append(msg)
        prev = abs_tick

    mid.save(path)


# ---------- Patterns ----------

BPM = 138
BARS = 4

A_PHRYGIAN = iso.Scale([0, 1, 3, 5, 7, 8, 10], name="phrygian")  # A as root


def compose_all() -> dict[str, Path]:
    """Write kick/hat/bass MIDI files. Returns mapping of track name -> path."""

    # Kick: classic 4-on-the-floor (Euclidean 4,16 = 4 hits in 16 steps)
    kick_events = pattern_to_events(
        rhythm=iso.PEuclidean(4, 16),
        pitch=SAMPLER_NOTE,
        velocity=120,
        step_beats=0.25,
        bars=BARS,
    )

    # Hat: Euclidean 11/16 for syncopation
    hat_events = pattern_to_events(
        rhythm=iso.PEuclidean(11, 16),
        pitch=SAMPLER_NOTE,
        velocity=iso.PSequence([85, 70, 70, 70, 90, 70, 70, 70]),
        step_beats=0.25,
        bars=BARS,
    )

    # Bass: off-beats (Euclidean 3,8), all on SAMPLER_NOTE
    # (Sampler is mono-pitched anyway; melodic content lives in lead/synth)
    bass_events = pattern_to_events(
        rhythm=iso.PEuclidean(3, 8),
        pitch=SAMPLER_NOTE,
        velocity=100,
        step_beats=0.5,
        bars=BARS,
    )

    paths = {
        "kick": OUT_DIR / "kick.mid",
        "hat": OUT_DIR / "hat.mid",
        "bass": OUT_DIR / "bass.mid",
    }
    events_to_midi(kick_events, BPM, paths["kick"])
    events_to_midi(hat_events, BPM, paths["hat"])
    events_to_midi(bass_events, BPM, paths["bass"])
    for name, p in paths.items():
        print(f"+ {name}: {p.name}")
    return paths


if __name__ == "__main__":
    compose_all()
