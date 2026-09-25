"""Regression test billing history: webhook status pending|sukses + GET /billing/history.

Cakup:
- POST /webhooks/vip-upgrade: HMAC fail-closed (503 tanpa secret, 401 sig salah)
- status=pending → insert history, user TIDAK jadi vip; status=success → vip aktif
- replay success → already (idempotent)
- GET /billing/history: 401 tanpa key, self-scope, IDOR 403 (owner boleh), filter status invalid 400
- GET /billing/history/{ref} & /billing/status/{ref}: 404, IDOR 403, raw_payload hanya owner
"""

import hashlib
import hmac
import json
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app
from src.core.auth.auth import create_user
from src.core.auth.auth_keys import get_user_by_id
from src.core.db.db_engine import get_engine
from src.core.db.models import VipUpgrade

_SECRET = "test_secret_billing_0123456789"

# Rate-limit scope "webhooks" default 5/s per-IP — longgar untuk test loop.
_ENV = patch.dict(
    os.environ,
    {"RATE_LIMIT_WEBHOOKS_BURST": "1000", "RATE_LIMIT_WEBHOOKS_SUSTAINED": "5000"},
)


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _hdr(user: dict) -> dict:
    return {"X-API-Key": user["api_key"]}


def _sign(body: bytes, secret: str = _SECRET) -> dict:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Signature": f"sha256={sig}", "Content-Type": "application/json"}


def _wh(payload: dict, secret: str = _SECRET) -> dict:
    body = json.dumps(payload).encode()
    return {"body": body, "headers": _sign(body, secret)}


def _ref(tag: str) -> str:
    return f"test-bill-{tag}-{uuid.uuid4().hex[:8]}"


class _DbCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        VipUpgrade.__table__.create(get_engine(), checkfirst=True)
        tag = uuid.uuid4().hex[:8]
        cls.owner = create_user(f"bill_owner_{tag}", "owner")
        cls.plain = create_user(f"bill_plain_{tag}", "user")
        cls.other = create_user(f"bill_other_{tag}", "user")


class TestWebhookHMAC(_DbCase):
    """HMAC fail-closed."""

    def test_tanpa_secret_503(self):
        body = json.dumps({"uid": self.plain["id"], "external_ref": _ref("ns")}).encode()
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": ""}):
            r = _client().post("/webhooks/vip-upgrade", content=body, headers=_sign(body, "x"))
        self.assertEqual(r.status_code, 503)

    def test_sig_salah_401(self):
        req = _wh({"uid": self.plain["id"], "external_ref": _ref("bad")}, secret="salah")
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            r = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
        self.assertEqual(r.status_code, 401)

    def test_sig_kosong_401(self):
        body = json.dumps({"uid": self.plain["id"], "external_ref": _ref("nosig")}).encode()
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            r = _client().post(
                "/webhooks/vip-upgrade",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(r.status_code, 401)

    def test_uid_kosong_400(self):
        req = _wh({"uid": "", "external_ref": _ref("nouid")})
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            r = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
        self.assertEqual(r.status_code, 400)

    def test_status_invalid_400(self):
        req = _wh({"uid": self.plain["id"], "external_ref": _ref("st"), "status": "lunas"})
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            r = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
        self.assertEqual(r.status_code, 400)

    def test_amount_salah_400(self):
        req = _wh({"uid": self.plain["id"], "external_ref": _ref("amt"), "amount_cents": 999})
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            r = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
        self.assertEqual(r.status_code, 400)


class TestWebhookStatusFlow(_DbCase):
    """pending → success: history tercatat, vip hanya aktif di success."""

    @staticmethod
    def _row(ref: str) -> VipUpgrade | None:
        from sqlalchemy.orm import sessionmaker

        with sessionmaker(bind=get_engine())() as db:
            return db.query(VipUpgrade).filter(VipUpgrade.external_ref == ref).first()

    def test_pending_tanpa_vip_lalu_success(self):
        ref = _ref("flow")
        uid = self.other["id"]
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            # 1) pending
            req = _wh({"uid": uid, "external_ref": ref, "status": "pending", "provider": "paymock"})
            r = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "pending")
            self.assertIsNone(r.json().get("role"))
            # history ada, status pending
            row = self._row(ref)
            self.assertIsNotNone(row)
            self.assertEqual(row.status, "pending")
            self.assertIsNone(row.paid_at)
            # user belum vip
            self.assertEqual(get_user_by_id(uid)["role"], "user")
            # 2) success (replay ref yang sama)
            req2 = _wh({"uid": uid, "external_ref": ref, "status": "success", "provider": "paymock"})
            r2 = _client().post("/webhooks/vip-upgrade", content=req2["body"], headers=req2["headers"])
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r2.json()["payment_status"], "success")
            row2 = self._row(ref)
            self.assertEqual(row2.status, "success")
            self.assertIsNotNone(row2.paid_at)
            self.assertEqual(get_user_by_id(uid)["role"], "vip")

    def test_replay_success_idempotent(self):
        ref = _ref("idem")
        uid = self.other["id"]
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            last = None
            for _ in range(3):
                req = _wh({"uid": uid, "external_ref": ref, "status": "success"})
                last = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
                self.assertEqual(last.status_code, 200)
            self.assertEqual(last.json()["status"], "already")
            self.assertEqual(get_user_by_id(uid)["role"], "vip")

    def test_failed_tidak_jadi_vip(self):
        ref = _ref("fail")
        uid = self.plain["id"]
        with patch.dict(os.environ, {"VIP_WEBHOOK_SECRET": _SECRET}):
            req = _wh({"uid": uid, "external_ref": ref, "status": "failed"})
            r = _client().post("/webhooks/vip-upgrade", content=req["body"], headers=req["headers"])
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "failed")
            self.assertEqual(get_user_by_id(uid)["role"], "user")
            self.assertEqual(self._row(ref).status, "failed")


