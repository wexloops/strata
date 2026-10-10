"""Local web server: library API, analysis jobs (SSE progress), exports, live OSC transport, built UI."""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import threading
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .exporters import FORMATS, export
from .library import Library, strata_home

WEB = Path(__file__).parent / "web"
DEMO = Path(__file__).parent.parent / "examples" / "demo"
STEMS = ("drums", "bass", "vocals", "other")


class Jobs:
    """Analysis jobs run one at a time (single GPU) on a worker thread; events are buffered for SSE."""

    def __init__(self, lib: Library):
        self.lib = lib
        self.jobs: dict[str, dict] = {}
        self._gpu = threading.Lock()

    def submit(self, path: Path, profile: str) -> str:
        jid = uuid.uuid4().hex[:12]
        self.jobs[jid] = {"events": [{"stage": "queued", "progress": 0.0, "message": path.name}], "done": False}
        threading.Thread(target=self._run, args=(jid, path, profile), daemon=True).start()
        return jid

    def _run(self, jid: str, path: Path, profile: str) -> None:
        from .pipeline import analyze

        job = self.jobs[jid]
        with self._gpu:
            try:
                a = analyze(path, profile=profile, lib=self.lib, progress=job["events"].append)
                job["events"].append({"done": True, "track_id": a["track"]["id"]})
            except Exception as e:
                job["events"].append({"error": f"{type(e).__name__}: {e}"})
        job["done"] = True


LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "testserver"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg", ".opus"}


def _hostname(value: str) -> str:
    from urllib.parse import urlsplit
    if "://" in value:
        value = urlsplit(value).netloc
    return value.rsplit(":", 1)[0] if not value.startswith("[") else value.split("]")[0] + "]"


def create_app(lib: Library | None = None) -> FastAPI:
    lib = lib or Library()
    lib.ensure_demo(DEMO)
    app = FastAPI(title="STRATA")

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        """This server can read local files, so only same-machine pages may talk to it:
        Host must be local (blocks DNS rebinding) and any Origin must be local (blocks CSRF)."""
        host = _hostname(request.headers.get("host", ""))
        origin = request.headers.get("origin")
        if host not in LOCAL_HOSTS or (origin and _hostname(origin) not in LOCAL_HOSTS):
            return JSONResponse({"detail": "STRATA only accepts requests from this machine"}, status_code=403)
        return await call_next(request)
    jobs = Jobs(lib)
    live: dict = {"session": None, "id": None}

    def load(tid: str) -> dict:
        if not lib.analysis_path(tid).exists():
            raise HTTPException(404, f"no analysis for {tid}")
        return lib.load_analysis(tid)

    @app.get("/api/tracks")
    def tracks():
        return lib.list()

    @app.get("/api/tracks/{tid}")
    def track(tid: str):
        return JSONResponse(load(tid))

    @app.delete("/api/tracks/{tid}")
    def delete_track(tid: str):
        try:
            gone = lib.delete(tid)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not gone:
            raise HTTPException(404, f"no analysis for {tid}")
        return {"ok": True, "deleted": tid}

    @app.get("/api/tracks/{tid}/audio")
    def track_audio(tid: str):
        p = Path(load(tid)["track"]["path"])
        if not p.exists():
            raise HTTPException(404, "source audio moved or deleted")
        return FileResponse(p)

    @app.get("/api/tracks/{tid}/stems/{name}")
    def stem(tid: str, name: str):
        p = lib.stems_dir(tid) / f"{name}.flac"
        if name not in STEMS or not p.exists():
            raise HTTPException(404, "stem not found")
        return FileResponse(p, media_type="audio/flac")

    @app.get("/api/tracks/{tid}/export/{fmt}")
    def export_track(tid: str, fmt: str):
        a = load(tid)
        if fmt != "all" and fmt not in FORMATS:
            raise HTTPException(400, f"unknown format {fmt}")
        out = lib.exports_dir(tid) / fmt
        shutil.rmtree(out, ignore_errors=True)
        audio = Path(a["track"]["path"])
        paths = export(a, fmt, out, audio if audio.exists() else None)
        if len(paths) == 1:
            return FileResponse(paths[0], filename=paths[0].name)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                z.write(p, p.relative_to(out))
        name = f"{a['track']['title']}_strata_{fmt}.zip".replace("/", "_")
        return StreamingResponse(iter([buf.getvalue()]), media_type="application/zip",
                                 headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_quote(name)}"})

    @app.post("/api/analyze")
    async def analyze_endpoint(request: Request, file: UploadFile | None = File(None), profile: str = Form("full")):
        if file is not None:
            up = strata_home() / "uploads"
            up.mkdir(parents=True, exist_ok=True)
            dst = up / Path(file.filename or "upload.wav").name
            with open(dst, "wb") as f:
                shutil.copyfileobj(file.file, f)
            path = dst
        else:
            if not request.headers.get("content-type", "").startswith("application/json"):
                raise HTTPException(415, "send multipart 'file' or JSON {path}")
            body = await request.json()
            path = Path(body.get("path", ""))
            profile = body.get("profile", profile)
            if path.suffix.lower() not in AUDIO_EXT or not path.is_file():
                raise HTTPException(400, f"not an audio file: {path}")
        return {"job": jobs.submit(path, profile)}

    @app.get("/api/jobs/{jid}/events")
    async def job_events(jid: str):
        if jid not in jobs.jobs:
            raise HTTPException(404, "no such job")

        async def stream():
            sent = 0
            while True:
                job = jobs.jobs[jid]
                evs = job["events"]
                while sent < len(evs):
                    yield f"data: {json.dumps(evs[sent])}\n\n"
                    sent += 1
                if job["done"] and sent >= len(evs):
                    return
                await asyncio.sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/live")
    async def live_toggle(request: Request):
        from .live import LiveSession

        body = await request.json()
        if live["session"]:
            live["session"].stop()
            live["session"] = None
        if body.get("on"):
            a = load(body["id"])
            live["session"] = LiveSession(a, body.get("host", "127.0.0.1"), int(body.get("port", 9000))).start()
            live["id"] = body["id"]
        return {"ok": True, "on": bool(live["session"])}

    @app.websocket("/api/transport")
    async def transport(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and _hostname(origin) not in LOCAL_HOSTS:
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_json()
                s = live["session"]
                if not s:
                    continue
                op, t = msg.get("op"), msg.get("t")
                if op == "play":
                    s.clock.play(at=float(t) if t is not None else None)
                elif op == "pause":
                    s.clock.pause()
                    if t is not None:
                        s.clock.seek(float(t))
                elif op == "seek" and t is not None:
                    s.clock.seek(float(t))
        except WebSocketDisconnect:
            pass

    if WEB.exists() and (WEB / "index.html").exists():
        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)
