"""P2.4 — Safe error handling for API and tool layers.

Provides:
- generate_request_id() — unique ID per request
- safe_error_response() — client-facing error without internal details
- log_internal_error() — server-side detailed error logging
- sanitize_exception() — strip sensitive info from exception messages
"""

import logging
import traceback
import uuid

logger = logging.getLogger("errors")

# Patterns that should NEVER appear in client responses
_SENSITIVE_PATTERNS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credentials",
    "authorization",
    "bearer",
    "/home/",
    "/usr/",
    "/var/",
    "/etc/",
    "/tmp/",
    "C:\\",
    "D:\\",
    "localhost:",
    "127.0.0.1",
    "0.0.0.0",
    "postgres://",
    "postgresql://",
    "redis://",
    "SQL:",
    "SELECT ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "Traceback",
    'File "',
    "line ",
)


def generate_request_id() -> str:
    """Generate a unique request ID (short UUID)."""
    return uuid.uuid4().hex[:12]


def sanitize_exception(exc: Exception) -> str:
    """Sanitize exception message for safe client display.

    Removes filesystem paths, SQL, credentials, stack traces, etc.
    Returns a generic but useful message.
    """
    msg = str(exc)
    if not msg:
        return "Terjadi kesalahan internal."

    # Check for sensitive patterns
    msg_lower = msg.lower()
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.lower() in msg_lower:
            return "Terjadi kesalahan internal. Lihat server log untuk detail."

    # Truncate long messages
    if len(msg) > 200:
        msg = msg[:200] + "..."

    return msg


def log_internal_error(
    request_id: str,
    exc: Exception,
    context: str = "",
    extra: dict | None = None,
) -> None:
    """Log detailed error internally (server-side only).

    This is the ONLY place where full exception details are logged.
    Client never sees this output.
    """
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    log_msg = f"[{request_id}] {context}: {exc}"
    if extra:
        log_msg += f" | extra={extra}"
    log_msg += f"\n{''.join(tb)}"
    logger.error(log_msg)


def safe_error_response(
    exc: Exception,
    request_id: str | None = None,
    context: str = "",
    status_code: int = 500,
) -> dict:
    """Build a safe error response for the client.

    Client receives: {"error": "internal_error", "request_id": "..."}
    Server logs: full exception details.

    Returns:
        dict suitable for JSONResponse
    """
    if request_id is None:
        request_id = generate_request_id()

    # Log internally with full details
    log_internal_error(request_id, exc, context)

    # Build safe client response
    safe_msg = sanitize_exception(exc)
    return {
        "error": "internal_error",
        "request_id": request_id,
        "detail": safe_msg,
    }
