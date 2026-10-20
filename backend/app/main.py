"""FastAPI app (M4). Jalankan: python -m clipper serve  (atau uvicorn app.main:app)."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.engine import Engine
from sqlmodel import select

from app import runner
from app.api import candidates, jobs, settings, templates
from app.config import REPO_ROOT, AppConfig, load_config
from app.db import make_engine, session
from app.models import STATUSES, Candidate, Job
from app.templates import ensure_default_templates
from app.worker import Worker

log = logging.getLogger("autoclip")
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def import_cli_jobs(engine: Engine, jobs_dir: Path) -> int:
    """Masukkan job hasil CLI (data/jobs/<id>/job.json) yang belum ada di database ke riwayat."""
    if not jobs_dir.exists():
        return 0
    added = 0
    with session(engine) as s:
        known = set(s.exec(select(Job.id)).all())
        for d in sorted(jobs_dir.iterdir()):
            job_file = d / "job.json"
            if not d.is_dir() or d.name in known or not job_file.exists():
                continue
            try:
                data = json.loads(job_file.read_text(encoding="utf-8"))
                meta_file = d / "meta.json"
                meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
                cands = json.loads((d / "candidates.json").read_text(encoding="utf-8")) \
                    if (d / "candidates.json").exists() else []
            except (OSError, json.JSONDecodeError):
                continue
            status = data.get("status", "failed")
            if status not in STATUSES or status in ("queued", "downloading", "analyzing", "rendering"):
                status = "failed" if not cands else "ready_for_review"
            created = data.get("created_at")
            s.add(Job(
                id=d.name, url=data.get("url", ""), video_id=meta.get("video_id", d.name),
                title=data.get("title", ""), channel=data.get("channel", ""),
                duration=float(data.get("duration") or 0), thumbnail=meta.get("thumbnail"),
                has_chat=bool(data.get("has_chat")), status=status, progress=100.0,
                error=data.get("error"), message="diimpor dari CLI",
                **({"created_at": datetime.fromisoformat(created)} if created else {}),
            ))
            s.flush()  # job harus ada sebelum kandidat (foreign key)
            for c in cands:
                fix = lambda p: p.replace("\\", "/") if isinstance(p, str) else None  # noqa: E731
                s.add(Candidate(
                    job_id=d.name, rank=c["rank"], peak_time=c["peak_time"], start=c["start"], end=c["end"],
                    score=c.get("score", 0), selected=bool(c.get("selected")),
                    clip_path=fix(c.get("clip_path")), thumb_path=fix(c.get("thumb_path")),
                    thumb_landscape_path=fix(c.get("thumb_landscape_path")), thumb_text=c.get("thumb_text"),
                ))
            added += 1
        s.commit()
    return added


def create_app(
    data_dir: Path | None = None, *, start_worker: bool = True,
    detect_fn: Callable = runner.run_detect, render_fn: Callable = runner.run_render,
    sse_poll_s: float = 0.5,
) -> FastAPI:
    startup_cfg = load_config(data_dir)
    pinned_dir = startup_cfg.data_dir

    def raw_config_loader() -> AppConfig:
        return load_config(data_dir)

    def config_loader() -> AppConfig:
        # Pengaturan dibaca ulang tiap request/tugas (langsung berlaku),
        # kecuali data_dir yang dikunci sampai restart (DB & antrean ada di sana).
        return replace(load_config(data_dir), data_dir=pinned_dir)

    engine = make_engine(startup_cfg.db_path)
    worker = Worker(engine, config_loader, detect_fn=detect_fn, render_fn=render_fn)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_default_templates(startup_cfg.templates_dir)
        n = import_cli_jobs(engine, startup_cfg.jobs_dir)
        if n:
            log.info("%d job CLI diimpor ke riwayat", n)
        if start_worker:
            worker.start()
            resumed = worker.recover()
            if resumed:
                log.info("%d job dilanjutkan setelah restart", resumed)
        yield
        worker.stop()
        engine.dispose()

    app = FastAPI(title="Auto Clipper API", version="0.4.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.worker = worker
    app.state.config_loader = config_loader
    app.state.raw_config_loader = raw_config_loader
    app.state.sse_poll_s = sse_poll_s

    app.add_middleware(
        CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"], allow_headers=["*"],
    )
    for r in (jobs.router, candidates.router, templates.router, settings.router):
        app.include_router(r)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "data_dir": str(pinned_dir), "busy": worker.current}

    # Build frontend (npm run build) disajikan langsung; tanpa build pakai Vite dev server :5173.
    if FRONTEND_DIST.exists():
        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(404)
            target = (FRONTEND_DIST / full_path).resolve()
            if full_path and target.is_file() and FRONTEND_DIST.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


def _default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    return create_app()


# `uvicorn app.main:app --factory` atau `python -m clipper serve`
app = _default_app
