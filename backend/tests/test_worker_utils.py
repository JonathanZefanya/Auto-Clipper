import json

from app.pipeline.download import _progress_hook
from app.worker import reuse_existing_source


def test_progress_hook_combines_files_and_never_decreases():
    seen = []
    hook = _progress_hook("video", lambda _l, pct: seen.append(pct))
    hook({"status": "downloading", "filename": "v", "downloaded_bytes": 50, "total_bytes_estimate": 100})
    hook({"status": "downloading", "filename": "v", "downloaded_bytes": 55, "total_bytes_estimate": 140})  # estimasi naik
    hook({"status": "finished", "filename": "v", "total_bytes": 120})
    hook({"status": "downloading", "filename": "a", "downloaded_bytes": 0, "total_bytes": 30})  # audio mulai
    hook({"status": "downloading", "filename": "a", "downloaded_bytes": 30, "total_bytes": 30})
    assert seen == sorted(seen)
    assert seen[0] == 50 and seen[-1] == 99.9


def _make_job(root, name, video_id, with_source=True):
    d = root / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"video_id": video_id}))
    if with_source:
        (d / "source.mp4").write_bytes(b"video")
        (d / "chat.json").write_text("{}")
    return d


def test_reuse_existing_source_hardlinks(tmp_path):
    jobs = tmp_path / "jobs"
    _make_job(jobs, "other", "BBBBBBBBBBB")
    _make_job(jobs, "old", "AAAAAAAAAAA")
    new = jobs / "new"
    assert reuse_existing_source(jobs, new, "AAAAAAAAAAA")
    assert (new / "source.mp4").read_bytes() == b"video"
    assert (new / "chat.json").exists()
    assert (new / "source.mp4").stat().st_nlink == 2  # hardlink, bukan salinan


def test_reuse_existing_source_none_available(tmp_path):
    jobs = tmp_path / "jobs"
    _make_job(jobs, "old", "AAAAAAAAAAA", with_source=False)
    assert not reuse_existing_source(jobs, jobs / "new", "AAAAAAAAAAA")
    assert not reuse_existing_source(tmp_path / "missing", tmp_path / "x", "AAAAAAAAAAA")
