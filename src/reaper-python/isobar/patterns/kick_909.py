"""TR-909 kick test: 4-on-the-floor, 4 bars @ 132 BPM -> MIDI file (mido direct)."""
from pathlib import Path

from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

KICK_NOTE = 36
BPM = 132
BARS = 4
BEATS_PER_BAR = 4
TICKS_PER_BEAT = 480

OUT = Path(__file__).resolve().parents[2] / "output" / "kick_909.mid"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    mid = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    track = MidiTrack()
    mid.tracks.append(track)
    track.append(MetaMessage("set_tempo", tempo=bpm2tempo(BPM), time=0))

    note_len = TICKS_PER_BEAT  # quarter note
    for _ in range(BARS * BEATS_PER_BAR):
        track.append(Message("note_on", note=KICK_NOTE, velocity=110, time=0))
        track.append(Message("note_off", note=KICK_NOTE, velocity=0, time=note_len))

    mid.save(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
