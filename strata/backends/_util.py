"""Shared helpers for backends."""
from __future__ import annotations

import gc

import numpy as np


def free_gpu() -> None:
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def norm01(x: np.ndarray, lo_pct: float = 1, hi_pct: float = 99) -> np.ndarray:
    """Percentile-clipped min-max normalization to 0..1 (flat input -> zeros)."""
    x = np.asarray(x, float)
    if x.size == 0:
        return x
    lo, hi = np.percentile(x, lo_pct), np.percentile(x, hi_pct)
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def fit_frames(x: np.ndarray, n: int) -> np.ndarray:
    """Resample a 1-D series to exactly n frames (linear)."""
    x = np.asarray(x, float)
    if x.size == n:
        return x
    if x.size == 0:
        return np.zeros(n)
    return np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x)


def ref_beats(ctx) -> list[float]:
    for name in ("beat_this", "allin1", "madmom_beats", "librosa_beats"):
        b = ctx.results.get(name, {}).get("beats")
        if b:
            return list(b)
    return []
