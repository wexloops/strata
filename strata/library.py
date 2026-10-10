"""On-disk library: $STRATA_HOME/library/<track id>/{analysis.json, stems/, cache/, exports/}."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path


TRACK_ID = re.compile(r"[0-9a-f]{16}")


def strata_home() -> Path:
    return Path(os.environ.get("STRATA_HOME", Path.home() / ".strata"))


def _safe(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@-]", "_", key)


class Library:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else strata_home() / "library"
        self.root.mkdir(parents=True, exist_ok=True)

    def track_dir(self, track_id: str) -> Path:
        d = self.root / track_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stems_dir(self, track_id: str) -> Path:
        d = self.track_dir(track_id) / "stems"
        d.mkdir(exist_ok=True)
        return d

    def exports_dir(self, track_id: str) -> Path:
        d = self.track_dir(track_id) / "exports"
        d.mkdir(exist_ok=True)
        return d

    def _cache_path(self, track_id: str, key: str) -> Path:
        d = self.track_dir(track_id) / "cache"
        d.mkdir(exist_ok=True)
        return d / f"{_safe(key)}.json"

    def cache_get(self, track_id: str, key: str) -> dict | None:
        p = self._cache_path(track_id, key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return None

    def cache_put(self, track_id: str, key: str, data: dict) -> None:
        p = self._cache_path(track_id, key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(p)

    def analysis_path(self, track_id: str) -> Path:
        return self.track_dir(track_id) / "analysis.json"

    def save_analysis(self, a: dict) -> Path:
        p = self.analysis_path(a["track"]["id"])
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(a, ensure_ascii=False))
        tmp.replace(p)
        return p

    def load_analysis(self, track_id: str) -> dict:
        return json.loads(self.analysis_path(track_id).read_text())

    def delete(self, track_id: str) -> bool:
        """Remove STRATA's data for a track (analysis, stems, cache, exports). Never touches source audio."""
        if not TRACK_ID.fullmatch(track_id):
            raise ValueError(f"not a track id: {track_id!r}")
        d = self.root / track_id
        if not d.is_dir():
            return False
        shutil.rmtree(d)
        return True

    def ensure_demo(self, demo_dir: Path) -> str | None:
        """Seed an empty library with the bundled demo (precomputed analysis, no GPU needed)."""
        src = demo_dir / "analysis.json"
        if not src.exists() or any(self.root.glob("*/analysis.json")):
            return None
        a = json.loads(src.read_text())
        a["track"]["path"] = str((demo_dir / Path(a["track"]["path"]).name).resolve())
        self.save_analysis(a)
        return a["track"]["id"]

    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir()):
            p = d / "analysis.json"
            if p.exists():
                try:
                    a = json.loads(p.read_text())
                except json.JSONDecodeError:
                    continue
                out.append({
                    "id": d.name,
                    "title": a["track"]["title"],
                    "duration": a["track"]["duration"],
                    "bpm": a["tempo"]["bpm"],
                    "key": a["key"]["label"],
                    "created": a["strata"]["created"],
                })
        return out
