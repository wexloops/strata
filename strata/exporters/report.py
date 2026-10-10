"""report.html: one self-contained file. Uses the web UI's report template when built, else a static SVG page."""
from __future__ import annotations

import html
import json
from pathlib import Path

from ..schema import STEM_COLORS, section_color
from . import _common
from .midi import _root

TEMPLATE = Path(__file__).resolve().parent.parent / "web" / "report_template.html"
PLACEHOLDER = "__STRATA_DATA__"
W, PAD = 1200, 16


def embed_json(a: dict) -> str:
    """JSON safe inside <script type="application/json">: no '<', '>', '&', U+2028/2029 left raw."""
    s = json.dumps(a, ensure_ascii=False, separators=(",", ":"))
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        s = s.replace(ch, esc)
    return s


def chord_color(root: str | None, quality: str | None) -> str:
    """Hue = root on the circle of fifths; lightness = quality (maj light, min dark)."""
    pc = _root(root)
    if pc is None or quality == "N":
        return "#2A2A33"
    light = 38 if (quality or "").startswith("min") or quality == "dim" else 68 if quality in ("maj", "maj7") else 54
    return f"hsl({pc * 7 % 12 * 30},70%,{light}%)"


def _x(t: float, dur: float) -> float:
    return round(PAD + (W - 2 * PAD) * t / dur, 2) if dur > 0 else PAD


def _lane(y: int, h: int, label: str, body: list[str]) -> str:
    return (f'<g transform="translate(0,{y})"><text x="{PAD}" y="-4" class="lane">{html.escape(label)}</text>'
            f'<rect x="{PAD}" y="0" width="{W - 2 * PAD}" height="{h}" class="bg"/>{"".join(body)}</g>')


def _svg(a: dict) -> str:
    dur = float(a["track"]["duration"]) or 1.0
    sections = [
        f'<rect x="{_x(s["start"], dur)}" y="0" width="{max(0.5, _x(s["end"], dur) - _x(s["start"], dur))}" height="36" '
        f'fill="{html.escape(s.get("color") or section_color(s["label"], i))}" opacity="{0.45 + 0.55 * s.get("confidence", 1):.2f}">'
        f'<title>{html.escape(s["label"])} {s["start"]:.2f}-{s["end"]:.2f}s</title></rect>'
        f'<text x="{_x(s["start"], dur) + 4}" y="23" class="sl">{html.escape(s["label"])}</text>'
        for i, s in enumerate(a["sections"])]
    beats = [f'<line x1="{_x(b["time"], dur)}" x2="{_x(b["time"], dur)}" y1="{0 if b.get("downbeat") else 8}" '
             f'y2="20" class="{"db" if b.get("downbeat") else "bt"}"/>' for b in a["beats"]]
    chords = [
        f'<rect x="{_x(c["start"], dur)}" y="0" width="{max(0.5, _x(c["end"], dur) - _x(c["start"], dur))}" height="24" '
        f'fill="{chord_color(c.get("root"), c.get("quality"))}"><title>{html.escape(c["label"])}</title></rect>'
        for c in a["chords"]]
    curves = a["curves"]
    name = "loudness" if "loudness" in curves["data"] else (curves["names"] or [None])[0]
    vals = (curves["data"].get(name) or []) if name else []
    step = max(1, len(vals) // 1200)  # at most ~1200 points
    pts = " ".join(f"{_x(i / curves['fps'], dur)},{round(60 - 60 * min(1.0, max(0.0, vals[i])), 2)}"
                   for i in range(0, len(vals), step))
    energy = [f'<polyline points="{pts}" fill="none" stroke="{STEM_COLORS["vocals"]}" stroke-width="1.2"/>'] if pts else []
    drops = [f'<line x1="{_x(d["time"], dur)}" x2="{_x(d["time"], dur)}" y1="-120" y2="220" class="drop"/>'
             for d in a["dynamics"]["drops"]]
    body = (_lane(20, 36, "sections", sections) + _lane(80, 20, "beats", beats)
            + _lane(124, 24, "chords", chords) + _lane(172, 60, f"energy ({name})", energy)
            + f'<g transform="translate(0,100)">{"".join(drops)}</g>')
    return f'<svg viewBox="0 0 {W} 248" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">{body}</svg>'


CSS = """
body{margin:0;background:#0b0b10;color:#e8e8f0;font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1240px;margin:0 auto;padding:28px 20px}
h1{font-size:22px;margin:0 0 4px}.meta{color:#9a9ab0;margin-bottom:18px}
.lane{fill:#9a9ab0;font-size:11px}.bg{fill:#16161e}.sl{fill:#0b0b10;font-size:12px;font-weight:600}
.db{stroke:#e8e8f0;stroke-width:1}.bt{stroke:#55556a;stroke-width:.6}.drop{stroke:#FF2A2A;stroke-dasharray:3 3}
table{border-collapse:collapse;margin-top:22px;width:100%}td,th{padding:4px 10px;text-align:left;border-bottom:1px solid #22222c}
th{color:#9a9ab0;font-weight:500}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
"""


def _fallback(a: dict) -> str:
    t, k, d = a["tempo"], a["key"], a["dynamics"]
    meta = [f"{t.get('bpm', 0):.1f} BPM", k.get("label") or "key ?", f"{a['track']['duration']:.1f}s"]
    if d.get("lufs") is not None:
        meta.append(f"{d['lufs']:.1f} LUFS")
    rows = "".join(
        f'<tr><td><span class="sw" style="background:{html.escape(s.get("color") or section_color(s["label"], i))}"></span>'
        f'{html.escape(s["label"])}</td><td>{s["start"]:.2f}</td><td>{s["end"]:.2f}</td>'
        f'<td>{s.get("energy", 0):.2f}</td><td>{html.escape(s.get("key") or "")}</td></tr>'
        for i, s in enumerate(a["sections"]))
    title = html.escape(_common.title(a))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>STRATA: {title}</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><main>'
            f'<h1>{title}</h1><div class="meta">{html.escape(" · ".join(meta))}</div>{_svg(a)}'
            f'<table><tr><th>section</th><th>start</th><th>end</th><th>energy</th><th>key</th></tr>{rows}</table>'
            f'</main><script id="strata-data" type="application/json">{embed_json(a)}</script></body></html>\n')


def export_report(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if TEMPLATE.exists():
        doc = TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, embed_json(a), 1)
    else:
        doc = _fallback(a)
    p = out_dir / "report.html"
    p.write_text(doc, encoding="utf-8")
    return [p]
