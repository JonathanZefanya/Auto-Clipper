"""F-04: analisis aktivitas live chat dari chat.json (JSONL keluaran yt-dlp)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from app.config import DetectConfig
from app.pipeline.signals import relative_z

MESSAGE_RENDERERS = (
    "liveChatTextMessageRenderer",
    "liveChatPaidMessageRenderer",
    "liveChatPaidStickerRenderer",
    "liveChatMembershipItemRenderer",
)


def _offset_ms(entry: dict[str, Any]) -> float | None:
    replay = entry.get("replayChatItemAction") or {}
    raw = replay.get("videoOffsetTimeMsec", entry.get("videoOffsetTimeMsec"))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _count_messages(entry: dict[str, Any]) -> int:
    actions = (entry.get("replayChatItemAction") or {}).get("actions") or []
    n = 0
    for action in actions:
        item = (action.get("addChatItemAction") or {}).get("item") or {}
        if any(r in item for r in MESSAGE_RENDERERS):
            n += 1
    return n


def iter_message_offsets(path: Path) -> Iterator[float]:
    """Yield offset (detik) tiap pesan; dibaca baris per baris, baris rusak dilewati."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ms = _offset_ms(entry)
            if ms is None or ms < 0:  # pesan sebelum stream dimulai
                continue
            for _ in range(_count_messages(entry)):
                yield ms / 1000.0


def parse_chat(path: Path) -> np.ndarray:
    return np.fromiter(iter_message_offsets(path), dtype=np.float64)


def chat_scores(offsets: np.ndarray, duration_s: int, cfg: DetectConfig) -> np.ndarray:
    """chat_z: pesan/detik -> rolling sum window -> geser mundur chat_delay -> z relatif baseline."""
    if duration_s <= 0:
        return np.zeros(0)
    secs = offsets[(offsets >= 0) & (offsets < duration_s)].astype(np.int64)
    per_sec = np.bincount(secs, minlength=duration_s).astype(np.float64)[:duration_s]

    window = max(1, cfg.chat_window_s)
    rate = np.convolve(per_sec, np.ones(window), mode="same")[:duration_s]  # window berpusat di t

    delay = max(0, cfg.chat_delay_s)
    shifted = np.zeros_like(rate)
    if delay < duration_s:
        shifted[: duration_s - delay] = rate[delay:]
    return relative_z(shifted, cfg.chat_baseline_s)
