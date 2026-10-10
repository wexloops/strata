"""Beat/downbeat/tempo ensemble.

The reference grid is stitched window by window from whichever backend is best corroborated there. Other backends confirm its beats
(confidence), fill its gaps (insertion needs >= 2 agreeing backends), and vote on downbeats, which a
Viterbi pass over bar position turns into consistent bars.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
from scipy.ndimage import median_filter

TOL = 0.07  # standard beat-tracking F-measure window (s)
ALT_RATIOS = (0.5, 2.0, 2 / 3, 1.5)
WINDOW = 12.0  # s, reference-selection window
AGREEMENT_POWER = 4


def empty_tempo() -> dict:
    return {"bpm": 0.0, "confidence": 0.0, "stable": False, "meter": 4, "alternatives": [], "map": []}


def _near(arr: np.ndarray, t: float, tol: float = TOL) -> bool:
    if arr.size == 0:
        return False
    i = np.searchsorted(arr, t)
    best = min(abs(arr[j] - t) for j in (i - 1, i) if 0 <= j < arr.size)
    return best <= tol


def f_measure(a: np.ndarray, b: np.ndarray) -> float:
    """Beat-tracking F-measure of a against b within TOL (symmetric)."""
    if a.size == 0 or b.size == 0:
        return 0.0
    p = np.mean([_near(b, t) for t in a])
    r = np.mean([_near(a, t) for t in b])
    return float(2 * p * r / (p + r)) if p + r else 0.0


def _ibi(a: np.ndarray) -> float:
    return float(np.median(np.diff(a))) if a.size >= 3 else 0.0


def pair_agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Agreement in the spirit of AMLt: same tempo counts even off-beat; metrical-level errors are penalized.

    phase = best F-measure of `a` against `b` or `b` shifted by half a beat (off-beat lock);
    tempo = 1 when the median intervals match within 5%, 0.5 at double/half time, else 0.25.
    """
    ia, ib = _ibi(a), _ibi(b)
    if not ia or not ib:
        return f_measure(a, b)
    phase = max(f_measure(a, b), f_measure(a, b + ib / 2))
    ratio = ia / ib
    if abs(ratio - 1) <= 0.05:
        tempo = 1.0
    elif any(abs(ratio / r - 1) <= 0.05 for r in (0.5, 2.0)):
        tempo = 0.5
    else:
        tempo = 0.25
    return phase * tempo


def choose_reference(usable: dict[str, np.ndarray], w: dict[str, float]) -> str:
    """Highest weight x (mean agreement with the other backends) ** AGREEMENT_POWER.

    The power makes agreement dominate: when everyone agrees weight decides; a backend the
    others don't corroborate (wrong metrical level, lost section) loses even with more weight.
    """
    if len(usable) == 1:
        return next(iter(usable))
    score = {}
    for k, arr in usable.items():
        others = [pair_agreement(arr, o) for j, o in usable.items() if j != k]
        score[k] = w[k] * float(np.mean(others)) ** AGREEMENT_POWER
    return max(score, key=lambda k: (score[k], w[k]))


def stitched_reference(usable: dict[str, np.ndarray], w: dict[str, float], duration: float,
                       win: float = WINDOW) -> tuple[np.ndarray, str]:
    """Pick the best-corroborated backend per window and stitch their beats.

    Models fail locally (a section of double time, a lost breakdown), so the reference is chosen
    window by window. Returns (stitched times, the backend that won the most windows).
    """
    if len(usable) == 1:
        k = next(iter(usable))
        return usable[k], k
    picks: list[str] = []
    out: list[float] = []
    for w0 in np.arange(0.0, max(duration, 1e-6), win):
        sub = {k: a[(a >= w0) & (a < w0 + win)] for k, a in usable.items()}
        sub = {k: a for k, a in sub.items() if a.size >= 2}
        if not sub:
            continue
        k = choose_reference(sub, w)
        picks.append(k)
        out.extend(sub[k].tolist())
    major = Counter(picks).most_common(1)[0][0]
    return np.array(sorted(out)), major


def dedupe(times: np.ndarray, frac: float = 0.25) -> np.ndarray:
    """Collapse beats closer than `frac` of the median interval into their mean."""
    if times.size < 3:
        return times
    gap = frac * float(np.median(np.diff(times)))
    out = [times[0]]
    for t in times[1:]:
        if t - out[-1] < gap:
            out[-1] = (out[-1] + t) / 2
        else:
            out.append(t)
    return np.array(out)


def _insert_gaps(ref: np.ndarray, others: dict[str, np.ndarray], duration: float) -> list[float]:
    """Beats the reference missed but >= 2 other backends agree on."""
    if len(others) < 2:
        return []
    ibi = float(np.median(np.diff(ref)))
    edges = np.concatenate([[-ibi], ref, [duration + ibi]])
    inserted = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a <= 1.5 * ibi:
            continue
        lo, hi = a + 0.5 * ibi, b - 0.5 * ibi
        pool = sorted(t for arr in others.values() for t in arr if lo <= t <= hi and 0 <= t <= duration)
        used: list[float] = []
        for t in pool:
            if any(abs(t - u) <= TOL for u in used):
                continue
            agree = [arr[np.argmin(np.abs(arr - t))] for arr in others.values() if _near(arr, t)]
            if len(agree) >= 2:
                used.append(t)
                inserted.append(float(np.mean(agree)))
    return inserted


