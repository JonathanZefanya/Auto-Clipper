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
    """Kesalahan yang pesannya langsung ditampilkan ke pengguna (Bahasa Indonesia).

    `unavailable=True` → LLM tidak bisa dipakai sama sekali (Ollama tidak jalan / model belum
    diunduh / tidak menjawab) sehingga boleh jatuh ke saran heuristik.
    """

    def __init__(self, message: str, unavailable: bool = False) -> None:
        super().__init__(message)
        self.unavailable = unavailable


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
    note: str = ""          # mis. alasan memakai saran heuristik tanpa LLM

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
                model = body.get("model", "") if body else ""
                raise TitleError(f"Model belum diunduh. Jalankan: ollama pull {model}".strip(), unavailable=True) from e
            raise TitleError(f"Ollama error {e.code}: {detail or e.reason}") from e
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if isinstance(e, TimeoutError) or "timed out" in str(e):
                raise TitleError(f"Ollama tidak menjawab dalam {self.timeout:g} detik.", unavailable=True) from e
            raise TitleError(
                f"Ollama tidak jalan di {self.base}. Pasang/buka Ollama atau jalankan `ollama serve`.",
                unavailable=True,
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


HEURISTIC_MODEL = "heuristik (tanpa LLM)"
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_STOP = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk", "dengan", "the", "and", "indonesia",
    # kata generik judul video yang tidak berguna sebagai hashtag
    "mode", "player", "part", "episode", "full", "video", "live", "stream", "ending", "main",
}


# kata reaksi khas streamer Indonesia → kalimat yang memuatnya lebih "klip-able"
_REACTION_WORDS = {
    "aduh", "waduh", "gawat", "gila", "anjir", "anjay", "astaga", "ampun", "hampir", "ketahuan",
    "kaget", "takut", "serem", "seram", "kabur", "lari", "mati", "wah", "wih", "hah", "loh", "lho",
    "parah", "mampus", "tolong", "awas", "akhirnya", "berhasil", "menang", "kalah", "bahaya",
}


def _squash_repeats(s: str) -> str:
    """'Gawat, gawat, gawat, gawat' → 'Gawat, gawat!' (pengulangan ≥3 kata yang sama)."""
    def repl(m: re.Match) -> str:
        w = m.group(1)
        return f"{w}, {w.lower()}!"
    return re.sub(r"\b(\w+)(?:[,\s]+\1\b){2,}[.!,]?", repl, s, flags=re.IGNORECASE)


def _sentence_case(s: str) -> str:
    s = s.strip()
    if s.isupper():
        # "GOCEK NUN" → "Gocek Nun" (frasa pendek), kalimat panjang → huruf kecil biasa
        return s.title() if len(s.split()) <= 5 else s[:1] + s[1:].lower()
    return s[:1].upper() + s[1:]


def heuristic_suggest(ctx: ClipContext, cfg: TitleConfig, reason: str = "") -> TitleSuggestion:
    """Saran sederhana tanpa LLM (Ollama belum ada): teks thumbnail + kalimat paling ekspresif di
    transkrip (seru '!' / tanya '?', panjang 3–12 kata) + konteks judul sumber. Tidak mengarang isi."""
    sentences = [_squash_repeats(s.strip(" ,;:")) for s in _SENT_SPLIT.split(ctx.transcript) if s.strip()]

    def score(s: str) -> float:
        words = re.findall(r"[\w-]+", s.lower())
        n = len(words)
        if n < 2 or n > 14:
            return -1.0
        emotion = min(2, sum(1 for w in words if w in _REACTION_WORDS))
        length = 1.0 if 3 <= n <= 7 else 0.4 if n <= 10 else 0.1   # judul Shorts: pendek & padat
        return 2.0 * ("!" in s) + 0.5 * ("?" in s) + 1.5 * emotion + length

    ranked = [s for s in sorted(sentences, key=score, reverse=True) if score(s) > 0]
    source_short = re.split(r"\s[-|–:]\s", ctx.source_title)[0].strip() if ctx.source_title else ""

    raw: list[str] = []
    if ctx.thumb_text:
        raw.append(_sentence_case(ctx.thumb_text))
    raw += [_sentence_case(s) for s in ranked[: cfg.count]]
    if ranked and source_short:
        raw.append(f"{_sentence_case(ranked[0]).rstrip('.')} | {source_short}")
    if not raw:
        raise TitleError("Transkrip klip terlalu pendek untuk dibuatkan judul.")

    titles: list[str] = []
    for t in raw:
        ct = clean_title(t, cfg.max_title_chars)
        if ct and ct.lower() not in {x.lower() for x in titles}:
            titles.append(ct)

    tags: list[str] = []
    for cand in [ctx.channel, *[w for w in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", source_short)
                                 if w.lower() not in _STOP][:3], "Shorts"]:
        h = clean_hashtag(cand) if cand else None
        if h and h.lower() not in {x.lower() for x in tags}:
            tags.append(h)
    desc = " ".join(sentences[:2])[:200]
    note = (reason + " " if reason else "") + "Saran sederhana tanpa LLM — pasang Ollama untuk hasil lebih baik."
    return TitleSuggestion(titles[: cfg.count], desc, tags[: cfg.hashtags], HEURISTIC_MODEL, note.strip())


def suggest(ctx: ClipContext, cfg: TitleConfig, client: OllamaClient | None = None) -> TitleSuggestion:
    if not cfg.enabled:
        raise TitleError("Saran judul dimatikan di Pengaturan.")
    if not ctx.transcript.strip() and not ctx.thumb_text.strip():
        raise TitleError("Transkrip klip kosong — tidak ada ucapan untuk dijadikan judul.")
    client = client or OllamaClient(cfg.ollama_url, cfg.timeout_s)
    try:
        content = client.chat(cfg.model, build_messages(ctx, cfg), response_schema(cfg), cfg.temperature, cfg.keep_alive)
    except TitleError as e:
        # Ollama belum terpasang/jalan atau model belum diunduh → tetap beri saran (heuristik)
        if e.unavailable and cfg.fallback_heuristic:
            return heuristic_suggest(ctx, cfg, reason=str(e))
        raise
    return parse_suggestion(content, cfg, cfg.model)
