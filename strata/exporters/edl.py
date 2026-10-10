"""resolve_markers.edl: CMX3600 in the shape DaVinci Resolve uses for timeline-marker EDLs."""
from __future__ import annotations

from pathlib import Path

from . import _common

# Resolve's marker palette (approximate swatch values) for nearest-color matching.
RESOLVE_COLORS = {
    "Blue": "#3D7BFF", "Cyan": "#00CED0", "Green": "#00AD00", "Yellow": "#F0C300", "Red": "#E2312D",
    "Pink": "#FF44C8", "Purple": "#9013FE", "Fuchsia": "#C02E6F", "Rose": "#FFA1B9", "Lavender": "#A193C8",
    "Sky": "#92E2FD", "Mint": "#72DB00", "Lemon": "#DCE95A", "Sand": "#C4915E", "Cocoa": "#6E5143",
    "Cream": "#F5EBE1",
}


def _event(i: int, m: dict) -> list[str]:
    start = _common.frame(m["time"])
    dur = max(1, _common.frame(m["end"]) - start) if m["end"] is not None else 1
    tin, tout = _common.timecode(start), _common.timecode(start + dur)
    color = _common.nearest_color(m["color"], RESOLVE_COLORS)
    name = m["name"].replace("|", "/")
    return [f"{i:03d}  001      V     C        {tin} {tout} {tin} {tout}  ",
            f" |C:ResolveColor{color} |M:{name} |D:{dur}", ""]


def export_edl(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"TITLE: {_common.clean(_common.title(a))}", "FCM: NON-DROP FRAME", ""]
    for i, m in enumerate(_common.markers(a), 1):
        lines += _event(i, m)
    p = out_dir / "resolve_markers.edl"
    p.write_text("\n".join(lines), encoding="utf-8")
    return [p]
