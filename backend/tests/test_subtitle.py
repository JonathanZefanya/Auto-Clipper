from app.config import SubtitleConfig
from app.pipeline.subtitle import Word, _ass_time, build_ass, clamp_words, group_words


def _words(spec):
    """spec: list of (start, text) dengan durasi kata 0.3 dtk."""
    return [Word(s, s + 0.3, t) for s, t in spec]


def test_group_two_to_four_words():
    cfg = SubtitleConfig(uppercase=False)
    words = _words([(i * 0.35, f"w{i}") for i in range(10)])
    lines = group_words(words, cfg)
    sizes = [len(ln.text.split()) for ln in lines]
    assert all(2 <= n <= 4 for n in sizes)
    assert sum(sizes) == 10


def test_long_gap_breaks_line():
    cfg = SubtitleConfig(uppercase=False)
    words = _words([(0.0, "halo"), (0.35, "semua"), (3.0, "wah"), (3.35, "gila")])
    lines = group_words(words, cfg)
    assert [ln.text for ln in lines] == ["halo semua", "wah gila"]


def test_sentence_end_breaks_and_uppercase():
    cfg = SubtitleConfig()
    words = _words([(0.0, "ayo"), (0.35, "main!"), (0.7, "sekarang"), (1.05, "juga")])
    assert [ln.text for ln in group_words(words, cfg)] == ["AYO MAIN!", "SEKARANG JUGA"]


def test_single_word_merged_into_previous():
    cfg = SubtitleConfig(uppercase=False)
    words = _words([(0.0, "a"), (0.35, "b"), (0.7, "c."), (1.05, "d")])
    lines = group_words(words, cfg)
    assert [ln.text for ln in lines] == ["a b c. d"]


def test_lines_held_until_next():
    cfg = SubtitleConfig(uppercase=False, hold_gap_s=0.3)
    words = _words([(0.0, "a"), (0.35, "b"), (0.7, "c"), (1.05, "d"), (1.6, "e"), (1.95, "f")])
    lines = group_words(words, cfg)
    assert lines[0].end == lines[1].start


def test_empty_words():
    assert group_words([], SubtitleConfig()) == []


def test_clamp_words():
    words = [Word(-0.5, 0.2, "a"), Word(10.0, 10.5, "b"), Word(59.8, 60.4, "c")]
    out = clamp_words(words, 60.0)
    assert [(w.start, w.end) for w in out] == [(0.0, 0.2), (10.0, 10.5), (59.8, 60.0)]


def test_ass_time():
    assert _ass_time(0) == "0:00:00.00"
    assert _ass_time(61.256) == "0:01:01.26"


def test_build_ass_position_and_escape():
    cfg = SubtitleConfig(position_in_gameplay=0.75)
    from app.pipeline.subtitle import Line

    ass = build_ass([Line(0, 1, "A {B}")], cfg, 1080, 1920, gameplay_top=768, gameplay_height=1152)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    # baseline = 768 + 1152*0.75 = 1632 -> MarginV = 288
    assert ",2,60,60,288,1" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Shorts" in ass
    assert "A (B)" in ass
