"""Model routing per task — pilih provider/model sesuai jenis tugas.

Default OFF (MODEL_ROUTING_ENABLED=0) → perilaku identik dengan get_llm().
Aktif bila env MODEL_ROUTE_<TASK>=provider[:model] diisi, mis.:
  MODEL_ROUTING_ENABLED=1
  MODEL_ROUTE_CODE=deepseek:deepseek-chat
  MODEL_ROUTE_CHAT=groq
Resolve gagal / provider tak tersedia → fallback fail-closed ke get_llm().
"""

from __future__ import annotations

import os
import threading

from dotenv import load_dotenv

load_dotenv()

_LOCK = threading.Lock()
_task_cache: dict[str, object] = {}

# agent_type → task label default (override input teks di classify_task)
_AGENT_TASK = {
    "coder_agent": "code",
    "admin_agent": "admin",
    "casual_agent": "chat",
}

# Kata kunci ringan untuk task non-agent (tanpa LLM)
_TASK_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ringkas", "summary", "summarize"), "summarize"),
    (("buat_plan", "rencana", "planning"), "plan"),
)


def _enabled() -> bool:
    return os.getenv("MODEL_ROUTING_ENABLED", "0").strip().lower() in {"1", "true", "yes"}


def classify_task(agent_type: str | None, user_input: str = "") -> str:
    """Tentukan label task dari agent_type + kata kunci input (tanpa LLM)."""
    lowered = (user_input or "").lower()
    for kws, task in _TASK_KEYWORDS:
        if any(k in lowered for k in kws):
            return task
    return _AGENT_TASK.get((agent_type or "").strip().lower(), "chat")


def resolve_route(task: str) -> tuple[str, str | None] | None:
    """Ambil (provider, model|None) dari env MODEL_ROUTE_<TASK>. None bila tak di-set."""
    if not _enabled():
        return None
    raw = os.getenv(f"MODEL_ROUTE_{task.strip().upper()}", "").strip()
    if not raw:
        return None
    provider, _, model = raw.partition(":")
    provider = provider.strip().lower()
    if not provider:
        return None
    return provider, (model.strip() or None)


def get_llm_for_task(task: str, agent_type: str | None = None, user_input: str = ""):
    """Return LLM untuk task; routing OFF/resolve gagal → get_llm() (fallback)."""
    from src.core.llm.factory import get_llm

    label = task or classify_task(agent_type, user_input)
    route = resolve_route(label)
    if route is None:
        return get_llm()
    provider, model = route
    cache_key = f"{provider}:{model or ''}"
    with _LOCK:
        if cache_key in _task_cache:
            return _task_cache[cache_key]

    llm = _init_task_provider(provider, model)
    if llm is None:
        return get_llm()
    with _LOCK:
        _task_cache[cache_key] = llm
    return llm


def _init_task_provider(provider: str, model: str | None):
    """Init provider+model spesifik; None bila gagal (caller fallback get_llm)."""
    try:
        from src.core.llm.factory import ProviderRegistry, _build_config

        config = _build_config(provider)
        if config is None:
            return None
        if model:
            config.model = model
        prov_cls = ProviderRegistry.get(provider)
        if prov_cls is None:
            return None
        return prov_cls.create(config)
    except Exception:
        # Fail-closed: error init → fallback get_llm() di pemanggil.
        return None


def reset_for_tests() -> None:
    with _LOCK:
        _task_cache.clear()
