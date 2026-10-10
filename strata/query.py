"""Read-side helpers: resolve a track, and answer the questions editors / Claude actually ask."""
from __future__ import annotations

import bisect
import json
from pathlib import Path

from .audio import file_id
from .library import Library

AUDIO_EXT = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg", ".opus"}


class NotAnalyzed(LookupError):
    pass


def resolve(target: str, lib: Library | None = None) -> dict:
    """analysis.json path | audio path (looked up by content id) | track id | unique title substring."""
    lib = lib or Library()
    p = Path(target)
    if p.suffix.lower() == ".json" and p.exists():
        return json.loads(p.read_text())
    if p.suffix.lower() in AUDIO_EXT and p.exists():
        tid = file_id(p)
        if lib.analysis_path(tid).exists():
            return lib.load_analysis(tid)
        raise NotAnalyzed(f"{p.name} has not been analyzed yet: run `strata analyze \"{p}\"`")
    if lib.analysis_path(target).exists():
        return lib.load_analysis(target)
    hits = [t for t in lib.list() if target.lower() in t["title"].lower()]
    if len(hits) == 1:
        return lib.load_analysis(hits[0]["id"])
    if len(hits) > 1:
        raise LookupError(f"'{target}' matches {len(hits)} tracks: " + ", ".join(h["title"] for h in hits))
    raise LookupError(f"no analysis found for '{target}'")


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def _span(items: list[dict], t: float, start: str = "start", end: str = "end") -> dict | None:
    starts = [x[start] for x in items]
    i = bisect.bisect_right(starts, t) - 1
    if 0 <= i < len(items) and t < items[i][end]:
        return items[i]
    return None


def at(a: dict, t: float) -> dict:
    beats = a["beats"]
    bt = [b["time"] for b in beats]
    i = bisect.bisect_right(bt, t) - 1
    beat = beats[i] if i >= 0 else None
    fps = a["curves"]["fps"]
    frame = min(max(int(t * fps), 0), len(next(iter(a["curves"]["data"].values()), [0])) - 1)
    sec = _span(a["sections"], t)
    chord = _span(a["chords"], t)
    lyric = _span(a["vocals"]["lyrics"], t)
    near = {k: [e for e in v if abs(e["time"] - t) <= 0.05] for k, v in a["events"].items()}
    nxt = next((c for c in a["cues"] if c["time"] > t), None)
    phase = None
    if beat and i + 1 < len(beats):
        phase = round((t - beat["time"]) / (beats[i + 1]["time"] - beat["time"]), 3)
    return {
        "time": round(t, 3),
        "section": {k: sec[k] for k in ("index", "label", "start", "end", "energy", "key", "tags")} if sec else None,
        "bar": beat["bar"] if beat else None,
        "beat": beat["beat"] if beat else None,
        "beat_phase": phase,
        "chord": chord["label"] if chord else None,
        "key": (sec or {}).get("key") or a["key"]["label"],
        "curves": {k: v[frame] for k, v in a["curves"]["data"].items() if v},
        "events": {k: v for k, v in near.items() if v},
        "lyric": lyric["text"] if lyric else None,
        "next_cue": nxt,
    }


def cues(a: dict, min_strength: float = 0.0, types: list[str] | None = None) -> list[dict]:
    return [c for c in a["cues"] if c["strength"] >= min_strength and (not types or c["type"] in types)]


def beats(a: dict, t0: float = 0.0, t1: float | None = None, downbeats_only: bool = False) -> list[dict]:
    t1 = a["track"]["duration"] if t1 is None else t1
    return [b for b in a["beats"] if t0 <= b["time"] <= t1 and (b["downbeat"] or not downbeats_only)]


def sections(a: dict) -> list[dict]:
    return [{k: s[k] for k in ("index", "start", "end", "label", "energy", "confidence", "key", "tags", "color")}
            for s in a["sections"]]


def summary(a: dict) -> str:
    t, tempo, key, dyn = a["track"], a["tempo"], a["key"], a["dynamics"]
    lines = [f"{t['title']}  ({mmss(t['duration'])}, id {t['id']})"]
    alts = ", ".join(f"{x['bpm']}" for x in tempo["alternatives"])
    lines.append(f"tempo  {tempo['bpm']} BPM  {tempo['meter']}/4  {'steady' if tempo['stable'] else 'drifting'}"
                 f"  conf {tempo['confidence']}" + (f"  (alt: {alts})" if alts else ""))
    if key["label"]:
        lines.append(f"key    {key['label']}  [{key['camelot']}]  conf {key['confidence']}")
    if dyn["lufs"] is not None:
        lines.append(f"level  {dyn['lufs']} LUFS  LRA {dyn['lra']}  peak {dyn['peak_db']} dBFS")
    tags = a["tags"]
    if tags["genre"]:
        lines.append("tags   " + ", ".join(x["label"] for x in tags["genre"][:3]) + " | "
                     + ", ".join(x["label"] for x in tags["mood"][:3]))
    lines.append("sections")
    for s in a["sections"]:
        bar = "#" * int(round(s["energy"] * 10))
        lines.append(f"  {mmss(s['start']):>7}  {s['label']:<10} {bar:<10} {s['key'] or '':<9} {', '.join(s['tags'])}")
    if dyn["builds"]:
        lines.append("builds " + ", ".join(f"{mmss(b['start'])}-{mmss(b['end'])}" for b in dyn["builds"]))
    if dyn["drops"]:
        lines.append("drops  " + ", ".join(f"{mmss(d['time'])} ({d['strength']})" for d in dyn["drops"]))
    ev = a["events"]
    lines.append(f"hits   kick {len(ev['kick'])}  snare {len(ev['snare'])}  hat {len(ev['hat'])}  accents {len(ev['accents'])}")
    lines.append(f"chords {len(a['chords'])} changes   notes " + "  ".join(f"{k} {len(v)}" for k, v in a["notes"].items()))
    sung = sum(x["end"] - x["start"] for x in a["vocals"]["activity"])
    lines.append(f"vocals {sung / max(t['duration'], 1e-9):.0%} of track" + (f", {len(a['vocals']['lyrics'])} lyric lines" if a["vocals"]["lyrics"] else ""))
    strong = cues(a, 0.6)
    lines.append(f"cues   {len(a['cues'])} total, {len(strong)} strong (>=0.6)")
    bad = [p for p in a["provenance"] if not p["ok"]]
    ok = [p["backend"] for p in a["provenance"] if p["ok"]]
    lines.append(f"models {len(ok)} ok: {', '.join(ok)}")
    for p in bad:
        lines.append(f"       {p['backend']} skipped: {p['error']}")
    return "\n".join(lines)
