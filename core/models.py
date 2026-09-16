from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class RoutingKeyword(Base):
    __tablename__ = 'routing_keywords'
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent = Column(String(50), nullable=False, index=True)
    keyword = Column(String(100), nullable=False, index=True)

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
    created_at = Column(DateTime, default=datetime.utcnow)
