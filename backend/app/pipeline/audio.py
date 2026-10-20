"""F-03: analisis lonjakan audio. Audio dibaca per chunk dari pipe FFmpeg agar hemat RAM."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

import numpy as np

from app.config import DetectConfig
from app.pipeline.signals import relative_z

_BYTES_PER_SAMPLE = 2  # s16le


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError(
            "FFmpeg tidak ditemukan di PATH. Instal dengan `winget install Gyan.FFmpeg` "
            "lalu buka ulang terminal."
        )
    return path


def iter_pcm_chunks(source: Path, sample_rate: int, chunk_s: int) -> Iterator[np.ndarray]:
    """Decode audio ke mono `sample_rate` Hz, yield float32 [-1, 1] per ~chunk_s detik."""
    cmd = [
        require_ffmpeg(), "-nostdin", "-v", "error",
        "-i", str(source), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "pipe:1",
    ]
    chunk_bytes = sample_rate * chunk_s * _BYTES_PER_SAMPLE
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    finished = False
    try:
        leftover = b""
        while True:
            data = proc.stdout.read(chunk_bytes)
            if not data:
                break
            data = leftover + data
            usable = len(data) - (len(data) % _BYTES_PER_SAMPLE)
            leftover = data[usable:]
            if usable:
                yield np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32768.0
        finished = True
    finally:
        if not finished and proc.poll() is None:
            proc.kill()  # konsumen berhenti lebih awal (mis. job dibatalkan)
        proc.stdout.close()
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        if proc.stderr:
            proc.stderr.close()
        code = proc.wait()
    if not finished:
        return
    if code != 0:
        raise RuntimeError(f"FFmpeg gagal mengekstrak audio (exit {code}): {stderr.strip()}")


def rms_per_second(chunks: Iterable[np.ndarray], sample_rate: int) -> np.ndarray:
    """RMS tiap 1 detik dari aliran chunk berukuran bebas. Detik terakhir yang parsial ikut dihitung."""
    out: list[np.ndarray] = []
    carry = np.empty(0, dtype=np.float32)
    for chunk in chunks:
        buf = np.concatenate([carry, chunk]) if carry.size else chunk
        n_full = buf.size // sample_rate
        if n_full:
            frames = buf[: n_full * sample_rate].reshape(n_full, sample_rate).astype(np.float64)
            out.append(np.sqrt(np.mean(frames**2, axis=1)))
        carry = buf[n_full * sample_rate:]
    if carry.size:
        out.append(np.array([np.sqrt(np.mean(carry.astype(np.float64) ** 2))]))
    return np.concatenate(out) if out else np.zeros(0)


def audio_scores(rms: np.ndarray, cfg: DetectConfig) -> np.ndarray:
    """audio_z: RMS (dB) relatif terhadap baseline median bergerak, dalam z-score ≥ 0."""
    import librosa

    if rms.size == 0:
        return np.zeros(0)
    db = librosa.amplitude_to_db(np.maximum(rms, 1e-10), ref=1.0, top_db=None)
    db = np.maximum(db, cfg.audio_floor_db)  # lantai untuk keheningan digital
    return relative_z(db, cfg.audio_baseline_s)


def analyze_audio(
    source: Path, cfg: DetectConfig,
    duration_s: float | None = None, on_progress: Callable[[float], None] | None = None,
    consumers: Sequence[Callable[[np.ndarray], None]] = (),
) -> tuple[np.ndarray, np.ndarray]:
    """Kembalikan (rms_per_detik, audio_z). on_progress(%) dipanggil per chunk bila durasi diketahui.

    `consumers` menerima setiap chunk yang sama (mis. YAMNet F-15) → audio hanya di-decode sekali.
    """
    chunks = iter_pcm_chunks(source, cfg.audio_sample_rate, cfg.audio_chunk_s)

    def tracked() -> Iterator[np.ndarray]:
        done = 0
        for chunk in chunks:
            for consume in consumers:
                consume(chunk)
            done += chunk.size
            if on_progress and duration_s:
                on_progress(min(100.0, 100.0 * done / cfg.audio_sample_rate / duration_s))
            yield chunk

    try:
        rms = rms_per_second(tracked(), cfg.audio_sample_rate)
    finally:
        chunks.close()  # pastikan FFmpeg berhenti walau dibatalkan di tengah
    return rms, audio_scores(rms, cfg)
