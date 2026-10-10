import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from strata import query
from strata.cli import main
from strata.library import Library
from strata.live import Clock, OscEmitter
from strata.server import create_app

FIX = Path(__file__).parent / "fixtures" / "sample_analysis.json"


@pytest.fixture
def a():
    return json.loads(FIX.read_text())


@pytest.fixture
def lib(tmp_path, monkeypatch, a):
    monkeypatch.setenv("STRATA_HOME", str(tmp_path))
    lib = Library()
    lib.save_analysis(a)
    return lib


# ---- query / cli ----

def test_at(a):
    r = query.at(a, 12.0)
    assert r["section"]["label"] == a["sections"][0]["label"]
    assert r["bar"] >= 1 and 1 <= r["beat"] <= 4 and 0 <= r["beat_phase"] < 1
    assert r["chord"] and set(r["curves"]) == set(a["curves"]["names"])


def test_summary(a):
    s = query.summary(a)
    assert "115.0 BPM" in s and "E major" in s and "chorus" in s


def test_cli_query(lib, a, capsys):
    assert main(["query", a["track"]["id"], "--summary"]) == 0
    assert "BPM" in capsys.readouterr().out
    assert main(["query", "fixture", "--cues", "--min", "0.6", "--json"]) == 0
    cues = json.loads(capsys.readouterr().out)
    assert cues and all(c["strength"] >= 0.6 for c in cues)
    assert main(["query", "nope-not-here"]) == 1


def test_cli_export(lib, a, tmp_path):
    assert main(["export", a["track"]["id"], "--format", "midi,labels", "--out", str(tmp_path / "x")]) == 0
    assert (tmp_path / "x" / "strata.mid").exists()


# ---- live ----

def test_tick_edges_once(a):
    e = OscEmitter(a)
    b = a["beats"][10]["time"]
    k = next(x["time"] for x in a["events"]["kick"] if x["time"] > b - 0.001)
    msgs = e.tick(b - 0.01, k + 0.001)
    addrs = [m[0] for m in msgs]
    assert addrs.count("/strata/beat") == 1 and addrs.count("/strata/kick") == 1
    assert "/strata/time" in addrs and "/strata/curve/loudness" in addrs


def test_seek_back_no_edges(a):
    e = OscEmitter(a)
    msgs = e.tick(100.0, 20.0)
    addrs = [m[0] for m in msgs]
    assert "/strata/beat" not in addrs and "/strata/kick" not in addrs
    assert "/strata/section" in addrs  # state resync


def test_clock():
    c = Clock()
    c.seek(5.0)
    assert c.time() == 5.0
    c.play()
    assert c.time() >= 5.0
    c.pause()
    t = c.time()
    assert c.time() == t


# ---- server ----

def test_server(lib, a):
    c = TestClient(create_app(lib=Library()))
    tracks = c.get("/api/tracks").json()
    assert [t["id"] for t in tracks] == [a["track"]["id"]]
    r = c.get(f"/api/tracks/{a['track']['id']}")
    assert r.status_code == 200 and r.json()["tempo"]["bpm"] == 115.0
    r = c.get(f"/api/tracks/{a['track']['id']}/export/midi")
    assert r.status_code == 200 and r.content[:4] == b"MThd"
    r = c.get(f"/api/tracks/{a['track']['id']}/export/csv")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert c.get("/api/tracks/nope").status_code == 404
    assert c.get(f"/api/tracks/{a['track']['id']}/export/bogus").status_code == 400


def test_server_rejects_foreign_origin_and_host(lib, a):
    c = TestClient(create_app(lib=Library()))
    assert c.get("/api/tracks", headers={"origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/tracks", headers={"host": "evil.example"}).status_code == 403
    r = c.post("/api/analyze", content='{"path": "/etc/passwd"}', headers={"content-type": "text/plain"})
    assert r.status_code == 415
    r = c.post("/api/analyze", json={"path": "/etc/passwd"})
    assert r.status_code == 400
    assert c.get("/api/tracks", headers={"origin": "http://localhost:3090"}).status_code == 200


def test_demo_seeds_empty_library_only(tmp_path):
    from strata.server import DEMO
    lib = Library(tmp_path / "lib")
    tid = lib.ensure_demo(DEMO)
    assert tid and Path(lib.load_analysis(tid)["track"]["path"]).exists()
    assert lib.ensure_demo(DEMO) is None


def test_delete_track_keeps_source_audio(lib, a, tmp_path):
    src = tmp_path / "source.wav"
    src.write_bytes(b"RIFF")
    a2 = json.loads(json.dumps(a))
    a2["track"]["id"], a2["track"]["path"] = "ab12cd34ef56ab78", str(src)
    lib.save_analysis(a2)
    (lib.stems_dir("ab12cd34ef56ab78") / "drums.flac").write_bytes(b"x")
    c = TestClient(create_app(lib=Library()))
    assert c.delete("/api/tracks/ab12cd34ef56ab78").status_code == 200
    assert not (lib.root / "ab12cd34ef56ab78").exists() and src.exists()
    assert c.delete("/api/tracks/ab12cd34ef56ab78").status_code == 404
    assert c.delete("/api/tracks/..%2F..%2Fetc").status_code in (400, 404, 405)  # never reaches a delete
    assert c.delete(f"/api/tracks/{a['track']['id']}", headers={"origin": "https://evil.example"}).status_code == 403


def test_cli_rm(lib, a, capsys):
    assert main(["rm", a["track"]["id"]]) == 0
    assert not lib.analysis_path(a["track"]["id"]).exists()
