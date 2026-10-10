"""strata.mid: type 1, 480 ppq. Tempo map, section markers, chord blocks, GM drums, stem notes, beats."""
from __future__ import annotations

from bisect import bisect_right
from pathlib import Path

import mido

from . import _common

PPQ = 480
DRUM_CH = 9
DRUM_NOTES = {"kick": 36, "snare": 38, "hat": 42}
BEAT_NOTE, DOWNBEAT_NOTE = 37, 76
HIT_TICKS = PPQ // 8  # 32nd-note gate for drum/beat hits
STEM_CH = {"bass": 1, "vocals": 2, "other": 3}
CHORD_CH = 0
PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
QUALITY = {
    "maj": [0, 4, 7], "min": [0, 3, 7], "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10],
    "dim": [0, 3, 6], "aug": [0, 4, 8], "sus2": [0, 2, 7], "sus4": [0, 5, 7], "N": [],
}
OCTAVE_4 = 60

# A tempo segment: (start tick, start seconds, microseconds per quarter).
Segment = tuple[int, float, int]


def _us(bpm: float) -> int:
    return mido.bpm2tempo(bpm if bpm and bpm > 0 else 120.0)


def seconds_to_ticks(t: float, segs: list[Segment], ppq: int = PPQ) -> int:
    """Integrate the tempo map: seconds -> absolute tick (nearest)."""
    if t <= 0:
        return 0
    i = max(0, bisect_right([s[1] for s in segs], t) - 1)
    tick, sec, us = segs[i]
    return tick + int(round((t - sec) * 1e6 / us * ppq))


def tempo_segments(a: dict, ppq: int = PPQ) -> list[Segment]:
    """Tempo map snapped to integer ticks; segment seconds are exact under the integer tempos."""
    tmap = sorted(a["tempo"].get("map") or [], key=lambda m: m["time"])
    segs: list[Segment] = [(0, 0.0, _us(tmap[0]["bpm"] if tmap else a["tempo"].get("bpm", 0)))]
    for m in tmap[1:]:
        us = _us(m["bpm"])
        tick = seconds_to_ticks(m["time"], segs, ppq)
        last_tick, last_sec, last_us = segs[-1]
        if us == last_us:
            continue
        if tick <= last_tick:
            segs[-1] = (last_tick, last_sec, us)
            continue
        segs.append((tick, last_sec + (tick - last_tick) * last_us / 1e6 / ppq, us))
    return segs


def _vel(x: float) -> int:
    return max(1, min(127, int(round(float(x) * 127))))


def _track(name: str, events: list[tuple[int, int, mido.Message]]) -> mido.MidiTrack:
    """events: (abs tick, priority, msg). Lower priority first at equal ticks (note_off before note_on)."""
    tr = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
    now = 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        tr.append(msg.copy(time=tick - now))
        now = tick
    tr.append(mido.MetaMessage("end_of_track", time=0))
    return tr


def _note(events: list, ch: int, pitch: int, vel: int, on: int, off: int) -> None:
    pitch = max(0, min(127, int(pitch)))
    events.append((on, 1, mido.Message("note_on", channel=ch, note=pitch, velocity=vel)))
    events.append((max(off, on + 1), 0, mido.Message("note_off", channel=ch, note=pitch, velocity=0)))


def _root(root: str | None) -> int | None:
    if not root or root[0].upper() not in PITCH_CLASS:
        return None
    pc = PITCH_CLASS[root[0].upper()] + root[1:].count("#") - root[1:].count("b")
    return pc % 12


def _tempo_track(a: dict, segs: list[Segment]) -> mido.MidiTrack:
    meter = int(a["tempo"].get("meter") or 4)
    ev = [(0, 0, mido.MetaMessage("text", text=_common.title(a))),
          (0, 0, mido.MetaMessage("time_signature", numerator=meter, denominator=4))]
    ev += [(tick, 1, mido.MetaMessage("set_tempo", tempo=us)) for tick, _, us in segs]
    return _track("tempo", ev)


def _marker_track(a: dict, segs: list[Segment]) -> mido.MidiTrack:
    ev = [(seconds_to_ticks(s["start"], segs), 0, mido.MetaMessage("marker", text=_common.clean(s["label"])))
          for s in a["sections"]]
    ev += [(seconds_to_ticks(d["time"], segs), 1, mido.MetaMessage("marker", text="drop"))
           for d in a["dynamics"]["drops"]]
    return _track("markers", ev)


def _chord_track(a: dict, segs: list[Segment]) -> mido.MidiTrack:
    ev: list = []
    for c in a["chords"]:
        root, intervals = _root(c.get("root")), QUALITY.get(c.get("quality") or "N")
        if root is None or not intervals:
            continue  # "N" (no chord) or unparseable root/quality
        on, off = seconds_to_ticks(c["start"], segs), seconds_to_ticks(c["end"], segs)
        for iv in intervals:
            _note(ev, CHORD_CH, OCTAVE_4 + root + iv, _vel(0.3 + 0.6 * c.get("confidence", 0.5)), on, off)
    return _track("chords", ev)


def _drum_track(a: dict, segs: list[Segment]) -> mido.MidiTrack:
    ev: list = []
    for kind, pitch in DRUM_NOTES.items():
        for e in a["events"].get(kind, []):
            on = seconds_to_ticks(e["time"], segs)
            _note(ev, DRUM_CH, pitch, _vel(e.get("strength", 0.8)), on, on + HIT_TICKS)
    return _track("drums", ev)


def _stem_track(a: dict, stem: str, segs: list[Segment]) -> mido.MidiTrack:
    ev: list = []
    for n in a["notes"].get(stem, []):
        _note(ev, STEM_CH[stem], n["pitch"], _vel(n.get("velocity", 0.8)),
              seconds_to_ticks(n["start"], segs), seconds_to_ticks(n["end"], segs))
    return _track(stem, ev)


def _beat_track(a: dict, segs: list[Segment]) -> mido.MidiTrack:
    ev: list = []
    for b in a["beats"]:
        on = seconds_to_ticks(b["time"], segs)
        down = bool(b.get("downbeat"))
        _note(ev, DRUM_CH, DOWNBEAT_NOTE if down else BEAT_NOTE, 110 if down else 80, on, on + HIT_TICKS)
    return _track("beats", ev)


def export_midi(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    segs = tempo_segments(a)
    mf = mido.MidiFile(type=1, ticks_per_beat=PPQ, charset="utf-8")
    mf.tracks.extend([_tempo_track(a, segs), _marker_track(a, segs), _chord_track(a, segs), _drum_track(a, segs)]
                     + [_stem_track(a, s, segs) for s in STEM_CH] + [_beat_track(a, segs)])
    p = out_dir / "strata.mid"
    mf.save(p)
    return [p]
