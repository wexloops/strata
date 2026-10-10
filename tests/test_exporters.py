"""Exporters: every format writes, parses, and carries unicode/quotes intact."""
import copy
import csv
import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import mido
import numpy as np
import pytest

from strata import exporters
from strata.exporters import _common, midi, report

FIXTURE = Path(__file__).parent / "fixtures" / "sample_analysis.json"
UNICODE_TITLE = 'Ñandú "Live" & <Dub>'


@pytest.fixture
def a() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _n_markers(a: dict) -> int:
    return len(_common.markers(a))


def _expected_markers(a: dict) -> int:
    # sections + every drop + strong cues (cues that merely restate a section/drop are folded in)
    cues = [c for c in a["cues"] if c["strength"] >= 0.6 and c["type"] not in ("section", "drop")]
    return len(a["sections"]) + len(a["dynamics"]["drops"]) + len(cues)


# --- registry ---------------------------------------------------------------------------------

def test_export_all_writes_every_format(a, tmp_path):
    paths = exporters.export(a, "all", tmp_path / "out")
    names = {p.name for p in paths}
    for expected in ["analysis.json", "beats.csv", "sections.csv", "chords.csv", "events.csv", "cues.csv",
                     "curves.csv", "strata.mid", "audacity.txt", "reaper_regions.csv", "premiere.xml",
                     "timeline.fcpxml", "resolve_markers.edl", "strata_ae.jsx", "curves.png", "curves.npy",
                     "curves.json", "report.html"]:
        assert expected in names
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


def test_export_rejects_unknown_format(a, tmp_path):
    with pytest.raises(ValueError):
        exporters.export(a, ["nope"], tmp_path)


def test_marker_selection(a):
    assert _n_markers(a) == _expected_markers(a)
    times = [m["time"] for m in _common.markers(a)]
    assert times == sorted(times)


def test_native_path_and_file_url():
    assert _common.native_path("/mnt/c/Users/x/a b.wav") == "C:/Users/x/a b.wav"
    assert _common.file_url("/mnt/c/Users/x/a b.wav") == "file:///C:/Users/x/a%20b.wav"
    assert _common.file_url("/tmp/Ñ \"q\".wav") == "file:///tmp/%C3%91%20%22q%22.wav"


# --- json / csv -------------------------------------------------------------------------------

def test_json_roundtrip(a, tmp_path):
    exporters.export(a, ["json"], tmp_path)
    assert json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8")) == a


