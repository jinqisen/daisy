from __future__ import annotations

from typing import Generator

from ..core.database import SessionLocal


def get_db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
