import numpy as np

from strata import schema
from strata.derive import derive


def _analysis():
    dur = 40.0
    a = schema.empty_analysis({"title": "t", "path": "", "id": "x" * 16, "duration": dur, "sample_rate": 44100, "channels": 2}, "full", 30)
    t = np.arange(0, dur, 0.5)
    a["beats"] = [{"time": float(x), "bar": i // 4 + 1, "beat": i % 4 + 1, "downbeat": i % 4 == 0, "confidence": 1.0, "votes": {}}
                  for i, x in enumerate(t)]
    a["bars"] = [{"index": i + 1, "start": float(x), "end": float(x + 2)} for i, x in enumerate(np.arange(0, dur, 2.0))]
    a["sections"] = [
        {"index": 0, "start": 0.0, "end": 8.0, "label": "intro", "confidence": 1.0, "energy": 0, "color": "", "key": None, "tags": [], "votes": {}},
        {"index": 1, "start": 8.0, "end": 16.0, "label": "B", "confidence": 1.0, "energy": 0, "color": "", "key": None, "tags": [], "votes": {}},
        {"index": 2, "start": 16.0, "end": 40.0, "label": "chorus", "confidence": 0.9, "energy": 0, "color": "", "key": None, "tags": [], "votes": {}},
    ]
    n = schema.n_frames(dur, 30)
    tt = np.arange(n) / 30
    loud = np.where(tt < 8, 0.2, np.where(tt < 16, 0.2 + 0.4 * (tt - 8) / 8, 0.95))
    a["curves"]["data"]["loudness"] = loud.tolist()
    a["curves"]["data"]["onset"] = (loud * 0.8).tolist()
    a["curves"]["data"]["centroid"] = loud.tolist()
    a["events"]["onsets"] = [{"time": float(x), "strength": 0.5} for x in t]
    a["events"]["kick"] = [{"time": float(x), "strength": 0.9} for x in t[::2]]
    return a


def test_build_and_drop_detected():
    a = derive(_analysis())
    builds = a["dynamics"]["builds"]
    assert builds and abs(builds[-1]["end"] - 16.0) <= 2.0 and builds[-1]["start"] <= 12.0
    drops = a["dynamics"]["drops"]
    assert any(abs(d["time"] - 16.0) < 0.01 and d["strength"] > 0.7 for d in drops)


def test_section_energy_color_and_cues():
    a = derive(_analysis())
    s = a["sections"]
    assert s[0]["color"] == schema.SECTION_COLORS["intro"] and s[2]["color"] == schema.SECTION_COLORS["chorus"]
    assert s[1]["color"] in schema.CLUSTER_COLORS
    assert s[2]["energy"] > s[0]["energy"]
    cues = a["cues"]
    assert [c["time"] for c in cues] == sorted(c["time"] for c in cues)
    sec_cues = [c for c in cues if c["type"] == "section"]
    assert len(sec_cues) == 3 and all(c["strength"] >= 0.8 for c in sec_cues)
    assert schema.validate(a) == []


def test_derive_on_empty_analysis():
    a = schema.empty_analysis({"title": "t", "path": "", "id": "x" * 16, "duration": 2.0, "sample_rate": 44100, "channels": 1}, "full", 30)
    a = derive(a)
    assert a["cues"] == [] and a["dynamics"]["builds"] == []
