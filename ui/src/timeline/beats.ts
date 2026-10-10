import { type Lane, MONO, text, visibleRange } from "./lane";

export const beatsLane: Lane = {
  id: "beats", name: "beats", height: 34,
  note: (a) => `${a.beats.length} / ${a.bars.length} bars`,
  draw({ ctx, a, view, y, h, x1 }) {
    const [i0, i1] = visibleRange(a.beats, view.t0, view.t1, (b) => b.time);
    const ibi = 60 / (a.tempo.bpm || 120);
    const beatPx = ibi * view.pps;
    const barPx = beatPx * (a.tempo.meter || 4);
    const labelEvery = barPx > 30 ? 1 : barPx > 9 ? 4 : barPx > 2.5 ? 16 : 64;
    for (let i = i0; i < i1; i++) {
      const b = a.beats[i];
      const x = Math.round(view.x(b.time)) + 0.5;
      if (x > x1) break;
      const c = b.confidence;
      if (b.downbeat) {
        const major = (b.bar - 1) % labelEvery === 0;
        ctx.fillStyle = `rgba(245,245,240,${(major ? 0.95 : 0.55) * (0.25 + 0.75 * c)})`;
        ctx.fillRect(x - (major && labelEvery === 1 ? 0.5 : 0), y + (major ? 0 : 12), major && labelEvery === 1 ? 2 : 1, h - (major ? 0 : 12));
        if (major) text(ctx, String(b.bar), x + 4, y + 7, `9.5px ${MONO}`, `rgba(245,245,240,${0.4 + 0.5 * c})`);
      } else if (beatPx > 3) {
        ctx.fillStyle = `rgba(245,245,240,${0.38 * (0.2 + 0.8 * c)})`;
        ctx.fillRect(x, y + h - 12, 1, 12);
      }
      if (c < 0.75 && beatPx > 5) {
        // low-confidence beats get a dissent dot so they read at a glance
        ctx.fillStyle = `rgba(255,90,54,${0.9 - c})`;
        ctx.fillRect(x - 1, y + h - 2, 3, 2);
      }
    }
    if (beatPx > 22) {
      for (let i = i0; i < i1; i++) {
        const b = a.beats[i];
        if (b.downbeat) continue;
        const x = view.x(b.time);
        text(ctx, String(b.beat), x + 3, y + h - 17, `8.5px ${MONO}`, "rgba(245,245,240,0.3)");
      }
    }
  },
};
