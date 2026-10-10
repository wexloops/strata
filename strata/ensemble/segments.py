"""Section ensemble: cluster boundary candidates, weighted vote, snap to downbeats, label by overlap."""
from __future__ import annotations

import numpy as np

EDGE = 1.0  # ignore boundaries this close to the track edges (s)
MIN_SECTION = 4.0  # shorter sections are absorbed by their neighbor (s)
NON_LABELS = {"start", "end"}


def _candidates(c: dict, duration: float) -> tuple[list[float], list[tuple[float, float, str]]]:
    """Normalize a backend result to (interior boundaries, labeled segments)."""
    if "segments" in c:
        segs = [(float(s["start"]), float(s["end"]), s["label"]) for s in c["segments"]]
        bounds = [s for s, _, _ in segs] + [e for _, e, _ in segs]
    else:
        bounds = [float(b) for b in c.get("boundaries", [])]
        edges = [0.0] + sorted(bounds) + [duration]
        labels = c.get("labels") or []
        segs = [(a, b, labels[i] if i < len(labels) else "section") for i, (a, b) in enumerate(zip(edges[:-1], edges[1:]))]
    bounds = sorted({round(b, 3) for b in bounds if EDGE < b < duration - EDGE})
    return bounds, segs


def _overlap_label(start: float, end: float, segs: list[tuple[float, float, str]]) -> str | None:
    best, best_ov = None, 0.0
    for a, b, lab in segs:
        if lab in NON_LABELS:
            continue
        ov = min(end, b) - max(start, a)
        if ov > best_ov:
            best, best_ov = lab, ov
    return best


def merge_sections(cands: dict[str, dict], weights: dict[str, float], beats: list[dict], duration: float) -> list[dict]:
    parsed = {k: _candidates(v, duration) for k, v in cands.items()}
    parsed = {k: v for k, v in parsed.items() if v[0] or v[1]}
    times = np.array([b["time"] for b in beats]) if beats else np.array([])
    ibi = float(np.median(np.diff(times))) if times.size > 1 else 0.5
    tol = max(0.5, ibi)
    total_w = sum(weights.get(k, 0.5) for k in parsed)

    pts = sorted((t, k) for k, (bounds, _) in parsed.items() for t in bounds)
    clusters: list[list[tuple[float, str]]] = []
    for t, k in pts:
        if clusters and t - clusters[-1][0][0] <= tol:
            clusters[-1].append((t, k))
        else:
            clusters.append([(t, k)])

    downs = np.array([b["time"] for b in beats if b.get("downbeat")])
    kept: list[tuple[float, dict]] = []
    for cl in clusters:
        by = {}
        for t, k in cl:
            by.setdefault(k, t)
        score = sum(weights.get(k, 0.5) for k in by)
        if total_w == 0 or score < 0.5 * total_w:
            continue
        t = sum(weights.get(k, 0.5) * by[k] for k in by) / score
        if downs.size:
            j = int(np.argmin(np.abs(downs - t)))
            if abs(downs[j] - t) <= ibi:
                t = float(downs[j])
        votes = {k: (weights.get(k, 0.5) if k in by else 0.0) for k in parsed}
        if kept and t - kept[-1][0] < tol:
            continue
        kept.append((t, {"score": score / total_w, "votes": votes}))

    # Absorb slivers (e.g. a 1 s tail before the end) into the neighboring section.
    changed = True
    while changed and kept:
        changed = False
        edges = [0.0] + [t for t, _ in kept] + [float(duration)]
        for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
            if b - a < MIN_SECTION:
                # section i starts at kept[i-1]; dropping that boundary merges it into the previous one
                kept.pop(i - 1 if i > 0 else 0)
                changed = True
                break
    edges = [0.0] + [t for t, _ in kept] + [float(duration)]
    labeled = [k for k, v in cands.items() if "segments" in v and k in parsed]
    label_src = max(labeled, key=lambda k: weights.get(k, 0.5)) if labeled else (next(iter(parsed)) if parsed else None)

    sections = []
    for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        meta = kept[i - 1][1] if i > 0 else {"score": 1.0, "votes": {k: weights.get(k, 0.5) for k in parsed}}
        label = _overlap_label(a, b, parsed[label_src][1]) if label_src else None
        sections.append({
            "index": i, "start": round(a, 3), "end": round(b, 3), "label": label or "section",
            "confidence": round(min(1.0, meta["score"]), 3), "energy": 0.0, "color": "", "key": None, "tags": [],
            "votes": meta["votes"],
        })
    return sections
