"""Unduh model kecil (MediaPipe .tflite, dll.) sekali ke data/models/."""
from __future__ import annotations

import urllib.request
from pathlib import Path


def ensure_model(models_dir: Path, url: str, log=print) -> Path:
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / Path(url.split("?")[0]).name
    if not path.exists():
        log(f"  mengunduh model → {path.name}")
        tmp = path.with_suffix(path.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp)
        except OSError as e:
            raise RuntimeError(f"Gagal mengunduh model dari {url}: {e}") from e
        tmp.replace(path)
    return path
