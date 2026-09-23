"""Regression test endpoint control-plane di src/api/routes_control.py.

Cakup:
- fail-closed auth: anonim 401, role user (bukan admin) ditolak 403 endpoint admin
- POST /keywords: choke-point sanitize agent invalid -> 400; audit gagal -> rollback + 500
- DELETE /keywords: agent invalid -> 400 tanpa sentuh remove_keyword; tidak ada -> 404
- GET /plans + /plans/{id}: owner-scoping (IDOR 403), 404 tak dikenal, limit clamp, steps
- PATCH /plans/{id}: status aktif/selesai/batal, 409 selesai -> batal, IDOR 403
- DELETE /sessions/{id}: owner-scoped, cascade hapus session_memory, 404/403
- DELETE /templates/{name}: bawaan -> 400, tak dikenal -> 404, kustom -> 200 hilang
"""

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app
from src.core.auth.auth import create_user
from src.core.db.db_engine import get_engine
from src.core.db.models import Plan, PlanStep, Session, SessionMemory
from src.core.llm import templates as prompt_templates


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _hdr(user: dict) -> dict:
    return {"X-API-Key": user["api_key"]}


class _DbCase(unittest.TestCase):
    """Setup user + tabel plans sekali per kelas."""

    @classmethod
    def setUpClass(cls):
        engine = get_engine()
        Plan.__table__.create(engine, checkfirst=True)
        PlanStep.__table__.create(engine, checkfirst=True)
        Session.__table__.create(engine, checkfirst=True)
        SessionMemory.__table__.create(engine, checkfirst=True)
        tag = uuid.uuid4().hex[:8]
        cls.user_a = create_user(f"ctrl_a_{tag}", "user")
        cls.user_b = create_user(f"ctrl_b_{tag}", "user")
        cls.admin = create_user(f"ctrl_admin_{tag}", "admin")
        cls.owner = create_user(f"ctrl_owner_{tag}", "owner")

    @staticmethod
    def _make_plan(owner_user_id: str, judul: str, status: str = "aktif", with_steps: bool = False) -> str:
        from sqlalchemy.orm import sessionmaker

        with sessionmaker(bind=get_engine())() as db:
            plan = Plan(
                owner_user_id=owner_user_id,
                judul=judul,
                tujuan=f"tujuan {judul}",
                status=status,
                total_langkah=1 if with_steps else 0,
            )
            db.add(plan)
            db.flush()
            if with_steps:
                db.add(PlanStep(plan_id=plan.id, urutan=1, deskripsi="langkah satu", status="selesai", hasil="ok"))
                db.add(PlanStep(plan_id=plan.id, urutan=2, deskripsi="langkah dua", status="pending"))
            db.commit()
            return plan.id


class TestUnauthFailClosed(_DbCase):
    """Semua endpoint baru wajib tolak tanpa API key."""

    def test_post_keywords_tanpa_key(self):
        r = _client().post("/keywords", json={"agent": "coder_agent", "keyword": "x"})
        self.assertIn(r.status_code, (401, 403))

    def test_delete_keywords_tanpa_key(self):
        r = _client().delete("/keywords", params={"agent": "coder_agent", "keyword": "x"})
        self.assertIn(r.status_code, (401, 403))

    def test_get_plans_tanpa_key(self):
        self.assertIn(_client().get("/plans").status_code, (401, 403))

    def test_get_plan_detail_tanpa_key(self):
        self.assertIn(_client().get("/plans/any-id").status_code, (401, 403))

    def test_delete_template_tanpa_key(self):
        self.assertIn(_client().delete("/templates/ringkas").status_code, (401, 403))

    def test_delete_session_tanpa_key(self):
        self.assertIn(_client().delete("/sessions/some-id").status_code, (401, 403))

    def test_patch_plan_tanpa_key(self):
        r = _client().patch("/plans/some-id", json={"status": "batal"})
        self.assertIn(r.status_code, (401, 403))


class TestAdminOnly(_DbCase):
    """Endpoint admin: role user -> 403, admin -> lanjut validasi."""

    def test_post_keywords_role_user_ditolak(self):
        r = _client().post("/keywords", json={"agent": "coder_agent", "keyword": "zxc"}, headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 403)

    def test_delete_keywords_role_user_ditolak(self):
        r = _client().delete("/keywords", params={"agent": "coder_agent", "keyword": "zxc"}, headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 403)

    def test_delete_template_role_user_ditolak(self):
        r = _client().delete("/templates/apa_saja", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 403)

    def test_owner_juga_dapat_akses_admin(self):
        r = _client().post("/keywords", json={"agent": "invalid_agent_x", "keyword": "k"}, headers=_hdr(self.owner))
        self.assertEqual(r.status_code, 400)


