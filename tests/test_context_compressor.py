from __future__ import annotations

import asyncio

from app.context.compress import ContextCompressor


class FakeConversationRepo:
    def __init__(self, *, total_count: int, compressed_count: int, summary: str | None, history: list[dict]):
        self.total_count = total_count
        self.compressed_count = compressed_count
        self.summary = summary
        self.history = history
        self.updated: list[tuple[str, str, int]] = []

    async def get_message_count(self, _conversation_id: str) -> int:
        return self.total_count

    async def get_compressed_summary(self, _conversation_id: str):
        return self.summary, self.compressed_count

    async def get_history(self, _conversation_id: str, limit: int = 1000):
        _ = limit
        return self.history

    async def update_compressed_summary(self, conversation_id: str, summary: str, compressed_count: int):
        self.updated.append((conversation_id, summary, compressed_count))


def test_context_compressor_maybe_compress_noop_when_below_threshold():
    compressor = ContextCompressor(compression_threshold=6, recent_messages_limit=10)

    repo = FakeConversationRepo(
        total_count=15,
        compressed_count=0,
        summary=None,
        history=[{"role": "user", "content": "x"}] * 15,
    )

    async def _run():
        did = await compressor.maybe_compress("c1", repo, user_id="u1")
        assert did is False
        assert repo.updated == []

    asyncio.run(_run())


def test_context_compressor_maybe_compress_triggers_and_persists(monkeypatch):
    compressor = ContextCompressor(compression_threshold=2, recent_messages_limit=1)

    repo = FakeConversationRepo(
        total_count=5,
        compressed_count=0,
        summary="OLD",
        history=[
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
        ],
    )

    async def fake_compress(messages, existing_summary=None, **_kwargs):
        assert existing_summary == "OLD"
        assert [m["content"] for m in messages] == ["u1", "a1"]
        return "NEW"

    monkeypatch.setattr(compressor, "_compress", fake_compress)

    async def _run():
        did = await compressor.maybe_compress("c1", repo, user_id="u1")
        assert did is True
        assert repo.updated == [("c1", "NEW", 2)]

    asyncio.run(_run())


def test_context_compressor_maybe_compress_returns_false_when_summary_empty(monkeypatch):
    compressor = ContextCompressor(compression_threshold=1, recent_messages_limit=0)

    repo = FakeConversationRepo(
        total_count=2,
        compressed_count=0,
        summary=None,
        history=[{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}],
    )

    async def fake_compress(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(compressor, "_compress", fake_compress)

    async def _run():
        did = await compressor.maybe_compress("c1", repo, user_id="u1")
        assert did is False
        assert repo.updated == []

    asyncio.run(_run())


def test_context_compressor_maybe_compress_handles_errors_gracefully():
    compressor = ContextCompressor(compression_threshold=1, recent_messages_limit=0)

    class BrokenRepo:
        async def get_message_count(self, _conversation_id: str) -> int:
            raise RuntimeError("boom")

    async def _run():
        did = await compressor.maybe_compress("c1", BrokenRepo(), user_id="u1")
        assert did is False

    asyncio.run(_run())


def test_context_compressor_format_messages_truncates_and_labels():
    compressor = ContextCompressor(history_text_max_len=3)
    out = compressor._format_messages_for_compression(
        [
            {"role": "user", "content": "123456"},
            {"role": "assistant", "content": "ok"},
        ]
    )
    assert "用户: 123..." in out
    assert "助手: ok" in out

