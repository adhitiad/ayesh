"""Input Sanitization & Prompt Injection Guard.

Middleware untuk FastAPI + helper functions untuk deteksi & blokir
prompt injection, data exfiltration, dan roleplay bypass.
"""

import html
import re

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Pola berbahaya (case-insensitive)
INJECTION_PATTERNS = [
    # Roleplay / persona bypass (EN + ID)
    r"(?i)ignore\s+(?:all\s+)?(?:previous\s+)?instructions?",
    r"(?i)abaikan\s+(?:semua\s+)?(?:instruksi|perintah)(?:\s+sebelumnya)?",
    r"(?i)lupakan\s+(?:semua\s+)?(?:instruksi|perintah|prompt)",
    r"(?i)forget\s+(?:all\s+)?(?:previous\s+)?(?:instructions?|prompts?)",
    r"(?i)you\s+are\s+now\s+(?:a\s+)?(?:developer|admin|root|system|unrestricted)",
    r"(?i)switch\s+to\s+(?:developer|admin|debug|unrestricted)\s+mode",
    r"(?i)disable\s+(?:safety|security|content|filter|guard)",
    r"(?i)bypass\s+(?:safety|security|filter|guard)",
    r"(?i)roleplay\s+as\s+(?:a\s+)?(?:developer|admin|hacker|unrestricted)",
    r"(?i)act\s+as\s+(?:a\s+)?(?:developer|admin|unrestricted)",
    r"(?i)pretend\s+(?:to\s+be\s+)?(?:a\s+)?(?:developer|admin|unrestricted)",
    r"(?i)simulate\s+(?:a\s+)?(?:developer|admin|unrestricted)",
    r"(?i)developer\s+mode",
    r"(?i)mode\s+(?:developer|admin|debug|tak\s*terbatas)",
    r"(?i)kamu\s+sekarang\s+(?:mode\s+)?(?:developer|admin)",
    r"(?i)nonaktifkan\s+(?:safety|filter|keamanan|pengaman|filter)",
    r"(?i)admin\s+mode",
    r"(?i)unrestricted\s+mode",
    # Data exfiltration (EN + ID)
    r"(?i)berikan\s+(?:password|kata\s*sandi|api\s*key|token|kunci)",
    r"(?i)(?:tampilkan|cetak|tunjukkan|keluarkan)\s+.*(?:password|kata\s*sandi|api\s*key|environment|secret|token|kunci)",
    r"(?i)(?:show|print|display|output|leak|exfiltrate|reveal)\s+(?:all\s+)?(?:environment\s+variables?|env\s+vars?|api\s+keys?|secrets?|tokens?|passwords?|credentials?)",
    r"(?i)(?:what\s+is|tell\s+me)\s+(?:your\s+)?(?:api\s+key|secret\s+key|token|password)",
    r"(?i)environment\s+variables?",
    r"(?i)process\.env",
    r"(?i)os\.environ",
    r"(?i)\$\{.*?\}",
    # System prompt extraction
    r"(?i)(?:show|print|display|output|reveal)\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt|instructions?)",
    r"(?i)what\s+(?:is|are)\s+(?:your\s+)?(?:system\s+prompt|instructions?|guidelines?)",
    r"(?i)repeat\s+(?:your\s+)?(?:system\s+prompt|instructions?|prompt)",
    # Tool/chain hijacking
    r"(?i)(?:execute|run|eval|compile)\s+(?:code|script|command|shell)",
    r"(?i)(?:import|require)\s+(?:os|sys|subprocess|shutil)",
    r"(?i)(?:__import__|eval|exec)\s*\(",
    r"(?i)subprocess\.(?:run|call|Popen)",
    r"(?i)os\.system",
    # SQL/NoSQL injection attempts in prompts
    r"(?i)(?:union\s+select|drop\s+table|delete\s+from|insert\s+into|update\s+set)",
    r"(?i)(?:or\s+1\s*=\s*1|'.*or.*')",
    # Instruction delimiter injection (token smuggling)
    r"(?:<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>)",
    r"(?:\[/INST\]|\[INST\]|<<SYS>>|<</SYS>>)",
    r"(?:###\s*(?:System|Instruction|Prompt|Assistant)\s*:)",
    r"(?:<\|endoftext\|>|<\|pad\|>|<\|UNK\|>)",
    # Indirect injection via tool output markers
    r"(?i)(?:NEW\s+INSTRUCTION|OVERRIDE|SYSTEM\s*MESSAGE|IMPORTANT\s*NOTICE)\s*:",
    r"(?i)disregard\s+(?:all\s+)?(?:previous|prior|above|earlier)",
    r"(?i)jangan\s+hiraukan\s+(?:semua\s+)?(?:instruksi|perintah)",
]