class TestCreateKeyword(_DbCase):
    """POST /keywords: validasi + choke-point + rollback audit."""

    def test_agent_invalid_fail_closed_400(self):
        with patch("src.api.routes_control.add_keyword_with_tools") as mock_add:
            r = _client().post(
                "/keywords",
                json={"agent": "evil_agent", "keyword": "hack", "allowed_tools": ["jalankan_python"]},
                headers=_hdr(self.admin),
            )
        self.assertEqual(r.status_code, 400)
        mock_add.assert_not_called()

    def test_body_kosong_400(self):
        r = _client().post("/keywords", json={}, headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 400)

    def test_allowed_tools_bukan_list_400(self):
        r = _client().post(
            "/keywords",
            json={"agent": "coder_agent", "keyword": "k", "allowed_tools": "tulis_kode"},
            headers=_hdr(self.admin),
        )
        self.assertEqual(r.status_code, 400)

    def test_keyword_terlalu_panjang_400(self):
        r = _client().post("/keywords", json={"agent": "coder_agent", "keyword": "x" * 101}, headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 400)

    def test_body_bukan_json_400(self):
        r = _client().post(
            "/keywords",
            content=b"bukan-json",
            headers={**_hdr(self.admin), "Content-Type": "application/json"},
        )
        self.assertEqual(r.status_code, 400)

    def test_sukses_sanitasi_tools_terpotong(self):
        with (
            patch("src.api.routes_control.add_keyword_with_tools", return_value=True) as mock_add,
            patch("src.api.routes_control.append_audit"),
            patch("src.api.routes_control.invalidate_routing_cache"),
        ):
            r = _client().post(
                "/keywords",
                json={
                    "agent": "coder_agent",
                    "keyword": "  BUGFIX ",
                    "allowed_tools": ["jalankan_python", "format_disk"],
                },
                headers=_hdr(self.admin),
            )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["keyword"], "bugfix")
        self.assertEqual(body["allowed_tools"], ["jalankan_python"])
        mock_add.assert_called_once_with("coder_agent", "bugfix", ["jalankan_python"])

    def test_gagal_simpan_400(self):
        with (
            patch("src.api.routes_control.add_keyword_with_tools", return_value=False),
            patch("src.api.routes_control.append_audit"),
        ):
            r = _client().post("/keywords", json={"agent": "coder_agent", "keyword": "k"}, headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 400)

    def test_audit_gagal_rollback_500(self):
        with (
            patch("src.api.routes_control.add_keyword_with_tools", return_value=True),
            patch("src.api.routes_control.append_audit", side_effect=RuntimeError("chain rusak")),
            patch("src.api.routes_control.remove_keyword", return_value=True) as mock_rm,
            patch("src.api.routes_control.invalidate_routing_cache") as mock_inv,
        ):
            r = _client().post(
                "/keywords", json={"agent": "coder_agent", "keyword": "rollback-kw"}, headers=_hdr(self.admin)
            )
        self.assertEqual(r.status_code, 500)
        self.assertIn("rollback", r.json()["detail"].lower())
        mock_rm.assert_called_once_with("coder_agent", "rollback-kw")
        self.assertGreaterEqual(mock_inv.call_count, 2)


