"""Beat This! (CPJKU, MIT code + weights). Reference beat grid."""
from __future__ import annotations

from ._util import free_gpu
from .base import Backend, Context


class BeatThis(Backend):
    name = "beat_this"
    license = "MIT"
    weights = {"beats": 1.0}

    def available(self) -> bool:
        try:
            import beat_this.inference  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        return "final0"

    def run(self, ctx: Context) -> dict:
        from beat_this.inference import Audio2Beats

        a2b = Audio2Beats(checkpoint_path="final0", device=ctx.device, dbn=False)
        beats, downbeats = a2b(ctx.mono, ctx.sr)
        del a2b
        free_gpu()
        return {"beats": [float(t) for t in beats], "downbeats": [float(t) for t in downbeats]}


BACKEND = BeatThis()
