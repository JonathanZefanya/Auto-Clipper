"""Koneksi SQLite (SQLModel). WAL agar SSE bisa membaca saat worker menulis."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registrasi tabel)


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SQLModel.metadata.create_all(engine)
    migrate(engine)
    return engine


def migrate(engine: Engine) -> list[str]:
    """Migrasi ringan: tambahkan kolom nullable baru ke tabel lama (create_all tidak mengubah tabel)."""
    added: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                if not col.nullable:
                    raise RuntimeError(f"Kolom wajib baru {table.name}.{col.name} butuh migrasi manual")
                ddl = col.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                added.append(f"{table.name}.{col.name}")
    return added


def session(engine: Engine) -> Session:
    return Session(engine, expire_on_commit=False)