class TestDeleteKeyword(_DbCase):
    """DELETE /keywords: agent divalidasi sebelum remove_keyword."""

    def test_agent_invalid_400_tanpa_sentuh_db(self):
        with patch("src.api.routes_control.remove_keyword") as mock_rm:
            r = _client().delete(
                "/keywords",
                params={"agent": "ghost_agent", "keyword": "x"},
                headers=_hdr(self.admin),
            )
        self.assertEqual(r.status_code, 400)
        mock_rm.assert_not_called()

    def test_param_kosong_400(self):
        r = _client().delete("/keywords", params={"agent": "  ", "keyword": ""}, headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 400)

    def test_tidak_ada_404(self):
        with (
            patch("src.api.routes_control.remove_keyword", return_value=False),
            patch("src.api.routes_control.append_audit"),
        ):
            r = _client().delete(
                "/keywords",
                params={"agent": "coder_agent", "keyword": "tak-ada"},
                headers=_hdr(self.admin),
            )
        self.assertEqual(r.status_code, 404)

    def test_sukses_200_keyword_lowercased(self):
        with (
            patch("src.api.routes_control.remove_keyword", return_value=True) as mock_rm,
            patch("src.api.routes_control.append_audit"),
            patch("src.api.routes_control.invalidate_routing_cache"),
        ):
            r = _client().delete(
                "/keywords",
                params={"agent": "admin_agent", "keyword": " DRAF "},
                headers=_hdr(self.admin),
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["keyword"], "draf")
        mock_rm.assert_called_once_with("admin_agent", "draf")

    def test_audit_gagal_tetap_200_warning(self):
        with (
            patch("src.api.routes_control.remove_keyword", return_value=True),
            patch("src.api.routes_control.append_audit", side_effect=RuntimeError("chain rusak")),
            patch("src.api.routes_control.invalidate_routing_cache"),
        ):
            r = _client().delete(
                "/keywords", params={"agent": "coder_agent", "keyword": "kode"}, headers=_hdr(self.admin)
            )
        self.assertEqual(r.status_code, 200)


class TestPlans(_DbCase):
    """GET /plans & /plans/{id}: owner-scoping, 404, clamp, steps."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan_a = cls._make_plan(cls.user_a["id"], "rencana milik a", with_steps=True)
        cls.plan_a_selesai = cls._make_plan(cls.user_a["id"], "rencana selesai a", status="selesai")
        cls.plan_b = cls._make_plan(cls.user_b["id"], "rencana milik b")

    def test_list_hanya_milik_sendiri(self):
        r = _client().get("/plans", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 200)
        ids = [p["id"] for p in r.json()["plans"]]
        self.assertIn(self.plan_a, ids)
        self.assertIn(self.plan_a_selesai, ids)
        self.assertNotIn(self.plan_b, ids)
        self.assertEqual(r.json()["count"], len(ids))

    def test_list_limit_clamp(self):
        r = _client().get("/plans", params={"limit": 999}, headers=_hdr(self.user_b))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["limit"], 50)

    def test_list_filter_status(self):
        r = _client().get("/plans", params={"status": "selesai"}, headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["plans"][0]["id"], self.plan_a_selesai)

    def test_detail_milik_sendiri_dengan_steps(self):
        r = _client().get(f"/plans/{self.plan_a}", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["judul"], "rencana milik a")
        self.assertEqual([s["urutan"] for s in body["steps"]], [1, 2])
        self.assertEqual(body["steps"][0]["status"], "selesai")

    def test_detail_idor_user_lain_403(self):
        r = _client().get(f"/plans/{self.plan_a}", headers=_hdr(self.user_b))
        self.assertEqual(r.status_code, 403)

    def test_detail_tidak_dikenal_404(self):
        r = _client().get("/plans/00000000-0000-0000-0000-000000000000", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 404)

    def test_detail_owner_role_boleh_semua(self):
        r = _client().get(f"/plans/{self.plan_b}", headers=_hdr(self.owner))
        self.assertEqual(r.status_code, 200)

    def test_list_user_b_hanya_rencana_b(self):
        r = _client().get("/plans", headers=_hdr(self.user_b))
        ids = [p["id"] for p in r.json()["plans"]]
        self.assertEqual(ids, [self.plan_b])


class TestTemplateDelete(_DbCase):
    """DELETE /templates/{name}: bawaan 400, tak dikenal 404, kustom 200."""

    def setUp(self):
        prompt_templates.reset_templates()

    def tearDown(self):
        prompt_templates.reset_templates()

    def test_template_bawaan_400(self):
        r = _client().delete("/templates/ringkas", headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 400)
        self.assertIsNotNone(prompt_templates.get_template("ringkas"))

    def test_template_tidak_dikenal_404(self):
        r = _client().delete("/templates/template_hilang_xyz", headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 404)

    def test_template_kustom_200_lalu_hilang(self):
        prompt_templates.register_template("uji_kustom_ctrl", "halo {nama}")
        r = _client().delete("/templates/uji_kustom_ctrl", headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertIsNone(prompt_templates.get_template("uji_kustom_ctrl"))

    def test_audit_gagal_tetap_200(self):
        prompt_templates.register_template("uji_kustom_audit", "isi")
        with patch("src.api.routes_control.append_audit", side_effect=RuntimeError("chain rusak")):
            r = _client().delete("/templates/uji_kustom_audit", headers=_hdr(self.admin))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(prompt_templates.get_template("uji_kustom_audit"))


class TestPlanPatch(_DbCase):
    """PATCH /plans/{id}: ubah status, owner-scoped, guard 409."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan_aktif = cls._make_plan(cls.user_a["id"], "rencana aktif patch")
        cls.plan_selesai = cls._make_plan(cls.user_a["id"], "rencana sudah selesai", status="selesai")

    def test_unauth_401(self):
        r = _client().patch(f"/plans/{self.plan_aktif}", json={"status": "batal"})
        self.assertIn(r.status_code, (401, 403))

    def test_idor_403(self):
        r = _client().patch(f"/plans/{self.plan_aktif}", json={"status": "batal"}, headers=_hdr(self.user_b))
        self.assertEqual(r.status_code, 403)

    def test_tidak_dikenal_404(self):
        r = _client().patch(
            "/plans/00000000-0000-0000-0000-000000000000",
            json={"status": "batal"},
            headers=_hdr(self.user_a),
        )
        self.assertEqual(r.status_code, 404)

    def test_status_invalid_400(self):
        r = _client().patch(f"/plans/{self.plan_aktif}", json={"status": "dihancurkan"}, headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 400)

    def test_body_bukan_json_400(self):
        r = _client().patch(
            f"/plans/{self.plan_aktif}",
            content=b"xxx",
            headers={**_hdr(self.user_a), "Content-Type": "application/json"},
        )
        self.assertEqual(r.status_code, 400)

    def test_sukses_ke_batal(self):
        r = _client().patch(f"/plans/{self.plan_aktif}", json={"status": "batal"}, headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "batal")
        r2 = _client().get(f"/plans/{self.plan_aktif}", headers=_hdr(self.user_a))
        self.assertEqual(r2.json()["status"], "batal")

    def test_selesai_tidak_bisa_dibatalkan_409(self):
        r = _client().patch(f"/plans/{self.plan_selesai}", json={"status": "batal"}, headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 409)


