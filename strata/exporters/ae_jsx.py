"""strata_ae.jsx: ExtendScript building a comp, audio layer markers, and a STRATA null of curve sliders."""
from __future__ import annotations

import json
from pathlib import Path

from ..schema import n_frames
from . import _common

# AE default label colors (Preferences > Labels), index -> swatch.
AE_LABELS = {
    "1": "#B53838", "2": "#E4D84C", "3": "#A9CBC7", "4": "#E5BCC9", "5": "#A9A9CA", "6": "#E7C19E",
    "7": "#B3C7B3", "8": "#677DE0", "9": "#4AA44C", "10": "#8E2C9A", "11": "#E8920D", "12": "#7F452A",
    "13": "#F46DD6", "14": "#3DA2A5", "15": "#A89677", "16": "#1E401E",
}

SCRIPT = r"""// STRATA -> After Effects. File > Scripts > Run Script File...
(function () {
    var D = __DATA__;

    function setKeys(prop, times, values) {
        if (typeof prop.setValuesAtTimes === "function") {
            prop.setValuesAtTimes(times, values);
        } else {
            for (var k = 0; k < times.length; k++) { prop.setValueAtTime(times[k], values[k]); }
        }
    }

    function addMarkers(layer) {
        var mp = layer.property("ADBE Marker");
        for (var i = 0; i < D.markers.length; i++) {
            var m = D.markers[i];
            var mv = new MarkerValue(m.name);
            mv.comment = m.comment;
            mv.duration = m.duration;
            try { mv.label = m.label; } catch (e) {}
            mp.setValueAtTime(m.time, mv);
        }
    }

    app.beginUndoGroup("STRATA import");
    try {
        var comp = app.project.items.addComp(D.title, 1920, 1080, 1, D.duration, D.fps);
        var host = null;
        var f = new File(D.audio);
        if (D.audio && f.exists) {
            host = comp.layers.add(app.project.importFile(new ImportOptions(f)));
        } else {
            host = comp.layers.addNull(D.duration);
            host.name = "STRATA markers (audio not found)";
        }
        addMarkers(host);

        var nul = comp.layers.addNull(D.duration);
        nul.name = "STRATA";
        var times = [];
        for (var t = 0; t < D.frames; t++) { times.push(t / D.fps); }
        var fx = nul.property("ADBE Effect Parade");
        for (var c = 0; c < D.curves.length; c++) {
            var slider = fx.addProperty("ADBE Slider Control");
            slider.name = D.curves[c].name;
            setKeys(slider.property("ADBE Slider Control-0001"), times, D.curves[c].values);
        }
        comp.openInViewer();
    } finally {
        app.endUndoGroup();
    }
})();
"""


def _payload(a: dict, audio_path: Path | None) -> dict:
    curves = a["curves"]
    fps = int(curves["fps"])
    # Keys strictly inside the comp: frames whose time < duration.
    frames = max(1, min(n_frames(a["track"]["duration"], fps),
                        min((len(curves["data"][k]) for k in curves["names"]), default=0)))
    marks = []
    for m in _common.markers(a):
        dur = (m["end"] - m["time"]) if m["end"] is not None else 0.0
        marks.append({"time": round(m["time"], 3), "duration": round(max(0.0, dur), 3), "name": m["name"],
                      "comment": m["comment"], "label": int(_common.nearest_color(m["color"], AE_LABELS))})
    src = _common.audio_source(a, audio_path)
    return {
        "title": _common.title(a), "duration": float(a["track"]["duration"]), "fps": fps, "frames": frames,
        "audio": _common.native_path(src) if src else "", "markers": marks,
        "curves": [{"name": k, "values": curves["data"][k][:frames]} for k in curves["names"]],
    }


def export_ae(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    # ensure_ascii: every non-ASCII char (and U+2028/2029) becomes a \u escape, so ExtendScript
    # reads the literal correctly regardless of the file encoding it assumes.
    data = json.dumps(_payload(a, audio_path), ensure_ascii=True, separators=(",", ":"))
    p = out_dir / "strata_ae.jsx"
    p.write_text(SCRIPT.replace("__DATA__", data), encoding="utf-8")
    return [p]
