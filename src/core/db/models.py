import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


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
