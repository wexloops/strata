import numpy as np

from strata.ensemble.beats import merge_beats
from strata.ensemble.segments import merge_sections
from strata.ensemble.categorical import normalize_chord, vote_key, vote_chords, chord_name

rng = np.random.default_rng(0)


def grid(bpm, n, t0=0.5, jitter=0.0):
    t = t0 + np.arange(n) * 60 / bpm
    return list(t + rng.normal(0, jitter, n)) if jitter else list(t)


# ---- beats -------------------------------------------------------------------------------

def test_agreeing_backends_high_confidence():
    ref = grid(120, 64)
    cands = {"beat_this": {"beats": ref, "downbeats": ref[::4]},
             "allin1": {"beats": grid(120, 64, jitter=0.01), "downbeats": ref[::4]}}
    beats, bars, tempo = merge_beats(cands, {"beat_this": 1.0, "allin1": 0.8}, 40.0)
    assert len(beats) == 64
    assert np.mean([b["confidence"] for b in beats]) > 0.9
    assert abs(tempo["bpm"] - 120) < 0.5 and tempo["stable"]
    assert beats[0]["votes"] == {"beat_this": True, "allin1": True}


def test_gap_inserted_when_two_others_agree():
    full = grid(120, 64)
    ref = full[:20] + full[25:]
    cands = {"beat_this": {"beats": ref, "downbeats": []},
             "allin1": {"beats": full, "downbeats": []},
             "librosa_beats": {"beats": full, "downbeats": []}}
    beats, _, _ = merge_beats(cands, {"beat_this": 1.0, "allin1": 0.8, "librosa_beats": 0.3}, 40.0)
    assert len(beats) == 64
    inserted = [b for b in beats if not b["votes"]["beat_this"]]
    assert len(inserted) == 5


def test_half_time_alternative():
    cands = {"beat_this": {"beats": grid(120, 64), "downbeats": []},
             "librosa_beats": {"beats": grid(60, 32), "downbeats": []}}
    _, _, tempo = merge_beats(cands, {"beat_this": 1.0, "librosa_beats": 0.3}, 40.0)
    assert abs(tempo["bpm"] - 120) < 0.5
    assert any(abs(a["bpm"] - 60) < 1 for a in tempo["alternatives"])


def test_viterbi_fixes_downbeat_errors():
    b = grid(120, 64)
    downs = b[::4]
    noisy = [d for i, d in enumerate(downs) if i not in (3, 7)] + [b[30], b[45]]
    cands = {"beat_this": {"beats": b, "downbeats": sorted(noisy)}}
    beats, bars, tempo = merge_beats(cands, {"beat_this": 1.0}, 40.0)
    assert tempo["meter"] == 4
    assert [x["time"] for x in beats if x["downbeat"]] == downs
    assert [x["beat"] for x in beats[:8]] == [1, 2, 3, 4, 1, 2, 3, 4]
    assert bars[0]["index"] == 1 and len(bars) == 16


def test_three_four():
    b = grid(90, 60)
    cands = {"beat_this": {"beats": b, "downbeats": b[::3]}}
    _, bars, tempo = merge_beats(cands, {"beat_this": 1.0}, 45.0)
    assert tempo["meter"] == 3 and len(bars) == 20


def test_no_reference_beats():
    beats, bars, tempo = merge_beats({"beat_this": {"beats": [], "downbeats": []}}, {"beat_this": 1.0}, 30.0)
    assert beats == [] and bars == [] and tempo["bpm"] == 0 and tempo["stable"] is False


# ---- sections ----------------------------------------------------------------------------

def _beats(bpm=120, n=200):
    t = grid(bpm, n, t0=0.0)
    return [{"time": x, "downbeat": i % 4 == 0} for i, x in enumerate(t)]


def test_boundary_voting_threshold():
    cands = {"allin1": {"segments": [{"start": 0, "end": 10, "label": "intro"}, {"start": 10, "end": 30.2, "label": "verse"},
                                     {"start": 30.2, "end": 50, "label": "chorus"}, {"start": 50, "end": 90, "label": "outro"}]},
             "ssm": {"boundaries": [10.3, 30.0, 70.0], "labels": ["A", "B", "C", "B"]}}
    secs = merge_sections(cands, {"allin1": 0.6, "ssm": 0.4}, _beats(), 90.0)
    starts = [s["start"] for s in secs]
    assert starts == [0.0, 10.0, 30.0, 50.0]
    assert [s["label"] for s in secs] == ["intro", "verse", "chorus", "outro"]
    assert secs[-1]["end"] == 90.0
    assert secs[1]["votes"] == {"allin1": 0.6, "ssm": 0.4}
    assert secs[3]["votes"]["ssm"] == 0.0


def test_snaps_to_downbeat():
    cands = {"ssm": {"boundaries": [16.4], "labels": ["A", "B"]}}
    secs = merge_sections(cands, {"ssm": 0.4}, _beats(), 40.0)
    assert secs[1]["start"] == 16.0  # downbeat every 2 s at 120 bpm
    assert [s["label"] for s in secs] == ["A", "B"]


def test_no_candidates_single_section():
    secs = merge_sections({}, {}, [], 40.0)
    assert len(secs) == 1 and secs[0]["label"] == "section" and secs[0]["end"] == 40.0


# ---- categorical -------------------------------------------------------------------------

