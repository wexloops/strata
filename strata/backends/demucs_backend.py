"""htdemucs stems (MIT). Fallback only: allin1 already separates when it runs."""
from __future__ import annotations

from pathlib import Path

import soundfile as sf

from ._util import free_gpu
from .base import Backend, Context


class Demucs(Backend):
    name = "demucs"
    license = "MIT"
    weights = {"stems": 1.0}
    requires = ("allin1",)

    def available(self) -> bool:
        try:
            import demucs.api  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        return "htdemucs-1"

    def run(self, ctx: Context) -> dict:
        if all(k in ctx.stems for k in ("drums", "bass", "vocals", "other")):
            return {"stems": {k: str(v) for k, v in ctx.stems.items()}, "note": "reused allin1 separation"}
        import torch
        from demucs.api import Separator

        sep = Separator(model="htdemucs", device=ctx.device)
        _, stems = sep.separate_tensor(torch.from_numpy(ctx.audio if ctx.audio.shape[0] == 2 else ctx.audio.repeat(2, 0)), ctx.sr)
        out = ctx.lib.stems_dir(ctx.track["id"])
        paths = {}
        for name, t in stems.items():
            dst = out / f"{name}.flac"
            sf.write(str(dst), t.cpu().numpy().T, sep.samplerate, subtype="PCM_16")
            paths[name] = str(dst)
        del sep
        free_gpu()
        self.restore(ctx, {"stems": paths})
        return {"stems": paths}

    def restore(self, ctx: Context, data: dict) -> None:
        for k, v in (data.get("stems") or {}).items():
            if Path(v).exists():
                ctx.stems.setdefault(k, Path(v))


BACKEND = Demucs()
