import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import config as _config  # noqa: F401

DATABASE_URL_ENV = "DATABASE_URL"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    """Return the configured URL using psycopg 3 for PostgreSQL URLs."""
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it before accessing the database."
        )

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def get_engine() -> Engine:
    """Create the application engine only on its first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory bound to the lazy application engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that closes its session after each request."""
    database = get_session_factory()()
    try:
        yield database
    finally:
        database.close()
