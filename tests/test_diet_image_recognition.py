import base64
from typing import Optional

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1.endpoints import diet as diet_api


def make_request(user_id: Optional[str] = None) -> Request:
    request = Request({"type": "http", "headers": []})
    if user_id is not None:
        request.state.user_id = user_id
    return request


def build_image_payload(raw: bytes = b"fake-image") -> str:
    return base64.b64encode(raw).decode("utf-8")


def test_recognize_image_success(monkeypatch, run):
    async def fake_recognize(
        user_id: str, images: list, context_text: Optional[str] = None
    ):
        assert user_id == "u1"
        assert len(images) == 1
        assert context_text == "晚餐照片"
        return {
            "dishes": [
                {
                    "name": "红烧牛肉",
                    "calories": 320,
                    "protein": 24.0,
                    "fat": 18.0,
                    "carbs": 10.0,
                    "confidence_score": 0.48,
                    "candidates": [
                        {"food_name": "红烧排骨", "confidence_score": 0.22}
                    ],
                    "low_confidence_candidates": [
                        {"name": "红烧排骨", "confidence_score": 0.22}
                    ],
                },
                {"name": "白米饭", "calories": 230},
            ],
            "message": "识别完成",
            "source": "ai_image",
            "confidence": 0.48,
            "needs_confirmation": True,
            "candidates": [
                {"food_name": "红烧排骨", "confidence_score": 0.22}
            ],
        }

    monkeypatch.setattr(diet_api.diet_service, "recognize_meal_from_images", fake_recognize)

    payload = diet_api.RecognizeMealFromImageRequest(
        images=[diet_api.ImageData(data=build_image_payload(), mime_type="image/jpeg")],
        context_text="晚餐照片",
    )
    response = run(diet_api.recognize_meal_from_image(payload, make_request("u1")))

    assert response.message == "识别完成"
    assert response.source == "ai_image"
    assert len(response.dishes) == 2
    assert response.dishes[0].name == "红烧牛肉"
    assert response.dishes[0].calories == 320
    assert response.dishes[0].confidence_score == 0.48
    assert response.dishes[0].candidates[0].name == "红烧排骨"
    assert response.dishes[0].low_confidence_candidates[0].food_name == "红烧排骨"
    assert response.dishes[1].name == "白米饭"
    assert response.confidence == 0.48
    assert response.needs_confirmation is True
    assert response.candidates[0].name == "红烧排骨"


def test_recognize_image_returns_empty_dishes(monkeypatch, run):
    async def fake_recognize(
        user_id: str, images: list, context_text: Optional[str] = None
    ):
        return {
            "dishes": [],
            "message": "未识别到清晰食物，请手动补充",
            "source": "ai_image",
        }

    monkeypatch.setattr(diet_api.diet_service, "recognize_meal_from_images", fake_recognize)

    payload = diet_api.RecognizeMealFromImageRequest(
        images=[diet_api.ImageData(data=build_image_payload(), mime_type="image/jpeg")]
    )
    response = run(diet_api.recognize_meal_from_image(payload, make_request("u1")))

    assert response.dishes == []
    assert "手动补充" in response.message
    assert response.source == "ai_image"


def test_recognize_image_vision_not_enabled(monkeypatch, run):
    error_message = "当前未开启拍照识别，请先配置 VISION_API_KEY 或可用的 LLM_API_KEY"

    async def fake_recognize(
        user_id: str, images: list, context_text: Optional[str] = None
    ):
        raise RuntimeError(error_message)

    monkeypatch.setattr(diet_api.diet_service, "recognize_meal_from_images", fake_recognize)

    payload = diet_api.RecognizeMealFromImageRequest(
        images=[diet_api.ImageData(data=build_image_payload(), mime_type="image/jpeg")]
    )

    with pytest.raises(HTTPException) as exc:
        run(diet_api.recognize_meal_from_image(payload, make_request("u1")))

    assert exc.value.status_code == 503
    assert exc.value.detail == error_message


def test_recognize_image_requires_auth(run):
    payload = diet_api.RecognizeMealFromImageRequest(
        images=[diet_api.ImageData(data=build_image_payload(), mime_type="image/jpeg")]
    )

    with pytest.raises(HTTPException) as exc:
        run(diet_api.recognize_meal_from_image(payload, make_request(None)))

    assert exc.value.status_code == 401


def test_recognize_image_validation_invalid_mime(run):
    with pytest.raises(ValidationError):
        diet_api.RecognizeMealFromImageRequest(
            images=[diet_api.ImageData(data=build_image_payload(), mime_type="image/bmp")]
        )


def test_recognize_image_validation_oversize(monkeypatch, run):
    monkeypatch.setattr(diet_api, "MAX_IMAGE_SIZE_MB", 0.00001)

    with pytest.raises(ValidationError):
        diet_api.RecognizeMealFromImageRequest(
            images=[
                diet_api.ImageData(
                    data=build_image_payload(raw=b"a" * 1024),
                    mime_type="image/jpeg",
                )
            ]
        )
