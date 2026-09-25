"""Premium model gate: VIP_ONLY_MODELS env comma list, check per model."""

import os


def _vip_models() -> set[str]:
    raw = os.getenv("VIP_ONLY_MODELS", "").strip()
    if not raw:
        return set()
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def is_premium_model(model: str) -> bool:
    """True bila model termasuk VIP-only."""
    if not model:
        return False
    vip = _vip_models()
    if not vip:
        return False
    m = model.strip().lower()
    return m in vip or any(m == v or m.endswith(f":{v}") or v in m for v in vip)


def vip_price_cents() -> int:
    """Harga VIP dalam cents USD — env VIP_PRICE_CENTS atau default 1387 ($13.87)."""
    try:
        return int(os.getenv("VIP_PRICE_CENTS", "1387"))
    except Exception:
        return 1387
