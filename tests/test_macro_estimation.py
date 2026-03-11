from app.diet.macro_estimation import estimate_macros_from_calories


def test_estimate_macros_from_calories_fat_loss():
    macros = estimate_macros_from_calories(1800, "fat_loss")
    assert macros["source"] == "AUTO"
    assert macros["confidence"] == 0.35
    assert macros["protein_g"] == 135.0
    assert macros["fat_g"] == 50.0
    assert macros["carbs_g"] == 202.5


def test_estimate_macros_from_calories_unknown_goal_defaults_to_maintenance():
    macros = estimate_macros_from_calories(1800, "unknown_goal")
    assert macros["protein_g"] == 112.5
    assert macros["fat_g"] == 60.0
    assert macros["carbs_g"] == 202.5


def test_estimate_macros_from_calories_invalid_calories_returns_nulls():
    macros = estimate_macros_from_calories(0, "fat_loss")
    assert macros["protein_g"] is None
    assert macros["fat_g"] is None
    assert macros["carbs_g"] is None

