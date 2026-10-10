"""BTC: Bi-directional Transformer for Chord recognition (Park et al., ISMIR 2019; MIT code + weights).

Model code vendored in ./btc (unchanged apart from imports); large-vocabulary checkpoint (170 classes).
Features reproduce upstream exactly: 22.05 kHz mono, CQT 144 bins / 24 per octave / hop 2048 in 10 s chunks.
"""
from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from ._util import free_gpu
from .base import Backend, Context

HERE = Path(__file__).parent / "btc"
SR, INST_LEN, N_BINS, BPO, HOP, TIMESTEP = 22050, 10.0, 144, 24, 2048, 108
ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
QUALS = ["min", "maj", "dim", "aug", "min6", "maj6", "min7", "minmaj7", "maj7", "7", "dim7", "hdim7", "sus2", "sus4"]
MODEL_CFG = {"feature_size": 144, "timestep": TIMESTEP, "num_chords": 170, "input_dropout": 0.2, "layer_dropout": 0.2,
             "attention_dropout": 0.2, "relu_dropout": 0.2, "num_layers": 8, "num_heads": 4, "hidden_size": 128,
             "total_key_depth": 128, "total_value_depth": 128, "filter_size": 128, "loss": "ce", "probs_out": False}


def idx_to_chord(i: int) -> str:
    if i == 169:
        return "N"
    if i == 168:
        return "X"
    root, q = ROOTS[i // 14], QUALS[i % 14]
    return root if i % 14 == 1 else f"{root}:{q}"


def features(y: np.ndarray) -> np.ndarray:
    step = int(SR * INST_LEN)
    chunks = [librosa.cqt(y[i:i + step], sr=SR, n_bins=N_BINS, bins_per_octave=BPO, hop_length=HOP)
              for i in range(0, len(y), step) if len(y[i:i + step]) > HOP]
    return np.log(np.abs(np.concatenate(chunks, axis=1)) + 1e-6)


class BTC(Backend):
    name = "btc"
    license = "MIT"
    weights = {"chords": 1.0}

    def available(self) -> bool:
        return (HERE / "btc_model_large_voca.pt").exists()

    def version(self) -> str:
        return "large-voca-1"

    def run(self, ctx: Context) -> dict:
        import torch
        from .btc.btc_model import BTC_model

        dev = torch.device(ctx.device)
        ck = torch.load(HERE / "btc_model_large_voca.pt", map_location="cpu", weights_only=False)
        model = BTC_model(config=MODEL_CFG).to(dev).eval()
        model.load_state_dict(ck["model"])
        y = librosa.resample(ctx.mono, orig_sr=ctx.sr, target_sr=SR)
        f = ((features(y).T - ck["mean"]) / ck["std"]).astype(np.float32)
        n = f.shape[0]
        pad = (-n) % TIMESTEP
        f = np.pad(f, ((0, pad), (0, 0)))
        x = torch.from_numpy(f).unsqueeze(0).to(dev)
        preds, conf = [], []
        with torch.no_grad():
            for t in range(f.shape[0] // TIMESTEP):
                h, _ = model.self_attn_layers(x[:, t * TIMESTEP:(t + 1) * TIMESTEP, :])
                logits = model.output_layer.output_projection(h).squeeze(0)
                p = torch.softmax(logits, dim=-1)
                m = p.max(dim=-1)
                preds += m.indices.tolist()
                conf += m.values.tolist()
        del model
        free_gpu()
        preds, conf = preds[:n], conf[:n]
        unit = INST_LEN / TIMESTEP
        out = []
        for i, (c, p) in enumerate(zip(preds, conf)):
            if out and out[-1]["_i"] == c:
                out[-1]["end"] = (i + 1) * unit
                out[-1]["_p"].append(p)
            else:
                out.append({"start": i * unit, "end": (i + 1) * unit, "_i": c, "_p": [p]})
        return {"chords": [{"start": round(s["start"], 3), "end": round(s["end"], 3), "label": idx_to_chord(s["_i"]),
                            "confidence": round(float(np.mean(s["_p"])), 3)} for s in out]}


BACKEND = BTC()
