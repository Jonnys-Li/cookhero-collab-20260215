from __future__ import annotations

import asyncio
import importlib
import uuid
from datetime import datetime, timedelta


evaluation_repo_mod = importlib.import_module("app.database.evaluation_repository")
EvaluationRepository = getattr(evaluation_repo_mod, "EvaluationRepository")


def test_evaluation_repository_stats_trends_and_alerts(monkeypatch, sqlite_session_context):
    monkeypatch.setattr(evaluation_repo_mod, "get_session_context", sqlite_session_context)

    repo = EvaluationRepository()

    async def _run():
        user_id = "u-eval"
        conv_uuid = uuid.uuid4()
        msg1_uuid = uuid.uuid4()
        msg2_uuid = uuid.uuid4()
        conv_id = str(conv_uuid)
        msg1 = str(msg1_uuid)
        msg2 = str(msg2_uuid)

        created1 = datetime.utcnow() - timedelta(days=1)
        created2 = datetime.utcnow()

        # RAGEvaluationModel.message_id has an FK to messages.id; seed messages first.
        from app.database.models import ConversationModel, MessageModel

        async with sqlite_session_context() as session:
            session.add(ConversationModel(id=conv_uuid, user_id=user_id))
            session.add(
                MessageModel(
                    id=msg1_uuid,
                    conversation_id=conv_uuid,
                    role="user",
                    content="hello",
                )
            )
            session.add(
                MessageModel(
                    id=msg2_uuid,
                    conversation_id=conv_uuid,
                    role="user",
                    content="hello again",
                )
            )
            await session.flush()

        e1 = await repo.create(
            message_id=msg1,
            conversation_id=conv_id,
            query="q1",
            context="ctx",
            response="r1",
            user_id=user_id,
            created_at=created1,
        )
        e2 = await repo.create(
            message_id=msg2,
            conversation_id=conv_id,
            query="q2",
            context="ctx",
            response="r2",
            user_id=user_id,
            created_at=created2,
        )

        assert await repo.update_results(
            evaluation_id=str(e2.id),
            results={"faithfulness": 0.2, "answer_relevancy": 0.9},
            duration_ms=123,
            status="completed",
        ) is True

        # Non-existent evaluation ids should return False.
        assert await repo.update_results(
            evaluation_id=str(uuid.uuid4()),
            results={},
            duration_ms=1,
        ) is False

        fetched = await repo.get_by_id(str(e1.id))
        assert fetched is not None
        assert fetched["evaluation_status"] == "pending"

        by_conv = await repo.get_by_conversation(conv_id, limit=10)
        assert len(by_conv) == 2

        stats = await repo.get_statistics(user_id=user_id)
        assert stats["total_evaluations"] == 1  # completed only
        assert stats["pending_count"] == 1
        assert stats["failed_count"] == 0
        assert stats["metrics"]["faithfulness"]["mean"] == 0.2
        assert stats["avg_evaluation_duration_ms"] == 123.0

        trends = await repo.get_trends(days=7, granularity="day", user_id=user_id)
        assert trends
        assert sum(int(t["count"]) for t in trends) == 1

        alerts = await repo.get_alerts({"faithfulness": 0.3}, limit=10, user_id=user_id)
        assert len(alerts) == 1
        assert "faithfulness" in alerts[0]["violated_thresholds"]

        assert await repo.get_alerts({}, limit=10, user_id=user_id) == []

    asyncio.run(_run())
