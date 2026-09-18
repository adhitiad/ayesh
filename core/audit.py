"""Audit log tamper-proof: hash-chain (tiap baris mengunci baris sebelumnya).

Skema: hash = SHA256(prev_hash + timestamp + actor + action + details).
Verifikasi: hitung ulang rantai; mismatch = data diubah/dihapus.
"""

import hashlib
import json
from datetime import datetime, timezone


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            actor TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            prev_hash TEXT NOT NULL DEFAULT 'GENESIS',
            hash TEXT NOT NULL
        );
    """)


def _canon_ts(ts) -> str:
    """Kanonik UTC deterministik, kebal session TimeZone PG (mis. WIB)."""
    from datetime import timezone as _tz
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_tz.utc)
    return ts.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _calc_hash(prev_hash: str, ts: str, actor: str, action: str, details: str) -> str:
    payload = f"{prev_hash}|{_canon_ts(ts)}|{actor}|{action}|{details}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_audit(action: str, actor: str = "", details: str = "") -> str:
    """Tambah baris audit, return hash-nya. Idempotent terhadap tabel belum ada."""
    from core.db import connect

    conn = connect()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    prev_hash = row[0] if row else "GENESIS"
    ts = datetime.now(timezone.utc).isoformat()
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False)[:2000]
    h = _calc_hash(prev_hash, ts, actor, action, details)
    cur.execute(
        "INSERT INTO audit_log(ts, actor, action, details, prev_hash, hash) "
        "VALUES (%s, %s, %s, %s, %s, %s);",
        (ts, actor, action, details, prev_hash, h),
    )
    conn.close()
    return h


def verify_audit_chain(limit: int = 10000) -> dict:
    """Verifikasi rantai dari awal (atau N terakhir dengan jangkar). Return status."""
    from core.db import connect

    conn = connect()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, ts, actor, action, details, prev_hash, hash "
        "FROM audit_log ORDER BY id ASC LIMIT %s;",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    prev = "GENESIS"
    for (rid, ts, actor, action, details, prev_hash, h) in rows:
        if prev_hash != prev:
            return {"ok": False, "broken_at_id": rid, "reason": "prev_hash mismatch (baris dihapus/sisipan)"}
        if _calc_hash(prev_hash, ts, actor, action, details) != h:
            return {"ok": False, "broken_at_id": rid, "reason": "hash mismatch (isi diubah)"}
        prev = h
    return {"ok": True, "checked": len(rows), "tip": prev[:16] if rows else "empty"}
