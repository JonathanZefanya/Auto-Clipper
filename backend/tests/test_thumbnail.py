import numpy as np
import pytest

from app.config import RenderConfig, ThumbnailConfig
from app.pipeline.render import Layout, build_command, with_intro
from app.pipeline.subtitle import Word
from app.pipeline.thumbnail import (
    Face, FrameScore, compose, default_text, fit_text, find_font, frame_times,
    laplacian_variance, pick_best, score_frame, text_center_y, wrap_text,
)


def test_frame_times_around_peak_within_clip():
    cfg = ThumbnailConfig(n_frames=5, window_before_s=3, window_after_s=2)
    ts = frame_times(peak=100, start=80, end=115, cfg=cfg)
    assert len(ts) == 5 and ts[0] == 97 and ts[-1] == 102
    ts = frame_times(peak=81, start=80, end=82, cfg=cfg)  # terpotong batas klip
    assert min(ts) >= 80 and max(ts) < 82


def test_laplacian_sharp_vs_flat():
    flat = np.full((50, 50, 3), 128, dtype=np.uint8)
    checker = (np.indices((50, 50)).sum(axis=0) % 2 * 255).astype(np.uint8)
    sharp = np.stack([checker] * 3, axis=-1)
    assert laplacian_variance(flat) == 0
    assert laplacian_variance(sharp) > 1000


def test_face_frame_beats_sharper_faceless_frame():
    cfg = ThumbnailConfig()
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (200, 100, 3), dtype=np.uint8)
    no_face = score_frame(img, [], 1.0, cfg)
    small = score_frame(img, [Face(10, 10, 20, 20, 0.9)], 2.0, cfg)
    big = score_frame(img, [Face(10, 120, 60, 60, 0.9)], 3.0, cfg)
    assert not no_face.has_face and big.has_face
    assert pick_best([no_face, small, big]).time == 3.0
    assert big.face_center_y == pytest.approx(150 / 200)


def test_pick_best_without_faces_uses_sharpness():
    scores = [FrameScore(1, False, 10, None), FrameScore(2, False, 50, None)]
    assert pick_best(scores).time == 2


def test_default_text_near_peak():
    cfg = ThumbnailConfig(text_max_words=3, text_window_s=2)
    words = [Word(i, i + 0.4, f"w{i}") for i in range(20)]
    assert default_text(words, peak_rel=10, cfg=cfg) == "w9 w10 w11"
    assert default_text([], 5, cfg) == cfg.fallback_text
    assert default_text([Word(0, 0.5, "mantap.")], 0, cfg) == "mantap"


def test_wrap_text():
    lines = wrap_text("aa bb cc dd", measure=lambda s: len(s) * 10, max_width=50)
    assert lines == ["aa bb", "cc dd"]


def test_text_position_avoids_face():
    cfg = ThumbnailConfig()
    assert text_center_y(0.2, cfg) == cfg.text_y_bottom
    assert text_center_y(0.8, cfg) == cfg.text_y_top
    assert text_center_y(None, cfg) == cfg.text_y_bottom


def test_fit_text_and_compose_size():
    cfg = ThumbnailConfig()
    font, lines, stroke = fit_text("WAH GILA INI SERU BANGET PARAH", 1080, cfg, find_font(cfg))
    assert 1 <= len(lines) <= cfg.max_lines and stroke >= 1
    img = compose(np.zeros((1920, 1080, 3), dtype=np.uint8), "wah gila", 0.3, cfg)
    assert img.size == (1080, 1920)
    assert np.asarray(img).max() > 0  # teks tergambar


def test_with_intro_graph_and_command(tmp_path):
    cfg = RenderConfig()
    g = with_intro("[0:v]scale=1080:1920[v]", cfg, 0.1)
    assert g.startswith("[0:v]scale=1080:1920[main];")
    assert "overlay=0:0:enable='lt(t,0.100)'" in g and g.endswith("[v]")
    cmd = build_command(tmp_path / "s.mp4", tmp_path / "o.mp4", 10, 30,
                        Layout("[0:v]null[v]", 0, 1920), "libx264", cfg,
                        intro_image=tmp_path / "t.png", intro_s=0.1)
    i = cmd.index("-loop")
    assert cmd[i:i + 2] == ["-loop", "1"] and str(tmp_path / "t.png") in cmd
    assert cmd.index(str(tmp_path / "s.mp4")) < i  # sumber tetap input #0
