from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace


def _food_item(diet_endpoint, name: str, calories: int):
    return diet_endpoint.FoodItemSchema(
        food_name=name,
        calories=calories,
        source="manual",
    )


def test_weekly_bundle_includes_training_compensation_when_meal_space_insufficient(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service

    user_id = "u_comp_training"
    request = build_request(user_id=user_id)
    week_start = date(2026, 3, 16)
    target_date = date(2026, 3, 18)

    run(
        diet_service.update_user_preference(
            user_id,
            calorie_goal=2000,
            stats={
                "planmode_profile": {
                    "weekly_intensity": "balanced",
                    "training_focus": "cardio",
                    "training_minutes_per_day": 30,
                    "training_days_per_week": 7,
                    "relax_modes": ["walk"],
                }
            },
        )
    )

    for offset in range(3):
        run(
            diet_endpoint.add_meal(
                diet_endpoint.AddMealRequest(
                    plan_date=target_date + timedelta(days=offset),
                    meal_type="dinner",
                    dishes=[diet_endpoint.DishSchema(name=f"计划晚餐{offset}", calories=260)],
                ),
                request,
            )
        )

    run(
        diet_endpoint.create_log(
            diet_endpoint.CreateLogRequest(
                log_date=week_start,
                meal_type="lunch",
                items=[_food_item(diet_endpoint, "高热量午餐", 920)],
            ),
            request,
        )
    )
    run(
        diet_endpoint.create_log(
            diet_endpoint.CreateLogRequest(
                log_date=week_start + timedelta(days=1),
                meal_type="dinner",
                items=[_food_item(diet_endpoint, "高热量晚餐", 880)],
            ),
            request,
        )
    )

    bundled = run(
        diet_endpoint.get_weekly_summary_bundle(
            request,
            week_start_date=week_start,
            target_date=target_date,
            meal_type="dinner",
        )
    )

    suggestion = bundled["compensation_suggestion"]
    assert suggestion["kind"] == "training_compensation"
    assert suggestion["uncovered_gap"] > 0
    assert suggestion["suggested_minutes"] >= 10
    assert suggestion["estimated_burn_kcal"] >= 40
    assert bundled["next_meal_correction"] is not None


def test_compensation_suggestion_falls_back_to_recovery_day(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service

    user_id = "u_comp_recovery"
    request = build_request(user_id=user_id)
    week_start = date(2026, 3, 16)
    target_date = date(2026, 3, 18)

    run(diet_service.update_user_preference(user_id, calorie_goal=1800))

    run(
        diet_endpoint.add_meal(
            diet_endpoint.AddMealRequest(
                plan_date=target_date,
                meal_type="dinner",
                dishes=[diet_endpoint.DishSchema(name="轻晚餐", calories=250)],
            ),
            request,
        )
    )
    run(
        diet_endpoint.create_log(
            diet_endpoint.CreateLogRequest(
                log_date=week_start,
                meal_type="lunch",
                items=[_food_item(diet_endpoint, "放纵餐", 1000)],
            ),
            request,
        )
    )

    suggestion = run(
        diet_endpoint.get_compensation_suggestion(
            request,
            week_start_date=week_start,
            target_date=target_date,
        )
    )

    assert suggestion.kind == "recovery_day"
    assert suggestion.relax_suggestions
    assert suggestion.suggested_minutes is None


def test_three_line_trends_include_goal_and_emotion_markers(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service

    user_id = "u_trend_lines"
    request = build_request(user_id=user_id)
    end_date = date(2026, 3, 18)

    run(
        diet_service.update_user_preference(
            user_id,
            age=30,
            biological_sex="male",
            height_cm=180,
            weight_kg=80,
            activity_level="moderate",
            goal_intent="fat_loss",
        )
    )

    run(
        diet_endpoint.create_log(
            diet_endpoint.CreateLogRequest(
                log_date=end_date - timedelta(days=1),
                meal_type="lunch",
                items=[_food_item(diet_endpoint, "正常午餐", 760)],
            ),
            request,
        )
    )
    run(
        diet_endpoint.create_log(
            diet_endpoint.CreateLogRequest(
                log_date=end_date,
                meal_type="dinner",
                items=[_food_item(diet_endpoint, "正常晚餐", 820)],
            ),
            request,
        )
    )
    run(
        diet_service.adjust_today_budget(
            user_id=user_id,
            delta_calories=100,
            target_date=end_date - timedelta(days=1),
            source="emotion_subagent",
            reason="压力进食",
        )
    )

    trends = run(
        diet_endpoint.get_three_line_trends(
            request,
            days=7,
            end_date=end_date,
        )
    )

    assert trends.days == 7
    assert len(trends.daily) == 7
    assert len(trends.series.intake) == 7
    assert len(trends.goal_source_changes) >= 1
    assert trends.goal_context["goal_source"] == "tdee_estimate"

    marked_day = next(item for item in trends.daily if item.date == (end_date - timedelta(days=1)).isoformat())
    assert marked_day.emotion_exemption_active is True
    assert marked_day.goal_source == "tdee_estimate"
    assert marked_day.effective_goal == 2410
