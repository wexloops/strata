"""madmom CNN key recognition. Code BSD, models CC BY-NC-SA 4.0 (non-commercial)."""
from __future__ import annotations

import numpy as np

from .base import Backend, Context


class MadmomKey(Backend):
    name = "madmom_key"
    license = "BSD-3 / CC BY-NC-SA 4.0 (models)"
    nc = True
    optional = True
    weights = {"key": 0.9}

    def available(self) -> bool:
        try:
            import madmom  # noqa: F401
            return True
        except Exception:
            return False

    def run(self, ctx: Context) -> dict:
        from madmom.audio.signal import Signal
        from madmom.features.key import CNNKeyRecognitionProcessor, key_prediction_to_label

        p = CNNKeyRecognitionProcessor()(Signal(ctx.mono, sample_rate=ctx.sr, num_channels=1))[0]
        scores = {}
        for i, prob in enumerate(p):
            onehot = np.zeros((1, 24))
            onehot[0, i] = 1
            scores[key_prediction_to_label(onehot)] = float(prob)
        best = max(scores, key=scores.get)
        return {"label": best, "confidence": scores[best], "scores": scores}


BACKEND = MadmomKey()
