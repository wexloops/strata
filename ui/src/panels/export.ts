// EXPORT: one button per format, downloads straight from the server.
import { type Api, EXPORT_FORMATS, downloadBlob } from "../api";
import type { Analysis } from "../types";

export class ExportPanel {
  constructor(private el: HTMLElement, private api: Api) { el.classList.add("exp"); }

  render(a: Analysis, id: string): void {
    const server = this.api.mode === "server";
    this.el.innerHTML = `
      <p class="p-lede">Every export is built from the same analysis, so cuts, markers and curves line up across tools.</p>
      <ul class="exp-list">${EXPORT_FORMATS.map((f) => {
        const enabled = server || f.fmt === "json";
        return `<li><button class="exp-b" data-fmt="${f.fmt}" ${enabled ? "" : "disabled"}>
          <span class="exp-l">${f.label}</span><span class="exp-f">${f.file}</span><span class="exp-t">${f.target}</span>
        </button></li>`;
      }).join("")}</ul>
      ${server ? "" : `<p class="p-note">Demo mode exports the analysis JSON locally. The other formats need <code>strata serve</code>.</p>`}`;
    this.el.querySelectorAll<HTMLButtonElement>(".exp-b").forEach((b) => b.addEventListener("click", () => {
      const fmt = b.dataset.fmt!;
      const url = this.api.exportUrl(id, fmt);
      if (url) {
        const link = document.createElement("a");
        link.href = url; link.download = "";
        document.body.appendChild(link); link.click(); link.remove();
        b.classList.add("sent"); setTimeout(() => b.classList.remove("sent"), 1200);
      } else if (fmt === "json") {
        downloadBlob("analysis.json", JSON.stringify(a, null, 1));
      }
    }));
  }
}
