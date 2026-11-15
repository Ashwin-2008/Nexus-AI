from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Configure test environment before importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("INGESTION_USE_CELERY", "false")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("VECTOR_INDEX_BACKEND", "memory")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")

from app.core.config import settings  # noqa: E402

settings.secret_key = os.environ["SECRET_KEY"]
settings.database_url = os.environ["DATABASE_URL"]

from app.db.base import Base  # noqa: E402
from app.db import session as db_session_module  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Point app DB session to test engine so background tasks and direct usage share the same DB
db_session_module.engine = engine
db_session_module.SessionLocal = TestingSessionLocal


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    # Clean tables per test for isolation
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
