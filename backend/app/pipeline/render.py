"""F-08 + F-09: potong → crop/scale sesuai template → vstack → burn subtitle → encode."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.config import RenderConfig
from app.pipeline.audio import require_ffmpeg
from app.templates import Box, Template

ProgressFn = Callable[[float], None]


@dataclass(frozen=True)
class Layout:
    """Hasil penataan output: area gameplay (y, tinggi) dipakai untuk posisi subtitle."""
    filtergraph: str
    gameplay_top: int
    gameplay_height: int


def _even(n: float) -> int:
    return int(round(n / 2)) * 2


def _crop(box: Box | None) -> str:
    if box is None:
        return ""
    return (
        f"crop=w=trunc(iw*{box.w:.4f}/2)*2:h=trunc(ih*{box.h:.4f}/2)*2:"
        f"x=trunc(iw*{box.x:.4f}):y=trunc(ih*{box.y:.4f}),"
    )


def _cover(w: int, h: int) -> str:
    """Scale agar menutupi w×h lalu crop tengah — tanpa distorsi, tanpa bar hitam."""
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def build_layout(template: Template, cfg: RenderConfig, ass_file: str | None = None) -> Layout:
    W, H = cfg.width, cfg.height
    tail = f"fps={cfg.fps},format=yuv420p"
    if ass_file:
        tail += f",ass={ass_file}"

    if template.layout_type == "split":
        top_h = _even(H * template.top_ratio)
        bot_h = H - top_h
        graph = (
            "[0:v]split=2[fc][gp];"
            f"[fc]{_crop(template.facecam_box)}{_cover(W, top_h)}[top];"
            f"[gp]{_crop(template.gameplay_box)}{_cover(W, bot_h)}[bot];"
            f"[top][bot]vstack=inputs=2,{tail}[v]"
        )
        return Layout(graph, gameplay_top=top_h, gameplay_height=bot_h)

    graph = f"[0:v]{_crop(template.gameplay_box)}{_cover(W, H)},{tail}[v]"
    return Layout(graph, gameplay_top=0, gameplay_height=H)


def with_intro(graph: str, cfg: RenderConfig, intro_s: float) -> str:
    """Tumpuk gambar input #1 (thumbnail) di atas klip selama intro_s detik pertama.

    Overlay (bukan concat) → durasi klip & sinkron audio tidak berubah, tetap ≤ 60 dtk.
    """
    if not graph.endswith("[v]"):
        raise ValueError("filtergraph harus berakhir dengan label [v]")
    main = graph[: -len("[v]")] + "[main]"
    return (
        f"{main};"
        f"[1:v]scale={cfg.width}:{cfg.height},setsar=1,format=yuva420p[intro];"
        f"[main][intro]overlay=0:0:enable='lt(t,{intro_s:.3f})':eof_action=pass,format=yuv420p[v]"
    )


@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    """Uji encode singkat; True bila h264_nvenc benar-benar bisa dipakai (driver + GPU)."""
    cmd = [
        require_ffmpeg(), "-v", "error", "-nostdin",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
        "-c:v", "h264_nvenc", "-f", "null", "-",
    ]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def choose_encoder(cfg: RenderConfig) -> str:
    if cfg.video_encoder == "auto":
        return "h264_nvenc" if nvenc_available() else "libx264"
    if cfg.video_encoder not in ("h264_nvenc", "libx264"):
        raise ValueError(f"video_encoder tidak dikenal: {cfg.video_encoder}")
    return cfg.video_encoder


def encoder_args(encoder: str, cfg: RenderConfig) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", cfg.nvenc_preset, "-tune", "hq",
                "-rc", "vbr", "-cq", str(cfg.nvenc_cq), "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", cfg.x264_preset, "-crf", str(cfg.x264_crf)]


def build_command(
    source: Path, out: Path, start: float, duration: float,
    layout: Layout, encoder: str, cfg: RenderConfig,
    intro_image: Path | None = None, intro_s: float = 0.1,
) -> list[str]:
    graph = layout.filtergraph
    intro_input: list[str] = []
    if intro_image is not None:
        graph = with_intro(graph, cfg, intro_s)
        intro_input = ["-loop", "1", "-t", f"{intro_s + 0.5:.3f}", "-i", str(intro_image)]
    return [
        require_ffmpeg(), "-y", "-nostdin", "-v", "error", "-progress", "pipe:1", "-nostats",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        *intro_input,
        "-filter_complex", graph,
        "-map", "[v]", "-map", "0:a:0?",
        *encoder_args(encoder, cfg),
        "-c:a", "aac", "-b:a", cfg.audio_bitrate,
        "-movflags", "+faststart",
        str(out),
    ]


def _run_ffmpeg(cmd: list[str], cwd: Path, duration: float, on_progress: ProgressFn | None) -> None:
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    assert proc.stdout is not None and proc.stderr is not None
    try:
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and on_progress and value.isdigit() and duration > 0:
                on_progress(min(100.0, int(value) / 1e6 / duration * 100))
    except BaseException:
        # dibatalkan (on_progress melempar) → hentikan FFmpeg, jangan biarkan jalan di belakang
        proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()
        raise
    stderr = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(stderr.strip() or f"FFmpeg exit {proc.returncode}")


def render_clip(
    source: Path, out: Path, start: float, end: float, template: Template, cfg: RenderConfig,
    ass_path: Path | None = None, on_progress: ProgressFn | None = None,
    intro_image: Path | None = None, intro_s: float = 0.1,
) -> str:
    """Render satu klip. Mengembalikan encoder yang dipakai. NVENC gagal → ulang dengan libx264.

    FFmpeg dijalankan dengan cwd = folder output dan nama file ASS relatif, sehingga
    path Windows (C:\\...) tidak perlu di-escape di dalam filtergraph.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if ass_path is not None and ass_path.parent.resolve() != out.parent.resolve():
        raise ValueError("File ASS harus berada di folder yang sama dengan output klip")
    layout = build_layout(template, cfg, ass_path.name if ass_path else None)
    duration = end - start
    encoder = choose_encoder(cfg)
    intro = intro_image.resolve() if intro_image else None

    def cmd(enc: str) -> list[str]:
        return build_command(source.resolve(), out.resolve(), start, duration, layout, enc, cfg,
                             intro_image=intro, intro_s=intro_s)

    try:
        try:
            _run_ffmpeg(cmd(encoder), out.parent, duration, on_progress)
        except RuntimeError as e:
            if encoder != "h264_nvenc":
                raise RuntimeError(f"Render gagal: {e}") from e
            _run_ffmpeg(cmd("libx264"), out.parent, duration, on_progress)
            encoder = "libx264"
    except BaseException:
        out.unlink(missing_ok=True)  # jangan tinggalkan klip setengah jadi
        raise
    return encoder
