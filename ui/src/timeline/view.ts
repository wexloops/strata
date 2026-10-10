// Horizontal time view: t0 (left edge time) + pixels per second.
export const GUTTER = 136;

export class View {
  t0 = 0;
  pps = 10;
  plotW = 800; // width of plot area in CSS px (canvas width minus gutter)
  duration = 1;
  follow = true;
  version = 0; // bumps on any change, renderers compare

  get t1(): number { return this.t0 + this.plotW / this.pps; }
  get minPps(): number { return this.plotW / Math.max(1e-3, this.duration); }
  get maxPps(): number { return 1600; }
  x(t: number): number { return GUTTER + (t - this.t0) * this.pps; }
  t(x: number): number { return this.t0 + (x - GUTTER) / this.pps; }

  setWidth(w: number): void {
    const fit = this.pps <= this.minPps + 1e-9;
    this.plotW = Math.max(50, w - GUTTER);
    if (fit) this.pps = this.minPps;
    this.clamp();
  }
  fit(): void { this.pps = this.minPps; this.t0 = 0; this.clamp(); }
  zoomAt(factor: number, anchorX: number): void {
    const ta = this.t(anchorX);
    this.pps = Math.max(this.minPps, Math.min(this.maxPps, this.pps * factor));
    this.t0 = ta - (anchorX - GUTTER) / this.pps;
    this.clamp();
  }
  pan(dt: number): void { this.t0 += dt; this.clamp(); }
  showAt(t: number, frac: number): void { this.t0 = t - frac * (this.plotW / this.pps); this.clamp(); }
  clamp(): void {
    const span = this.plotW / this.pps;
    this.t0 = Math.max(0, Math.min(this.t0, Math.max(0, this.duration - span)));
    this.version++;
  }
}
