"""Key and chord voting over a shared vocabulary."""
from __future__ import annotations

import re

import numpy as np

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ENHARMONIC = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E", "E#": "F", "B#": "C"}
QUALITIES = ["maj", "min", "7", "maj7", "min7", "dim", "aug", "sus2", "sus4", "N"]
_QMAP = {
    "": "maj", "maj": "maj", "M": "maj", "maj6": "maj", "6": "maj", "add9": "maj",
    "min": "min", "m": "min", "min6": "min", "m6": "min", "minmaj7": "min",
    "7": "7", "9": "7", "11": "7", "13": "7", "dom7": "7",
    "maj7": "maj7", "M7": "maj7", "maj9": "maj7",
    "min7": "min7", "m7": "min7", "min9": "min7", "min11": "min7",
    "dim": "dim", "dim7": "dim", "hdim7": "dim", "m7b5": "dim", "o": "dim",
    "aug": "aug", "+": "aug", "sus2": "sus2", "sus4": "sus4", "sus": "sus4", "7sus4": "sus4",
}
# Camelot wheel: (tonic, mode) -> code
_CAMELOT_MAJ = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
_CAMELOT_MIN = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]


def norm_root(r: str) -> str | None:
    r = r.strip()
    if not r:
        return None
    r = r[0].upper() + r[1:]
    r = _ENHARMONIC.get(r, r)
    return r if r in NOTES else None


def normalize_chord(label: str) -> tuple[str | None, str]:
    label = (label or "N").strip()
    if label in ("N", "X", "") or label.startswith("N"):
        return None, "N"
    label = label.split("/")[0]
    label = re.sub(r"\(.*\)", "", label)
    if ":" in label:
        root, q = label.split(":", 1)
    else:
        m = re.match(r"^([A-Ga-g][#b]?)(.*)$", label)
        if not m:
            return None, "N"
        root, q = m.group(1), m.group(2)
    r = norm_root(root)
    if r is None:
        return None, "N"
    return r, _QMAP.get(q, "maj" if q.startswith("maj") else "min" if q.startswith("min") else "7" if q[:1].isdigit() else "maj")


def chord_name(root: str | None, quality: str) -> str:
    if root is None or quality == "N":
        return "N"
    return root + {"maj": "", "min": "m"}.get(quality, quality)


def parse_key(label: str) -> tuple[str | None, str | None]:
    if not label:
        return None, None
    s = label.replace(":", " ").strip()
    parts = s.split()
    root = norm_root(parts[0])
    mode = parts[1].lower() if len(parts) > 1 else ("minor" if parts[0][0].islower() else "major")
    mode = "minor" if mode.startswith("min") else "major"
    return root, mode


def camelot(tonic: str | None, mode: str | None) -> str | None:
    if tonic is None:
        return None
    i = NOTES.index(tonic)
    return (_CAMELOT_MIN if mode == "minor" else _CAMELOT_MAJ)[i]


def key_label(tonic: str | None, mode: str | None) -> str | None:
    return f"{tonic} {mode}" if tonic else None


def vote_key(cands: dict[str, dict], weights: dict[str, float]) -> dict:
    scores: dict[str, float] = {}
    votes = {}
    for k, c in cands.items():
        if not c.get("label"):
            continue
        w = weights.get(k, 0.5)
        tonic, mode = parse_key(c["label"])
        lab = key_label(tonic, mode)
        if lab is None:
            continue
        votes[k] = {"label": lab, "confidence": round(float(c.get("confidence", 1.0)), 3)}
        if c.get("scores"):
            for sl, p in c["scores"].items():
                t2, m2 = parse_key(sl)
                l2 = key_label(t2, m2)
                if l2:
                    scores[l2] = scores.get(l2, 0) + w * float(p)
        else:
            scores[lab] = scores.get(lab, 0) + w * float(c.get("confidence", 1.0))
    if not scores:
        return {"label": None, "tonic": None, "mode": None, "camelot": None, "confidence": 0.0, "votes": votes}
    best = max(scores, key=scores.get)
    tonic, mode = parse_key(best)
    total_w = sum(weights.get(k, 0.5) for k in votes)
    return {"label": best, "tonic": tonic, "mode": mode, "camelot": camelot(tonic, mode),
            "confidence": round(min(1.0, scores[best] / total_w), 3), "votes": votes}


def _label_at(chords: list[dict], a: float, b: float) -> str | None:
    best, ov_best = None, 0.0
    for c in chords:
        ov = min(b, c["end"]) - max(a, c["start"])
        if ov > ov_best:
            best, ov_best = c["label"], ov
    return best


def vote_chords(cands: dict[str, dict], weights: dict[str, float], beats: list[dict], duration: float) -> list[dict]:
    cands = {k: v for k, v in cands.items() if v.get("chords")}
    if not cands:
        return []
    if len(beats) >= 2:
        grid = [b["time"] for b in beats]
        grid = ([0.0] if grid[0] > 0.05 else []) + grid + ([duration] if grid[-1] < duration - 0.05 else [])
    else:
        grid = list(np.arange(0, duration, 0.5)) + [duration]
    order = sorted(cands, key=lambda k: -weights.get(k, 0.5))
    cells = []
    for a, b in zip(grid[:-1], grid[1:]):
        tally: dict[tuple, float] = {}
        full: dict[tuple, str] = {}
        for k in order:
            lab = _label_at(cands[k]["chords"], a, b)
            if lab is None:
                continue
            key = normalize_chord(lab)
            tally[key] = tally.get(key, 0) + weights.get(k, 0.5)
            full.setdefault(key, lab)
        if not tally:
            cells.append((a, b, (None, "N"), "N", 0.0))
            continue
        win = max(tally, key=tally.get)
        cells.append((a, b, win, full[win], tally[win] / sum(tally.values())))
    out: list[dict] = []
    for a, b, key, lab, conf in cells:
        if out and (out[-1]["root"], out[-1]["quality"]) == key:
            out[-1]["end"] = b
            out[-1]["_c"].append(conf)
            continue
        out.append({"start": a, "end": b, "label": chord_name(*key), "label_full": lab,
                    "root": key[0], "quality": key[1], "_c": [conf]})
    for c in out:
        c["confidence"] = round(float(np.mean(c.pop("_c"))), 3)
        c["start"], c["end"] = round(float(c["start"]), 3), round(float(c["end"]), 3)
    return out
