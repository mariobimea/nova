"""
Models module - SQLAlchemy database models
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Fix Railway PostgreSQL URL (postgres:// -> postgresql://)
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()

def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Import models after Base is defined to avoid circular imports
from .workflow import Workflow
from .execution import Execution
from .chain_of_work import ChainOfWork
from .chain_of_work_step import ChainOfWorkStep

__all__ = ["Base", "engine", "SessionLocal", "get_db", "Workflow", "Execution", "ChainOfWork", "ChainOfWorkStep"]
