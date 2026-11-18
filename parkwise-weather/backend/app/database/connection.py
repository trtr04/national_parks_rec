"""
Database connection setup with SQLAlchemy 2.0.

One engine per process, one Session per request.
The same code works for SQLite (local dev) and PostgreSQL (Neon in production);
only DATABASE_URL changes.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Parent class for every ORM table in app/database/models.py."""


def normalize_database_url(url: str) -> str:
    """
    Point plain PostgreSQL URLs at the psycopg (v3) driver in requirements.txt.

    Neon and Render hand out 'postgres://' or 'postgresql://' URLs. Without a driver
    name, SQLAlchemy picks one based on its own version (psycopg2 before 2.1, psycopg
    after), so the driver is named explicitly. URLs that already name one are kept.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def build_engine(url: str) -> Engine:
    url = normalize_database_url(url)

    if url.startswith("sqlite"):
        # Make sure the folder for the .db file exists (e.g. parkwise-weather/data/).
        db_path = url.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(
            url,
            # FastAPI may use the connection from a different thread than the one that opened it.
            connect_args={"check_same_thread": False},
        )

        # SQLite ignores FOREIGN KEY constraints unless you switch them on per connection.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    # pool_pre_ping checks a pooled connection is still alive before using it.
    # Hosted Postgres (Neon) closes idle connections, so this avoids random first-request errors.
    return create_engine(url, pool_pre_ping=True)


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: opens a session for one request and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables. Safe to run repeatedly (existing tables are left alone)."""
    from app.database import models  # noqa: F401  (import registers the tables on Base)

    Base.metadata.create_all(bind=engine)
