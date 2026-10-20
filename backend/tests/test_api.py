"""Test API M4 dengan runner palsu (tanpa jaringan, FFmpeg, atau GPU)."""
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Job
from app.db import session
from app.pipeline.detect import Candidate as DetCandidate
from app.pipeline.download import DownloadError, VideoMeta
from app.runner import ClipResult, DetectOutput

VID = "dQw4w9WgXcQ"
URL = f"https://youtu.be/{VID}"


def fake_detect(url, job_dir: Path, cfg, report, force_download=False):
    report("downloading", 50, "mengunduh video")
    (job_dir / "source.mp4").write_bytes(b"0123456789" * 100)
    report("analyzing", 50, "analisis audio")
    (job_dir / "scores.json").write_text(json.dumps({
        "duration": 300, "has_chat": False, "threshold": 1.5, "used_fallback": False,
        "smoothed": [0.1] * 300, "audio": [0.1] * 300, "chat": None,
    }))
    cands = [
        DetCandidate(rank=1, peak_time=120, start=100, end=135, score=100),
        DetCandidate(rank=2, peak_time=200, start=180, end=215, score=80),
        DetCandidate(rank=3, peak_time=40, start=20, end=55, score=60),
    ]
    meta = VideoMeta(VID, url, "Judul Tes", "Channel Tes", 300.0, "http://thumb", "was_live", False)
    return DetectOutput(meta, False, cands, False, 1.5)


def fake_render(source, job_dir: Path, clips, template, rcfg, scfg, tcfg, models_dir, options,
                report=None, credit=None, log=None):
    (job_dir / "clips").mkdir(exist_ok=True)
    (job_dir / "thumbs").mkdir(exist_ok=True)
    out = []
    for c in clips:
        report("rendering", 50, f"render klip #{c.rank}")
        (job_dir / "clips" / f"clip_{c.rank:02d}.mp4").write_bytes(b"mp4")
        (job_dir / "clips" / f"clip_{c.rank:02d}.txt").write_text(credit.title if credit else "")
        (job_dir / "thumbs" / f"clip_{c.rank:02d}.png").write_bytes(b"png")
        out.append(ClipResult(
            rank=c.rank, clip_path=f"clips/clip_{c.rank:02d}.mp4", thumb_path=f"thumbs/clip_{c.rank:02d}.png",
            credit_path=f"clips/clip_{c.rank:02d}.txt", thumb_text=c.thumb_text or "TEKS",
        ))
    return out


def failing_detect(*a, **k):
    raise DownloadError("Video tidak tersedia")


def slow_detect(url, job_dir, cfg, report, force_download=False):
    for i in range(1000):  # ±10 dtk bila tidak dibatalkan
        report("downloading", i / 10, "mengunduh video")
        time.sleep(0.01)
    return fake_detect(url, job_dir, cfg, report)


def slow_render(*args, report=None, **kw):
    for i in range(1000):
        report("rendering", i / 10, "render klip #1")
        time.sleep(0.01)
    return fake_render(*args, report=report, **kw)


