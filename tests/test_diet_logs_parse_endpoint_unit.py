from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _build_anon_request():
    return SimpleNamespace(state=SimpleNamespace())


def test_parse_diet_logs_requires_auth(run):
    from app.api.v1.endpoints import diet as diet_endpoint

    payload = diet_endpoint.ParseDietInputRequest(text="午饭吃了牛肉面")
    with pytest.raises(HTTPException) as exc:
        run(diet_endpoint.parse_diet_log_input(payload, _build_anon_request()))
    assert exc.value.status_code == 401


def test_parse_diet_logs_happy_path(monkeypatch, run, build_request):
    from app.diet.service import diet_service

    async def _fake_parse(*_args, **_kwargs):
        return {
            "meal_type": "lunch",
            "items": [
                {
                    "food_name": "牛肉面",
                    "weight_g": 400,
                    "unit": "碗",
                    "calories": 650,
                    "protein": 25.0,
                    "fat": 18.0,
                    "carbs": 85.0,
                    "candidates": [
                        {
                            "food_name": "炸酱面",
                            "confidence_score": 0.31,
                        }
                    ],
                }
            ],
            "used_vision": False,
            "confidence": 0.52,
            "needs_confirmation": True,
            "candidates": [
                {
                    "food_name": "牛杂面",
                    "confidence_score": 0.22,
                }
            ],
        }

    monkeypatch.setattr(diet_service, "_parse_diet_input_with_ai", _fake_parse)

    from app.api.v1.endpoints import diet as diet_endpoint

    request = build_request(user_id="u_parse_1")
    resp = run(
        diet_endpoint.parse_diet_log_input(
            diet_endpoint.ParseDietInputRequest(text="午饭吃了牛肉面"),
            request,
        )
    )
    assert resp.used_vision is False
    assert resp.meal_type == "lunch"
    assert len(resp.items) == 1
    assert resp.items[0].food_name == "牛肉面"
    assert resp.items[0].source == "ai_text"
    assert resp.items[0].candidates[0].name == "炸酱面"
    assert resp.items[0].candidates[0].food_name == "炸酱面"
    assert resp.items[0].low_confidence_candidates[0].name == "炸酱面"
    assert resp.confidence == 0.52
    assert resp.needs_confirmation is True
    assert resp.candidates[0].name == "牛杂面"
    assert resp.candidates[0].food_name == "牛杂面"
