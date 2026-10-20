"""F-06 pilih kandidat, F-07 trim awal/akhir."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from app.api import deps
from app.api.schemas import CandidateOut, CandidatePatch
from app.config import AppConfig
from app.db import session
from app.models import Candidate, Job
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
        if job is not None and job.status == "rendering" and w.is_busy(job.id):
            raise HTTPException(409, "Job sedang dirender")

        if body.start is not None or body.end is not None:
            start = c.start if body.start is None else round(body.start, 3)
            end = c.end if body.end is None else round(body.end, 3)
            validate_range(start, end, cfg.detect.max_clip_s, job.duration if job else 0.0)
            if (start, end) != (c.start, c.end):
                c.start, c.end = start, end
                # hasil lama tidak lagi sesuai rentang → perlu render ulang
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
