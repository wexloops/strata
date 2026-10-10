"""All-In-One (mir-aidj/all-in-one, MIT code + weights; vendored PR #39 runs NA in plain torch).

Also owns stem separation: its htdemucs pass is kept and converted to FLAC stems for every
downstream backend, so the track is separated once.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import soundfile as sf

from ._util import free_gpu
from .base import Backend, Context

STEMS = ("drums", "bass", "vocals", "other")


class Allin1(Backend):
    name = "allin1"
    license = "MIT"
    weights = {"beats": 0.8, "sections": 0.6}

    unavailable_reason: str | None = None

    def available(self) -> bool:
        try:
            import allin1  # noqa: F401
            return True
        except Exception as e:  # surface the real cause in provenance / doctor
            self.unavailable_reason = f"import failed: {type(e).__name__}: {e}"
            return False

    def version(self) -> str:
        return "1.1.0-pr39"

    def run(self, ctx: Context) -> dict:
        import allin1

        work = ctx.lib.track_dir(ctx.track["id"]) / "allin1"
        work.mkdir(exist_ok=True)
        src = work / f"track{ctx.path.suffix.lower()}"
        if src.exists() or src.is_symlink():
            src.unlink()
        try:
            os.symlink(ctx.path.resolve(), src)
        except OSError:
            shutil.copy(ctx.path, src)
        r = allin1.analyze(str(src), demix_dir=str(work / "demix"), spec_dir=str(work / "spec"),
                           keep_byproducts=True, device=ctx.device, multiprocess=False)
        stems = {}
        demixed = work / "demix" / "htdemucs" / "track"
        out = ctx.lib.stems_dir(ctx.track["id"])
        for s in STEMS:
            wav = demixed / f"{s}.wav"
            if wav.exists():
                y, sr = sf.read(str(wav))
                dst = out / f"{s}.flac"
                sf.write(str(dst), y, sr, subtype="PCM_16")
                stems[s] = str(dst)
        shutil.rmtree(work, ignore_errors=True)
        free_gpu()
        self.restore(ctx, {"stems": stems})
        return {
            "beats": [float(t) for t in r.beats],
            "downbeats": [float(t) for t in r.downbeats],
            "segments": [{"start": float(s.start), "end": float(s.end), "label": s.label} for s in r.segments],
            "bpm": float(r.bpm) if r.bpm else 0.0,
            "stems": stems,
        }

    def restore(self, ctx: Context, data: dict) -> None:
        for k, v in (data.get("stems") or {}).items():
            if Path(v).exists():
                ctx.stems[k] = Path(v)


BACKEND = Allin1()
