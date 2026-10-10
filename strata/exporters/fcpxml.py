"""timeline.fcpxml (FCPXML 1.10): one audio asset-clip on the spine; sections as chapter markers."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from . import _common

FPS = _common.FPS
AUDIO_RATES = {32000: "32k", 44100: "44.1k", 48000: "48k", 88200: "88.2k", 96000: "96k",
               176400: "176.4k", 192000: "192k"}


def rt(frames: int) -> str:
    """Frame-aligned rational time."""
    return f"{frames}/{FPS}s" if frames else "0s"


def _markers(clip: ET.Element, a: dict) -> None:
    for m in _common.markers(a):
        attrs = {"start": rt(_common.frame(m["time"])), "duration": rt(1), "value": m["name"], "note": m["comment"]}
        if m["kind"] == "section":
            ET.SubElement(clip, "chapter-marker", {**attrs, "posterOffset": "0s"})
        else:
            ET.SubElement(clip, "marker", attrs)


def export_fcpxml(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    n, name = _common.total_frames(a), _common.title(a)
    dur = rt(n)
    sr = int(a["track"].get("sample_rate") or 48000)

    root = ET.Element("fcpxml", version="1.10")
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", name="FFVideoFormat1080p30", frameDuration=f"1/{FPS}s",
                  width="1920", height="1080")
    asset = ET.SubElement(res, "asset", id="r2", name=name, start="0s", duration=dur, hasAudio="1",
                          audioSources="1", audioChannels=str(int(a["track"].get("channels") or 2)),
                          audioRate=str(sr))
    ET.SubElement(asset, "media-rep", kind="original-media",
                  src=_common.file_url(_common.audio_source(a, audio_path)))

    event = ET.SubElement(ET.SubElement(root, "library"), "event", name="STRATA")
    project = ET.SubElement(event, "project", name=name)
    seq = ET.SubElement(project, "sequence", format="r1", duration=dur, tcStart="0s", tcFormat="NDF",
                        audioLayout="stereo", audioRate=AUDIO_RATES.get(sr, "48k"))
    spine = ET.SubElement(seq, "spine")
    clip = ET.SubElement(spine, "asset-clip", ref="r2", offset="0s", name=name, start="0s", duration=dur)
    _markers(clip, a)

    ET.indent(root)
    p = out_dir / "timeline.fcpxml"
    p.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'
                 + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    return [p]
