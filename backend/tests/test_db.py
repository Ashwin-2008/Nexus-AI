from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def test_database_connectivity(db_session: Session) -> None:
    result = db_session.execute(text("SELECT 1")).scalar_one()
    assert result == 1
