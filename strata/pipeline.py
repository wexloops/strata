"""Run backends (cached), then ensembles + derive into one validated analysis.json."""
from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio as audio_mod
from .backends.base import Backend, Context, registry
from .derive import derive
from .ensemble.beats import merge_beats
from .ensemble.categorical import NOTES, camelot, key_label, vote_chords, vote_key
from .ensemble.segments import merge_sections
from .library import Library
from .schema import empty_analysis, n_frames, round_floats, validate

Progress = Callable[[dict], None]

for _noisy in ("httpx", "httpx2", "huggingface_hub", "urllib3", "faster_whisper"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


class SchemaError(RuntimeError):
    pass


def _device(device: str | None) -> str:
    if device:
        return device
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _emit(progress: Progress | None, stage: str, frac: float, message: str = "") -> None:
    if progress:
        progress({"stage": stage, "progress": round(frac, 3), "message": message})


def run_backends(ctx: Context, backends: list[Backend], force: bool = False, progress: Progress | None = None) -> list[dict]:
    prov = []
    tid = ctx.track["id"]
    for i, b in enumerate(backends):
        _emit(progress, b.name, i / max(len(backends), 1), f"running {b.name}")
        rec = {"backend": b.name, "dimension": ",".join(b.dimensions), "version": b.version(), "license": b.license,
               "nc": b.nc, "ok": False, "error": None, "seconds": 0.0, "cached": False}
        if not b.available():
            rec["error"] = getattr(b, "unavailable_reason", None) or ("not installed" + (" (optional extra)" if b.optional else ""))
            prov.append(rec)
            continue
        key = f"{b.name}@{b.version()}"
        cached = None if force else ctx.lib.cache_get(tid, key)
        t0 = time.perf_counter()
        if cached is not None:
            b.restore(ctx, cached)
            ctx.results[b.name] = cached
            rec.update(ok=True, cached=True)
        else:
            try:
                r = b.run(ctx)
                ctx.lib.cache_put(tid, key, r)
                ctx.results[b.name] = r
                rec["ok"] = True
            except Exception as e:  # one backend never kills the run
                rec["error"] = f"{type(e).__name__}: {e}"[:500]
                log = ctx.lib.track_dir(tid) / "errors.log"
                with open(log, "a") as f:
                    f.write(f"--- {b.name}\n{traceback.format_exc()}\n")
        rec["seconds"] = round(time.perf_counter() - t0, 2)
        prov.append(rec)
    return prov


def _by_dim(ctx: Context, backends: list[Backend], dim: str) -> tuple[dict, dict]:
    cands, weights = {}, {}
    for b in backends:
        if dim in b.weights and b.name in ctx.results:
            cands[b.name] = ctx.results[b.name]
            weights[b.name] = b.weights[dim]
    return cands, weights


def _first(ctx: Context, name: str) -> dict:
    return ctx.results.get(name) or {}


def _local_keys(a: dict, windows: list[dict]) -> None:
    """Per-section key from windowed 24-class template scores."""
    for s in a["sections"]:
        acc = np.zeros(24)
        for w in windows:
            ov = min(s["end"], w["end"]) - max(s["start"], w["start"])
            if ov > 0:
                acc += ov * np.asarray(w["scores"])
        if acc.any():
            k = int(np.argmax(acc))
            tonic, mode = NOTES[k % 12], ("major" if k < 12 else "minor")
            s["key"] = key_label(tonic, mode)


def _section_tags(a: dict, windows: list[dict], labels: list[str], top: int = 3) -> None:
    for s in a["sections"]:
        acc = np.zeros(len(labels))
        for w in windows:
            ov = min(s["end"], w["end"]) - max(s["start"], w["start"])
            if ov > 0:
                acc += ov * np.asarray(w["scores"])
        if acc.any():
            s["tags"] = [labels[i] for i in np.argsort(-acc)[:top]]


def assemble(ctx: Context, backends: list[Backend], profile: str, fps: int, provenance: list[dict]) -> dict:
    dur = ctx.track["duration"]
    a = empty_analysis(ctx.track, profile, fps)
    a["provenance"] = provenance

    cands, w = _by_dim(ctx, backends, "beats")
    a["beats"], a["bars"], a["tempo"] = merge_beats(cands, w, dur)

    cands, w = _by_dim(ctx, backends, "sections")
    a["sections"] = merge_sections(cands, w, a["beats"], dur)

    cands, w = _by_dim(ctx, backends, "key")
    a["key"] = vote_key(cands, w)
    _local_keys(a, _first(ctx, "key_template").get("windows", []))

    cands, w = _by_dim(ctx, backends, "chords")
    a["chords"] = vote_chords(cands, w, a["beats"], dur)

    n = n_frames(dur, fps)
    for r in ctx.results.values():
        for name, arr in (r.get("curves") or {}).items():
            if name in a["curves"]["data"]:
                arr = list(arr)[:n] + [0.0] * max(0, n - len(arr))
                a["curves"]["data"][name] = arr
    feats = _first(ctx, "features")
    a["dynamics"].update({k: feats[k] for k in ("lufs", "lra", "peak_db", "silences") if k in feats})

    drums = _first(ctx, "drums_bands")
    for k in ("kick", "snare", "hat", "onsets"):
        a["events"][k] = drums.get(k, [])
    a["notes"].update({k: v for k, v in _first(ctx, "notes_basicpitch").items() if k in a["notes"]})
    a["vocals"]["activity"] = _first(ctx, "vocals_activity").get("activity", [])
    a["vocals"]["lyrics"] = _first(ctx, "lyrics_whisper").get("lyrics", [])

    tags = _first(ctx, "tags_clap")
    for k in ("genre", "mood", "instruments"):
        a["tags"][k] = tags.get(k, [])
    if tags.get("windows"):
        _section_tags(a, tags["windows"], tags["labels"])

    return derive(a)


def analyze(path: str | Path, profile: str = "full", fps: int = 30, device: str | None = None,
            progress: Progress | None = None, only: list[Backend] | None = None, lib: Library | None = None,
            force: bool = False) -> dict:
    lib = lib or Library()
    path = Path(path)
    _emit(progress, "load", 0.0, f"loading {path.name}")
    info = audio_mod.track_info(path)
    y, sr = audio_mod.load(path)
    ctx = Context(path=path, track=info, audio=y, sr=sr, lib=lib, device=_device(device), fps=fps)
    backends = only if only is not None else registry(profile)
    prov = run_backends(ctx, backends, force=force, progress=progress)
    _emit(progress, "ensemble", 0.95, "voting + deriving")
    a = assemble(ctx, backends, profile, fps, prov)
    round_floats(a)
    errs = validate(a)
    if errs:
        raise SchemaError("; ".join(errs))
    lib.save_analysis(a)
    _emit(progress, "done", 1.0, "done")
    return a
