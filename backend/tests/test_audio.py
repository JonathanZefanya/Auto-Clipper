import numpy as np

from app.config import DetectConfig
from app.pipeline.audio import audio_scores, rms_per_second

SR = 1000


def _chunks(x: np.ndarray, size: int):
    for i in range(0, x.size, size):
        yield x[i:i + size]


def test_rms_chunked_matches_direct():
    rng = np.random.default_rng(0)
    x = rng.uniform(-1, 1, SR * 10 + 300).astype(np.float32)
    rms = rms_per_second(_chunks(x, 1777), SR)  # chunk bukan kelipatan detik
    assert rms.size == 11
    direct = np.sqrt(np.mean(x[: SR * 10].reshape(10, SR).astype(np.float64) ** 2, axis=1))
    np.testing.assert_allclose(rms[:10], direct, rtol=1e-6)
    np.testing.assert_allclose(rms[10], np.sqrt(np.mean(x[SR * 10:].astype(np.float64) ** 2)), rtol=1e-6)


def test_relative_spike_detected():
    # baseline pelan, lalu bagian keras (tetap relatif) dan satu lonjakan pendek
    rms = np.full(600, 0.05)
    rms[300:600] = 0.2          # level naik permanen -> baseline ikut naik
    rms[450:455] = 0.9          # lonjakan pendek
    score = audio_scores(rms, DetectConfig())
    assert score.shape == rms.shape
    assert score.min() >= 0.0
    assert np.argmax(score) in range(450, 455)
    assert score[500:600].max() < 0.05  # level tinggi yang stabil bukan lonjakan
