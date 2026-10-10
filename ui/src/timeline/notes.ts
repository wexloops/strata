// Mini piano roll across the bass / vocals / other stems.
import { STEM } from "../colors";
import type { Analysis, Note } from "../types";
import { type Lane, MONO, DIM, text, visibleRange } from "./lane";

const ORDER = ["other", "bass", "vocals"] as const;
const range = new WeakMap<Analysis, [number, number]>();
function pitchRange(a: Analysis): [number, number] {
  let r = range.get(a);
  if (r) return r;
  let lo = 127, hi = 0;
  for (const k of ORDER) for (const n of a.notes[k]) { if (n.pitch < lo) lo = n.pitch; if (n.pitch > hi) hi = n.pitch; }
  r = lo > hi ? [36, 84] : [lo - 1, hi + 1];
  range.set(a, r);
  return r;
}
const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
export const midiName = (p: number) => `${NAMES[p % 12]}${Math.floor(p / 12) - 1}`;

export const notesLane: Lane = {
  id: "notes", name: "notes", height: 84,
  note: (a) => { const [lo, hi] = pitchRange(a); return `${midiName(lo + 1)}–${midiName(hi - 1)}`; },
  draw({ ctx, a, view, y, h, x0, x1 }) {
    const [lo, hi] = pitchRange(a);
    const span = hi - lo;
    const ph = h / span;
    // octave guides
    for (let p = Math.ceil(lo / 12) * 12; p <= hi; p += 12) {
      const yy = Math.round(y + h - (p - lo) * ph) + 0.5;
      ctx.fillStyle = "rgba(245,245,240,0.06)";
      ctx.fillRect(x0, yy, x1 - x0, 1);
      text(ctx, `C${p / 12 - 1}`, x1 - 4, yy - 5, `8.5px ${MONO}`, "rgba(245,245,240,0.25)", "right");
    }
    for (const k of ORDER) {
      const ns: Note[] = a.notes[k];
      const [i0, i1] = visibleRange(ns, view.t0 - 30, view.t1, (n) => n.start);
      ctx.fillStyle = STEM[k];
      for (let i = i0; i < i1; i++) {
        const n = ns[i];
        if (n.end < view.t0) continue;
        const xa = Math.max(x0, view.x(n.start)), xb = Math.min(x1, view.x(n.end));
        if (xb <= xa) continue;
        ctx.globalAlpha = (k === "other" ? 0.3 : 0.45) + 0.55 * n.velocity;
        ctx.fillRect(xa, y + h - (n.pitch - lo + 1) * ph, Math.max(1, xb - xa - 0.5), Math.max(1.5, ph - 0.5));
      }
    }
    ctx.globalAlpha = 1;
  },
  gutter({ ctx, y, h }) {
    ORDER.slice().reverse().forEach((k, i) => {
      const yy = y + h - 12 - i * 13;
      ctx.fillStyle = STEM[k];
      ctx.fillRect(14, yy - 3, 6, 6);
      text(ctx, k, 25, yy, `9.5px ${MONO}`, DIM);
    });
  },
};
