import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.config import DetectConfig
from app.pipeline.detect import combine, detect
from app.pipeline.reaction import ReactionScorer, reaction_scores, windows_to_seconds


def test_windows_to_seconds_maps_overlap_and_max():
    # jendela 0.975 dtk: mulai 0.0 → detik 0; mulai 1.95 → detik 1 dan 2
    out = windows_to_seconds([(0.0, 0.2), (0.975, 0.5), (1.95, 0.9), (100.0, 1.0)], 4)
    np.testing.assert_allclose(out, [0.5, 0.9, 0.9, 0.0])


def test_reaction_scores_spike():
    per_sec = np.full(300, 0.02)
    per_sec[150:153] = 0.9
    z = reaction_scores(per_sec, DetectConfig())
    assert int(np.argmax(z)) in range(150, 153) and z.min() >= 0


def test_combine_three_signals_and_missing():
    cfg = DetectConfig(w_audio=0.5, w_chat=0.5, w_reaction=1.0)
    a, c, r = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
    np.testing.assert_allclose(combine(a, c, cfg, r), [0.25, 0.25, 0.5])
    np.testing.assert_allclose(combine(a, None, cfg, r), [1 / 3, 0, 2 / 3])  # tanpa chat
    np.testing.assert_allclose(combine(a, None, cfg, None), a)


def test_reaction_creates_candidate():
    rng = np.random.default_rng(1)
    audio = rng.uniform(0, 0.05, 900)
    audio[200:207] = 1.0
    reaction = np.zeros(900)
    reaction[600:607] = 3.0  # tawa tanpa lonjakan volume
    res = detect(audio, None, 900, DetectConfig(w_reaction=1.0), reaction=reaction)
    assert 600 <= max(c.peak_time for c in res.candidates) <= 607


YAMNET = Path(__file__).resolve().parents[2] / "data" / "models" / "yamnet.tflite"


@pytest.mark.skipif(not YAMNET.exists() or shutil.which("ffmpeg") is None, reason="butuh yamnet.tflite + FFmpeg")
def test_reaction_scorer_real_model():
    sr = 16000
    with ReactionScorer(YAMNET, DetectConfig().reaction_classes, sr) as scorer:
        for _ in range(3):  # 3 chunk @ 20 dtk sinus (bukan reaksi)
            scorer.feed((0.2 * np.sin(2 * np.pi * 440 * np.arange(sr * 20) / sr)).astype(np.float32))
    assert scorer.error is None
    per_sec = scorer.per_second(60)
    assert per_sec.shape == (60,) and per_sec.max() < 0.3
    assert len(scorer.windows) >= 60
