"""Database engine and session factory.

Swap DATABASE_URL in config.py to point at Azure SQL later - models stay unchanged.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)

# check_same_thread=False required for SQLite with FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import inspect, text

    from app.models import models  # noqa: F401

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
