"""F-15: deteksi reaksi vokal (tawa, teriak, sorak) dengan YAMNet via MediaPipe AudioClassifier.

Dipasang sebagai konsumen chunk di analyze_audio → audio hanya di-decode sekali.
YAMNet menghasilkan satu prediksi per jendela 0,975 dtk; dipetakan ke skor per detik.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from app.config import DetectConfig
from app.pipeline.signals import relative_z

WINDOW_S = 0.975


def windows_to_seconds(windows: Sequence[tuple[float, float]], duration_s: int) -> np.ndarray:
    """[(mulai_detik, skor)] per jendela → array per detik (maks skor jendela yang menyentuh detik itu)."""
    out = np.zeros(max(0, duration_s))
    for t, score in windows:
        first = int(math.floor(t))
        last = int(math.floor(t + WINDOW_S - 1e-9))
        for sec in range(max(0, first), min(duration_s, last + 1)):
            if score > out[sec]:
                out[sec] = score
    return out


def reaction_scores(per_second: np.ndarray, cfg: DetectConfig) -> np.ndarray:
    """reaction_z: lonjakan relatif probabilitas reaksi terhadap baseline median bergerak."""
    return relative_z(per_second, cfg.reaction_baseline_s)


class ReactionScorer:
    """Context manager. `feed(chunk)` untuk tiap chunk PCM float32 mono; error → nonaktif, tidak menggagalkan job."""

    def __init__(
        self, model_path: Path, classes: Sequence[str], sample_rate: int,
        log: Callable[[str], None] = lambda _m: None,
    ) -> None:
        self.model_path = model_path
        self.classes = list(classes)
        self.sample_rate = sample_rate
        self.log = log
        self.windows: list[tuple[float, float]] = []
        self.error: str | None = None
        self._offset_s = 0.0
        self._clf: Any = None
        self._AudioData: Any = None

    def __enter__(self) -> ReactionScorer:
        from mediapipe.tasks.python import audio
        from mediapipe.tasks.python.components.containers.audio_data import AudioData
        from mediapipe.tasks.python.core.base_options import BaseOptions

        options = audio.AudioClassifierOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=audio.RunningMode.AUDIO_CLIPS,
            category_allowlist=self.classes,
            max_results=len(self.classes),
        )
        self._clf = audio.AudioClassifier.create_from_options(options)
        self._AudioData = AudioData
        return self

    def __exit__(self, *exc: object) -> None:
        if self._clf is not None:
            self._clf.close()
            self._clf = None

    @property
    def ok(self) -> bool:
        return self.error is None and self._clf is not None

    def feed(self, chunk: np.ndarray) -> None:
        start = self._offset_s
        self._offset_s += chunk.size / self.sample_rate
        if not self.ok or chunk.size < self.sample_rate * 0.1:
            return
        try:
            results = self._clf.classify(
                self._AudioData.create_from_array(np.ascontiguousarray(chunk, dtype=np.float32), self.sample_rate)
            )
        except Exception as e:  # jangan gagalkan analisis karena sinyal tambahan
            self.error = f"{type(e).__name__}: {e}"
            self.log(f"deteksi tawa/teriak dimatikan: {self.error}")
            return
        for r in results:
            cats = r.classifications[0].categories if r.classifications else []
            score = max((c.score for c in cats), default=0.0)
            self.windows.append((start + r.timestamp_ms / 1000.0, float(score)))

    def per_second(self, duration_s: int) -> np.ndarray:
        return windows_to_seconds(self.windows, duration_s)
