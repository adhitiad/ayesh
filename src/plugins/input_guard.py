"""Input Sanitization & Prompt Injection Guard.

Middleware untuk FastAPI + helper functions untuk deteksi & blokir
prompt injection, data exfiltration, dan roleplay bypass.
"""

import base64
import binascii
import html
import re
import unicodedata

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


def _normalize_text(text: str) -> str:
    """Normalisasi Unicode NFKC untuk mendeteksi homoglyph dan encoding bypass."""
    return unicodedata.normalize("NFKC", text)


def _deobfuscate_text(text: str) -> str:
    """Hapus karakter obfuscasi umum di antara huruf: i-g-n-o-r-e → ignore.

    Menangani: hyphens, dots, underscores, asterisks, tildes, dll.
    Contoh: 'i.g-n-o-r-e' → 'ignore', 'b.y.p.a.s.s' → 'bypass'
    """
    # Strip obfuscation chars antara huruf: a-z, 0-9 yang dipisah non-alnum
    return re.sub(r"(?i)([a-z0-9])[\s.\-_*~`|/\\]{1,3}([a-z0-9])", r"\1\2", text)


def _detect_encoded_suspicious(text: str) -> list[str]:
    """Deteksi string mencurigakan yang tampak Base64 atau hex panjang."""
    suspicious = []
    # Deteksi Base64: string >=10 char dengan charset Base64 dan valid padding
    b64_pattern = re.compile(r"(?:[A-Za-z0-9+/]{10,}={0,2})")
    for match in b64_pattern.finditer(text):
        candidate = match.group()
        try:
            decoded = base64.b64decode(candidate, validate=True)
            decoded_text = decoded.decode("utf-8", errors="ignore")
            if len(decoded) >= 4 and any(
                word in decoded_text.lower()
                for word in ["import", "os.", "sys.", "exec", "eval", "subprocess", "password", "secret"]
            ):
                suspicious.append(f"base64:{candidate[:20]}...")
        except binascii.Error, ValueError:
            pass
    # Deteksi hex encoded string (>=10 chars)
    hex_pattern = re.compile(r"(?:0x[0-9a-fA-F]{8,}|(?:[0-9a-fA-F]{2}){8,})")
    for match in hex_pattern.finditer(text):
        suspicious.append(f"hex:{match.group()[:20]}...")
    # Deteksi encoded whitespace/tab chars
    if re.search(r"(?:\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4})", text):
        suspicious.append("encoded_escape_sequence")
    return suspicious


def detect_injection(text: str) -> list[tuple[str, str]]:
    """Deteksi pola injeksi dalam teks. Return list of (matched_pattern, matched_text).

    Normalisasi NFKC diterapkan sebelum regex untuk mengatasi homoglyph dan encoding bypass.
    Deobfuscation diterapkan untuk mendeteksi word splitting (i-g-n-o-r-e → ignore).
    """
    matches = []
    # Normalisasi NFKC untuk mendeteksi homoglyph, full-width chars, dll.
    normalized = _normalize_text(text)
    # Deobfuscation: hapus karakter pemisah antara huruf
    deobfuscated = _deobfuscate_text(normalized)
    for pattern, raw in _COMPILED_PATTERNS:
        # Cek pada text yang sudah deobfuscated (lebih ketat)
        for match in pattern.finditer(deobfuscated):
            matches.append((raw, match.group()))
        # Cek juga pada original normalized (backward-compatible)
        for match in pattern.finditer(normalized):
            if match.group() not in [m[1] for m in matches]:
                matches.append((raw, match.group()))
    # Deteksi string Base64/hex mencurigakan
    encoded = _detect_encoded_suspicious(normalized)
    for enc in encoded:
        matches.append(("encoded_suspicious", enc))
    return matches


def sanitize_input(text: str, max_len: int = 10000) -> str:
    """Sanitasi input: escape HTML, batasi panjang, hapus kontrol karakter.

    Normalisasi NFKC diterapkan untuk mengatasi homoglyph sebelum sanitasi.
    """
    if not text:
        return ""
    # Normalisasi NFKC untuk mengatasi homoglyph dan encoding bypass
    text = _normalize_text(text)
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

    # Normalisasi NFKC sebelum pengecekan
    normalized = _normalize_text(text)

    # Cek panjang ekstrem (gunakan text asli untuk panjang)
    if len(text) > 50000:
        return False, "Input terlalu panjang (max 50k karakter)"

    # Deteksi injeksi pada text yang sudah dinormalisasi
    matches = detect_injection(normalized)
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

                _logging.getLogger("input_guard").warning(f"Blocked {request.url.path}: {reason}")
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


# Pattern untuk sanitasi tool output — strip token delimiter & injection markers
_TOOL_OUTPUT_SANITIZE_PATTERNS = [
    re.compile(r"<\|im_start\|>.*?<\|im_end\|>", re.DOTALL),
    re.compile(r"<\|system\|>.*?<\|endoftext\|>", re.DOTALL),
    re.compile(r"<\|user\|>.*?<\|assistant\|>", re.DOTALL),
    re.compile(r"\[/INST\].*?\[INST\]", re.DOTALL),
    re.compile(r"<<SYS>>.*?<</SYS>>", re.DOTALL),
    re.compile(r"###\s*(?:System|Instruction|Prompt|Assistant)\s*:.*", re.DOTALL),
    re.compile(r"(?i)(?:NEW\s+INSTRUCTION|OVERRIDE|SYSTEM\s*MESSAGE)\s*:.*", re.DOTALL),
]


def sanitize_tool_output(text: str, max_len: int = 20000) -> str:
    """Bersihkan output tool dari potensi indirect prompt injection.

    - Strip token delimiter / instruction markers
    - Batasi panjang
    - Decode escape sequences mencurigakan
    """
    if not text:
        return ""
    text = _normalize_text(text)
    for pat in _TOOL_OUTPUT_SANITIZE_PATTERNS:
        text = pat.sub("", text)
    text = text[:max_len]
    return text


# Helper untuk dipakai manual di route_request atau tools
def validate_user_input(message: str) -> tuple[bool, str]:
    """Validasi input user: return (valid, sanitized_message)."""
    safe, reason = guard_prompt(message)
    if not safe:
        return False, reason
    return True, sanitize_input(message)
