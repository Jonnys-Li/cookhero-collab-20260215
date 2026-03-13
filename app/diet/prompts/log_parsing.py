"""饮食记录解析提示词."""

DIET_LOG_SYSTEM_PROMPT = """你是专业的饮食记录解析助手。
任务：从用户描述或图片中识别食物并输出结构化 JSON。
要求：只输出 JSON，不要解释。"""

DIET_LOG_IMAGE_PROMPT_TEMPLATE = """你将收到用户的饮食图片{extra_text}。
请识别其中的食物，并输出严格 JSON：
{{
  "meal_type": "breakfast/lunch/dinner/snack 或 null",
  "items": [
    {{
      "food_name": "食物名称（中文）",
      "weight_g": 数值或 null,
      "unit": "份/个/碗等单位或 null",
      "calories": 数值或 null,
      "protein": 数值或 null,
      "fat": 数值或 null,
      "carbs": 数值或 null
    }}
  ]
}}

规则：
1. 能区分多个食物时，必须拆分为多个 items。
2. 如果 `weight_g` 或 `unit` 不为 null，则 `calories/protein/fat/carbs` 必须给出**数值**（不要填 null；可合理估算，但不要填 0）。
3. 如果 `weight_g` 和 `unit` 都为 null，则 `calories/protein/fat/carbs` 允许为 null（表示需要用户补充分量后再估算）。
4. meal_type 无法判断则为 null。
5. food_name 尽量具体，例如“红烧牛肉”“白米饭”。
6. 只输出 JSON，不要追加说明。"""

DIET_LOG_TEXT_PROMPT_TEMPLATE = """请解析用户的饮食描述并输出严格 JSON。

用户描述：{text}

输出格式：
{{
  "meal_type": "breakfast/lunch/dinner/snack 或 null",
  "items": [
    {{
      "food_name": "食物名称（中文）",
      "weight_g": 数值或 null,
      "unit": "份/个/碗等单位或 null",
      "calories": 数值或 null,
      "protein": 数值或 null,
      "fat": 数值或 null,
      "carbs": 数值或 null
    }}
  ]
}}

规则：
1. 明显有多个食物时，必须拆分为多个 items。
2. meal_type 可从时间或食物类型推断，无法判断则为 null。
3. 如果 `weight_g` 或 `unit` 不为 null，则 `calories/protein/fat/carbs` 必须给出**数值**（不要填 null；可合理估算，但不要填 0）。
4. 如果 `weight_g` 和 `unit` 都为 null，则 `calories/protein/fat/carbs` 允许为 null（表示需要用户补充分量后再估算）。
5. 只输出 JSON，不要追加说明。"""
