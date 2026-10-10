"""S-KEY (Deezer, ICASSP 2025; MIT code + weights). Self-supervised key estimation."""
from __future__ import annotations

from ._util import free_gpu
from .base import Backend, Context


class SKey(Backend):
    name = "skey"
    license = "MIT"
    weights = {"key": 1.0}

    def available(self) -> bool:
        try:
            import skey.key_detection  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        return "skey-icassp25"

    def run(self, ctx: Context) -> dict:
        import torch
        import torchaudio
        from skey.key_detection import key_map, load_checkpoint, load_model_components

        dev = torch.device(ctx.device)
        ckpt = load_checkpoint()
        sr = ckpt["audio"]["sr"]
        hcqt, chromanet, crop = load_model_components(ckpt, dev)
        x = torch.from_numpy(ctx.mono[None, :]).float()
        x = torchaudio.functional.resample(x, ctx.sr, sr)
        x = x / (x.abs().max() + 1e-9)
        with torch.no_grad():
            # ChromaNet's head already ends in a softmax: rows are key probabilities.
            p = chromanet(crop(hcqt(x.unsqueeze(0).to(dev)), torch.zeros(1).to(dev))).mean(dim=0).cpu().numpy()
        del hcqt, chromanet
        free_gpu()
        scores = {}
        for i, prob in enumerate(p):
            tonic, mode = key_map[i].split()
            scores[f"{tonic} {mode.lower()}"] = scores.get(f"{tonic} {mode.lower()}", 0.0) + float(prob)
        best = max(scores, key=scores.get)
        return {"label": best, "confidence": float(scores[best]), "scores": scores}


BACKEND = SKey()
