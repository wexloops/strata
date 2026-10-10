"""Build tests/fixtures/sample_analysis.json: schema-valid, every layer populated.

Fully synthetic (no third-party music): a 115 BPM, 176 s song form with every layer populated.
Deterministic (seeded).
"""
import json
import math
from pathlib import Path

import numpy as np

from strata import schema

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
rng = np.random.default_rng(7)

BEAT0, IBI = 0.29, 60 / 115
SEGMENTS = [(0.0, 17.0, "intro"), (17.0, 41.9, "verse"), (41.9, 62.5, "chorus"), (62.5, 89.0, "chorus"),
            (89.0, 103.6, "verse"), (103.6, 120.1, "bridge"), (120.1, 136.5, "chorus"), (136.5, 156.6, "chorus"),
            (156.6, 176.0, "outro")]
n_beats = int((176.0 - BEAT0) / IBI)
a1 = {"beats": [round(BEAT0 + i * IBI, 3) for i in range(n_beats)],
      "beat_positions": [(i % 4) + 1 for i in range(n_beats)],
      "segments": [{"start": s0, "end": s1, "label": lab} for s0, s1, lab in SEGMENTS]}
duration = 176.0
track = {"title": "STRATA fixture Ñandú \"test\"", "path": "examples/demo/axys-signal-without-state.mp3",
         "id": "f17a0e0000000001", "duration": duration, "sample_rate": 44100, "channels": 2}
a = schema.empty_analysis(track, "full", 30)
a["provenance"] = [
    {"backend": b, "dimension": d, "version": "fixture", "license": l, "nc": nc, "ok": True, "error": None, "seconds": 1.0}
    for b, d, l, nc in [("allin1", "beats", "MIT", False), ("beat_this", "beats", "MIT", False),
                        ("librosa_beats", "beats", "ISC", False), ("madmom_beats", "beats", "BSD/CC BY-NC-SA", True),
                        ("ssm", "sections", "MIT", False), ("skey", "key", "MIT", False), ("btc", "chords", "MIT", False)]
]
beats_t = a1["beats"]
pos = a1["beat_positions"] or [(i % 4) + 1 for i in range(len(beats_t))]
bar = 0
for t, p in zip(beats_t, pos):
    if p == 1:
        bar += 1
    votes = {"beat_this": True, "allin1": True, "librosa_beats": bool(rng.random() > 0.2), "madmom_beats": bool(rng.random() > 0.1)}
    a["beats"].append({"time": t, "bar": max(bar, 1), "beat": p, "downbeat": p == 1,
                       "confidence": round(sum(votes.values()) / 4, 3), "votes": votes})
downs = [b["time"] for b in a["beats"] if b["downbeat"]]
for i, t in enumerate(downs):
    a["bars"].append({"index": i + 1, "start": t, "end": downs[i + 1] if i + 1 < len(downs) else duration})
a["tempo"].update({"bpm": 115.0, "confidence": 0.93, "stable": True, "meter": 4,
                   "alternatives": [{"bpm": 57.5, "support": 0.1}],
                   "map": [{"time": round(t, 3), "bpm": round(115 + 2 * math.sin(t / 20), 2)} for t in downs]})
segs = [s for s in a1["segments"] if s["label"] not in ("start", "end")] or [
    {"start": 0, "end": 17, "label": "intro"}, {"start": 17, "end": 42, "label": "verse"},
    {"start": 42, "end": 89, "label": "chorus"}, {"start": 89, "end": 176, "label": "outro"}]
for i, s in enumerate(segs):
    a["sections"].append({"index": i, "start": s["start"], "end": s["end"], "label": s["label"],
                          "confidence": round(0.6 + 0.4 * rng.random(), 3), "energy": round(0.3 + 0.6 * rng.random(), 3),
                          "color": schema.section_color(s["label"], i), "key": "E major",
                          "tags": ["warm", "baroque pop"], "votes": {"allin1": 0.6, "ssm": round(0.4 * rng.random(), 3)}})
a["key"] = {"label": "E major", "tonic": "E", "mode": "major", "camelot": "12B", "confidence": 0.81,
            "votes": {"skey": {"label": "E major", "confidence": 0.84}, "template": {"label": "A major", "confidence": 0.41}}}