def _meter(times: np.ndarray, downbeat_sets: list[np.ndarray]) -> int:
    spans = []
    for d in downbeat_sets:
        idx = [int(np.argmin(np.abs(times - t))) for t in d if _near(times, t)]
        spans += [b - a for a, b in zip(idx, idx[1:]) if 2 <= b - a <= 7]
    if not spans:
        return 4
    return Counter(spans).most_common(1)[0][0]


def _viterbi_positions(score: np.ndarray, m: int, p_reset: float = 1e-3) -> np.ndarray:
    """Most likely bar position (0 = downbeat) per beat given per-beat downbeat probability.

    Votes are squashed into [0.15, 0.85] so a single wrong vote costs less than a bar reset;
    a sustained phase shift (several bars of contrary votes) still wins.
    """
    n = len(score)
    score = 0.15 + 0.7 * score
    eps = 0.0
    emit = np.empty((n, m))
    emit[:, 0] = np.log(eps + score)
    emit[:, 1:] = np.log(eps + 1 - score)[:, None]
    trans = np.full((m, m), np.log(p_reset / max(m - 1, 1)))
    for s in range(m):
        trans[s, (s + 1) % m] = np.log(1 - p_reset)
    delta = emit[0].copy()
    back = np.zeros((n, m), dtype=int)
    for i in range(1, n):
        cand = delta[:, None] + trans
        back[i] = np.argmax(cand, axis=0)
        delta = cand[back[i], np.arange(m)] + emit[i]
    path = np.empty(n, dtype=int)
    path[-1] = int(np.argmax(delta))
    for i in range(n - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    return path


def merge_beats(cands: dict[str, dict], weights: dict[str, float], duration: float) -> tuple[list, list, dict]:
    usable = {k: np.sort(np.asarray(v.get("beats", []), float)) for k, v in cands.items() if len(v.get("beats", [])) >= 4}
    if not usable:
        return [], [], empty_tempo()
    w = {k: float(weights.get(k, 0.5)) for k in usable}
    stitched, ref_name = stitched_reference(usable, w, duration)
    ref = dedupe(stitched)
    others = {k: v for k, v in usable.items() if k != ref_name}

    inserted = _insert_gaps(ref, usable if len(usable) > 2 else others, duration)
    times = dedupe(np.sort(np.concatenate([ref, inserted]))) if inserted else ref
    total_w = sum(w.values())

    beats = []
    for t in times:
        votes = {k: _near(arr, t) for k, arr in usable.items()}
        conf = sum(w[k] for k, v in votes.items() if v) / total_w
        beats.append({"time": float(t), "bar": 0, "beat": 0, "downbeat": False, "confidence": round(conf, 3), "votes": votes})

    # Downbeats: weighted vote per beat, then Viterbi for consistent bars.
    down = {k: np.sort(np.asarray(cands[k].get("downbeats", []), float)) for k in usable if len(cands[k].get("downbeats", []))}
    meter = _meter(times, list(down.values()))
    if down:
        dw = sum(w[k] for k in down)
        score = np.array([sum(w[k] for k, d in down.items() if _near(d, t)) / dw for t in times])
    else:
        score = np.full(len(times), 0.5)
        score[0] = 0.9  # no evidence: assume the first beat is a downbeat
    pos = _viterbi_positions(score, meter)

    bar = 0
    for b, p in zip(beats, pos):
        if p == 0:
            bar += 1
        b["bar"], b["beat"], b["downbeat"] = bar, int(p) + 1, bool(p == 0)
    down_t = [b["time"] for b in beats if b["downbeat"]]
    bars = [{"index": i + 1, "start": t, "end": down_t[i + 1] if i + 1 < len(down_t) else float(duration)}
            for i, t in enumerate(down_t)]

    ibis = np.diff(times)
    ibi = float(np.median(ibis))
    bpm = 60.0 / ibi
    local = 60.0 / median_filter(ibis, size=min(8, len(ibis)), mode="nearest")
    stable = bool(np.mean(np.abs(local / bpm - 1) <= 0.02) >= 0.9)
    tmap_idx = [i for i, b in enumerate(beats[:-1]) if b["downbeat"]] or [0]
    tmap = [{"time": beats[i]["time"], "bpm": round(float(local[min(i, len(local) - 1)]), 2)} for i in tmap_idx]

    alts: dict[float, float] = {}
    for k, arr in others.items():
        ratio = float(np.median(np.diff(arr))) / ibi
        for r in ALT_RATIOS:
            if abs(ratio / r - 1) < 0.05:
                alt = round(bpm / r, 1)
                alts[alt] = alts.get(alt, 0) + w[k] / total_w
    tempo = {
        "bpm": round(bpm, 2),
        "confidence": round(float(np.mean([b["confidence"] for b in beats])), 3),
        "stable": stable,
        "meter": int(meter),
        "alternatives": [{"bpm": k, "support": round(v, 3)} for k, v in sorted(alts.items(), key=lambda x: -x[1])],
        "map": tmap,
    }
    return beats, bars, tempo
