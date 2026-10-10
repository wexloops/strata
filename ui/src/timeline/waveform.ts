// Stacked stem envelopes, mirrored about the center line.
import { STEM, rgba } from "../colors";
import type { Analysis } from "../types";
import { type Lane, curveMax, DIM, MONO, text } from "./lane";

export const STEMS = ["drums", "bass", "vocals", "other"] as const;
const norm = new WeakMap<Analysis, number>();

function stackMax(a: Analysis): number {
  let m = norm.get(a);
  if (m !== undefined) return m;
  m = 1e-6;
  const ds = STEMS.map((s) => a.curves.data[`rms_${s}`] ?? []);
  const n = Math.max(...ds.map((d) => d.length));
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (const d of ds) s += d[i] ?? 0;
    if (s > m) m = s;
  }
  norm.set(a, m);
  return m;
}

export const waveformLane: Lane = {
  id: "waveform", name: "waveform", height: 96,
  note: (a) => (STEMS.some((s) => a.curves.data[`rms_${s}`]) ? "4 stems" : "no stems"),
  draw({ ctx, a, view, y, h, x0, x1 }) {
    const mid = y + h / 2;
    const half = h / 2 - 3;
    const ds = STEMS.map((s) => a.curves.data[`rms_${s}`]);
    if (ds.every((d) => !d)) {
      text(ctx, "no stem curves in this analysis", x0 + 8, mid, `10px ${MONO}`, DIM);
      return;
    }
    const scale = half / stackMax(a);
    const fps = a.curves.fps;
    const cols = Math.max(1, Math.ceil(x1 - x0));
    const step = 1; // px per column
    const cum = new Float32Array((STEMS.length + 1) * (cols + 1));
    for (let c = 0; c <= cols; c++) {
      const ta = view.t(x0 + c * step), tb = view.t(x0 + (c + 1) * step);
      let acc = 0;
      for (let k = 0; k < STEMS.length; k++) {
        acc += curveMax(ds[k], fps, ta, tb) * scale;
        cum[(k + 1) * (cols + 1) + c] = acc;
      }
    }
    // outermost first so inner bands paint over
    for (let k = STEMS.length - 1; k >= 0; k--) {
      const row = (k + 1) * (cols + 1);
      ctx.beginPath();
      ctx.moveTo(x0, mid - cum[row]);
      for (let c = 1; c <= cols; c++) ctx.lineTo(x0 + c * step, mid - cum[row + c]);
      for (let c = cols; c >= 0; c--) ctx.lineTo(x0 + c * step, mid + cum[row + c]);
      ctx.closePath();
      ctx.fillStyle = rgba(STEM[STEMS[k]], k === 3 ? 0.55 : 0.92);
      ctx.fill();
      // band separation: hairline black seam on the band's outer edge
      ctx.strokeStyle = "rgba(0,0,0,0.55)";
      ctx.lineWidth = 0.75;
      ctx.stroke();
    }
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(x0, Math.round(mid), x1 - x0, 1);
  },
  gutter({ ctx, y, h }) {
    const x = 14;
    STEMS.forEach((s, i) => {
      const yy = y + h - 12 - (STEMS.length - 1 - i) * 13;
      ctx.fillStyle = STEM[s];
      ctx.fillRect(x, yy - 3, 6, 6);
      text(ctx, s, x + 11, yy, `9.5px ${MONO}`, DIM);
    });
  },
};
