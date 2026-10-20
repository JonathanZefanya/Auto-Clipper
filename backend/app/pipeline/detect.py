"""F-05: skor gabungan, smoothing, peak picking, dan pembentukan kandidat klip."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.signal import find_peaks

from app.config import DetectConfig


@dataclass
class Candidate:
    rank: int
    peak_time: int
    start: int
    end: int
    score: int  # 0..100

    @property
    def duration(self) -> int:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "duration": self.duration}


@dataclass
class DetectionResult:
    combined: np.ndarray
    smoothed: np.ndarray
    threshold: float
    used_fallback: bool
    candidates: list[Candidate]


def combine(
    audio: np.ndarray, chat: np.ndarray | None, cfg: DetectConfig, reaction: np.ndarray | None = None,
) -> np.ndarray:
    """w_audio·audio + w_chat·chat + w_reaction·reaction, bobot dinormalisasi atas sinyal yang ada.

    Tanpa chat dan reaksi → audio saja.
    """
    signals = [(audio, cfg.w_audio)]
    if chat is not None and chat.size:
        signals.append((chat, cfg.w_chat))
    if reaction is not None and reaction.size:
        signals.append((reaction, cfg.w_reaction))
    if len(signals) == 1:
        return audio.astype(np.float64)
    total = sum(w for _, w in signals)
    if total <= 0:
        raise ValueError("Jumlah bobot sinyal harus > 0")
    n = max(s.size for s, _ in signals)
    out = np.zeros(n)
    for s, w in signals:
        out += w * np.pad(s.astype(np.float64), (0, n - s.size))
    return out / total


def smooth(x: np.ndarray, window_s: int) -> np.ndarray:
    if window_s <= 1 or x.size == 0:
        return x.astype(np.float64)
    kernel = np.ones(window_s) / window_s
    return np.convolve(x, kernel, mode="same")[: x.size]


def pick_peaks(s: np.ndarray, cfg: DetectConfig) -> tuple[np.ndarray, float, bool]:
    """Indeks puncak di atas ambang mean + z·std, berjarak minimal min_peak_gap_s.

    Jika tidak ada yang lolos ambang, kembalikan 1 puncak tertinggi (fallback).
    """
    threshold = float(s.mean() + cfg.threshold_z * s.std())
    peaks, _ = find_peaks(s, height=threshold, distance=max(1, cfg.min_peak_gap_s))
    if peaks.size == 0:
        return np.array([int(np.argmax(s))]), threshold, True
    return peaks, threshold, False


def build_candidates(
    peaks: np.ndarray, s: np.ndarray, duration_s: int, cfg: DetectConfig
) -> list[Candidate]:
    """Puncak → jendela [p−pad_before, p+pad_after], gabung overlap, batasi max_clip_s, urut skor."""
    windows: list[list[int]] = []  # [start, end, peak]
    for p in sorted(int(p) for p in peaks):
        start = max(0, p - cfg.pad_before_s)
        end = min(duration_s, p + cfg.pad_after_s)
        if windows and start <= windows[-1][1]:
            w = windows[-1]
            w[1] = max(w[1], end)
            if s[p] > s[w[2]]:
                w[2] = p
        else:
            windows.append([start, end, p])

    max_score = float(s.max()) if s.size else 0.0
    out: list[Candidate] = []
    for start, end, p in windows:
        if end - start > cfg.max_clip_s:
            start = int(np.clip(p - cfg.pad_before_s, start, end - cfg.max_clip_s))
            end = start + cfg.max_clip_s
        score = round(100 * float(s[p]) / max_score) if max_score > 0 else 0
        out.append(Candidate(rank=0, peak_time=p, start=start, end=end, score=score))

    out.sort(key=lambda c: (-float(s[c.peak_time]), c.peak_time))
    for i, c in enumerate(out, start=1):
        c.rank = i
    return out


def detect(
    audio: np.ndarray, chat: np.ndarray | None, duration_s: int, cfg: DetectConfig,
    reaction: np.ndarray | None = None,
) -> DetectionResult:
    combined = combine(audio, chat, cfg, reaction)
    if combined.size == 0:
        raise ValueError("Sinyal kosong: tidak ada audio yang bisa dianalisis.")
    duration_s = max(duration_s, combined.size)
    smoothed = smooth(combined, cfg.smooth_window_s)
    peaks, threshold, fallback = pick_peaks(smoothed, cfg)
    candidates = build_candidates(peaks, smoothed, duration_s, cfg)
    return DetectionResult(combined, smoothed, threshold, fallback, candidates)
