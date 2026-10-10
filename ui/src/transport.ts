// Playback clock. Audio element when available; a silent virtual clock otherwise so the
// timeline, OSC follow and visualizer still run without audio.
type Listener = (e: { op: "play" | "pause" | "seek"; t: number }) => void;

export class Transport {
  audio: HTMLAudioElement | null = null;
  duration = 0;
  playing = false;
  silent = true; // true when no audio is driving the clock
  private vStart = 0; // virtual clock: performance.now() at play
  private vOffset = 0; // virtual clock: time at play
  private listeners: Listener[] = [];

  on(fn: Listener): void { this.listeners.push(fn); }
  private emit(op: "play" | "pause" | "seek"): void { const t = this.time(); for (const f of this.listeners) f({ op, t }); }

  load(src: string | null, duration: number): Promise<boolean> {
    this.pause(false);
    this.duration = duration;
    this.vOffset = 0;
    if (this.audio) { this.audio.removeAttribute("src"); this.audio.load(); this.audio = null; }
    this.silent = true;
    if (!src) return Promise.resolve(false);
    const el = new Audio();
    el.preload = "auto";
    el.crossOrigin = "anonymous";
    return new Promise((resolve) => {
      const done = (ok: boolean) => {
        el.removeEventListener("loadedmetadata", onOk); el.removeEventListener("error", onErr);
        if (ok) { this.audio = el; this.silent = false; }
        resolve(ok);
      };
      const onOk = () => done(true);
      const onErr = () => done(false);
      el.addEventListener("loadedmetadata", onOk);
      el.addEventListener("error", onErr);
      el.addEventListener("ended", () => { if (this.playing) { this.playing = false; this.emit("pause"); } });
      el.src = src;
    });
  }

  time(): number {
    if (this.audio && !this.silent) return this.audio.currentTime;
    if (!this.playing) return this.vOffset;
    const t = this.vOffset + (performance.now() - this.vStart) / 1000;
    if (t >= this.duration) { this.playing = false; this.vOffset = this.duration; this.emit("pause"); return this.duration; }
    return t;
  }

  async play(): Promise<void> {
    if (this.playing) return;
    if (this.time() >= this.duration - 0.01) this.seek(0, false);
    this.playing = true;
    if (this.audio && !this.silent) {
      try { await this.audio.play(); }
      catch {
        // Autoplay refusal or decode failure: keep the timeline moving on the silent clock.
        this.vOffset = this.audio.currentTime;
        this.silent = true;
        this.vStart = performance.now();
      }
    } else {
      this.vStart = performance.now();
    }
    this.emit("play");
  }

  pause(notify = true): void {
    if (!this.playing) return;
    this.vOffset = this.time();
    this.playing = false;
    if (this.audio) this.audio.pause();
    if (notify) this.emit("pause");
  }

  toggle(): void { this.playing ? this.pause() : void this.play(); }

  seek(t: number, notify = true): void {
    t = Math.max(0, Math.min(this.duration, t));
    this.vOffset = t;
    this.vStart = performance.now();
    if (this.audio) this.audio.currentTime = t;
    if (notify) this.emit("seek");
  }
}
