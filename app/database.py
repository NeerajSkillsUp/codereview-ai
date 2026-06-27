from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os
from app.config import settings

DATABASE_URL = settings.DATABASE_URL

# ─── RESILIENT PRODUCTION URL FIX ───
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Fixes a known compatibility break between SQLAlchemy and cloud string schemas
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./sql_app.db"

# ─── ENGINE DRIVER INITIALIZATION ───
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping checks the connection health before executing commands,
    # which prevents drops from external database sleep cycles.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class CodeReviewHistory(Base):
    __tablename__ = "code_reviews"
    id = Column(Integer, primary_key=True, index=True)
    repo_name = Column(String, index=True)
    pr_number = Column(Integer)
    action = Column(String)
    ai_feedback = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)