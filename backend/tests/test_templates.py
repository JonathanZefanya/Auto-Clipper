import pytest

from app.config import RenderConfig
from app.pipeline.render import build_layout, encoder_args
from app.templates import (
    DEFAULT_TEMPLATES, Box, Template, ensure_default_templates, list_templates, load_template,
)


def test_default_templates_roundtrip(tmp_path):
    ensure_default_templates(tmp_path)
    assert set(list_templates(tmp_path)) == {t.name for t in DEFAULT_TEMPLATES}
    for t in DEFAULT_TEMPLATES:
        assert load_template(tmp_path, t.name) == t


def test_missing_template_lists_available(tmp_path):
    ensure_default_templates(tmp_path)
    with pytest.raises(ValueError, match="center"):
        load_template(tmp_path, "tidak-ada")


@pytest.mark.parametrize("bad", [
    dict(name="x", layout_type="split"),                                   # split tanpa facecam
    dict(name="x", layout_type="center_crop", gameplay_box=Box(0.5, 0, 0.6, 1)),  # keluar frame
    dict(name="a b", layout_type="center_crop"),                           # nama tidak valid
    dict(name="x", layout_type="grid"),
])
def test_invalid_templates(bad):
    with pytest.raises(ValueError):
        Template(**bad).validate()


def test_split_layout_dimensions():
    cfg = RenderConfig()
    t = Template("s", "split", facecam_box=Box(0.7, 0.6, 0.3, 0.4), top_ratio=0.4)
    lay = build_layout(t, cfg, "clip_01.ass")
    assert lay.gameplay_top == 768 and lay.gameplay_height == 1152
    assert "vstack=inputs=2" in lay.filtergraph
    assert "scale=1080:768" in lay.filtergraph and "scale=1080:1152" in lay.filtergraph
    assert lay.filtergraph.endswith("ass=clip_01.ass[v]")


def test_center_layout():
    lay = build_layout(Template("c", "center_crop"), RenderConfig())
    assert (lay.gameplay_top, lay.gameplay_height) == (0, 1920)
    assert "crop=1080:1920" in lay.filtergraph and "ass=" not in lay.filtergraph


def test_encoder_args():
    cfg = RenderConfig()
    assert "h264_nvenc" in encoder_args("h264_nvenc", cfg)
    assert "libx264" in encoder_args("libx264", cfg)
