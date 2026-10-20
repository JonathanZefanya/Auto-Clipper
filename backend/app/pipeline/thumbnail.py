"""F-11: thumbnail otomatis.

1. Ambil beberapa frame di sekitar puncak (sudah ditata 9:16 sesuai template, sama seperti klip).
2. Deteksi wajah dengan MediaPipe Tasks FaceDetector; pilih frame dengan wajah terbesar,
   paling yakin, dan paling tajam. Tanpa wajah → frame paling tajam.
3. Komposisi Pillow: teks besar ber-outline, diletakkan menjauhi wajah.
Output: thumbs/clip_<nn>.png (1080x1920) dan opsional thumbs/clip_<nn>_16x9.png (1280x720).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from app.config import RenderConfig, ThumbnailConfig
from app.pipeline.audio import require_ffmpeg
from app.pipeline.render import build_layout
from app.pipeline.subtitle import Word
from app.templates import Template


@dataclass(frozen=True)
class Face:
    x: float  # piksel
    y: float
    w: float
    h: float
    score: float


@dataclass(frozen=True)
class FrameScore:
    time: float
    has_face: bool
    score: float
    face_center_y: float | None  # fraksi tinggi frame


@dataclass(frozen=True)
class ThumbResult:
    shorts_path: Path
    landscape_path: Path | None
    time: float
    has_face: bool
    text: str


# ---------------------------------------------------------------- frame

def frame_times(peak: float, start: float, end: float, cfg: ThumbnailConfig) -> list[float]:
    """n_frames titik waktu di [peak − before, peak + after], dibatasi ke dalam klip."""
    lo = max(start, peak - cfg.window_before_s)
    hi = min(end - 0.05, peak + cfg.window_after_s)
    if hi <= lo:
        return [max(start, min(peak, end - 0.05))]
    n = max(1, cfg.n_frames)
    return [float(t) for t in np.linspace(lo, hi, n)]


def grab_frame(source: Path, t: float, filtergraph: str, width: int, height: int) -> np.ndarray:
    """Satu frame RGB (H, W, 3) pada waktu t setelah melewati filtergraph ([0:v] → [v])."""
    cmd = [
        require_ffmpeg(), "-nostdin", "-v", "error",
        "-ss", f"{t:.3f}", "-i", str(source),
        "-filter_complex", filtergraph, "-map", "[v]",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    expected = width * height * 3
    if proc.returncode != 0 or len(proc.stdout) < expected:
        raise RuntimeError(f"Gagal mengambil frame @{t:.2f}s: {proc.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(proc.stdout[:expected], dtype=np.uint8).reshape(height, width, 3)


def landscape_graph(width: int, height: int) -> str:
    return f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1[v]"


# ---------------------------------------------------------------- ketajaman & skor

def laplacian_variance(rgb: np.ndarray) -> float:
    """Ukuran ketajaman: varians Laplacian pada grayscale (makin besar makin tajam)."""
    if rgb.shape[0] < 3 or rgb.shape[1] < 3:
        return 0.0
    g = rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4.0 * g[1:-1, 1:-1]
    return float(lap.var())


def score_frame(rgb: np.ndarray, faces: Sequence[Face], t: float, cfg: ThumbnailConfig) -> FrameScore:
    h, w = rgb.shape[:2]
    best: tuple[float, Face] | None = None
    for f in faces:
        x0, y0 = int(max(0, f.x)), int(max(0, f.y))
        x1, y1 = int(min(w, f.x + f.w)), int(min(h, f.y + f.h))
        if x1 <= x0 or y1 <= y0:
            continue
        area = (x1 - x0) * (y1 - y0) / (w * h)
        sharp = min(1.0, laplacian_variance(rgb[y0:y1, x0:x1]) / cfg.sharpness_ref)
        s = area * f.score * (0.25 + 0.75 * sharp)
        if best is None or s > best[0]:
            best = (s, f)
    if best is not None:
        f = best[1]
        return FrameScore(t, True, best[0], (f.y + f.h / 2) / h)
    return FrameScore(t, False, laplacian_variance(rgb), None)


def pick_best(scores: Sequence[FrameScore]) -> FrameScore:
    """Frame berwajah selalu menang atas frame tanpa wajah; selebihnya skor tertinggi."""
    if not scores:
        raise ValueError("Tidak ada frame untuk dipilih")
    return max(scores, key=lambda s: (s.has_face, s.score))


# ---------------------------------------------------------------- MediaPipe

def ensure_face_model(models_dir: Path, url: str) -> Path:
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / Path(url.split("?")[0]).name
    if not path.exists():
        print(f"  mengunduh model deteksi wajah → {path.name}")
        tmp = path.with_suffix(".part")
        try:
            urllib.request.urlretrieve(url, tmp)
        except OSError as e:
            raise RuntimeError(f"Gagal mengunduh model MediaPipe dari {url}: {e}") from e
        tmp.replace(path)
    return path


class FaceDetector:
    """Context manager di sekitar MediaPipe Tasks FaceDetector (CPU, mode IMAGE)."""

    def __init__(self, model_path: Path, min_confidence: float) -> None:
        self.model_path = model_path
        self.min_confidence = min_confidence
        self._detector: Any = None
        self._mp: Any = None

    def __enter__(self) -> FaceDetector:
        import mediapipe as mp

        self._mp = mp
        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=self.min_confidence,
        )
        self._detector = mp.tasks.vision.FaceDetector.create_from_options(options)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._detector is not None:
            self._detector.close()
            self._detector = None

    def detect(self, rgb: np.ndarray) -> list[Face]:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._detector.detect(image)
        faces = []
        for d in result.detections:
            b = d.bounding_box
            score = d.categories[0].score if d.categories else 0.0
            faces.append(Face(b.origin_x, b.origin_y, b.width, b.height, float(score)))
        return faces


# ---------------------------------------------------------------- teks

_TRAILING_PUNCT = re.compile(r"[.,;:…]+$")


def default_text(words: Sequence[Word], peak_rel: float, cfg: ThumbnailConfig) -> str:
    """Potongan transkrip di sekitar puncak (maks text_max_words kata), atau fallback_text."""
    if not words:
        return cfg.fallback_text
    near = [w for w in words if abs((w.start + w.end) / 2 - peak_rel) <= cfg.text_window_s] or list(words)
    if len(near) > cfg.text_max_words:
        centre = min(range(len(near)), key=lambda i: abs((near[i].start + near[i].end) / 2 - peak_rel))
        lo = max(0, min(centre - cfg.text_max_words // 2, len(near) - cfg.text_max_words))
        near = near[lo:lo + cfg.text_max_words]
    text = _TRAILING_PUNCT.sub("", " ".join(w.text for w in near).strip())
    return text or cfg.fallback_text


def find_font(cfg: ThumbnailConfig) -> str | None:
    if cfg.font_path:
        if not Path(cfg.font_path).exists():
            raise ValueError(f"font_path tidak ditemukan: {cfg.font_path}")
        return cfg.font_path
    windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        windir / "ariblk.ttf", windir / "impact.ttf", windir / "arialbd.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Black.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _load_font(path: str | None, size: int):
    from PIL import ImageFont

    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def wrap_text(text: str, measure, max_width: float) -> list[str]:
    """Bungkus kata secara greedy berdasarkan fungsi measure(str) -> lebar piksel."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and measure(trial) > max_width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, width: int, cfg: ThumbnailConfig, font_path: str | None):
    """Ukuran font terbesar sehingga teks muat ≤ max_lines baris di dalam margin."""
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    max_w = width * (1 - 2 * cfg.margin_ratio)
    size = int(width * cfg.font_size_ratio)
    min_size = max(8, int(width * cfg.min_font_size_ratio))
    while True:
        font = _load_font(font_path, size)
        stroke = max(1, int(size * cfg.stroke_ratio))
        measure = lambda s: draw.textlength(s, font=font) + 2 * stroke  # noqa: E731
        lines = wrap_text(text, measure, max_w)
        if (len(lines) <= cfg.max_lines and all(measure(ln) <= max_w for ln in lines)) or size <= min_size:
            return font, lines, stroke
        size = max(min_size, int(size * 0.9))


