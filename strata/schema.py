"""Canonical analysis.json shape (schema 1). Everything downstream reads only this."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

from . import __version__

SCHEMA_VERSION = 1

SECTION_COLORS = {
    "intro": "#5B6CFF",
    "verse": "#2EC4B6",
    "pre-chorus": "#9BE564",
    "chorus": "#FF3D7F",
    "drop": "#FF2A2A",
    "build": "#FFB627",
    "bridge": "#B45CFF",
    "break": "#00B8FF",
    "inst": "#00B8FF",
    "solo": "#00B8FF",
    "outro": "#7A7AA8",
    "start": "#2A2A33",
    "end": "#2A2A33",
    "silence": "#2A2A33",
}
# Unlabeled (repetition-cluster) sections cycle through these.
CLUSTER_COLORS = ["#5B6CFF", "#2EC4B6", "#FF3D7F", "#B45CFF", "#FFB627", "#00B8FF", "#9BE564", "#7A7AA8"]

STEM_COLORS = {"drums": "#FF7A1A", "bass": "#8B5CFF", "vocals": "#7DF9FF", "other": "#F5F5F0"}

CURVE_NAMES = [
    "loudness", "rms", "rms_drums", "rms_bass", "rms_vocals", "rms_other",
    "kick", "snare", "hat", "onset", "centroid", "flux",
] + [f"band_{i}" for i in range(8)]

REQUIRED_KEYS = [
    "strata", "track", "provenance", "tempo", "beats", "bars", "sections", "key", "chords",
    "events", "notes", "dynamics", "vocals", "tags", "cues", "curves",
]
EVENT_KINDS = ["kick", "snare", "hat", "onsets", "accents"]
NOTE_STEMS = ["bass", "vocals", "other"]


def section_color(label: str, index: int = 0) -> str:
    if label in SECTION_COLORS:
        return SECTION_COLORS[label]
    return CLUSTER_COLORS[index % len(CLUSTER_COLORS)]


def n_frames(duration: float, fps: int) -> int:
    return int(math.ceil(duration * fps))


def empty_analysis(track: dict, profile: str, fps: int) -> dict:
    n = n_frames(track["duration"], fps)
    return {
        "strata": {
            "version": __version__,
            "schema": SCHEMA_VERSION,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "profile": profile,
        },
        "track": dict(track),
        "provenance": [],
        "tempo": {"bpm": 0.0, "confidence": 0.0, "stable": False, "meter": 4, "alternatives": [], "map": []},
        "beats": [],
        "bars": [],
        "sections": [],
        "key": {"label": None, "tonic": None, "mode": None, "camelot": None, "confidence": 0.0, "votes": {}},
        "chords": [],
        "events": {k: [] for k in EVENT_KINDS},
        "notes": {k: [] for k in NOTE_STEMS},
        "dynamics": {"lufs": None, "lra": None, "peak_db": None, "builds": [], "drops": [], "silences": []},
        "vocals": {"activity": [], "lyrics": []},
        "tags": {"genre": [], "mood": [], "instruments": []},
        "cues": [],
        "curves": {"fps": fps, "names": list(CURVE_NAMES), "data": {k: [0.0] * n for k in CURVE_NAMES}},
    }


def _sorted(items, key) -> bool:
    vals = [it.get(key, 0) for it in items]
    return all(a <= b for a, b in zip(vals, vals[1:]))


def validate(d: dict) -> list[str]:
    errs: list[str] = []
    for k in REQUIRED_KEYS:
        if k not in d:
            errs.append(f"missing key: {k}")
    if errs:
        return errs
    if d["strata"].get("schema") != SCHEMA_VERSION:
        errs.append(f"strata.schema must be {SCHEMA_VERSION}")
    for name, key in (("beats", "time"), ("bars", "start"), ("sections", "start"), ("chords", "start"), ("cues", "time")):
        if not isinstance(d[name], list):
            errs.append(f"{name} must be a list")
        elif not _sorted(d[name], key):
            errs.append(f"{name} not sorted by {key}")
    for k, v in d["events"].items():
        if not _sorted(v, "time"):
            errs.append(f"events.{k} not sorted by time")
    for k, v in d["notes"].items():
        if not _sorted(v, "start"):
            errs.append(f"notes.{k} not sorted by start")
    curves = d["curves"]
    n = n_frames(d["track"]["duration"], curves["fps"])
    for name in curves["names"]:
        arr = curves["data"].get(name)
        if arr is None:
            errs.append(f"curve {name} missing")
        elif abs(len(arr) - n) > 1:
            errs.append(f"curve {name} has {len(arr)} frames, expected {n}")
    return errs


def _builtin(v):
    return v.item() if isinstance(v, np.generic) else v


def round_floats(obj, nd: int = 3, curve_nd: int = 4):
    """Round in place: times/values to 3 dp, curve samples to 4 dp. Also turns numpy scalars into builtins."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            v = obj[k] = _builtin(v)
            if k == "curves" and isinstance(v, dict) and "data" in v:
                v["data"] = {n: [round(float(x), curve_nd) for x in arr] for n, arr in v["data"].items()}
            elif isinstance(v, float):
                obj[k] = round(v, nd)
            else:
                round_floats(v, nd, curve_nd)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            v = obj[i] = _builtin(v)
            if isinstance(v, float):
                obj[i] = round(v, nd)
            else:
                round_floats(v, nd, curve_nd)
    return obj