class TestSessionDelete(_DbCase):
    """DELETE /sessions/{id}: hapus session + memonya, owner-scoped."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.session_id = f"ctrl-sess-{uuid.uuid4().hex[:8]}"
        cls.session_lain = f"ctrl-sess-lain-{uuid.uuid4().hex[:8]}"
        from sqlalchemy.orm import sessionmaker

        with sessionmaker(bind=get_engine())() as db:
            db.add(
                Session(
                    id=cls.session_id,
                    owner_user_id=cls.user_a["id"],
                    user_id="default",
                    nama="session uji hapus",
                )
            )
            db.add(Session(id=cls.session_lain, owner_user_id=cls.user_b["id"], user_id="default"))
            db.add(
                SessionMemory(session_id=cls.session_id, owner_user_id=cls.user_a["id"], role="user", content="halo")
            )
            db.commit()

    @staticmethod
    def _session_exists(session_id: str) -> bool:
        from sqlalchemy.orm import sessionmaker

        with sessionmaker(bind=get_engine())() as db:
            return db.query(Session).filter(Session.id == session_id).first() is not None

    def test_unauth_401(self):
        self.assertIn(_client().delete(f"/sessions/{self.session_id}").status_code, (401, 403))

    def test_tidak_dikenal_404(self):
        r = _client().delete("/sessions/00000000-0000-0000-0000-000000000000", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 404)

    def test_idor_403_session_lain_tetap_ada(self):
        r = _client().delete(f"/sessions/{self.session_lain}", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self._session_exists(self.session_lain))

    def test_sukses_hapus_session_dan_memory(self):
        sid = f"ctrl-sess-del-{uuid.uuid4().hex[:8]}"
        from sqlalchemy.orm import sessionmaker

        with sessionmaker(bind=get_engine())() as db:
            db.add(Session(id=sid, owner_user_id=self.user_a["id"], user_id="default"))
            db.add(SessionMemory(session_id=sid, owner_user_id=self.user_a["id"], role="assistant", content="pesan"))
            db.commit()
        r = _client().delete(f"/sessions/{sid}", headers=_hdr(self.user_a))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertFalse(self._session_exists(sid))
        with sessionmaker(bind=get_engine())() as db:
            sisa = db.query(SessionMemory).filter(SessionMemory.session_id == sid).count()
        self.assertEqual(sisa, 0)


if __name__ == "__main__":
    unittest.main()
