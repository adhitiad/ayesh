"""Tes ops: backup memuat tabel auth/identitas & retention membuang data auth kedaluwarsa.

Mock cursor — tanpa DB (ikut pola tes unit cepat tanpa infra).
"""

import unittest
from unittest.mock import patch

from ops.backup import TABLES, dump_all
from ops.retention import purge

_REQUIRED_NEW = {
    "users",
    "vip_upgrades",
    "auth_sessions",
    "auth_tokens",
    "auth_oauth_states",
    "user_llm_configs",
    "user_skill_overrides",
    "user_mcp_overrides",
    "plans",
    "plan_steps",
    "monologues",
}


class _FakeDumpCursor:
    def __init__(self):
        self.description = []
        self._rows = []

    def execute(self, sql, params=None):
        table = sql.split("FROM", 1)[1].strip().rstrip(";").strip()
        self.description = [("id",), ("payload",)]
        self._rows = [(f"{table}-1", {"n": 1}), (f"{table}-2", None)]

    def fetchall(self):
        return self._rows


class _FakeDumpConn:
    def __init__(self):
        self.cur = _FakeDumpCursor()
        self.closed = False

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


class _FakeCursor:
    """Cursor palsu: kembalikan rowcount terprogram per tabel; bisa gagal per tabel."""

    def __init__(self, counts: dict, fail: set | None = None):
        self.counts = counts
        self.fail = fail or set()
        self.executed: list[tuple[str, tuple]] = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params or ()))
        for table in self.counts:
            if f"FROM {table} " in sql:
                if table in self.fail:
                    raise RuntimeError("db down")
                self.rowcount = self.counts[table]
                return
        raise AssertionError(f"SQL tak dikenal: {sql}")


class _FakeConn:
    def __init__(self, counts: dict, fail: set | None = None):
        self.cur = _FakeCursor(counts, fail)
        self.closed = False

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


class TestBackupTables(unittest.TestCase):
    def test_tables_include_auth_and_identity(self):
        missing = sorted(t for t in _REQUIRED_NEW if t not in TABLES)
        self.assertEqual(missing, [])
        self.assertGreaterEqual(len(TABLES), 25)

    def test_all_tables_exist_in_orm(self):
        from src.core.db.models import Base

        orm = set(Base.metadata.tables.keys())
        missing = [t for t in TABLES if t not in orm]
        self.assertEqual(missing, [], f"tabel backup tanpa model ORM (restore rentan): {missing}")

    def test_dump_all_covers_new_tables(self):
        conn = _FakeDumpConn()
        with patch("src.core.db.db.connect", return_value=conn):
            data = dump_all()
        self.assertEqual(set(data["tables"]), set(TABLES))
        for table in _REQUIRED_NEW:
            entry = data["tables"][table]
            self.assertNotIn("error", entry, f"{table}: {entry.get('error')}")
            self.assertEqual(entry["columns"], ["id", "payload"])
            self.assertEqual(len(entry["rows"]), 2)
        self.assertTrue(conn.closed)


class TestRetentionPurge(unittest.TestCase):
    _COUNTS = {
        "logs": 5,
        "request_stats": 4,
        "background_tasks": 6,
        "auth_sessions": 3,
        "auth_tokens": 2,
        "auth_oauth_states": 9,
    }

    def test_purge_covers_auth_tables_with_days_auth(self):
        conn = _FakeConn(self._COUNTS)
        with patch("src.core.db.db.connect", return_value=conn):
            out = purge(days_logs=7, days_stats=14, days_tasks=21, days_auth=30)
        self.assertEqual(out, self._COUNTS)
        self.assertTrue(conn.closed)

        def _params(fragment: str) -> tuple:
            for sql, params in conn.cur.executed:
                if fragment in sql:
                    return tuple(params)
            raise AssertionError(f"SQL berisi {fragment!r} tidak ditemukan")

        self.assertEqual(_params("FROM logs"), ("7",))
        self.assertEqual(_params("FROM auth_sessions"), ("30", "30"))
        self.assertEqual(_params("FROM auth_tokens"), ("30",))
        self.assertEqual(_params("FROM auth_oauth_states"), ())

        sess_sql = next(s for s, _ in conn.cur.executed if "FROM auth_sessions" in s)
        self.assertIn("expires_at", sess_sql)
        self.assertIn("revoked_at", sess_sql)

    def test_default_days_auth_is_30(self):
        conn = _FakeConn(self._COUNTS)
        with patch("src.core.db.db.connect", return_value=conn):
            purge()
        tok_params = next(p for s, p in conn.cur.executed if "FROM auth_tokens" in s)
        self.assertEqual(tok_params, ("30",))

    def test_failure_is_skip_not_crash(self):
        conn = _FakeConn(self._COUNTS, fail={"auth_sessions"})
        with patch("src.core.db.db.connect", return_value=conn):
            out = purge()
        self.assertTrue(str(out["auth_sessions"]).startswith("skip:"), out["auth_sessions"])
        self.assertEqual(out["auth_tokens"], 2)

    def test_never_touches_protected_tables(self):
        conn = _FakeConn(self._COUNTS)
        with patch("src.core.db.db.connect", return_value=conn):
            purge()
        for sql, _ in conn.cur.executed:
            for forbidden in ("FROM audit_log ", "FROM sessions ", "FROM preferensi ", "FROM proyek "):
                self.assertNotIn(forbidden, sql, f"retention tak boleh menyentuh {forbidden.strip()!r}")


if __name__ == "__main__":
    unittest.main()
