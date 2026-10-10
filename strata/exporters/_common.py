"""Shared helpers for exporters: marker selection, timecode, paths, color matching."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from ..schema import SECTION_COLORS, n_frames, section_color

FPS = 30
CUE_MIN_STRENGTH = 0.6
CUE_COLORS = {"accent": "#FFB627", "downbeat": "#F5F5F0"}

_WSL_DRIVE = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")
_WIN_DRIVE = re.compile(r"^[A-Za-z]:/")


def title(a: dict) -> str:
    t = (a["track"].get("title") or "").strip()
    return t or Path(a["track"].get("path") or "STRATA").stem or "STRATA"


def clean(text: str) -> str:
    """Single-line label: tabs, newlines and control chars become spaces."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()


def audio_source(a: dict, audio_path: Path | None) -> str:
    return str(audio_path) if audio_path is not None else str(a["track"].get("path") or "")


def native_path(p: str) -> str:
    """WSL /mnt/<drive>/... -> <DRIVE>:/... so Windows hosts (Premiere, Resolve, AE) can open it."""
    m = _WSL_DRIVE.match(p)
    return f"{m.group(1).upper()}:{m.group(2) or '/'}" if m else p


def file_url(p: str) -> str:
    n = native_path(p)
    if _WIN_DRIVE.match(n):
        return "file:///" + n[:2] + quote(n[2:], safe="/")
    return "file://" + quote(str(Path(n).absolute()), safe="/")


def frame(t: float, fps: int = FPS) -> int:
    return int(round(t * fps))


def total_frames(a: dict, fps: int = FPS) -> int:
    return max(1, n_frames(a["track"]["duration"], fps))


def timecode(frames: int, fps: int = FPS, hour: int = 1) -> str:
    """Non-drop-frame timecode, offset by `hour` hours."""
    f = frames + hour * 3600 * fps
    return f"{f // (3600 * fps):02d}:{f // (60 * fps) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


def markers(a: dict, min_strength: float = CUE_MIN_STRENGTH) -> list[dict]:
    """Sections + every drop + cues >= min_strength, sorted by time.

    Cues of type section/drop restate the section/drop layers, so they are folded in rather than
    duplicated. Each marker: {time, end, kind, name, comment, color}; end is None for point markers.
    """
    out: list[dict] = []
    for i, s in enumerate(a["sections"]):
        bits = [f"energy {s.get('energy', 0):.2f}"]
        if s.get("key"):
            bits.append(f"key {s['key']}")
        out.append({"time": s["start"], "end": s["end"], "kind": "section", "name": clean(s["label"]) or "section",
                    "comment": ", ".join(bits), "color": s.get("color") or section_color(s["label"], i)})
    for d in a["dynamics"]["drops"]:
        out.append({"time": d["time"], "end": None, "kind": "drop", "name": "drop",
                    "comment": f"strength {d.get('strength', 0):.2f}", "color": SECTION_COLORS["drop"]})
    for c in a["cues"]:
        if c.get("strength", 0) < min_strength or c.get("type") in ("section", "drop"):
            continue
        out.append({"time": c["time"], "end": None, "kind": "cue", "name": clean(c.get("label") or c["type"]) or "cue",
                    "comment": f"{c['type']} cue, strength {c['strength']:.2f}",
                    "color": CUE_COLORS.get(c["type"], SECTION_COLORS["build"])})
    out.sort(key=lambda m: (m["time"], m["kind"] != "section"))
    return out


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def nearest_color(hex_color: str, palette: dict[str, str]) -> str:
    """Palette key whose hex is closest (RGB distance) to hex_color."""
    r, g, b = _rgb(hex_color)
    return min(palette, key=lambda k: sum((x - y) ** 2 for x, y in zip((r, g, b), _rgb(palette[k]))))
