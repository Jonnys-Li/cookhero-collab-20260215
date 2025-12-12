# app/conductor.py
"""
Conductor - 调度器

多智能体系统的"大脑"，负责：
1. 意图识别 → 决定拉起哪些子 Agent
2. 上下文分发 → 给每个子 Agent 分配独立的子上下文
3. 结果收集 → 收集所有子计划
4. 冲突检测 → 检测子计划之间的冲突
5. 反思循环 → 如有冲突，触发重新规划
6. 结果合并 → 生成最终的综合计划

这是 2026 级 AI-Native 架构的核心组件。
"""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from app.agents.diet_planner import DietPlannerAgent
from app.agents.rag_agent import RAGAgent
from app.cards.base import BaseCard
from app.cards.combined import CombinedLifestylePlanCard
from app.context.profile import UserProfile
from app.context.goals import GoalManager
from app.context.ledger import PreferenceLedger
from app.context.memory import LongTermMemory
from app.router import IntentRouter, Intent, IntentType


class ConductorStatus(str, Enum):
    """Conductor 状态"""
    IDLE = "idle"
    ROUTING = "routing"           # 意图路由中
    DISPATCHING = "dispatching"   # 分发任务中
    EXECUTING = "executing"       # Agent 执行中
    MERGING = "merging"          # 合并结果中
    REFLECTING = "reflecting"     # 反思检查中
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionPlan(BaseModel):
    """执行计划"""
    plan_id: str
    intent: Intent
    agents_to_invoke: List[str] = Field(default_factory=list)
    execution_order: str = Field(default="parallel", description="parallel 或 sequential")
    context_slices: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class ConductorResult(BaseModel):
    """Conductor 执行结果"""
    session_id: str
    status: ConductorStatus
    
    # 意图
    intent: Optional[Intent] = None
    
    # Agent 结果
    agent_results: Dict[str, AgentResult] = Field(default_factory=dict)
    
    # 最终输出
    final_output: Optional[BaseCard] = None
    
    # 冲突和解决
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts_resolved: bool = False
    
    # 元信息
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    
    # 错误
    error: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class Conductor:
    """
    Conductor - 多智能体调度器
    
    使用方式：
    ```python
    conductor = Conductor(user_id="user_001")
    result = await conductor.run("帮我规划下周的减脂饮食计划")
    ```
    """
    
    def __init__(
        self,
        user_id: str,
        user_profile: Optional[UserProfile] = None,
        goal_manager: Optional[GoalManager] = None,
        preference_ledger: Optional[PreferenceLedger] = None,
        memory: Optional[LongTermMemory] = None,
        llm=None,
    ):
        """
        初始化 Conductor
        
        Args:
            user_id: 用户ID
            user_profile: 用户画像（可选，会自动创建默认）
            goal_manager: 目标管理器
            preference_ledger: 偏好账本
            memory: 长期记忆
            llm: LLM 实例
        """
        self.user_id = user_id
        self.llm = llm
        
        # 用户上下文
        self.user_profile = user_profile or UserProfile(user_id=user_id)
        self.goal_manager = goal_manager or GoalManager(user_id=user_id)
        self.preference_ledger = preference_ledger or PreferenceLedger(user_id=user_id)
        self.memory = memory or LongTermMemory(user_id=user_id)
        
        # 意图路由器
        self.router = IntentRouter()
        
        # Agent 注册表
        self._agents: Dict[str, BaseAgent] = {}
        self._register_default_agents()
        
        # 状态
        self.status = ConductorStatus.IDLE
    
    def _register_default_agents(self):
        """注册默认的 Agent"""
        self.register_agent("diet_planner", DietPlannerAgent(llm=self.llm))
        self.register_agent("rag_agent", RAGAgent(llm=self.llm))
        # TODO: 注册更多 Agent
        # self.register_agent("training_planner", TrainingPlannerAgent(llm=self.llm))
        # self.register_agent("nutrition_calculator", NutritionCalculatorAgent(llm=self.llm))
    
    def register_agent(self, name: str, agent: BaseAgent):
        """注册 Agent"""
        self._agents[name] = agent
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """获取 Agent"""
        return self._agents.get(name)
    
    def build_context(self, task: str, intent: Intent) -> AgentContext:
        """
        构建 Agent 上下文
        
        从用户上下文湖中提取相关信息，构建精简的 Agent 上下文
        """
        # 获取相关记忆
        relevant_memories = []
        if self.memory:
            memory_entries = self.memory.search(task, top_k=3)
            relevant_memories = [m.content for m in memory_entries]
        
        # 构建上下文
        context = AgentContext(
            user_id=self.user_id,
            user_profile=self.user_profile.to_context_dict(),
            goals=[g.to_context_dict() for g in self.goal_manager.get_active_goals()[:5]],
            constraints=self.goal_manager.get_merged_constraints(),
            preferences=self.preference_ledger.get_preference_summary(),
            relevant_memories=relevant_memories,
        )
        
        # 根据意图添加特定上下文
        if intent.intent_type == IntentType.DIET_PLAN:
            # 饮食计划需要营养目标
            if self.user_profile.nutrition_targets.daily_calories:
                context.constraints["target_daily_calories"] = self.user_profile.nutrition_targets.daily_calories
            if self.user_profile.nutrition_targets.protein_g:
                context.constraints["min_daily_protein_g"] = self.user_profile.nutrition_targets.protein_g
            
            # 添加饮食限制到偏好
            restrictions = []
            dr = self.user_profile.dietary_restrictions
            restrictions.extend([f"过敏:{a}" for a in dr.allergies])
            restrictions.extend([f"不耐受:{i}" for i in dr.intolerances])
            restrictions.extend([f"不吃:{d}" for d in dr.dislikes])
            context.preferences["dietary_restrictions"] = restrictions
        
        return context
    
    def create_execution_plan(self, task: str, intent: Intent) -> ExecutionPlan:
        """
        创建执行计划
        
        根据意图决定需要调用哪些 Agent
        """
        agents_to_invoke = []
        execution_order = "parallel"
        
        # 根据意图类型决定 Agent
        if intent.intent_type == IntentType.DIET_PLAN:
            agents_to_invoke = ["rag_agent", "diet_planner"]
            execution_order = "sequential"  # RAG 先执行，为 diet_planner 提供数据
        
        elif intent.intent_type == IntentType.TRAINING_PLAN:
            agents_to_invoke = ["training_planner"]
        
        elif intent.intent_type == IntentType.COMBINED_PLAN:
            # 综合计划需要多个 Agent 协作
            agents_to_invoke = ["rag_agent", "diet_planner", "training_planner"]
            execution_order = "parallel"  # 可并行执行
        
        elif intent.intent_type == IntentType.RECIPE_SEARCH:
            agents_to_invoke = ["rag_agent"]
        
        elif intent.intent_type == IntentType.QUESTION:
            agents_to_invoke = ["rag_agent"]
        
        else:
            # 默认使用 RAG Agent
            agents_to_invoke = ["rag_agent"]
        
        # 过滤掉未注册的 Agent
        agents_to_invoke = [a for a in agents_to_invoke if a in self._agents]
        
        return ExecutionPlan(
            plan_id=f"exec_{uuid.uuid4().hex[:8]}",
            intent=intent,
            agents_to_invoke=agents_to_invoke,
            execution_order=execution_order,
        )
    
    async def execute_agents(
        self, 
        task: str,
        plan: ExecutionPlan, 
        context: AgentContext,
    ) -> Dict[str, AgentResult]:
        """
        执行 Agent
        
        根据执行计划调用 Agent，支持并行或顺序执行
        """
        results: Dict[str, AgentResult] = {}
        
        if plan.execution_order == "parallel":
            # 并行执行
            tasks = []
            for agent_name in plan.agents_to_invoke:
                agent = self._agents.get(agent_name)
                if agent:
                    tasks.append(self._run_agent(agent_name, agent, task, context))
            
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, agent_name in enumerate(plan.agents_to_invoke):
                if isinstance(completed[i], Exception):
                    results[agent_name] = AgentResult(
                        agent_name=agent_name,
                        status=AgentStatus.FAILED,
                        error=str(completed[i]),
                    )
                else:
                    results[agent_name] = completed[i]
        
        else:
            # 顺序执行
            for agent_name in plan.agents_to_invoke:
                agent = self._agents.get(agent_name)
                if agent:
                    try:
                        result = await agent.run(task, context)
                        results[agent_name] = result
                        
                        # 将前一个 Agent 的结果传递给下一个
                        if result.output_card:
                            context.sibling_results[agent_name] = {
                                "card_type": result.output_card.card_type.value,
                                "summary": result.output_card.to_summary(),
                            }
                    except Exception as e:
                        results[agent_name] = AgentResult(
                            agent_name=agent_name,
                            status=AgentStatus.FAILED,
                            error=str(e),
                        )
        
        return results
    
    async def _run_agent(
        self, 
        agent_name: str, 
        agent: BaseAgent, 
        task: str, 
        context: AgentContext,
    ) -> AgentResult:
        """运行单个 Agent"""
        return await agent.run(task, context)
    
    def merge_results(
        self, 
        intent: Intent,
        agent_results: Dict[str, AgentResult],
    ) -> Optional[BaseCard]:
        """
        合并多个 Agent 的结果
        
        根据意图类型决定合并策略
        """
        # 如果只有一个 Agent，直接返回其结果
        if len(agent_results) == 1:
            result = list(agent_results.values())[0]
            return result.output_card
        
        # 综合计划：合并饮食和训练计划
        if intent.intent_type == IntentType.COMBINED_PLAN:
            diet_result = agent_results.get("diet_planner")
            training_result = agent_results.get("training_planner")
            
            if diet_result and diet_result.output_card:
                from datetime import date
                
                combined = CombinedLifestylePlanCard(
                    card_id=f"combined_{uuid.uuid4().hex[:8]}",
                    user_id=self.user_id,
                    title=f"综合生活计划",
                    start_date=date.today(),
                    end_date=date.today(),
                    diet_plan=diet_result.output_card if hasattr(diet_result.output_card, 'daily_plans') else None,
                    training_plan=training_result.output_card if training_result and hasattr(training_result.output_card, 'daily_plans') else None,
                )
                
                # 构建每日综合视图
                combined.build_daily_combined()
                
                return combined
        
        # 饮食计划
        if intent.intent_type == IntentType.DIET_PLAN:
            diet_result = agent_results.get("diet_planner")
            if diet_result:
                return diet_result.output_card
        
        # 默认：返回第一个成功的结果
        for result in agent_results.values():
            if result.status == AgentStatus.COMPLETED and result.output_card:
                return result.output_card
        
        return None
    
    def detect_conflicts(
        self, 
        agent_results: Dict[str, AgentResult],
    ) -> List[Dict[str, Any]]:
        """
        检测结果之间的冲突
        """
        conflicts = []
        
        # 获取所有输出卡片
        cards = []
        for name, result in agent_results.items():
            if result.output_card:
                cards.append((name, result.output_card))
        
        # 检测饮食和训练冲突
        diet_card = next((c for n, c in cards if "diet" in n), None)
        training_card = next((c for n, c in cards if "training" in n), None)
        
        if diet_card and training_card:
            # 这里可以实现更复杂的冲突检测逻辑
            # 例如：训练日碳水不足、恢复日热量过高等
            pass
        
        return conflicts
    
    async def run(self, task: str, session_id: Optional[str] = None) -> ConductorResult:
        """
        运行 Conductor 的完整流程
        
        Args:
            task: 用户任务/查询
            session_id: 会话ID（可选）
        
        Returns:
            执行结果
        """
        session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        started_at = datetime.now()
        
        try:
            # 1. 意图路由
            self.status = ConductorStatus.ROUTING
            intent = self.router.classify(task)
            
            # 2. 构建上下文
            context = self.build_context(task, intent)
            
            # 3. 创建执行计划
            self.status = ConductorStatus.DISPATCHING
            exec_plan = self.create_execution_plan(task, intent)
            
            # 4. 执行 Agent
            self.status = ConductorStatus.EXECUTING
            agent_results = await self.execute_agents(task, exec_plan, context)
            
            # 5. 冲突检测
            self.status = ConductorStatus.REFLECTING
            conflicts = self.detect_conflicts(agent_results)
            
            # 6. 合并结果
            self.status = ConductorStatus.MERGING
            final_output = self.merge_results(intent, agent_results)
            
            # 7. 记录到长期记忆
            if final_output:
                self.memory.add_memory(
                    content=f"任务: {task}\n结果: {final_output.to_summary()}",
                    content_type="plan",
                    importance=0.7,
                )
            
            # 完成
            self.status = ConductorStatus.COMPLETED
            completed_at = datetime.now()
            
            return ConductorResult(
                session_id=session_id,
                status=ConductorStatus.COMPLETED,
                intent=intent,
                agent_results=agent_results,
                final_output=final_output,
                conflicts_detected=conflicts,
                conflicts_resolved=len(conflicts) == 0,
                started_at=started_at,
                completed_at=completed_at,
                total_duration_seconds=(completed_at - started_at).total_seconds(),
            )
            
        except Exception as e:
            self.status = ConductorStatus.FAILED
            return ConductorResult(
                session_id=session_id,
                status=ConductorStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=datetime.now(),
            )
    
    async def chat(self, message: str) -> str:
        """
        便捷的对话接口
        
        返回文本响应而非完整的 ConductorResult
        """
        result = await self.run(message)
        
        if result.status == ConductorStatus.FAILED:
            return f"抱歉，处理您的请求时出现问题：{result.error}"
        
        if result.final_output:
            return result.final_output.to_summary()
        
        # 检查是否有任何 Agent 返回了文本输出
        for agent_result in result.agent_results.values():
            if agent_result.output_text:
                return agent_result.output_text
        
        return "已处理您的请求，但没有生成具体输出。"
