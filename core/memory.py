"""Koneksi Redis untuk memori jangka pendek agen."""

from __future__ import annotations

import os

import redis
from dotenv import load_dotenv
from core.logger import setup_logger

load_dotenv()

logger = setup_logger("memory")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_redis_client() -> redis.Redis:
    """Buat client Redis dari REDIS_URL.

    Catatan: ``protocol=2`` (RESP2) dipakai agar kompatibel dengan server
    Redis versi lama yang belum mendukung perintah HELLO (RESP3).
    Hapus parameter ini jika server Redis sudah versi >= 6.
    """
    return redis.from_url(REDIS_URL, decode_responses=True, protocol=2)


def test_redis_connection() -> bool:
    """Tes koneksi (PING) ke server Redis lokal (localhost:6379)."""
    try:
        client = get_redis_client()
        response = client.ping()
        logger.info(f"[OK] Terhubung ke Redis ({REDIS_URL}) - PING -> {response}")
        return True
    except redis.exceptions.ConnectionError as exc:
        logger.error(f"[GAGAL] Tidak dapat terhubung ke Redis ({REDIS_URL})")
        logger.error(f"        Detail: {exc}")
        return False


if __name__ == "__main__":
    test_redis_connection()
