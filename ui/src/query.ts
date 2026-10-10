// Time lookups over an Analysis. Everything is time-sorted (spec §6), so binary search.
import type { Analysis, Beat, Chord, Section, Lyric, TimedStrength, Cue, Build } from "./types";

/** Index of last item with key(item) <= t, or -1. */
export function lastAtOrBefore<T>(arr: T[], t: number, key: (x: T) => number): number {
  let lo = 0, hi = arr.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (key(arr[mid]) <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}
/** Index of first item with key(item) >= t (arr.length if none). */
export function firstAtOrAfter<T>(arr: T[], t: number, key: (x: T) => number): number {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (key(arr[mid]) < t) lo = mid + 1; else hi = mid; }
  return lo;
}
export function spanAt<T extends { start: number; end: number }>(arr: T[], t: number): T | null {
  const i = lastAtOrBefore(arr, t, (x) => x.start);
  return i >= 0 && t < arr[i].end ? arr[i] : null;
}
export function nearest(arr: TimedStrength[], t: number): TimedStrength | null {
  if (!arr.length) return null;
  const i = firstAtOrAfter(arr, t, (x) => x.time);
  const a = arr[i - 1], b = arr[i];
  if (!a) return b; if (!b) return a;
  return t - a.time <= b.time - t ? a : b;
}
export function lastEvent(arr: TimedStrength[], t: number): TimedStrength | null {
  const i = lastAtOrBefore(arr, t, (x) => x.time);
  return i >= 0 ? arr[i] : null;
}
export function curveAt(a: Analysis, name: string, t: number): number {
  const d = a.curves.data[name];
  if (!d || !d.length) return 0;
  const f = t * a.curves.fps;
  const i = Math.max(0, Math.min(d.length - 1, Math.floor(f)));
  const j = Math.min(d.length - 1, i + 1);
  const u = Math.max(0, Math.min(1, f - i));
  return d[i] * (1 - u) + d[j] * u;
}

export interface Moment {
  t: number;
  section: Section | null; sectionIndex: number; sectionProgress: number;
  beat: Beat | null; beatIndex: number; beatPhase: number; barPhase: number;
  chord: Chord | null; lyric: Lyric | null; build: Build | null;
  loudness: number; key: string;
  kick: TimedStrength | null; snare: TimedStrength | null; hat: TimedStrength | null;
  drop: TimedStrength | null; cue: Cue | null; bpm: number;
}

export function momentAt(a: Analysis, t: number): Moment {
  const si = lastAtOrBefore(a.sections, t, (s) => s.start);
  const section = si >= 0 && t < a.sections[si].end ? a.sections[si] : null;
  const bi = lastAtOrBefore(a.beats, t, (b) => b.time);
  const beat = bi >= 0 ? a.beats[bi] : null;
  let beatPhase = 0, barPhase = 0;
  if (beat) {
    const next = a.beats[bi + 1];
    const ibi = next ? next.time - beat.time : 60 / (a.tempo.bpm || 120);
    beatPhase = Math.max(0, Math.min(1, (t - beat.time) / ibi));
    barPhase = ((beat.beat - 1) + beatPhase) / (a.tempo.meter || 4);
  }
  const ci = lastAtOrBefore(a.cues, t + 1e-6, (c) => c.time);
  const mi = lastAtOrBefore(a.tempo.map, t, (m) => m.time);
  return {
    t, section, sectionIndex: section ? si : -1,
    sectionProgress: section ? (t - section.start) / Math.max(1e-6, section.end - section.start) : 0,
    beat, beatIndex: bi, beatPhase, barPhase,
    chord: spanAt(a.chords, t), lyric: spanAt(a.vocals.lyrics, t), build: spanAt(a.dynamics.builds, t),
    loudness: curveAt(a, "loudness", t),
    key: section?.key || a.key.label,
    kick: nearest(a.events.kick, t), snare: nearest(a.events.snare, t), hat: nearest(a.events.hat, t),
    drop: nearest(a.dynamics.drops, t), cue: ci >= 0 ? a.cues[ci] : null,
    bpm: mi >= 0 ? a.tempo.map[mi].bpm : a.tempo.bpm,
  };
}

export function fmtTime(t: number, ms = true): string {
  const s = Math.max(0, t);
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  const ss = ms ? sec.toFixed(3).padStart(6, "0") : Math.floor(sec).toString().padStart(2, "0");
  return `${m.toString().padStart(2, "0")}:${ss}`;
}
