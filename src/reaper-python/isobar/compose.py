"""Compose techno patterns with isobar's pattern language, write MIDI files via mido.

Why this design:
- isobar's Timeline.run() insists on realtime playback even for file output.
- PatternWriterMIDI is too limited (no velocity, no Euclidean rests).
- So we use isobar's Pattern classes as generators and write events ourselves.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import isobar as iso
from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spec import Arrangement, TrackSpec, load_spec  # noqa: E402

TICKS_PER_BEAT = 480
OUT_DIR = Path(__file__).resolve().parents[1] / "output"


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


# ---------- Patterns (driven by arrangement.toml) ----------

def _rhythm_pattern(track: TrackSpec):
    """Build an isobar rhythm generator from a TrackSpec.rhythm."""
    r = track.rhythm
    if r.type == "euclidean":
        return iso.PEuclidean(r.hits, r.steps)
    raise ValueError(f"unsupported rhythm type: {r.type!r}")


def _velocity_pattern(track: TrackSpec):
    v = track.velocity
    return v if isinstance(v, int) else iso.PSequence(list(v))


def compose_track(track: TrackSpec, spec: Arrangement) -> list[Event]:
    return pattern_to_events(
        rhythm=_rhythm_pattern(track),
        pitch=spec.sampler_note,
        velocity=_velocity_pattern(track),
        step_beats=track.step,
        bars=spec.bars,
    )


def compose_all(spec: Arrangement | None = None) -> dict[str, Path]:
    """Write one MIDI file per track from the arrangement spec.

    Returns a mapping of track name -> output path.
    """
    spec = spec or load_spec()
    paths: dict[str, Path] = {}
    for track in spec.tracks:
        events = compose_track(track, spec)
        path = OUT_DIR / f"{track.name}.mid"
        events_to_midi(events, spec.bpm, path)
        paths[track.name] = path
        print(f"+ {track.name}: {path.name} ({len(events)} notes)")
    return paths


if __name__ == "__main__":
    compose_all()
