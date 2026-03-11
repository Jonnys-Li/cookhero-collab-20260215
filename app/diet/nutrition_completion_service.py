"""
Nutrition completion service for diet plan dishes.

Uses RAG retrieval as primary signal and an LLM parser to extract
calories/protein/fat/carbs for dishes with missing nutrition fields.
"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from typing import Any, Optional

logger = logging.getLogger(__name__)

NUTRITION_FIELDS = ("calories", "protein", "fat", "carbs")
MIN_CONFIDENCE = 0.55
MAX_CONTEXT_CHARS = 1800


class NutritionCompletionService:
    """Resolve missing nutrition metrics for dishes from RAG context."""

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None

    @staticmethod
    def _extract_json(content: str) -> Optional[dict[str, Any]]:
        text = (content or "").strip()
        if not text:
            return None

        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]

        try:
            payload = json.loads(text.strip())
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _normalize_candidate(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        out: dict[str, Any] = {}
        for field in NUTRITION_FIELDS:
            raw = payload.get(field)
            if raw is None:
                continue
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                continue
            if numeric <= 0:
                continue
            if field == "calories":
                out[field] = int(round(numeric))
            else:
                out[field] = round(numeric, 1)

        confidence = payload.get("confidence")
        if confidence is not None:
            try:
                conf = float(confidence)
                out["confidence"] = max(0.0, min(1.0, conf))
            except (TypeError, ValueError):
                pass

        return out if any(field in out for field in NUTRITION_FIELDS) else None

    async def _retrieve_context(
        self,
        *,
        dish_name: str,
        user_id: str,
    ) -> Optional[str]:
        try:
            from app.services.rag_service import rag_service_instance

            retrieval = await rag_service_instance.retrieve(
                query=f"{dish_name} 营养成分 热量 蛋白质 脂肪 碳水",
                skip_rewrite=True,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("RAG retrieval failed for nutrition lookup: %s", exc)
            return None

        context = (retrieval.context or "").strip()
        if not context:
            return None
        return context[:MAX_CONTEXT_CHARS]

    async def _extract_nutrition(
        self,
        *,
        dish_name: str,
        context: str,
    ) -> Optional[dict[str, Any]]:
        try:
            from app.config import settings
            from app.llm.provider import LLMProvider

            provider = LLMProvider(settings.llm)
            invoker = provider.create_invoker("fast", temperature=0.1, streaming=False)
        except Exception as exc:
            logger.warning("LLM provider unavailable for nutrition extraction: %s", exc)
            return None

        system_prompt = (
            "你是食物营养信息提取器。"
            "只基于提供上下文输出 JSON，不要补充解释。"
        )
        user_prompt = (
            "请根据上下文提取菜品营养值。"
            "若无法确定字段请返回 null。\n\n"
            f"菜品：{dish_name}\n"
            f"上下文：{context}\n\n"
            "输出 JSON："
            '{"calories": number|null, "protein": number|null, '
            '"fat": number|null, "carbs": number|null, "confidence": number}'
        )

        try:
            response = await invoker.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception as exc:
            logger.warning("LLM extraction failed for dish '%s': %s", dish_name, exc)
            return None

        raw_content = getattr(response, "content", response)
        payload = self._extract_json(str(raw_content))
        if not payload:
            return None
        return self._normalize_candidate(payload)

    async def _resolve_dish_nutrition(
        self,
        *,
        dish_name: str,
        user_id: str,
    ) -> Optional[dict[str, Any]]:
        context = await self._retrieve_context(dish_name=dish_name, user_id=user_id)
        if not context:
            return None
        candidate = await self._extract_nutrition(dish_name=dish_name, context=context)
        if not candidate:
            return None

        confidence = candidate.get("confidence")
        if isinstance(confidence, float) and confidence < MIN_CONFIDENCE:
            return None
        return candidate

    async def complete_dishes(
        self,
        *,
        user_id: str,
        dishes: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        normalized = [deepcopy(dish) if isinstance(dish, dict) else {} for dish in dishes]
        changed = False
        cache: dict[str, Optional[dict[str, Any]]] = {}

        for dish in normalized:
            dish_name = str(dish.get("name") or "").strip()
            if not dish_name:
                continue

            missing_fields = [
                field for field in NUTRITION_FIELDS if self._is_missing(dish.get(field))
            ]
            if not missing_fields:
                continue

            cache_key = dish_name.lower()
            if cache_key not in cache:
                cache[cache_key] = await self._resolve_dish_nutrition(
                    dish_name=dish_name,
                    user_id=user_id,
                )
            candidate = cache.get(cache_key)
            if not candidate:
                continue

            local_change = False
            for field in missing_fields:
                value = candidate.get(field)
                if value is None:
                    continue
                dish[field] = value
                local_change = True

            if local_change:
                dish["nutrition_source"] = "RAG"
                confidence = candidate.get("confidence")
                if isinstance(confidence, float):
                    dish["nutrition_confidence"] = round(confidence, 2)
                changed = True

        return normalized, changed


nutrition_completion_service = NutritionCompletionService()

