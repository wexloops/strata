"""Kick / snare / hat hits from the drum stem (ours, MIT).

Per-band log-energy flux -> adaptive-threshold peak picking. Bands are detected independently
(a kick and a hat can share a frame). Kick attacks leak into the upper bands, so a snare/hat onset
that coincides with a stronger lower-band hit only counts if it is comparably strong (LEAK_RATIO).
"""
from __future__ import annotations

import librosa
import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from ..schema import n_frames
from ._util import ref_beats
from .base import Backend, Context

N_FFT, HOP = 2048, 256
BANDS = {"kick": [(30, 150)], "snare": [(180, 2500), (4000, 8000)], "hat": [(7000, 16000)]}
REFRACTORY = 0.05
COINCIDE = 0.025
LEAK_RATIO = 0.75
REL_MIN = {"kick": 0.3, "snare": 0.3, "hat": 0.25}
ONSET_REL_MIN = 0.3
# Musical prior: densest plausible hit rate per beat; the strongest hits win when exceeded.
MAX_PER_BEAT = {"kick": 1.5, "snare": 1.0, "hat": 4.0}


def band_flux(S: np.ndarray, freqs: np.ndarray, ranges) -> np.ndarray:
    mask = np.zeros_like(freqs, dtype=bool)
    for lo, hi in ranges:
        mask |= (freqs >= lo) & (freqs < hi)
    e = np.log1p(1000 * S[mask].sum(axis=0))
    return np.maximum(np.r_[0, np.diff(e)], 0)


def band_envelope(y: np.ndarray, sr: int, ranges) -> np.ndarray:
    """Rectified, 1 ms-smoothed band-passed signal for sample-accurate attack refinement."""
    sig = np.zeros_like(y)
    for lo, hi in ranges:
        sos = butter(4, [lo, min(hi, sr / 2 - 100)], "bandpass", fs=sr, output="sos")
        sig += sosfiltfilt(sos, y)
    k = max(1, int(0.001 * sr))
    return np.convolve(np.abs(sig), np.ones(k) / k, mode="same")


def refine(times: np.ndarray, env: np.ndarray, sr: int, win: float = 0.03) -> np.ndarray:
    """Snap each coarse onset to where the band envelope first reaches half its local peak."""
    out = []
    for t in times:
        a, b = max(0, int((t - win) * sr)), min(len(env), int((t + win) * sr))
        seg = env[a:b]
        if seg.size == 0 or seg.max() <= 0:
            out.append(t)
            continue
        peak = int(np.argmax(seg))
        above = np.nonzero(seg[:peak + 1] >= 0.5 * seg[peak])[0]
        out.append((a + (above[0] if above.size else peak)) / sr)
    return np.array(out)


def pick(flux: np.ndarray, fps: float, rel_min: float, max_hits: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Peaks whose prominence is at least `rel_min` of the band's strong-hit level (p95 prominence).

    Returns (frame indices, strengths 0..1). Prominence (height above the surrounding floor) rejects
    the dense small bumps of live kits and bleed; thresholding against the band's own distribution
    holds up on sparse stems, where median/MAD thresholds collapse toward zero.
    """
    wait = max(1, int(REFRACTORY * fps))
    peaks, props = find_peaks(flux, distance=wait, prominence=0)
    if peaks.size == 0:
        return peaks, np.array([])
    prom = props["prominences"]
    ref = float(np.percentile(prom, 95)) + 1e-9
    keep = prom >= rel_min * ref
    if max_hits is not None and keep.sum() > max_hits:
        keep &= prom >= np.sort(prom[keep])[-max_hits]
    return peaks[keep], np.minimum(1.0, prom[keep] / ref)


def suppress_leakage(hits: list[dict], louder: list[list[dict]]) -> list[dict]:
    """Drop hits that coincide with a stronger lower-band hit unless comparably strong themselves."""
    out = []
    for e in hits:
        ok = True
        for other in louder:
            for o in other:
                if abs(o["time"] - e["time"]) <= COINCIDE and e["strength"] < LEAK_RATIO * o["strength"]:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            out.append(e)
    return out


def envelope(flux: np.ndarray, fps_in: float, n: int, decay: float = 0.82) -> np.ndarray:
    """Fast-attack / exponential-release envelope resampled to n frames (good for driving visuals)."""
    ref = np.percentile(flux[flux > 0], 99) if np.any(flux > 0) else 1.0
    x = np.clip(flux / (ref + 1e-9), 0, 1)
    env = np.zeros_like(x)
    d = decay ** (30.0 / fps_in)  # `decay` is per 1/30 s
    for i in range(len(x)):
        env[i] = max(x[i], env[i - 1] * d if i else 0)
    # max-pool into output frames so short hits survive downsampling
    edges = np.linspace(0, len(env), n + 1).astype(int)
    return np.array([env[a:max(b, a + 1)].max() if a < len(env) else 0.0 for a, b in zip(edges[:-1], edges[1:])])


class DrumBands(Backend):
    name = "drums_bands"
    license = "MIT"
    weights = {"events": 1.0}
    requires = ("allin1", "demucs", "beat_this")

    def version(self) -> str:
        return "3"

    def run(self, ctx: Context) -> dict:
        y = ctx.stem("drums")
        if y is None:
            y = ctx.mono
        sr = ctx.sr
        fps = sr / HOP
        n = n_frames(ctx.track["duration"], ctx.fps)
        S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)) ** 2
        freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
        n_beats = len(ref_beats(ctx))
        out, curves = {}, {}
        for k, ranges in BANDS.items():
            f = band_flux(S, freqs, ranges)
            cap = int(MAX_PER_BEAT[k] * n_beats) if n_beats else None
            peaks, strength = pick(f, fps, REL_MIN[k], cap)
            times = refine(peaks / fps, band_envelope(y, sr, ranges), sr)
            out[k] = [{"time": round(float(t), 3), "strength": round(float(st), 3)} for t, st in zip(times, strength)]
            curves[k] = [round(float(v), 4) for v in envelope(f, fps, n)]
        out["snare"] = suppress_leakage(out["snare"], [out["kick"]])
        out["hat"] = suppress_leakage(out["hat"], [out["kick"], out["snare"]])
        on = librosa.onset.onset_strength(y=ctx.mono, sr=sr, hop_length=HOP)
        on_peaks, on_str = pick(on, fps, ONSET_REL_MIN)
        out["onsets"] = [{"time": round(float(p / fps), 3), "strength": round(float(st), 3)} for p, st in zip(on_peaks, on_str)]
        out["curves"] = curves
        return out


BACKEND = DrumBands()
