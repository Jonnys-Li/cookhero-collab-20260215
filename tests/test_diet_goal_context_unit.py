from __future__ import annotations

from datetime import date


def test_budget_and_weekly_summary_use_tdee_estimate_when_profile_complete(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service, get_week_start_date

    user_id = "u_goal_ctx_complete"
    request = build_request(user_id=user_id)

    run(
        diet_service.update_user_preference(
            user_id,
            age=30,
            biological_sex="male",
            height_cm=180,
            weight_kg=80,
            activity_level="moderate",
            goal_intent="maintain",
        )
    )

    budget = run(diet_endpoint.get_budget(request, target_date=date.today()))
    assert budget["goal_source"] == "tdee_estimate"
    assert budget["base_goal"] == 2760
    assert budget["effective_goal"] == 2760
    assert budget["estimate_context"]["tdee_kcal"] == 2760
    assert budget["goal_context"]["uses_tdee_estimate"] is True

    weekly = run(
        diet_endpoint.get_weekly_summary(
            request,
            week_start_date=get_week_start_date(date.today()),
        )
    )
    assert weekly["goal_source"] == "tdee_estimate"
    assert weekly["base_goal"] == 2760
    assert weekly["weekly_goal_calories"] == 19320
    assert weekly["goal_context"]["estimate_context"]["recommended_calorie_goal"] == 2760


def test_budget_falls_back_when_metabolic_profile_incomplete(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service, get_week_start_date

    user_id = "u_goal_ctx_fallback"
    request = build_request(user_id=user_id)

    run(
        diet_service.update_user_preference(
            user_id,
            age=30,
            height_cm=180,
            weight_kg=80,
        )
    )

    budget = run(diet_endpoint.get_budget(request, target_date=date.today()))
    assert budget["goal_source"] == "default1800"
    assert budget["base_goal"] == 1800
    assert budget["estimate_context"] is None
    assert budget["goal_context"]["fallback_used"] is True

    weekly = run(
        diet_endpoint.get_weekly_summary(
            request,
            week_start_date=get_week_start_date(date.today()),
        )
    )
    assert weekly["goal_source"] == "default1800"
    assert weekly["estimate_context"] is None


def test_replan_preview_exposes_goal_context_without_regression(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service

    user_id = "u_goal_ctx_replan"
    request = build_request(user_id=user_id)
    target_date = date.today()

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
        diet_endpoint.add_meal(
            diet_endpoint.AddMealRequest(
                plan_date=target_date,
                meal_type="dinner",
                dishes=[diet_endpoint.DishSchema(name="测试晚餐", calories=620)],
            ),
            request,
        )
    )

    preview = run(
        diet_endpoint.preview_replan(
            diet_endpoint.ReplanPreviewRequest(
                target_date=target_date,
                meal_type="dinner",
                candidate_count=2,
            ),
            request,
        )
    )

    assert preview.candidates
    assert preview.weekly_context["goal_source"] == "tdee_estimate"
    assert preview.weekly_context["goal_context"]["uses_tdee_estimate"] is True
    assert preview.weekly_context["estimate_context"]["recommended_calorie_goal"] == 2310
