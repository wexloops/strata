"""analysis.json + flat CSVs (Sheets, TouchDesigner CHOP)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..schema import n_frames


def export_json(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "analysis.json"
    p.write_text(json.dumps(a, indent=2, ensure_ascii=False), encoding="utf-8")
    return [p]


def _write(path: Path, header: list[str], rows) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def _curve_rows(a: dict):
    curves = a["curves"]
    fps, names = curves["fps"], curves["names"]
    n = n_frames(a["track"]["duration"], fps)
    cols = [curves["data"][k] for k in names]
    for i in range(n):
        # Curves may be +-1 frame off nominal (schema tolerance): hold the last sample.
        yield [i, round(i / fps, 4)] + [c[min(i, len(c) - 1)] if c else 0.0 for c in cols]


def export_csv(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    events = sorted(((k, e["time"], e.get("strength", 0)) for k, v in a["events"].items() for e in v),
                    key=lambda r: (r[1], r[0]))
    return [
        _write(out_dir / "beats.csv", ["time", "bar", "beat", "downbeat", "confidence"],
               ([b["time"], b.get("bar"), b.get("beat"), int(bool(b.get("downbeat"))), b.get("confidence", 0)]
                for b in a["beats"])),
        _write(out_dir / "sections.csv", ["index", "start", "end", "label", "confidence", "energy", "color", "key"],
               ([s.get("index"), s["start"], s["end"], s["label"], s.get("confidence", 0), s.get("energy", 0),
                 s.get("color", ""), s.get("key") or ""] for s in a["sections"])),
        _write(out_dir / "chords.csv", ["start", "end", "label", "label_full", "root", "quality", "confidence"],
               ([c["start"], c["end"], c["label"], c.get("label_full", ""), c.get("root", ""), c.get("quality", ""),
                 c.get("confidence", 0)] for c in a["chords"])),
        _write(out_dir / "events.csv", ["kind", "time", "strength"], events),
        _write(out_dir / "cues.csv", ["time", "type", "strength", "label"],
               ([c["time"], c["type"], c.get("strength", 0), c.get("label", "")] for c in a["cues"])),
        _write(out_dir / "curves.csv", ["frame", "time"] + list(a["curves"]["names"]), _curve_rows(a)),
    ]
