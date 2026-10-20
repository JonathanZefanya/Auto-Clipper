"""run_render memakai subtitle hasil edit (F-16) tanpa memanggil Whisper."""
from pathlib import Path

from app import runner
from app.config import RenderConfig, SubtitleConfig, ThumbnailConfig
from app.pipeline import render, subdoc, subtitle
from app.pipeline.subtitle import Line
from app.templates import Template


def test_render_uses_edited_subtitles(tmp_path, monkeypatch):
    rendered = {}

    def fake_render_clip(source, out: Path, start, end, template, cfg, ass_path=None, **kw):
        out.write_bytes(b"mp4")
        rendered[out.name] = ass_path.read_text(encoding="utf-8") if ass_path else ""
        return "libx264"

    class NoWhisper:
        def __init__(self, *a, **k):
            raise AssertionError("Whisper tidak boleh dipanggil bila subtitle sudah ada")

    monkeypatch.setattr(render, "render_clip", fake_render_clip)
    monkeypatch.setattr(subtitle, "Transcriber", NoWhisper)
    monkeypatch.setattr(runner.audio, "require_ffmpeg", lambda: "ffmpeg")

    # dokumen dibuat untuk rentang 100..135, klip kini di-trim jadi 102..135
    subdoc.save_doc(tmp_path, 1, subdoc.SubDoc(100, 135, [Line(3.0, 4.0, "TEKS EDITAN")], edited=True))
    results = runner.run_render(
        tmp_path / "source.mp4", tmp_path, [runner.ClipSpec(1, 102, 135, 120)],
        Template("c", "center_crop"), RenderConfig(), SubtitleConfig(), ThumbnailConfig(),
        tmp_path / "models", runner.RenderOptions(subtitle=True, thumbnail=False),
    )
    ass = rendered["clip_01.mp4"]
    assert "TEKS EDITAN" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.00" in ass  # 3–4 dtk digeser −2 dtk
    assert results[0].clip_path == "clips/clip_01.mp4" and results[0].subs_path is None
