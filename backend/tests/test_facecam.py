import numpy as np
import pytest

from app.config import FacecamConfig, RenderConfig
from app.pipeline import facecam
from app.pipeline.facecam import Det
from app.pipeline.thumbnail import Face


def test_tiles_cover_frame_with_overlap():
    ts = facecam.tiles(1280, 720, 3)
    assert ts[0] == (0, 0, 1280, 720) and len(ts) == 10
    assert max(x + w for x, _, w, _ in ts) == 1280 and max(y + h for _, y, _, h in ts) == 720


def test_nms_keeps_best():
    a, b = Det(0.1, 0.1, 0.1, 0.1, 0.9), Det(0.11, 0.1, 0.1, 0.1, 0.7)
    c = Det(0.5, 0.5, 0.1, 0.1, 0.8)
    assert facecam.nms([b, a, c], 0.4) == [a, c]


def test_detect_tiled_maps_tile_coords_back():
    class FakeDetector:
        def detect(self, rgb):
            # hanya tile berukuran tertentu "melihat" wajah di pojok kiri-atas tile
            return [Face(10, 20, 30, 40, 0.9)] if rgb.shape[:2] == (360, 640) else []

    dets = facecam.detect_tiled(np.zeros((720, 1280, 3), np.uint8), FakeDetector(), FacecamConfig())
    assert dets and all(abs(d.w - 30 / 1280) < 1e-9 for d in dets)
    assert any(abs(d.x - (320 + 10) / 1280) < 1e-9 and abs(d.y - (180 + 20) / 720) < 1e-9 for d in dets)


def _stable_and_moving(n=10):
    rng = np.random.default_rng(0)
    frames = []
    for i in range(n):
        fr = [Det(0.80 + rng.uniform(-0.005, 0.005), 0.70, 0.06, 0.10, 0.9)]  # facecam kanan-bawah
        if i % 2 == 0:  # wajah karakter game, pindah-pindah
            fr.append(Det(rng.uniform(0.1, 0.6), rng.uniform(0.1, 0.5), 0.08, 0.12, 0.95))
        frames.append(fr)
    return frames


def test_pick_stable_cluster():
    cfg = FacecamConfig()
    frames = _stable_and_moving()
    best = facecam.pick_facecam(facecam.cluster_faces(frames, cfg), len(frames), cfg)
    assert best is not None and len(best.frames) == 10
    assert abs(best.median().x - 0.80) < 0.01


def test_pick_none_when_no_stable_face():
    cfg = FacecamConfig()
    frames = [[Det(0.1 * i, 0.1, 0.05, 0.08, 0.9)] for i in range(10)]
    assert facecam.pick_facecam(facecam.cluster_faces(frames, cfg), 10, cfg) is None


@pytest.mark.parametrize("face", [
    Det(0.80, 0.70, 0.06, 0.10, 0.9),   # pojok kanan bawah → harus di-clamp
    Det(0.02, 0.02, 0.05, 0.09, 0.9),   # pojok kiri atas
    Det(0.45, 0.40, 0.10, 0.18, 0.9),   # tengah
])
def test_facecam_box_aspect_contains_face_inside_frame(face):
    cfg, W, H = FacecamConfig(), 1280, 720
    aspect = facecam.target_aspect(RenderConfig(), 0.4)
    assert aspect == pytest.approx(1080 / 768)
    b = facecam.facecam_box(face, W, H, aspect, cfg)
    assert 0 <= b.x and 0 <= b.y and b.x + b.w <= 1 + 1e-4 and b.y + b.h <= 1 + 1e-4
    assert (b.w * W) / (b.h * H) == pytest.approx(aspect, rel=0.02)
    assert b.x <= face.x and b.y <= face.y
    assert b.x + b.w >= face.x + face.w - 1e-4 and b.y + b.h >= face.y + face.h - 1e-4
