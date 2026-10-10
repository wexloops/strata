"""Derived layers: section energy/colors, builds, drops, accents, ranked edit cues (spec §5)."""
from __future__ import annotations

import numpy as np

from .schema import SECTION_COLORS, section_color

BUILD_MIN_RISE = 0.12
BUILD_MAX_STEP = 0.2
DROP_MIN_JUMP = 0.15
CUE_PRIORITY = {"section": 0, "drop": 1, "downbeat": 2, "accent": 3}


def _curve(a: dict, name: str) -> np.ndarray:
    return np.asarray(a["curves"]["data"].get(name, []), float)


def _mean(arr: np.ndarray, fps: int, t0: float, t1: float) -> float:
    i0, i1 = int(t0 * fps), max(int(t1 * fps), int(t0 * fps) + 1)
    seg = arr[i0:i1]
    return float(seg.mean()) if seg.size else 0.0


def _sections(a: dict, loud: np.ndarray, fps: int) -> None:
    # Energy = mean percentile rank of loudness: spreads 0..1 even on loud, compressed masters.
    rank = (np.argsort(np.argsort(loud)) / max(loud.size - 1, 1)) if loud.size and np.ptp(loud) > 0 else loud
    for s in a["sections"]:
        s["energy"] = round(_mean(rank, fps, s["start"], s["end"]), 3) if loud.size else 0.0
        lab = s["label"]
        idx = ord(lab[0]) - 65 if len(lab) == 1 and lab.isupper() else s["index"]
        s["color"] = SECTION_COLORS.get(lab) or section_color(lab, idx)


def _bar_series(a: dict, fps: int) -> tuple[list[dict], np.ndarray]:
    bars = a["bars"]
    if not bars:
        return [], np.array([])
    loud, onset, cent = _curve(a, "loudness"), _curve(a, "onset"), _curve(a, "centroid")
    comp = np.array([np.mean([_mean(c, fps, b["start"], b["end"]) for c in (loud, onset, cent) if c.size])
                     for b in bars])
    return bars, comp


def _builds(bars: list[dict], comp: np.ndarray) -> list[dict]:
    """Runs of >= 2 gradual bar-to-bar rises. A step above BUILD_MAX_STEP is a drop, not a build."""
    steps = np.diff(comp)
    rising = (steps >= 0.02) & (steps <= BUILD_MAX_STEP)
    out, i = [], 0
    while i < len(steps):
        if not rising[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(steps) and rising[j + 1]:
            j += 1
        rise = comp[j + 1] - comp[i]
        if j - i + 1 >= 2 and rise >= BUILD_MIN_RISE:
            out.append({"start": bars[i + 1]["start"], "end": bars[j + 1]["end"], "strength": round(min(1.0, rise / 0.4), 3)})
        i = j + 1
    return out


def _drops(a: dict, bars: list[dict], loud: np.ndarray, fps: int, builds: list[dict]) -> list[dict]:
    out = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        before = _mean(loud, fps, max(prev["start"], cur["start"] - 1.0), cur["start"])
        after = _mean(loud, fps, cur["start"], min(cur["end"], cur["start"] + 2.0))
        jump = after - before
        if jump < DROP_MIN_JUMP or after < 0.5:
            continue
        after_build = any(abs(b["end"] - cur["start"]) <= (cur["end"] - cur["start"]) for b in builds)
        if after_build or before < 0.15 or jump >= 0.3:
            out.append({"time": cur["start"], "strength": round(min(1.0, jump / 0.4), 3)})
    return out


def _accents(a: dict) -> list[dict]:
    onsets = a["events"]["onsets"]
    if not onsets:
        return []
    s = np.array([o["strength"] for o in onsets])
    hits = np.sort([e["time"] for k in ("kick", "snare", "hat") for e in a["events"][k]])
    if hits.size:
        thr = np.percentile(s, 90)
        return [o for o in onsets if o["strength"] >= thr and np.min(np.abs(hits - o["time"])) <= 0.05]
    thr = np.percentile(s, 95)
    return [o for o in onsets if o["strength"] >= thr]


def _cues(a: dict) -> list[dict]:
    cues = [{"time": s["start"], "type": "section", "strength": round(0.8 + 0.2 * s["confidence"], 3), "label": s["label"]}
            for s in a["sections"]]
    cues += [{"time": d["time"], "type": "drop", "strength": round(0.7 + 0.3 * d["strength"], 3), "label": "drop"}
             for d in a["dynamics"]["drops"]]
    for b in a["beats"]:
        if not b["downbeat"]:
            continue
        sec = next((s for s in a["sections"] if s["start"] <= b["time"] < s["end"]), None)
        if sec and sec["energy"] >= 0.6:
            phrase = 0.15 if (b["bar"] - 1) % 4 == 0 else 0.0
            cues.append({"time": b["time"], "type": "downbeat", "strength": round(0.4 + 0.2 * sec["energy"] + phrase, 3),
                         "label": f"bar {b['bar']}"})
    # Accents top out below 0.6 so "cues >= 0.6" means structural moments only.
    cues += [{"time": e["time"], "type": "accent", "strength": round(0.25 + 0.3 * e["strength"], 3), "label": "accent"}
             for e in a["events"]["accents"]]
    # Coincident cues collapse into one: highest-priority type, strongest strength.
    cues.sort(key=lambda c: (c["time"], CUE_PRIORITY[c["type"]]))
    out: list[dict] = []
    for c in cues:
        if out and c["time"] - out[-1]["time"] <= 0.05:
            prev = out[-1]
            prev["strength"] = max(prev["strength"], c["strength"])
            if c["type"] == "drop" and prev["type"] == "section":
                prev["label"] = f"{prev['label']} (drop)"
            continue
        out.append(dict(c))
    return out


def derive(a: dict) -> dict:
    fps = a["curves"]["fps"]
    loud = _curve(a, "loudness")
    _sections(a, loud, fps)
    bars, comp = _bar_series(a, fps)
    builds = _builds(bars, comp) if comp.size else []
    a["dynamics"]["builds"] = builds
    a["dynamics"]["drops"] = _drops(a, bars, loud, fps, builds) if loud.size and bars else []
    a["events"]["accents"] = _accents(a)
    a["cues"] = _cues(a)
    return a
