"""madmom CNN features + CRF chord recognition. Code BSD, models CC BY-NC-SA 4.0 (non-commercial)."""
from __future__ import annotations

from .base import Backend, Context


class MadmomChords(Backend):
    name = "madmom_chords"
    license = "BSD-3 / CC BY-NC-SA 4.0 (models)"
    nc = True
    optional = True
    weights = {"chords": 0.8}

    def available(self) -> bool:
        try:
            import madmom  # noqa: F401
            return True
        except Exception:
            return False

    def run(self, ctx: Context) -> dict:
        from madmom.audio.signal import Signal
        from madmom.features.chords import CNNChordFeatureProcessor, CRFChordRecognitionProcessor

        feats = CNNChordFeatureProcessor()(Signal(ctx.mono, sample_rate=ctx.sr, num_channels=1))
        res = CRFChordRecognitionProcessor()(feats)
        return {"chords": [{"start": float(s), "end": float(e), "label": str(l)} for s, e, l in res]}


BACKEND = MadmomChords()
