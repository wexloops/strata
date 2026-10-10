import { sectionColor, inkOn, rgba } from "../colors";
import { fmtTime } from "../query";
import { type Lane, MONO, DISPLAY, text, fitLabel, visibleRange } from "./lane";

export const sectionsLane: Lane = {
  id: "sections", name: "sections", height: 52,
  note: (a) => `${a.sections.length} parts`,
  draw({ ctx, a, view, y, h, x0, x1 }) {
    const [i0, i1] = visibleRange(a.sections, view.t0, view.t1, (s) => s.start, (s) => s.end);
    const counts: Record<string, number> = {};
    for (let i = 0; i < i0; i++) counts[a.sections[i].label] = (counts[a.sections[i].label] ?? 0) + 1;
    for (let i = i0; i < i1; i++) {
      const s = a.sections[i];
      const n = (counts[s.label] = (counts[s.label] ?? 0) + 1);
      const col = sectionColor(s);
      const xa = Math.max(x0, view.x(s.start)), xb = Math.min(x1, view.x(s.end));
      const w = xb - xa;
      if (w <= 0) continue;
      // confidence → opacity
      ctx.fillStyle = rgba(col, 0.3 + 0.7 * s.confidence);
      ctx.fillRect(xa + 1, y + 1, Math.max(0.5, w - 2), h - 2);
      // energy as a top-weighted inner bar
      ctx.fillStyle = "rgba(0,0,0,0.32)";
      ctx.fillRect(xa + 1, y + h - 5, Math.max(0.5, w - 2), 4);
      ctx.fillStyle = rgba(inkOn(col) === "#000" ? "#000000" : "#F5F5F0", 0.85);
      ctx.fillRect(xa + 1, y + h - 5, Math.max(0.5, (w - 2) * s.energy), 4);
      if (w > 34) {
        const ink = inkOn(col);
        const pad = 7;
        ctx.font = `700 19px ${DISPLAY}`;
        const lab = fitLabel(ctx, s.label + (n > 1 ? ` ${n}` : ""), w - pad * 2);
        if (lab) text(ctx, lab, xa + pad, y + 18, `700 19px ${DISPLAY}`, ink);
        ctx.font = `9.5px ${MONO}`;
        const meta = fitLabel(ctx, `${fmtTime(s.start, false)}  ${Math.round(s.end - s.start)}s`, w - pad * 2);
        if (meta) text(ctx, meta, xa + pad, y + 35, `9.5px ${MONO}`, ink === "#000" ? "rgba(0,0,0,0.62)" : "rgba(245,245,240,0.7)");
      }
    }
  },
};
