"""LAION CLAP zero-shot tags (CC0 code; laion/larger_clap_music weights Apache-2.0). Extra: strata[tags]."""
from __future__ import annotations

import os

import librosa
import numpy as np

from ._util import free_gpu
from .base import Backend, Context
from .tag_labels import GENRES, INSTRUMENTS, MOODS, PROMPTS

MODEL = "laion/larger_clap_music"
SR, WIN = 48000, 10.0
TOP = 5


class ClapTags(Backend):
    name = "tags_clap"
    license = "CC0 / Apache-2.0 (weights)"
    optional = True
    weights = {"tags": 1.0}

    # Disabled by default: on this stack (torch 2.11, transformers 4.57 and 5.x alike) the CLAP
    # text tower returns near-identical embeddings for every prompt, so every tag ties.
    unavailable_reason = "disabled: CLAP text embeddings collapse on this stack (set STRATA_ENABLE_CLAP=1 to retry)"

    def available(self) -> bool:
        if os.environ.get("STRATA_ENABLE_CLAP") != "1":
            return False
        try:
            import transformers  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        return "larger_clap_music-2"

    def run(self, ctx: Context) -> dict:
        import torch
        from transformers import ClapModel, ClapProcessor

        dev = ctx.device
        model = ClapModel.from_pretrained(MODEL).to(dev).eval()
        proc = ClapProcessor.from_pretrained(MODEL)
        y = librosa.resample(ctx.mono, orig_sr=ctx.sr, target_sr=SR)
        step = int(WIN * SR)
        starts = list(range(0, max(len(y) - step // 2, 1), step))
        clips = [y[s:s + step] for s in starts]
        vocab = {"genre": GENRES, "mood": MOODS, "instruments": INSTRUMENTS}
        with torch.no_grad():
            probs = {}
            for cat, labels in vocab.items():
                text = proc(text=[PROMPTS[cat].format(l) for l in labels], return_tensors="pt", padding=True)
                rows = []
                for i in range(0, len(clips), 8):
                    aud = proc(audio=clips[i:i + 8], sampling_rate=SR, return_tensors="pt")
                    out = model(input_ids=text["input_ids"].to(dev), attention_mask=text["attention_mask"].to(dev),
                                input_features=aud["input_features"].to(dev),
                                is_longer=aud.get("is_longer", None) if aud.get("is_longer", None) is None else aud["is_longer"].to(dev))
                    rows.append(torch.softmax(out.logits_per_audio, dim=-1))
                probs[cat] = torch.cat(rows).cpu().numpy()
        del model
        free_gpu()
        out = {}
        for cat, labels in vocab.items():
            g = probs[cat].mean(axis=0)
            out[cat] = [{"label": labels[i], "score": round(float(g[i]), 3)} for i in np.argsort(-g)[:TOP]]
        out["labels"] = MOODS
        out["windows"] = [{"start": round(s / SR, 3), "end": round(min(len(y), s + step) / SR, 3),
                           "scores": [round(float(v), 4) for v in probs["mood"][i]]} for i, s in enumerate(starts)]
        return out


BACKEND = ClapTags()