def text_center_y(face_center_y: float | None, cfg: ThumbnailConfig) -> float:
    """Taruh teks di sisi yang berlawanan dengan wajah (default: bawah)."""
    if face_center_y is not None and face_center_y >= 0.5:
        return cfg.text_y_top
    return cfg.text_y_bottom


def compose(rgb: np.ndarray, text: str, face_center_y: float | None, cfg: ThumbnailConfig):
    """Gambar teks besar ber-outline di atas frame. Mengembalikan PIL.Image."""
    from PIL import Image, ImageDraw

    img = Image.fromarray(rgb).convert("RGB")
    W, H = img.size
    text = text.upper() if cfg.uppercase else text
    font, lines, stroke = fit_text(text, W, cfg, find_font(cfg))
    draw = ImageDraw.Draw(img)

    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * cfg.line_spacing)
    block_h = line_h * len(lines)
    cy = H * text_center_y(face_center_y, cfg)
    y = int(min(max(cy - block_h / 2, H * cfg.margin_ratio), H * (1 - cfg.margin_ratio) - block_h))

    for i, line in enumerate(lines):
        lw = draw.textlength(line, font=font)
        x = (W - lw) / 2
        is_last = i == len(lines) - 1
        if is_last and cfg.highlight_color and " " in line:
            head, last = line.rsplit(" ", 1)
            head += " "
            draw.text((x, y), head, font=font, fill=cfg.text_color,
                      stroke_width=stroke, stroke_fill=cfg.stroke_color)
            draw.text((x + draw.textlength(head, font=font), y), last, font=font,
                      fill=cfg.highlight_color, stroke_width=stroke, stroke_fill=cfg.stroke_color)
        else:
            fill = cfg.highlight_color if (is_last and cfg.highlight_color and len(lines) > 1) else cfg.text_color
            draw.text((x, y), line, font=font, fill=fill,
                      stroke_width=stroke, stroke_fill=cfg.stroke_color)
        y += line_h
    return img


