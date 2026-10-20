"""Orkestrasi pipeline (detect: F-01..F-05, render: F-08..F-12) — dipakai CLI dan worker API.

Modul ini tidak tahu soal job.json / SQLite; status & progres dilaporkan lewat `Reporter`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.config import DetectConfig, RenderConfig, SubtitleConfig, ThumbnailConfig
from app.jobs import write_json
from app.pipeline import audio, chat, detect, download, subdoc
from app.pipeline.detect import Candidate
from app.templates import Template

# report(status, progress_0_100 | None, message | None); status: downloading | analyzing | rendering
# Reporter boleh melempar `Cancelled` untuk menghentikan job di titik progres berikutnya.
Reporter = Callable[[str, float | None, str | None], None]


class Cancelled(Exception):
    """Job dibatalkan pengguna (dilempar dari Reporter)."""


def _noop(status: str, progress: float | None = None, message: str | None = None) -> None:
    pass


def _round_list(x: np.ndarray | None) -> list[float] | None:
    return None if x is None else [round(float(v), 4) for v in x]


def rel_path(path: Path, root: Path) -> str:
    """Path relatif dengan '/' (konsisten di Windows & Linux, aman untuk URL)."""
    return path.relative_to(root).as_posix()


# ================================================================ detect

@dataclass
class DetectOutput:
    meta: download.VideoMeta
    has_chat: bool
    candidates: list[Candidate]
    used_fallback: bool
    threshold: float
    has_reaction: bool = False


def load_or_fetch_meta(url: str, job_dir: Path, force: bool = False) -> download.VideoMeta:
    meta_path = job_dir / "meta.json"
    if meta_path.exists() and (job_dir / "source.mp4").exists() and not force:
        return download.VideoMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
    meta = download.fetch_metadata(url)
    job_dir.mkdir(parents=True, exist_ok=True)
    write_json(meta_path, meta.to_dict())
    return meta


def _open_reaction_scorer(cfg: DetectConfig, models_dir: Path | None, log: Callable[[str], None]):
    """F-15: siapkan YAMNet; gagal (offline, MediaPipe error) → None, analisis lanjut tanpa sinyal ini."""
    if not cfg.reaction_enabled or models_dir is None:
        return None
    from app.pipeline.assets import ensure_model
    from app.pipeline.reaction import ReactionScorer

    try:
        model = ensure_model(models_dir, cfg.reaction_model_url, log=log)
        return ReactionScorer(model, cfg.reaction_classes, cfg.audio_sample_rate, log=log).__enter__()
    except Exception as e:
        log(f"deteksi tawa/teriak tidak tersedia: {e}")
        return None


def run_detect(
    url: str, job_dir: Path, cfg: DetectConfig, report: Reporter = _noop,
    force_download: bool = False, models_dir: Path | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> DetectOutput:
    """Unduh (reuse bila ada) → analisis audio & chat → kandidat. Menulis meta/scores/candidates.json.

    Raises download.DownloadError (unduh gagal), RuntimeError/ValueError (analisis gagal).
    """
    audio.require_ffmpeg()
    job_dir.mkdir(parents=True, exist_ok=True)

    # ---- F-01 + F-02
    report("downloading", 0, "mengambil metadata")
    meta = load_or_fetch_meta(url, job_dir, force_download)

    source = job_dir / "source.mp4"
    if source.exists() and not force_download:
        report("downloading", 90, "source.mp4 sudah ada, dipakai ulang")
    else:
        download.download_video(
            meta.url, job_dir, cfg,
            lambda _label, pct: report("downloading", pct * 0.9, "mengunduh video"),
        )

    chat_path: Path | None = job_dir / "chat.json"
    if chat_path.exists() and not force_download:
        report("downloading", 100, "chat.json sudah ada, dipakai ulang")
    elif meta.chat_available:
        report("downloading", 90, "mengunduh live chat")
        chat_path = download.download_chat(
            meta.url, job_dir,
            lambda _label, pct: report("downloading", 90 + pct * 0.1, "mengunduh live chat"),
        )
    else:
        chat_path = None
    report("downloading", 100, "live chat: " + ("ada" if chat_path else "tidak ada (audio saja)"))

    # ---- F-03 .. F-05
    report("analyzing", 0, "analisis audio")
    scorer = _open_reaction_scorer(cfg, models_dir, log)
    label = "analisis audio + tawa/teriak" if scorer else "analisis audio"
    try:
        _, audio_score = audio.analyze_audio(
            source, cfg, duration_s=meta.duration or None,
            on_progress=lambda pct: report("analyzing", pct * 0.9, label),
            consumers=[scorer.feed] if scorer else (),
        )
    finally:
        if scorer:
            scorer.__exit__(None, None, None)
    duration_s = int(audio_score.size)

    reaction_score = None
    if scorer and scorer.error is None and scorer.windows:
        from app.pipeline.reaction import reaction_scores

        reaction_score = reaction_scores(scorer.per_second(duration_s), cfg)

    chat_score = None
    if chat_path is not None:
        report("analyzing", 90, "analisis chat")
        offsets = chat.parse_chat(chat_path)
        if offsets.size:
            chat_score = chat.chat_scores(offsets, duration_s, cfg)
        report("analyzing", 97, f"{offsets.size} pesan chat")

    result = detect.detect(audio_score, chat_score, duration_s, cfg, reaction=reaction_score)
    write_json(job_dir / "scores.json", {
        "fps": 1,
        "duration": duration_s,
        "has_chat": chat_score is not None,
        "has_reaction": reaction_score is not None,
        "reaction": _round_list(reaction_score),
        "threshold": round(result.threshold, 4),
        "used_fallback": result.used_fallback,
        "excluded": result.excluded,
        "config": cfg.to_dict(),
        "audio": _round_list(audio_score),
        "chat": _round_list(chat_score),
        "combined": _round_list(result.combined),
        "smoothed": _round_list(result.smoothed),
    })
    write_json(job_dir / "candidates.json", [c.to_dict() for c in result.candidates])
    report("analyzing", 100, f"{len(result.candidates)} kandidat ditemukan")
    return DetectOutput(meta, chat_score is not None, result.candidates, result.used_fallback,
                        result.threshold, has_reaction=reaction_score is not None)


# ================================================================ render

@dataclass
class ClipSpec:
    rank: int
    start: float
    end: float
    peak_time: float
    thumb_text: str | None = None


@dataclass
class ClipResult:
    rank: int
    clip_path: str | None = None          # relatif terhadap job_dir, pakai '/'
    thumb_path: str | None = None
    thumb_landscape_path: str | None = None
    thumb_text: str | None = None
    credit_path: str | None = None
    subs_path: str | None = None
    encoder: str | None = None
    has_face: bool | None = None


@dataclass
class RenderOptions:
    subtitle: bool = True
    thumbnail: bool = True
    landscape: bool = False
    intro_frame: bool = False
    only_thumbs: bool = False


@dataclass
class Credit:
    """F-12: info kredit sumber untuk clip_<nn>.txt."""
    title: str
    url: str
    channel: str


def credit_text(credit: Credit, start: float, end: float) -> str:
    def ts(s: float) -> str:
        s = int(s)
        return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:d}:{s % 60:02d}"

    sep = "&" if "?" in credit.url else "?"
    return (
        f"Judul sumber : {credit.title}\n"
        f"Channel      : {credit.channel}\n"
        f"Link sumber  : {credit.url}{sep}t={int(start)}s\n"
        f"Rentang      : {ts(start)} - {ts(end)}\n"
    )


@dataclass
class _Progress:
    """Progres gabungan beberapa fase berbobot → 0..100 untuk status 'rendering'."""
    report: Reporter
    total: float
    done: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)

    def step(self, phase: str, frac: float, message: str) -> None:
        w = self.weights[phase]
        self.report("rendering", min(100.0, 100.0 * (self.done + w * frac) / self.total), message)

    def finish(self, phase: str) -> None:
        self.done += self.weights[phase]


def _transcribe_clip(tr: Any, source: Path, c: ClipSpec, scfg: SubtitleConfig) -> tuple[list, list]:
    from app.pipeline import subtitle

    dur = c.end - c.start
    pcm = subtitle.extract_audio_segment(source, c.start, dur, scfg.sample_rate, scfg.audio_filter)
    words = subtitle.clamp_words(tr.transcribe(pcm), dur)
    return words, subtitle.group_words(words, scfg)


def run_transcribe(
    source: Path, job_dir: Path, clips: list[ClipSpec], scfg: SubtitleConfig,
    report: Reporter = _noop, log: Callable[[str], None] = lambda _m: None,
) -> dict[int, str]:
    """F-16: transkripsi klip (tanpa render) → dokumen subtitle yang bisa diedit. Hasil: rank → subs_path."""
    from app.pipeline import subtitle

    audio.require_ffmpeg()
    if not clips:
        raise ValueError("Tidak ada klip yang dipilih")
    out: dict[int, str] = {}
    report("transcribing", 0, "memuat model Whisper")
    with subtitle.Transcriber(scfg, log=log) as tr:
        for i, c in enumerate(clips):
            report("transcribing", 100 * i / len(clips), f"transkripsi klip #{c.rank} ({tr.device})")
            words, lines = _transcribe_clip(tr, source, c, scfg)
            path = subdoc.save_doc(job_dir, c.rank, subdoc.SubDoc(c.start, c.end, lines,
                                                                     source=subdoc.fingerprint(scfg)))
            out[c.rank] = rel_path(path, job_dir)
            log(f"#{c.rank}: {len(words)} kata → {len(lines)} baris ({tr.device})")
    log("model Whisper di-unload")
    report("transcribing", 100, "transkripsi selesai")
    return out


def run_render(
    source: Path, job_dir: Path, clips: list[ClipSpec], template: Template,
    rcfg: RenderConfig, scfg: SubtitleConfig, tcfg: ThumbnailConfig, models_dir: Path,
    options: RenderOptions, report: Reporter = _noop, credit: Credit | None = None,
    log: Callable[[str], None] = lambda _m: None,
) -> list[ClipResult]:
    """Transkripsi (GPU) → unload → thumbnail (CPU) → render (NVENC). Urutan menjaga VRAM."""
    from app.pipeline import render, subtitle, thumbnail

    audio.require_ffmpeg()
    if not clips:
        raise ValueError("Tidak ada klip yang dipilih")
    if options.intro_frame and not options.thumbnail:
        raise ValueError("Frame pembuka butuh thumbnail aktif")

    clips_dir = job_dir / "clips"
    thumbs_dir = job_dir / "thumbs"
    clips_dir.mkdir(parents=True, exist_ok=True)
    layout = render.build_layout(template, rcfg)
    results = {c.rank: ClipResult(rank=c.rank, thumb_text=c.thumb_text) for c in clips}

    do_subs = options.subtitle and not options.only_thumbs
    need_text = {c.rank for c in clips if options.thumbnail and not c.thumb_text}
    # F-16: dokumen subtitle (hasil edit / transkripsi sebelumnya) dipakai apa adanya → Whisper dilewati.
    docs = {c.rank: subdoc.load_doc(job_dir, c.rank) for c in clips}
    # dokumen otomatis dari pengaturan transkripsi lama → transkripsi ulang (hasil edit tetap dipakai)
    docs = {r: d if d is not None and d.is_current(scfg) else None for r, d in docs.items()}
    to_transcribe = [
        c for c in clips
        if docs[c.rank] is None and (do_subs or c.rank in need_text)
    ]
    do_render = not options.only_thumbs

    weights = {
        "transcribe": 2.0 * len(to_transcribe),
        "thumbnail": 1.0 * len(clips) if options.thumbnail else 0.0,
        "render": 4.0 * len(clips) if do_render else 0.0,
    }
    prog = _Progress(report, total=sum(weights.values()) or 1.0, weights=weights)

    # ---- F-10 / F-16
    lines_by_rank: dict[int, list] = {}
    words_by_rank: dict[int, list] = {}
    for c in clips:
        doc = docs[c.rank]
        if doc is not None:
            lines_by_rank[c.rank] = subdoc.display_lines(doc, c.start, c.end, scfg)
            words_by_rank[c.rank] = subdoc.lines_to_words(lines_by_rank[c.rank])
    if to_transcribe:
        prog.step("transcribe", 0, "memuat model Whisper")
        with subtitle.Transcriber(scfg, log=log) as tr:
            for i, c in enumerate(to_transcribe):
                prog.step("transcribe", i / len(to_transcribe), f"transkripsi klip #{c.rank} ({tr.device})")
                words, lines = _transcribe_clip(tr, source, c, scfg)
                words_by_rank[c.rank], lines_by_rank[c.rank] = words, lines
                # simpan agar bisa diedit lalu dirender ulang tanpa Whisper
                path = subdoc.save_doc(job_dir, c.rank, subdoc.SubDoc(c.start, c.end, lines,
                                                                     source=subdoc.fingerprint(scfg)))
                results[c.rank].subs_path = rel_path(path, job_dir)
                log(f"#{c.rank}: {len(words)} kata ({tr.device})")
        log("model Whisper di-unload")
    prog.finish("transcribe")

    ass_paths: dict[int, Path] = {}
    if do_subs:
        for c in clips:
            ass = clips_dir / f"clip_{c.rank:02d}.ass"
            ass.write_text(
                subtitle.build_ass(lines_by_rank.get(c.rank, []), scfg, rcfg.width, rcfg.height,
                                   layout.gameplay_top, layout.gameplay_height),
                encoding="utf-8",
            )
            ass_paths[c.rank] = ass

    # ---- F-11
    thumb_paths: dict[int, Path] = {}
    if options.thumbnail:
        tcfg = tcfg.with_overrides(landscape=options.landscape)
        model_path = thumbnail.ensure_face_model(models_dir, tcfg.face_model_url)
        with thumbnail.FaceDetector(model_path, tcfg.face_min_confidence) as detector:
            for i, c in enumerate(clips):
                prog.step("thumbnail", i / len(clips), f"thumbnail klip #{c.rank}")
                text = c.thumb_text or thumbnail.default_text(
                    words_by_rank.get(c.rank, []), c.peak_time - c.start, tcfg)
                res = thumbnail.generate_thumbnail(
                    source, thumbs_dir, c.rank, c.peak_time, c.start, c.end, text,
                    template, rcfg, tcfg, detector,
                )
                thumb_paths[c.rank] = res.shorts_path
                r = results[c.rank]
                r.thumb_text = res.text
                r.thumb_path = rel_path(res.shorts_path, job_dir)
                r.thumb_landscape_path = rel_path(res.landscape_path, job_dir) if res.landscape_path else None
                r.has_face = res.has_face
        prog.finish("thumbnail")

    # ---- F-08 / F-09 / F-12
    if do_render:
        for i, c in enumerate(clips):
            out = clips_dir / f"clip_{c.rank:02d}.mp4"
            base = i / len(clips)
            msg = f"render klip #{c.rank}"
            prog.step("render", base, msg)
            used = render.render_clip(
                source, out, c.start, c.end, template, rcfg,
                ass_path=ass_paths.get(c.rank),
                on_progress=lambda pct, base=base, msg=msg: prog.step(
                    "render", base + pct / 100 / len(clips), msg),
                intro_image=thumb_paths.get(c.rank) if options.intro_frame else None,
                intro_s=tcfg.intro_duration_s,
            )
            r = results[c.rank]
            r.clip_path = rel_path(out, job_dir)
            r.encoder = used
            if credit is not None:
                txt = clips_dir / f"clip_{c.rank:02d}.txt"
                txt.write_text(credit_text(credit, c.start, c.end), encoding="utf-8")
                r.credit_path = rel_path(txt, job_dir)
            log(f"#{c.rank}: {out.name} ({used})")
        prog.finish("render")

    report("rendering", 100, "selesai")
    return [results[c.rank] for c in clips]


def clip_specs_from_dicts(candidates: list[dict[str, Any]]) -> list[ClipSpec]:
    return [
        ClipSpec(rank=c["rank"], start=float(c["start"]), end=float(c["end"]),
                 peak_time=float(c["peak_time"]), thumb_text=c.get("thumb_text") or None)
        for c in candidates
    ]
