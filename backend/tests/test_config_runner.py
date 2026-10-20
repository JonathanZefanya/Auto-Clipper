import json

import pytest

from app.config import load_config, save_settings
from app.runner import Credit, credit_text


def test_save_settings_partial_and_data_dir(tmp_path):
    cfg = load_config(tmp_path)
    new = save_settings(cfg, {"detect": {"pad_before_s": 25}, "thumbnail": {"landscape": True},
                              "data_dir": str(tmp_path / "lain")})
    assert new.detect.pad_before_s == 25 and new.thumbnail.landscape is True
    raw = json.loads((tmp_path / "config.json").read_text())
    assert raw["data_dir"] == str(tmp_path / "lain")
    # data_dir eksplisit (argumen) tetap menang atas config.json
    assert load_config(tmp_path).data_dir == tmp_path


@pytest.mark.parametrize("updates", [
    {"detect": {"max_clip_s": 90}},
    {"detect": {"w_audio": 0, "w_chat": 0, "w_reaction": 0}},
    {"detect": {"w_reaction": -1}},
    {"detect": {"download_max_height": 999}},
    {"subtitle": {"device": "tpu"}},
    {"render": {"video_encoder": "x"}},
    {"render": {"width": True}},
    {"unknown": {}},
])
def test_save_settings_rejects_invalid(tmp_path, updates):
    with pytest.raises(ValueError):
        save_settings(load_config(tmp_path), updates)
    assert not (tmp_path / "config.json").exists()


def test_credit_text():
    txt = credit_text(Credit("Judul", "https://www.youtube.com/watch?v=abc", "Chan"), 3725.4, 3760)
    assert "Link sumber  : https://www.youtube.com/watch?v=abc&t=3725s" in txt
    assert "Rentang      : 1:02:05 - 1:02:40" in txt and "Chan" in txt
