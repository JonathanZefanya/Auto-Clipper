"""F-08: kelola template layout (JSON di data/templates/)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api import deps
from app.api.schemas import TemplateIn
from app.config import AppConfig
from app.templates import (
    DEFAULT_TEMPLATES, Template, ensure_default_templates, list_templates, load_template, save_template,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])
BUILTIN = {t.name for t in DEFAULT_TEMPLATES}


@router.get("")
def get_templates(cfg: AppConfig = Depends(deps.config)) -> list[dict]:
    ensure_default_templates(cfg.templates_dir)
    out = []
    for name in list_templates(cfg.templates_dir):
        try:
            out.append({**load_template(cfg.templates_dir, name).to_dict(), "builtin": name in BUILTIN})
        except ValueError:
            continue  # file rusak dilewati
    return out


@router.get("/{name}")
def get_template(name: str, cfg: AppConfig = Depends(deps.config)) -> dict:
    ensure_default_templates(cfg.templates_dir)
    try:
        return load_template(cfg.templates_dir, name).to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("", status_code=201)
def upsert_template(body: TemplateIn, cfg: AppConfig = Depends(deps.config)) -> dict:
    try:
        t = Template.from_dict(body.model_dump())
        save_template(cfg.templates_dir, t)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return t.to_dict()


@router.delete("/{name}", status_code=204)
def delete_template(name: str, cfg: AppConfig = Depends(deps.config)) -> Response:
    if name in BUILTIN:
        raise HTTPException(400, "Template bawaan tidak bisa dihapus")
    path = cfg.templates_dir / f"{name}.json"
    if name not in list_templates(cfg.templates_dir):
        raise HTTPException(404, "Template tidak ditemukan")
    path.unlink()
    return Response(status_code=204)
