"""STRATA as an MCP server (`strata mcp`, stdio) so Claude Desktop / claude.ai / any MCP client can drive it.

Thin layer over the same functions the CLI uses. Tracks are addressed like the CLI: an audio path
(Windows paths such as C:\\Music\\a.wav are accepted on WSL), a track id, or a unique title substring.
"""
from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__, query
from .library import Library

INSTRUCTIONS = """STRATA analyzes music into one JSON: sections, tempo/beats/bars, key, chords, drum hits,
builds/drops, vocals + timed lyrics, ranked cue points and per-frame curves. Analyze a file once
(1-2 min on a GPU, cached after), then use summary / at / sections / cues / beats to answer
questions or plan edits, export to write Premiere/Resolve/AE/MIDI/CSV files, and live_start to play
the analysis as OSC into Notch/TouchDesigner/Resolume. Times are seconds. Cue strength >= 0.6 means
structural moments (section starts, drops)."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_live: dict = {"session": None, "track": None}


def native_to_local(p: str) -> str:
    """Accept Windows paths when running under WSL: C:\\x\\y.wav -> /mnt/c/x/y.wav."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p.strip().strip('"'))
    if m and Path("/mnt").exists():
        return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")
    return p.strip().strip('"')


def _load(track: str) -> dict:
    try:
        return query.resolve(native_to_local(track), Library())
    except LookupError as e:  # not analyzed / ambiguous / unknown: tell the model what to do
        raise ToolError(str(e)) from e


def build_server() -> MCPServer:
    mcp = MCPServer(name="strata", title="STRATA", version=__version__, instructions=INSTRUCTIONS,
                    website_url="https://github.com/wexloops/strata")

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=False))
    async def analyze(path: str, ctx: Context, profile: Literal["full", "commercial-safe"] = "full",
                      fast: bool = False) -> str:
        """Analyze an audio file (wav/mp3/flac/aif/m4a). Returns the text summary and track id.
        Cached: re-analyzing the same file is instant. `fast` skips optional extras (lyrics)."""
        from .backends.base import registry
        from .pipeline import analyze as run

        path = native_to_local(path)
        if not Path(path).is_file():
            raise ToolError(f"no such file: {path}")
        events: list[dict] = []
        result: dict = {}

        def work():
            try:
                result["a"] = run(path, profile=profile, progress=events.append,
                                  only=registry(profile, include_optional=not fast))
            except Exception as e:  # surfaced to the client below
                result["error"] = f"{type(e).__name__}: {e}"

        th = threading.Thread(target=work, daemon=True)
        th.start()
        sent = 0
        while th.is_alive() or sent < len(events):
            while sent < len(events):
                e = events[sent]
                sent += 1
                if "progress" in e:
                    await ctx.report_progress(e["progress"], 1.0, e.get("message") or e.get("stage"))
            await asyncio.sleep(0.5)
        if "error" in result:
            raise ToolError(result["error"])
        a = result["a"]
        return f"track id: {a['track']['id']}\n\n{query.summary(a)}"

    @mcp.tool(annotations=READ)
    def library() -> list[dict]:
        """List analyzed tracks: id, title, duration, bpm, key."""
        return Library().list()

    @mcp.tool(annotations=READ)
    def summary(track: str) -> str:
        """Compact text breakdown of an analyzed track (tempo, key, loudness, sections, drops, hits)."""
        return query.summary(_load(track))

    @mcp.tool(annotations=READ)
    def at(track: str, seconds: float) -> dict:
        """Everything happening at one moment: section, bar.beat, chord, key, curve values, nearby hits, lyric."""
        return query.at(_load(track), seconds)

    @mcp.tool(annotations=READ)
    def sections(track: str) -> list[dict]:
        """Sections with start/end (s), label, energy 0..1, local key and confidence."""
        return query.sections(_load(track))

    @mcp.tool(annotations=READ)
    def cues(track: str, min_strength: float = 0.6, types: list[str] | None = None) -> list[dict]:
        """Ranked edit points. types: section, drop, downbeat, accent. >= 0.6 = structural."""
        return query.cues(_load(track), min_strength, types)

    @mcp.tool(annotations=READ)
    def beats(track: str, start: float = 0.0, end: float | None = None, downbeats_only: bool = False) -> list[dict]:
        """Beats (time, bar, beat-in-bar, downbeat, confidence) between start and end seconds."""
        return [{k: b[k] for k in ("time", "bar", "beat", "downbeat", "confidence")}
                for b in query.beats(_load(track), start, end, downbeats_only)]

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=False))
    def export(track: str, formats: list[str] | None = None, out_dir: str | None = None) -> list[str]:
        """Write export files and return their paths. formats: json, csv, midi, labels, premiere, fcpxml,
        edl, ae, texture, report (default: all). out_dir defaults to the track's library exports folder."""
        from .exporters import export as run

        a = _load(track)
        out = Path(native_to_local(out_dir)) if out_dir else Library().exports_dir(a["track"]["id"])
        audio = Path(a["track"]["path"])
        return [str(p) for p in run(a, formats or ["all"], out, audio if audio.exists() else None)]

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, open_world_hint=True))
    def live_start(track: str, host: str = "127.0.0.1", port: int = 9000, start_at: float = 0.0) -> str:
        """Start playing the analysis as OSC (60 Hz) to host:port from start_at seconds. See the README
        for the address map (/strata/beat, /strata/section, /strata/kick, /strata/curve/<name>...)."""
        from .live import LiveSession

        live_stop()
        a = _load(track)
        s = LiveSession(a, host, port).start()
        s.clock.play(at=start_at)
        _live.update(session=s, track=a["track"]["title"])
        return f"OSC live: {a['track']['title']} -> {host}:{port} from {start_at}s"

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=False))
    def live_stop() -> str:
        """Stop OSC playback."""
        s = _live["session"]
        if not s:
            return "nothing playing"
        s.stop()
        title = _live["track"]
        _live.update(session=None, track=None)
        return f"stopped {title}"

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False))
    def remove(track: str) -> str:
        """Remove a track's STRATA data (analysis, stems, cache, exports) from the library.
        The source audio file is never touched."""
        a = _load(track)
        Library().delete(a["track"]["id"])
        return f"removed {a['track']['title']} from the library; source audio untouched"

    return mcp


def main() -> None:
    build_server().run("stdio")
