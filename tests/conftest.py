import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


@pytest.fixture
def run():
    """Small helper to run async endpoint/service calls from sync tests."""

    def _run(coro):
        return asyncio.run(coro)

    return _run


@pytest.fixture
def build_request():
    """Build a minimal request-like object with `request.state.user_id`."""

    def _build_request(user_id: str = "u1"):
        return SimpleNamespace(state=SimpleNamespace(user_id=user_id))

    return _build_request


@pytest.fixture(scope="module")
def sqlite_session_context(tmp_path_factory):
    """
    Provide an isolated async SQLAlchemy session context backed by a temp SQLite DB.

    Many repository modules hard-import `get_session_context` at module import time.
    In tests we monkeypatch those module-level references to this context manager,
    so we can exercise real SQLAlchemy queries without touching the app's global DB.
    """

    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database.models import Base

    # Ensure all models are registered on Base.metadata.
    # Keep these imports inside the fixture to avoid slowing down collection.
    import app.agent.database.models  # noqa: F401
    import app.community.database.models  # noqa: F401
    import app.diet.database.models  # noqa: F401

    db_dir = tmp_path_factory.mktemp("sqlite_db")
    db_path = db_dir / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(db_url, echo=False)
    # Mirror production semantics for FK cascades: SQLite requires an explicit pragma.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-redef]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def _init_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_schema())

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    @asynccontextmanager
    async def _context():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    yield _context

    asyncio.run(engine.dispose())
