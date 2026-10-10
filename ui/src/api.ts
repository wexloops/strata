// Server API client (plan Task 11 contract) with an offline DEMO fallback.
//
// server mode: FastAPI at the same origin.
// demo mode:   no server answered /api/tracks with JSON, so we load /demo/sample_analysis.json + /demo/audio.mp3
//              (vite public dir, gitignored). Analyze/export/live are disabled; JSON export still works locally.
import { normalize, type Analysis, type TrackSummary } from "./types";

export type Mode = "server" | "demo" | "offline";
export const EXPORT_FORMATS = [
  { fmt: "json", label: "Analysis JSON", file: "analysis.json", target: "everything, Claude" },
  { fmt: "csv", label: "CSV tables", file: "beats / sections / chords / events / cues / curves", target: "Sheets, TouchDesigner CHOP" },
  { fmt: "midi", label: "MIDI", file: "strata.mid", target: "Ableton, any DAW" },
  { fmt: "labels", label: "Labels", file: "audacity.txt, reaper_regions.csv", target: "Audacity, Reaper" },
  { fmt: "premiere", label: "Premiere XML", file: "premiere.xml", target: "Premiere Pro" },
  { fmt: "fcpxml", label: "FCPXML", file: "timeline.fcpxml", target: "Resolve, Final Cut" },
  { fmt: "edl", label: "EDL markers", file: "resolve_markers.edl", target: "Resolve" },
  { fmt: "ae", label: "After Effects", file: "strata_ae.jsx", target: "AE comp + keyframed sliders" },
  { fmt: "texture", label: "Curve texture", file: "curves.png / .npy / .json", target: "Notch, TD, shaders" },
  { fmt: "report", label: "Report", file: "report.html", target: "share a single file" },
  { fmt: "all", label: "Everything", file: "strata_exports.zip", target: "all of the above" },
] as const;

export interface JobEvent { stage?: string; progress?: number; message?: string; done?: boolean; track_id?: string; error?: string; }

const DEMO_ID = "__demo__";

export class Api {
  mode: Mode = "offline";
  private demo: Analysis | null = null;
  private ws: WebSocket | null = null;
  private wsPending: string | null = null;
  private wsRetry = 0;

  async init(): Promise<void> {
    try {
      const r = await fetch("/api/tracks", { headers: { accept: "application/json" } });
      if (r.ok && (r.headers.get("content-type") || "").includes("json")) {
        await r.clone().json();
        this.mode = "server";
        this.connectTransport();
        return;
      }
    } catch { /* no server: fall through to demo */ }
    try {
      const r = await fetch("/demo/sample_analysis.json");
      if (r.ok && (r.headers.get("content-type") || "").includes("json")) {
        this.demo = normalize(await r.json());
        this.mode = "demo";
        return;
      }
    } catch { /* nothing */ }
    this.mode = "offline";
  }

  async listTracks(): Promise<TrackSummary[]> {
    if (this.mode === "demo" && this.demo) {
      const a = this.demo;
      return [{ id: DEMO_ID, title: a.track.title, duration: a.track.duration, bpm: a.tempo.bpm, key: a.key.label, created: a.strata.created }];
    }
    if (this.mode !== "server") return [];
    const r = await fetch("/api/tracks");
    if (!r.ok) throw new Error(`Library request failed (${r.status})`);
    return r.json();
  }

  async getTrack(id: string): Promise<Analysis> {
    if (this.mode === "demo" && this.demo) return this.demo;
    const r = await fetch(`/api/tracks/${encodeURIComponent(id)}`);
    if (!r.ok) throw new Error(`Track ${id} could not be loaded (${r.status})`);
    return normalize(await r.json());
  }

  audioUrl(id: string): string {
    return this.mode === "demo" ? "/demo/audio.mp3" : `/api/tracks/${encodeURIComponent(id)}/audio`;
  }

  exportUrl(id: string, fmt: string): string | null {
    return this.mode === "server" ? `/api/tracks/${encodeURIComponent(id)}/export/${fmt}` : null;
  }

  /** Upload a file for analysis. Streams SSE progress to onEvent; resolves with the new track id. */
  analyze(file: File, profile: string, onEvent: (e: JobEvent) => void): Promise<string> {
    if (this.mode !== "server") return Promise.reject(new Error("Analysis needs the STRATA server. Run `strata serve` and reload."));
    return (async () => {
      const fd = new FormData();
      fd.append("file", file);
      if (profile) fd.append("profile", profile);
      const r = await fetch("/api/analyze", { method: "POST", body: fd });
      if (!r.ok) throw new Error(`Upload rejected (${r.status}): ${(await r.text()).slice(0, 200)}`);
      const { job } = await r.json();
      return new Promise<string>((resolve, reject) => {
        const es = new EventSource(`/api/jobs/${encodeURIComponent(job)}/events`);
        let finished = false;
        es.onmessage = (m) => {
          let e: JobEvent;
          try { e = JSON.parse(m.data); } catch { return; }
          onEvent(e);
          if (e.done && e.track_id) { finished = true; es.close(); resolve(e.track_id); }
          else if (e.error) { finished = true; es.close(); reject(new Error(e.error)); }
        };
        es.onerror = () => {
          if (finished) return;
          if (es.readyState === EventSource.CLOSED) reject(new Error("Lost the progress stream from the server."));
        };
      });
    })();
  }

  /** Remove a track's analysis, stems, cache and exports. The source audio file is never touched. */
  async deleteTrack(id: string): Promise<void> {
    if (this.mode !== "server") throw new Error("Removing tracks needs the STRATA server.");
    const r = await fetch(`/api/tracks/${encodeURIComponent(id)}`, { method: "DELETE" });
    let body: { ok?: boolean; error?: string; detail?: string } = {};
    try { body = await r.json(); } catch { /* non-JSON error page */ }
    if (r.status === 404) throw new Error("This track is no longer in the library.");
    if (!r.ok || body.ok === false) throw new Error(body.error || body.detail || `The server could not remove this track (${r.status}).`);
  }

  async live(id: string, host: string, port: number, on: boolean): Promise<void> {
    if (this.mode !== "server") throw new Error("Live OSC needs the STRATA server. Run `strata serve`.");
    const r = await fetch("/api/live", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id, host, port, on }),
    });
    if (!r.ok) throw new Error(`Live request failed (${r.status}): ${(await r.text()).slice(0, 200)}`);
    const body = await r.json().catch(() => ({ ok: true }));
    if (body && body.ok === false) throw new Error(body.error || "Server refused to start the OSC clock.");
  }

  /** Keep the server OSC clock following the UI transport. */
  transport(op: "play" | "pause" | "seek", t: number): void {
    if (this.mode !== "server") return;
    const msg = JSON.stringify({ op, t: Math.round(t * 1000) / 1000 });
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(msg);
    else this.wsPending = msg;
  }

  private connectTransport(): void {
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/transport`;
    let ws: WebSocket;
    try { ws = new WebSocket(url); } catch { return; }
    this.ws = ws;
    ws.onopen = () => {
      this.wsRetry = 0;
      if (this.wsPending) { ws.send(this.wsPending); this.wsPending = null; }
    };
    ws.onclose = () => {
      this.ws = null;
      const delay = Math.min(10000, 500 * 2 ** this.wsRetry++);
      setTimeout(() => this.connectTransport(), delay);
    };
  }
}

/** Trigger a browser download of an in-memory blob. */
export function downloadBlob(name: string, data: BlobPart, type = "application/json"): void {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
