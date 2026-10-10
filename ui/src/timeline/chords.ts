// KEY strip (local key per section) above chord blocks (hue = root on circle of fifths, lightness = quality).
import { chordColor, chordHSL } from "../colors";
import { type Lane, MONO, DIM, text, fitLabel, visibleRange } from "./lane";

function keyCamelot(label: string, globalLabel: string, globalCamelot: string): string {
  return label === globalLabel ? globalCamelot : "";
}

export const chordsLane: Lane = {
  id: "chords", name: "key + chords", height: 50,
  note: (a) => `${a.key.label || "?"} ${a.key.camelot}`.trim(),
  draw({ ctx, a, view, y, h, x0, x1 }) {
    const keyH = 14;
    // merge contiguous sections with the same local key
    const spans: { start: number; end: number; key: string }[] = [];
    for (const s of a.sections) {
      const k = s.key || a.key.label;
      const last = spans.at(-1);
      if (last && last.key === k && Math.abs(last.end - s.start) < 0.05) last.end = s.end;
      else spans.push({ start: s.start, end: s.end, key: k });
    }
    if (!spans.length && a.key.label) spans.push({ start: 0, end: a.track.duration, key: a.key.label });
    for (const sp of spans) {
      const xa = Math.max(x0, view.x(sp.start)), xb = Math.min(x1, view.x(sp.end));
      if (xb <= xa) continue;
      ctx.fillStyle = "rgba(245,245,240,0.16)";
      ctx.fillRect(xa, y + keyH - 1, xb - xa, 1);
      ctx.fillRect(Math.round(xa), y + 2, 1, keyH - 2);
      const cam = keyCamelot(sp.key, a.key.label, a.key.camelot);
      ctx.font = `9.5px ${MONO}`;
      const lab = fitLabel(ctx, `${sp.key}${cam ? "  " + cam : ""}`, xb - xa - 10);
      if (lab) text(ctx, lab, Math.max(xa, x0) + 5, y + 7, `9.5px ${MONO}`, DIM);
    }
    const cy = y + keyH + 3, ch = h - keyH - 4;
    const [i0, i1] = visibleRange(a.chords, view.t0, view.t1, (c) => c.start, (c) => c.end);
    for (let i = i0; i < i1; i++) {
      const c = a.chords[i];
      const xa = Math.max(x0, view.x(c.start)), xb = Math.min(x1, view.x(c.end));
      const w = xb - xa;
      if (w <= 0) continue;
      ctx.fillStyle = chordColor(c.root, c.quality, 0.35 + 0.65 * c.confidence);
      ctx.fillRect(xa + 0.5, cy, Math.max(0.5, w - 1), ch);
      if (w > 18) {
        const l = chordHSL(c.root, c.quality)[2];
        ctx.font = `600 11px ${MONO}`;
        const lab = fitLabel(ctx, c.label, w - 8);
        if (lab) text(ctx, lab, xa + 5, cy + ch / 2 + 0.5, `600 11px ${MONO}`, l > 50 ? "rgba(0,0,0,0.85)" : "rgba(245,245,240,0.92)");
      }
    }
  },
};