def wait_current(app, job_id, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if app.state.worker.current == job_id:
            return
        time.sleep(0.01)
    raise AssertionError(f"{job_id} tidak pernah berjalan")


def make_client(tmp_path, **kw):
    app = create_app(tmp_path, detect_fn=kw.pop("detect_fn", fake_detect),
                     render_fn=kw.pop("render_fn", fake_render), sse_poll_s=0.02, **kw)
    return app, TestClient(app)


def wait(app):
    assert app.state.worker.join_idle(10)


@pytest.fixture
def ready(tmp_path):
    """Client + job yang sudah selesai dianalisis."""
    app, client = make_client(tmp_path)
    with client:
        r = client.post("/api/jobs", json={"url": URL, "template": "center", "title": "Judul Awal"})
        assert r.status_code == 201, r.text
        job_id = r.json()["id"]
        wait(app)
        yield app, client, job_id


def test_create_job_validation(tmp_path):
    app, client = make_client(tmp_path)
    with client:
        assert client.post("/api/jobs", json={"url": "https://vimeo.com/1"}).status_code == 400
        r = client.post("/api/jobs", json={"url": URL, "template": "tidak-ada"})
        assert r.status_code == 400 and "Template" in r.json()["detail"]


def test_detect_flow_and_detail(ready):
    app, client, job_id = ready
    assert job_id.startswith(VID)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "ready_for_review"
    assert job["title"] == "Judul Tes" and job["channel"] == "Channel Tes"
    assert [c["rank"] for c in job["candidates"]] == [1, 2, 3]
    assert job["candidates"][0]["duration"] == 35
    listed = client.get("/api/jobs").json()
    assert listed[0]["id"] == job_id and listed[0]["candidate_count"] == 3


def test_sse_stream_ends_on_terminal(ready):
    app, client, job_id = ready
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "event: job" in body and '"status": "ready_for_review"' in body
    assert "event: end" in body
    assert client.get("/api/jobs/nope/events").status_code == 404


def test_scores(ready):
    app, client, job_id = ready
    data = client.get(f"/api/jobs/{job_id}/scores").json()
    assert data["duration"] == 300 and len(data["smoothed"]) == 300
    assert len(data["candidates"]) == 3


def test_source_supports_range(ready):
    app, client, job_id = ready
    r = client.get(f"/api/jobs/{job_id}/source", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == b"0123456789"


def test_trim_validation(ready):
    app, client, job_id = ready
    cid = client.get(f"/api/jobs/{job_id}").json()["candidates"][0]["id"]
    assert client.patch(f"/api/candidates/{cid}", json={"end": 170}).status_code == 422   # 70 dtk
    assert client.patch(f"/api/candidates/{cid}", json={"end": 90}).status_code == 422    # end < start
    assert client.patch(f"/api/candidates/{cid}", json={"start": -1}).status_code == 422
    assert client.patch(f"/api/candidates/{cid}", json={"end": 301}).status_code == 422   # > durasi video
    r = client.patch(f"/api/candidates/{cid}", json={"start": 95, "end": 140, "thumb_text": " WAH "})
    assert r.status_code == 200
    c = r.json()
    assert (c["start"], c["end"], c["duration"], c["thumb_text"]) == (95, 140, 45, "WAH")
    assert client.patch("/api/candidates/99999", json={"selected": True}).status_code == 404


def test_selection_render_gallery_zip(ready):
    app, client, job_id = ready
    assert client.post(f"/api/jobs/{job_id}/render", json={}).status_code == 400  # belum ada pilihan

    r = client.post(f"/api/jobs/{job_id}/selection", json={"selected": True})
    assert all(c["selected"] for c in r.json()["candidates"])
    r = client.post(f"/api/jobs/{job_id}/selection", json={"selected": False})
    assert not any(c["selected"] for c in r.json()["candidates"])

    cands = client.get(f"/api/jobs/{job_id}").json()["candidates"]
    client.patch(f"/api/candidates/{cands[0]['id']}", json={"selected": True})
    client.patch(f"/api/candidates/{cands[2]['id']}", json={"selected": True})
    r = client.post(f"/api/jobs/{job_id}/render", json={"template": "contoh-split", "landscape": True})
    assert r.status_code == 202, r.text
    wait(app)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done" and job["template"] == "contoh-split" and job["clip_count"] == 2
    assert job["render_options"]["landscape"] is True
    c1 = job["candidates"][0]
    assert c1["clip_url"] == f"/api/jobs/{job_id}/files/clips/clip_01.mp4"
    assert client.get(c1["clip_url"]).content == b"mp4"
    assert client.get(c1["thumb_url"]).status_code == 200
    assert job["candidates"][1]["clip_url"] is None

    # path traversal ditolak
    assert client.get(f"/api/jobs/{job_id}/files/clips/..%2F..%2Fjob.json").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/files/export/x.zip").status_code == 404

    r = client.get(f"/api/jobs/{job_id}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert names == sorted([
        "clips/clip_01.mp4", "clips/clip_01.txt", "thumbs/clip_01.png",
        "clips/clip_03.mp4", "clips/clip_03.txt", "thumbs/clip_03.png",
    ])

    # trim setelah render → hasil lama ditandai perlu render ulang
    r = client.patch(f"/api/candidates/{c1['id']}", json={"start": 101})
    assert r.json()["clip_path"] is None


def test_delete_job(ready, tmp_path):
    app, client, job_id = ready
    assert (tmp_path / "jobs" / job_id).exists()
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert not (tmp_path / "jobs" / job_id).exists()
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_failed_download_marks_failed(tmp_path):
    app, client = make_client(tmp_path, detect_fn=failing_detect)
    with client:
        job_id = client.post("/api/jobs", json={"url": URL}).json()["id"]
        wait(app)
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "failed" and "tidak tersedia" in job["error"]
        assert client.post(f"/api/jobs/{job_id}/render", json={}).status_code == 400


def test_cancel_running_and_queued(tmp_path):
    app, client = make_client(tmp_path, detect_fn=slow_detect)
    with client:
        a = client.post("/api/jobs", json={"url": URL}).json()["id"]
        b = client.post("/api/jobs", json={"url": "https://youtu.be/aaaaaaaaaaa"}).json()["id"]
        wait_current(app, a)

        r = client.post(f"/api/jobs/{b}/cancel")                 # masih antre
        assert r.status_code == 200
        assert r.json()["status"] == "failed" and r.json()["queue_position"] is None

        r = client.post(f"/api/jobs/{a}/cancel")                 # sedang mengunduh
        assert r.status_code == 200 and r.json()["message"] == "membatalkan…"
        wait(app)
        ja, jb = client.get(f"/api/jobs/{a}").json(), client.get(f"/api/jobs/{b}").json()
        assert ja["status"] == "failed" and ja["error"] == "Dibatalkan oleh pengguna"
        assert jb["status"] == "failed" and jb["candidate_count"] == 0   # tidak pernah diproses
        assert client.post(f"/api/jobs/{a}/cancel").status_code == 409
        assert client.delete(f"/api/jobs/{a}").status_code == 204


def test_cancel_render_returns_to_review(tmp_path):
    app, client = make_client(tmp_path, render_fn=slow_render)
    with client:
        job_id = client.post("/api/jobs", json={"url": URL}).json()["id"]
        wait(app)
        client.post(f"/api/jobs/{job_id}/selection", json={"selected": True})
        assert client.post(f"/api/jobs/{job_id}/render", json={}).status_code == 202
        wait_current(app, job_id)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        wait(app)
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "ready_for_review" and job["clip_count"] == 0
        assert job["message"] == "render dibatalkan" and job["error"] is None


def test_cancel_stale_active_status(tmp_path):
    app, client = make_client(tmp_path, start_worker=False)
    with client:
        job_id = client.post("/api/jobs", json={"url": URL}).json()["id"]
        with session(app.state.engine) as s:
            job = s.get(Job, job_id)
            job.status = "downloading"
            s.add(job)
            s.commit()
        app.state.worker.cancel(job_id, "detect")  # keluarkan dari antrean worker yang tidak jalan
        with session(app.state.engine) as s:     # status nyangkut: aktif tapi tidak diproses
            job = s.get(Job, job_id)
            job.status = "downloading"
            s.add(job)
            s.commit()
        r = client.post(f"/api/jobs/{job_id}/cancel")
        assert r.status_code == 200 and r.json()["status"] == "failed"


def test_recover_interrupted_job(tmp_path):
    app, client = make_client(tmp_path, start_worker=False)
    with client:
        job_id = client.post("/api/jobs", json={"url": URL}).json()["id"]
        with session(app.state.engine) as s:
            job = s.get(Job, job_id)
            job.status = "downloading"   # seolah-olah app mati di tengah unduhan
            s.add(job)
            s.commit()
    app2, client2 = make_client(tmp_path)
    with client2:
        wait(app2)
        assert client2.get(f"/api/jobs/{job_id}").json()["status"] == "ready_for_review"


def test_import_cli_job(tmp_path):
    d = tmp_path / "jobs" / VID
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({
        "id": VID, "url": URL, "title": "Dari CLI", "channel": "C", "duration": 600,
        "has_chat": False, "status": "done", "error": None, "created_at": "2026-10-20T04:24:36+00:00",
    }))
    (d / "candidates.json").write_text(json.dumps([
        {"rank": 1, "peak_time": 50, "start": 30, "end": 65, "score": 100, "selected": True,
         "clip_path": "clips\\clip_01.mp4"},
    ]))
    app, client = make_client(tmp_path)
    with client:
        job = client.get(f"/api/jobs/{VID}").json()
        assert job["title"] == "Dari CLI" and job["status"] == "done"
        assert job["candidates"][0]["clip_path"] == "clips/clip_01.mp4"


