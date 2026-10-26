"""Endpoint job: F-01 preview, F-06 review data, F-12 unduh, F-13 progres/riwayat."""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.engine import Engine
from sqlmodel import select

from app.api import deps
from app.api.schemas import (
    CandidateOut, FacecamIn, JobCreate, JobDetail, JobOut, PreviewIn, PreviewOut, RenderIn, SelectionIn,
)
from app.config import AppConfig
from app.db import session
from app.models import ACTIVE_STATUSES, Candidate, Job, utcnow
from app.pipeline import download
from app.pipeline.audio import require_ffmpeg
from app.runner import RenderOptions
from app.templates import ensure_default_templates, list_templates
from app.worker import Worker

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

TERMINAL = ("ready_for_review", "done", "failed")
SERVED_DIRS = ("clips", "thumbs")
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _job_out(job: Job, cands: list[Candidate], w: Worker) -> JobOut:
    return JobOut.of(job, cands, w.queue_position(job.id))


def _detail(job: Job, cands: list[Candidate], w: Worker) -> JobDetail:
    base = _job_out(job, cands, w).model_dump()
    return JobDetail(
        **base,
        candidates=[CandidateOut.of(c) for c in cands],
        render_options=json.loads(job.render_options) if job.render_options else None,
    )


def _job_dir(cfg: AppConfig, job_id: str) -> Path:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(404, f"Job {job_id} tidak ditemukan")
    base = cfg.jobs_dir.resolve()
    target = (base / job_id).resolve()
    if target.parent != base:
        raise HTTPException(404, f"Job {job_id} tidak ditemukan")
    return cfg.jobs_dir / job_id


# ---------------------------------------------------------------- F-01

@router.post("/preview", response_model=PreviewOut)
def preview(body: PreviewIn) -> PreviewOut:
    try:
        download.parse_youtube_url(body.url)
        meta = download.fetch_metadata(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except download.DownloadError as e:
        raise HTTPException(502, str(e)) from e
    return PreviewOut(**meta.to_dict())


@router.post("", response_model=JobOut, status_code=201)
def create_job(
    body: JobCreate,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> JobOut:
    try:
        video_id = download.parse_youtube_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    ensure_default_templates(cfg.templates_dir)
    template = body.template or cfg.render.default_template
    if template not in list_templates(cfg.templates_dir):
        raise HTTPException(400, f"Template {template!r} tidak ditemukan")

    job = Job(
        id=f"{video_id}-{secrets.token_hex(3)}", url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id, template=template, status="queued", task="detect",
        title=body.title or "", channel=body.channel or "", duration=body.duration or 0.0,
        thumbnail=body.thumbnail, message="menunggu antrean",
    )
    with session(engine) as s:
        s.add(job)
        s.commit()
    w.enqueue(job.id, "detect")
    return _job_out(job, [], w)


# ---------------------------------------------------------------- F-13

@router.get("", response_model=list[JobOut])
def list_jobs(engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker)) -> list[JobOut]:
    with session(engine) as s:
        jobs = s.exec(select(Job).order_by(Job.created_at.desc())).all()
        cands = s.exec(select(Candidate)).all()
    by_job: dict[str, list[Candidate]] = {}
    for c in cands:
        by_job.setdefault(c.job_id, []).append(c)
    return [_job_out(j, by_job.get(j.id, []), w) for j in jobs]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker)) -> JobDetail:
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        return _detail(job, deps.job_candidates(s, job_id), w)