prog = [("E", "maj"), ("C#", "min"), ("A", "maj"), ("B", "7"), ("F#", "min7"), ("E", "maj7")]
t, i = 0.3, 0
while t < duration - 2:
    r, q = prog[i % len(prog)]
    d = 2.088 * (1 + (i % 2))
    lab = r if q == "maj" else (r + "m" if q == "min" else r + q)
    a["chords"].append({"start": round(t, 3), "end": round(min(t + d, duration), 3), "label": lab,
                        "label_full": f"{r}:{q}", "root": r, "quality": q, "confidence": round(0.5 + 0.5 * rng.random(), 3)})
    t += d
    i += 1
for b in a["beats"]:
    if b["beat"] in (1, 3):
        a["events"]["kick"].append({"time": b["time"], "strength": round(0.5 + 0.5 * rng.random(), 3)})
    else:
        a["events"]["snare"].append({"time": b["time"], "strength": round(0.4 + 0.5 * rng.random(), 3)})
    a["events"]["hat"].append({"time": round(b["time"] + 0.26, 3), "strength": round(0.2 + 0.3 * rng.random(), 3)})
    a["events"]["onsets"].append({"time": b["time"], "strength": round(rng.random(), 3)})
a["events"]["hat"] = [h for h in a["events"]["hat"] if h["time"] < duration]
a["events"]["accents"] = [o for o in a["events"]["onsets"] if o["strength"] > 0.92]
for stem, lo in (("bass", 28), ("vocals", 60), ("other", 52)):
    t = 1.0
    while t < duration - 1:
        dur = float(rng.choice([0.26, 0.52, 1.04]))
        a["notes"][stem].append({"start": round(t, 3), "end": round(t + dur * 0.9, 3),
                                 "pitch": int(lo + rng.integers(0, 14)), "velocity": round(0.4 + 0.6 * rng.random(), 3)})
        t += dur
a["dynamics"].update({"lufs": -12.4, "lra": 6.1, "peak_db": -0.3,
                      "builds": [{"start": 33.0, "end": 41.9, "strength": 0.62}],
                      "drops": [{"time": 41.9, "strength": 0.71}, {"time": 120.11, "strength": 0.55}],
                      "silences": [{"start": 175.2, "end": 176.0}]})
a["vocals"]["activity"] = [{"start": 17.2, "end": 40.5}, {"start": 42.0, "end": 88.0}, {"start": 103.0, "end": 170.0}]
a["vocals"]["lyrics"] = [{"start": 17.4, "end": 19.8, "text": "signal in the static, hold the line"},
                         {"start": 20.5, "end": 23.9, "text": "every layer folding into time"}]
a["tags"] = {"genre": [{"label": "baroque pop", "score": 0.61}, {"label": "psychedelic pop", "score": 0.22}],
             "mood": [{"label": "tender", "score": 0.55}, {"label": "euphoric", "score": 0.2}],
             "instruments": [{"label": "french horn", "score": 0.4}, {"label": "harpsichord", "score": 0.3}]}
n = schema.n_frames(duration, 30)
tt = np.arange(n) / 30
env = np.interp(tt, [s["start"] for s in a["sections"]] + [duration], [s["energy"] for s in a["sections"]] + [0.2])
data = {}
for name in schema.CURVE_NAMES:
    base = env * (0.7 + 0.3 * np.sin(tt * (1 + len(name) % 5)))
    if name in ("kick", "snare", "hat", "onset", "flux"):
        evs = a["events"]["kick" if name in ("kick", "onset", "flux") else ("snare" if name == "snare" else "hat")]
        base = np.zeros(n)
        for e in evs:
            k = int(e["time"] * 30)
            base[k:k + 6] = np.maximum(base[k:k + 6], e["strength"] * np.exp(-np.arange(len(base[k:k + 6])) / 2))
    data[name] = np.clip(base + 0.03 * rng.random(n), 0, 1).tolist()
a["curves"]["data"] = data
cues = [{"time": s["start"], "type": "section", "strength": 0.9, "label": s["label"]} for s in a["sections"]]
cues += [{"time": d["time"], "type": "drop", "strength": d["strength"], "label": "drop"} for d in a["dynamics"]["drops"]]
cues += [{"time": b["time"], "type": "downbeat", "strength": 0.4, "label": f"bar {b['bar']}"} for b in a["beats"] if b["downbeat"]]
a["cues"] = sorted(cues, key=lambda c: c["time"])
schema.round_floats(a)
errs = schema.validate(a)
assert not errs, errs
(HERE / "sample_analysis.json").write_text(json.dumps(a, ensure_ascii=False))
print("ok", len(a["beats"]), "beats", len(a["sections"]), "sections")
