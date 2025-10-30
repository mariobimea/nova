"""
Database connection and session management for NOVA.

Provides:
- SessionLocal: Factory for creating database sessions
- get_db(): Context manager for DB sessions
- engine: SQLAlchemy engine instance
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable not set. "
        "Please configure it in .env file."
    )

# Create engine
# pool_pre_ping=True ensures connections are valid before using them
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False  # Set to True for SQL query logging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            workflow = db.query(Workflow).filter(Workflow.id == 1).first()
            db.add(execution)
            db.commit()

    The session is automatically closed when exiting the context,
    and rolled back if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Session:
    """
    Get a new database session (without context manager).

    Usage:
        db = get_db_session()
        try:
            workflow = db.query(Workflow).first()
            db.commit()
        finally:
            db.close()

    Note: You must manually close the session after use.
    Prefer using get_db() context manager when possible.
    """
    return SessionLocal()
