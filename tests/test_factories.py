"""Test factories: verifikasi factory_boy menghasilkan instance model yang valid.

Fitur roadmap: Fixture & factory (#21) — factory_boy + pytest-factoryboy.
Unittest, cepat, tanpa LLM/infra — pakai build() (tanpa persist).
"""

import unittest

from tests import factories as f


class TestFactoriesBuild(unittest.TestCase):
    """Semua factory dapat build() instance model dengan atribut valid."""

    def test_session_factory(self):
        s = f.SessionFactory.build()
        self.assertIsNotNone(s.id)
        self.assertIsNotNone(s.owner_user_id)
        self.assertIn(s.agent_type, ("coder_agent", "admin_agent", "casual_agent"))
        self.assertTrue(s.nama)

    def test_routing_keyword_factory(self):
        kw = f.RoutingKeywordFactory.build()
        self.assertTrue(kw.keyword)
        self.assertIn(kw.agent, ("coder_agent", "admin_agent", "casual_agent"))
        self.assertIsInstance(kw.allowed_tools, list)

    def test_user_factory(self):
        u = f.UserFactory.build(role="admin")
        self.assertIsNotNone(u.id)
        self.assertEqual(u.role, "admin")
        self.assertTrue(u.prefix.startswith("fr_"))
        self.assertTrue(u.active)

    def test_feedback_factory(self):
        fb = f.FeedbackFactory.build(rating=5)
        self.assertTrue(fb.session_id)
        self.assertEqual(fb.rating, 5)
        self.assertIn(fb.agent_type, ("coder_agent", "admin_agent", "casual_agent"))

    def test_request_stat_factory(self):
        rs = f.RequestStatFactory.build(prompt_tokens=100, completion_tokens=50)
        self.assertEqual(rs.prompt_tokens, 100)
        self.assertEqual(rs.completion_tokens, 50)
        self.assertEqual(rs.total_tokens, 150)
        self.assertGreaterEqual(rs.cost_usd, 0)

    def test_audit_log_factory(self):
        al = f.AuditLogFactory.build()
        self.assertTrue(al.action)
        self.assertTrue(al.hash)
        self.assertTrue(al.prev_hash)

    def test_plan_factory(self):
        plan = f.PlanFactory.build(status="aktif")
        self.assertIsNotNone(plan.id)
        self.assertTrue(plan.judul)
        self.assertTrue(plan.tujuan)
        self.assertIn(plan.status, ("aktif", "selesai", "batal"))
        self.assertGreater(plan.total_langkah, 0)
        self.assertLessEqual(plan.langkah_selesai, plan.total_langkah)

    def test_plan_step_factory(self):
        step = f.PlanStepFactory.build(urutan=2, status="selesai")
        self.assertIsNotNone(step.id)
        self.assertTrue(step.plan_id)
        self.assertEqual(step.urutan, 2)
        self.assertIn(step.status, ("pending", "berjalan", "selesai", "gagal"))
        self.assertTrue(step.deskripsi)

    def test_independent_instances(self):
        s1 = f.SessionFactory.build(agent_type="coder_agent")
        s2 = f.SessionFactory.build(agent_type="admin_agent")
        u1 = f.UserFactory.build()
        u2 = f.UserFactory.build()
        self.assertNotEqual(s1.id, s2.id)
        self.assertNotEqual(u1.id, u2.id)
        self.assertEqual(s1.agent_type, "coder_agent")
        self.assertEqual(s2.agent_type, "admin_agent")


if __name__ == "__main__":
    unittest.main()
