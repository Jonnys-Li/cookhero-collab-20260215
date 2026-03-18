import uuid
from datetime import datetime

import pytest

from app.diet.service import DietService


class FakePreference:
    def __init__(self, user_id: str):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.common_foods = []
        self.avoided_foods = []
        self.diet_tags = []
        self.avg_daily_calories_min = None
        self.avg_daily_calories_max = None
        self.deviation_patterns = []
        self.stats = {}
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        stats = self.stats or {}
        goals = stats.get("goals", {}) if isinstance(stats, dict) else {}
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "common_foods": self.common_foods,
            "avoided_foods": self.avoided_foods,
            "diet_tags": self.diet_tags,
            "avg_daily_calories_min": self.avg_daily_calories_min,
            "avg_daily_calories_max": self.avg_daily_calories_max,
            "deviation_patterns": self.deviation_patterns,
            "stats": stats,
            "calorie_goal": goals.get("calorie_goal"),
            "protein_goal": goals.get("protein_goal"),
            "fat_goal": goals.get("fat_goal"),
            "carbs_goal": goals.get("carbs_goal"),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class FakeDietRepository:
    def __init__(self):
        self.preferences: dict[str, FakePreference] = {}

    async def get_user_preference(self, user_id: str):
        return self.preferences.get(user_id)

    async def get_log_items_by_date_range(self, user_id: str, start_date, end_date):
        return []

    async def upsert_user_preference(self, user_id: str, **kwargs):
        pref = self.preferences.get(user_id)
        if not pref:
            pref = FakePreference(user_id)
            self.preferences[user_id] = pref

        for key, value in kwargs.items():
            if hasattr(pref, key):
                setattr(pref, key, value)
        pref.updated_at = datetime.utcnow()
        return pref


def test_update_preferences_persists_metabolic_profile_and_estimate(run):
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    result = run(
        service.update_user_preference(
            "u1",
            age=30,
            biological_sex="male",
            height_cm=180,
            weight_kg=80,
            activity_level="moderate",
            goal_intent="maintain",
        )
    )

    stored_profile = repo.preferences["u1"].stats["metabolic_profile"]
    assert stored_profile == {
        "age": 30,
        "biological_sex": "male",
        "height_cm": 180.0,
        "weight_kg": 80.0,
        "activity_level": "moderate",
        "goal_intent": "maintain",
    }
    assert result["metabolic_profile"] == stored_profile
    assert result["metabolic_estimate"] == {
        "formula": "mifflin_st_jeor",
        "bmr_kcal": 1780,
        "tdee_kcal": 2760,
        "activity_factor": 1.55,
        "goal_adjustment_kcal": 0,
        "recommended_calorie_goal": 2760,
        "goal_intent": "maintain",
        "is_complete": True,
    }


def test_get_user_preference_exposes_metabolic_estimate(run):
    repo = FakeDietRepository()
    repo.preferences["u1"] = FakePreference("u1")
    repo.preferences["u1"].stats = {
        "metabolic_profile": {
            "age": 26,
            "biological_sex": "female",
            "height_cm": 165,
            "weight_kg": 58,
            "activity_level": "light",
            "goal_intent": "fat_loss",
        }
    }
    service = DietService(repository=repo)

    result = run(service.get_user_preference("u1"))

    assert result["metabolic_profile"]["age"] == 26
    assert result["metabolic_estimate"]["bmr_kcal"] == 1320
    assert result["metabolic_estimate"]["tdee_kcal"] == 1820
    assert result["metabolic_estimate"]["recommended_calorie_goal"] == 1370


def test_use_estimated_calorie_goal_writes_goal_and_source(run):
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    result = run(
        service.update_user_preference(
            "u1",
            age=30,
            biological_sex="male",
            height_cm=180,
            weight_kg=80,
            activity_level="moderate",
            goal_intent="fat_loss",
            use_estimated_calorie_goal=True,
        )
    )

    goals = repo.preferences["u1"].stats["goals"]
    goals_meta = repo.preferences["u1"].stats["goals_meta"]
    budget = run(service.get_today_budget("u1"))

    assert goals["calorie_goal"] == 2310
    assert goals_meta["calorie_goal_source"] == "tdee_estimate"
    assert goals_meta["calorie_goal_seeded"] is False
    assert budget["goal_source"] == "tdee_estimate"
    assert budget["base_goal"] == 2310
    assert result["calorie_goal"] == 2310
    assert result["metabolic_estimate"]["recommended_calorie_goal"] == 2310


def test_use_estimated_calorie_goal_requires_complete_profile(run):
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    with pytest.raises(ValueError, match="代谢画像未填写完整"):
        run(
            service.update_user_preference(
                "u1",
                age=30,
                height_cm=180,
                weight_kg=80,
                use_estimated_calorie_goal=True,
            )
        )


def test_incomplete_metabolic_profile_falls_back_to_default_budget(run):
    repo = FakeDietRepository()
    service = DietService(repository=repo)

    result = run(
        service.update_user_preference(
            "u1",
            age=30,
            height_cm=180,
            weight_kg=80,
        )
    )
    budget = run(service.get_today_budget("u1"))

    assert result["metabolic_profile"] == {
        "age": 30,
        "height_cm": 180.0,
        "weight_kg": 80.0,
    }
    assert result["metabolic_estimate"] is None
    assert budget["goal_source"] == "default1800"
    assert budget["base_goal"] == 1800
