from __future__ import annotations

import hashlib
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

SR = 44100


def file_id(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load(path: str | Path, sr: int = SR, mono: bool = False) -> tuple[np.ndarray, int]:
    """Return float32 audio shaped (channels, samples) at `sr`."""
    y, _ = librosa.load(str(path), sr=sr, mono=mono)
    if y.ndim == 1:
        y = y[None, :]
    return y.astype(np.float32), sr


def track_info(path: str | Path) -> dict:
    p = Path(path)
    try:
        info = sf.info(str(p))
        duration, rate, channels = info.duration, info.samplerate, info.channels
    except Exception:  # mp3 etc. on old libsndfile: fall back to decoding
        y, rate = librosa.load(str(p), sr=None, mono=False)
        channels = 1 if y.ndim == 1 else y.shape[0]
        duration = y.shape[-1] / rate
    return {
        "title": p.stem,
        "path": str(p.resolve()),
        "id": file_id(p),
        "duration": round(float(duration), 3),
        "sample_rate": int(rate),
        "channels": int(channels),
    }
