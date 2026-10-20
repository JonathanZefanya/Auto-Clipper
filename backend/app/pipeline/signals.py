"""Utilitas sinyal per detik yang dipakai audio (F-03) dan chat (F-04)."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter


def relative_z(x: np.ndarray, baseline_s: int) -> np.ndarray:
    """Lonjakan relatif sebagai z-score: (x − median bergerak) / std, nilai negatif dipotong ke 0.

    Suara/chat yang ramai secara konstan ikut menaikkan baseline, sehingga hanya
    lonjakan yang mendapat skor tinggi (PRD §12 langkah 2–3).
    """
    if x.size == 0:
        return np.zeros(0)
    x = x.astype(np.float64)
    baseline = median_filter(x, size=max(1, baseline_s), mode="nearest")
    spike = x - baseline
    sd = float(spike.std())
    if sd <= 0:
        return np.zeros_like(x)
    return np.clip(spike / sd, 0.0, None)
