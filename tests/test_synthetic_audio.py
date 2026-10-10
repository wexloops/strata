"""DSP backends on synthetic audio with known ground truth (CPU, fast)."""
import numpy as np
import soundfile as sf

from strata import audio
from strata.backends.base import Context
from strata.backends.chords_template import BACKEND as chords_template
from strata.backends.drums_bands import BACKEND as drums
from strata.backends.features import BACKEND as features
from strata.backends.key_template import BACKEND as key_template
from strata.library import Library
from strata.schema import n_frames

SR = 44100
rng = np.random.default_rng(1)


def _ctx(tmp_path, y, name="x.wav"):
    p = tmp_path / name
    sf.write(p, y, SR)
    info = audio.track_info(p)
    a, sr = audio.load(p)
    return Context(path=p, track=info, audio=a, sr=sr, lib=Library(tmp_path / "lib"), fps=30)


def _f1(est, ref, tol=0.015):
    est, ref = np.array(est), np.array(ref)
    hit = sum(np.min(np.abs(est - r)) <= tol for r in ref) if est.size else 0
    p = hit / max(len(est), 1)
    r = hit / max(len(ref), 1)
    return 2 * p * r / max(p + r, 1e-9)


def drum_track(dur=12.0):
    y = np.zeros(int(SR * dur))
    kicks = np.arange(0.5, dur - 0.5, 0.5)
    hats = kicks + 0.25
    t = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * (60 + 90 * np.exp(-t * 40)) * t) * np.exp(-t * 18)
    hat = rng.normal(0, 1, int(0.04 * SR)) * np.exp(-np.arange(int(0.04 * SR)) / SR * 120)
    from scipy.signal import butter, sosfilt
    hat = sosfilt(butter(4, 9000, "hp", fs=SR, output="sos"), hat)
    for k in kicks:
        i = int(k * SR)
        y[i:i + len(kick)] += 0.8 * kick[: len(y) - i]
    for h in hats:
        i = int(h * SR)
        y[i:i + len(hat)] += 0.3 * hat[: len(y) - i]
    return y, kicks, hats


def test_drum_bands_kick_and_hat(tmp_path):
    y, kicks, hats = drum_track()
    ctx = _ctx(tmp_path, y)
    r = drums.run(ctx)
    assert _f1([e["time"] for e in r["kick"]], kicks) > 0.95
    assert _f1([e["time"] for e in r["hat"]], hats) > 0.95
    n = n_frames(ctx.track["duration"], 30)
    assert all(len(r["curves"][k]) == n for k in ("kick", "snare", "hat"))


def test_features_curves_and_silence(tmp_path):
    y, _, _ = drum_track(12.0)
    y[int(5 * SR):int(7 * SR)] = 0.0
    ctx = _ctx(tmp_path, y)
    r = features.run(ctx)
    n = n_frames(ctx.track["duration"], 30)
    for name, arr in r["curves"].items():
        assert len(arr) == n, name
        assert min(arr) >= 0 and max(arr) <= 1, name
    assert any(s["start"] <= 5.3 and s["end"] >= 6.7 for s in r["silences"])
    assert r["lufs"] is not None and r["peak_db"] <= 0.5


def triad(freqs, dur):
    t = np.arange(int(SR * dur)) / SR
    env = np.minimum(1, t * 50) * np.minimum(1, (dur - t) * 50)
    return env * sum(np.sin(2 * np.pi * f * h * t) / h for f in freqs for h in (1, 2, 3)) * 0.1


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


def test_template_chords_and_key(tmp_path):
    prog = [(60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)]  # C G Am F
    y = np.concatenate([triad([midi(n) for n in c], 2.0) for c in prog * 2])
    ctx = _ctx(tmp_path, y)
    ctx.results["beat_this"] = {"beats": list(np.arange(0, 16, 0.5))}
    ch = chords_template.run(ctx)["chords"]
    roots = [c["label"].split(":")[0] for c in ch if c["label"] != "N" and c["end"] - c["start"] >= 1.0]
    assert roots[:4] == ["C", "G", "A", "F"]
    k = key_template.run(ctx)
    assert k["label"] in ("C major", "A minor")
    assert len(k["windows"]) >= 2 and len(k["windows"][0]["scores"]) == 24
