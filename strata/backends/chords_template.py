"""Beat-synchronous chroma template matching (ours, MIT). Low-weight chord baseline."""
from __future__ import annotations

import librosa
import numpy as np

from ..ensemble.categorical import NOTES
from ._util import ref_beats
from .base import Backend, Context

SR, HOP = 22050, 512
INTERVALS = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10),
             "dim": (0, 3, 6), "aug": (0, 4, 8), "sus2": (0, 2, 7), "sus4": (0, 5, 7)}
# Triads are preferred unless the 7th is clearly present.
PRIOR = {"maj": 1.0, "min": 1.0, "7": 0.93, "maj7": 0.93, "min7": 0.93, "dim": 0.85, "aug": 0.8, "sus2": 0.85, "sus4": 0.85}


def templates() -> tuple[np.ndarray, list[str]]:
    T, labels = [], []
    for r in range(12):
        for q, iv in INTERVALS.items():
            v = np.zeros(12)
            v[[(r + i) % 12 for i in iv]] = 1
            T.append(PRIOR[q] * v / np.linalg.norm(v))
            labels.append(f"{NOTES[r]}:{q}")
    return np.array(T), labels


def classify(chroma: np.ndarray, energy_floor: float = 1e-3) -> list[tuple[str, float]]:
    """chroma: (12, n) -> per-column (label, score)."""
    T, labels = templates()
    out = []
    for c in chroma.T:
        nrm = np.linalg.norm(c)
        if nrm < energy_floor:
            out.append(("N", 0.0))
            continue
        s = T @ (c / nrm)
        k = int(np.argmax(s))
        out.append((labels[k], float(s[k])))
    return out


class TemplateChords(Backend):
    name = "chords_template"
    license = "MIT"
    weights = {"chords": 0.3}
    requires = ("allin1", "demucs", "beat_this")

    def run(self, ctx: Context) -> dict:
        y = librosa.resample(ctx.harmonic(), orig_sr=ctx.sr, target_sr=SR)
        dur = len(y) / SR
        chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
        rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
        beats = [b for b in ref_beats(ctx) if b < dur] or list(np.arange(0, dur, 0.5))
        edges = [0.0] + beats + [dur]
        fr = librosa.time_to_frames(edges, sr=SR, hop_length=HOP)
        cols, quiet = [], []
        for a, b in zip(fr[:-1], fr[1:]):
            b = max(b, a + 1)
            cols.append(np.median(chroma[:, a:b], axis=1))
            quiet.append(float(rms[a:b].mean()) < 0.01 * float(rms.max() + 1e-9))
        res = classify(np.array(cols).T)
        chords = []
        for (lab, sc), q, a, b in zip(res, quiet, edges[:-1], edges[1:]):
            lab = "N" if q else lab
            if chords and chords[-1]["label"] == lab:
                chords[-1]["end"] = b
            else:
                chords.append({"start": a, "end": b, "label": lab, "confidence": round(sc, 3)})
        return {"chords": [{**c, "start": round(c["start"], 3), "end": round(c["end"], 3)} for c in chords]}


BACKEND = TemplateChords()
