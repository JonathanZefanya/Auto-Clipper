"""F-19: saran judul via Ollama — parsing, prompt, klien HTTP (server palsu), API."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import runner
from app.config import SubtitleConfig, TitleConfig, load_config, save_settings
from app.pipeline import subdoc
from app.pipeline.subtitle import Line
from app.pipeline.titles import (
    ClipContext, OllamaClient, TitleError, build_messages, clean_hashtag, clean_title,
    model_installed, parse_suggestion, suggest, transcript_text,
)

CFG = TitleConfig()


# ---------------------------------------------------------------- parsing

def test_parse_suggestion_cleans_and_limits():
    content = json.dumps({
        "titles": ['"Gawat! Nun Hampir Menangkap Gue 😱"', "1. Gawat! nun hampir menangkap gue 😱",
                   "- " + "Sangat panjang " * 20, "Kabur Lewat Pintu Utama #EvilNun"],
        "description": "  Detik-detik menegangkan\nsaat kabur.  ",
        "hashtags": ["evil nun", "#Horor", "#horor", "", "#Game-Indonesia"],
    })
    s = parse_suggestion(content, CFG, "qwen2.5:7b")
    assert s.titles[0] == "Gawat! Nun Hampir Menangkap Gue 😱"
    assert len(s.titles) == 3                                  # duplikat (beda kapital) dibuang
    assert all(len(t) <= CFG.max_title_chars + 1 for t in s.titles) and s.titles[1].endswith("…")
    assert s.titles[2] == "Kabur Lewat Pintu Utama"            # hashtag nyasar di judul dibuang
    assert s.description == "Detik-detik menegangkan saat kabur."
    assert s.hashtags == ["#evilnun", "#Horor", "#GameIndonesia"]
    assert s.model == "qwen2.5:7b"


def test_parse_suggestion_json_wrapped_in_text_and_errors():
    s = parse_suggestion('Berikut hasilnya:\n{"titles": ["Judul A"], "description": "", "hashtags": []}', CFG)
    assert s.titles == ["Judul A"]
    for bad in ("bukan json", "[1, 2]", '{"titles": []}', '{"titles": ["  "]}'):
        with pytest.raises(TitleError):
            parse_suggestion(bad, CFG)


def test_clean_helpers():
    assert clean_title("“Wah Gila!”", 80) == "Wah Gila!"
    assert clean_hashtag("# hal lo") == "#hallo" and clean_hashtag("###") is None
    assert model_installed("qwen2.5:7b", ["qwen2.5:7b"]) and model_installed("llama3", ["llama3:latest"])
    assert not model_installed("qwen2.5:7b", ["qwen2.5:3b"])


def test_prompt_contains_context_and_limits():
    ctx = ClipContext("aduh gimana ya teman-teman", "Evil Nun Extreme", "MiawAug", "GOCEK NUN", 35)
    msgs = build_messages(ctx, CFG)
    assert msgs[0]["role"] == "system" and "JUJUR" in msgs[0]["content"] and "80 karakter" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "Evil Nun Extreme" in user and "MiawAug" in user and "GOCEK NUN" in user and "aduh gimana" in user
    assert transcript_text(["satu  dua", "", "tiga"], 100) == "satu dua tiga"
    assert transcript_text(["kata " * 50], 20).endswith("…")


# ---------------------------------------------------------------- klien HTTP (server Ollama palsu)

class FakeOllama(BaseHTTPRequestHandler):
    requests: list = []

    def log_message(self, *a):  # senyap
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"models": [{"name": "qwen2.5:7b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(body)
        if body["model"] != "qwen2.5:7b":
            return self._send(404, {"error": f"model '{body['model']}' not found"})
        content = json.dumps({"titles": ["Nun Hampir Nangkep Gue!", "Kabur Detik Terakhir"],
                              "description": "Kabur dari Nun.", "hashtags": ["evilnun", "horor"]})
        self._send(200, {"message": {"role": "assistant", "content": content}})


@pytest.fixture
def ollama_url():
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    FakeOllama.requests = []
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_client_chat_sends_schema_and_unloads(ollama_url):
    cfg = TitleConfig(ollama_url=ollama_url)
    s = suggest(ClipContext("aduh gawat"), cfg)
    assert s.titles == ["Nun Hampir Nangkep Gue!", "Kabur Detik Terakhir"] and s.hashtags == ["#evilnun", "#horor"]
    req = FakeOllama.requests[-1]
    assert req["stream"] is False and req["keep_alive"] == "0"
    assert req["format"]["required"] == ["titles", "description", "hashtags"]
    assert OllamaClient(ollama_url, 3).models() == ["qwen2.5:7b"]


def test_client_errors_are_actionable(ollama_url):
    with pytest.raises(TitleError, match="ollama pull llama9"):
        suggest(ClipContext("x"), TitleConfig(ollama_url=ollama_url, model="llama9", fallback_heuristic=False))
    with pytest.raises(TitleError, match="tidak jalan"):
        suggest(ClipContext("x"), TitleConfig(ollama_url="http://127.0.0.1:9", timeout_s=5, fallback_heuristic=False))
    with pytest.raises(TitleError, match="kosong"):
        suggest(ClipContext("   "), TitleConfig(ollama_url=ollama_url))
    with pytest.raises(TitleError, match="dimatikan"):
        suggest(ClipContext("x"), TitleConfig(enabled=False))


REAL_CTX = ClipContext(  # transkrip nyata klip 4:35–5:10 (Evil Nun, MiawAug)
    transcript="Aduh, gimana ya, teman-teman? Ini tricky banget masalahnya. Cookie box-nya akan ada suaranya "
               "pas kita buka, apa namanya? Nail-nya. Hampir aja gue ketahuan. Ya ampun, bad timing banget. "
               "Gawat, gawat, gawat, gawat. Tutup lagi boleh nggak? Nggak usah, jangan dulu ditutup.",
    source_title="Pro Player Di Extreme Mode - Evil Nun The Broken Mask Indonesia (Main Door Ending)",
    channel="MiawAug", thumb_text="GOCEK NUN", duration_s=35,
)


def test_fallback_heuristic_when_ollama_missing():
    """Ollama belum terpasang (port tertutup) → tetap dapat saran, ditandai tanpa LLM."""
    cfg = TitleConfig(ollama_url="http://127.0.0.1:9", timeout_s=5)
    s = suggest(REAL_CTX, cfg)
    assert s.model == "heuristik (tanpa LLM)" and "tidak jalan" in s.note and "Ollama" in s.note
    # teks thumbnail, lalu kalimat reaksi pendek (pengulangan dipadatkan), bukan kalimat panjang
    assert s.titles == ["Gocek Nun", "Gawat, gawat!", "Hampir aja gue ketahuan."]
    assert s.hashtags[0] == "#MiawAug" and "#Shorts" in s.hashtags and "#Extreme" in s.hashtags
    assert "#Mode" not in s.hashtags and "#Player" not in s.hashtags
    assert s.description.startswith("Aduh, gimana ya, teman-teman?")


def test_fallback_model_missing_and_disabled(ollama_url):
    s = suggest(REAL_CTX, TitleConfig(ollama_url=ollama_url, model="belum-ada:1b"))
    assert s.model == "heuristik (tanpa LLM)" and "ollama pull belum-ada:1b" in s.note
    with pytest.raises(TitleError, match="terlalu pendek"):
        suggest(ClipContext("ya"), TitleConfig(ollama_url="http://127.0.0.1:9", timeout_s=5))


# ---------------------------------------------------------------- runner & config

class FakeClient:
    def __init__(self):
        self.messages = None

    def chat(self, model, messages, schema, temperature, keep_alive):
        self.messages = messages
        return json.dumps({"titles": ["Judul Uji"], "description": "D", "hashtags": ["#a"]})


def test_suggest_clip_titles_uses_subtitle_doc(tmp_path):
    credit = runner.Credit("Video Sumber", "https://www.youtube.com/watch?v=abc", "Chan")
    spec = runner.ClipSpec(1, 100, 135, 120, thumb_text="WAH")
    with pytest.raises(TitleError, match="belum ditranskripsi"):
        runner.suggest_clip_titles(tmp_path, spec, credit, SubtitleConfig(), CFG, FakeClient())
    subdoc.save_doc(tmp_path, 1, subdoc.SubDoc(100, 135, [Line(1, 2, "ADUH GIMANA"), Line(3, 4, "GAWAT")], edited=True))
    fc = FakeClient()
    s = runner.suggest_clip_titles(tmp_path, spec, credit, SubtitleConfig(), CFG, fc)
    assert s.titles == ["Judul Uji"]
    assert "ADUH GIMANA GAWAT" in fc.messages[1]["content"] and "Video Sumber" in fc.messages[1]["content"]


def test_credit_text_includes_title_block():
    credit = runner.Credit("Sumber", "https://www.youtube.com/watch?v=abc", "Chan")
    txt = runner.credit_text(credit, 65, 100, "Judul Klip", "Deskripsi.", ["#a", "#b"])
    assert txt.startswith("Judul klip   : Judul Klip\nDeskripsi    : Deskripsi.\nHashtag      : #a #b\n\n")
    assert "Link sumber  : https://www.youtube.com/watch?v=abc&t=65s" in txt
    assert runner.credit_text(credit, 65, 100).startswith("Judul sumber")


@pytest.mark.parametrize("updates", [
    {"title": {"ollama_url": "http://192.168.1.5:11434"}},
    {"title": {"ollama_url": "https://evil.example.com"}},
    {"title": {"model": "bad model; rm"}},
    {"title": {"count": 0}},
])
def test_title_settings_validated(tmp_path, updates):
    with pytest.raises(ValueError):
        save_settings(load_config(tmp_path), updates)


def test_title_settings_accept_local(tmp_path):
    cfg = save_settings(load_config(tmp_path), {"title": {"ollama_url": "http://localhost:11500", "model": "gemma3:4b"}})
    assert cfg.title.model == "gemma3:4b"


# ---------------------------------------------------------------- API

def test_api_titles_flow(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from tests.test_api import URL, fake_detect, fake_render, fake_transcribe

    from app.main import create_app
    from app.pipeline import titles as titles_mod

    app = create_app(tmp_path, detect_fn=fake_detect, render_fn=fake_render, transcribe_fn=fake_transcribe,
                     sse_poll_s=0.02)
    with TestClient(app) as client:
        job_id = client.post("/api/jobs", json={"url": URL}).json()["id"]
        assert app.state.worker.join_idle(10)
        cid = client.get(f"/api/jobs/{job_id}").json()["candidates"][0]["id"]

        r = client.post(f"/api/candidates/{cid}/titles")
        assert r.status_code == 409 and "belum ditranskripsi" in r.json()["detail"]

        client.patch(f"/api/candidates/{cid}", json={"selected": True})
        client.post(f"/api/jobs/{job_id}/transcribe")
        assert app.state.worker.join_idle(10)
        monkeypatch.setattr(titles_mod, "OllamaClient", lambda *a, **k: FakeClient())
        r = client.post(f"/api/candidates/{cid}/titles")
        assert r.status_code == 200, r.text
        assert r.json()["suggestions"]["titles"] == ["Judul Uji"] and r.json()["title"] is None

        # render → clip_01.txt; memilih judul memperbarui txt tanpa render ulang
        client.post(f"/api/jobs/{job_id}/render", json={})
        assert app.state.worker.join_idle(10)
        r = client.patch(f"/api/candidates/{cid}", json={"title": "  Judul   Pilihan  "})
        assert r.json()["title"] == "Judul Pilihan"
        txt = (tmp_path / "jobs" / job_id / "clips" / "clip_01.txt").read_text(encoding="utf-8")
        assert "Judul klip   : Judul Pilihan" in txt and "Hashtag      : #a" in txt

        st = client.get("/api/llm/status").json()
        assert st["model"] == "qwen2.5:7b" and "available" in st