# ---------------------------------------------------------------- orkestrasi

def generate_thumbnail(
    source: Path, out_dir: Path, rank: int, peak: float, start: float, end: float, text: str,
    template: Template, rcfg: RenderConfig, cfg: ThumbnailConfig, detector: FaceDetector,
) -> ThumbResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = build_layout(template, rcfg).filtergraph

    scores: list[FrameScore] = []
    frames: dict[float, np.ndarray] = {}
    for t in frame_times(peak, start, end, cfg):
        try:
            rgb = grab_frame(source, t, graph, rcfg.width, rcfg.height)
        except RuntimeError as e:
            print(f"  [peringatan] {e}", file=sys.stderr)
            continue
        frames[t] = rgb
        scores.append(score_frame(rgb, detector.detect(rgb), t, cfg))
    if not scores:
        raise RuntimeError(f"Tidak ada frame yang bisa diambil untuk thumbnail klip #{rank}")

    best = pick_best(scores)
    shorts_path = out_dir / f"clip_{rank:02d}.png"
    compose(frames[best.time], text, best.face_center_y, cfg).save(shorts_path, optimize=True)

    landscape_path = None
    if cfg.landscape:
        W, H = cfg.landscape_width, cfg.landscape_height
        rgb = grab_frame(source, best.time, landscape_graph(W, H), W, H)
        land = score_frame(rgb, detector.detect(rgb), best.time, cfg)
        landscape_path = out_dir / f"clip_{rank:02d}_16x9.png"
        compose(rgb, text, land.face_center_y, cfg).save(landscape_path, optimize=True)

    return ThumbResult(shorts_path, landscape_path, best.time, best.has_face, text)
