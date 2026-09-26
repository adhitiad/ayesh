"""Auth manusia (web): email/password, OAuth, 2FA, sesi cookie, CSRF.

Semua mutasi yang membawa cookie `ayesh_session` tunduk pada CSRFMiddleware
(double-submit X-CSRF-Token). Endpoint publik (register/login/oauth callback)
tidak butuh sesi; rate-limit scope "auth" berlaku di middleware.

Observability: tiap event security dicatat ke counter Prometheus
`ayesh_auth_events_total` dan audit hash-chain (`append_audit`, best-effort).
Tidak ada password/token/kode yang ditulis ke log/audit.
"""

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.models import (
    AuthAccountDeleteRequest,
    AuthEmailVerifyRequest,
    AuthLogin2FARequest,
    AuthLoginRequest,
    AuthMeUpdateRequest,
    AuthPasswordChangeRequest,
    AuthPasswordResetConfirmRequest,
    AuthPasswordResetRequest,
    AuthRegisterRequest,
    AuthResendVerifyRequest,
    AuthTotpConfirmRequest,
    AuthTotpDisableRequest,
)
from src.core.auth.account import (
    EmailAlreadyRegistered,
    authenticate_password,
    change_user_password,
    confirm_email_verification,
    confirm_password_reset,
    confirm_totp,
    delete_account_self,
    disable_totp,
    enable_totp,
    get_account,
    issue_2fa_challenge,
    issue_password_reset,
    link_oauth_identity,
    list_linked_accounts,
    regenerate_backup_codes,
    register_with_password,
    resend_verification,
    resolve_2fa_challenge,
    unlink_oauth_provider,
    update_display_name,
    verify_user_totp,
)
from src.core.auth.auth import require_authenticated
from src.core.auth.auth_context import get_current_user
from src.core.auth.emailer import email_enabled, public_link_base, send_email
from src.core.auth.oauth import exchange_oauth, start_oauth
from src.core.auth.passwords import password_policy_ok
from src.core.auth.sessions import (
    clear_session_cookies,
    create_session,
    list_user_sessions,
    read_session_token,
    revoke_all_user_sessions,
    revoke_session,
    revoke_session_by_id,
    set_session_cookie,
    verify_session,
)
from src.core.auth.totp import generate_totp_secret, totp_uri
from src.core.observability.prometheus_metrics import record_auth_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _auth_audit(action: str, actor: str = "", details: dict | None = None) -> None:
    """Tulis baris audit hash-chain (best-effort).

    Audit adalah observability, bukan boundary akses: kalau menulis gagal
    (chain rusak/DB down) outcome auth tidak berubah menjadi DoS. Tidak pernah
    menulis password/token/kode ke `details`.
    """
    try:
        from src.core.auth.audit import append_audit

        append_audit(action, actor=actor, details=details or {})
    except Exception:
        logger.warning("Gagal menulis audit %s actor=%s", action, actor, exc_info=True)


def _establish_session(
    response,
    user_id: str,
    request: Request | None,
) -> None:
    ip = request.client.host if request is not None and request.client else None
    user_agent = request.headers.get("user-agent") if request is not None else None
    info = create_session(user_id, ip=ip, user_agent=user_agent)
    set_session_cookie(response, info["session_token"])


def _send_verification_email(account: dict, token: str) -> None:
    """Kirim email verifikasi. Raise bila SMTP aktif tapi gagal (fail-closed)."""
    link = f"{public_link_base()}/auth/email/verify?token={token}"
    subject = "Verifikasi email Ayesh"
    html = (
        f"<p>Halo {account.get('name', '')},</p>"
        "<p>Klik link berikut untuk memverifikasi email akun Ayesh Anda:</p>"
        f'<p><a href="{link}">{link}</a></p>'
    )
    import anyio

    anyio.from_thread.run(send_email, account["email"], subject, html)


