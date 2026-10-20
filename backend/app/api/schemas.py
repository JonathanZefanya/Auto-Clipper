"""Schema request/response API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import Candidate, Job


class PreviewIn(BaseModel):
    url: str


class PreviewOut(BaseModel):
    video_id: str
    url: str
    title: str
    channel: str
    duration: float
    thumbnail: Optional[str]
    live_status: Optional[str]
    chat_available: bool


class JobCreate(BaseModel):
    url: str
    template: Optional[str] = None
    # Opsional: metadata dari /preview agar riwayat langsung menampilkan judul saat masih antre.
    title: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[float] = None
    thumbnail: Optional[str] = None


class CandidateOut(BaseModel):
    id: int
    job_id: str
    rank: int
    peak_time: float
    start: float
    end: float
    duration: float
    score: int
    selected: bool
    clip_path: Optional[str]
    thumb_path: Optional[str]
    thumb_landscape_path: Optional[str]
    thumb_text: Optional[str]
    credit_path: Optional[str]
    subs_path: Optional[str] = None
    clip_url: Optional[str]
    thumb_url: Optional[str]
    thumb_landscape_url: Optional[str]

    @classmethod
    def of(cls, c: Candidate) -> CandidateOut:
        def url(path: Optional[str]) -> Optional[str]:
            return f"/api/jobs/{c.job_id}/files/{path}" if path else None

        return cls(
            **c.model_dump(exclude={"id"}), id=c.id or 0, duration=round(c.end - c.start, 3),
            clip_url=url(c.clip_path), thumb_url=url(c.thumb_path),
            thumb_landscape_url=url(c.thumb_landscape_path),
        )


class JobOut(BaseModel):
    id: str
    url: str
    video_id: str
    title: str
    channel: str
    duration: float
    thumbnail: Optional[str]
    has_chat: bool
    template: str
    status: str
    progress: float
    message: Optional[str]
    error: Optional[str]
    task: str
    created_at: datetime
    updated_at: datetime
    queue_position: Optional[int] = None
    candidate_count: int = 0
    selected_count: int = 0
    clip_count: int = 0

    @classmethod
    def of(cls, job: Job, candidates: list[Candidate], queue_position: Optional[int]) -> JobOut:
        return cls(
            **job.model_dump(exclude={"render_options"}),
            queue_position=queue_position,
            candidate_count=len(candidates),
            selected_count=sum(1 for c in candidates if c.selected),
            clip_count=sum(1 for c in candidates if c.clip_path),
        )


class JobDetail(JobOut):
    candidates: list[CandidateOut] = Field(default_factory=list)
    render_options: Optional[dict] = None


class CandidatePatch(BaseModel):
    selected: Optional[bool] = None
    start: Optional[float] = None
    end: Optional[float] = None
    thumb_text: Optional[str] = None


class SelectionIn(BaseModel):
    """Pilih semua / hapus pilihan (F-06), atau set daftar id."""
    selected: Optional[bool] = None
    ids: Optional[list[int]] = None


class RenderIn(BaseModel):
    template: Optional[str] = None
    subtitle: Optional[bool] = None
    thumbnail: Optional[bool] = None
    landscape: Optional[bool] = None
    intro_frame: Optional[bool] = None
    only_thumbs: bool = False


class SubLineIn(BaseModel):
    start: float
    end: float
    text: str


class SubtitlesIn(BaseModel):
    lines: list[SubLineIn]


class FacecamIn(BaseModel):
    top_ratio: float = Field(0.4, ge=0.1, le=0.9)
    frames: Optional[int] = Field(None, ge=2, le=40)


class BoxIn(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class TemplateIn(BaseModel):
    name: str
    layout_type: str
    facecam_box: Optional[BoxIn] = None
    gameplay_box: Optional[BoxIn] = None
    top_ratio: float = 0.4
