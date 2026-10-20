"""Regresi dari feedback pemakaian: outro jadi kandidat, subtitle menggantung."""
import numpy as np

from app.config import DetectConfig, SubtitleConfig
from app.pipeline import subdoc
from app.pipeline.detect import allowed_mask, detect, excluded_ranges
from app.pipeline.subtitle import Line, Word, group_words


def _signal(n, spikes, seed=0):
    x = np.random.default_rng(seed).uniform(0, 0.02, n)
    for t, h in spikes.items():
        x[t - 3:t + 4] = h
    return x


def test_outro_and_intro_not_candidates():
    # 692 dtk (seperti video pengguna): outro paling keras di detik 674, intro di detik 10
    audio = _signal(692, {10: 1.0, 300: 0.6, 674: 1.0})
    res = detect(audio, None, 692, DetectConfig())
    peaks = [c.peak_time for c in res.candidates]
    assert peaks == [300]
    assert res.excluded == [[0, 30], [647, 692]]


def test_outro_rising_into_boundary_is_not_a_fake_peak():
    audio = np.full(600, 0.01)
    audio[300:304] = 0.5
    audio[540:] = np.linspace(0.2, 1.0, 60)  # outro makin ramai sampai akhir
    res = detect(audio, None, 600, DetectConfig())
    assert all(c.peak_time < 540 for c in res.candidates)


def test_exclusion_disabled_for_short_videos_and_configurable():
    assert allowed_mask(100, DetectConfig()).all()          # 30 + 45 ≥ separuh 100 dtk
    m = allowed_mask(600, DetectConfig(exclude_start_s=0, exclude_end_s=60))
    assert m[:540].all() and not m[540:].any()
    assert excluded_ranges(m) == [[540, 600]]
    assert allowed_mask(600, DetectConfig(exclude_start_s=0, exclude_end_s=0)).all()


def test_fallback_stays_out_of_outro():
    audio = 0.3 + 0.01 * np.sin(np.arange(600) / 5)
    audio[585:592] = 1.0  # outro sangat keras tidak boleh dipilih walau fallback
    res = detect(audio, None, 600, DetectConfig(sensitivity=0.0))
    assert res.used_fallback and res.candidates[0].peak_time < 555


def test_long_last_word_is_capped():
    # kasus nyata: "BABAK 3 SELESAI" 14.64 → 29.98 dtk
    words = [Word(14.64, 15.5, "BABAK"), Word(16.0, 16.8, "3"), Word(17.4, 29.98, "SELESAI")]
    lines = group_words(words, SubtitleConfig(uppercase=False))
    assert lines[-1].end <= 17.4 + SubtitleConfig().max_word_s + 1e-9


def test_stored_auto_subtitles_are_capped_but_edits_kept():
    scfg = SubtitleConfig()
    auto = subdoc.SubDoc(275, 310, [Line(14.64, 29.98, "BABAK 3 SELESAI")], edited=False)
    out = subdoc.display_lines(auto, 275, 310, scfg)
    assert out[0].end == round(14.64 + scfg.max_line_s + scfg.max_word_s, 3) or out[0].end < 19
    edited = subdoc.SubDoc(275, 310, [Line(14.64, 29.98, "SENGAJA LAMA")], edited=True)
    assert subdoc.display_lines(edited, 275, 310, scfg)[0].end == 29.98
