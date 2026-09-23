"""Test factories untuk model ORM menggunakan factory_boy.

Fitur roadmap: Fixture & factory (#21) — factory_boy + pytest-factoryboy.
Menyediakan factory untuk semua model ORM utama.
"""

import random
import uuid
from datetime import UTC, datetime

import factory
from factory.alchemy import SQLAlchemyModelFactory

from src.core.db.models import (
    AuditLog,
    BackgroundTask,
    Feedback,
    LogEntry,
    Monologue,
    PendingApproval,
    Plan,
    PlanStep,
    Preferensi,
    Proyek,
    RequestStat,
    RoutingKeyword,
    RoutingLearning,
    ScheduledJob,
    Session,
    SessionMemory,
    ToolFailure,
    User,
)


class _BaseFactory(SQLAlchemyModelFactory):
    """Base factory dengan session SQLAlchemy."""

    class Meta:
        abstract = True
        sqlalchemy_session = None  # di-set via pytest fixture db_session
        sqlalchemy_session_persistence = "commit"


def _gen_uuid() -> str:
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


class SessionFactory(_BaseFactory):
    class Meta:
        model = Session

    id = factory.LazyFunction(_gen_uuid)
    owner_user_id = factory.LazyFunction(_gen_uuid)
    user_id = factory.LazyAttribute(lambda o: o.owner_user_id)
    nama = factory.Faker("sentence", nb_words=3)
    context = factory.Faker("text", max_nb_chars=200)
    agent_type = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    created_at = factory.LazyFunction(_now_utc)
    updated_at = factory.LazyFunction(_now_utc)


class RoutingKeywordFactory(_BaseFactory):
    class Meta:
        model = RoutingKeyword

    agent = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    keyword = factory.Faker("word")
    allowed_tools = factory.LazyFunction(list)


class SessionMemoryFactory(_BaseFactory):
    class Meta:
        model = SessionMemory

    session_id = factory.LazyFunction(_gen_uuid)
    role = factory.Faker("random_element", elements=("user", "assistant", "system"))
    content = factory.Faker("text", max_nb_chars=500)
    timestamp = factory.LazyFunction(_now_utc)


class LogEntryFactory(_BaseFactory):
    class Meta:
        model = LogEntry

    logger_name = factory.Faker("word")
    level = factory.Faker("random_element", elements=("INFO", "WARNING", "ERROR", "DEBUG"))
    message = factory.Faker("text", max_nb_chars=300)
    timestamp = factory.LazyFunction(_now_utc)


class FeedbackFactory(_BaseFactory):
    class Meta:
        model = Feedback

    session_id = factory.LazyFunction(_gen_uuid)
    agent_type = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    rating = factory.Faker("random_int", min=1, max=5)
    comment = factory.Faker("sentence", nb_words=8)
    corrected_agent = None
    created_at = factory.LazyFunction(_now_utc)


class ToolFailureFactory(_BaseFactory):
    class Meta:
        model = ToolFailure

    tool_name = factory.Faker("random_element", elements=("tulis_kode", "baca_file", "cari_web", "jalankan_python"))
    keyword = factory.Faker("word")
    error_message = factory.Faker("sentence", nb_words=6)
    agent_type = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    session_id = factory.LazyFunction(_gen_uuid)
    created_at = factory.LazyFunction(_now_utc)


class RoutingLearningFactory(_BaseFactory):
    class Meta:
        model = RoutingLearning

    source = factory.Faker("random_element", elements=("feedback", "tool_failure", "manual"))
    user_input = factory.Faker("sentence", nb_words=8)
    old_agent = factory.Faker("random_element", elements=("casual_agent", "coder_agent", "admin_agent"))
    new_agent = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    keyword = factory.Faker("word")
    tools = factory.LazyFunction(list)
    created_at = factory.LazyFunction(_now_utc)


class MonologueFactory(_BaseFactory):
    class Meta:
        model = Monologue

    id = factory.LazyFunction(_gen_uuid)
    user_id = factory.LazyFunction(_gen_uuid)
    agent_type = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    role = factory.Faker("random_element", elements=("summary", "monologue", "context"))
    content = factory.Faker("text", max_nb_chars=1000)
    timestamp = factory.LazyFunction(_now_utc)


class UserFactory(_BaseFactory):
    class Meta:
        model = User

    id = factory.LazyFunction(_gen_uuid)
    name = factory.Faker("name")
    key_hash = factory.Faker("sha256")
    prefix = factory.Faker("pystr_format", string_format="fr_????")
    role = factory.Faker("random_element", elements=("user", "admin"))
    active = True
    created_at = factory.LazyFunction(_now_utc)
    old_key_hash = None
    old_prefix = None
    old_key_expires_at = None


class PreferensiFactory(_BaseFactory):
    class Meta:
        model = Preferensi

    user_id = factory.Faker("word")
    key = factory.Faker("word")
    value = factory.Faker("pystr", min_chars=5, max_chars=50)
    updated_at = factory.LazyFunction(_now_utc)


