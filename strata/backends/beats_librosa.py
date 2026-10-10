"""librosa dynamic-programming beat tracker (ISC). Low-weight DSP baseline."""
from __future__ import annotations

import librosa

from .base import Backend, Context


class LibrosaBeats(Backend):
    name = "librosa_beats"
    license = "ISC"
    weights = {"beats": 0.3}

    def run(self, ctx: Context) -> dict:
        y = librosa.resample(ctx.mono, orig_sr=ctx.sr, target_sr=22050)
        _, beats = librosa.beat.beat_track(y=y, sr=22050, units="time")
        return {"beats": [float(t) for t in beats], "downbeats": []}


BACKEND = LibrosaBeats()