@router.patch("/{job_id}", response_model=JobOut)
def update_job(
    job_id: str, body: dict,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> JobOut:
    """Ganti template job (dipakai saat render berikutnya)."""
    template = body.get("template")
    if not isinstance(template, str) or template not in list_templates(cfg.templates_dir):
        raise HTTPException(400, "Template tidak ditemukan")
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        job.template = template
        s.add(job)
        s.commit()
        return _job_out(job, deps.job_candidates(s, job_id), w)


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str, engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> Response:
    if w.is_busy(job_id):
        raise HTTPException(409, "Job sedang diproses / di antrean; tunggu sampai selesai.")
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        for c in deps.job_candidates(s, job_id):
            s.delete(c)
        s.delete(job)
        s.commit()
    shutil.rmtree(_job_dir(cfg, job_id), ignore_errors=True)
    return Response(status_code=204)


@router.get("/{job_id}/events")
async def job_events(
    job_id: str, request: Request,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
) -> StreamingResponse:
    """SSE progres job. Mengirim event `job` setiap ada perubahan; selesai saat status terminal."""
    poll_s = request.app.state.sse_poll_s

    def snapshot() -> dict | None:
        with session(engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                return None
            return _job_out(job, deps.job_candidates(s, job_id), w).model_dump(mode="json")

    if await anyio.to_thread.run_sync(snapshot) is None:
        raise HTTPException(404, f"Job {job_id} tidak ditemukan")

    async def stream():
        yield "retry: 3000\n\n"
        last: str | None = None
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            data = await anyio.to_thread.run_sync(snapshot)
            if data is None:
                yield "event: deleted\ndata: {}\n\n"
                return
            payload = json.dumps(data)
            if payload != last:
                last, idle = payload, 0.0
                yield f"event: job\ndata: {payload}\n\n"
            if data["status"] in TERMINAL and data["queue_position"] is None:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(poll_s)
            idle += poll_s
            if idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- F-06

@router.get("/{job_id}/scores")
def job_scores(
    job_id: str, engine: Engine = Depends(deps.engine), cfg: AppConfig = Depends(deps.config),
) -> dict:
    with session(engine) as s:
        deps.get_job_or_404(s, job_id)
        cands = deps.job_candidates(s, job_id)
    path = _job_dir(cfg, job_id) / "scores.json"
    if not path.exists():
        raise HTTPException(404, "Skor belum tersedia (analisis belum selesai)")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "duration": data.get("duration"),
        "has_chat": data.get("has_chat"),
        "has_reaction": bool(data.get("has_reaction")),
        "has_face": bool(data.get("has_face")),
        "face": data.get("face"),
        "face_info": data.get("face_info"),
        "threshold": data.get("threshold"),
        "used_fallback": data.get("used_fallback"),
        "excluded": data.get("excluded") or [],
        "smoothed": data.get("smoothed"),
        "audio": data.get("audio"),
        "chat": data.get("chat"),
        "reaction": data.get("reaction"),
        "candidates": [
            {"id": c.id, "rank": c.rank, "peak_time": c.peak_time, "start": c.start, "end": c.end,
             "score": c.score, "selected": c.selected}
            for c in cands
        ],
    }


@router.get("/{job_id}/source")
def job_source(job_id: str, cfg: AppConfig = Depends(deps.config)) -> FileResponse:
    """Video sumber dengan dukungan HTTP Range (preview HTML5)."""
    path = _job_dir(cfg, job_id) / "source.mp4"
    if not path.exists():
        raise HTTPException(404, "source.mp4 belum ada")
    return FileResponse(path, media_type="video/mp4")


@router.get("/{job_id}/frame")
def job_frame(
    job_id: str, t: float = Query(0.0, ge=0), width: int = Query(1280, ge=160, le=1920),
    cfg: AppConfig = Depends(deps.config),
) -> Response:
    """Satu frame JPEG dari sumber (untuk editor template F-08)."""
    path = _job_dir(cfg, job_id) / "source.mp4"
    if not path.exists():
        raise HTTPException(404, "source.mp4 belum ada")
    cmd = [require_ffmpeg(), "-nostdin", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
           "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise HTTPException(500, f"Gagal mengambil frame: {proc.stderr.decode(errors='replace').strip()}")
    return Response(proc.stdout, media_type="image/jpeg")


@router.post("/{job_id}/detect-facecam")
def detect_facecam(
    job_id: str, body: FacecamIn,
    engine: Engine = Depends(deps.engine), cfg: AppConfig = Depends(deps.config),
) -> dict:
    """F-17: saran kotak facecam dari beberapa frame sumber (MediaPipe, CPU, ±beberapa detik)."""
    from app.pipeline import facecam, thumbnail

    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        duration = job.duration
    source = _job_dir(cfg, job_id) / "source.mp4"
    if not source.exists():
        raise HTTPException(404, "source.mp4 belum ada")
    fc = cfg.facecam if body.frames is None else cfg.facecam.with_overrides(frames=body.frames)
    try:
        model = thumbnail.ensure_face_model(cfg.models_dir, cfg.thumbnail.face_model_url)
        with thumbnail.FaceDetector(model, fc.min_confidence) as detector:
            res = facecam.detect_facecam(source, duration, body.top_ratio, cfg.render, fc, detector)
    except ImportError as e:
        raise HTTPException(500, f"MediaPipe belum terpasang ({e})") from e
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e
    if res is None:
        raise HTTPException(
            422, "Facecam tidak terdeteksi: tidak ada wajah yang posisinya stabil di frame sampel. "
                 "Gambar kotak facecam secara manual.")
    return {
        "facecam_box": asdict(res.box),
        "face_box": {"x": res.face.x, "y": res.face.y, "w": res.face.w, "h": res.face.h},
        "hits": res.hits,
        "frames": res.frames,
        "confidence": res.confidence,
        "time": res.best_time,
    }


@router.get("/{job_id}/files/{kind}/{name}")
def job_file(job_id: str, kind: str, name: str, cfg: AppConfig = Depends(deps.config)) -> FileResponse:
    """File hasil (clips/*, thumbs/*). Range request didukung untuk video."""
    if kind not in SERVED_DIRS or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(404, "File tidak ditemukan")
    base = (_job_dir(cfg, job_id) / kind).resolve()
    path = (base / name).resolve()
    if path.parent != base or not path.is_file():
        raise HTTPException(404, "File tidak ditemukan")
    return FileResponse(path)


# ---------------------------------------------------------------- F-09..F-11 (antrekan render)

@router.post("/{job_id}/render", response_model=JobOut, status_code=202)
def render_job(
    job_id: str, body: RenderIn,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> JobOut:
    if w.is_busy(job_id):
        raise HTTPException(409, "Job sedang diproses / di antrean")
    ensure_default_templates(cfg.templates_dir)
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        cands = deps.job_candidates(s, job_id)
        if job.status in ACTIVE_STATUSES:
            raise HTTPException(409, f"Job masih {job.status}")
        if not cands:
            raise HTTPException(400, "Belum ada kandidat; jalankan analisis dulu")
        if not any(c.selected for c in cands):
            raise HTTPException(400, "Pilih minimal 1 kandidat")
        if not (_job_dir(cfg, job_id) / "source.mp4").exists():
            raise HTTPException(400, "source.mp4 tidak ada")
        if body.template:
            if body.template not in list_templates(cfg.templates_dir):
                raise HTTPException(400, f"Template {body.template!r} tidak ditemukan")
            job.template = body.template

        options = RenderOptions(
            subtitle=cfg.subtitle.enabled if body.subtitle is None else body.subtitle,
            thumbnail=cfg.thumbnail.enabled if body.thumbnail is None else body.thumbnail,
            landscape=cfg.thumbnail.landscape if body.landscape is None else body.landscape,
            intro_frame=cfg.thumbnail.intro_frame if body.intro_frame is None else body.intro_frame,
            only_thumbs=body.only_thumbs,
        )
        if (options.intro_frame or options.only_thumbs) and not options.thumbnail:
            raise HTTPException(400, "Frame pembuka / thumbnail saja butuh thumbnail aktif")

        job.render_options = json.dumps(asdict(options))
        job.task, job.status, job.progress, job.error = "render", "queued", 0.0, None
        job.message = "menunggu antrean render"
        job.updated_at = utcnow()
        s.add(job)
        s.commit()
        out = _job_out(job, cands, w)
    w.enqueue(job_id, "render")
    out.queue_position = w.queue_position(job_id)
    return out


@router.post("/{job_id}/transcribe", response_model=JobOut, status_code=202)
def transcribe_job(
    job_id: str, engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> JobOut:
    """F-16: transkripsi kandidat terpilih tanpa render → subtitle bisa diedit sebelum render."""
    if w.is_busy(job_id):
        raise HTTPException(409, "Job sedang diproses / di antrean")
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        cands = deps.job_candidates(s, job_id)
        if job.status in ACTIVE_STATUSES:
            raise HTTPException(409, f"Job masih {job.status}")
        if not any(c.selected for c in cands):
            raise HTTPException(400, "Pilih minimal 1 kandidat untuk ditranskripsi")
        if not (_job_dir(cfg, job_id) / "source.mp4").exists():
            raise HTTPException(400, "source.mp4 tidak ada")
        job.task, job.status, job.progress, job.error = "transcribe", "queued", 0.0, None
        job.message = "menunggu antrean transkripsi"
        job.updated_at = utcnow()
        s.add(job)
        s.commit()
        out = _job_out(job, cands, w)
    w.enqueue(job_id, "transcribe")
    out.queue_position = w.queue_position(job_id)
    return out


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: str, engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
) -> JobOut:
    """Batalkan job yang antre / berjalan. Yang sedang berjalan berhenti di laporan progres
    berikutnya (unduh, analisis, atau render); status 'nyangkut' tanpa worker langsung dibereskan."""
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        task, status = job.task, job.status
    if status not in ACTIVE_STATUSES:
        raise HTTPException(409, "Job tidak sedang berjalan")
    w.cancel(job_id, task)
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        return _job_out(job, deps.job_candidates(s, job_id), w)


# ---------------------------------------------------------------- F-12

def _zip_members(job_dir: Path, cands: list[Candidate]) -> list[tuple[Path, str]]:
    members: list[tuple[Path, str]] = []
    for c in cands:
        for rel in (c.clip_path, c.credit_path, c.thumb_path, c.thumb_landscape_path):
            if rel and (job_dir / rel).is_file():
                members.append((job_dir / rel, rel))
    return members


@router.get("/{job_id}/download")
def download_zip(
    job_id: str, engine: Engine = Depends(deps.engine), cfg: AppConfig = Depends(deps.config),
) -> FileResponse:
    """Semua hasil (klip, kredit .txt, thumbnail) sebagai ZIP."""
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        cands = deps.job_candidates(s, job_id)
    job_dir = _job_dir(cfg, job_id)
    members = _zip_members(job_dir, cands)
    if not members:
        raise HTTPException(404, "Belum ada hasil render")

    export = job_dir / "export"
    export.mkdir(exist_ok=True)
    zip_path = export / f"{job.video_id}_clips.zip"
    newest = max(p.stat().st_mtime for p, _ in members)
    names = sorted(arc for _, arc in members)
    stale = True
    if zip_path.exists() and zip_path.stat().st_mtime >= newest:
        with zipfile.ZipFile(zip_path) as zf:
            stale = sorted(zf.namelist()) != names
    if stale:
        tmp = zip_path.with_suffix(".part")
        with zipfile.ZipFile(tmp, "w") as zf:
            for path, arc in members:
                compress = zipfile.ZIP_DEFLATED if path.suffix == ".txt" else zipfile.ZIP_STORED
                zf.write(path, arc, compress_type=compress)
        tmp.replace(zip_path)
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@router.post("/{job_id}/open-folder")
def open_folder(job_id: str, cfg: AppConfig = Depends(deps.config)) -> dict:
    """Buka folder output di file explorer (hanya bila backend jalan langsung di desktop)."""
    job_dir = _job_dir(cfg, job_id)
    folder = job_dir / "clips" if (job_dir / "clips").exists() else job_dir
    if not folder.exists():
        raise HTTPException(404, "Folder job tidak ada")
    opened = False
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
            opened = True
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(folder)])
            opened = True
        elif shutil.which("open"):
            subprocess.Popen(["open", str(folder)])
            opened = True
    except OSError:
        opened = False
    return {"path": str(folder.resolve()), "opened": opened}


@router.post("/{job_id}/selection", response_model=JobDetail)
def set_selection(
    job_id: str, body: SelectionIn,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
) -> JobDetail:
    """Pilih semua / hapus pilihan (F-06) atau set daftar id terpilih."""
    with session(engine) as s:
        job = deps.get_job_or_404(s, job_id)
        cands = deps.job_candidates(s, job_id)
        ids = set(body.ids or [])
        for c in cands:
            c.selected = (c.id in ids) if body.ids is not None else bool(body.selected)
            s.add(c)
        s.commit()
        return _detail(job, cands, w)
