"""Test observability auth: counter Prometheus + audit trail hash-chain.

Butuh DB (Postgres). User/sesi di-cleanup; baris audit sengaja append-only
(chain tamper-proof), konsisten dengan tests test_prompt_structure.
"""

import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app
from src.core.auth.audit import _calc_hash, _canon_ts, append_audit, verify_audit_chain
from src.core.db.db import connect
from src.core.db.db_engine import get_session
from src.core.db.models import AuthSession, AuthToken, User
from src.core.observability.prometheus_metrics import record_auth_event, render

_KNOWN_UIDS: list[str] = []

_ENV = patch.dict(
    os.environ,
    {
        "AUTH_DEV_VERIFY": "1",
        "AUTH_REQUIRE_EMAIL_VERIFICATION": "1",
        "RATE_LIMIT_AUTH_BURST": "500",
        "RATE_LIMIT_AUTH_SUSTAINED": "10000",
        "RATE_LIMIT_AUTH_USER_BURST": "500",
        "RATE_LIMIT_AUTH_USER_SUSTAINED": "10000",
    },
)


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()
    with get_session() as db:
        db.query(AuthSession).filter(AuthSession.user_id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.query(AuthToken).filter(AuthToken.user_id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.commit()


def _email() -> str:
    return f"obs{uuid.uuid4().hex[:12]}@test.local"


def _parse_metric(text: str, name: str, labels: dict[str, str]) -> int:
    target = name + "{"
    for line in text.splitlines():
        if not line.startswith(target):
            continue
        label_part = line[len(target) :].split("}", 1)[0]
        pairs = dict(pair.split("=", 1) for pair in label_part.split(","))
        if all(pairs.get(k, "").strip('"') == v for k, v in labels.items()):
            return int(line.rsplit(" ", 1)[1])
    return 0


class TestAuthMetrics(unittest.TestCase):
    def test_record_auth_event_renders(self):
        event = f"unit_evt_{uuid.uuid4().hex[:8]}"
        record_auth_event(event, "ok")
        text = render()
        self.assertEqual(_parse_metric(text, "ayesh_auth_events_total", {"event": event, "outcome": "ok"}), 1)
        self.assertIn("# TYPE ayesh_auth_events_total counter", text)

    def test_flow_events_present(self):
        client = TestClient(app, raise_server_exceptions=False)
        email = _email()
        r = client.post("/auth/register", json={"email": email, "password": "secret-pass-123", "name": "Obs"})
        self.assertEqual(r.status_code, 201, r.text)
        _KNOWN_UIDS.append(r.json()["account"]["id"])
        wrong = client.post("/auth/login", json={"email": email, "password": "wrong-pass-999"})
        self.assertEqual(wrong.status_code, 401)
        text = render()
        self.assertGreaterEqual(
            _parse_metric(text, "ayesh_auth_events_total", {"event": "register", "outcome": "ok"}), 1
        )
        self.assertGreaterEqual(
            _parse_metric(text, "ayesh_auth_events_total", {"event": "login", "outcome": "fail"}), 1
        )


class TestAuthAudit(unittest.TestCase):
    def test_chain_records_and_stays_valid(self):
        client = TestClient(app, raise_server_exceptions=False)
        email = _email()
        r = client.post("/auth/register", json={"email": email, "password": "secret-pass-123", "name": "Audit"})
        self.assertEqual(r.status_code, 201, r.text)
        uid = r.json()["account"]["id"]
        _KNOWN_UIDS.append(uid)
        token = r.json()["dev_link"].rsplit("token=", 1)[1]
        ok = client.post("/auth/email/verify", json={"token": token})
        self.assertEqual(ok.status_code, 200)
        bad = client.post("/auth/login", json={"email": email, "password": "wrong-pass-999"})
        self.assertEqual(bad.status_code, 401)
        good = client.post("/auth/login", json={"email": email, "password": "secret-pass-123"})
        self.assertEqual(good.status_code, 200)

        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT action, actor, details, ts, prev_hash, hash FROM audit_log "
                "WHERE action IN ('register','login','login_failed','email_verified') "
                "ORDER BY id ASC;"
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        actions = [a for a, *_ in rows]
        for want in ("register", "login", "login_failed", "email_verified"):
            self.assertIn(want, actions, f"action {want} harus tercatat di audit")
        scoped = {"register", "login", "login_failed"}
        my_rows = [row for row in rows if (row[1] == uid or email in row[2]) and row[0] in scoped]
        my_actions = {r[0] for r in my_rows}
        self.assertEqual(my_actions, scoped, "register/login/login_failed untuk email ini harus tercatat di audit")
        for action, actor, details, ts, prev_hash, h in my_rows:
            if action == "register":
                self.assertEqual(actor, uid)
            if action == "login_failed":
                self.assertIn(email, details)
                self.assertNotIn("wrong-pass-999", details)
            recomputed = _calc_hash(prev_hash, _canon_ts(ts), actor, action, details)
            self.assertEqual(recomputed, h, f"hash tidak konsisten untuk {action}")
        for action, actor, details, ts, prev_hash, h in rows:
            if action == "email_verified":
                recomputed = _calc_hash(prev_hash, _canon_ts(ts), actor, action, details)
                self.assertEqual(recomputed, h, "hash tidak konsisten untuk email_verified")

        self.assertTrue(verify_audit_chain()["ok"])

    def test_audit_failure_does_not_block_auth(self):
        email = _email()
        with patch("src.core.auth.audit.append_audit", side_effect=RuntimeError("chain rusak")):
            client = TestClient(app, raise_server_exceptions=False)
            r = client.post("/auth/register", json={"email": email, "password": "secret-pass-123", "name": "NoAudit"})
        self.assertEqual(r.status_code, 201, r.text)
        _KNOWN_UIDS.append(r.json()["account"]["id"])
        login = client.post("/auth/login", json={"email": email, "password": "secret-pass-123"})
        self.assertEqual(login.status_code, 403, login.text)  # email_not_verified (normal flow, bukan blokir audit)


class TestAuditHelper(unittest.TestCase):
    def test_append_audit_plain(self):
        h = append_audit("unit_audit_helper", actor="test", details={"marker": uuid.uuid4().hex})
        self.assertTrue(h)
        self.assertTrue(verify_audit_chain()["ok"])


if __name__ == "__main__":
    unittest.main()
