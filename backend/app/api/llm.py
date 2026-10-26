"""F-19: status LLM lokal (Ollama) untuk UI."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api import deps
from app.config import AppConfig
from app.pipeline.titles import OllamaClient, TitleError, model_installed

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status")
def llm_status(cfg: AppConfig = Depends(deps.config)) -> dict:
    t = cfg.title
    out = {"enabled": t.enabled, "url": t.ollama_url, "model": t.model,
           "available": False, "models": [], "model_ready": False, "error": None}
    try:
        models = OllamaClient(t.ollama_url, timeout_s=3).models()
    except TitleError as e:
        out["error"] = str(e)
        return out
    out.update(available=True, models=models, model_ready=model_installed(t.model, models))
    if not out["model_ready"]:
        out["error"] = f"Model {t.model} belum diunduh. Jalankan: ollama pull {t.model}"
    return out
