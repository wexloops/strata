# STRATA: design spec

**Date:** 2026-10-10 · **Owner:** David Wexler / HYPRGRPH · **License:** MIT (code)

## 1. Intent

STRATA is an open-source music analysis tool, shipped on the HYPRGRPH shelf. You drop in a track and get every musically meaningful layer back as one canonical data file: sections, tempo map, beats/bars, key, chords, drum hits, notes, dynamics, builds/drops, vocals, tags, and dense per-frame curves. The output looks like a beautiful color-coded breakdown and is ready to drive edits, live shows and code.

**Success:** on a real track, the timeline matches what you hear (sections, downbeats, drops, hits, key/chords), and the exports drive Premiere/Resolve/AE/Notch/Resolume/TD/Ableton/Claude with no manual cleanup.

**Constraints:**
- Runs locally on a single NVIDIA GPU (RTX 5090 reference), with a CPU fallback.
- Open source. Every backend carries a license tag, and a `commercial-safe` profile excludes non-commercial (NC) models.
- NC weights are never redistributed. Users install them explicitly.

**Non-goals (v1):**
- Real-time analysis of live input (Tixl's DeepAudioAnalyzer covers that).
- A desktop installer (Tauri wrap is v2).
- Training models.
- Writing Ableton .als files.

## 2. Architecture (approach A)

```
audio ──► pipeline ──► backends (per dimension, cached) ──► ensemble ──► derive ──► analysis.json
                                                                                         │
            CLI (strata) ◄── Claude skill                                                ├─► exporters (json/csv/midi/labels/xml/edl/jsx/texture/html)
            server (FastAPI) ◄── web UI (Vite+TS: timeline, visualizer, export, live) ───┤
                                                                                         └─► live OSC clock
```

**Python package `strata`** (py3.12, torch cu128):

| Module | Job |
|---|---|
| `audio.py` | load/resample (librosa/soundfile), sha256 id, duration |
| `library.py` | `$STRATA_HOME` (default `~/.strata`). `library/<id>/` holds `analysis.json`, `stems/*.flac`, `cache/<backend>.json`, `exports/` |
| `schema.py` | dataclasses + `SCHEMA_VERSION=1` + validation |
| `pipeline.py` | runs stages in dependency order, caches each backend result, records provenance (version, license, seconds, error). One failing backend never kills the run: it is recorded as `ok:false` and the ensemble proceeds without it. |
| `backends/` | one file per backend. Each implements the `Backend` protocol: `name, dimension, license, nc, weight, available(), run(ctx) -> dict` |
| `ensemble/` | beats, segments, categorical (key/chords) voting |
| `derive.py` | builds/drops, accents, ranked edit cues, section energy, colors |
| `exporters/` | one file per format, each a pure function of `analysis.json` |
| `live.py` | OSC clock: play/pause/seek/rate driven by UI or OSC input, 60 Hz emit |
| `server.py` | REST + SSE progress + WS transport, serves the built UI |
| `cli.py` | `analyze`, `export`, `query`, `serve`/`open`, `live`, `doctor`, `backends` |

## 3. Backend roster (v1)

The weight is the vote weight. NC means opt-in (`pip install strata[nc]`), excluded under `--profile commercial-safe`.

| Dimension | Backend | License (code/weights) | Weight | Notes |
|---|---|---|---|---|
| stems | demucs htdemucs | MIT/MIT | n/a | single shared run, reused by allin1 |
| beats | Beat This! | MIT/MIT | 1.0 | reference grid |
| beats | allin1 (vendored, PR #39 torch NA) | MIT/MIT | 0.8 | also gives downbeats + sections |
| beats | madmom RNN+DBN | BSD/CC BY-NC-SA | 0.8 | NC |
| beats | librosa beat_track | ISC | 0.3 | DSP baseline |
| sections | allin1 | MIT/MIT | 0.6 | functional labels |
| sections | SSM novelty (ours) | MIT | 0.4 | beat-synced chroma+MFCC self-similarity, checkerboard kernel |
| key | S-KEY (Deezer) | MIT/MIT | 1.0 | |
| key | Krumhansl-Schmuckler template (ours) | MIT | 0.4 | on the drumless mix |
| key | madmom CNN key | BSD/NC | 0.9 | NC |
| chords | BTC large-vocab (vendored) | MIT/MIT | 1.0 | |
| chords | chroma template (ours) | MIT | 0.3 | beat-synchronous |
| chords | madmom CNN+CRF | BSD/NC | 0.8 | NC |
| drums | band-onset classifier on drum stem (ours) | MIT | n/a | kick/snare/hat + strength |
| notes | basic-pitch (ONNX, `--no-deps`) | Apache/Apache | n/a | bass, vocals, other stems |
| dynamics | pyloudnorm + librosa | MIT/ISC | n/a | LUFS, LRA, short-term loudness |
| tags | LAION CLAP (larger_clap_music) | CC0/Apache | n/a | zero-shot genre/mood/instruments, global + per section |
| lyrics | faster-whisper word timestamps on vocal stem | MIT/MIT | n/a | optional extra `[lyrics]` |

**Plugin slots, not built in v1:** Music Flamingo / Qwen3-Omni captioner (semantic description), SongFormer (NC), Essentia (AGPL, subprocess). The `Backend` protocol supports them without core changes.

## 4. Ensemble

- **Beats.** The reference is the highest-weight available backend (Beat This!). For each reference beat, confidence = weighted share of the other backends with a beat within ±70 ms. Where the reference has a gap of more than 1.5 IBI and at least 2 other backends agree, the beat is inserted. Half- and double-time disagreement is detected from IBI ratios and reported as `tempo.alternatives`.
- **Downbeats.** Each backend votes per beat on "is downbeat". Meter M is the mode of downbeat spacing. A Viterbi pass over bar position (0..M-1, advance +1 mod M, reset penalty) enforces consistent bars.
- **Tempo.** Local BPM comes from consensus IBIs (median filter over 8 beats). Global BPM = 60 / median IBI. `stable` is true if 90% of local BPM values fall within 2% of global.
- **Sections.** Boundary candidates from all backends are clustered within max(0.5 s, 1 beat). Score = Σ weight. A boundary is kept if the score is ≥ 0.5, then snapped to the nearest downbeat when that is within 1 beat. Labels come from allin1 by overlap. Without allin1, labels come from SSM repetition clusters (A/B/C…). Every section gets energy (mean loudness percentile), a color from the fixed palette (§7), a confidence and per-backend votes.
- **Key / chords.** Labels are normalized to a shared vocabulary: root × {maj, min, 7, maj7, min7, dim, aug, sus2, sus4, N}. Key is a weighted vote over 24 classes using each backend's confidence. Local key is computed per section with the template backend. Chords are voted per beat. Contiguous identical beats merge, and changes snap to beats. The winning backend's full label is kept as `label_full`.

## 5. Derived layers

- **Builds/drops.** A build is a rising window (≥ 2 bars) in loudness + onset density + spectral centroid. A drop is a section or downbeat where short-term loudness jumps ≥ 3 LU (or the drum-stem RMS jumps ≥ 6 dB) after a build or a near-silence.
- **Accents.** Top-percentile onset strength coinciding with drum hits.
- **Cues.** A ranked list of edit points: section starts > drops > downbeats in high-energy sections > accents. Each has a `strength` from 0 to 1, so "cut on every cue above 0.6" is a single filter.

## 6. Canonical schema (`analysis.json`, schema 1)

Times are seconds (float, 3 dp). Every list is time-sorted.

```jsonc
{
  "strata": {"version": "0.1.0", "schema": 1, "created": "ISO8601", "profile": "full|commercial-safe"},
  "track": {"title": "", "path": "", "id": "sha256[:16]", "duration": 0, "sample_rate": 44100, "channels": 2},
  "provenance": [{"backend": "beat_this", "dimension": "beats", "version": "", "license": "MIT", "nc": false,
                  "ok": true, "error": null, "seconds": 0}],
  "tempo": {"bpm": 0, "confidence": 0, "stable": true, "meter": 4, "alternatives": [{"bpm": 0, "support": 0}],
            "map": [{"time": 0, "bpm": 0}]},
  "beats": [{"time": 0, "bar": 1, "beat": 1, "downbeat": true, "confidence": 0, "votes": {"beat_this": true}}],
  "bars": [{"index": 1, "start": 0, "end": 0}],
  "sections": [{"index": 0, "start": 0, "end": 0, "label": "chorus", "confidence": 0, "energy": 0, "color": "#hex",
                "key": "A minor", "tags": ["euphoric"], "votes": {"allin1": 1, "ssm": 0.8}}],
  "key": {"label": "A minor", "tonic": "A", "mode": "minor", "camelot": "8A", "confidence": 0,
          "votes": {"skey": {"label": "A minor", "confidence": 0}}},
  "chords": [{"start": 0, "end": 0, "label": "Am", "label_full": "A:min7", "root": "A", "quality": "min", "confidence": 0}],
  "events": {"kick": [{"time": 0, "strength": 0}], "snare": [], "hat": [], "onsets": [], "accents": []},
  "notes": {"bass": [{"start": 0, "end": 0, "pitch": 40, "velocity": 0}], "vocals": [], "other": []},
  "dynamics": {"lufs": 0, "lra": 0, "peak_db": 0, "builds": [{"start": 0, "end": 0, "strength": 0}],
               "drops": [{"time": 0, "strength": 0}], "silences": [{"start": 0, "end": 0}]},
  "vocals": {"activity": [{"start": 0, "end": 0}], "lyrics": [{"start": 0, "end": 0, "text": ""}]},
  "tags": {"genre": [{"label": "", "score": 0}], "mood": [], "instruments": []},
  "cues": [{"time": 0, "type": "section|drop|downbeat|accent", "strength": 0, "label": ""}],
  "curves": {"fps": 30, "names": ["loudness", "rms", "rms_drums", "rms_bass", "rms_vocals", "rms_other", "kick", "snare", "hat",
             "onset", "centroid", "flux", "band_0".."band_7"], "data": {"loudness": [0.0]}}
}
```

Curves are normalized to 0..1 per track (raw LUFS is in `dynamics`), with 4 dp, at `--fps` (default 30; 24/25/30/60). `stems` are referenced by library path, not embedded.

## 7. Color system

- **Section palette** (fixed per label, so colors read consistently across tracks): intro `#5B6CFF`, verse `#2EC4B6`, pre-chorus `#9BE564`, chorus `#FF3D7F`, drop `#FF2A2A`, build `#FFB627`, bridge `#B45CFF`, break/inst/solo `#00B8FF`, outro `#7A7AA8`, start/end/silence `#2A2A33`.
- **Stems:** drums `#FF7A1A`, bass `#8B5CFF`, vocals `#7DF9FF`, other `#F5F5F0`.
- **Chords:** hue = root on the circle of fifths, lightness = quality (maj light, min dark).
- **Confidence** maps to opacity everywhere.

## 8. Exporters (v1)

| Format | File | Target |
|---|---|---|
| JSON | `analysis.json` | everything, Claude |
| CSV | `beats/sections/chords/events/cues/curves.csv` | Sheets, TouchDesigner (curves CSV = CHOP) |
| MIDI | `strata.mid` | Ableton/any DAW: tempo map, section markers, chord blocks, GM drums (36/38/42), notes per stem, beat track |
| Labels | `audacity.txt`, `reaper_regions.csv` | Audacity, Reaper |
| Premiere | `premiere.xml` (FCP7 xmeml) | sequence + audio + markers (sections, drops, cues) |
| Resolve/FCP | `timeline.fcpxml` (1.10) + `resolve_markers.edl` | markers colored by section |
| After Effects | `strata_ae.jsx` | comp + audio + layer markers + "STRATA" null with keyframed sliders per curve |
| Texture | `curves.png` (16-bit, W=frames, H=curves) + `curves.npy` + `curves.json` | Notch/TD/shaders |
| Report | `report.html` | self-contained single-file breakdown to share |

## 9. Live (OSC)

The server holds the clock; the UI sends play/pause/seek. External control: `/strata/play`, `/strata/pause`, `/strata/seek f`. Each 60 Hz tick emits:

- `/strata/time f`, `/strata/beat/phase f`, `/strata/bar/phase f`
- `/strata/section/progress f`, `/strata/curve/<name> f`

Edge-triggered messages:

- `/strata/beat i`, `/strata/downbeat i`, `/strata/bar i`
- `/strata/section s i`, `/strata/chord s`
- `/strata/kick f`, `/strata/snare f`, `/strata/hat f`
- `/strata/drop f`, `/strata/cue s f`

`strata live <track> --osc host:port` runs headless from now, or from `--at`.

## 10. Web UI

Vite + TypeScript + Canvas2D (timeline) + WebGL2 (visualizer), built into `strata/web/`. Dark HYPRGRPH look.

- **Library** sidebar plus a drop zone. Analysis progress streams over SSE.
- **Timeline:** zoom/scroll lanes with a minimap.
  - SECTIONS: colored blocks + labels
  - WAVEFORM: stacked stem envelopes in stem colors
  - BEATS: bars/downbeats, opacity = confidence
  - KEY + CHORDS
  - DRUMS: kick/snare/hat ticks
  - NOTES: mini piano roll
  - ENERGY: loudness curve + builds/drops
  - CUES
  - AGREEMENT: one row per backend showing its beats/boundaries against consensus, so disagreement is visible
- **Transport:** play/pause/seek with the playhead synced to audio. The hover inspector reads every layer at a given time.
- **Panels:**
  - EXPORT: buttons that download from the server
  - LIVE: OSC host/port, on/off
  - VISUALIZER: a full-bleed WebGL scene driven by the data (section color fields, kick shockwaves, hat sparks, chord hue, energy scale)

## 11. Claude skill

`skill/strata/SKILL.md` gets installed to `~/.claude/skills/strata`. It teaches `strata analyze | query | export`, schema field meanings and recipes: cut lists from cues, section-aligned shot plans, OSC maps for Notch, BPM-synced loop lengths.

`strata query <track|json>` answers the questions Claude actually asks:

- `--at t` reads every layer at time t
- `--sections`
- `--cues --min 0.6`
- `--beats --from a --to b`
- `--summary`, a compact text digest

## 12. Error handling

- A missing optional backend is skipped and recorded in provenance.
- If every backend for a dimension fails, that dimension is empty and `provenance` says why. The run still exits 0, with a warning summary.
- Non-zero exits are reserved for unreadable audio, a bad CLI invocation, or a schema validation failure.
- `strata doctor` reports GPU, each backend's availability and license, and the disk paths in use.

## 13. Testing

- **Unit:** ensemble voting (synthetic beat lists with jitter, outliers, half-time), Viterbi downbeats, boundary clustering, label normalization, every exporter (XML parses, MIDI loads via mido and round-trips times, EDL/CSV formats).
- **Synthetic audio:** a click track at known BPM keeps beat error within 20 ms. Synthetic triad progressions give the right chord/key. A sine-burst track gives the expected drum bands.
- **Real smoke:** a full analysis of a reference song checks schema validity, plausible BPM/sections and a nonempty set of every layer.
- **UI:** build plus a Playwright smoke run that loads an analysis, renders the lanes with no console errors, and checks that playback moves the playhead.

## 14. Repo / distribution

- Repo `wexloops/strata` (public when David says so; private until then). Root holds the MIT `LICENSE` and a `THIRD_PARTY.md` listing every backend's license.
- `pyproject` extras: `[nc]` (madmom), `[lyrics]` (faster-whisper), `[tags]` (transformers CLAP), `[dev]`.
- Vendored: `vendor/all-in-one` (PR #39) and `strata/backends/btc/` (MIT, weights fetched at first run from the upstream repo).
- `strata doctor` installs nothing silently.
