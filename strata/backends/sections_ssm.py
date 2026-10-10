"""Self-similarity boundaries + repetition labels (ours, MIT).

Beat-synchronous chroma + MFCC -> path-enhanced self-similarity -> checkerboard novelty -> peaks.
Segments are labeled A/B/C... by clustering their mean features, so repeats share a letter.
"""
from __future__ import annotations

import librosa
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.signal import find_peaks

from ._util import ref_beats
from .base import Backend, Context

SR = 22050
HOP = 512
KERNEL = 16  # beats


def _checkerboard(n: int) -> np.ndarray:
    half = n // 2
    g = np.exp(-0.5 * (np.linspace(-2, 2, n) ** 2))
    k = np.outer(g, g)
    sign = np.ones((n, n))
    sign[:half, half:] = -1
    sign[half:, :half] = -1
    return k * sign


def novelty(S: np.ndarray, size: int = KERNEL) -> np.ndarray:
    k = _checkerboard(size)
    half = size // 2
    P = np.pad(S, half, mode="edge")
    return np.array([np.sum(P[i:i + size, i:i + size] * k) for i in range(S.shape[0])])


class SSMSections(Backend):
    name = "ssm"
    license = "MIT"
    weights = {"sections": 0.4}
    requires = ("beat_this", "librosa_beats")

    def version(self) -> str:
        return "2"

    def run(self, ctx: Context) -> dict:
        beats = ref_beats(ctx)
        y = librosa.resample(ctx.mono, orig_sr=ctx.sr, target_sr=SR)
        if len(beats) < KERNEL * 2:
            return {"boundaries": [], "labels": []}
        chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
        mfcc = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13, hop_length=HOP)
        frames = librosa.time_to_frames(beats, sr=SR, hop_length=HOP)
        frames = np.unique(np.clip(frames, 0, chroma.shape[1] - 1))
        X = np.vstack([
            librosa.util.normalize(librosa.util.sync(chroma, frames, aggregate=np.median), axis=0),
            librosa.util.normalize(librosa.util.sync(mfcc[1:], frames, aggregate=np.mean), axis=0),
        ])
        Xn = X / (np.linalg.norm(X, axis=0, keepdims=True) + 1e-9)
        S = Xn.T @ Xn
        S = librosa.segment.path_enhance(S, 9)
        nov = novelty(S)
        nov = (nov - nov.min()) / (np.ptp(nov) + 1e-9)
        peaks, _ = find_peaks(nov, distance=8, height=np.mean(nov) + 0.5 * np.std(nov))
        bt = librosa.frames_to_time(frames, sr=SR, hop_length=HOP)
        bidx = [0] + [int(p) for p in peaks if 4 <= p <= len(bt) - 4] + [len(bt)]
        feats = np.array([X[:, a:b].mean(axis=1) for a, b in zip(bidx[:-1], bidx[1:])])
        if len(feats) > 1:
            cl = fcluster(linkage(feats, method="average", metric="cosine"), t=0.12, criterion="distance")
        else:
            cl = np.array([1])
        letters, labels = {}, []
        for c in cl:
            letters.setdefault(c, chr(65 + len(letters) % 26))
            labels.append(letters[c])
        return {"boundaries": [float(bt[i]) for i in bidx[1:-1]], "labels": labels}


BACKEND = SSMSections()
