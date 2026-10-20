"""F-18: reaksi wajah dari area facecam dengan MediaPipe Face Landmarker (blendshapes).

Frame area facecam di-crop & di-scale oleh FFmpeg lalu dibaca satu per satu dari pipe (hemat RAM).
Decode CPU berjalan bersamaan dengan pembacaan ekspresi; total ≈ waktu decode (±4% durasi untuk 1080p60).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np

from app.config import DetectConfig
from app.pipeline.audio import require_ffmpeg
from app.pipeline.signals import relative_z
from app.templates import Box


def expression_score(bs: Mapping[str, float] | None) -> float:
    """0..1: maks dari 'kaget' (mulut terbuka + mata melebar + alis naik) dan 'tertawa' (senyum + mulut terbuka)."""
    if not bs:
        return 0.0
    g = lambda k: float(bs.get(k, 0.0))  # noqa: E731
    jaw = g("jawOpen")
    surprise = (jaw + (g("eyeWideLeft") + g("eyeWideRight")) / 2 + g("browInnerUp")) / 3
    laugh = ((g("mouthSmileLeft") + g("mouthSmileRight")) / 2 + jaw) / 2
    return max(surprise, laugh)


def samples_to_seconds(samples: Sequence[tuple[float, float]], duration_s: int) -> np.ndarray:
    """[(detik, skor)] → array per detik (maks sampel di detik itu)."""
    out = np.zeros(max(0, duration_s))
    for t, score in samples:
        i = int(t)
        if 0 <= i < duration_s and score > out[i]:
            out[i] = score
    return out


def face_scores(per_second: np.ndarray, cfg: DetectConfig) -> np.ndarray:
    """face_z: lonjakan ekspresi relatif terhadap baseline median bergerak (streamer yang selalu
    tersenyum tidak membuat semua detik bernilai tinggi)."""
    return relative_z(per_second, cfg.face_baseline_s)


def crop_filter(box: Box, fps: float, size: int) -> str:
    return (
        f"fps={fps},"
        f"crop=trunc(iw*{box.w:.4f}/2)*2:trunc(ih*{box.h:.4f}/2)*2:trunc(iw*{box.x:.4f}):trunc(ih*{box.y:.4f}),"
        f"scale={size}:{size}"
    )


def analyze_face(
    source: Path, box: Box, duration_s: float, cfg: DetectConfig, model_path: Path,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[np.ndarray, float]:
    """Kembalikan (skor ekspresi per detik 0..1, fraksi frame dengan wajah terdeteksi).

    on_progress(%) boleh melempar (pembatalan) → FFmpeg dihentikan.
    """
    import mediapipe as mp

    size = cfg.face_size
    frame_bytes = size * size * 3
    cmd = [
        require_ffmpeg(), "-nostdin", "-v", "error", "-i", str(source), "-an",
        "-vf", crop_filter(box, cfg.face_fps, size), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
    )
    samples: list[tuple[float, float]] = []
    found = total = 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdout is not None
    try:
        with mp.tasks.vision.FaceLandmarker.create_from_options(options) as lm:
            while True:
                buf = proc.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                t = total / cfg.face_fps
                rgb = np.frombuffer(buf, np.uint8).reshape(size, size, 3).copy()
                res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(t * 1000))
                if res.face_blendshapes:
                    found += 1
                    bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
                    samples.append((t, expression_score(bs)))
                total += 1
                if on_progress and duration_s and total % max(1, int(cfg.face_fps * 10)) == 0:
                    on_progress(min(100.0, 100.0 * t / duration_s))
    except BaseException:
        proc.kill()
        raise
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    n_sec = int(np.ceil(duration_s)) if duration_s else int(np.ceil(total / cfg.face_fps))
    return samples_to_seconds(samples, n_sec), (found / total if total else 0.0)
