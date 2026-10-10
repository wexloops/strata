import numpy as np
import soundfile as sf
import pytest

from strata import audio, schema
from strata.library import Library


def _sine(sr, dur=1.0, ch=2, f=440.0):
    t = np.arange(int(sr * dur)) / sr
    x = 0.3 * np.sin(2 * np.pi * f * t)
    return np.stack([x] * ch, axis=1) if ch > 1 else x


def test_formats_and_rates(tmp_path):
    sf.write(tmp_path / "a.wav", _sine(48000), 48000)
    sf.write(tmp_path / "a.flac", _sine(48000), 48000)
    sf.write(tmp_path / "m.wav", _sine(22050, ch=1), 22050)
    for name in ("a.wav", "a.flac"):
        y, sr = audio.load(tmp_path / name)
        assert sr == 44100 and y.shape[0] == 2 and abs(y.shape[1] - 44100) < 50
    y, sr = audio.load(tmp_path / "m.wav")
    assert y.shape[0] == 1
    info = audio.track_info(tmp_path / "a.wav")
    assert len(info["id"]) == 16 and info["title"] == "a"
    assert abs(info["duration"] - 1.0) < 0.01 and info["sample_rate"] == 48000
    assert audio.track_info(tmp_path / "a.wav")["id"] == info["id"]


def test_unicode_path(tmp_path):
    p = tmp_path / "Ñandú dub mix.wav"
    sf.write(p, _sine(44100), 44100)
    assert audio.track_info(p)["title"] == "Ñandú dub mix"


def _track():
    return {"title": "t", "path": "/t.wav", "id": "0" * 16, "duration": 2.0, "sample_rate": 44100, "channels": 2}


def test_empty_validates():
    a = schema.empty_analysis(_track(), "full", 30)
    assert schema.validate(a) == []
    assert len(a["curves"]["data"]["loudness"]) == 60
    b = dict(a)
    del b["tempo"]
    assert any("tempo" in e for e in schema.validate(b))
    a["beats"] = [{"time": 1.0}, {"time": 0.5}]
    assert any("beats" in e for e in schema.validate(a))


def test_curve_length_checked():
    a = schema.empty_analysis(_track(), "full", 30)
    a["curves"]["data"]["rms"] = [0.0] * 10
    assert any("rms" in e for e in schema.validate(a))


def test_round_times():
    a = schema.empty_analysis(_track(), "full", 30)
    a["beats"] = [{"time": 0.123456, "confidence": 0.98765}]
    schema.round_floats(a)
    assert a["beats"][0]["time"] == 0.123


def test_library_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATA_HOME", str(tmp_path))
    lib = Library()
    assert lib.cache_get("abc", "x@1") is None
    lib.cache_put("abc", "x@1", {"v": [1, 2]})
    assert lib.cache_get("abc", "x@1") == {"v": [1, 2]}
    a = schema.empty_analysis(_track(), "full", 30)
    lib.save_analysis(a)
    assert lib.load_analysis("0" * 16)["track"]["title"] == "t"
    assert [t["id"] for t in lib.list()] == ["0" * 16]
