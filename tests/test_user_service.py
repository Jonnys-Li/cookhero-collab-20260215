from __future__ import annotations

import asyncio
import importlib
import uuid

import pytest


def test_user_service_sqlite_crud_and_profile_updates(monkeypatch, sqlite_session_context):
    user_service_mod = importlib.import_module("app.services.user_service")
    monkeypatch.setattr(user_service_mod, "get_session_context", sqlite_session_context)

    UserService = getattr(user_service_mod, "UserService")
    service = UserService()

    user_id = uuid.uuid4()
    other_id = uuid.uuid4()

    async def _seed():
        from app.database.models import UserModel

        async with sqlite_session_context() as session:
            session.add(UserModel(id=user_id, username="u1", password_hash="x"))
            session.add(UserModel(id=other_id, username="u2", password_hash="x"))

    async def _run():
        await _seed()

        u1 = await service.get_user_by_username("u1")
        assert u1 is not None
        assert str(u1.id) == str(user_id)

        assert await service.get_user_by_username("missing") is None

        by_id = await service.get_user_by_id(str(user_id))
        assert by_id is not None
        assert by_id.username == "u1"

        assert await service.get_user_by_id(None) is None
        assert await service.get_user_by_id("not-a-uuid") is None

        updated = await service.update_profile(
            "u1",
            {
                "occupation": "chef",
                "bio": "b1",
                "profile": "p1",
                "user_instruction": "i1",
                "username": "u1-new",
            },
        )
        assert updated.username == "u1-new"
        assert updated.occupation == "chef"
        assert updated.user_instruction == "i1"

        with pytest.raises(ValueError):
            await service.update_profile("missing", {"bio": "x"})

        with pytest.raises(ValueError):
            await service.update_profile("u1-new", {"username": "u2"})

    asyncio.run(_run())

