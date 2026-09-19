import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

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
    context = Column(Text, nullable=True)
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
    content = Column(Text, nullable=False)
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
    content = Column(Text, nullable=False)
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


class Preferensi(Base):
    __tablename__ = "preferensi"
    user_id = Column(String(36), nullable=False, server_default="default")
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (PrimaryKeyConstraint("user_id", "key", name="preferensi_user_pkey"),)


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
    args = Column(Text, nullable=False, server_default="")
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
    prompt = Column(Text, nullable=False)
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
    input = Column(Text, nullable=False, server_default="")
    session_id = Column(String(100), nullable=False, server_default="")
    owner_user_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False, server_default="default")
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="NOW()")
    updated_at = Column(DateTime, nullable=False, server_default="NOW()")


class RequestStat(Base):
    __tablename__ = "request_stats"
    id = Column(String(36), primary_key=True)
    ts = Column(DateTime, nullable=False, server_default="NOW()")
    session_id = Column(String(100), nullable=False, server_default="")
    agent_type = Column(String(50), nullable=False, server_default="")
    tools = Column(Text, nullable=False, server_default="")
    latency_s = Column(Float, nullable=False, server_default="0")
    prompt_tokens = Column(Integer, nullable=False, server_default="0")
    completion_tokens = Column(Integer, nullable=False, server_default="0")
    total_tokens = Column(Integer, nullable=False, server_default="0")
    success = Column(Boolean, nullable=False, server_default="true")
