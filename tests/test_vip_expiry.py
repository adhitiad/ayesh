"""Regression test masa aktif vip: expired → peran turun, akses premium ditutup.

Cakup (fix require_vip tidak mengecek vip_expires_at):
- verify_key menormalkan role vip yang kedaluwarsa → "user" (lazy demote di DB)
- GET /analytics & /metrics (require_vip) → 403 saat expired, 200 saat aktif
- premium gate POST /users/{uid}/llm-configs → 403 saat expired
- vip tanpa expiry (legacy) & owner tidak terpengaruh
- replay ref yang sudah memberi hak setelah expired → "already", TIDAK grant ulang
- ref BARU saat masih vip → perpanjangan benar-benar terjadi
"""

import os
import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app
from src.core.auth.auth import create_user
from src.core.auth.auth_context import _utcnow
from src.core.auth.auth_keys import get_user_by_id, invalidate_user_cache, set_user_vip, verify_key
from src.core.db.db_engine import get_engine, get_session
from src.core.db.models import User, VipUpgrade

# Scope health (metrics) + default (analytics) + users (llm-configs) longgar untuk loop test.
_ENV = patch.dict(
    os.environ,
    {
        "RATE_LIMIT_HEALTH_BURST": "1000",
        "RATE_LIMIT_HEALTH_SUSTAINED": "5000",
        "RATE_LIMIT_DEFAULT_BURST": "1000",
        "RATE_LIMIT_DEFAULT_SUSTAINED": "5000",
        "RATE_LIMIT_USERS_BURST": "1000",
        "RATE_LIMIT_USERS_SUSTAINED": "5000",
    },
)


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _hdr(user: dict) -> dict:
    return {"X-API-Key": user["api_key"]}


def _set_expires(uid: str, expires, role: str = "vip") -> None:
    """Set role + vip_expires_at langsung di DB (bypass webhook)."""
    with get_session() as db:
        u = db.query(User).filter(User.id == uid).first()
        u.role = role  # type: ignore[assignment]
        u.vip_expires_at = expires  # type: ignore[assignment]
        db.commit()
    invalidate_user_cache(uid)


class TestVipExpiry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        VipUpgrade.__table__.create(get_engine(), checkfirst=True)
        tag = uuid.uuid4().hex[:8]
        cls.owner = create_user(f"exp_owner_{tag}", "owner")
        cls.active = create_user(f"exp_active_{tag}", "user")
        cls.expired = create_user(f"exp_dead_{tag}", "user")
        cls.legacy = create_user(f"exp_legacy_{tag}", "user")
        cls.replay = create_user(f"exp_replay_{tag}", "user")
        set_user_vip(cls.active["id"], external_ref=f"exp-active-{tag}")
        set_user_vip(cls.expired["id"], external_ref=f"exp-dead-{tag}")
        set_user_vip(cls.legacy["id"], external_ref=f"exp-legacy-{tag}")
        set_user_vip(cls.replay["id"], external_ref=f"exp-replay-{tag}")
        _set_expires(cls.expired["id"], _utcnow() - timedelta(hours=1))
        # vip legacy: role=vip tanpa batas waktu (kolom NULL) → tetap aktif
        _set_expires(cls.legacy["id"], None)
        _set_expires(cls.owner["id"], _utcnow() - timedelta(days=1), role="owner")

    def test_vip_aktif_lolos_require_vip(self):
        r = _client().get("/analytics", headers=_hdr(self.active))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(verify_key(self.active["api_key"])["role"], "vip")
        self.assertEqual(_client().get("/users/me", headers=_hdr(self.active)).json()["role"], "vip")

    def test_vip_expired_verify_key_turun_peran(self):
        info = verify_key(self.expired["api_key"])
        self.assertEqual(info["role"], "user")
        self.assertIsNotNone(info.get("vip_expires_at"))
        # lazy demote tertulis di DB; riwayat expiry dipertahankan
        row = get_user_by_id(self.expired["id"])
        self.assertEqual(row["role"], "user")
        self.assertIsNotNone(row["vip_expires_at"])

    def test_vip_expired_ditolak_endpoint_vip(self):
        for path in ("/analytics", "/metrics", "/metrics/prometheus"):
            r = _client().get(path, headers=_hdr(self.expired))
            self.assertEqual(r.status_code, 403, f"{path} harus 403 saat expired, dapat {r.status_code}")

    def test_vip_expired_role_context_user(self):
        r = _client().get("/users/me", headers=_hdr(self.expired))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "user")

    def test_vip_expired_premium_gate_403(self):
        with patch.dict(os.environ, {"VIP_ONLY_MODELS": "gpt-4o"}):
            r = _client().post(
                f"/users/{self.expired['id']}/llm-configs",
                headers=_hdr(self.expired),
                json={"provider": "openai", "model": "gpt-4o"},
            )
        self.assertEqual(r.status_code, 403)
        self.assertIn("premium", r.json()["detail"].lower())

    def test_vip_tanpa_expiry_tetap_aktif(self):
        self.assertEqual(verify_key(self.legacy["api_key"])["role"], "vip")
        r = _client().get("/analytics", headers=_hdr(self.legacy))
        self.assertEqual(r.status_code, 200)

    def test_owner_tidak_terpengaruh_expiry(self):
        self.assertEqual(verify_key(self.owner["api_key"])["role"], "owner")
        r = _client().get("/analytics", headers=_hdr(self.owner))
        self.assertEqual(r.status_code, 200)

    def test_replay_ref_setelah_expired_tidak_grant_ulang(self):
        # ref yang sudah memberi hak direplay setelah masa aktif habis
        from src.core.db.models import VipUpgrade as _VU

        tag = uuid.uuid4().hex[:8]
        old_ref = f"exp-old-{tag}"
        set_user_vip(self.replay["id"], external_ref=old_ref)
        _set_expires(self.replay["id"], _utcnow() - timedelta(days=1))
        self.assertEqual(verify_key(self.replay["api_key"])["role"], "user")

        with get_session() as db:
            row = db.query(_VU).filter(_VU.external_ref == old_ref).first()
            applied = row.applied_at if row else None
        self.assertIsNotNone(applied, "ref lama wajib sudah ditandai applied")

        result = set_user_vip(self.replay["id"], external_ref=old_ref)
        self.assertTrue(result.get("already"))
        self.assertEqual(get_user_by_id(self.replay["id"])["role"], "user")

    def test_ref_baru_perpanjang_vip(self):
        before = get_user_vip_expiry(self.active["id"])
        new_ref = f"exp-renew-{uuid.uuid4().hex[:8]}"
        result = set_user_vip(self.active["id"], external_ref=new_ref)
        self.assertFalse(result.get("already"))
        after = get_user_vip_expiry(self.active["id"])
        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        self.assertGreater(after, before)
        self.assertEqual(get_user_by_id(self.active["id"])["role"], "vip")


def get_user_vip_expiry(uid: str):
    row = get_user_by_id(uid)
    val = (row or {}).get("vip_expires_at")
    if not val:
        return None
    from datetime import datetime

    return datetime.fromisoformat(val)


if __name__ == "__main__":
    unittest.main()
