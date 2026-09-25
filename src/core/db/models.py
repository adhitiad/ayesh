import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, Numeric, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from src.core.db.encryption import EncryptedText

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# ─── Existing ORM models ────────────────────────────────────────────


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    owner_user_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True, default="default")
    nama = Column(String(200), nullable=True)
    context = Column(EncryptedText, nullable=True)
    agent_type = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RoutingKeyword(Base):
    __tablename__ = "routing_keywords"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, index=True, default="default")
    agent = Column(String(50), nullable=False, index=True)
    keyword = Column(String(100), nullable=False, index=True)
    allowed_tools = Column(JSONB, default=list, nullable=True)


class SessionMemory(Base):
    __tablename__ = "session_memory"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    session_id = Column(String(100), nullable=False, index=True)
    owner_user_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(EncryptedText, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class LogEntry(Base):
    __tablename__ = "logs"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    logger_name = Column(String(100))
    level = Column(String(20))
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    session_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(50))
    rating = Column(Integer)
    comment = Column(String(500))
    corrected_agent = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ToolFailure(Base):
    __tablename__ = "tool_failures"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    tool_name = Column(String(50), nullable=False, index=True)
    keyword = Column(String(100), nullable=True, index=True)
    error_message = Column(Text)
    agent_type = Column(String(50))
    session_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class RoutingLearning(Base):
    __tablename__ = "routing_learnings"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    source = Column(String(50), nullable=False)
    user_input = Column(Text)
    old_agent = Column(String(50))
    new_agent = Column(String(50))
    keyword = Column(String(100))
    tools = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class Monologue(Base):
    __tablename__ = "monologues"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(EncryptedText, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


# ─── Raw psycopg2 → ORM models ──────────────────────────────────────


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(128), nullable=False, unique=True)
    prefix = Column(String(10), nullable=False, server_default="")
    role = Column(String(10), nullable=False, server_default="user")
    active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, nullable=False, server_default="NOW()")
    # Rotasi API key: key lama dipertahankan valid selama masa tenggang (grace).
    old_key_hash = Column(String(128), nullable=True)
    old_prefix = Column(String(20), nullable=True)
    old_key_expires_at = Column(DateTime, nullable=True)
    # VIP: paid tier $13.87 — role=vip, metadata opsional.
    vip_since = Column(DateTime, nullable=True)
    vip_expires_at = Column(DateTime, nullable=True)
    vip_ref = Column(String(100), nullable=True)
    vip_amount_cents = Column(Integer, nullable=True)


class VipUpgrade(Base):
    """Idempoten webhook vip: external_ref unik, amount $13.87 + pending|sukses history."""

    __tablename__ = "vip_upgrades"
    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    external_ref = Column(String(100), nullable=False, unique=True, index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(10), nullable=False, server_default="USD")
    status = Column(String(20), nullable=False, server_default="pending")
    provider = Column(String(50), nullable=False, server_default="manual")
    raw_payload = Column(Text, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    # Saat hak vip benar-benar diberikan oleh ref ini. NULL = dibayar belum / belum
    # ter-apply → boleh di-upgrade. Terisi = replay tidak boleh memberi hak lagi.
    applied_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default="NOW()")
    created_at = Column(DateTime, nullable=False, server_default="NOW()")


class Preferensi(Base):
    __tablename__ = "preferensi"
    user_id = Column(String(36), nullable=False, server_default="default")
    key = Column(String(100), nullable=False)
    value = Column(EncryptedText, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (PrimaryKeyConstraint("user_id", "key", name="preferensi_user_key_pkey"),)


class Proyek(Base):
    __tablename__ = "proyek"
    user_id = Column(String(36), nullable=False, server_default="default")
    nama = Column(String(100), nullable=False)
    goal = Column(Text, nullable=False, server_default="")
    status = Column(String(20), nullable=False, server_default="aktif")
    catatan = Column(Text, nullable=False, server_default="")
    updated_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (PrimaryKeyConstraint("user_id", "nama", name="proyek_user_pkey"),)


class PendingApproval(Base):
    __tablename__ = "pending_approvals"
    id = Column(String(36), primary_key=True)
    tool = Column(String(100), nullable=False)
    args = Column(EncryptedText, nullable=False, server_default="")
    session_id = Column(String(100), nullable=False, server_default="")
    owner_user_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False, server_default="default")
    status = Column(String(20), nullable=False, server_default="pending")
    created_at = Column(DateTime, nullable=False, server_default="NOW()")
    decided_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(String(36), primary_key=True)
    ts = Column(DateTime, nullable=False, server_default="NOW()")
    actor = Column(String(100), nullable=False, server_default="")
    action = Column(String(50), nullable=False)
    details = Column(Text, nullable=False, server_default="")
    prev_hash = Column(String(64), nullable=False, server_default="GENESIS")
    hash = Column(String(64), nullable=False)


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    prompt = Column(EncryptedText, nullable=False)
    interval_detik = Column(Integer, nullable=True)
    daily_at = Column(String(10), nullable=True)
    session_id = Column(String(100), nullable=False)
    owner_user_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False, server_default="default")
    allowed_tools = Column(Text, nullable=False, server_default="[]")
    approval_policy = Column(String(20), nullable=False, server_default="deny_all")
    enabled = Column(Boolean, nullable=False, server_default="true")
    last_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="NOW()")


