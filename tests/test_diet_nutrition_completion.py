import asyncio
import uuid
from copy import deepcopy
from datetime import date

from app.diet.nutrition_completion_service import NutritionCompletionService
from app.diet.service import DietService


def run(coro):
    return asyncio.run(coro)


def test_complete_dishes_only_fills_missing_fields(monkeypatch):
    service = NutritionCompletionService()

    async def fake_resolve(*, dish_name: str, user_id: str):
        return {
            "calories": 420,
            "protein": 30.0,
            "fat": 12.0,
            "carbs": 34.0,
            "confidence": 0.9,
        }

    monkeypatch.setattr(service, "_resolve_dish_nutrition", fake_resolve)

    dishes = [
        {
            "name": "鸡胸沙拉",
            "calories": 460,  # 用户已填写，不应被覆盖
            "protein": None,
            "fat": None,
            "carbs": None,
        }
    ]
    enriched, changed = run(service.complete_dishes(user_id="u1", dishes=dishes))

    assert changed is True
    assert enriched[0]["calories"] == 460
    assert enriched[0]["protein"] == 30.0
    assert enriched[0]["fat"] == 12.0
    assert enriched[0]["carbs"] == 34.0
    assert enriched[0]["nutrition_source"] == "RAG"
    assert enriched[0]["nutrition_confidence"] == 0.9


class FakeMeal:
    def __init__(
        self,
        *,
        meal_id: str,
        user_id: str,
        plan_date: date,
        meal_type: str,
        dishes: list[dict],
        total_calories=None,
        total_protein=None,
        total_fat=None,
        total_carbs=None,
        notes=None,
    ):
        self.id = meal_id
        self.user_id = user_id
        self.plan_date = plan_date
        self.meal_type = meal_type
        self.dishes = dishes
        self.total_calories = total_calories
        self.total_protein = total_protein
        self.total_fat = total_fat
        self.total_carbs = total_carbs
        self.notes = notes

    def to_dict(self):
        return {
            "id": str(self.id),
            "plan_date": self.plan_date.isoformat(),
            "meal_type": self.meal_type,
            "dishes": deepcopy(self.dishes),
            "total_calories": self.total_calories,
            "total_protein": self.total_protein,
            "total_fat": self.total_fat,
            "total_carbs": self.total_carbs,
            "notes": self.notes,
        }


class FakeDietRepoForNutrition:
    def __init__(self):
        self.meals_by_id: dict[str, FakeMeal] = {}
        self.updated_count = 0

    async def add_meal_to_plan(self, **kwargs):
        meal_id = str(uuid.uuid4())
        meal = FakeMeal(
            meal_id=meal_id,
            user_id=kwargs["user_id"],
            plan_date=kwargs["plan_date"],
            meal_type=kwargs["meal_type"],
            dishes=kwargs.get("dishes") or [],
            total_calories=kwargs.get("total_calories"),
            total_protein=kwargs.get("total_protein"),
            total_fat=kwargs.get("total_fat"),
            total_carbs=kwargs.get("total_carbs"),
            notes=kwargs.get("notes"),
        )
        self.meals_by_id[meal_id] = meal
        return meal

    async def get_plan_meals_by_week(self, user_id: str, week_start_date: date):
        return [meal for meal in self.meals_by_id.values() if meal.user_id == user_id]

    async def update_meal(self, meal_id: str, **kwargs):
        meal = self.meals_by_id.get(str(meal_id))
        if not meal:
            return None
        if "dishes" in kwargs:
            meal.dishes = kwargs["dishes"]
        if "total_calories" in kwargs:
            meal.total_calories = kwargs["total_calories"]
        if "total_protein" in kwargs:
            meal.total_protein = kwargs["total_protein"]
        if "total_fat" in kwargs:
            meal.total_fat = kwargs["total_fat"]
        if "total_carbs" in kwargs:
            meal.total_carbs = kwargs["total_carbs"]
        self.updated_count += 1
        return meal

    async def get_meal(self, meal_id: str):
        return self.meals_by_id.get(str(meal_id))


def test_add_meal_graceful_when_completion_fails(monkeypatch):
    repo = FakeDietRepoForNutrition()
    service = DietService(repository=repo)

    async def raise_error(*args, **kwargs):
        raise RuntimeError("nutrition backend unavailable")

    from app.diet import nutrition_completion_service as completion_module

    monkeypatch.setattr(
        completion_module.nutrition_completion_service,
        "complete_dishes",
        raise_error,
    )

    result = run(
        service.add_meal(
            user_id="u1",
            plan_date=date.today(),
            meal_type="lunch",
            dishes=[{"name": "牛肉饭", "calories": 520}],
            notes="test",
        )
    )

    assert result["dishes"][0]["name"] == "牛肉饭"
    assert result["total_calories"] == 520


def test_get_plan_by_week_backfills_missing_nutrition(monkeypatch):
    repo = FakeDietRepoForNutrition()
    meal = FakeMeal(
        meal_id=str(uuid.uuid4()),
        user_id="u1",
        plan_date=date.today(),
        meal_type="dinner",
        dishes=[{"name": "豆腐蔬菜碗", "calories": 380, "protein": None, "fat": None, "carbs": None}],
        total_calories=380,
        total_protein=None,
        total_fat=None,
        total_carbs=None,
    )
    repo.meals_by_id[str(meal.id)] = meal

    service = DietService(repository=repo)

    async def fake_complete(*, user_id: str, dishes: list[dict]):
        enriched = deepcopy(dishes)
        enriched[0]["protein"] = 18.0
        enriched[0]["fat"] = 11.0
        enriched[0]["carbs"] = 42.0
        enriched[0]["nutrition_source"] = "RAG"
        enriched[0]["nutrition_confidence"] = 0.84
        return enriched, True

    from app.diet import nutrition_completion_service as completion_module

    monkeypatch.setattr(
        completion_module.nutrition_completion_service,
        "complete_dishes",
        fake_complete,
    )

    plan = run(service.get_plan_by_week("u1", date.today()))
    assert plan is not None
    assert repo.updated_count == 1
    returned_meal = plan["meals"][0]
    assert returned_meal["dishes"][0]["protein"] == 18.0
    assert returned_meal["total_protein"] == 18.0

