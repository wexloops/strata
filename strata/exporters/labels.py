"""audacity.txt label track + reaper_regions.csv (Region/Marker Manager import)."""
from __future__ import annotations

import csv
from pathlib import Path

from . import _common


def export_labels(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    marks = _common.markers(a)

    aud = out_dir / "audacity.txt"
    lines = [f"{m['time']:.6f}\t{(m['end'] if m['end'] is not None else m['time']):.6f}\t{m['name']}" for m in marks]
    aud.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rpp = out_dir / "reaper_regions.csv"
    with open(rpp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "Name", "Start", "End", "Length"])
        for i, s in enumerate(a["sections"], 1):
            w.writerow([f"R{i}", _common.clean(s["label"]), f"{s['start']:.3f}", f"{s['end']:.3f}",
                        f"{s['end'] - s['start']:.3f}"])
        points = [m for m in marks if m["kind"] != "section"]
        for i, m in enumerate(points, 1):
            w.writerow([f"M{i}", m["name"], f"{m['time']:.3f}", "", ""])
    return [aud, rpp]
