"""Exporter registry. Every exporter: fn(a, out_dir, audio_path) -> list[Path], pure in `a`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .ae_jsx import export_ae
from .edl import export_edl
from .fcpxml import export_fcpxml
from .json_csv import export_csv, export_json
from .labels import export_labels
from .midi import export_midi
from .premiere_xml import export_premiere
from .report import export_report
from .texture import export_texture

Exporter = Callable[[dict, Path, "Path | None"], list[Path]]

FORMATS: dict[str, Exporter] = {
    "json": export_json,
    "csv": export_csv,
    "midi": export_midi,
    "labels": export_labels,
    "premiere": export_premiere,
    "fcpxml": export_fcpxml,
    "edl": export_edl,
    "ae": export_ae,
    "texture": export_texture,
    "report": export_report,
}


def resolve_formats(fmts: list[str] | str) -> list[str]:
    names = [fmts] if isinstance(fmts, str) else list(fmts)
    if "all" in names:
        return list(FORMATS)
    unknown = [f for f in names if f not in FORMATS]
    if unknown:
        raise ValueError(f"unknown export format(s): {', '.join(unknown)}; choose from {', '.join(FORMATS)} or all")
    return list(dict.fromkeys(names))


def export(a: dict, fmts: list[str] | str, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for f in resolve_formats(fmts):
        paths += FORMATS[f](a, out_dir, audio_path)
    return paths
