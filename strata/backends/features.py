"""Dense per-frame curves + loudness stats (pyloudnorm K-weighting, librosa spectral features)."""
from __future__ import annotations

import librosa
import numpy as np
import pyloudnorm as pyln

from ..schema import n_frames
from ._util import fit_frames, norm01
from .base import Backend, Context

BAND_EDGES = [20, 60, 150, 400, 1000, 2500, 6000, 12000, 20000]
SILENCE_LUFS = -50.0


def k_weight(meter: pyln.Meter, y: np.ndarray) -> np.ndarray:
    for f in meter._filters.values():
        y = f.apply_filter(y)
    return y


def momentary_lufs(meter: pyln.Meter, y: np.ndarray, sr: int, hop: int, win_s: float = 0.4) -> np.ndarray:
    ms = k_weight(meter, y) ** 2
    win = int(win_s * sr)
    c = np.concatenate([[0.0], np.cumsum(ms)])
    starts = np.arange(0, len(y), hop)
    lo, hi = np.maximum(starts - win // 2, 0), np.minimum(starts + win // 2, len(y))
    mean = (c[hi] - c[lo]) / np.maximum(hi - lo, 1)
    return -0.691 + 10 * np.log10(mean + 1e-12)


def lra(short_term: np.ndarray) -> float:
    st = short_term[short_term > -70]
    if st.size == 0:
        return 0.0
    rel = 10 * np.log10(np.mean(10 ** (st / 10))) - 20
    st = st[st > rel]
    return float(np.percentile(st, 95) - np.percentile(st, 10)) if st.size else 0.0


def db_curve(y: np.ndarray, hop: int, n: int, floor: float = -60.0) -> np.ndarray:
    r = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    db = np.maximum(20 * np.log10(r + 1e-9), floor)
    return fit_frames((db - floor) / -floor, n)


def silences(lufs: np.ndarray, fps: float, min_len: float = 0.5) -> list[dict]:
    quiet = lufs < SILENCE_LUFS
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) / fps >= min_len:
                out.append({"start": round(start / fps, 3), "end": round(i / fps, 3)})
            start = None
    return out


class Features(Backend):
    name = "features"
    license = "MIT"
    weights = {"curves": 1.0}
    requires = ("allin1", "demucs")

    def version(self) -> str:
        return "2"

    def run(self, ctx: Context) -> dict:
        sr, fps, y = ctx.sr, ctx.fps, ctx.mono
        n = n_frames(ctx.track["duration"], fps)
        hop = int(round(sr / fps))
        meter = pyln.Meter(sr)
        stereo = ctx.audio.T if ctx.audio.shape[0] > 1 else ctx.audio[0]
        try:
            integrated = float(meter.integrated_loudness(stereo))
        except ValueError:  # shorter than one gating block
            integrated = float("-inf")
        mom = momentary_lufs(meter, y, sr, hop)
        st = momentary_lufs(meter, y, sr, int(sr), win_s=3.0)
        curves = {"loudness": norm01(fit_frames(np.maximum(mom, -70), n), 1, 99.5),
                  "rms": db_curve(y, hop, n)}
        for s in ("drums", "bass", "vocals", "other"):
            ys = ctx.stem(s)
            curves[f"rms_{s}"] = db_curve(ys, hop, n) if ys is not None else np.zeros(n)
        S = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=4096)
        curves["onset"] = norm01(fit_frames(librosa.onset.onset_strength(S=librosa.amplitude_to_db(S), sr=sr), n))
        curves["centroid"] = norm01(fit_frames(librosa.feature.spectral_centroid(S=S, sr=sr)[0], n))
        flux = np.r_[0, np.sqrt(np.sum(np.maximum(np.diff(S, axis=1), 0) ** 2, axis=0))]
        curves["flux"] = norm01(fit_frames(flux, n))
        for i, (lo, hi) in enumerate(zip(BAND_EDGES[:-1], BAND_EDGES[1:])):
            band = S[(freqs >= lo) & (freqs < hi)].sum(axis=0)
            curves[f"band_{i}"] = norm01(fit_frames(librosa.amplitude_to_db(band + 1e-9), n), 1, 99.5)
        peak = float(np.max(np.abs(ctx.audio))) if ctx.audio.size else 0.0
        return {
            "curves": {k: [round(float(v), 4) for v in arr] for k, arr in curves.items()},
            "lufs": round(integrated, 2) if np.isfinite(integrated) else None,
            "lra": round(lra(st), 2),
            "peak_db": round(20 * np.log10(peak), 2) if peak > 0 else None,
            "silences": silences(mom, sr / hop),
        }


BACKEND = Features()
