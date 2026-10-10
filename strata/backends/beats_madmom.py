"""madmom RNN + DBN downbeat tracker. Code BSD, model files CC BY-NC-SA 4.0 (non-commercial)."""
from __future__ import annotations

from .base import Backend, Context


class MadmomBeats(Backend):
    name = "madmom_beats"
    license = "BSD-3 / CC BY-NC-SA 4.0 (models)"
    nc = True
    optional = True
    weights = {"beats": 0.8}

    def available(self) -> bool:
        try:
            import madmom  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        import madmom
        return madmom.__version__

    def run(self, ctx: Context) -> dict:
        from madmom.audio.signal import Signal
        from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor

        sig = Signal(ctx.mono, sample_rate=ctx.sr, num_channels=1)
        act = RNNDownBeatProcessor()(sig)
        res = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)(act)
        return {"beats": [float(t) for t, _ in res], "downbeats": [float(t) for t, p in res if int(p) == 1]}


BACKEND = MadmomBeats()
