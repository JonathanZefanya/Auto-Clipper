import numpy as np

from app.config import DetectConfig
from app.pipeline.detect import build_candidates, combine, detect


def _signal(n: int, spikes: dict[int, float], noise: float = 0.02, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, noise, n)
    for t, h in spikes.items():
        x[t - 3:t + 4] = h
    return x


def test_three_spikes_three_candidates_sorted():
    audio = _signal(1200, {200: 0.6, 600: 1.0, 1000: 0.8})
    res = detect(audio, None, 1200, DetectConfig())
    assert [c.peak_time for c in res.candidates] == [600, 1000, 200]
    assert [c.rank for c in res.candidates] == [1, 2, 3]
    assert res.candidates[0].score == 100
    assert res.candidates[1].score > res.candidates[2].score
    c = res.candidates[0]
    assert (c.start, c.end) == (580, 615)
    assert not res.used_fallback


def test_min_gap_keeps_only_strongest():
    audio = _signal(600, {300: 1.0, 330: 0.7})
    res = detect(audio, None, 600, DetectConfig())
    assert len(res.candidates) == 1
    assert res.candidates[0].peak_time == 300


def test_flat_signal_fallback_single_candidate():
    audio = np.full(500, 0.3)
    audio[250] = 0.31
    res = detect(audio, None, 500, DetectConfig(sensitivity=0.0))
    assert len(res.candidates) == 1
    assert res.used_fallback


def test_overlap_merge_and_max_duration():
    cfg = DetectConfig(pad_before_s=20, pad_after_s=15, max_clip_s=60)
    s = np.zeros(400)
    s[100], s[125], s[150] = 0.5, 1.0, 0.6
    cands = build_candidates(np.array([100, 125, 150]), s, 400, cfg)
    assert len(cands) == 1
    c = cands[0]
    assert c.peak_time == 125
    assert c.duration == 60
    assert c.start <= 125 <= c.end
    assert c.start == 105  # peak - pad_before


def test_candidate_clamped_to_video_bounds():
    cfg = DetectConfig()
    s = np.zeros(30)
    s[5] = 1.0
    c = build_candidates(np.array([5]), s, 30, cfg)[0]
    assert (c.start, c.end) == (0, 20)


def test_combine_weights_and_no_chat():
    cfg = DetectConfig(w_audio=0.6, w_chat=0.4)
    a, c = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    np.testing.assert_allclose(combine(a, c, cfg), [0.6, 0.4])
    np.testing.assert_allclose(combine(a, None, cfg), a)


def test_chat_contributes_peak():
    audio = _signal(900, {200: 0.5})
    chat = np.zeros(900)
    chat[597:604] = 1.0
    res = detect(audio, chat, 900, DetectConfig(w_audio=0.5, w_chat=0.5))
    assert {c.peak_time for c in res.candidates} >= {200, 600}


def test_sensitivity_monotonic():
    audio = _signal(3000, {t: h for t, h in zip(range(150, 3000, 150), np.linspace(0.2, 1.0, 19))})
    low = detect(audio, None, 3000, DetectConfig(sensitivity=0.0))
    high = detect(audio, None, 3000, DetectConfig(sensitivity=1.0))
    assert len(high.candidates) >= len(low.candidates)
