"""Backend protocol + registry. One backend = one model/algorithm contributing to one or more dimensions."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..library import Library


@dataclass
class Context:
    path: Path
    track: dict
    audio: np.ndarray  # (channels, samples) float32 at sr
    sr: int
    lib: Library
    device: str = "cpu"
    fps: int = 30
    stems: dict[str, Path] = field(default_factory=dict)
    results: dict[str, dict] = field(default_factory=dict)  # backend name -> result

    @property
    def mono(self) -> np.ndarray:
        if not hasattr(self, "_mono"):
            self._mono = self.audio.mean(axis=0)
        return self._mono

    def stem(self, name: str, sr: int | None = None) -> np.ndarray | None:
        """Mono stem audio, or None if stems weren't separated."""
        p = self.stems.get(name)
        if p is None or not Path(p).exists():
            return None
        import librosa
        y, _ = librosa.load(str(p), sr=sr or self.sr, mono=True)
        return y

    def harmonic(self) -> np.ndarray:
        """Drumless mix when stems exist (better for key/chords), else the full mix."""
        parts = [self.stem(n) for n in ("bass", "vocals", "other")]
        parts = [p for p in parts if p is not None]
        if not parts:
            return self.mono
        n = min(len(p) for p in parts)
        return np.sum([p[:n] for p in parts], axis=0)


class Backend:
    name: str = ""
    license: str = ""
    nc: bool = False
    weights: dict[str, float] = {}  # dimension -> vote weight
    requires: tuple[str, ...] = ()  # backend names that must run first (ordering only)
    optional: bool = False  # extra-only backends: skipped quietly when unavailable

    @property
    def dimensions(self) -> tuple[str, ...]:
        return tuple(self.weights)

    def available(self) -> bool:
        return True

    def version(self) -> str:
        return "1"

    def run(self, ctx: Context) -> dict:
        raise NotImplementedError

    def restore(self, ctx: Context, data: dict) -> None:
        """Re-apply side effects of a cached result (e.g. stem paths)."""


BACKEND_MODULES = [
    "allin1_backend", "demucs_backend", "beats_beatthis", "beats_librosa", "beats_madmom",
    "sections_ssm", "key_skey", "key_template", "key_madmom", "chords_btc", "chords_template", "chords_madmom",
    "features", "drums_bands", "notes_basicpitch", "vocals_activity", "tags_clap", "lyrics_whisper",
]


def all_backends() -> list[Backend]:
    out = []
    for m in BACKEND_MODULES:
        mod = importlib.import_module(f"strata.backends.{m}")
        out.append(mod.BACKEND)
    return out


def toposort(backends: list[Backend]) -> list[Backend]:
    by = {b.name: b for b in backends}
    done: list[Backend] = []
    seen: set[str] = set()

    def visit(b: Backend):
        if b.name in seen:
            return
        seen.add(b.name)
        for r in b.requires:
            if r in by:
                visit(by[r])
        done.append(b)

    for b in backends:
        visit(b)
    return done


def registry(profile: str = "full", include_optional: bool = True) -> list[Backend]:
    out = []
    for b in all_backends():
        if profile == "commercial-safe" and b.nc:
            continue
        if b.optional and not include_optional:
            continue
        out.append(b)
    return toposort(out)