class ProyekFactory(_BaseFactory):
    class Meta:
        model = Proyek

    user_id = factory.Faker("word")
    nama = factory.Faker("sentence", nb_words=3)
    goal = factory.Faker("sentence", nb_words=8)
    status = factory.Faker("random_element", elements=("aktif", "selesai", "dihentikan"))
    catatan = factory.Faker("text", max_nb_chars=100)
    updated_at = factory.LazyFunction(_now_utc)


class PlanFactory(_BaseFactory):
    class Meta:
        model = Plan

    id = factory.LazyFunction(_gen_uuid)
    owner_user_id = factory.LazyFunction(_gen_uuid)
    session_id = factory.LazyFunction(_gen_uuid)
    judul = factory.Faker("sentence", nb_words=3)
    tujuan = factory.Faker("sentence", nb_words=8)
    status = factory.Faker("random_element", elements=("aktif", "selesai", "batal"))
    langkah_selesai = factory.LazyAttribute(lambda o: random.randint(0, o.total_langkah))  # noqa: S311
    total_langkah = factory.Faker("random_int", min=1, max=20)
    created_at = factory.LazyFunction(_now_utc)
    updated_at = factory.LazyFunction(_now_utc)


class PlanStepFactory(_BaseFactory):
    class Meta:
        model = PlanStep

    id = factory.LazyFunction(_gen_uuid)
    plan_id = factory.LazyFunction(_gen_uuid)
    urutan = factory.Faker("random_int", min=1, max=20)
    deskripsi = factory.Faker("sentence", nb_words=8)
    status = factory.Faker("random_element", elements=("pending", "berjalan", "selesai", "gagal"))
    hasil = factory.Faker("text", max_nb_chars=300)
    created_at = factory.LazyFunction(_now_utc)
    updated_at = factory.LazyFunction(_now_utc)


class PendingApprovalFactory(_BaseFactory):
    class Meta:
        model = PendingApproval

    id = factory.LazyFunction(_gen_uuid)
    tool = factory.Faker("random_element", elements=("tulis_kode", "jalankan_python", "panggil_mcp"))
    args = factory.Faker("json")
    session_id = factory.LazyFunction(_gen_uuid)
    owner_user_id = factory.LazyFunction(_gen_uuid)
    user_id = factory.LazyAttribute(lambda o: o.owner_user_id)
    status = factory.Faker("random_element", elements=("pending", "approved", "denied"))
    created_at = factory.LazyFunction(_now_utc)
    decided_at = None


class AuditLogFactory(_BaseFactory):
    class Meta:
        model = AuditLog

    ts = factory.LazyFunction(_now_utc)
    actor = factory.Faker("name")
    action = factory.Faker("random_element", elements=("create", "read", "update", "delete", "app_run"))
    details = factory.Faker("json")
    prev_hash = factory.Faker("sha256")
    hash = factory.Faker("sha256")


class ScheduledJobFactory(_BaseFactory):
    class Meta:
        model = ScheduledJob

    id = factory.LazyFunction(_gen_uuid)
    name = factory.Faker("sentence", nb_words=3)
    prompt = factory.Faker("sentence", nb_words=12)
    interval_detik = factory.Faker("random_int", min=60, max=86400)
    daily_at = None
    session_id = factory.LazyFunction(_gen_uuid)
    owner_user_id = factory.LazyFunction(_gen_uuid)
    user_id = factory.LazyAttribute(lambda o: o.owner_user_id)
    allowed_tools = factory.LazyFunction(lambda: "[]")
    approval_policy = "deny_all"
    enabled = True
    last_run = None
    created_at = factory.LazyFunction(_now_utc)


class BackgroundTaskFactory(_BaseFactory):
    class Meta:
        model = BackgroundTask

    kind = factory.Faker("random_element", elements=("chat", "summary", "cleanup"))
    status = factory.Faker("random_element", elements=("pending", "running", "done", "failed"))
    input = factory.Faker("sentence", nb_words=10)
    session_id = factory.LazyFunction(_gen_uuid)
    result = None
    error = None
    created_at = factory.LazyFunction(_now_utc)
    updated_at = factory.LazyFunction(_now_utc)


class RequestStatFactory(_BaseFactory):
    class Meta:
        model = RequestStat

    ts = factory.LazyFunction(_now_utc)
    session_id = factory.LazyFunction(_gen_uuid)
    agent_type = factory.Faker("random_element", elements=("coder_agent", "admin_agent", "casual_agent"))
    tools = factory.Faker("sentence", nb_words=3)
    latency_s = factory.Faker("pyfloat", min_value=0.1, max_value=10.0)
    prompt_tokens = factory.Faker("random_int", min=0, max=5000)
    completion_tokens = factory.Faker("random_int", min=0, max=5000)
    total_tokens = factory.LazyAttribute(lambda o: o.prompt_tokens + o.completion_tokens)
    success = True
    model = factory.Faker("random_element", elements=("gpt-4o", "gpt-4o-mini", "gemini-2.0-flash", "llama-3.3-70b"))
    cost_usd = factory.LazyAttribute(
        lambda o: round((o.prompt_tokens / 1_000_000 * 2.5) + (o.completion_tokens / 1_000_000 * 10.0), 6)
    )
