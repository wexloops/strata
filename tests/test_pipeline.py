import numpy as np
import soundfile as sf

from strata.backends.base import Backend
from strata.library import Library
from strata.pipeline import analyze


class FakeBeats(Backend):
    name = "fake_beats"
    license = "MIT"
    weights = {"beats": 1.0}
    calls = 0

    def run(self, ctx):
        FakeBeats.calls += 1
        d = ctx.track["duration"]
        beats = list(np.arange(0.5, d - 0.1, 0.5))
        return {"beats": beats, "downbeats": beats[::4]}


class Boom(Backend):
    name = "boom"
    license = "MIT"
    weights = {"key": 1.0}

    def run(self, ctx):
        raise RuntimeError("kaboom")


class Missing(Backend):
    name = "missing"
    optional = True
    weights = {"tags": 1.0}

    def available(self):
        return False


def _wav(p, dur, silent=False):
    sr = 44100
    t = np.arange(int(sr * dur)) / sr
    y = np.zeros_like(t) if silent else 0.2 * np.sin(2 * np.pi * 220 * t)
    sf.write(p, y, sr)
    return p


def test_failure_isolated_and_valid(tmp_path):
    lib = Library(tmp_path / "lib")
    a = analyze(_wav(tmp_path / "x.wav", 12), only=[FakeBeats(), Boom(), Missing()], lib=lib)
    prov = {p["backend"]: p for p in a["provenance"]}
    assert prov["boom"]["ok"] is False and "kaboom" in prov["boom"]["error"]
    assert prov["missing"]["error"].startswith("not installed")
    assert prov["fake_beats"]["ok"] and abs(a["tempo"]["bpm"] - 120) < 0.1
    assert len(a["sections"]) == 1
    assert lib.load_analysis(a["track"]["id"])["tempo"]["bpm"] == a["tempo"]["bpm"]


def test_cache_reuse(tmp_path):
    lib = Library(tmp_path / "lib")
    p = _wav(tmp_path / "x.wav", 8)
    FakeBeats.calls = 0
    a1 = analyze(p, only=[FakeBeats()], lib=lib)
    a2 = analyze(p, only=[FakeBeats()], lib=lib)
    assert FakeBeats.calls == 1
    assert a2["provenance"][0]["cached"] is True
    assert a1["beats"] == a2["beats"]


def test_silent_and_short_audio(tmp_path):
    lib = Library(tmp_path / "lib")
    a = analyze(_wav(tmp_path / "s.wav", 2, silent=True), only=[Boom()], lib=lib)
    assert a["tempo"]["bpm"] == 0 and a["beats"] == [] and a["cues"][0]["type"] == "section"
