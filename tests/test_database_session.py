from __future__ import annotations

import asyncio
import importlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def test_database_session_contexts_commit_rollback_and_background_factory(tmp_path, monkeypatch):
    session_mod = importlib.import_module("app.database.session")

    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Patch the module-level engine/sessionmaker to use our isolated SQLite DB.
    monkeypatch.setattr(session_mod, "db_async_url", db_url, raising=False)
    monkeypatch.setattr(session_mod, "is_sqlite", True, raising=False)
    monkeypatch.setattr(session_mod, "_engine", engine)
    monkeypatch.setattr(session_mod, "async_session_factory", factory)

    # Reset background engine state so we cover its creation path deterministically.
    monkeypatch.setattr(session_mod, "_background_engine", None, raising=False)
    monkeypatch.setattr(session_mod, "_background_session_factory", None, raising=False)

    async def _run():
        await session_mod.init_db()

        from app.database.models import UserModel

        # Commit path
        user1 = uuid.uuid4()
        async with session_mod.get_session_context() as session:
            session.add(UserModel(id=user1, username="u1", password_hash="x"))
            await session.flush()

        async with session_mod.get_session_context() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.username == "u1")
            )
            assert result.scalar_one_or_none() is not None

        # Rollback path
        try:
            async with session_mod.get_session_context() as session:
                session.add(UserModel(id=uuid.uuid4(), username="u2", password_hash="x"))
                await session.flush()
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        async with session_mod.get_session_context() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.username == "u2")
            )
            assert result.scalar_one_or_none() is None

        # Background factory caching + teardown
        bg1 = session_mod.get_background_session_factory()
        bg2 = session_mod.get_background_session_factory()
        assert bg1 is bg2

        await session_mod.close_background_db()
        assert session_mod._background_engine is None
        assert session_mod._background_session_factory is None

        await session_mod.close_db()

    asyncio.run(_run())

