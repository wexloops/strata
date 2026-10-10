"""Where the singing is: vocal-stem RMS gate (ours, MIT)."""
from __future__ import annotations

import librosa
import numpy as np

from .base import Backend, Context

HOP = 1024
MERGE_GAP, MIN_LEN = 0.3, 0.25


class VocalActivity(Backend):
    name = "vocals_activity"
    license = "MIT"
    weights = {"vocals": 1.0}
    requires = ("allin1", "demucs")

    def run(self, ctx: Context) -> dict:
        y = ctx.stem("vocals")
        if y is None:
            return {"activity": []}
        r = librosa.feature.rms(y=y, frame_length=HOP * 2, hop_length=HOP)[0]
        if r.max() <= 0:
            return {"activity": []}
        on = (20 * np.log10(r + 1e-9) > -40) & (r > 0.15 * r.max())
        t = librosa.frames_to_time(np.arange(len(r)), sr=ctx.sr, hop_length=HOP)
        segs, start = [], None
        for i, v in enumerate(np.append(on, False)):
            if v and start is None:
                start = t[i]
            elif not v and start is not None:
                segs.append([float(start), float(t[min(i, len(t) - 1)])])
                start = None
        merged = []
        for s in segs:
            if merged and s[0] - merged[-1][1] <= MERGE_GAP:
                merged[-1][1] = s[1]
            else:
                merged.append(s)
        return {"activity": [{"start": round(a, 3), "end": round(b, 3)} for a, b in merged if b - a >= MIN_LEN]}


BACKEND = VocalActivity()
