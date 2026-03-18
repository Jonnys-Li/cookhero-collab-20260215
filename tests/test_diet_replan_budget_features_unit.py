from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str):
        return self.store.get(key)


def _anon_request():
    return SimpleNamespace(state=SimpleNamespace())


def test_replan_preview_requires_auth(run):
    from app.api.v1.endpoints import diet as diet_endpoint

    with pytest.raises(HTTPException) as exc:
        run(
            diet_endpoint.preview_replan(
                diet_endpoint.ReplanPreviewRequest(
                    target_date="2026-03-18",
                    meal_type="dinner",
                ),
                _anon_request(),
            )
        )

    assert exc.value.status_code == 401


def test_replan_preview_apply_and_shopping_list(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint

    request = build_request(user_id="u_replan")
    target_date = date(2026, 3, 18)
    week_start = target_date - timedelta(days=target_date.weekday())

    run(
        diet_endpoint.add_meal(
            diet_endpoint.AddMealRequest(
                plan_date=target_date,
                meal_type="dinner",
                dishes=[diet_endpoint.DishSchema(name="原计划晚餐", calories=650)],
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

    assert preview.meal_type == "dinner"
    assert preview.candidates
    assert preview.selected_candidate.dish_name
    assert preview.apply_path.endswith("/diet/replan/apply")

    applied = run(
        diet_endpoint.apply_replan(
            diet_endpoint.ReplanApplyRequest(
                target_date=target_date,
                meal_type="dinner",
                selected_candidate=preview.selected_candidate,
                notes="单测改餐",
            ),
            request,
        )
    )

    assert applied.action == "updated"
    assert applied.meal["dishes"][0]["name"] == preview.selected_candidate.dish_name

    shopping_list = run(
        diet_endpoint.get_shopping_list(
            request,
            week_start_date=week_start,
        )
    )

    assert shopping_list.item_count >= 1
    assert shopping_list.items[0].name == preview.selected_candidate.dish_name


def test_budget_and_weekly_summary_include_emotion_exemption(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.services.emotion_exemption_service import emotion_exemption_service

    fake_redis = FakeRedis()
    emotion_exemption_service.set_redis(fake_redis)

    request = build_request(user_id="u_budget")
    target_date = date.today()
    week_start = target_date - timedelta(days=target_date.weekday())

    activated = run(
        emotion_exemption_service.activate(
            user_id="u_budget",
            target_date=target_date,
            summary="检测到高风险负面情绪，已暂停纠偏与预算调整。",
        )
    )

    assert activated["is_active"] is True

    budget = run(diet_endpoint.get_budget(request, target_date=target_date))
    assert budget["emotion_exemption"]["active"] is True
    assert budget["emotion_exemption"]["storage"] == "redis"
    assert budget["today_adjustment"] == 0

    exemption = run(
        diet_endpoint.get_emotion_exemption_status(
            request,
            target_date=target_date,
        )
    )
    assert exemption.active is True
    assert exemption.level == "high"
    assert exemption.summary == "检测到高风险负面情绪，已暂停纠偏与预算调整。"

    weekly = run(
        diet_endpoint.get_weekly_summary(
            request,
            week_start_date=week_start,
        )
    )
    assert "today_budget" in weekly
    assert "emotion_exemption" in weekly
    assert weekly["emotion_exemption"]["active"] is True


def test_parse_and_recognize_low_confidence_candidates(monkeypatch, run, build_request):
    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import diet_service

    async def fake_parse(*_args, **_kwargs):
        return {
            "meal_type": "lunch",
            "items": [
                {
                    "food_name": "牛肉面",
                    "calories": 620,
                    "confidence_score": 0.52,
                    "low_confidence_candidates": [
                        {"name": "炸酱面", "confidence_score": 0.31},
                        {"name": "牛杂面", "confidence_score": 0.17},
                    ],
                }
            ],
            "used_vision": False,
            "message": "存在低置信候选，请确认。",
        }

    async def fake_recognize(*_args, **_kwargs):
        return {
            "dishes": [
                {
                    "name": "红烧牛肉",
                    "calories": 320,
                    "low_confidence_candidates": [
                        {"name": "红烧排骨", "confidence_score": 0.22}
                    ],
                }
            ],
            "message": "识别完成",
            "source": "ai_image",
        }

    monkeypatch.setattr(diet_service, "_parse_diet_input_with_ai", fake_parse)
    monkeypatch.setattr(diet_endpoint.diet_service, "recognize_meal_from_images", fake_recognize)

    request = build_request(user_id="u_parse")
    parsed = run(
        diet_endpoint.parse_diet_log_input(
            diet_endpoint.ParseDietInputRequest(text="午饭吃了面"),
            request,
        )
    )
    assert parsed.message == "存在低置信候选，请确认。"
    assert parsed.items[0].low_confidence_candidates[0].name == "炸酱面"

    recognized = run(
        diet_endpoint.recognize_meal_from_image(
            diet_endpoint.RecognizeMealFromImageRequest(
                images=[diet_endpoint.ImageData(data="ZmFrZS1pbWFnZQ==", mime_type="image/jpeg")]
            ),
            request,
        )
    )
    assert recognized.dishes[0].low_confidence_candidates[0].name == "红烧排骨"


def test_weekly_replan_adds_training_compensation_when_diet_space_is_insufficient(
    run,
    build_request,
    sqlite_session_context,
    monkeypatch,
):
    import app.diet.database.repository as diet_repo_module

    monkeypatch.setattr(diet_repo_module, "get_session_context", sqlite_session_context)

    from app.api.v1.endpoints import diet as diet_endpoint
    from app.diet.service import get_week_start_date

    request = build_request(user_id="u_replan_comp")
    today = date.today()
    week_start = get_week_start_date(today)

    run(
        diet_endpoint.add_meal(
            diet_endpoint.AddMealRequest(
                plan_date=today,
                meal_type="breakfast",
                dishes=[diet_endpoint.DishSchema(name="计划早餐", calories=420)],
            ),
            request,
        )
    )
    run(
        diet_endpoint.add_meal(
            diet_endpoint.AddMealRequest(
                plan_date=today,
                meal_type="dinner",
                dishes=[diet_endpoint.DishSchema(name="已锁定晚餐", calories=280)],
                notes="用户手动固定，不自动调整",
            ),
            request,
        )
    )
    run(
        diet_endpoint.create_log(
            diet_endpoint.CreateLogRequest(
                log_date=today,
                meal_type="breakfast",
                items=[diet_endpoint.FoodItemSchema(food_name="额外加餐", calories=1400)],
                notes="unit-test over target",
            ),
            request,
        )
    )

    preview = run(
        diet_endpoint.get_weekly_replan_preview(
            request,
            week_start_date=week_start,
        )
    )

    assert preview.meal_changes == []
    assert preview.write_conflicts
    assert preview.compensation_summary is not None
    assert preview.compensation_suggestions
    assert preview.compensation_suggestions[0]["minutes"] >= 20
