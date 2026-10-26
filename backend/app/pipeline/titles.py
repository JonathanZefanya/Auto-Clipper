"""F-19: saran judul klip (+ deskripsi & hashtag) dengan LLM lokal via Ollama.

Hanya standard library (urllib). Output dipaksa JSON lewat `format` (JSON schema) Ollama, lalu
dirapikan di `parse_suggestion` karena model kecil tetap bisa melanggar batas panjang/format.
Model di-unload segera (`keep_alive`) agar VRAM bebas untuk Whisper/NVENC.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from app.config import TitleConfig


class TitleError(RuntimeError):
    """Kesalahan yang pesannya langsung ditampilkan ke pengguna (Bahasa Indonesia)."""


@dataclass
class ClipContext:
    transcript: str
    source_title: str = ""
    channel: str = ""
    thumb_text: str = ""
    duration_s: float = 0.0


@dataclass
class TitleSuggestion:
    titles: list[str]
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- prompt

def transcript_text(lines: Sequence[str], max_chars: int) -> str:
    """Gabung baris subtitle jadi kalimat; dipotong agar prompt tetap kecil."""
    text = re.sub(r"\s+", " ", " ".join(s.strip() for s in lines if s.strip())).strip()
    return text if len(text) <= max_chars else text[:max_chars].rsplit(" ", 1)[0] + " …"


def response_schema(cfg: TitleConfig) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "titles": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": cfg.count},
            "description": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}, "maxItems": cfg.hashtags},
        },
        "required": ["titles", "description", "hashtags"],
    }


def build_messages(ctx: ClipContext, cfg: TitleConfig) -> list[dict[str, str]]:
    system = (
        "Kamu penulis judul YouTube Shorts berbahasa Indonesia untuk klip streamer/gaming. "
        f"Buat {cfg.count} opsi judul yang menarik dan memancing rasa penasaran, tapi JUJUR: hanya "
        "berdasarkan isi transkrip, jangan mengarang kejadian atau nama. "
        f"Setiap judul maksimal {cfg.max_title_chars} karakter, bahasa santai ala Shorts, boleh 1 emoji, "
        "tanpa tanda kutip, tanpa hashtag di judul. "
        "Tambahkan 1 deskripsi singkat (1–2 kalimat) dan "
        f"{cfg.hashtags} hashtag relevan (tanpa spasi). Balas hanya JSON sesuai skema."
    )
    parts = [
        f"Judul video sumber: {ctx.source_title or '-'}",
        f"Channel: {ctx.channel or '-'}",
    ]
    if ctx.thumb_text:
        parts.append(f"Teks thumbnail: {ctx.thumb_text}")
    if ctx.duration_s:
        parts.append(f"Durasi klip: {round(ctx.duration_s)} detik")
    parts.append(f"Transkrip klip:\n{ctx.transcript}")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(parts)}]


# ---------------------------------------------------------------- parsing & sanitasi

_QUOTES = "\"'“”‘’«»`"


def clean_title(t: str, max_chars: int) -> str:
    t = re.sub(r"\s+", " ", str(t)).strip().strip(_QUOTES).strip()
    t = re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", t)          # "1. Judul" / "- Judul"
    t = re.sub(r"(\s#[\w]+)+\s*$", "", t).strip()          # hashtag yang nyasar di akhir judul
    if len(t) > max_chars:
        t = t[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:-–") + "…"
    return t


def clean_hashtag(h: str) -> str | None:
    tag = re.sub(r"[^\w]", "", str(h).strip().lstrip("#"), flags=re.UNICODE)
    return f"#{tag}" if tag else None


def parse_suggestion(content: str, cfg: TitleConfig, model: str = "") -> TitleSuggestion:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)  # model kadang membungkus JSON dengan teks
        if not m:
            raise TitleError("Jawaban model bukan JSON yang valid — coba lagi.")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise TitleError("Jawaban model bukan JSON yang valid — coba lagi.") from e
    if not isinstance(data, dict):
        raise TitleError("Format jawaban model tidak dikenal — coba lagi.")

    raw_titles = data.get("titles") or []
    if isinstance(raw_titles, str):
        raw_titles = [raw_titles]
    titles: list[str] = []
    seen: set[str] = set()
    for t in raw_titles:
        ct = clean_title(t, cfg.max_title_chars)
        if ct and ct.lower() not in seen:
            seen.add(ct.lower())
            titles.append(ct)
    if not titles:
        raise TitleError("Model tidak menghasilkan judul — coba lagi.")

    tags: list[str] = []
    for h in data.get("hashtags") or []:
        ch = clean_hashtag(h)
        if ch and ch.lower() not in {x.lower() for x in tags}:
            tags.append(ch)
    desc = re.sub(r"\s+", " ", str(data.get("description") or "")).strip()[:300]
    return TitleSuggestion(titles[: cfg.count], desc, tags[: cfg.hashtags], model)


# ---------------------------------------------------------------- klien Ollama

class OllamaClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout_s

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (URL divalidasi localhost)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", "")
            except (ValueError, OSError):
                pass
            if e.code == 404 and "not found" in detail:
                raise TitleError(f"Model belum diunduh. Jalankan: ollama pull {body.get('model') if body else ''}".strip()) from e
            raise TitleError(f"Ollama error {e.code}: {detail or e.reason}") from e
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if isinstance(e, TimeoutError) or "timed out" in str(e):
                raise TitleError(f"Ollama tidak menjawab dalam {self.timeout:g} detik.") from e
            raise TitleError(
                f"Ollama tidak jalan di {self.base}. Buka aplikasi Ollama atau jalankan `ollama serve`."
            ) from e

    def models(self) -> list[str]:
        return [m.get("name", "") for m in self._request("GET", "/api/tags").get("models", [])]

    def chat(self, model: str, messages: list[dict], schema: dict, temperature: float, keep_alive: str) -> str:
        res = self._request("POST", "/api/chat", {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {"temperature": temperature},
            "keep_alive": keep_alive,
        })
        return str((res.get("message") or {}).get("content", ""))


def model_installed(model: str, installed: Sequence[str]) -> bool:
    """`qwen2.5:7b` cocok dengan `qwen2.5:7b`; nama tanpa tag cocok dengan `:latest`."""
    want = model if ":" in model else f"{model}:latest"
    return want in installed or model in installed


def suggest(ctx: ClipContext, cfg: TitleConfig, client: OllamaClient | None = None) -> TitleSuggestion:
    if not cfg.enabled:
        raise TitleError("Saran judul dimatikan di Pengaturan.")
    if not ctx.transcript.strip():
        raise TitleError("Transkrip klip kosong — tidak ada ucapan untuk dijadikan judul.")
    client = client or OllamaClient(cfg.ollama_url, cfg.timeout_s)
    content = client.chat(cfg.model, build_messages(ctx, cfg), response_schema(cfg), cfg.temperature, cfg.keep_alive)
    return parse_suggestion(content, cfg, cfg.model)
