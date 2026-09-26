import os
import time
from typing import ClassVar

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.core.auth.auth import verify_key
from src.core.observability.logger import request_log_context
from src.core.observability.prometheus_metrics import record_request
from src.core.system.error_handling import generate_request_id
from src.core.system.rate_limit import _scope_for_path, check_rate_limit
from src.plugins.input_guard import PromptInjectionGuardMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = "accelerometer=(), camera=(), geolocation=(), microphone=()"
        # HSTS only if HTTPS is detected
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestLogContextMiddleware(BaseHTTPMiddleware):
    """Seed ContextVar request_id dari header X-Request-ID (atau generate baru).

    Id yang sama dipantulkan kembali via header respons. Menjadi dasar request
    ID tracing: semua log JSON pada request async membawa request_id yang sama.
    """

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or generate_request_id()
        request.state.request_id = rid
        with request_log_context(request_id=rid):
            response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def _resolve_client_ip(request: Request) -> str:
    """Resolve real client IP from X-Forwarded-For header (trusted proxy) or connection.

    When behind a reverse proxy (nginx, Cloudflare, ALB), request.client.host is
    the proxy's IP. X-Forwarded-For provides the original client IP.
    Only trusts the first (leftmost) non-private IP to prevent spoofing.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # X-Forwarded-For format: "client, proxy1, proxy2"
        for part in xff.split(","):
            ip = part.strip()
            if not ip:
                continue
            # Skip private/reserved IPs (attacker-controlled)
            try:
                import ipaddress

                addr = ipaddress.ip_address(ip)
                if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                    continue
                return ip
            except ValueError:
                continue
    return request.client.host if request.client else "unknown"


def _authed_user_info(request: Request) -> tuple[str, str] | None:
    """Return (user_id, role) bila kredensial valid (API key atau session cookie)."""
    key = (request.headers.get("X-API-Key") or "").strip()
    if not key:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            key = auth_header[7:].strip()
    user = None
    if key:
        try:
            user = verify_key(key)
        except Exception:
            user = None
    if not user:
        user = _session_user_from_cookie(request)
    if not user:
        return None
    return user["id"], user.get("role", "user")


def _session_user_from_cookie(request: Request) -> dict | None:
    """Resolve user via session cookie (fail-closed)."""
    from src.core.auth.auth_keys import load_user_profile
    from src.core.auth.sessions import read_session_token, verify_session

    cookies = getattr(request, "cookies", None)
    if not isinstance(cookies, dict) or not cookies:
        return None
    token = read_session_token(request)
    if not token:
        return None
    try:
        info = verify_session(token)
    except Exception:
        return None
    if not info:
        return None
    return load_user_profile(info["user_id"])


def _origin_allowed(request: Request) -> bool:
    """Cek Origin (bila ada): harus same-origin (Host) atau ada di CORS_ORIGINS.

    Aman utk CSRF: Origin dari browser harus berupa situs resmi. Absen Origin
    (kiriman non-browser, mis. curl dengan key) → lewat (session cookie tetap
    divalidasi terpisah via X-CSRF-Token).
    """
    origin = request.headers.get("origin")
    if not origin:
        return True
    from urllib.parse import urlsplit

    parsed = urlsplit(origin)
    if not parsed.scheme or not parsed.netloc:
        return False
    host = request.headers.get("host") or ""
    if parsed.netloc == host:
        return True
    allowed = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if o.strip()
    ]
    return origin.rstrip("/") in {a.rstrip("/") for a in allowed}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Fail-closed CSRF untuk request ber-session cookie.

    Mutasi (non-GET) yang membawa cookie ayesh_session wajib: Origin diizinkan
    + X-CSRF-Token cocok dgn cookie ayesh_csrf (double-submit). Request tanpa
    cookie sesi (API-key/publik) tidak terkena (tidak ada state yang dipertaruhkan).
    """

    _SAFE_METHODS: ClassVar[set[str]] = {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def dispatch(self, request: Request, call_next):
        if request.method in self._SAFE_METHODS:
            return await call_next(request)
        from src.core.auth.sessions import read_session_token, verify_csrf

        if not read_session_token(request):
            return await call_next(request)
        if not _origin_allowed(request):
            return JSONResponse(status_code=403, content={"error": "csrf_origin", "detail": "Origin tidak diizinkan."})
        if not verify_csrf(request):
            return JSONResponse(
                status_code=403,
                content={"error": "csrf_token", "detail": "X-CSRF-Token tidak cocok dengan cookie ayesh_csrf."},
            )
        return await call_next(request)


def _authed_user_id(request: Request) -> str | None:
    info = _authed_user_info(request)
    return info[0] if info else None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scope = _scope_for_path(request.url.path)
        if not scope:
            return await call_next(request)
        client_ip = _resolve_client_ip(request)
        # Per-IP selalu
        allowed, info = check_rate_limit(scope, client_ip, kind="ip")
        if not allowed:
            retry_after = info.get("retry_after", 60)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "detail": "Rate limit terlampaui.",
                    "retry_after": retry_after,
                    "limit": info.get("limit", 0),
                    "remaining": info.get("remaining", 0),
                    "reason": info.get("reason", "unknown"),
                    "bucket": f"ip:{client_ip}",
                },
                headers={"Retry-After": str(retry_after)},
            )
        # Per-user hanya bila API key valid (role-aware untuk vip)
        info_user = _authed_user_info(request)
        if info_user:
            user_id, role = info_user
            allowed, info = check_rate_limit(scope, user_id, kind="user", role=role)
            if not allowed:
                retry_after = info.get("retry_after", 60)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": "Rate limit terlampaui.",
                        "retry_after": retry_after,
                        "limit": info.get("limit", 0),
                        "remaining": info.get("remaining", 0),
                        "reason": info.get("reason", "unknown"),
                        "bucket": f"user:{user_id}",
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)


def _route_label(request: Request) -> str:
    """Label route cardinalitas rendah: pola route, bukan path mentah."""
    route = request.scope.get("route")
    path_attr = getattr(route, "path", None)
    if isinstance(path_attr, str) and path_attr:
        return path_attr
    return "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Catat counter + histogram Prometheus per request.

    Ditambahkan TERAKHIR di setup_middleware → paling luar, sehingga status
    429 (rate limit) dan 500 (exception) tetap terrekam.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            record_request(
                _route_label(request),
                request.method,
                500,
                time.perf_counter() - start,
            )
            raise
        record_request(
            _route_label(request),
            request.method,
            response.status_code,
            time.perf_counter() - start,
        )
        return response


def setup_middleware(app: FastAPI):
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLogContextMiddleware)
    app.add_middleware(PromptInjectionGuardMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CSRFMiddleware)
    # Terakhir → middleware paling luar; menangkap 429/500 dari lapisan bawah.
    app.add_middleware(MetricsMiddleware)
