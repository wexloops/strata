// Library sidebar + drop zone with SSE progress.
import type { Api, JobEvent } from "../api";
import type { TrackSummary } from "../types";
import { fmtTime } from "../query";

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export class Library {
  private el: HTMLElement;
  private list: HTMLElement;
  private jobs: HTMLElement;
  private tracks: TrackSummary[] = [];
  active = "";
  onOpen: (id: string) => void = () => {};
  /** Called after a track is removed; `next` is the neighbour to open, or null when the library is empty. */
  onDeleted: (id: string, next: string | null) => void = () => {};
  private confirming = "";
  private errors = new Map<string, string>();

  constructor(el: HTMLElement, private api: Api) {
    this.el = el;
    const demo = api.mode !== "server";
    el.innerHTML = `
      <div class="lib-h"><span>library</span><span class="lib-n"></span></div>
      <ol class="lib-list" aria-label="Analyzed tracks"></ol>
      <div class="lib-jobs"></div>
      <label class="drop ${demo ? "off" : ""}" tabindex="0">
        <input type="file" accept="audio/*,.wav,.mp3,.flac,.aiff,.aif,.ogg,.m4a" hidden ${demo ? "disabled" : ""}>
        <span class="drop-l">Drop audio to analyze</span>
        <span class="drop-s">${demo ? "Needs the STRATA server. Run <code>strata serve</code> to analyze your own tracks." : "or click to choose a file"}</span>
      </label>
      <div class="lib-prof">
        <label for="profile">profile</label>
        <select id="profile" ${demo ? "disabled" : ""}>
          <option value="full">full</option>
          <option value="commercial-safe">commercial-safe</option>
        </select>
      </div>
      ${demo ? `<p class="lib-demo">${api.mode === "demo" ? "Showing demo data. No server answered at <code>/api</code>." : "No server and no demo data found."}</p>` : ""}`;
    this.list = el.querySelector(".lib-list")!;
    this.jobs = el.querySelector(".lib-jobs")!;
    const drop = el.querySelector<HTMLLabelElement>(".drop")!;
    const input = drop.querySelector("input")!;
    input.addEventListener("change", () => { for (const f of input.files ?? []) this.analyze(f); input.value = ""; });
    drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    // whole window is a drop target
    window.addEventListener("dragover", (e) => { e.preventDefault(); document.body.classList.add("dragging"); });
    window.addEventListener("dragleave", (e) => { if (!e.relatedTarget) document.body.classList.remove("dragging"); });
    window.addEventListener("drop", (e) => {
      e.preventDefault();
      document.body.classList.remove("dragging");
      for (const f of e.dataTransfer?.files ?? []) this.analyze(f);
    });
  }

  async refresh(): Promise<TrackSummary[]> {
    try { this.tracks = await this.api.listTracks(); }
    catch (e) { this.list.innerHTML = `<li class="lib-err">${esc((e as Error).message)}</li>`; return []; }
    this.render();
    return this.tracks;
  }

  setActive(id: string): void { this.active = id; this.render(); }

  private get canDelete(): boolean { return this.api.mode === "server"; }

  private askDelete(id: string): void {
    if (!this.canDelete) return;
    this.confirming = id;
    this.errors.delete(id);
    this.render();
    this.list.querySelector<HTMLButtonElement>(`[data-cancel="${CSS.escape(id)}"]`)?.focus();
  }

  private cancelDelete(id: string): void {
    this.confirming = "";
    this.render();
    this.list.querySelector<HTMLButtonElement>(`.trk[data-id="${CSS.escape(id)}"]`)?.focus();
  }

  private async doDelete(id: string): Promise<void> {
    const row = this.list.querySelector<HTMLElement>(`li[data-row="${CSS.escape(id)}"]`);
    row?.classList.add("busy");
    row?.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      await this.api.deleteTrack(id);
    } catch (e) {
      this.confirming = "";
      this.errors.set(id, (e as Error).message);
      this.render();
      return;
    }
    const i = this.tracks.findIndex((t) => t.id === id);
    this.tracks = this.tracks.filter((t) => t.id !== id);
    this.confirming = "";
    this.errors.delete(id);
    const next = this.tracks[Math.min(Math.max(0, i), this.tracks.length - 1)]?.id ?? null;
    this.render();
    this.onDeleted(id, next);
    const focusId = next ?? "";
    (this.list.querySelector<HTMLButtonElement>(`.trk[data-id="${CSS.escape(focusId)}"]`) ?? this.el.querySelector<HTMLElement>(".drop"))?.focus();
  }

  private render(): void {
    this.el.querySelector(".lib-n")!.textContent = String(this.tracks.length);
    if (!this.tracks.length) {
      this.list.innerHTML = `<li class="lib-empty">No tracks yet. Drop an audio file below to analyze it.</li>`;
      return;
    }
    const del = this.canDelete;
    this.list.innerHTML = this.tracks.map((t) => {
      const id = esc(t.id);
      const err = this.errors.get(t.id);
      const confirm = this.confirming === t.id;
      return `
      <li data-row="${id}" class="${confirm ? "confirming" : ""}">
        <button class="trk ${t.id === this.active ? "on" : ""}" data-id="${id}" aria-current="${t.id === this.active}"${del ? ` aria-keyshortcuts="Delete"` : ""}>
          <span class="trk-t">${esc(t.title || t.id)}</span>
          <span class="trk-m"><span>${fmtTime(t.duration, false)}</span><span>${t.bpm ? t.bpm.toFixed(1) : "–"}</span><span>${esc(t.key || "")}</span></span>
        </button>
        ${del && !confirm ? `<button class="trk-x" data-del="${id}" aria-label="Remove ${esc(t.title || t.id)} from library" title="Remove from library (Delete)">remove</button>` : ""}
        ${confirm ? `<div class="trk-confirm" role="group" aria-label="Confirm removal">
          <p>Remove from library? Your audio file stays.</p>
          <div><button class="trk-yes" data-yes="${id}">Remove</button><button class="trk-no" data-cancel="${id}">Cancel</button></div>
        </div>` : ""}
        ${err ? `<p class="trk-err" role="alert">${esc(err)}</p>` : ""}
      </li>`;
    }).join("");
    this.list.querySelectorAll<HTMLButtonElement>(".trk").forEach((b) => {
      b.addEventListener("click", () => this.onOpen(b.dataset.id!));
      b.addEventListener("keydown", (e) => {
        if (del && (e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); e.stopPropagation(); this.askDelete(b.dataset.id!); }
      });
    });
    this.list.querySelectorAll<HTMLButtonElement>("[data-del]").forEach((b) => b.addEventListener("click", () => this.askDelete(b.dataset.del!)));
    this.list.querySelectorAll<HTMLButtonElement>("[data-yes]").forEach((b) => b.addEventListener("click", () => void this.doDelete(b.dataset.yes!)));
    this.list.querySelectorAll<HTMLButtonElement>("[data-cancel]").forEach((b) => b.addEventListener("click", () => this.cancelDelete(b.dataset.cancel!)));
    this.list.querySelectorAll<HTMLElement>(".trk-confirm").forEach((c) => c.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); this.cancelDelete(this.confirming); }
    }));
  }

  private analyze(file: File): void {
    const row = document.createElement("div");
    row.className = "job";
    row.innerHTML = `<div class="job-t">${esc(file.name)}</div><div class="job-bar"><b></b></div><div class="job-s">uploading</div>`;
    this.jobs.prepend(row);
    const bar = row.querySelector<HTMLElement>(".job-bar b")!;
    const st = row.querySelector<HTMLElement>(".job-s")!;
    const profile = (this.el.querySelector("#profile") as HTMLSelectElement).value;
    const on = (e: JobEvent) => {
      if (typeof e.progress === "number") bar.style.width = `${Math.round(e.progress * 100)}%`;
      if (e.stage || e.message) st.textContent = [e.stage, e.message].filter(Boolean).join("  ");
    };
    this.api.analyze(file, profile, on).then(async (id) => {
      bar.style.width = "100%";
      st.textContent = "done";
      row.classList.add("ok");
      await this.refresh();
      this.onOpen(id);
      setTimeout(() => row.remove(), 4000);
    }).catch((err: Error) => {
      row.classList.add("err");
      st.textContent = err.message;
    });
  }
}
