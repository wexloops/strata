"""Krumhansl-Kessler key profiles on drumless chroma (ours, MIT). Global key + windowed scores."""
from __future__ import annotations

import librosa
import numpy as np

from ..ensemble.categorical import NOTES
from .base import Backend, Context

MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
SR = 22050
HOP = 2048
WIN, STEP = 12.0, 6.0
LABELS = [f"{n} major" for n in NOTES] + [f"{n} minor" for n in NOTES]


def key_scores(chroma_mean: np.ndarray, temp: float = 0.04) -> np.ndarray:
    """Softmax over the 24 profile correlations; index = LABELS order."""
    c = np.array([np.corrcoef(chroma_mean, np.roll(p, k))[0, 1] for p in (MAJOR, MINOR) for k in range(12)])
    c = np.nan_to_num(c, nan=0.0)
    e = np.exp((c - c.max()) / temp)
    return e / e.sum()


class TemplateKey(Backend):
    name = "key_template"
    license = "MIT"
    weights = {"key": 0.4}
    requires = ("allin1", "demucs")

    def run(self, ctx: Context) -> dict:
        y = librosa.resample(ctx.harmonic(), orig_sr=ctx.sr, target_sr=SR)
        chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
        fps = SR / HOP
        g = key_scores(chroma.mean(axis=1))
        windows = []
        t, dur = 0.0, chroma.shape[1] / fps
        while t < dur:
            a, b = int(t * fps), int(min(dur, t + WIN) * fps)
            if b - a > 4 and chroma[:, a:b].sum() > 0:
                windows.append({"start": round(t, 3), "end": round(min(dur, t + WIN), 3),
                                "scores": [round(float(x), 4) for x in key_scores(chroma[:, a:b].mean(axis=1))]})
            t += STEP
        k = int(np.argmax(g))
        return {"label": LABELS[k], "confidence": float(g[k]),
                "scores": {LABELS[i]: float(g[i]) for i in range(24)}, "windows": windows}


BACKEND = TemplateKey()
