"""CLI: python -m clipper detect|render|templates|serve — lapisan tipis di atas app.runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import load_config
from app.jobs import create_job, load_job, write_json
from app.pipeline import download
from app.pipeline.detect import Candidate
from app.runner import (
    Credit, RenderOptions, clip_specs_from_dicts, run_detect, run_render,
)


def fmt_time(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def format_table(candidates: list[Candidate]) -> str:
    header = f"{'Rank':>4}  {'Start':>8}  {'End':>8}  {'Peak':>8}  {'Durasi':>6}  {'Skor':>4}"
    lines = [header, "-" * len(header)]
    for c in candidates:
        lines.append(
            f"{c.rank:>4}  {fmt_time(c.start):>8}  {fmt_time(c.end):>8}  "
            f"{fmt_time(c.peak_time):>8}  {str(c.duration) + 's':>6}  {c.score:>4}"
        )
    return "\n".join(lines)


class ConsoleReporter:
    """Cetak progres di satu baris; pesan baru → baris baru."""

    def __init__(self) -> None:
        self._last = ""

    def __call__(self, status: str, progress: float | None = None, message: str | None = None) -> None:
        msg = message or ""
        if msg != self._last and self._last:
            print()
        self._last = msg
        pct = f"{progress:5.1f}%" if progress is not None else "      "
        print(f"\r  [{status}] {pct} {msg}", end="", flush=True)

    def close(self) -> None:
        if self._last:
            print()
        self._last = ""


def cmd_detect(args: argparse.Namespace) -> int:
    try:
        video_id = download.parse_youtube_url(args.url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    app_cfg = load_config(Path(args.data_dir) if args.data_dir else None)
    cfg = app_cfg.detect.with_overrides(
        sensitivity=args.sensitivity,
        min_peak_gap_s=args.min_gap,
        chat_delay_s=args.chat_delay,
        w_audio=args.w_audio,
        w_chat=args.w_chat,
        w_reaction=args.w_reaction,
        reaction_enabled=False if args.no_reaction else None,
        w_face=args.w_face,
        face_enabled=False if args.no_face else None,
    )
    job = create_job(app_cfg.jobs_dir, args.job_id or video_id, args.url)
    print(f"Job: {job.id}  ({job.dir})")

    reporter = ConsoleReporter()

    def report(status: str, progress: float | None = None, message: str | None = None) -> None:
        if job.status != status:
            job.set_status(status)
        reporter(status, progress, message)

    try:
        out = run_detect(args.url, job.dir, cfg, report, force_download=args.force_download,
                         models_dir=app_cfg.models_dir, facecam_cfg=app_cfg.facecam,
                         log=lambda m: (reporter.close(), print(f"  {m}")))
    except (download.DownloadError, RuntimeError, ValueError) as e:
        reporter.close()
        job.set_status("failed", str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1
    reporter.close()

    job.title, job.channel, job.duration = out.meta.title, out.meta.channel, out.meta.duration
    job.has_chat = out.has_chat
    job.set_status("ready_for_review")

    print(f"\nJudul   : {out.meta.title}\nChannel : {out.meta.channel}\nDurasi  : {fmt_time(out.meta.duration)}")
    print(f"Live chat: {'ada' if out.has_chat else 'tidak ada (pakai audio saja)'}")
    print(f"Tawa/teriak (YAMNet): {'dipakai' if out.has_reaction else 'tidak dipakai'}")
    print(f"Ekspresi wajah     : {'dipakai' if out.has_face else 'tidak dipakai'}\n")
    if out.used_fallback:
        print("Tidak ada puncak yang melewati ambang; mengambil 1 puncak tertinggi.")
    print(f"{len(out.candidates)} kandidat (sensitivity={cfg.sensitivity}, ambang z={cfg.threshold_z:.2f}):\n")
    print(format_table(out.candidates))
    print(f"\nTersimpan: {job.dir / 'scores.json'}\n           {job.dir / 'candidates.json'}")
    return 0


def parse_ids(raw: str) -> list[int]:
    try:
        ids = [int(x) for x in raw.replace(" ", "").split(",") if x]
    except ValueError as e:
        raise ValueError(f"--ids harus berupa angka dipisah koma, mis. 1,2,3 (dapat {raw!r})") from e
    if not ids:
        raise ValueError("--ids kosong")
    return list(dict.fromkeys(ids))


def cmd_render(args: argparse.Namespace) -> int:
    from app.templates import ensure_default_templates, load_template

    app_cfg = load_config(Path(args.data_dir) if args.data_dir else None)
    rcfg = app_cfg.render.with_overrides(video_encoder=args.encoder)
    scfg = app_cfg.subtitle.with_overrides(
        model=args.whisper_model,
        cpu_model=args.whisper_model,  # model eksplisit berlaku juga saat fallback CPU
        device=args.device,
    )
    tcfg = app_cfg.thumbnail
    options = RenderOptions(
        subtitle=scfg.enabled and not args.no_subtitle,
        thumbnail=tcfg.enabled and not args.no_thumbnail,
        landscape=args.thumb_landscape or tcfg.landscape,
        intro_frame=args.intro_frame or tcfg.intro_frame,
        only_thumbs=args.only_thumbs,
    )
    try:
        ensure_default_templates(app_cfg.templates_dir)
        template = load_template(app_cfg.templates_dir, args.template or rcfg.default_template)
        job = load_job(app_cfg.jobs_dir, args.job_id)
        ids = parse_ids(args.ids)
        if args.thumb_text is not None and len(ids) != 1:
            raise ValueError("--thumb-text hanya bisa dipakai dengan satu --ids")
        if (options.only_thumbs or options.intro_frame) and not options.thumbnail:
            raise ValueError("--only-thumbs / --intro-frame butuh thumbnail aktif (hapus --no-thumbnail)")
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    source = job.dir / "source.mp4"
    cand_path = job.dir / "candidates.json"
    if not source.exists() or not cand_path.exists():
        print(f"Error: source.mp4 / candidates.json tidak ada di {job.dir}", file=sys.stderr)
        return 2
    candidates = json.loads(cand_path.read_text(encoding="utf-8"))
    by_rank = {c["rank"]: c for c in candidates}
    missing = [i for i in ids if i not in by_rank]
    if missing:
        print(f"Error: kandidat {missing} tidak ada (tersedia rank 1..{len(candidates)})", file=sys.stderr)
        return 2
    selected = [by_rank[i] for i in ids]
    for c in selected:
        if c["end"] - c["start"] > app_cfg.detect.max_clip_s:
            print(f"Error: kandidat #{c['rank']} lebih dari {app_cfg.detect.max_clip_s} detik", file=sys.stderr)
            return 2
    if args.thumb_text is not None:
        selected[0]["thumb_text"] = args.thumb_text.strip()

    what = "thumbnail" if options.only_thumbs else "render"
    print(f"Job {job.id}: {what} {len(selected)} klip, template '{template.name}' ({template.layout_type})")
    reporter = ConsoleReporter()
    try:
        job.set_status("rendering")
        results = run_render(
            source, job.dir, clip_specs_from_dicts(selected), template,
            rcfg, scfg, tcfg, app_cfg.models_dir, options, report=reporter,
            credit=Credit(job.title, job.url, job.channel),
            log=lambda m: (reporter.close(), print(f"  {m}")),
        )
    except ImportError as e:
        reporter.close()
        job.set_status("failed", str(e))
        print(f"\nError: library belum terpasang ({e}). Jalankan: pip install -e \".[dev,cuda]\"", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as e:
        reporter.close()
        job.set_status("failed", str(e))
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    reporter.close()

    for r in results:
        c = by_rank[r.rank]
        for key in ("clip_path", "thumb_path", "thumb_landscape_path", "thumb_text", "subs_path"):
            value = getattr(r, key)
            if value is not None:
                c[key] = value
    if not options.only_thumbs:
        for c in candidates:
            c["selected"] = c["rank"] in ids
    write_json(cand_path, candidates)
    job.set_status("done")

    print(f"\nHasil: {job.dir / ('thumbs' if options.only_thumbs else 'clips')}")
    for r in results:
        parts = [p for p in (r.clip_path, r.thumb_path, r.thumb_landscape_path) if p]
        text = f' — "{r.thumb_text}"' if r.thumb_text else ""
        print(f"  #{r.rank}: {', '.join(parts)}{text}")
    if options.thumbnail:
        print("Ubah teks thumbnail: edit `thumb_text` di candidates.json atau pakai --thumb-text, "
              "lalu jalankan ulang dengan --only-thumbs.")
    return 0


def cmd_templates(args: argparse.Namespace) -> int:
    from app.templates import ensure_default_templates, list_templates

    app_cfg = load_config(Path(args.data_dir) if args.data_dir else None)
    ensure_default_templates(app_cfg.templates_dir)
    print(f"Template di {app_cfg.templates_dir}:")
    for name in list_templates(app_cfg.templates_dir):
        print(f"  - {name}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from app.main import create_app

    app = create_app(Path(args.data_dir) if args.data_dir else None)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipper", description="Auto clipper: detect (M1), render + subtitle + thumbnail (M2–M3), serve (M4)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("detect", help="Unduh video + chat lalu deteksi kandidat klip")
    p.add_argument("url", help="Link YouTube (watch?v=, youtu.be/, live/)")
    p.add_argument("--sensitivity", type=float, help="0..1, makin besar makin banyak klip")
    p.add_argument("--min-gap", type=int, help="Jarak minimal antar puncak (detik)")
    p.add_argument("--chat-delay", type=int, help="Geser mundur sinyal chat (detik)")
    p.add_argument("--w-audio", type=float, help="Bobot skor audio")
    p.add_argument("--w-chat", type=float, help="Bobot skor chat")
    p.add_argument("--w-reaction", type=float, help="Bobot skor tawa/teriak (YAMNet)")
    p.add_argument("--no-reaction", action="store_true", help="Matikan deteksi tawa/teriak")
    p.add_argument("--w-face", type=float, help="Bobot skor ekspresi wajah")
    p.add_argument("--no-face", action="store_true", help="Matikan deteksi ekspresi wajah")
    p.add_argument("--job-id", help="ID job (default: video id)")
    p.add_argument("--data-dir", help="Folder data (default: <repo>/data)")
    p.add_argument("--force-download", action="store_true", help="Unduh ulang walau file sudah ada")
    p.set_defaults(func=cmd_detect)

    r = sub.add_parser("render", help="Render kandidat terpilih jadi klip 9:16 + subtitle + thumbnail")
    r.add_argument("job_id", help="ID job (folder di data/jobs/)")
    r.add_argument("--ids", required=True, help="Rank kandidat, dipisah koma, mis. 1,2,3")
    r.add_argument("--template", help="Nama template di data/templates/ (default: center)")
    r.add_argument("--no-subtitle", action="store_true", help="Render tanpa subtitle")
    r.add_argument("--whisper-model", help="medium | large-v3")
    r.add_argument("--device", choices=["auto", "cuda", "cpu"], help="Perangkat Whisper")
    r.add_argument("--encoder", choices=["auto", "h264_nvenc", "libx264"], help="Encoder video")
    r.add_argument("--no-thumbnail", action="store_true", help="Lewati pembuatan thumbnail")
    r.add_argument("--thumb-landscape", action="store_true", help="Juga buat thumbnail 1280x720")
    r.add_argument("--intro-frame", action="store_true",
                   help="Sisipkan thumbnail sebagai frame pembuka klip (±0,1 dtk)")
    r.add_argument("--thumb-text", help="Teks thumbnail (hanya dengan satu --ids)")
    r.add_argument("--only-thumbs", action="store_true", help="Buat ulang thumbnail saja, tanpa render video")
    r.add_argument("--data-dir", help="Folder data (default: <repo>/data)")
    r.set_defaults(func=cmd_render)

    t = sub.add_parser("templates", help="Tampilkan template layout yang tersedia")
    t.add_argument("--data-dir", help="Folder data (default: <repo>/data)")
    t.set_defaults(func=cmd_templates)

    s = sub.add_parser("serve", help="Jalankan backend API (FastAPI) untuk web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--data-dir", help="Folder data (default: dari config / <repo>/data)")
    s.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)
