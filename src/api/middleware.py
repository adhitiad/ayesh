import time

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


def _authed_user_id(request: Request) -> str | None:
    """Resolve user id dari API key valid (X-API-Key atau Bearer).

    Return None bila tanpa key / key invalid / lookup gagal — request tetap
    rate-limited per-IP. Lookup di sini reduplikasi auth endpoint agar bucket
    per-user bisa dihitung di middleware sebelum handler jalan.
    """
    key = (request.headers.get("X-API-Key") or "").strip()
    if not key:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            key = auth_header[7:].strip()
    if not key:
        return None
    try:
        user = verify_key(key)
    except Exception:
        # DB error tidak boleh membuat 500 di middleware; jatuh ke bucket IP saja.
        return None
    return user["id"] if user else None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scope = _scope_for_path(request.url.path)
        if not scope:
            return await call_next(request)
        # Per-IP selalu; per-user hanya bila API key valid (bucket terpisah).
        client_ip = _resolve_client_ip(request)
        identities = [("ip", client_ip)]
        user_id = _authed_user_id(request)
        if user_id:
            identities.append(("user", user_id))
        for kind, identity in identities:
            allowed, info = check_rate_limit(scope, identity, kind=kind)
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
                        "bucket": f"{kind}:{identity}",
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
    # Terakhir → middleware paling luar; menangkap 429/500 dari lapisan bawah.
    app.add_middleware(MetricsMiddleware)