def test_settings(tmp_path):
    app, client = make_client(tmp_path)
    with client:
        s = client.get("/api/settings").json()
        assert s["detect"]["sensitivity"] == 0.5 and "large-v3" in s["options"]["whisper_models"]
        r = client.put("/api/settings", json={"detect": {"sensitivity": 0.8, "chat_delay_s": 5},
                                              "subtitle": {"model": "medium"}})
        assert r.status_code == 200, r.text
        assert r.json()["detect"]["sensitivity"] == 0.8 and r.json()["subtitle"]["model"] == "medium"
        saved = json.loads((tmp_path / "config.json").read_text())
        assert saved["detect"] == {"sensitivity": 0.8, "chat_delay_s": 5}
        assert client.put("/api/settings", json={"detect": {"sensitivity": 2}}).status_code == 422
        assert client.put("/api/settings", json={"detect": {"nope": 1}}).status_code == 422
        assert client.put("/api/settings", json={"detect": {"max_clip_s": "x"}}).status_code == 422
        assert client.get("/api/settings").json()["detect"]["sensitivity"] == 0.8  # tidak berubah


def test_templates_api(tmp_path):
    app, client = make_client(tmp_path)
    with client:
        names = {t["name"] for t in client.get("/api/templates").json()}
        assert {"center", "contoh-split"} <= names
        body = {"name": "windah", "layout_type": "split", "top_ratio": 0.35,
                "facecam_box": {"x": 0.7, "y": 0.6, "w": 0.3, "h": 0.4}}
        assert client.post("/api/templates", json=body).status_code == 201
        assert client.get("/api/templates/windah").json()["top_ratio"] == 0.35
        bad = {**body, "facecam_box": {"x": 0.8, "y": 0.6, "w": 0.3, "h": 0.4}}
        assert client.post("/api/templates", json=bad).status_code == 422
        assert client.delete("/api/templates/center").status_code == 400
        assert client.delete("/api/templates/windah").status_code == 204
