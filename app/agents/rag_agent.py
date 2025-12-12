# app/agents/rag_agent.py
"""
RAG 检索 Agent

专注于从知识库检索信息：
- 菜谱检索
- 烹饪技巧查询
- 食材知识查询

这是一个轻量级 Agent，主要封装 RAG 工具，
为其他 Agent 提供知识检索服务。
"""

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, AgentContext, AgentPlan
from app.cards.base import BaseCard, CardType, CardStatus
from app.tools.rag import RAGTool, RAGQueryInput, RAGQueryResult, RecipeItem


class RAGResultCard(BaseCard):
    """
    RAG 检索结果卡片
    
    封装 RAG 检索结果，便于被其他 Agent 消费
    """
    card_type: CardType = Field(default=CardType.RECIPE)
    
    # 查询信息
    query: str = Field(..., description="原始查询")
    
    # 结果
    recipes: List[RecipeItem] = Field(default_factory=list)
    tips: List[str] = Field(default_factory=list, description="烹饪技巧")
    related_info: List[str] = Field(default_factory=list, description="相关信息")
    
    # 元信息
    total_found: int = 0
    search_time_ms: Optional[float] = None
    
    # 回答（如果是问答类查询）
    answer: Optional[str] = Field(None, description="基于检索结果生成的回答")
    
    def to_summary(self) -> str:
        if self.recipes:
            recipe_names = ", ".join(r.name for r in self.recipes[:3])
            return f"[检索结果] {self.query} → {recipe_names} 等{self.total_found}个结果"
        elif self.answer:
            return f"[回答] {self.answer[:100]}..."
        else:
            return f"[检索] {self.query} → 无结果"


class RAGAgent(BaseAgent[RAGResultCard]):
    """
    RAG 检索 Agent
    
    职责：
    1. 理解用户查询意图
    2. 构建合适的检索查询
    3. 检索并整理结果
    4. 如需要，基于检索结果生成回答
    """
    
    name = "rag_agent"
    description = "知识检索，从菜谱库和烹饪知识库中检索相关信息"
    output_card_type = RAGResultCard
    
    def __init__(self, llm=None, rag_tool: Optional[RAGTool] = None):
        super().__init__(llm=llm)
        self.rag_tool = rag_tool or RAGTool()
        self._tools = [self.rag_tool]
    
    async def plan(self, task: str, context: AgentContext) -> AgentPlan:
        """规划检索步骤"""
        
        # 分析查询类型
        is_recipe_search = any(kw in task for kw in ["菜谱", "做法", "怎么做", "食谱", "推荐"])
        is_question = any(kw in task for kw in ["什么", "为什么", "如何", "怎样", "？"])
        
        steps = ["1. 解析用户查询意图"]
        
        if is_recipe_search:
            steps.extend([
                "2. 检索匹配的菜谱",
                "3. 按相关性排序结果",
                "4. 提取关键信息（食材、步骤、营养）",
            ])
        elif is_question:
            steps.extend([
                "2. 检索相关知识",
                "3. 整合检索结果",
                "4. 生成回答",
            ])
        else:
            steps.extend([
                "2. 执行通用检索",
                "3. 整理返回结果",
            ])
        
        return AgentPlan(
            plan_id=f"rag_plan_{uuid.uuid4().hex[:8]}",
            steps=steps,
            tools_needed=["rag_query"],
            reasoning=f"用户查询: {task[:50]}...",
        )
    
    async def execute(self, plan: AgentPlan, context: AgentContext) -> RAGResultCard:
        """执行检索"""
        
        # 从 plan 中获取原始查询（这里简化处理，实际应从 task 传入）
        query = plan.reasoning.replace("用户查询: ", "").rstrip("...")
        
        # 构建检索输入
        exclude_ingredients = []
        for restriction in context.preferences.get("dietary_restrictions", []):
            if ":" in restriction:
                ingredient = restriction.split(":")[-1].strip()
                exclude_ingredients.append(ingredient)
        
        rag_input = RAGQueryInput(
            query=query,
            exclude_ingredients=exclude_ingredients,
            top_k=5,
        )
        
        # 执行检索
        rag_result = await self.rag_tool.execute(rag_input)
        
        # 构建结果卡片
        result_card = RAGResultCard(
            card_id=f"rag_result_{uuid.uuid4().hex[:8]}",
            user_id=context.user_id,
            query=query,
            recipes=rag_result.recipes,
            total_found=rag_result.total_found,
            search_time_ms=rag_result.search_time_ms,
            source_agent=self.name,
        )
        
        # 如果有结果且有 LLM，可以生成回答
        if rag_result.recipes and self.llm:
            # TODO: 使用 LLM 生成回答
            pass
        
        return result_card
    
    async def search_recipes(
        self,
        query: str,
        context: AgentContext,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> List[RecipeItem]:
        """
        便捷方法：直接搜索菜谱
        
        供其他 Agent 调用
        """
        exclude_ingredients = []
        for restriction in context.preferences.get("dietary_restrictions", []):
            if ":" in restriction:
                ingredient = restriction.split(":")[-1].strip()
                exclude_ingredients.append(ingredient)
        
        rag_input = RAGQueryInput(
            query=query,
            exclude_ingredients=exclude_ingredients,
            category=category,
            top_k=top_k,
        )
        
        result = await self.rag_tool.execute(rag_input)
        return result.recipes
    
    async def answer_question(
        self,
        question: str,
        context: AgentContext,
    ) -> str:
        """
        便捷方法：回答问题
        
        基于 RAG 检索生成回答
        """
        # 检索相关内容
        rag_input = RAGQueryInput(query=question, top_k=3)
        result = await self.rag_tool.execute(rag_input)
        
        if not result.recipes:
            return "抱歉，我没有找到相关信息。"
        
        # 简单的回答生成（无 LLM 时的降级方案）
        if not self.llm:
            contents = []
            for recipe in result.recipes[:2]:
                if recipe.raw_content:
                    contents.append(f"【{recipe.name}】\n{recipe.raw_content[:500]}...")
            
            return "\n\n".join(contents) if contents else "找到了一些相关菜谱，但无法生成详细回答。"
        
        # TODO: 使用 LLM 生成结构化回答
        return f"根据检索到的 {len(result.recipes)} 个相关结果..."
    
    def get_system_prompt(self, context: AgentContext) -> str:
        """生成 RAG Agent 的系统提示词"""
        return f"""你是 CookHero 的知识检索助手，专注于从菜谱库和烹饪知识库中检索信息。

{context.to_prompt_context()}

你的职责：
1. 理解用户的查询意图
2. 从知识库中检索最相关的信息
3. 整理并呈现检索结果
4. 必要时基于检索结果生成回答

检索范围：
- 菜谱（HowToCook 仓库）
- 烹饪技巧和经验
- 食材知识

输出要求：
- 优先返回最相关的结果
- 包含菜谱名称、主要食材、烹饪时间等关键信息
- 如用户有饮食限制，排除不合适的结果
"""
