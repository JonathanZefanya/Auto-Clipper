"""Worker satu antrean (F-13): hanya satu job diproses pada satu waktu (menjaga VRAM)."""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from sqlalchemy.engine import Engine
from sqlmodel import select

from app import runner
from app.config import AppConfig
from app.db import session
from app.models import ACTIVE_STATUSES, Candidate, Job, utcnow
from app.pipeline.download import DownloadError
from app.templates import ensure_default_templates, load_template

log = logging.getLogger("autoclip.worker")

TASKS = ("detect", "transcribe", "render")


class DbReporter:
    """Reporter runner → tabel Job. Ditahan (throttle) agar tidak menulis DB tiap frame."""

    def __init__(
        self, engine: Engine, job_id: str, min_interval_s: float = 0.4,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.engine = engine
        self.job_id = job_id
        self.min_interval_s = min_interval_s
        self.cancel_event = cancel_event
        self._last: tuple[str, str | None] = ("", None)
        self._last_pct = -100.0
        self._last_t = 0.0

    def __call__(self, status: str, progress: float | None = None, message: str | None = None) -> None:
        # Titik pembatalan: setiap laporan progres (unduh, analisis per chunk, render per baris progres).
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise runner.Cancelled()
        now = time.monotonic()
        changed = (status, message) != self._last
        pct = max(self._last_pct, 0.0) if progress is None else progress
        moved = abs(pct - self._last_pct) >= 1.0 and now - self._last_t >= self.min_interval_s
        if not (changed or moved or (pct >= 100 and self._last_pct < 100)):
            return
        self._last, self._last_pct, self._last_t = (status, message), pct, now
        with session(self.engine) as s:
            job = s.get(Job, self.job_id)
            if job is None:
                return
            job.status = status
            job.progress = round(max(0.0, min(100.0, pct)), 1)
            job.message = message
            job.updated_at = utcnow()
            s.add(job)
            s.commit()

    def log(self, message: str) -> None:
        log.info("[%s] %s", self.job_id, message)


def set_status(engine: Engine, job_id: str, status: str, *, progress: float | None = None,
               message: str | None = None, error: str | None = None) -> None:
    with session(engine) as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        job.status = status
        if progress is not None:
            job.progress = progress
        job.message = message
        job.error = error
        job.updated_at = utcnow()
        s.add(job)
        s.commit()


def reuse_existing_source(jobs_dir: Path, job_dir: Path, video_id: str) -> bool:
    """Hardlink source.mp4/meta.json/chat.json dari job lain dengan video sama (hemat unduh & disk)."""
    if (job_dir / "source.mp4").exists():
        return True
    for other in jobs_dir.iterdir() if jobs_dir.exists() else []:
        if other == job_dir or not other.is_dir():
            continue
        meta = other / "meta.json"
        src = other / "source.mp4"
        if not (src.exists() and meta.exists()):
            continue
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("video_id") != video_id:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            for name in ("source.mp4", "meta.json", "chat.json"):
                if (other / name).exists() and not (job_dir / name).exists():
                    os.link(other / name, job_dir / name)
            return True
        except OSError:
            return False
    return False


class Worker:
    def __init__(
        self, engine: Engine, config_loader: Callable[[], AppConfig],
        detect_fn: Callable = runner.run_detect, render_fn: Callable = runner.run_render,
        transcribe_fn: Callable = runner.run_transcribe,
    ) -> None:
        self.engine = engine
        self.config_loader = config_loader
        self.detect_fn = detect_fn
        self.render_fn = render_fn
        self.transcribe_fn = transcribe_fn
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._pending: list[str] = []
        self._skip: set[str] = set()          # job antre yang dibatalkan sebelum sempat jalan
        self._cancel_event = threading.Event()  # pembatalan job yang sedang berjalan
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.current: str | None = None
        self._current_task: str | None = None

    # ------------------------------------------------------------ antrean
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="autoclip-worker", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout)
            self._thread = None

    def enqueue(self, job_id: str, task: str) -> None:
        if task not in TASKS:
            raise ValueError(f"task tidak dikenal: {task}")
        with self._lock:
            self._pending.append(job_id)
        self._queue.put((job_id, task))

    def is_busy(self, job_id: str) -> bool:
        with self._lock:
            return job_id == self.current or job_id in self._pending

    def queue_position(self, job_id: str) -> int | None:
        """0 = sedang diproses, 1.. = urutan antrean, None = tidak di antrean."""
        with self._lock:
            if job_id == self.current:
                return 0
            return self._pending.index(job_id) + 1 if job_id in self._pending else None

    def cancel(self, job_id: str, task: str) -> str:
        """Batalkan job. Hasil: 'queued' (dikeluarkan dari antrean), 'running' (diberi tanda batal,
        berhenti di laporan progres berikutnya), atau 'idle' (tidak sedang diproses)."""
        with self._lock:
            if job_id == self.current:
                # tulis pesan DULU, baru set tanda batal → status akhir dari worker tidak tertimpa
                with session(self.engine) as s:
                    job = s.get(Job, job_id)
                    if job is not None:
                        job.message = "membatalkan…"
                        s.add(job)
                        s.commit()
                self._cancel_event.set()
                result = "running"
            elif job_id in self._pending:
                self._pending.remove(job_id)
                self._skip.add(job_id)
                result = "queued"
            else:
                result = "idle"
        if result != "running":
            self._mark_cancelled(job_id, task)
        return result

    def _restore_review(self, job_id: str, message: str) -> None:
        """Kembali ke status review: 'done' bila sudah ada klip, selain itu 'ready_for_review'."""
        with session(self.engine) as s:
            rendered = s.exec(
                select(Candidate).where(Candidate.job_id == job_id, Candidate.clip_path != None)  # noqa: E711
            ).first()
        set_status(self.engine, job_id, "done" if rendered else "ready_for_review",
                   progress=100, message=message)

    def _mark_cancelled(self, job_id: str, task: str) -> None:
        """Unduh/analisis batal → failed (bisa dihapus). Transkripsi/render batal → kembali ke review."""
        if task in ("render", "transcribe"):
            self._restore_review(job_id, "render dibatalkan" if task == "render" else "transkripsi dibatalkan")
        else:
            set_status(self.engine, job_id, "failed", progress=0, message=None,
                       error="Dibatalkan oleh pengguna")

    def join_idle(self, timeout: float = 30.0) -> bool:
        """Untuk test: tunggu sampai antrean kosong."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                if not self._pending and self.current is None:
                    return True
            time.sleep(0.02)
        return False

    def recover(self) -> int:
        """NFR-5: job yang terputus (app ditutup saat berjalan) dimasukkan ulang ke antrean."""
        with session(self.engine) as s:
            jobs = s.exec(
                select(Job).where(Job.status.in_(ACTIVE_STATUSES)).order_by(Job.created_at)
            ).all()
        for job in jobs:
            set_status(self.engine, job.id, "queued", progress=0, message="dilanjutkan setelah restart")
            self.enqueue(job.id, job.task)
        return len(jobs)

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            job_id, task = item
            with self._lock:
                if job_id in self._skip:  # dibatalkan saat masih antre
                    self._skip.discard(job_id)
                    continue
                if job_id in self._pending:
                    self._pending.remove(job_id)
                self.current, self._current_task = job_id, task
                self._cancel_event.clear()
            try:
                if task == "detect":
                    self._run_detect(job_id)
                elif task == "transcribe":
                    self._run_transcribe(job_id)
                else:
                    self._run_render(job_id)
            except Exception as e:  # worker tidak boleh mati karena satu job
                if isinstance(e, runner.Cancelled) or self._cancel_event.is_set():
                    log.info("job %s dibatalkan", job_id)
                    self._mark_cancelled(job_id, task)
                else:
                    log.exception("job %s gagal", job_id)
                    set_status(self.engine, job_id, "failed", error=f"{type(e).__name__}: {e}")
            finally:
                with self._lock:
                    self.current = self._current_task = None
                    self._cancel_event.clear()

    def _fail(self, job_id: str, error: str) -> None:
        # yt-dlp/FFmpeg bisa membungkus pembatalan jadi error biasa → tetap anggap batal.
        if self._cancel_event.is_set():
            raise runner.Cancelled()
        set_status(self.engine, job_id, "failed", error=error)

    # ------------------------------------------------------------ tugas
    def _run_detect(self, job_id: str) -> None:
        cfg = self.config_loader()
        with session(self.engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            url, video_id = job.url, job.video_id
        job_dir = cfg.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        reuse_existing_source(cfg.jobs_dir, job_dir, video_id)
        reporter = DbReporter(self.engine, job_id, cancel_event=self._cancel_event)
        try:
            out = self.detect_fn(url, job_dir, cfg.detect, reporter,
                                 models_dir=cfg.models_dir, log=reporter.log, facecam_cfg=cfg.facecam)
        except (DownloadError, RuntimeError, ValueError, OSError) as e:
            self._fail(job_id, str(e))
            return
        if self._cancel_event.is_set():
            raise runner.Cancelled()

        with session(self.engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            shutil.rmtree(job_dir / "subs", ignore_errors=True)  # rank kandidat baru → subtitle lama tak berlaku
            job.title, job.channel, job.duration = out.meta.title, out.meta.channel, out.meta.duration
            job.thumbnail = out.meta.thumbnail or job.thumbnail
            job.has_chat = out.has_chat
            for old in s.exec(select(Candidate).where(Candidate.job_id == job_id)).all():
                s.delete(old)
            for c in out.candidates:
                s.add(Candidate(job_id=job_id, rank=c.rank, peak_time=c.peak_time,
                                start=c.start, end=c.end, score=c.score))
            job.status, job.progress, job.error = "ready_for_review", 100.0, None
            job.message = f"{len(out.candidates)} kandidat"
            job.updated_at = utcnow()
            s.add(job)
            s.commit()

    def _selected(self, s, job_id: str) -> list[Candidate]:
        return list(s.exec(
            select(Candidate).where(Candidate.job_id == job_id, Candidate.selected == True)  # noqa: E712
            .order_by(Candidate.rank)
        ).all())

    def _run_transcribe(self, job_id: str) -> None:
        """F-16: transkripsi kandidat terpilih → dokumen subtitle yang bisa diedit (tanpa render)."""
        cfg = self.config_loader()
        with session(self.engine) as s:
            if s.get(Job, job_id) is None:
                return
            specs = [runner.ClipSpec(c.rank, c.start, c.end, c.peak_time) for c in self._selected(s, job_id)]
        job_dir = cfg.jobs_dir / job_id
        reporter = DbReporter(self.engine, job_id, cancel_event=self._cancel_event)
        try:
            paths = self.transcribe_fn(job_dir / "source.mp4", job_dir, specs, cfg.subtitle,
                                       report=reporter, log=reporter.log)
        except ImportError as e:
            self._fail(job_id, f"Library belum terpasang ({e}). Jalankan: pip install -e \".[dev,cuda]\"")
            return
        except (RuntimeError, ValueError, OSError) as e:
            self._fail(job_id, str(e))
            return
        if self._cancel_event.is_set():
            raise runner.Cancelled()
        with session(self.engine) as s:
            for c in s.exec(select(Candidate).where(Candidate.job_id == job_id)).all():
                if c.rank in paths:
                    c.subs_path = paths[c.rank]
                    s.add(c)
            s.commit()
        self._restore_review(job_id, f"{len(paths)} klip ditranskripsi — subtitle bisa diedit")

    def _run_render(self, job_id: str) -> None:
        cfg = self.config_loader()
        with session(self.engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            cands = self._selected(s, job_id)
            options = runner.RenderOptions(**json.loads(job.render_options or "{}"))
            template_name, credit = job.template, runner.Credit(job.title, job.url, job.channel)
        job_dir = cfg.jobs_dir / job_id
        try:
            ensure_default_templates(cfg.templates_dir)
            template = load_template(cfg.templates_dir, template_name)
            specs = [
                runner.ClipSpec(c.rank, c.start, c.end, c.peak_time, c.thumb_text or None) for c in cands
            ]
            set_status(self.engine, job_id, "rendering", progress=0, message="mulai render")
            reporter = DbReporter(self.engine, job_id, cancel_event=self._cancel_event)
            results = self.render_fn(
                job_dir / "source.mp4", job_dir, specs, template,
                cfg.render, cfg.subtitle, cfg.thumbnail, cfg.models_dir, options,
                report=reporter, credit=credit, log=reporter.log,
            )
        except ImportError as e:
            self._fail(job_id, f"Library belum terpasang ({e}). Jalankan: pip install -e \".[dev,cuda]\"")
            return
        except (RuntimeError, ValueError, OSError) as e:
            self._fail(job_id, str(e))
            return
        if self._cancel_event.is_set():
            raise runner.Cancelled()

        with session(self.engine) as s:
            by_rank = {
                c.rank: c for c in s.exec(select(Candidate).where(Candidate.job_id == job_id)).all()
            }
            for r in results:
                c = by_rank.get(r.rank)
                if c is None:
                    continue
                for key, value in asdict(r).items():
                    if hasattr(c, key) and key != "rank" and value is not None:
                        setattr(c, key, value)
                s.add(c)
            job = s.get(Job, job_id)
            if job is not None:
                job.status, job.progress, job.error = "done", 100.0, None
                job.message = f"{len(results)} klip selesai"
                job.updated_at = utcnow()
                s.add(job)
            s.commit()
