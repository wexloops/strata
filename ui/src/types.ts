// Canonical STRATA analysis schema 1 (spec §6). Fields are optional-tolerant at read time.

export interface Provenance {
  backend: string; dimension: string; version: string; license: string;
  nc: boolean; ok: boolean; error: string | null; seconds: number;
}
export interface Beat { time: number; bar: number; beat: number; downbeat: boolean; confidence: number; votes: Record<string, boolean>; }
export interface Bar { index: number; start: number; end: number; }
export interface Section {
  index: number; start: number; end: number; label: string; confidence: number; energy: number;
  color: string; key?: string; tags?: string[]; votes: Record<string, number>;
}
export interface Chord { start: number; end: number; label: string; label_full: string; root: string; quality: string; confidence: number; }
export interface TimedStrength { time: number; strength: number; }
export interface Note { start: number; end: number; pitch: number; velocity: number; }
export interface Span { start: number; end: number; }
export interface Build extends Span { strength: number; }
export interface Lyric extends Span { text: string; }
export interface Cue { time: number; type: string; strength: number; label: string; }
export interface Tag { label: string; score: number; }

export interface Analysis {
  strata: { version: string; schema: number; created: string; profile: string };
  track: { title: string; path: string; id: string; duration: number; sample_rate: number; channels: number };
  provenance: Provenance[];
  tempo: { bpm: number; confidence: number; stable: boolean; meter: number;
           alternatives: { bpm: number; support: number }[]; map: { time: number; bpm: number }[] };
  beats: Beat[];
  bars: Bar[];
  sections: Section[];
  key: { label: string; tonic: string; mode: string; camelot: string; confidence: number;
         votes: Record<string, { label: string; confidence: number }> };
  chords: Chord[];
  events: { kick: TimedStrength[]; snare: TimedStrength[]; hat: TimedStrength[]; onsets: TimedStrength[]; accents: TimedStrength[] };
  notes: { bass: Note[]; vocals: Note[]; other: Note[] };
  dynamics: { lufs: number; lra: number; peak_db: number; builds: Build[]; drops: TimedStrength[]; silences: Span[] };
  vocals: { activity: Span[]; lyrics: Lyric[] };
  tags: { genre: Tag[]; mood: Tag[]; instruments: Tag[] };
  cues: Cue[];
  curves: { fps: number; names: string[]; data: Record<string, number[]> };
}

export interface TrackSummary { id: string; title: string; duration: number; bpm: number; key: string; created: string; }

/** Fill any missing containers so renderers never have to null-check. */
export function normalize(a: Partial<Analysis>): Analysis {
  const x = a as Analysis;
  x.strata ??= { version: "?", schema: 1, created: "", profile: "full" };
  x.track ??= { title: "untitled", path: "", id: "", duration: 0, sample_rate: 44100, channels: 2 };
  x.provenance ??= [];
  x.tempo ??= { bpm: 0, confidence: 0, stable: false, meter: 4, alternatives: [], map: [] };
  x.tempo.meter ||= 4;
  x.beats ??= []; x.bars ??= []; x.sections ??= []; x.chords ??= []; x.cues ??= [];
  x.key ??= { label: "", tonic: "", mode: "", camelot: "", confidence: 0, votes: {} };
  x.events ??= { kick: [], snare: [], hat: [], onsets: [], accents: [] };
  for (const k of ["kick", "snare", "hat", "onsets", "accents"] as const) x.events[k] ??= [];
  x.notes ??= { bass: [], vocals: [], other: [] };
  for (const k of ["bass", "vocals", "other"] as const) x.notes[k] ??= [];
  x.dynamics ??= { lufs: 0, lra: 0, peak_db: 0, builds: [], drops: [], silences: [] };
  x.dynamics.builds ??= []; x.dynamics.drops ??= []; x.dynamics.silences ??= [];
  x.vocals ??= { activity: [], lyrics: [] };
  x.vocals.activity ??= []; x.vocals.lyrics ??= [];
  x.tags ??= { genre: [], mood: [], instruments: [] };
  x.curves ??= { fps: 30, names: [], data: {} };
  x.curves.data ??= {};
  if (!x.track.duration) {
    const last = x.sections.at(-1)?.end ?? x.beats.at(-1)?.time ?? 0;
    x.track.duration = last || 1;
  }
  for (const s of x.sections) s.votes ??= {};
  for (const b of x.beats) b.votes ??= {};
  return x;
}
