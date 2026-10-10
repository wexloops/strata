import { fmtTime } from "../query";
import { type Lane, MONO, DIM, HAIR, text } from "./lane";

const STEPS = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];

export const ruler: Lane = {
  id: "ruler", name: "time", height: 24,
  note: (a) => fmtTime(a.track.duration, false),
  draw({ ctx, view, y, h, x1 }) {
    const step = STEPS.find((s) => s * view.pps >= 84) ?? 300;
    const minor = step / 5;
    ctx.fillStyle = HAIR;
    for (let t = Math.floor(view.t0 / minor) * minor; t <= view.t1; t += minor) {
      const x = Math.round(view.x(t)) + 0.5;
      if (x > x1) break;
      ctx.fillRect(x, y + h - 4, 1, 4);
    }
    const ms = step < 1;
    for (let t = Math.floor(view.t0 / step) * step; t <= view.t1 + step; t += step) {
      const x = Math.round(view.x(t)) + 0.5;
      if (x > x1) break;
      ctx.fillStyle = "rgba(245,245,240,0.35)";
      ctx.fillRect(x, y + h - 9, 1, 9);
      text(ctx, ms ? fmtTime(t) : fmtTime(t, false), x + 4, y + 9, `10px ${MONO}`, DIM);
    }
  },
};