@router.post("/register", status_code=201)
def auth_register(request: Request, body: AuthRegisterRequest):
    try:
        result = register_with_password(body.email, body.password, body.name, username=body.username)
    except EmailAlreadyRegistered as e:
        record_auth_event("register", "conflict")
        _auth_audit(
            "register_failed",
            details={"email": body.email, "reason": "email_terdaftar", "hint_provider": e.hint_provider},
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Email sudah terdaftar. Silakan login dengan Google/GitHub atau password.",
                "hint_provider": e.hint_provider,
            },
        ) from e
    except ValueError as e:
        record_auth_event("register", "invalid")
        _auth_audit("register_failed", details={"email": body.email, "reason": str(e)})
        raise HTTPException(status_code=400, detail=str(e)) from e
    account = result["account"]
    record_auth_event("register", "ok")
    _auth_audit("register", actor=account["id"], details={"email": account["email"], "method": "password"})
    try:
        if email_enabled():
            _send_verification_email(account, result["email_verify_token"])
    except Exception:
        logger.exception("Gagal kirim email verifikasi untuk %s", account.get("email"))
        raise HTTPException(
            status_code=503, detail="Registrasi berhasil tetapi email verifikasi gagal dikirim."
        ) from None
    payload: dict = {"status": "registered", "account": account}
    if result.get("dev_link"):
        payload["dev_link"] = result["dev_link"]
    payload["request_id"] = getattr(request.state, "request_id", None)
    return payload


