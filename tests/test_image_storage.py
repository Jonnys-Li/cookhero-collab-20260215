from __future__ import annotations

import asyncio

from app.config import ImageStorageConfig
from app.utils import image_storage


def test_upload_to_imgbb_disabled_and_missing_key_short_circuit(monkeypatch):
    monkeypatch.setattr(
        image_storage.settings,
        "image_storage",
        ImageStorageConfig(enabled=False, api_key="k"),
    )

    async def _run_disabled():
        assert await image_storage.upload_to_imgbb("img") is None

    asyncio.run(_run_disabled())

    monkeypatch.setattr(
        image_storage.settings,
        "image_storage",
        ImageStorageConfig(enabled=True, api_key=None),
    )

    async def _run_missing_key():
        assert await image_storage.upload_to_imgbb("img") is None

    asyncio.run(_run_missing_key())


def test_upload_to_imgbb_success_and_failure_paths(monkeypatch):
    monkeypatch.setattr(
        image_storage.settings,
        "image_storage",
        ImageStorageConfig(enabled=True, api_key="k", upload_url="https://example.com", expiration=123),
    )

    class FakeResponse:
        def __init__(self, payload: dict, *, raise_for_status: bool = False):
            self._payload = payload
            self._raise = raise_for_status

        def raise_for_status(self):
            if self._raise:
                raise RuntimeError("bad status")

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout
            self.posts = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, data: dict):
            self.posts.append((url, data))
            return FakeResponse(
                {
                    "success": True,
                    "data": {
                        "url": "u",
                        "display_url": "du",
                        "delete_url": "del",
                        "thumb": {"url": "tu"},
                    },
                }
            )

    monkeypatch.setattr(image_storage.httpx, "AsyncClient", FakeAsyncClient)

    async def _run_success():
        out = await image_storage.upload_to_imgbb("imgdata", mime_type="image/png")
        assert out is not None
        assert out["url"] == "u"
        assert out["display_url"] == "du"
        assert out["thumb_url"] == "tu"

    asyncio.run(_run_success())

    # Failure: API returns success=false
    class FakeAsyncClientFail(FakeAsyncClient):
        async def post(self, url: str, data: dict):
            self.posts.append((url, data))
            return FakeResponse({"success": False})

    monkeypatch.setattr(image_storage.httpx, "AsyncClient", FakeAsyncClientFail)

    async def _run_fail():
        assert await image_storage.upload_to_imgbb("imgdata") is None

    asyncio.run(_run_fail())

    # Failure: exception during request/raise_for_status
    class FakeAsyncClientRaise(FakeAsyncClient):
        async def post(self, url: str, data: dict):
            self.posts.append((url, data))
            return FakeResponse({"success": True}, raise_for_status=True)

    monkeypatch.setattr(image_storage.httpx, "AsyncClient", FakeAsyncClientRaise)

    async def _run_raise():
        assert await image_storage.upload_to_imgbb("imgdata") is None

    asyncio.run(_run_raise())

