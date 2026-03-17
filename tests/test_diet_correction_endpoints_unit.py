from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _build_anon_request():
    return SimpleNamespace(state=SimpleNamespace())


def test_apply_next_meal_correction_requires_auth(run):
    from app.api.v1.endpoints import diet as diet_endpoint

    payload = diet_endpoint.ApplyNextMealCorrectionRequest(
        plan_date="2026-03-17",
        meal_type="dinner",
        dish_name="test",
        calories=400,
    )
    with pytest.raises(HTTPException) as exc:
        run(diet_endpoint.apply_next_meal_correction(payload, _build_anon_request()))
    assert exc.value.status_code == 401


def test_weekly_summary_bundle_requires_auth(run):
    from app.api.v1.endpoints import diet as diet_endpoint

    with pytest.raises(HTTPException) as exc:
        run(diet_endpoint.get_weekly_summary_bundle(_build_anon_request()))
    assert exc.value.status_code == 401


def test_apply_next_meal_correction_happy_path(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint

    request = build_request(user_id="u_test_2")

    created = run(
        diet_endpoint.apply_next_meal_correction(
            diet_endpoint.ApplyNextMealCorrectionRequest(
                plan_date="2026-03-17",
                meal_type="dinner",
                dish_name="纠偏餐",
                calories=420,
                notes="unit test",
            ),
            request,
        )
    )
    assert created["plan_date"] == "2026-03-17"
    assert created["meal_type"] == "dinner"
    assert created["meal"]["meal_type"] == "dinner"
    assert created["meal"]["dishes"][0]["name"] == "纠偏餐"

    # Bundle endpoint should return a nutrition_snapshot that can be sent to community.
    bundled = run(
        diet_endpoint.get_weekly_summary_bundle(
            request,
            week_start_date=None,
            target_date=None,
            meal_type=None,
        )
    )
    assert "weekly_summary" in bundled
    assert "deviation" in bundled
    assert "next_meal_correction" in bundled
    assert "nutrition_snapshot" in bundled
    assert bundled["nutrition_snapshot"]["kind"] == "weekly_recap"
