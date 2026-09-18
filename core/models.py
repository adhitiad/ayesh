from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(String(36), primary_key=True, default=gen_uuid)
    nama = Column(String(200), nullable=True)
    context = Column(Text, nullable=True)
    agent_type = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RoutingKeyword(Base):
    __tablename__ = 'routing_keywords'
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent = Column(String(50), nullable=False, index=True)
    keyword = Column(String(100), nullable=False, index=True)
    allowed_tools = Column(JSONB, default=list, nullable=True)

class SessionMemory(Base):
    __tablename__ = 'session_memory'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class LogEntry(Base):
    __tablename__ = 'logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    logger_name = Column(String(100))
    level = Column(String(20))
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Feedback(Base):
    __tablename__ = 'feedback'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(50))
    rating = Column(Integer)
    comment = Column(String(500))
    corrected_agent = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ToolFailure(Base):
    __tablename__ = 'tool_failures'
    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_name = Column(String(50), nullable=False, index=True)
    keyword = Column(String(100), nullable=True, index=True)
    error_message = Column(Text)
    agent_type = Column(String(50))
    session_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class RoutingLearning(Base):
    __tablename__ = 'routing_learnings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)
    user_input = Column(Text)
    old_agent = Column(String(50))
    new_agent = Column(String(50))
    keyword = Column(String(100))
    tools = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

class Monologue(Base):
    __tablename__ = 'monologues'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