def test_normalize_chord():
    assert normalize_chord("A:min7") == ("A", "min7")
    assert normalize_chord("Bb:maj") == ("A#", "maj")
    assert normalize_chord("N") == (None, "N")
    assert normalize_chord("C:hdim7") == ("C", "dim")
    assert normalize_chord("E:maj/3") == ("E", "maj")
    assert normalize_chord("F#") == ("F#", "maj")
    assert normalize_chord("G:sus4(b7)") == ("G", "sus4")
    assert chord_name("A", "min") == "Am" and chord_name("C", "maj") == "C" and chord_name(None, "N") == "N"


def test_vote_key():
    k = vote_key({"skey": {"label": "A minor", "confidence": 0.8}, "madmom_key": {"label": "A minor", "confidence": 0.7},
                  "template": {"label": "C major", "confidence": 0.9}}, {"skey": 1.0, "madmom_key": 0.9, "template": 0.4})
    assert k["label"] == "A minor" and k["camelot"] == "8A" and k["tonic"] == "A" and k["mode"] == "minor"
    assert 0 < k["confidence"] <= 1


def test_vote_chords_majority_and_merge():
    beats = [{"time": t} for t in np.arange(0, 8, 0.5)]
    a = {"chords": [{"start": 0, "end": 4, "label": "C:maj"}, {"start": 4, "end": 8, "label": "A:min"}]}
    b = {"chords": [{"start": 0, "end": 4, "label": "C:maj7"}, {"start": 4, "end": 8, "label": "A:min"}]}
    c = {"chords": [{"start": 0, "end": 8, "label": "C:maj7"}]}
    ch = vote_chords({"btc": a, "template": b, "madmom_chords": c}, {"btc": 1.0, "template": 0.3, "madmom_chords": 0.8}, beats, 8.0)
    assert [x["label"] for x in ch] == ["Cmaj7", "Am"]
    assert ch[0]["start"] == 0 and ch[0]["end"] == 4.0 and ch[1]["end"] == 8.0
    assert ch[0]["root"] == "C" and ch[0]["quality"] == "maj7"


def test_reference_chosen_by_consensus_not_weight():
    good = grid(120, 160)  # 80 s at 120
    half = [t for t in good if t < 40]
    bad = half + list(np.arange(40, 80, 0.25))  # top-weighted model goes double-time halfway
    cands = {"beat_this": {"beats": bad, "downbeats": []},
             "allin1": {"beats": grid(120, 160, jitter=0.01), "downbeats": good[::4]},
             "madmom_beats": {"beats": grid(120, 160, jitter=0.01), "downbeats": good[::4]},
             "librosa_beats": {"beats": grid(120, 160, jitter=0.01), "downbeats": []}}
    w = {"beat_this": 1.0, "allin1": 0.8, "madmom_beats": 0.8, "librosa_beats": 0.3}
    beats, _, tempo = merge_beats(cands, w, 80.0)
    assert abs(tempo["bpm"] - 120) < 1
    assert 150 <= len(beats) <= 170


def test_near_duplicate_beats_collapse():
    b = grid(120, 64)
    dup = sorted(b + [b[10] + 0.03, b[30] + 0.04])
    beats, _, _ = merge_beats({"beat_this": {"beats": dup, "downbeats": []}}, {"beat_this": 1.0}, 40.0)
    assert len(beats) == 64


def test_windowed_reference_with_three_backends():
    good = grid(120, 160)
    bad = [t for t in good if t < 40] + list(np.arange(40, 80, 0.25))
    cands = {"beat_this": {"beats": bad, "downbeats": []},
             "allin1": {"beats": grid(120, 160, jitter=0.01), "downbeats": good[::4]},
             "librosa_beats": {"beats": grid(120, 160, jitter=0.01), "downbeats": []}}
    beats, _, tempo = merge_beats(cands, {"beat_this": 1.0, "allin1": 0.8, "librosa_beats": 0.3}, 80.0)
    assert abs(tempo["bpm"] - 120) < 1 and tempo["stable"]
    assert 155 <= len(beats) <= 165
    early = [b for b in beats if b["time"] < 30]
    assert all(b["votes"]["beat_this"] for b in early)  # the strong model still owns the windows it gets right


def test_offbeat_locked_models_beat_a_double_time_model():
    on = grid(120, 160)
    off = [t + 0.25 for t in on]
    double = sorted(on + off)  # contains both phases -> naive F-measure prefers it
    cands = {"beat_this": {"beats": double, "downbeats": []},
             "allin1": {"beats": on, "downbeats": on[::4]},
             "librosa_beats": {"beats": off, "downbeats": []}}
    _, _, tempo = merge_beats(cands, {"beat_this": 1.0, "allin1": 0.8, "librosa_beats": 0.3}, 80.0)
    assert abs(tempo["bpm"] - 120) < 1


def test_sliver_sections_merge_into_neighbor():
    cands = {"allin1": {"segments": [{"start": 0, "end": 30, "label": "intro"}, {"start": 30, "end": 88.7, "label": "chorus"},
                                     {"start": 88.7, "end": 90, "label": "end"}]}}
    secs = merge_sections(cands, {"allin1": 0.6}, _beats(), 90.0)
    assert [s["label"] for s in secs] == ["intro", "chorus"] and secs[-1]["end"] == 90.0
    assert [s["index"] for s in secs] == [0, 1]
