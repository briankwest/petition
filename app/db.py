"""Database wiring. DATABASE_URL comes from Dokku's postgres plugin (postgres://…); we rewrite
the scheme for SQLAlchemy+psycopg3. Without DATABASE_URL we use a local SQLite file so
`make app-dev` and the tests work with no services running."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from toolkit import ROOT


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        (ROOT / "output").mkdir(exist_ok=True)
        return f"sqlite:///{ROOT / 'output' / 'dev.db'}"
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str | None = None):
    url = url or database_url()
    kw = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw = {"connect_args": {"check_same_thread": False}}
    eng = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(eng=None) -> None:
    from . import models  # noqa: F401  (registers tables)
    Base.metadata.create_all(eng or engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
