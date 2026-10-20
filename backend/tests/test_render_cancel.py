import shutil
import subprocess
import time

import pytest

from app.config import RenderConfig
from app.runner import Cancelled
from app.templates import Template
from app.pipeline.render import render_clip

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="butuh FFmpeg")


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    path = tmp_path_factory.mktemp("src") / "source.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=30",
         "-f", "lavfi", "-i", "sine=d=30", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(path)],
        check=True,
    )
    return path


def test_cancel_during_audio_analysis(source):
    from app.config import DetectConfig
    from app.pipeline.audio import analyze_audio

    def on_progress(pct):
        raise Cancelled()

    with pytest.raises(Cancelled):
        analyze_audio(source, DetectConfig(audio_chunk_s=1), duration_s=30, on_progress=on_progress)
    # tanpa pembatalan, pipeline yang sama tetap normal
    rms, score = analyze_audio(source, DetectConfig(audio_chunk_s=7), duration_s=30)
    assert rms.size == 30 and score.size == 30


def test_cancel_kills_ffmpeg_and_removes_partial(source, tmp_path):
    out = tmp_path / "clips" / "clip_01.mp4"
    calls = []

    def on_progress(pct):
        calls.append(pct)
        raise Cancelled()

    t0 = time.monotonic()
    with pytest.raises(Cancelled):
        render_clip(source, out, 0, 30, Template("c", "center_crop"),
                    RenderConfig(video_encoder="libx264", x264_preset="slow"), on_progress=on_progress)
    assert calls, "progres harus sempat dilaporkan"
    assert not out.exists()
    assert time.monotonic() - t0 < 10  # tidak menunggu render 30 dtk selesai
