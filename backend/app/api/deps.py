from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Candidate, Job
from app.worker import Worker


def engine(request: Request) -> Engine:
    return request.app.state.engine


def worker(request: Request) -> Worker:
    return request.app.state.worker


def config(request: Request) -> AppConfig:
    return request.app.state.config_loader()


def get_job_or_404(s: Session, job_id: str) -> Job:
    job = s.get(Job, job_id)
    if job is None:
        raise HTTPException(404, f"Job {job_id} tidak ditemukan")
    return job


def job_candidates(s: Session, job_id: str) -> list[Candidate]:
    return list(s.exec(select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.rank)).all())
