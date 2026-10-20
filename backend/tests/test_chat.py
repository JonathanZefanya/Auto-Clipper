import json

import numpy as np

from app.config import DetectConfig
from app.pipeline.chat import chat_scores, parse_chat


def _line(ms: int, n: int = 1, renderer: str = "liveChatTextMessageRenderer") -> str:
    actions = [{"addChatItemAction": {"item": {renderer: {"message": {"runs": [{"text": "w"}]}}}}}] * n
    return json.dumps({"replayChatItemAction": {"actions": actions, "videoOffsetTimeMsec": str(ms)}})


def test_parse_chat(tmp_path):
    lines = [
        _line(-5000),                                   # sebelum stream, dibuang
        _line(1500),
        _line(2500, n=2),
        _line(3000, renderer="liveChatPaidMessageRenderer"),
        _line(4000, renderer="liveChatViewerEngagementMessageRenderer"),  # bukan pesan
        "{rusak",
        "",
    ]
    path = tmp_path / "chat.json"
    path.write_text("\n".join(lines), encoding="utf-8")
    np.testing.assert_allclose(parse_chat(path), [1.5, 2.5, 2.5, 3.0])


def test_chat_delay_shifts_peak_earlier():
    duration = 300
    offsets = np.repeat(np.arange(150, 153, dtype=float), 50)  # ledakan chat di detik 150-152
    no_delay = chat_scores(offsets, duration, DetectConfig(chat_delay_s=0))
    delayed = chat_scores(offsets, duration, DetectConfig(chat_delay_s=7))
    assert delayed.size == duration
    assert int(np.argmax(no_delay)) - int(np.argmax(delayed)) == 7
    assert delayed.max() > 0
    assert delayed.min() >= 0


def test_chat_empty_duration():
    assert chat_scores(np.array([1.0]), 0, DetectConfig()).size == 0