class BackgroundTask(Base):
    __tablename__ = "background_tasks"
    id = Column(String(36), primary_key=True)
    kind = Column(String(20), nullable=False, server_default="chat")
    status = Column(String(20), nullable=False, server_default="pending")
    input = Column(EncryptedText, nullable=False, server_default="")
    session_id = Column(String(100), nullable=False, server_default="")
    owner_user_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False, server_default="default")
    result = Column(EncryptedText, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="NOW()")
    updated_at = Column(DateTime, nullable=False, server_default="NOW()")


class UserMemory(Base):
    __tablename__ = "user_memory"
    owner_user_id = Column(String(36), primary_key=True, nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True, default="default")
    fact_type = Column(String(50), nullable=False, index=True)  # 'fact', 'preference', 'decision', 'goal'
    key = Column(String(100), primary_key=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)  # 0.0 - 1.0
    source_session = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (PrimaryKeyConstraint("owner_user_id", "key", name="user_memory_user_key_pkey"),)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False, default=gen_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    judul: Mapped[str] = mapped_column(String(200), nullable=False)
    tujuan: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="aktif", index=True
    )  # aktif, selesai, batal
    langkah_selesai: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_langkah: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlanStep(Base):
    __tablename__ = "plan_steps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False, default=gen_uuid)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    urutan: Mapped[int] = mapped_column(Integer, nullable=False)
    deskripsi: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, berjalan, selesai, gagal
    hasil: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RequestStat(Base):
    __tablename__ = "request_stats"
    id = Column(String(36), primary_key=True)
    ts = Column(DateTime, nullable=False, server_default="NOW()")
    session_id = Column(String(100), nullable=False, server_default="")
    user_id = Column(String(36), nullable=True, server_default=None)
    agent_type = Column(String(50), nullable=False, server_default="")
    tools = Column(Text, nullable=False, server_default="")
    latency_s = Column(Float, nullable=False, server_default="0")
    prompt_tokens = Column(Integer, nullable=False, server_default="0")
    completion_tokens = Column(Integer, nullable=False, server_default="0")
    total_tokens = Column(Integer, nullable=False, server_default="0")
    success = Column(Boolean, nullable=False, server_default="true")
    model = Column(String(100), nullable=False, server_default="")
    cost_usd = Column(Numeric(12, 6), nullable=True)


# ── Per-user LLM configs ──────────────────────────────────────────────


class UserLLMConfig(Base):
    """Satu user punya banyak config LLM, 1 di antaranya default."""

    __tablename__ = "user_llm_configs"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(200), nullable=False)
    api_key = Column(EncryptedText, nullable=True)
    temperature = Column(Float, nullable=True)
    is_default = Column(Boolean, nullable=False, server_default="false")
    is_public = Column(Boolean, nullable=False, server_default="false")
    fallback_config_ids = Column(Text, nullable=True, server_default=None)
    created_at = Column(DateTime, nullable=False, server_default="NOW()")


class UserSkillOverride(Base):
    """User on/off skill tertentu. Tanpa record = default (on)."""

    __tablename__ = "user_skill_overrides"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    skill_name = Column(String(100), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default="true")


class UserMCPOverride(Base):
    """User on/off MCP server tertentu. Tanpa record = default (on)."""

    __tablename__ = "user_mcp_overrides"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    mcp_name = Column(String(100), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default="true")
