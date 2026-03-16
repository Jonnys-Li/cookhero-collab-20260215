from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

import app.diet.database.repository as diet_repo_mod
from app.diet.database.repository import DietRepository


def test_diet_repository_plan_logs_and_summaries(monkeypatch, sqlite_session_context):
    monkeypatch.setattr(diet_repo_mod, "get_session_context", sqlite_session_context)

    repo = DietRepository()

    async def _run():
        user_id = "u-diet"
        week_start = date(2026, 3, 9)

        meal_breakfast = await repo.add_meal_to_plan(
            user_id,
            week_start,
            "breakfast",
            dishes=[{"dish_name": "oats"}],
            total_calories=400,
        )
        meal_lunch = await repo.add_meal_to_plan(
            user_id,
            week_start,
            "lunch",
            dishes=[{"dish_name": "chicken rice"}],
            total_calories=700,
        )

        meals = await repo.get_plan_meals_by_week(user_id, week_start)
        assert len(meals) >= 2

        fetched = await repo.get_meal(str(meal_breakfast.id))
        assert fetched is not None and fetched.meal_type == "breakfast"

        updated = await repo.update_meal(str(meal_breakfast.id), notes="n1", total_protein=30)
        assert updated is not None and updated.notes == "n1"

        copied = await repo.copy_meal(
            str(meal_breakfast.id),
            week_start + timedelta(days=8),  # outside the current week window
            target_meal_type="dinner",
        )
        assert copied is not None and copied.meal_type == "dinner"

        # Invalid meal ids should not crash.
        assert await repo.get_meal("bad") is None
        assert await repo.update_meal("bad", notes="x") is None
        assert await repo.delete_meal("bad") is False
        assert await repo.copy_meal("bad", week_start) is None

        # Create a deterministic log id so we can update it later.
        log_uuid = uuid.uuid4()
        created = await repo.create_log_items(
            user_id=user_id,
            log_date=week_start,
            meal_type="breakfast",
            plan_meal_id=str(meal_breakfast.id),
            log_id=log_uuid,
            notes="m1",
            items=[
                {
                    "food_name": "egg",
                    "weight_g": 100,
                    "unit": "g",
                    "calories": 155,
                    "protein": 13,
                    "fat": 11,
                    "carbs": 1,
                },
                {
                    "food_name": "rice",
                    "calories": 200,
                },
            ],
        )
        assert len(created) == 2
        assert str(created[0].log_id) == str(log_uuid)

        assert await repo.get_log_items_by_log_id("bad") == []
        by_log = await repo.get_log_items_by_log_id(str(log_uuid))
        assert len(by_log) == 2

        by_date = await repo.get_log_items_by_date(user_id, week_start)
        assert len(by_date) == 2

        summary = await repo.get_daily_summary(user_id, week_start)
        assert summary["total_calories"] == 355
        assert summary["log_count"] == 1
        assert "breakfast" in summary["meals_logged"]

        weekly = await repo.get_weekly_summary(user_id, week_start)
        assert weekly["week_start_date"] == week_start.isoformat()
        assert week_start.isoformat() in weekly["daily_data"]

        assert await repo.update_log_notes(str(log_uuid), "note2") is True
        assert await repo.update_log_notes("bad", "n") is False

        # Update metadata with the same meal/date to keep plan-vs-actual stable.
        assert (
            await repo.update_log_metadata(
                str(log_uuid),
                meal_type="breakfast",
                log_date=week_start,
                notes="note3",
            )
            is True
        )
        assert await repo.update_log_metadata("bad", meal_type="breakfast") is False

        new_item = await repo.add_item_to_log(str(log_uuid), "banana", calories=100)
        assert new_item is not None and new_item.food_name == "banana"
        assert await repo.add_item_to_log("bad", "x") is None

        pref = await repo.upsert_user_preference(user_id, common_foods=["egg"])
        assert pref.user_id == user_id
        pref2 = await repo.get_user_preference(user_id)
        assert pref2 is not None and pref2.common_foods == ["egg"]

        deviation = await repo.calculate_plan_vs_actual_deviation(user_id, week_start)
        assert deviation["has_plan"] is True
        assert deviation["execution_rate"] == 50.0
        assert deviation["total_plan_calories"] == 1100
        assert deviation["total_actual_calories"] == 455  # 155 + 200 + 100

        assert await repo.delete_log_items(str(log_uuid)) is True
        assert await repo.delete_log_items("bad") is False
        assert await repo.get_log_items_by_log_id(str(log_uuid)) == []

        # Make sure delete_meal succeeds for valid ids.
        assert await repo.delete_meal(str(meal_lunch.id)) is True

    asyncio.run(_run())

