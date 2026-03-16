from __future__ import annotations

import asyncio

import pytest

from app.services.mcp_service import MCPService


def test_mcp_service_create_update_delete_with_sqlite(monkeypatch, sqlite_session_context):
    import app.services.mcp_service as mcp_mod

    # Use isolated SQLite DB instead of the global Postgres session context.
    monkeypatch.setattr(mcp_mod, "get_session_context", sqlite_session_context)

    service = MCPService()

    unregister_calls: list[str] = []
    monkeypatch.setattr(service, "_unregister_server", lambda name: unregister_calls.append(name))

    async def fake_register_server(server, *, strict: bool = False):
        _ = strict
        return [f"mcp_{server.name}_tool"]

    monkeypatch.setattr(service, "register_server", fake_register_server)

    async def _run():
        # Disabled server should not attempt registration.
        server1, tools1 = await service.create_server(
            user_id="u1",
            name="s1",
            endpoint="https://example.com",
            enabled=False,
        )
        assert server1.name == "s1"
        assert tools1 == []

        # Enabled server should validate and register tools.
        server2, tools2 = await service.create_server(
            user_id="u1",
            name="s2",
            endpoint="https://example.com",
            enabled=True,
        )
        assert server2.name == "s2"
        assert tools2 == ["mcp_s2_tool"]

        # Duplicate name for same user should fail.
        with pytest.raises(ValueError):
            await service.create_server(
                user_id="u1",
                name="s2",
                endpoint="https://example.com",
                enabled=False,
            )

        # Update can disable and triggers unregister after commit.
        updated, loaded = await service.update_server(
            user_id="u1",
            name="s2",
            enabled=False,
        )
        assert updated is not None
        assert loaded == []
        assert "s2" in unregister_calls

        # Delete removes record and unregisters.
        assert await service.delete_server("u1", "s2") is True
        assert await service.delete_server("u1", "missing") is False

    asyncio.run(_run())

