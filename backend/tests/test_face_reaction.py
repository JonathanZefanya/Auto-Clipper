import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from app import runner
from app.config import DetectConfig, FacecamConfig
from app.pipeline import face_reaction
from app.pipeline.detect import combine, detect
from app.pipeline.face_reaction import crop_filter, expression_score, samples_to_seconds
from app.templates import Box


def test_expression_score():
    assert expression_score(None) == 0.0
    neutral = {"jawOpen": 0.05, "eyeWideLeft": 0.05, "eyeWideRight": 0.05, "browInnerUp": 0.05,
               "mouthSmileLeft": 0.1, "mouthSmileRight": 0.1}
    surprised = {**neutral, "jawOpen": 0.9, "eyeWideLeft": 0.8, "eyeWideRight": 0.8, "browInnerUp": 0.7}
    laughing = {**neutral, "jawOpen": 0.6, "mouthSmileLeft": 0.95, "mouthSmileRight": 0.9}
    assert expression_score(neutral) < 0.15
    assert expression_score(surprised) > 0.7
    assert expression_score(laughing) > 0.7


def test_samples_to_seconds_takes_max_per_second():
    out = samples_to_seconds([(0.0, 0.2), (0.5, 0.6), (2.5, 0.3), (99.0, 1.0)], 4)
    np.testing.assert_allclose(out, [0.6, 0, 0.3, 0])


def test_crop_filter():
    f = crop_filter(Box(0.03, 0.7, 0.22, 0.28), 2.0, 256)
    assert f.startswith("fps=2.0,crop=") and f.endswith("scale=256:256") and "iw*0.0300" in f


def test_face_signal_in_combine_and_detect():
    cfg = DetectConfig(w_audio=0.5, w_face=0.5)
    np.testing.assert_allclose(combine(np.array([1.0, 0]), None, cfg, face=np.array([0, 1.0])), [0.5, 0.5])
    rng = np.random.default_rng(3)
    audio = rng.uniform(0, 0.05, 900)
    audio[200:207] = 1.0
    face = np.zeros(900)
    face[500:507] = 3.0  # reaksi wajah tanpa suara keras
    res = detect(audio, None, 900, DetectConfig(w_face=1.0), face=face)
    assert any(500 <= c.peak_time <= 507 for c in res.candidates)


def test_analyze_face_skips_without_facecam(monkeypatch, tmp_path):
    from app.pipeline import facecam, thumbnail

    class FakeDet:
        def __init__(self, *a): ...
        def __enter__(self): return self
        def __exit__(self, *e): ...

    monkeypatch.setattr("app.pipeline.assets.ensure_model", lambda d, url, log=None: tmp_path / "m")
    monkeypatch.setattr(thumbnail, "FaceDetector", FakeDet)
    monkeypatch.setattr(facecam, "detect_facecam", lambda *a, **k: None)
    score, info = runner._analyze_face(tmp_path / "s.mp4", 600, DetectConfig(), FacecamConfig(), tmp_path,
                                       lambda p, m: None, lambda m: None)
    assert score is None and info == {"skipped": "tidak ada facecam"}


def test_analyze_face_skips_when_face_rarely_detected(monkeypatch, tmp_path):
    """Avatar VTuber: wajah jarang terdeteksi → sinyal dilewati agar tidak menambah noise."""
    from app.pipeline import facecam, thumbnail

    class FakeDet:
        def __init__(self, *a): ...
        def __enter__(self): return self
        def __exit__(self, *e): ...

    class FakeFc:
        box = Box(0, 0.6, 0.3, 0.4)

    monkeypatch.setattr("app.pipeline.assets.ensure_model", lambda d, url, log=None: tmp_path / "m")
    monkeypatch.setattr(thumbnail, "FaceDetector", FakeDet)
    monkeypatch.setattr(facecam, "detect_facecam", lambda *a, **k: FakeFc())
    monkeypatch.setattr(face_reaction, "analyze_face", lambda *a, **k: (np.ones(600), 0.1))
    score, info = runner._analyze_face(tmp_path / "s.mp4", 600, DetectConfig(), FacecamConfig(), tmp_path,
                                       lambda p, m: None, lambda m: None)
    assert score is None and info["skipped"] == "wajah jarang terdeteksi" and info["detect_frac"] == 0.1

    monkeypatch.setattr(face_reaction, "analyze_face", lambda *a, **k: (np.r_[np.zeros(300), np.ones(250)], 0.9))
    score, info = runner._analyze_face(tmp_path / "s.mp4", 600, DetectConfig(), FacecamConfig(), tmp_path,
                                       lambda p, m: None, lambda m: None)
    assert score is not None and score.size == 600 and "skipped" not in info


LANDMARKER = Path(__file__).resolve().parents[2] / "data" / "models" / "face_landmarker.task"


@pytest.mark.skipif(not LANDMARKER.exists() or shutil.which("ffmpeg") is None,
                    reason="butuh face_landmarker.task + FFmpeg")
def test_analyze_face_real_model_no_face_and_cancel(tmp_path):
    src = tmp_path / "s.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=20",
                    "-c:v", "libx264", "-preset", "ultrafast", str(src)], check=True)
    per_sec, frac = face_reaction.analyze_face(src, Box(0, 0.5, 0.3, 0.5), 20, DetectConfig(), LANDMARKER)
    assert per_sec.shape == (20,) and frac == 0.0

    def cancel(_pct):
        raise runner.Cancelled()

    t0 = time.monotonic()
    with pytest.raises(runner.Cancelled):
        face_reaction.analyze_face(src, Box(0, 0.5, 0.3, 0.5), 20, DetectConfig(face_fps=5), LANDMARKER,
                                   on_progress=cancel)
    assert time.monotonic() - t0 < 10
