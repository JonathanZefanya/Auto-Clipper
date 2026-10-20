"""F-17: auto-deteksi posisi facecam.

Facecam = wajah yang posisinya stabil di banyak frame (wajah di gameplay bergerak/berganti).
1. Sampel N frame di sepanjang video.
2. Deteksi wajah per frame dengan tiling (wajah di overlay facecam kecil terhadap frame penuh).
3. Kelompokkan deteksi berdasarkan posisi; pilih kelompok yang hadir di paling banyak frame.
4. Kotak facecam = kotak wajah median diperluas, rasio disesuaikan dengan area atas layout split.
Semua koordinat dinormalisasi 0..1 (sama dengan template F-08).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from app.config import FacecamConfig, RenderConfig
from app.templates import Box


@dataclass(frozen=True)
class Det:
    x: float  # normalisasi 0..1
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Cluster:
    dets: list[tuple[int, Det]] = field(default_factory=list)  # (indeks frame, deteksi)

    @property
    def frames(self) -> set[int]:
        return {i for i, _ in self.dets}

    def median(self) -> Det:
        arr = np.array([[d.x, d.y, d.w, d.h, d.score] for _, d in self.dets])
        return Det(*map(float, np.median(arr, axis=0)))


@dataclass(frozen=True)
class FacecamResult:
    box: Box
    face: Det
    hits: int
    frames: int
    confidence: float          # hits / frames
    best_time: float           # frame contoh dengan wajah facecam


class Detector(Protocol):
    def detect(self, rgb: np.ndarray) -> list: ...


def sample_times(duration: float, cfg: FacecamConfig) -> list[float]:
    if duration <= 0:
        return [0.0]
    lo, hi = duration * cfg.sample_from, duration * cfg.sample_to
    n = max(2, cfg.frames)
    return [float(t) for t in np.linspace(lo, hi, n)]


def tiles(width: int, height: int, grid: int) -> list[tuple[int, int, int, int]]:
    """Frame penuh + grid N×N tile berukuran 2/(N+1) frame dengan overlap 50%."""
    out = [(0, 0, width, height)]
    if grid < 2:
        return out
    tw, th = int(2 * width / (grid + 1)), int(2 * height / (grid + 1))
    for gy in range(grid):
        for gx in range(grid):
            out.append((int(gx * tw / 2), int(gy * th / 2), tw, th))
    return out


def iou(a: Det, b: Det) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def nms(dets: Sequence[Det], thresh: float) -> list[Det]:
    keep: list[Det] = []
    for d in sorted(dets, key=lambda d: -d.score):
        if all(iou(d, k) < thresh for k in keep):
            keep.append(d)
    return keep


def detect_tiled(rgb: np.ndarray, detector: Detector, cfg: FacecamConfig) -> list[Det]:
    """Deteksi wajah di frame penuh + tile, dipetakan ke koordinat normal frame, lalu NMS."""
    H, W = rgb.shape[:2]
    found: list[Det] = []
    for x0, y0, tw, th in tiles(W, H, cfg.tile_grid):
        crop = np.ascontiguousarray(rgb[y0:y0 + th, x0:x0 + tw])
        for f in detector.detect(crop):
            if f.score < cfg.min_confidence or f.w <= 0 or f.h <= 0:
                continue
            found.append(Det((x0 + f.x) / W, (y0 + f.y) / H, f.w / W, f.h / H, float(f.score)))
    return nms(found, cfg.nms_iou)


def cluster_faces(per_frame: Sequence[Sequence[Det]], cfg: FacecamConfig) -> list[Cluster]:
    """Greedy: deteksi masuk kelompok terdekat bila jarak pusat ≤ cluster_dist × lebar wajah & ukuran mirip."""
    clusters: list[Cluster] = []
    for i, dets in enumerate(per_frame):
        for d in dets:
            best, best_dist = None, math.inf
            for c in clusters:
                m = c.median()
                dist = math.hypot(d.cx - m.cx, d.cy - m.cy)
                size_ok = 0.5 <= d.w / m.w <= 2.0
                if size_ok and dist <= cfg.cluster_dist * max(d.w, m.w) and dist < best_dist:
                    best, best_dist = c, dist
            if best is None:
                best = Cluster()
                clusters.append(best)
            best.dets.append((i, d))
    return clusters


def pick_facecam(clusters: Sequence[Cluster], n_frames: int, cfg: FacecamConfig) -> Cluster | None:
    """Kelompok yang hadir di frame terbanyak (≥ min_frame_frac); seri → wajah lebih besar."""
    need = max(2, math.ceil(cfg.min_frame_frac * n_frames))
    ok = [c for c in clusters if len(c.frames) >= need]
    if not ok:
        return None
    return max(ok, key=lambda c: (len(c.frames), c.median().w))


def facecam_box(face: Det, frame_w: int, frame_h: int, target_aspect: float, cfg: FacecamConfig) -> Box:
    """Perluas kotak wajah → kotak facecam (normalisasi) dengan rasio lebar/tinggi = target_aspect (piksel)."""
    fw, fh = face.w * frame_w, face.h * frame_h
    fcx, fcy = face.cx * frame_w, face.cy * frame_h
    bw = fw * cfg.expand_w
    bh = bw / target_aspect
    if bh < fh * cfg.min_expand_h:
        bh = fh * cfg.min_expand_h
        bw = bh * target_aspect
    # muat di dalam frame (pertahankan rasio)
    scale = min(1.0, frame_w / bw, frame_h / bh)
    bw, bh = bw * scale, bh * scale
    x = min(max(0.0, fcx - bw / 2), frame_w - bw)
    y = min(max(0.0, fcy - cfg.face_y_in_box * bh), frame_h - bh)
    r = lambda v: round(v, 4)  # noqa: E731
    return Box(r(x / frame_w), r(y / frame_h), r(min(bw / frame_w, 1 - x / frame_w)), r(min(bh / frame_h, 1 - y / frame_h)))


def target_aspect(rcfg: RenderConfig, top_ratio: float) -> float:
    """Rasio lebar/tinggi area facecam di output split (mis. 1080 × 768 → 1.406)."""
    return rcfg.width / max(1, round(rcfg.height * top_ratio))


def detect_facecam(
    source: Path, duration: float, top_ratio: float, rcfg: RenderConfig, cfg: FacecamConfig,
    detector: Detector,
) -> FacecamResult | None:
    from app.pipeline.thumbnail import grab_frame

    W, H = cfg.frame_width, cfg.frame_height
    graph = f"[0:v]scale={W}:{H},setsar=1[v]"  # koordinat normal tetap benar walau rasio sumber beda
    times = sample_times(duration, cfg)
    per_frame: list[list[Det]] = []
    for t in times:
        try:
            rgb = grab_frame(source, t, graph, W, H)
        except RuntimeError:
            per_frame.append([])
            continue
        per_frame.append(detect_tiled(rgb, detector, cfg))

    best = pick_facecam(cluster_faces(per_frame, cfg), len(times), cfg)
    if best is None:
        return None
    face = best.median()
    top = max(best.dets, key=lambda fd: fd[1].score)
    return FacecamResult(
        box=facecam_box(face, W, H, target_aspect(rcfg, top_ratio), cfg),
        face=face,
        hits=len(best.frames),
        frames=len(times),
        confidence=round(len(best.frames) / len(times), 3),
        best_time=times[top[0]],
    )
