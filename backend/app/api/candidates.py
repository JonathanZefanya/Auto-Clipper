"""F-06 pilih kandidat, F-07 trim awal/akhir."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.engine import Engine

from app.api import deps
from app.api.schemas import CandidateOut, CandidatePatch, SubtitlesIn
from app.config import AppConfig, SubtitleConfig
from app.db import session
from app.models import Candidate, Job
from app.pipeline import subdoc
from app.runner import rel_path
from app.worker import Worker

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def validate_range(start: float, end: float, max_clip_s: float, video_duration: float) -> None:
    if start < 0:
        raise HTTPException(422, "start tidak boleh negatif")
    if end <= start:
        raise HTTPException(422, "end harus lebih besar dari start")
    if end - start > max_clip_s + 1e-6:
        raise HTTPException(422, f"Durasi klip maksimal {max_clip_s:g} detik")
    if video_duration > 0 and end > video_duration + 1e-6:
        raise HTTPException(422, f"end melebihi durasi video ({video_duration:g} detik)")


def _candidate_ctx(s, candidate_id: int, w: Worker, write: bool = False) -> tuple[Candidate, Job]:
    c = s.get(Candidate, candidate_id)
    if c is None:
        raise HTTPException(404, "Kandidat tidak ditemukan")
    job = s.get(Job, c.job_id)
    if job is None:
        raise HTTPException(404, "Job tidak ditemukan")
    if write and job.status in ("rendering", "transcribing") and w.is_busy(job.id):
        raise HTTPException(409, f"Job sedang {job.status}")
    return c, job


def _subs_payload(c: Candidate, doc: subdoc.SubDoc, scfg: SubtitleConfig) -> dict:
    return {
        "candidate_id": c.id,
        "duration": round(c.end - c.start, 3),
        "edited": doc.edited,
        "stale": subdoc.is_stale(doc, c.start, c.end),
        "clip_start": doc.clip_start,
        "clip_end": doc.clip_end,
        "lines": [
            {"start": ln.start, "end": ln.end, "text": ln.text}
            for ln in subdoc.display_lines(doc, c.start, c.end, scfg)
        ],
    }


@router.get("/{candidate_id}/subtitles")
def get_subtitles(
    candidate_id: int, engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> dict:
    """F-16: baris subtitle (waktu relatif terhadap rentang klip saat ini)."""
    with session(engine) as s:
        c, _ = _candidate_ctx(s, candidate_id, w)
    doc = subdoc.load_doc(cfg.jobs_dir / c.job_id, c.rank)
    if doc is None:
        raise HTTPException(404, "Belum ada transkripsi untuk klip ini")
    return _subs_payload(c, doc, cfg.subtitle)


@router.put("/{candidate_id}/subtitles")
def put_subtitles(
    candidate_id: int, body: SubtitlesIn,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> dict:
    with session(engine) as s:
        c, _ = _candidate_ctx(s, candidate_id, w, write=True)
        try:
            lines = subdoc.validate_lines([ln.model_dump() for ln in body.lines], c.end - c.start)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        job_dir = cfg.jobs_dir / c.job_id
        doc = subdoc.SubDoc(c.start, c.end, lines, edited=True)
        path = subdoc.save_doc(job_dir, c.rank, doc)
        c.subs_path = rel_path(path, job_dir)
        s.add(c)
        s.commit()
        s.refresh(c)
        return _subs_payload(c, doc, cfg.subtitle)


@router.delete("/{candidate_id}/subtitles", status_code=204)
def delete_subtitles(
    candidate_id: int, engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> Response:
    """Reset ke subtitle otomatis (Whisper dijalankan lagi saat render/transkripsi berikutnya)."""
    with session(engine) as s:
        c, _ = _candidate_ctx(s, candidate_id, w, write=True)
        subdoc.delete_doc(cfg.jobs_dir / c.job_id, c.rank)
        c.subs_path = None
        s.add(c)
        s.commit()
    return Response(status_code=204)


@router.patch("/{candidate_id}", response_model=CandidateOut)
def patch_candidate(
    candidate_id: int, body: CandidatePatch,
    engine: Engine = Depends(deps.engine), w: Worker = Depends(deps.worker),
    cfg: AppConfig = Depends(deps.config),
) -> CandidateOut:
    with session(engine) as s:
        c = s.get(Candidate, candidate_id)
        if c is None:
            raise HTTPException(404, "Kandidat tidak ditemukan")
        job = s.get(Job, c.job_id)
        if job is not None and job.status in ("rendering", "transcribing") and w.is_busy(job.id):
            raise HTTPException(409, f"Job sedang {job.status}")

        if body.start is not None or body.end is not None:
            start = c.start if body.start is None else round(body.start, 3)
            end = c.end if body.end is None else round(body.end, 3)
            validate_range(start, end, cfg.detect.max_clip_s, job.duration if job else 0.0)
            if (start, end) != (c.start, c.end):
                c.start, c.end = start, end
                # hasil lama tidak lagi sesuai rentang → perlu render ulang
                # (subtitle tetap: waktunya digeser otomatis, lihat subdoc.shift_lines)
                c.clip_path = c.credit_path = None
                c.thumb_path = c.thumb_landscape_path = None
        if body.selected is not None:
            c.selected = body.selected
        if body.thumb_text is not None:
            c.thumb_text = body.thumb_text.strip() or None
        s.add(c)
        s.commit()
        s.refresh(c)
        return CandidateOut.of(c)