@router.post("/login")
def auth_login(request: Request, body: AuthLoginRequest):
    identifier = (body.identifier or body.email or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier atau email wajib")
    user_id, err = authenticate_password(identifier, body.password)
    if err == "email_not_verified":
        record_auth_event("login", "email_not_verified")
        _auth_audit("login_failed", details={"identifier": identifier, "reason": "email_not_verified"})
        raise HTTPException(status_code=403, detail="Email belum diverifikasi. Cek email atau minta ulang token.")
    if err:
        record_auth_event("login", "fail")
        _auth_audit("login_failed", details={"identifier": identifier, "reason": err})
        raise HTTPException(status_code=401, detail="Email atau password salah.")
    account = get_account(user_id)
    if not account:
        record_auth_event("login", "fail")
        _auth_audit("login_failed", details={"uid": user_id})
        raise HTTPException(status_code=401, detail="Akun tidak ditemukan atau dinonaktifkan.")
    if account["totp_enabled"]:
        record_auth_event("login", "2fa_required")
        _auth_audit("login_2fa_challenge", actor=user_id)
        challenge = issue_2fa_challenge(user_id)
        return {"status": "2fa_required", "challenge": challenge}
    record_auth_event("login", "ok")
    _auth_audit("login", actor=user_id, details={"method": "password"})
    resp = JSONResponse({"status": "ok", "account": account})
    _establish_session(resp, user_id, request)
    return resp


@router.post("/login/2fa")
def auth_login_2fa(request: Request, body: AuthLogin2FARequest):
    user_id = resolve_2fa_challenge(body.challenge)
    if not user_id:
        record_auth_event("login_2fa", "expired")
        raise HTTPException(status_code=400, detail="Challenge 2FA tidak valid atau kedaluwarsa.")
    ok, _ = verify_user_totp(user_id, body.code)
    if not ok:
        record_auth_event("login_2fa", "fail")
        _auth_audit("login_2fa_failed", actor=user_id)
        raise HTTPException(status_code=401, detail="Kode 2FA salah.")
    account = get_account(user_id)
    if not account:
        record_auth_event("login_2fa", "fail")
        raise HTTPException(status_code=401, detail="Akun tidak ditemukan.")
    record_auth_event("login_2fa", "ok")
    _auth_audit("login", actor=user_id, details={"method": "totp"})
    resp = JSONResponse({"status": "ok", "account": account})
    _establish_session(resp, user_id, request)
    return resp


@router.post("/logout")
def auth_logout(request: Request):
    token = read_session_token(request)
    if token:
        revoke_session(token)
        _auth_audit("logout", actor=get_current_user() or "anon")
    record_auth_event("logout", "ok")
    resp = JSONResponse({"status": "logged_out"})
    clear_session_cookies(resp)
    return resp


@router.get("/me")
def auth_me(request: Request):
    require_authenticated(request)
    account = get_account(get_current_user())
    if not account:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan.")
    account["request_id"] = getattr(request.state, "request_id", None)
    return account


# ── W6: sesi, profil, hapus-akun ───────────────────────────────────────


@router.get("/sessions")
def auth_sessions_list(request: Request):
    require_authenticated(request)
    token = read_session_token(request)
    sessions = list_user_sessions(get_current_user(), token)
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/sessions/{session_id}")
def auth_session_revoke(request: Request, session_id: str):
    require_authenticated(request)
    uid = get_current_user()
    token = read_session_token(request)
    current = verify_session(token) if token else None
    if not revoke_session_by_id(uid, session_id):
        record_auth_event("session_revoke", "not_found")
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan.")
    is_current = bool(current and str(current["id"]) == session_id)
    record_auth_event("session_revoke", "ok")
    _auth_audit("session_revoke", actor=uid, details={"current": is_current})
    resp = JSONResponse({"status": "revoked", "current": is_current})
    if is_current:
        clear_session_cookies(resp)
    return resp


@router.patch("/me")
def auth_me_update(request: Request, body: AuthMeUpdateRequest):
    require_authenticated(request)
    uid = get_current_user()
    try:
        account = update_display_name(uid, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not account:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan.")
    record_auth_event("account_update", "ok")
    _auth_audit("account_update", actor=uid)
    return account


@router.delete("/me")
def auth_me_delete(request: Request, body: AuthAccountDeleteRequest):
    require_authenticated(request)
    uid = get_current_user()
    err = delete_account_self(uid, body.password, body.code)
    if err:
        record_auth_event("account_delete", err)
        _auth_audit("account_delete_failed", actor=uid, details={"reason": err})
        messages = {
            "no_password": "Akun tanpa password (OAuth-only) tidak bisa hapus-akun mandiri.",  # nosec B105 - kunci dict kode error, bukan kredensial
            "bad_password": "Password salah.",  # nosec B105 - kunci dict kode error, bukan kredensial
            "code_required": "2FA aktif — kode TOTP/backup wajib diisi.",
            "bad_code": "Kode 2FA salah.",
        }
        raise HTTPException(status_code=400, detail=messages.get(err, "Gagal menghapus akun."))
    record_auth_event("account_delete", "ok")
    _auth_audit("account_deleted", actor=uid)
    resp = JSONResponse({"status": "deleted"})
    clear_session_cookies(resp)
    return resp


# ── W9e: koneksi OAuth (settings) ──────────────────────────────────────


@router.get("/linked-accounts")
def auth_linked_accounts(request: Request):
    require_authenticated(request)
    accounts = list_linked_accounts(get_current_user())
    return {"accounts": accounts, "count": len(accounts)}


@router.delete("/linked-accounts/{provider}")
def auth_linked_account_unlink(request: Request, provider: str):
    require_authenticated(request)
    uid = get_current_user()
    err = unlink_oauth_provider(uid, provider)
    if err == "last_provider":
        record_auth_event("oauth_unlink", "denied")
        raise HTTPException(
            status_code=400,
            detail="Koneksi terakhir tidak bisa dilepas — tambah password atau provider lain dulu.",
        )
    if err:
        record_auth_event("oauth_unlink", "not_found")
        raise HTTPException(status_code=404, detail="Koneksi tidak ditemukan.")
    record_auth_event("oauth_unlink", "ok")
    _auth_audit("oauth_unlink", actor=uid, details={"provider": provider})
    return {"status": "unlinked", "provider": provider}


@router.post("/email/verify")
def auth_email_verify(body: AuthEmailVerifyRequest):
    if not confirm_email_verification(body.token):
        record_auth_event("email_verify", "fail")
        raise HTTPException(status_code=400, detail="Token verifikasi tidak valid atau sudah terpakai.")
    record_auth_event("email_verify", "ok")
    _auth_audit("email_verified")
    return {"status": "verified"}


@router.post("/email/verify/request")
def auth_email_verify_request(body: AuthResendVerifyRequest):
    result = resend_verification(body.email)
    record_auth_event("resend_verify", "sent" if result["sent"] else "noop")
    payload = {"status": "sent"} if result["sent"] else {"status": "noop"}
    if result.get("dev_link"):
        payload["dev_link"] = result["dev_link"]
    return payload


@router.post("/password/reset")
def auth_password_reset(body: AuthPasswordResetRequest):
    result = issue_password_reset(body.email)
    record_auth_event("password_reset", "issued" if result["sent"] else "noop")
    _auth_audit("password_reset_issued", details={"email": body.email})
    resp = {"status": "sent"}
    if result.get("dev_link"):
        resp["dev_link"] = result["dev_link"]
    return resp


@router.post("/password/reset/confirm")
def auth_password_reset_confirm(body: AuthPasswordResetConfirmRequest):
    ok, err = password_policy_ok(body.new_password)
    if not ok:
        record_auth_event("password_reset_confirm", "weak")
        raise HTTPException(status_code=400, detail=err)
    if not confirm_password_reset(body.token, body.new_password):
        record_auth_event("password_reset_confirm", "fail")
        raise HTTPException(status_code=400, detail="Token reset tidak valid atau sudah terpakai.")
    record_auth_event("password_reset_confirm", "ok")
    _auth_audit("password_reset_confirmed")
    return {"status": "password_updated"}


@router.post("/password/change")
def auth_password_change(request: Request, body: AuthPasswordChangeRequest):
    require_authenticated(request)
    uid = get_current_user()
    try:
        change_user_password(uid, body.current_password, body.new_password)
    except ValueError as e:
        record_auth_event("password_change", "fail")
        _auth_audit("password_change_failed", actor=uid)
        raise HTTPException(status_code=400, detail=str(e)) from e
    token = read_session_token(request)
    revoked = revoke_all_user_sessions(uid, keep_token=token)
    record_auth_event("password_change", "ok")
    _auth_audit("password_change", actor=uid, details={"revoked_sessions": revoked})
    return {"status": "password_updated", "revoked_sessions": revoked}


@router.get("/2fa/status")
def auth_2fa_status(request: Request):
    require_authenticated(request)
    account = get_account(get_current_user())
    return {"enabled": bool(account and account["totp_enabled"])}


@router.post("/2fa/setup")
def auth_2fa_setup(request: Request):
    require_authenticated(request)
    uid = get_current_user()
    account = get_account(uid)
    if not account:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan.")
    if account["totp_enabled"]:
        record_auth_event("totp_setup", "conflict")
        raise HTTPException(status_code=400, detail="2FA sudah aktif. Nonaktifkan dahulu untuk setup ulang.")
    secret = generate_totp_secret()
    if not enable_totp(uid, secret):
        record_auth_event("totp_setup", "fail")
        raise HTTPException(status_code=400, detail="Gagal menyimpan secret 2FA.")
    record_auth_event("totp_setup", "ok")
    _auth_audit("totp_setup", actor=uid)
    return {"secret": secret, "uri": totp_uri(secret, account["email"] or account["name"])}


@router.post("/2fa/confirm")
def auth_2fa_confirm(request: Request, body: AuthTotpConfirmRequest):
    require_authenticated(request)
    uid = get_current_user()
    backup_codes = confirm_totp(uid, body.code)
    if backup_codes is None:
        record_auth_event("totp_enable", "fail")
        _auth_audit("totp_confirm_failed", actor=uid)
        raise HTTPException(status_code=400, detail="Kode TOTP salah.")
    record_auth_event("totp_enable", "ok")
    _auth_audit("totp_enable", actor=uid)
    return {"status": "enabled", "backup_codes": backup_codes}


@router.post("/2fa/disable")
def auth_2fa_disable(request: Request, body: AuthTotpDisableRequest):
    require_authenticated(request)
    uid = get_current_user()
    if not disable_totp(uid, body.password):
        record_auth_event("totp_disable", "fail")
        _auth_audit("totp_disable_failed", actor=uid)
        raise HTTPException(status_code=400, detail="Password salah atau akun tanpa password.")
    token = read_session_token(request)
    revoked = revoke_all_user_sessions(uid, keep_token=token)
    record_auth_event("totp_disable", "ok")
    _auth_audit("totp_disable", actor=uid, details={"revoked_sessions": revoked})
    return {"status": "disabled", "revoked_sessions": revoked}


@router.post("/2fa/backup/regenerate")
def auth_backup_regenerate(request: Request):
    """Bikin ulang 10 backup code — kode lama langsung tak berlaku (W6)."""
    require_authenticated(request)
    uid = get_current_user()
    codes = regenerate_backup_codes(uid)
    if codes is None:
        record_auth_event("backup_regenerate", "fail")
        raise HTTPException(status_code=400, detail="2FA belum aktif.")
    record_auth_event("backup_regenerate", "ok")
    _auth_audit("backup_regenerate", actor=uid)
    return {"status": "regenerated", "backup_codes": codes}


def _safe_redirect(redirect_to: str) -> str:
    if redirect_to.startswith("//"):
        return "/"
    if urlparse(redirect_to).netloc:
        return "/"
    return redirect_to if redirect_to.startswith("/") else "/"


@router.get("/oauth/{provider}")
def auth_oauth_start(provider: str, redirect_to: str = "/"):
    try:
        result = start_oauth(provider, redirect_to=_safe_redirect(redirect_to))
    except ValueError as e:
        record_auth_event("oauth_start", "fail")
        raise HTTPException(status_code=400, detail=str(e)) from e
    record_auth_event("oauth_start", "ok")
    return RedirectResponse(result["authorize_url"], status_code=302)


@router.get("/oauth/{provider}/callback")
async def auth_oauth_callback(provider: str, code: str = "", state: str = ""):
    if not code or not state:
        record_auth_event("oauth", "missing_params")
        return RedirectResponse("/?auth=error&reason=missing_params", status_code=302)
    try:
        redirect_to, profile = await exchange_oauth(provider, code, state)
    except Exception as e:
        logger.warning("OAuth callback gagal provider=%s: %s", provider, e)
        record_auth_event("oauth", "fail")
        return RedirectResponse("/?auth=error&reason=oauth_failed", status_code=302)
    try:
        user = link_oauth_identity(profile)
    except ValueError as e:
        # W9d: provider bilang email tidak verified → tolak fail-closed, alasan
        # diekspos agar UI bisa mengarahkan (sisanya tetap generik anti-enumerasi).
        reason = str(e) if str(e) == "email_unverified" else "oauth_failed"
        logger.warning("OAuth link ditolak provider=%s reason=%s", provider, reason)
        record_auth_event("oauth", "fail")
        return RedirectResponse(f"/?auth=error&reason={reason}", status_code=302)
    except Exception as e:
        logger.warning("OAuth callback gagal provider=%s: %s", provider, e)
        record_auth_event("oauth", "fail")
        return RedirectResponse("/?auth=error&reason=oauth_failed", status_code=302)
    record_auth_event("oauth", "ok")
    _auth_audit(
        "oauth_link", actor=user["id"], details={"provider": profile.get("provider"), "email": profile.get("email")}
    )
    _auth_audit("login", actor=user["id"], details={"method": "oauth", "provider": profile.get("provider")})
    resp = RedirectResponse(f"{redirect_to or '/'}?auth=ok", status_code=302)
    _establish_session(resp, user["id"], None)
    return resp
