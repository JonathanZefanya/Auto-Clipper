"""F-14: pengaturan (config.json)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.config import save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

OPTIONS = {
    "whisper_models": ["medium", "large-v3"],
    "download_heights": [480, 720, 1080, 1440, 2160],
    "devices": ["auto", "cuda", "cpu"],
    "encoders": ["auto", "h264_nvenc", "libx264"],
}


def _payload(request: Request) -> dict:
    cfg = request.app.state.config_loader()
    raw_cfg = request.app.state.raw_config_loader()
    return {
        **cfg.to_settings(),
        # data_dir yang tersimpan (berlaku setelah restart) vs yang sedang dipakai
        "data_dir_configured": str(raw_cfg.data_dir),
        "restart_required": raw_cfg.data_dir.resolve() != cfg.data_dir.resolve(),
        "config_file": str(cfg.config_file),
        "options": OPTIONS,
    }


@router.get("")
def get_settings(request: Request) -> dict:
    return _payload(request)


@router.put("")
def put_settings(body: dict, request: Request) -> dict:
    try:
        save_settings(request.app.state.raw_config_loader(), body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _payload(request)
