"""F-01 (validasi link + metadata) dan F-02 (unduh video & live chat) via yt-dlp."""
from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from app.config import DetectConfig

_VIDEO_ID = r"(?P<id>[A-Za-z0-9_-]{11})"
_URL_PATTERNS = [
    re.compile(rf"^https?://(?:www\.|m\.|music\.)?youtube\.com/watch\?(?:[^#]*&)?v={_VIDEO_ID}(?:[&#].*)?$"),
    re.compile(rf"^https?://youtu\.be/{_VIDEO_ID}(?:[?#/].*)?$"),
    re.compile(rf"^https?://(?:www\.|m\.)?youtube\.com/live/{_VIDEO_ID}(?:[?#/].*)?$"),
]

ProgressFn = Callable[[str, float], None]


class DownloadError(RuntimeError):
    pass


@dataclass
class VideoMeta:
    video_id: str
    url: str
    title: str
    channel: str
    duration: float
    thumbnail: str | None
    live_status: str | None
    chat_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_youtube_url(url: str) -> str:
    """Kembalikan video_id, atau ValueError jika format link tidak didukung."""
    url = url.strip()
    for pattern in _URL_PATTERNS:
        m = pattern.match(url)
        if m:
            return m.group("id")
    raise ValueError(
        f"Link tidak valid: {url!r}. Format yang didukung: "
        "youtube.com/watch?v=<id>, youtu.be/<id>, youtube.com/live/<id>"
    )


def _canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _ydl(opts: dict[str, Any]):
    import yt_dlp

    base = {"quiet": True, "no_warnings": True, "noplaylist": True}
    return yt_dlp.YoutubeDL({**base, **opts})


def fetch_metadata(url: str) -> VideoMeta:
    import yt_dlp

    video_id = parse_youtube_url(url)
    canonical = _canonical_url(video_id)
    try:
        with _ydl({"skip_download": True}) as ydl:
            info = ydl.extract_info(canonical, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(f"Gagal mengambil metadata video: {e}") from e

    live_status = info.get("live_status")
    if live_status in ("is_live", "is_upcoming"):
        raise DownloadError("Video masih live / belum mulai. Tunggu sampai VOD tersedia.")

    return VideoMeta(
        video_id=video_id,
        url=canonical,
        title=info.get("title") or "",
        channel=info.get("channel") or info.get("uploader") or "",
        duration=float(info.get("duration") or 0),
        thumbnail=info.get("thumbnail"),
        live_status=live_status,
        chat_available="live_chat" in (info.get("subtitles") or {}),
    )


def _progress_hook(label: str, on_progress: ProgressFn | None):
    """Progres gabungan semua file (video + audio diunduh terpisah), dijaga tidak mundur
    walau yt-dlp memperbarui perkiraan ukuran total."""
    files: dict[str, tuple[float, float]] = {}
    best = 0.0

    def hook(d: dict[str, Any]) -> None:
        nonlocal best
        if on_progress is None or d.get("status") not in ("downloading", "finished"):
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if not total:
            return
        done = total if d.get("status") == "finished" else d.get("downloaded_bytes", 0)
        files[str(d.get("filename", ""))] = (float(done), float(total))
        pct = 100.0 * sum(f[0] for f in files.values()) / sum(f[1] for f in files.values())
        best = max(best, min(pct, 99.9))
        on_progress(label, best)

    return hook


def download_video(
    url: str, job_dir: Path, cfg: DetectConfig, on_progress: ProgressFn | None = None
) -> Path:
    """Unduh video maks `download_max_height` ke job_dir/source.mp4."""
    import yt_dlp

    target = job_dir / "source.mp4"
    h = cfg.download_max_height
    opts = {
        "format": (
            f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={h}]+ba/b[height<={h}]"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(job_dir / "source.%(ext)s"),
        "progress_hooks": [_progress_hook("video", on_progress)],
        "noprogress": True,
    }
    try:
        with _ydl(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(f"Gagal mengunduh video: {e}") from e
    if not target.exists():
        raise DownloadError(f"Unduhan selesai tetapi {target.name} tidak ditemukan.")
    return target


def download_chat(url: str, job_dir: Path, on_progress: ProgressFn | None = None) -> Path | None:
    """Unduh live chat replay ke job_dir/chat.json. None jika tidak tersedia/gagal."""
    import yt_dlp

    target = job_dir / "chat.json"
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "subtitleslangs": ["live_chat"],
        "outtmpl": str(job_dir / "source.%(ext)s"),
        "progress_hooks": [_progress_hook("chat", on_progress)],
        "noprogress": True,
    }
    try:
        with _ydl(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        print(f"  [peringatan] live chat gagal diunduh, lanjut tanpa chat: {e}", file=sys.stderr)
        return None
    produced = sorted(job_dir.glob("source*.live_chat.json"))
    if not produced:
        return None
    produced[0].replace(target)
    return target
