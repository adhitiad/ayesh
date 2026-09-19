from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.core.system.rate_limit import _scope_for_path, check_rate_limit
from src.plugins.input_guard import PromptInjectionGuardMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), microphone=()"
        )
        # HSTS only if HTTPS is detected
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scope = _scope_for_path(request.url.path)
        if scope:
            client_ip = request.client.host if request.client else "unknown"
            allowed, info = check_rate_limit(scope, client_ip)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "detail": "Rate limit terlampaui.",
                        "retry_after": info.get("retry_after", 60),
                        "limit": info.get("limit", 0),
                        "remaining": info.get("remaining", 0),
                        "reason": info.get("reason", "unknown"),
                    },
                )
        return await call_next(request)


def setup_middleware(app: FastAPI):
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PromptInjectionGuardMiddleware)
    app.add_middleware(RateLimitMiddleware)
