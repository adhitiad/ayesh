"""Estimasi biaya LLM per request dari jumlah token.

Nilai default per-1M token (USD) mengikuti provider pada LLM_FALLBACK_ORDER
(NVIDIA NIM, Groq, Google Gemini, OpenAI-compatible). Tabel dapat diperluas
via register_model_price / env COST_PER_1M_PROMPT & COST_PER_1M_COMPLETION
sebagai fallback untuk model yang tidak dikenal.
"""

import logging

logger = logging.getLogger(__name__)

# Model → (harga input per 1M token USD, harga output per 1M token USD).
# Angka kisaran publik; perkiraan kasar untuk observability, bukan billing.
_DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "llama-3.3-70b-instruct": (0.85, 2.1),
    "llama-3.1-8b-instruct": (0.18, 0.18),
    "llama-3.3-70b-versatile": (0.85, 2.1),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1-nano": (0.1, 0.4),
    "gemini-2.0-flash": (0.1, 0.4),
    "gemini-1.5-flash": (0.075, 0.3),
    "gemini-1.5-pro": (1.25, 5.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "deepseek-chat": (0.27, 1.1),
    "command-r-plus": (3.0, 15.0),
    "phi-3-mini": (0.1, 0.1),
}

_pricing_overrides: dict[str, tuple[float, float]] = {}


def register_model_price(model: str, input_usd_1m: float, output_usd_1m: float) -> None:
    """Tambahkan/ubah harga untuk satu model."""
    _pricing_overrides[model] = (float(input_usd_1m), float(output_usd_1m))


def _env_float(name: str, default: float) -> float:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def price_for(model: str):
    """(input_usd_1m, output_usd_1m) untuk model, fallback env / 0."""
    key = (model or "").strip().lower()
    if not key:
        return (0.0, 0.0)
    priced = _pricing_overrides.get(key) or _DEFAULT_PRICING.get(key)
    if priced:
        return priced
    return (
        _env_float("COST_PER_1M_PROMPT", 0.0),
        _env_float("COST_PER_1M_COMPLETION", 0.0),
    )


def estimate_cost_usd(model: str, prompt_tokens: int | None, completion_tokens: int | None) -> float:
    """Perkiraan biaya USD untuk request. Tanpa harga/threshold → 0.0."""
    try:
        in_1m, out_1m = price_for(model)
        if in_1m <= 0 and out_1m <= 0:
            return 0.0
        p = max(0, int(prompt_tokens or 0))
        c = max(0, int(completion_tokens or 0))
        return round((p / 1_000_000 * in_1m) + (c / 1_000_000 * out_1m), 6)
    except Exception as _e:
        logger.debug("estimate_cost_usd error: %s", _e)
        return 0.0
