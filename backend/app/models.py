"""Model SQLite (F-13, NFR-5). Template layout tetap disimpan sebagai JSON di data/templates/ (F-08)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

STATUSES = (
    "queued", "downloading", "analyzing", "ready_for_review", "transcribing", "rendering", "done", "failed",
)
ACTIVE_STATUSES = ("queued", "downloading", "analyzing", "transcribing", "rendering")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    url: str
    video_id: str = Field(index=True)
    title: str = ""
    channel: str = ""
    duration: float = 0.0
    thumbnail: Optional[str] = None       # thumbnail sumber (URL YouTube)
    has_chat: bool = False
    template: str = "center"
    status: str = Field(default="queued", index=True)
    progress: float = 0.0                 # 0..100 dalam status saat ini
    message: Optional[str] = None         # langkah yang sedang berjalan
    error: Optional[str] = None
    task: str = "detect"                  # tugas terakhir/aktif: detect | transcribe | render
    render_options: Optional[str] = None  # JSON RenderOptions untuk render terakhir
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class Candidate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True)
    rank: int
    peak_time: float
    start: float
    end: float
    score: int
    selected: bool = False
    clip_path: Optional[str] = None
    thumb_path: Optional[str] = None
    thumb_landscape_path: Optional[str] = None
    thumb_text: Optional[str] = None
    credit_path: Optional[str] = None
    subs_path: Optional[str] = None       # F-16: dokumen subtitle yang bisa diedit
