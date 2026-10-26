"""Folder job dan job.json (field selaras model Job di Feature.md)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from app.models import STATUSES as JOB_STATUSES

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class Job:
    id: str
    url: str
    dir: Path
    title: str = ""
    channel: str = ""
    duration: float = 0.0
    has_chat: bool = False
    status: str = "queued"
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def json_path(self) -> Path:
        return self.dir / "job.json"

    def set_status(self, status: str, error: str | None = None) -> None:
        if status not in JOB_STATUSES:
            raise ValueError(f"status tidak dikenal: {status}")
        self.status = status
        self.error = error
        self.save()

    def save(self) -> None:
        data = asdict(self)
        data.pop("dir")
        self.json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_job_id(job_id: str) -> None:
    if not _JOB_ID_RE.match(job_id):
        raise ValueError(f"ID job tidak valid: {job_id!r}")


def create_job(jobs_dir: Path, job_id: str, url: str) -> Job:
    _validate_job_id(job_id)
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    job = Job(id=job_id, url=url, dir=job_dir)
    existing = job.json_path
    if existing.exists():
        try:
            job.created_at = json.loads(existing.read_text(encoding="utf-8")).get("created_at", job.created_at)
        except json.JSONDecodeError:
            pass
    job.save()
    return job


def load_job(jobs_dir: Path, job_id: str) -> Job:
    _validate_job_id(job_id)
    job_dir = jobs_dir / job_id
    path = job_dir / "job.json"
    if not path.exists():
        raise ValueError(f"Job {job_id!r} tidak ditemukan ({path}). Jalankan `clipper detect` dulu.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Job(dir=job_dir, **data)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