class TestBillingHistoryEndpoint(_DbCase):
    """GET /billing/history + detail + status."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ref_pending = _ref("histp")
        cls.ref_sukses = _ref("hists")
        VipUpgrade.__table__.create(get_engine(), checkfirst=True)
        from sqlalchemy.orm import sessionmaker

        with sessionmaker(bind=get_engine())() as db:
            db.add(
                VipUpgrade(
                    user_id=cls.plain["id"],
                    external_ref=cls.ref_pending,
                    amount_cents=1387,
                    status="pending",
                    provider="paymock",
                )
            )
            db.add(
                VipUpgrade(
                    user_id=cls.plain["id"],
                    external_ref=cls.ref_sukses,
                    amount_cents=1387,
                    status="success",
                    provider="paymock",
                )
            )
            db.commit()

    def test_unauth_401(self):
        self.assertIn(_client().get("/billing/history").status_code, (401, 403))

    def test_self_list(self):
        r = _client().get("/billing/history", headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        refs = [i["external_ref"] for i in data["items"]]
        self.assertIn(self.ref_pending, refs)
        self.assertIn(self.ref_sukses, refs)
        self.assertGreaterEqual(data["total"], 2)

    def test_filter_status(self):
        r = _client().get("/billing/history", params={"status": "pending"}, headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 200)
        refs = [i["external_ref"] for i in r.json()["items"]]
        self.assertIn(self.ref_pending, refs)
        self.assertNotIn(self.ref_sukses, refs)

    def test_filter_status_invalid_400(self):
        r = _client().get("/billing/history", params={"status": "nyasar"}, headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 400)

    def test_idor_user_lain_403(self):
        r = _client().get("/billing/history", params={"uid": self.plain["id"]}, headers=_hdr(self.other))
        self.assertEqual(r.status_code, 403)

    def test_owner_bisa_lihat_uid_lain(self):
        r = _client().get("/billing/history", params={"uid": self.plain["id"]}, headers=_hdr(self.owner))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user_id"], self.plain["id"])

    def test_limit_clamp(self):
        r = _client().get("/billing/history", params={"limit": 999}, headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["limit"], 100)

    def test_detail_milik_sendiri(self):
        r = _client().get(f"/billing/history/{self.ref_sukses}", headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["amount_cents"], 1387)
        self.assertIsNone(body["raw_payload"])
        self.assertIn("vip_active", body)

    def test_detail_idor_403(self):
        r = _client().get(f"/billing/history/{self.ref_sukses}", headers=_hdr(self.other))
        self.assertEqual(r.status_code, 403)

    def test_detail_owner_dapat_raw(self):
        r = _client().get(f"/billing/history/{self.ref_sukses}", headers=_hdr(self.owner))
        self.assertEqual(r.status_code, 200)

    def test_detail_404(self):
        r = _client().get("/billing/history/tidak-ada-ref-xyz", headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 404)

    def test_status_endpoint(self):
        r = _client().get(f"/billing/status/{self.ref_pending}", headers=_hdr(self.plain))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "pending")
        self.assertIn("vip_active", body)

    def test_status_unauth_401(self):
        self.assertIn(_client().get(f"/billing/status/{self.ref_pending}").status_code, (401, 403))

    def test_status_idor_403(self):
        r = _client().get(f"/billing/status/{self.ref_sukses}", headers=_hdr(self.other))
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
