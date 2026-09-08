"""Database engine and session factory.

Swap DATABASE_URL in config.py to point at Azure SQL later - models stay unchanged.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)

# check_same_thread=False required for SQLite with FastAPI (requests may use other threads)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    """Enforce FK constraints; SQLite leaves them off by default."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one Session per request, always closed afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create missing tables, then apply lightweight column adds for local upgrades.

    Full Alemmic migrations are out of scope for the prototype; CaseNumber is an
    example of an in-place ALTER when an older SQLite file already exists.
    """
    from sqlalchemy import inspect, text

    from app.models import models  # noqa: F401  # register models on Base.metadata

    Base.metadata.create_all(bind=engine)

    # Lightweight SQLite column add for local prototype upgrades
    inspector = inspect(engine)
    if "Bookings" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("Bookings")}
        if "CaseNumber" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE Bookings ADD COLUMN CaseNumber VARCHAR(64) NOT NULL DEFAULT ''")
                )
