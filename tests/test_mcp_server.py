import asyncio
import json
from pathlib import Path

import pytest

from strata.library import Library
from strata.mcp_server import build_server, native_to_local

FIX = Path(__file__).parent / "fixtures" / "sample_analysis.json"


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATA_HOME", str(tmp_path))
    lib = Library()
    lib.save_analysis(json.loads(FIX.read_text()))
    return lib


def call(name, **args):
    return asyncio.run(build_server().call_tool(name, args))


def text(res) -> str:
    return "".join(c.text for c in res.content if getattr(c, "type", "") == "text")


def test_tools_listed():
    names = {t.name for t in asyncio.run(build_server().list_tools())}
    assert {"analyze", "library", "summary", "at", "sections", "cues", "beats", "export",
            "live_start", "live_stop", "remove"} <= names


def test_read_tools(lib):
    assert "fixture" in text(call("library"))
    assert "BPM" in text(call("summary", track="fixture"))
    at = json.loads(text(call("at", track="fixture", seconds=12.0)))
    assert at["section"]["label"] and at["bar"] >= 1
    cues = call("cues", track="fixture", min_strength=0.6)
    assert "section" in text(cues)


def test_export_and_remove(lib, tmp_path):
    out = text(call("export", track="fixture", formats=["midi"], out_dir=str(tmp_path / "x")))
    assert "strata.mid" in out and (tmp_path / "x" / "strata.mid").exists()
    assert "untouched" in text(call("remove", track="fixture"))
    assert lib.list() == []


def test_errors_are_tool_errors(lib):
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="no such file"):
        asyncio.run(build_server().call_tool("analyze", {"path": "/nope/a.wav"}))
    with pytest.raises(ToolError, match="no analysis"):
        asyncio.run(build_server().call_tool("summary", {"track": "never-heard-of-it"}))


def test_windows_paths():
    assert native_to_local(r"C:\Users\x\a b.wav") == "/mnt/c/Users/x/a b.wav"
    assert native_to_local("/home/a.wav") == "/home/a.wav"
