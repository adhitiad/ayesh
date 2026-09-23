"""Enkripsi at-rest kolom sensitif DB (Fernet/AES-128-CBC + HMAC).

Aktif bila `DB_SECRET_KEY` di-set (Fernet key). Tanpa key → fitur OFF,
nilai disimpan/dibaca plaintext (kompatibel instalasi lama; warn sekali).

Generate key baru:
    python -m src.core.db.encryption --generate-key
Enkripsi data plaintext lama yang sudah ada di tabel tercakup:
    python -m src.core.db.encryption --encrypt-existing

Fail-closed: nilai yang TERLIHAT seperti token Fernet tetapi gagal
didekripsi (key salah / data dirusak) → RuntimeError, tidak pernah
mengembalikan nilai mentah. Nilai plaintext lama (bukan token) lolos
apa adanya agar tidak merusak data pra-fitur.

Kolom tercakup dideklarasikan di `_COVERED` dan dipakai model ORM via
`EncryptedText` (TypeDecorator, impl TEXT → tanpa migrasi skema).
Catatan: `ops/backup.py` memakai raw SQL → ekspor backup berisi
ciphertext (portabel hanya dengan DB_SECRET_KEY yang sama).
"""

import base64
import binascii
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

# tabel -> kolom sensitif yang dienkripsi (single source of truth)
_COVERED: dict[str, tuple[str, ...]] = {
    "sessions": ("context",),
    "session_memory": ("content",),
    "monologues": ("content",),
    "pending_approvals": ("args",),
    "preferensi": ("value",),
    "scheduled_jobs": ("prompt",),
    "background_tasks": ("input", "result"),
}

_fernet: Fernet | None = None
_key_loaded = False
_off_warned = False


def generate_key() -> str:
    """Fernet key baru (url-safe base64, 32 byte)."""
    return Fernet.generate_key().decode("ascii")


def reset_cache() -> None:
    """Reset singleton key (dipakai test / reload env)."""
    global _fernet, _key_loaded, _off_warned
    _fernet = None
    _key_loaded = False
    _off_warned = False


def get_fernet() -> Fernet | None:
    """Fernet dari `DB_SECRET_KEY`, atau None bila fitur OFF.

    Key ada tapi tidak valid → RuntimeError (misconfig harus keras,
    jangan diam-diam simpan plaintext).
    """
    global _fernet, _key_loaded, _off_warned
    if _key_loaded:
        return _fernet
    _key_loaded = True
    raw = os.getenv("DB_SECRET_KEY", "").strip()
    if not raw:
        if not _off_warned:
            _off_warned = True
            logger.warning(
                "DB_SECRET_KEY tidak di-set — enkripsi kolom sensitif DB OFF "
                "(generate: python -m src.core.db.encryption --generate-key)"
            )
        return None
    try:
        _fernet = Fernet(raw.encode("ascii"))
    except (ValueError, binascii.Error, TypeError) as e:
        raise RuntimeError(
            "DB_SECRET_KEY bukan Fernet key valid (generate: python -m src.core.db.encryption --generate-key)"
        ) from e
    return _fernet


def _looks_like_token(value: str) -> bool:
    """True bila value kemungkinan token Fernet (bukan plaintext lama).

    Token = urlsafe-base64, byte pertama 0x80 (versi), panjang >= 33 byte.
    """
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return len(raw) >= 33 and raw[0] == 0x80


class EncryptedText(TypeDecorator):
    """TEXT transparan: enkripsi saat tulis, dekripsi saat baca."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        text = value if isinstance(value, str) else str(value)
        f = get_fernet()
        if f is None:
            return text
        return f.encrypt(text.encode("utf-8")).decode("ascii")

    def process_result_value(self, value, dialect):
        if value is None or not isinstance(value, str):
            return value
        if not _looks_like_token(value):
            return value  # plaintext lama — kompatibilitas mundur
        f = get_fernet()
        if f is None:
            return value  # tanpa key tak bisa dekripsi; kembalikan apa adanya
        try:
            return f.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeDecodeError) as e:
            raise RuntimeError(
                "Dekripsi kolom DB gagal — DB_SECRET_KEY salah atau data rusak (fail-closed, nilai tidak dikembalikan)"
            ) from e


def encrypt_existing() -> dict[str, int]:
    """Enkripsi in-place baris plaintext lama di semua kolom tercakup."""
    from sqlalchemy import text as sa_text

    from src.core.db.db_engine import get_engine

    f = get_fernet()
    if f is None:
        raise RuntimeError("DB_SECRET_KEY belum di-set — tidak bisa enkripsi.")
    counts: dict[str, int] = {}
    with get_engine().begin() as conn:
        for table, cols in _COVERED.items():
            for col in cols:
                rows = conn.execute(
                    sa_text(f"SELECT ctid, {col} FROM {table} WHERE {col} IS NOT NULL")  # nosec B608  # noqa: S608
                ).all()
                n = 0
                for ctid, val in rows:
                    if not isinstance(val, str) or _looks_like_token(val):
                        continue
                    token = f.encrypt(val.encode("utf-8")).decode("ascii")
                    conn.execute(
                        sa_text(f"UPDATE {table} SET {col} = :v WHERE ctid = :c"),  # nosec B608  # noqa: S608
                        {"v": token, "c": ctid},
                    )
                    n += 1
                counts[f"{table}.{col}"] = n
    return counts


def main() -> int:
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(description="Utilitas enkripsi kolom DB")
    p.add_argument("--generate-key", action="store_true", help="Cetak Fernet key baru")
    p.add_argument("--encrypt-existing", action="store_true", help="Enkripsi data plaintext lama")
    args = p.parse_args()
    if args.generate_key:
        print(generate_key())
        return 0
    if args.encrypt_existing:
        for k, v in encrypt_existing().items():
            print(f"{k}: {v} baris dienkripsi")
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
