"""curves.png (16-bit gray, W=frames, H=curves) + curves.npy + curves.json for Notch/TD/shaders."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..schema import n_frames


def curve_matrix(a: dict) -> np.ndarray:
    """(names, frames) float32; rows padded with their last sample to the nominal frame count."""
    curves = a["curves"]
    n = max(1, n_frames(a["track"]["duration"], curves["fps"]))
    m = np.zeros((len(curves["names"]), n), dtype=np.float32)
    for i, k in enumerate(curves["names"]):
        row = np.asarray(curves["data"].get(k) or [0.0], dtype=np.float32)[:n]
        m[i, :len(row)] = row
        m[i, len(row):] = row[-1]
    return m


def export_texture(a: dict, out_dir: Path, audio_path: Path | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = curve_matrix(a)
    png, npy, meta = out_dir / "curves.png", out_dir / "curves.npy", out_dir / "curves.json"
    u16 = np.round(np.clip(m, 0.0, 1.0) * 65535).astype(np.uint16)
    Image.fromarray(u16).save(png)  # uint16 -> mode I;16
    np.save(npy, m)
    names = list(a["curves"]["names"])
    meta.write_text(json.dumps({"names": names, "fps": a["curves"]["fps"], "frames": int(m.shape[1]),
                                "rows": {k: i for i, k in enumerate(names)}, "range": [0, 1]}, indent=2))
    return [png, npy, meta]
