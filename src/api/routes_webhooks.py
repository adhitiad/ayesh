"""Webhook VIP: POST /webhooks/vip-upgrade — HMAC, idempotent, $13.87, status pending|sukses."""

import hashlib
import hmac
import json
import os
import secrets

from fastapi import APIRouter, HTTPException, Request

from src.core.auth.auth_keys import set_user_vip
from src.core.llm.premium import vip_price_cents
from src.core.system.error_handling import generate_request_id

router = APIRouter(prefix="/webhooks")


def _verify_hmac(request: Request, body: bytes) -> None:
    secret = os.getenv("VIP_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="VIP_WEBHOOK_SECRET belum dikonfigurasi (fail-closed)")
    sig = request.headers.get("X-Signature") or request.headers.get("X-Webhook-Signature") or ""
    sig = sig.strip()
    if not sig:
        # fallback Bearer
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.startswith("Bearer "):
            sig = auth[7:].strip()
    if not sig:
        raise HTTPException(status_code=401, detail="Signature webhook diperlukan")
    # Support sha256=hex or raw hex
    if sig.startswith("sha256="):
        sig = sig[7:]
    calc = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not secrets.compare_digest(calc.lower(), sig.lower()) and not secrets.compare_digest(secret, sig):
        raise HTTPException(status_code=401, detail="Signature tidak valid")


@router.post("/vip-upgrade")
async def vip_upgrade(request: Request):
    request_id = generate_request_id()
    body_bytes = await request.body()
    _verify_hmac(request, body_bytes)
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="body harus JSON") from e
    uid = str(data.get("uid") or data.get("user_id") or "").strip()
    external_ref = str(data.get("external_ref") or "").strip()
    amount_cents = data.get("amount_cents")
    currency = str(data.get("currency") or "USD").strip().upper()
    status = str(data.get("status") or "success").strip().lower()
    provider = str(data.get("provider") or "manual").strip()[:50]

    if not uid or not external_ref:
        raise HTTPException(status_code=400, detail="uid dan external_ref wajib")
    if len(external_ref) > 100:
        raise HTTPException(status_code=400, detail="external_ref maksimal 100 karakter")
    if currency != "USD":
        raise HTTPException(status_code=400, detail="currency harus USD")
    if status not in ("pending", "success", "failed", "expired"):
        raise HTTPException(status_code=400, detail="status harus pending|success|failed|expired")

    expected = vip_price_cents()
    if amount_cents is not None:
        try:
            amt = int(amount_cents)
        except Exception:
            raise HTTPException(status_code=400, detail="amount_cents harus integer") from None
        if amt != expected:
            raise HTTPException(status_code=400, detail=f"amount_cents harus {expected} (${expected / 100:.2f})")

    # Simpan history dulu (pending tidak aktifkan vip)
    from src.core.db.db_engine import get_engine

    try:
        from src.core.auth.auth_keys import _ensure_vip_tables

        _ensure_vip_tables()
        with get_engine().begin() as conn:
            from sqlalchemy import text

            # cek external_ref sudah ada (applied_at = hak sudah pernah diberikan)
            existing = conn.execute(
                text("SELECT status, user_id, applied_at FROM vip_upgrades WHERE external_ref=:ref"),
                {"ref": external_ref},
            ).fetchone()
            raw = json.dumps(data, ensure_ascii=False)[:4000]
            if existing:
                old_status = str(existing[0])
                already_applied = existing[2] is not None
                # update status (pending→success, dll); paid_at tidak ditimpa saat replay
                conn.execute(
                    text(
                        "UPDATE vip_upgrades SET status=:st, provider=:prov, raw_payload=:raw, updated_at=NOW(), "
                        "paid_at=CASE WHEN :st='success' AND paid_at IS NULL THEN NOW() ELSE paid_at END "
                        "WHERE external_ref=:ref"
                    ),
                    {"st": status, "prov": provider, "raw": raw, "ref": external_ref},
                )
                if old_status == "success" and status == "success" and already_applied:
                    # replay ref yang sudah memberi hak → jangan extend lagi
                    return {"status": "already", "external_ref": external_ref, "request_id": request_id}
                if status != "success":
                    return {"status": status, "external_ref": external_ref, "request_id": request_id}
            else:
                import uuid as _uuid

                new_id = str(_uuid.uuid4())
                conn.execute(
                    text(
                        "INSERT INTO vip_upgrades (id, user_id, external_ref, amount_cents, currency, status, provider, raw_payload, paid_at) VALUES (:id, :uid, :ref, :amt, :cur, :st, :prov, :raw, CASE WHEN :st='success' THEN NOW() ELSE NULL END)"
                    ),
                    {
                        "id": new_id,
                        "uid": uid,
                        "ref": external_ref,
                        "amt": expected,
                        "cur": currency,
                        "st": status,
                        "prov": provider,
                        "raw": raw,
                    },
                )
                if status != "success":
                    return {"status": status, "external_ref": external_ref, "request_id": request_id}
    except HTTPException:
        raise
    except Exception as _e:
        import logging as _lg

        _lg.getLogger(__name__).warning("vip history save gagal: %s", _e)
        # lanjut coba vip jika success

    if status != "success":
        try:
            from src.core.auth.audit import append_audit

            append_audit(
                f"payment_{status}", actor=f"webhook:{external_ref}", details={"user_id": uid, "amount_cents": expected}
            )
        except Exception as _e:
            import logging as _lg

            _lg.getLogger(__name__).debug("audit payment_%s gagal: %s", status, _e)
        return {"status": status, "external_ref": external_ref, "request_id": request_id}

    result = set_user_vip(uid, external_ref=external_ref, amount_cents=expected)
    if result is None:
        raise HTTPException(status_code=404, detail="User tidak ditemukan atau owner tidak bisa di-vip")
    if result.get("already"):
        return {"status": "already", "role": result["role"], "vip_ref": result.get("vip_ref"), "request_id": request_id}
    result["request_id"] = request_id
    result["payment_status"] = "success"
    # audit
    try:
        from src.core.auth.audit import append_audit

        append_audit("vip_upgrade", actor=f"webhook:{external_ref}", details={"user_id": uid, "amount_cents": expected})
    except Exception as _e:
        import logging as _lg

        _lg.getLogger(__name__).debug("audit vip_upgrade gagal: %s", _e)
    return result