def test_csv_files(a, tmp_path):
    exporters.export(a, ["csv"], tmp_path)
    with open(tmp_path / "beats.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(a["beats"])
    with open(tmp_path / "events.csv", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["kind", "time", "strength"]
    assert len(rows) - 1 == sum(len(v) for v in a["events"].values())
    # curves.csv: header row then purely numeric rows (TouchDesigner CHOP)
    with open(tmp_path / "curves.csv", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["frame", "time"] + a["curves"]["names"]
    n = len(a["curves"]["data"][a["curves"]["names"][0]])
    assert len(rows) - 1 == n
    for row in rows[1:]:
        [float(x) for x in row]


# --- midi -------------------------------------------------------------------------------------

def test_midi_tracks_and_marker_roundtrip(a, tmp_path):
    exporters.export(a, ["midi"], tmp_path)
    mf = mido.MidiFile(tmp_path / "strata.mid", charset="utf-8")
    assert mf.type == 1 and mf.ticks_per_beat == 480
    names = [next(m.name for m in t if m.type == "track_name") for t in mf.tracks]
    assert names == ["tempo", "markers", "chords", "drums", "bass", "vocals", "other", "beats"]

    # Walk the merged file with mido's own tempo handling: marker seconds must match sections.
    t, markers = 0.0, []
    for msg in mf:  # iterating a MidiFile yields delta times in seconds
        t += msg.time
        if msg.type == "marker":
            markers.append((t, msg.text))
    first = a["sections"][0]
    assert markers[0][1] == first["label"]
    assert abs(markers[0][0] - first["start"]) < 0.001
    # every section marker round-trips, not just the first
    sec = [m for m in markers if not m[1].startswith("drop")]
    assert len(sec) == len(a["sections"])
    for (mt, _), s in zip(sec, a["sections"]):
        assert abs(mt - s["start"]) < 0.001


def test_seconds_to_ticks_global_bpm(a):
    a["tempo"]["map"] = []
    a["tempo"]["bpm"] = 120.0
    segs = midi.tempo_segments(a)
    assert midi.seconds_to_ticks(1.0, segs) == 960  # 2 beats at 480 ppq


def test_midi_drums_and_beats(a, tmp_path):
    exporters.export(a, ["midi"], tmp_path)
    mf = mido.MidiFile(tmp_path / "strata.mid", charset="utf-8")
    by_name = {next(m.name for m in t if m.type == "track_name"): t for t in mf.tracks}
    drum_notes = {m.note for m in by_name["drums"] if m.type == "note_on"}
    assert drum_notes <= {36, 38, 42} and {36, 38, 42} <= drum_notes
    assert all(m.channel == 9 for m in by_name["drums"] if m.type == "note_on")
    beat_ons = [m.note for m in by_name["beats"] if m.type == "note_on"]
    assert len(beat_ons) == len(a["beats"])
    assert beat_ons.count(76) == sum(b["downbeat"] for b in a["beats"])
    chord_ons = [m for m in by_name["chords"] if m.type == "note_on"]
    assert len(chord_ons) >= 3 * len(a["chords"])


# --- labels -----------------------------------------------------------------------------------

def test_audacity_labels(a, tmp_path):
    exporters.export(a, ["labels"], tmp_path)
    lines = (tmp_path / "audacity.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == _expected_markers(a)
    for line in lines:
        assert re.match(r"^\d+\.\d+\t\d+\.\d+\t[^\t]+$", line), line


def test_reaper_regions(a, tmp_path):
    exporters.export(a, ["labels"], tmp_path)
    with open(tmp_path / "reaper_regions.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert ",".join(rows[0]) == "#,Name,Start,End,Length"
    regions = [r for r in rows[1:] if r[0].startswith("R")]
    assert len(regions) == len(a["sections"])
    assert float(regions[0][2]) == pytest.approx(a["sections"][0]["start"])
    assert any(r[0] == "M1" for r in rows[1:])


# --- NLE xml ----------------------------------------------------------------------------------

def test_premiere_xml(a, tmp_path):
    exporters.export(a, ["premiere"], tmp_path)
    root = ET.parse(tmp_path / "premiere.xml").getroot()
    assert root.tag == "xmeml"
    seq = root.find("sequence")
    assert seq.find("rate/timebase").text == "30" and seq.find("rate/ntsc").text == "FALSE"
    clip = seq.find("media/audio/track/clipitem")
    assert clip.find("file/pathurl").text.startswith("file://")
    assert len(seq.findall("marker")) == _expected_markers(a)


def test_fcpxml(a, tmp_path):
    exporters.export(a, ["fcpxml"], tmp_path)
    root = ET.parse(tmp_path / "timeline.fcpxml").getroot()
    assert root.tag == "fcpxml" and root.get("version") == "1.10"
    clip = root.find("library/event/project/sequence/spine/asset-clip")
    assert clip is not None
    chapters, plain = clip.findall("chapter-marker"), clip.findall("marker")
    assert len(chapters) == len(a["sections"])
    assert len(chapters) + len(plain) == _expected_markers(a)
    rx = re.compile(r"^(\d+/30s|0s)$")
    for m in chapters + plain:
        assert rx.match(m.get("start")) and rx.match(m.get("duration"))
    assert root.find("resources/asset/media-rep").get("src").startswith("file://")


def test_edl(a, tmp_path):
    exporters.export(a, ["edl"], tmp_path)
    lines = (tmp_path / "resolve_markers.edl").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("TITLE: ") and lines[1] == "FCM: NON-DROP FRAME"
    events = [l for l in lines if re.match(r"^\d{3}  001      V     C        \d\d:\d\d:\d\d:\d\d", l)]
    notes = [l for l in lines if l.startswith(" |C:Resolve")]
    assert len(events) == len(notes) == _expected_markers(a)
    assert events[0].split()[4] == _common.timecode(_common.frame(a["sections"][0]["start"]))
    assert all(re.match(r"^ \|C:ResolveColor\w+ \|M:[^|]+ \|D:\d+$", n) for n in notes)


# --- AE / texture / report --------------------------------------------------------------------

def test_ae_jsx(a, tmp_path):
    exporters.export(a, ["ae"], tmp_path)
    src = (tmp_path / "strata_ae.jsx").read_text(encoding="utf-8")
    assert "app.project.items.addComp" in src and "setValueAtTime" in src and "setValuesAtTimes" in src
    assert "app.beginUndoGroup" in src and "app.endUndoGroup" in src
    assert src.count("{") == src.count("}") and src.count("(") == src.count(")")
    assert json.dumps(a["track"]["title"]) in src  # quotes escaped, unicode \u-escaped


def test_texture(a, tmp_path):
    exporters.export(a, ["texture"], tmp_path)
    png = (tmp_path / "curves.png").read_bytes()
    width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
    names = a["curves"]["names"]
    assert bit_depth == 16 and color_type == 0 and height == len(names)
    arr = np.load(tmp_path / "curves.npy")
    assert arr.dtype == np.float32 and arr.shape == (len(names), width)
    meta = json.loads((tmp_path / "curves.json").read_text())
    assert meta["names"] == names and meta["frames"] == width and meta["fps"] == a["curves"]["fps"]
    assert np.allclose(arr[0, :10], a["curves"]["data"][names[0]][:10], atol=1e-6)


_EXTERNAL = re.compile(r"""\b(?:src|href)\s*=\s*["']?(?!data:|#)""", re.I)
_BODIES = re.compile(r"(<(script|style)\b[^>]*>).*?(</\2>)", re.I | re.S)


def external_refs(html: str) -> list[str]:
    """src/href attributes on real tags; inlined script/style bodies are code, not references."""
    return _EXTERNAL.findall(_BODIES.sub(r"\1\3", html))


def test_report_fallback_self_contained(a, tmp_path, monkeypatch):
    monkeypatch.setattr(report, "TEMPLATE", tmp_path / "missing.html")
    exporters.export(a, ["report"], tmp_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html>") and "<svg" in html
    assert not external_refs(html)
    assert 'id="strata-data"' in html


def test_report_template_injection(a, tmp_path, monkeypatch):
    tpl = tmp_path / "tpl.html"
    tpl.write_text('<!doctype html><script id="strata-data" type="application/json">__STRATA_DATA__</script>')
    monkeypatch.setattr(report, "TEMPLATE", tpl)
    a["track"]["title"] = "evil </script><script>alert(1)</script>\u2028"
    exporters.export(a, ["report"], tmp_path / "out")
    html = (tmp_path / "out" / "report.html").read_text(encoding="utf-8")
    assert "__STRATA_DATA__" not in html and html.count("</script>") == 1 and "\u2028" not in html
    payload = re.search(r'type="application/json">(.*)</script>', html, re.S).group(1)
    assert json.loads(payload)["track"]["title"] == a["track"]["title"]


def test_report_default(a, tmp_path):
    exporters.export(a, ["report"], tmp_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert not external_refs(html)


# --- unicode ----------------------------------------------------------------------------------

def test_unicode_title_escaping(a, tmp_path):
    a = copy.deepcopy(a)
    audio = tmp_path / 'Ñandú "Live" & <Dub>.wav'
    a["track"]["title"] = UNICODE_TITLE
    a["track"]["path"] = str(audio)
    a["sections"][0]["label"] = 'intro "ñ" & <x>'
    out = tmp_path / "out dir ñ"
    paths = exporters.export(a, "all", out)
    assert all(p.exists() for p in paths)

    prem = ET.parse(out / "premiere.xml").getroot()
    assert prem.find("sequence/name").text == UNICODE_TITLE
    url = prem.find("sequence/media/audio/track/clipitem/file/pathurl").text
    assert "%C3%91and%C3%BA%20%22Live%22%20%26%20%3CDub%3E.wav" in url
    assert prem.find("sequence/marker/name").text == 'intro "ñ" & <x>'

    fcp = ET.parse(out / "timeline.fcpxml").getroot()
    assert fcp.find("library/event/project").get("name") == UNICODE_TITLE
    assert fcp.find(".//chapter-marker").get("value") == 'intro "ñ" & <x>'

    jsx = (out / "strata_ae.jsx").read_text(encoding="utf-8")
    assert json.dumps(UNICODE_TITLE) in jsx
    assert '"Live"' not in jsx.replace('\\"Live\\"', "")

    mf = mido.MidiFile(out / "strata.mid", charset="utf-8")
    texts = [m.text for t in mf.tracks for m in t if m.type in ("text", "marker")]
    assert UNICODE_TITLE in texts and 'intro "ñ" & <x>' in texts

    assert UNICODE_TITLE in (out / "resolve_markers.edl").read_text(encoding="utf-8").splitlines()[0]
    assert 'intro "ñ" & <x>' in (out / "audacity.txt").read_text(encoding="utf-8")
    with open(out / "reaper_regions.csv", newline="", encoding="utf-8") as f:
        assert list(csv.reader(f))[1][1] == 'intro "ñ" & <x>'
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "<Dub>" not in html
    assert json.loads((out / "analysis.json").read_text(encoding="utf-8"))["track"]["title"] == UNICODE_TITLE
