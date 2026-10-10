"""premiere.xml: FCP7 xmeml v5 sequence (30 fps NDF) with the audio clip and sequence markers."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from . import _common

FPS = _common.FPS


def _sub(parent: ET.Element, tag: str, text=None, **attrib) -> ET.Element:
    el = ET.SubElement(parent, tag, attrib)
    if text is not None:
        el.text = str(text)
    return el


def _rate(parent: ET.Element) -> None:
    r = _sub(parent, "rate")
    _sub(r, "timebase", FPS)
    _sub(r, "ntsc", "FALSE")


def _audio_chars(parent: ET.Element, a: dict) -> None:
    sc = _sub(parent, "samplecharacteristics")
    _sub(sc, "depth", 16)
    _sub(sc, "samplerate", int(a["track"].get("sample_rate") or 48000))


def _file(parent: ET.Element, a: dict, src: str, n: int) -> None:
    f = _sub(parent, "file", id="file-1")
    _sub(f, "name", PurePosixPath(_common.native_path(src).replace("\\", "/")).name or _common.title(a))
    _sub(f, "pathurl", _common.file_url(src))
    _rate(f)
    _sub(f, "duration", n)
    au = _sub(_sub(f, "media"), "audio")
    _audio_chars(au, a)
    _sub(au, "channelcount", int(a["track"].get("channels") or 2))


def _clip(track: ET.Element, a: dict, src: str, n: int) -> None:
    c = _sub(track, "clipitem", id="clipitem-1")
    _sub(c, "name", _common.title(a))
    _sub(c, "enabled", "TRUE")
    _sub(c, "duration", n)
    _rate(c)
    for tag, val in (("start", 0), ("end", n), ("in", 0), ("out", n)):
        _sub(c, tag, val)
    _file(c, a, src, n)
    st = _sub(c, "sourcetrack")
    _sub(st, "mediatype", "audio")
    _sub(st, "trackindex", 1)


def _media(seq: ET.Element, a: dict, src: str, n: int) -> None:
    media = _sub(seq, "media")
    video = _sub(media, "video")
    vsc = _sub(_sub(video, "format"), "samplecharacteristics")
    _rate(vsc)
    _sub(vsc, "width", 1920)
    _sub(vsc, "height", 1080)
    _sub(vsc, "pixelaspectratio", "square")
    _sub(video, "track")
    audio = _sub(media, "audio")
    _sub(audio, "numOutputChannels", 2)
    _audio_chars(_sub(audio, "format"), a)
    _clip(_sub(audio, "track"), a, src, n)


def _marker(seq: ET.Element, m: dict) -> None:
    el = _sub(seq, "marker")
    _sub(el, "name", m["name"])
    _sub(el, "comment", m["comment"])
    _sub(el, "in", _common.frame(m["time"]))
    _sub(el, "out", _common.frame(m["end"]) if m["end"] is not None else -1)


def export_premiere(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = _common.total_frames(a)
    src = _common.audio_source(a, audio_path)
    root = ET.Element("xmeml", version="5")
    seq = _sub(root, "sequence", id="sequence-1")
    _sub(seq, "name", _common.title(a))
    _sub(seq, "duration", n)
    _rate(seq)
    tc = _sub(seq, "timecode")
    _rate(tc)
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "frame", 0)
    _sub(tc, "displayformat", "NDF")
    _media(seq, a, src, n)
    for m in _common.markers(a):
        _marker(seq, m)
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    p = out_dir / "premiere.xml"
    p.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body + "\n", encoding="utf-8")
    return [p]
