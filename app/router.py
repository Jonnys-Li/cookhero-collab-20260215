# app/router.py
"""
意图路由器 - Intent Router

轻量级的意图分类器，负责：
1. 识别用户查询的意图类型
2. 提取关键实体（食材、时间、目标等）
3. 决定应该调用哪些 Agent

阶段一：基于规则的简单分类
阶段二：使用小模型（如 Qwen-1.8B）进行分类
阶段三：可选用大模型进行复杂意图理解
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """意图类型"""
    # 计划类
    DIET_PLAN = "diet_plan"           # 饮食计划
    TRAINING_PLAN = "training_plan"   # 训练计划
    COMBINED_PLAN = "combined_plan"   # 综合计划（饮食+训练）
    MEAL_SUGGESTION = "meal_suggestion"  # 单餐建议
    
    # 查询类
    RECIPE_SEARCH = "recipe_search"   # 菜谱搜索
    NUTRITION_QUERY = "nutrition_query"  # 营养查询
    INGREDIENT_QUERY = "ingredient_query"  # 食材查询
    
    # 问答类
    QUESTION = "question"             # 通用问题
    HOW_TO = "how_to"                 # 怎么做类问题
    
    # 操作类
    MODIFY_PLAN = "modify_plan"       # 修改计划
    FEEDBACK = "feedback"             # 用户反馈
    
    # 其他
    GREETING = "greeting"             # 问候
    UNKNOWN = "unknown"               # 未知意图


class Intent(BaseModel):
    """意图识别结果"""
    intent_type: IntentType
    confidence: float = Field(default=1.0, ge=0, le=1)
    
    # 提取的实体
    entities: Dict[str, Any] = Field(default_factory=dict)
    
    # 原始输入
    original_query: str = ""
    
    # 子意图（用于复杂查询）
    sub_intents: List["Intent"] = Field(default_factory=list)
    
    # 推理过程（可选，用于调试）
    reasoning: Optional[str] = None


class IntentRouter:
    """
    意图路由器
    
    基于规则的意图分类（阶段一实现）
    """
    
    def __init__(self, llm=None):
        """
        Args:
            llm: 可选的 LLM，用于复杂意图理解
        """
        self.llm = llm
        
        # 意图关键词映射
        self._intent_patterns = {
            IntentType.DIET_PLAN: [
                r"饮食计划", r"餐饮计划", r"周食谱", r"一周.*吃",
                r"减脂餐", r"增肌餐", r"健康饮食",
                r"规划.*饮食", r"安排.*吃什么",
            ],
            IntentType.TRAINING_PLAN: [
                r"训练计划", r"健身计划", r"运动计划",
                r"跑步计划", r"增肌训练", r"减脂训练",
            ],
            IntentType.COMBINED_PLAN: [
                r"(饮食|吃).*(训练|运动|健身)",
                r"(训练|运动|健身).*(饮食|吃)",
                r"生活计划", r"一周安排",
            ],
            IntentType.MEAL_SUGGESTION: [
                r"今天吃什么", r"推荐.*菜", r"午餐吃什么",
                r"晚餐建议", r"早餐推荐", r"吃点什么",
            ],
            IntentType.RECIPE_SEARCH: [
                r"菜谱", r"食谱", r"做法", r"怎么做.*菜",
                r".*的做法", r"教我做", r"学做",
            ],
            IntentType.NUTRITION_QUERY: [
                r"热量", r"卡路里", r"营养", r"蛋白质",
                r"碳水", r"脂肪", r".*多少热量",
            ],
            IntentType.INGREDIENT_QUERY: [
                r"食材", r".*能做什么菜", r".*可以做什么",
                r".*替代", r"代替.*",
            ],
            IntentType.HOW_TO: [
                r"怎么", r"如何", r"怎样", r"方法",
            ],
            IntentType.QUESTION: [
                r"什么是", r"为什么", r"是什么", r"\?", r"？",
            ],
            IntentType.MODIFY_PLAN: [
                r"修改", r"调整", r"换一个", r"不想吃",
                r"更改", r"替换",
            ],
            IntentType.FEEDBACK: [
                r"好吃", r"难吃", r"喜欢", r"不喜欢",
                r"太.*了", r"很好", r"不错",
            ],
            IntentType.GREETING: [
                r"^你好", r"^hi", r"^hello", r"^嗨",
                r"在吗", r"^早", r"^晚安",
            ],
        }
        
        # 实体提取模式
        self._entity_patterns = {
            "time_period": [
                (r"下?周", "week"),
                (r"今天", "today"),
                (r"明天", "tomorrow"),
                (r"(\d+)[天日]", "days"),
            ],
            "meal_type": [
                (r"早餐|早饭", "breakfast"),
                (r"午餐|午饭|中午", "lunch"),
                (r"晚餐|晚饭|晚上", "dinner"),
                (r"加餐|零食", "snack"),
            ],
            "goal": [
                (r"减脂|减肥|瘦", "weight_loss"),
                (r"增肌|增重", "muscle_gain"),
                (r"健康", "health"),
                (r"马拉松|跑步", "marathon"),
            ],
            "calories": [
                (r"(\d+)\s*(?:kcal|千卡|大卡)", "target_calories"),
            ],
            "protein": [
                (r"蛋白质?\s*(\d+)\s*[gG克]", "target_protein"),
            ],
        }
    
    def classify(self, query: str) -> Intent:
        """
        对用户查询进行意图分类
        
        Args:
            query: 用户输入
        
        Returns:
            Intent 对象
        """
        query = query.lower()
        
        # 尝试匹配各个意图
        matched_intents = []
        
        for intent_type, patterns in self._intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    matched_intents.append(intent_type)
                    break
        
        # 确定主意图
        if not matched_intents:
            intent_type = IntentType.UNKNOWN
        elif len(matched_intents) == 1:
            intent_type = matched_intents[0]
        else:
            # 多个匹配时的优先级
            priority = [
                IntentType.COMBINED_PLAN,
                IntentType.DIET_PLAN,
                IntentType.TRAINING_PLAN,
                IntentType.MEAL_SUGGESTION,
                IntentType.RECIPE_SEARCH,
                IntentType.NUTRITION_QUERY,
            ]
            for p in priority:
                if p in matched_intents:
                    intent_type = p
                    break
            else:
                intent_type = matched_intents[0]
        
        # 提取实体
        entities = self._extract_entities(query)
        
        # 计算置信度（简单实现）
        confidence = 0.9 if intent_type != IntentType.UNKNOWN else 0.3
        
        return Intent(
            intent_type=intent_type,
            confidence=confidence,
            entities=entities,
            original_query=query,
            reasoning=f"匹配到意图: {matched_intents}" if matched_intents else "未匹配到任何意图模式",
        )
    
    def _extract_entities(self, query: str) -> Dict[str, Any]:
        """提取实体"""
        entities = {}
        
        for entity_type, patterns in self._entity_patterns.items():
            for pattern, value in patterns:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    # 如果有捕获组，提取数值
                    if match.groups():
                        entities[entity_type] = {
                            "type": value,
                            "value": match.group(1),
                        }
                    else:
                        entities[entity_type] = value
                    break
        
        return entities
    
    async def classify_with_llm(self, query: str) -> Intent:
        """
        使用 LLM 进行意图分类（阶段二）
        
        更准确但更慢，用于复杂查询
        """
        if not self.llm:
            return self.classify(query)
        
        # TODO: 实现 LLM 意图分类
        # 1. 构建 prompt
        # 2. 调用 LLM
        # 3. 解析响应
        
        return self.classify(query)
    
    def get_required_agents(self, intent: Intent) -> List[str]:
        """
        根据意图返回需要调用的 Agent 列表
        """
        agent_mapping = {
            IntentType.DIET_PLAN: ["rag_agent", "diet_planner"],
            IntentType.TRAINING_PLAN: ["training_planner"],
            IntentType.COMBINED_PLAN: ["rag_agent", "diet_planner", "training_planner"],
            IntentType.MEAL_SUGGESTION: ["rag_agent", "diet_planner"],
            IntentType.RECIPE_SEARCH: ["rag_agent"],
            IntentType.NUTRITION_QUERY: ["nutrition_calculator"],
            IntentType.INGREDIENT_QUERY: ["rag_agent"],
            IntentType.HOW_TO: ["rag_agent"],
            IntentType.QUESTION: ["rag_agent"],
            IntentType.MODIFY_PLAN: ["diet_planner"],
            IntentType.FEEDBACK: [],
            IntentType.GREETING: [],
            IntentType.UNKNOWN: ["rag_agent"],
        }
        
        return agent_mapping.get(intent.intent_type, ["rag_agent"])