# Kompilasi regex
_COMPILED_PATTERNS = [(re.compile(p), p) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> list[tuple[str, str]]:
    """Deteksi pola injeksi dalam teks. Return list of (matched_pattern, matched_text)."""
    matches = []
    for pattern, raw in _COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((raw, match.group()))
    return matches


def sanitize_input(text: str, max_len: int = 10000) -> str:
    """Sanitasi input: escape HTML, batasi panjang, hapus kontrol karakter."""
    if not text:
        return ""
    # Batasi panjang
    text = text[:max_len]
    # Hapus karakter kontrol (kecuali newline, tab)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    # Escape HTML untuk mencegah XSS di log/UI
    text = html.escape(text)
    return text


def guard_prompt(text: str) -> tuple[bool, str]:
    """Guard prompt: return (safe, reason). Jika unsafe, safe=False dengan alasan."""
    if not text:
        return True, ""

    # Cek panjang ekstrem
    if len(text) > 50000:
        return False, "Input terlalu panjang (max 50k karakter)"

    # Deteksi injeksi
    matches = detect_injection(text)
    if matches:
        patterns = [m[0] for m in matches[:3]]  # Ambil max 3 pola
        return False, f"Terdeteksi pola injeksi: {', '.join(patterns)}"

    return True, ""


class PromptInjectionGuardMiddleware(BaseHTTPMiddleware):
    """Middleware FastAPI untuk guard prompt injection di endpoint /chat."""

    def __init__(self, app, protected_paths: list[str] | None = None):
        super().__init__(app)
        self.protected_paths = protected_paths or [
            "/chat",
            "/chat/stream",
            "/chat/stream/tokens",
        ]

    async def dispatch(self, request: Request, call_next):
        # Hanya guard path yang dilindungi
        if request.url.path not in self.protected_paths:
            return await call_next(request)

        # Hanya POST dengan body JSON
        if request.method != "POST":
            return await call_next(request)

        try:
            body = await request.body()
            if not body:
                return await call_next(request)

            import json

            data = json.loads(body)
            message = data.get("message", "")

            # Gate saja (tanpa rewrite body): sanitasi sudah di route_request.
            # Detail pola hanya di log server, respons generik.
            safe, reason = guard_prompt(message)
            if not safe:
                import logging as _logging

                _logging.getLogger("input_guard").warning(
                    f"Blocked {request.url.path}: {reason}"
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Prompt injection detected",
                        "detail": "Input ditolak: terdeteksi pola prompt injection.",
                        "code": "PROMPT_INJECTION",
                    },
                )

        except Exception:
            # P3.5 — Fail-closed: reject on parse failure for security
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Request parsing failed",
                    "detail": "Gagal memproses request.",
                },
            )

        return await call_next(request)


# Helper untuk dipakai manual di route_request atau tools
def validate_user_input(message: str) -> tuple[bool, str]:
    """Validasi input user: return (valid, sanitized_message)."""
    safe, reason = guard_prompt(message)
    if not safe:
        return False, reason
    return True, sanitize_input(message)
