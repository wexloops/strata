---
name: strata
description: Analyze music with STRATA (HYPRGRPH's ensemble music analyzer) and use the result to drive edits, music-synced visuals, OSC shows and loop lengths. Use whenever the user wants a track's sections, BPM/tempo map, beats/downbeats, key, chords, drum hits, drops/builds, lyrics timing, energy curves, cut points/cue lists, markers for Premiere/Resolve/AE, MIDI of a song's structure, or OSC playback into Notch/Resolume/TouchDesigner, or says "strata", "analyze this track", "break this song down", "cut to the beat", "where's the drop".
---

# STRATA

Ensemble music analysis. Several open-source models are weighed against each other per dimension, and the output is ONE canonical `analysis.json` (schema 1) plus exporters.

Run commands inside the STRATA install's venv (see the repo README):
```bash
cd <path to strata> && source .venv/bin/activate
export STRATA_HOME=<library dir>   # optional; default ~/.strata. On WSL, a /mnt/c/... path lets Windows apps open exports
```

## Commands
| Need | Command |
|---|---|
| Analyze (about 1.5 min per 3-min track on the 5090; cached after) | `strata analyze "<audio>" [--export all] [--fast] [--profile commercial-safe]` |
| Text digest | `strata query "<audio or id or title>" --summary` |
| Everything at a moment | `strata query <t> --at 63.2` |
| Sections | `strata query <t> --sections --json` |
| Cut list | `strata query <t> --cues --min 0.6 --json` (types: section,drop,downbeat,accent) |
| Beats in a range | `strata query <t> --beats --from 30 --to 60 [--downbeats]` |
| Export files | `strata export <t> --format premiere,fcpxml,edl,ae,midi,labels,csv,texture,report,json \| all [--out DIR]` |
| OSC playback | `strata live <t> --osc 127.0.0.1:9000 [--at 0] [--listen 9001]` |
| Web UI | `strata serve --open` -> http://localhost:3090 |
| Health | `strata doctor`, `strata backends` |

`<t>` = analysis.json path, the audio file (looked up by content hash), a track id, or a unique title substring. Audio paths must be analyzed first.

## analysis.json fields (times are seconds)
- `tempo` {bpm, stable, meter, alternatives[], map[]}; `beats[]` {time, bar, beat, downbeat, confidence, votes{backend: bool}}; `bars[]`
- `sections[]` {start, end, label (intro/verse/chorus/bridge/outro/... or A/B/C), energy 0..1 (loudness percentile), key, color, confidence, votes}
- `key` {label, camelot, confidence, votes}; `chords[]` {start, end, label, label_full, root, quality}
- `events` {kick, snare, hat, onsets, accents: [{time, strength}]}; `notes` {bass, vocals, other: [{start, end, pitch, velocity}]}
- `dynamics` {lufs, lra, peak_db, builds[], drops[], silences[]}; `vocals` {activity[], lyrics[{start, end, text, words[]}]}
- `cues[]` {time, type, strength, label}: ranked edit points. section >= 0.8, drop >= 0.7, accents < 0.6, so `--min 0.6` = structural moments.
- `curves` {fps, names, data}: per-frame 0..1 loudness, rms, rms_{drums,bass,vocals,other}, kick/snare/hat envelopes, onset, centroid, flux, band_0..7.
- `provenance[]`: which backends ran, their license, and `nc` (non-commercial weights).

## Recipes
- **Cut on the music:** `--cues --min 0.6` for structure; add downbeats inside sections with energy >= 0.6 for faster cutting.
- **Shot plan per section:** `--sections`, one shot idea per section, duration = end - start, and match intensity to energy.
- **BPM-synced loop length:** bars x meter x 60 / bpm seconds (8 bars at 120 BPM = 16 s).
- **Notch/TD/Resolume:** `strata live` sends `/strata/beat i bar_beat`, `/strata/downbeat bar`, `/strata/section label idx`, `/strata/chord s`, `/strata/kick|snare|hat strength`, `/strata/drop`, `/strata/cue type strength`, plus every 60 Hz tick `/strata/time`, `/strata/beat/phase`, `/strata/bar/phase`, `/strata/section/progress`, `/strata/curve/<name>`.
- **Shaders:** `--format texture` writes curves.png (16-bit, W=frames, H=curve rows) + curves.npy.
- **Editors:** premiere.xml (FCP7 XML), timeline.fcpxml (Resolve/FCP), resolve_markers.edl, strata_ae.jsx (File > Scripts > Run Script File).

## Caveats
- If `tempo.stable` is false the track drifts (live drummer), so use the beats list rather than a fixed grid.
- Drum hits come from DSP on the separated drum stem: good timing, approximate class on dense mixes.
- CLAP mood/genre tags are disabled (an embedding bug on this stack). The editor imports are spec-built but haven't been round-tripped in every app yet.
