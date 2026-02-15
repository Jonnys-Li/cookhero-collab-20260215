# app/agent/subagents/builtin/cooking_master.py
"""
CookingMasterSubagent - 烹饪大师 Subagent

专业的烹饪指导助手，提供食谱推荐、烹饪技巧、食材替换建议等。
"""

import logging
from typing import Awaitable, Callable, Optional

from app.agent.subagents.base import BaseSubagent, SubagentConfig
from app.agent.types import TraceStep, ToolResult

logger = logging.getLogger(__name__)


COOKING_MASTER_SYSTEM_PROMPT = """你是 CookHero 的烹饪大师，专注于为用户提供专业的烹饪指导和食谱推荐。

## 你的专业能力

1. **食谱知识**：精通各大菜系的经典菜品和创新菜品，包括中式、西式、日式、韩式等
2. **烹饪技巧**：掌握各种烹饪方法和技巧，如煎、炒、烹、炸、炖、煮、蒸、烤等
3. **食材知识**：了解食材的营养价值、搭配禁忌、选购技巧和保存方法
4. **个性化推荐**：能根据用户的口味偏好、厨艺水平、可用食材提供定制化建议
5. **问题诊断**：能够诊断烹饪过程中遇到的问题并提供解决方案

## 工作流程

1. **需求分析**：理解用户的具体需求
   - 找食谱（特定菜品或食材）
   - 学技巧（烹饪方法、刀工等）
   - 解决烹饪问题（为什么失败、如何改进）
   - 食材替换（缺少某种食材时的替代方案）

2. **信息收集**：如需要，使用 `web_search` 搜索：
   - 最新的食谱和烹饪技巧
   - 当季推荐食材
   - 营养搭配建议
   - 特殊饮食需求的烹饪方案

3. **个性化调整**：根据用户的以下信息调整建议
   - 饮食偏好和限制
   - 过敏原
   - 厨艺水平
   - 可用厨具

4. **清晰输出**：提供结构化、易于理解和执行的烹饪指导

## 输出格式

请以结构化的方式输出内容：

1. **菜品/技巧名称**：清晰标识主题
2. **食材清单**：列出所需食材及用量（含替换建议）
3. **详细步骤**：分步骤说明操作流程，标注关键技巧
4. **小贴士**：提供实用的烹饪技巧和注意事项
5. **营养信息**：如相关，提供简单的营养分析
6. **常见问题**：预测可能遇到的问题并提供解决方案

## 注意事项

- 优先考虑用户的过敏原和饮食限制
- 提供实用的食材替代建议
- 考虑用户的厨艺水平，提供难度适中的建议
- 对于复杂的技巧，提供分层次的指导（基础版+进阶版）
- 使用中文输出，便于用户理解
- 搜索时使用中文关键词以获取更相关的资料

最终结果输出要求：
- 回答中不要包含任何工具调用的痕迹或格式
- 回答不能只是工具调用结果，必须结合上下文和用户的需求进行总结和建议
- 一定要使用 Markdown 格式，方便用户阅读和理解"""


class CookingMasterSubagent(BaseSubagent):
    """
    烹饪大师 Subagent。

    主要功能：
    - 提供专业的食谱推荐
    - 解答烹饪技巧问题
    - 提供食材替换建议
    - 诊断和解决烹饪问题

    可用工具：
    - datetime: 获取当前日期和季节信息
    - web_search: 搜索食谱、烹饪技巧、食材信息
    - diet_analysis: 获取用户饮食偏好和限制
    """

    @classmethod
    def get_default_config(cls) -> SubagentConfig:
        """获取默认配置。"""
        return SubagentConfig(
            name="cooking_master",
            display_name="烹饪大师",
            description=(
                "专业烹饪指导助手，提供个性化食谱推荐、烹饪技巧讲解、"
                "食材替换建议，以及烹饪问题诊断和解决方案。"
            ),
            system_prompt=COOKING_MASTER_SYSTEM_PROMPT,
            tools=["datetime", "web_search", "diet_analysis"],
            max_iterations=12,
            enabled=True,
            builtin=True,
            category="cooking",
        )

    async def execute(
        self,
        task: str,
        user_id: Optional[str] = None,
        background: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        执行烹饪指导任务。

        Args:
            task: 任务描述（如 "怎么做红烧肉" 或 "鸡蛋可以用什么替代"）
            user_id: 用户 ID
            background: 额外背景信息

        Returns:
            ToolResult: 包含烹饪指导的结果
        """
        enriched_context: dict = {}

        if user_id:
            try:
                # 获取用户基本信息
                from app.services.user_service import user_service

                user_data = await user_service.get_user_by_id(user_id)
                if user_data and hasattr(user_data, 'profile') and user_data.profile:
                    enriched_context["user_profile"] = user_data.profile

                # 获取用户饮食偏好
                from app.diet.service import diet_service

                preferences = await diet_service.get_user_preference(user_id)
                if preferences:
                    enriched_context["user_preferences"] = preferences

            except Exception as e:
                logger.warning(f"Failed to get user context for cooking master: {e}")

        # 组装背景信息
        combined_background = self._build_background(background, enriched_context)

        # 执行任务
        return await self.run_with_tools(
            task=task,
            user_id=user_id,
            background=combined_background,
            event_handler=event_handler,
        )

    def _build_background(self, base: Optional[str], context: dict) -> Optional[str]:
        """
        构建背景信息，添加用户上下文。

        Args:
            base: 基础背景信息
            context: 上下文信息

        Returns:
            组合后的背景信息
        """
        parts = []

        if base:
            parts.append(base)

        # 添加用户偏好信息
        if context.get("user_preferences"):
            prefs = context["user_preferences"]
            pref_parts = []

            if prefs.get("dietary_restrictions"):
                pref_parts.append(
                    f"饮食限制: {', '.join(prefs['dietary_restrictions'])}"
                )
            if prefs.get("allergies"):
                pref_parts.append(f"过敏原: {', '.join(prefs['allergies'])}")
            if prefs.get("favorite_cuisines"):
                pref_parts.append(
                    f"喜爱的菜系: {', '.join(prefs['favorite_cuisines'])}"
                )
            avoided_foods = prefs.get("avoided_foods") or prefs.get("disliked_foods")
            if avoided_foods:
                pref_parts.append(f"不喜欢的食物: {', '.join(avoided_foods)}")

            if pref_parts:
                parts.append("## 用户饮食偏好\n" + "\n".join(pref_parts))

        # 添加用户画像
        if context.get("user_profile"):
            parts.append(f"## 用户信息\n{context['user_profile']}")

        if not parts:
            return None

        return "\n\n".join(parts)


# 创建默认配置的实例工厂
def create_cooking_master() -> CookingMasterSubagent:
    """创建默认配置的烹饪大师 Subagent。"""
    config = CookingMasterSubagent.get_default_config()
    return CookingMasterSubagent(config)


__all__ = ["CookingMasterSubagent", "create_cooking_master", "COOKING_MASTER_SYSTEM_PROMPT"]
