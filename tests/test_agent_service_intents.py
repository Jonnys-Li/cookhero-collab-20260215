from __future__ import annotations

from datetime import datetime

from app.agent.service_intents import (
    calculate_nutrition_totals,
    extract_log_items_from_vision_analysis,
    extract_simple_food_items_from_text,
    format_nutrition_totals_text,
    has_concrete_food_quantity,
    infer_meal_type_for_log,
    is_diet_log_query,
    is_diet_nutrition_query,
    is_meal_plan_query,
)


def test_is_meal_plan_query_basic():
    assert is_meal_plan_query("帮我做一周饮食计划") is True
    assert is_meal_plan_query("我想要7天备餐方案") is True
    assert is_meal_plan_query("鸡胸肉热量是多少") is False


def test_is_diet_log_query_basic():
    assert is_diet_log_query("帮我记录今天的午餐") is True
    assert is_diet_log_query("把这餐加到饮食管理") is True
    assert is_diet_log_query("鸡胸肉热量是多少") is False


def test_has_concrete_food_quantity():
    assert has_concrete_food_quantity("鸡胸肉 200g") is True
    assert has_concrete_food_quantity("米饭 1 碗") is True
    assert has_concrete_food_quantity("鸡胸肉热量是多少") is False


def test_is_diet_nutrition_query_requires_quantity_and_keywords():
    assert is_diet_nutrition_query("20g 鸡胸肉多少卡路里？") is True
    assert is_diet_nutrition_query("鸡胸肉热量多少？") is False
    # Exclude budget/goal questions
    assert is_diet_nutrition_query("预算 200 kcal 还剩多少？") is False


def test_extract_simple_food_items_from_text_parses_two_orders():
    items1 = extract_simple_food_items_from_text("鸡胸肉 20g")
    assert items1 and items1[0]["food_name"] == "鸡胸肉"
    assert items1[0]["weight_g"] == 20.0

    items2 = extract_simple_food_items_from_text("20g 鸡胸肉")
    assert items2 and items2[0]["food_name"] == "鸡胸肉"
    assert items2[0]["weight_g"] == 20.0


def test_calculate_nutrition_totals_sums_and_ignores_missing_or_non_positive():
    totals = calculate_nutrition_totals(
        [
            {"calories": 100, "protein": 10, "fat": 3, "carbs": 1},
            {"calories": 50, "protein": None, "fat": 0, "carbs": 2},
            {"calories": -10, "protein": 1, "fat": 1, "carbs": 1},
        ]
    )
    assert totals["calories"] == 150.0
    assert totals["protein"] == 11.0
    assert totals["fat"] == 4.0
    assert totals["carbs"] == 4.0


def test_format_nutrition_totals_text_includes_kj_when_requested():
    text = format_nutrition_totals_text(
        {"calories": 120.0, "protein": 20.0, "fat": 3.0, "carbs": 1.0},
        include_kj=True,
    )
    assert "kcal" in text
    assert "kJ" in text
    assert "P" in text and "F" in text and "C" in text


def test_infer_meal_type_for_log_accepts_explicit_and_fallback_by_time():
    assert infer_meal_type_for_log("lunch") == "lunch"
    assert infer_meal_type_for_log(None, now=datetime(2024, 1, 1, 9, 0, 0)) == "breakfast"
    assert infer_meal_type_for_log(None, now=datetime(2024, 1, 1, 12, 0, 0)) == "lunch"
    assert infer_meal_type_for_log(None, now=datetime(2024, 1, 1, 18, 0, 0)) == "dinner"
    assert infer_meal_type_for_log(None, now=datetime(2024, 1, 1, 23, 0, 0)) == "snack"


def test_extract_log_items_from_vision_analysis_normalizes_types_and_filters_invalid():
    items = extract_log_items_from_vision_analysis(
        {
            "items": [
                {
                    "food_name": "鸡胸肉",
                    "weight_g": "200",
                    "unit": "g",
                    "calories": "300",
                    "protein": "40.5",
                    "fat": None,
                    "carbs": 1,
                },
                {"food_name": "", "weight_g": 10},
                "not-a-dict",
            ]
        }
    )
    assert len(items) == 1
    item = items[0]
    assert item["food_name"] == "鸡胸肉"
    assert item["weight_g"] == 200.0
    assert item["calories"] == 300
    assert item["protein"] == 40.5

