# app/agents/base.py
"""
Agent 抽象基类

定义所有 Agent 必须实现的接口：
- plan(): 规划阶段 - 理解任务，制定执行计划
- execute(): 执行阶段 - 调用工具，生成结果
- reflect(): 反思阶段 - 验证结果，处理异常

设计原则：
1. Agent 不持有状态，状态通过 Context 注入
2. Agent 只负责单一领域的任务
3. 所有输出都是 Structure Card
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from pydantic import BaseModel, Field

from app.cards.base import BaseCard


class AgentStatus(str, Enum):
    """Agent 执行状态"""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentContext(BaseModel):
    """
    Agent 上下文
    
    包含 Agent 执行任务所需的所有信息：
    - 用户画像
    - 目标约束
    - 历史记忆
    - 会话信息
    """
    
    # 用户信息
    user_id: str
    user_profile: Dict[str, Any] = Field(default_factory=dict, description="用户画像摘要")
    
    # 目标和约束
    goals: List[Dict[str, Any]] = Field(default_factory=list, description="活跃目标列表")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="合并后的约束条件")
    
    # 偏好
    preferences: Dict[str, Any] = Field(default_factory=dict, description="用户偏好摘要")
    
    # 记忆
    relevant_memories: List[str] = Field(default_factory=list, description="相关历史记忆")
    
    # 会话
    session_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    
    # 任务链
    parent_task_id: Optional[str] = None
    sibling_results: Dict[str, Any] = Field(default_factory=dict, description="兄弟 Agent 的结果")

    def to_prompt_context(self) -> str:
        """
        转换为可插入 prompt 的上下文字符串
        """
        lines = []
        
        if self.user_profile:
            lines.append("【用户画像】")
            for key, value in self.user_profile.items():
                lines.append(f"- {key}: {value}")
        
        if self.goals:
            lines.append("\n【活跃目标】")
            for goal in self.goals[:3]:  # 最多3个
                lines.append(f"- {goal.get('title', '')}: {goal.get('constraints', {})}")
        
        if self.constraints:
            lines.append("\n【硬约束】")
            for key, value in self.constraints.items():
                lines.append(f"- {key}: {value}")
        
        if self.preferences.get("dietary_restrictions"):
            lines.append("\n【饮食限制】")
            for r in self.preferences["dietary_restrictions"]:
                lines.append(f"- {r}")
        
        if self.relevant_memories:
            lines.append("\n【相关历史】")
            for mem in self.relevant_memories[:3]:
                lines.append(f"- {mem[:100]}...")
        
        return "\n".join(lines)


class AgentPlan(BaseModel):
    """Agent 执行计划"""
    plan_id: str
    steps: List[str] = Field(default_factory=list, description="执行步骤")
    tools_needed: List[str] = Field(default_factory=list, description="需要使用的工具")
    estimated_time_seconds: Optional[int] = None
    reasoning: Optional[str] = Field(None, description="规划推理过程")


class AgentResult(BaseModel):
    """Agent 执行结果"""
    agent_name: str
    status: AgentStatus
    
    # 输出
    output_card: Optional[BaseCard] = Field(None, description="结构化输出卡片")
    output_text: Optional[str] = Field(None, description="文本输出（仅用于简单回答）")
    
    # 执行详情
    plan: Optional[AgentPlan] = None
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list, description="执行追踪")
    
    # 反思结果
    reflection: Optional[str] = None
    issues_found: List[str] = Field(default_factory=list)
    improvements_made: List[str] = Field(default_factory=list)
    
    # 元信息
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # 错误信息
    error: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


# 输出卡片类型参数
CardT = TypeVar("CardT", bound=BaseCard)


class BaseAgent(ABC, Generic[CardT]):
    """
    Agent 抽象基类
    
    所有 Agent 必须：
    1. 定义 output_card_type（输出的卡片类型）
    2. 实现 plan(), execute(), reflect() 方法
    3. 通过 tools 属性声明使用的工具
    
    执行流程：
    1. run() 入口 → 
    2. plan() 规划 → 
    3. execute() 执行 → 
    4. reflect() 反思 → 
    5. 返回 AgentResult
    """
    
    # 子类必须定义
    name: str = "base_agent"
    description: str = "Base agent"
    output_card_type: Type[CardT]
    
    def __init__(self, llm=None, tools: Optional[List] = None):
        """
        Args:
            llm: LLM 实例（如 ChatOpenAI）
            tools: 工具列表
        """
        self.llm = llm
        self._tools = tools or []
        self.status = AgentStatus.IDLE
    
    @property
    def tools(self) -> List:
        """返回该 Agent 使用的工具"""
        return self._tools
    
    @abstractmethod
    async def plan(self, task: str, context: AgentContext) -> AgentPlan:
        """
        规划阶段
        
        分析任务，制定执行计划。
        
        Args:
            task: 任务描述
            context: Agent 上下文
        
        Returns:
            执行计划
        """
        pass
    
    @abstractmethod
    async def execute(self, plan: AgentPlan, context: AgentContext) -> CardT:
        """
        执行阶段
        
        按照计划执行任务，调用工具，生成结构化输出。
        
        Args:
            plan: 执行计划
            context: Agent 上下文
        
        Returns:
            输出卡片
        """
        pass
    
    async def reflect(
        self, 
        output: CardT, 
        context: AgentContext,
        max_iterations: int = 2,
    ) -> tuple[CardT, List[str]]:
        """
        反思阶段
        
        验证输出是否满足约束，如有问题则尝试修复。
        
        Args:
            output: 执行阶段的输出
            context: Agent 上下文
            max_iterations: 最大修复迭代次数
        
        Returns:
            (修复后的输出, 发现的问题列表)
        """
        issues = []
        
        # 验证约束
        if hasattr(output, 'validate_constraints'):
            violations = output.validate_constraints(context.constraints)
            issues.extend(violations)
        
        # 默认实现：只记录问题，不自动修复
        # 子类可重写以实现自动修复逻辑
        
        return output, issues
    
    async def run(self, task: str, context: AgentContext) -> AgentResult:
        """
        运行 Agent 的完整流程
        
        Args:
            task: 任务描述
            context: Agent 上下文
        
        Returns:
            执行结果
        """
        started_at = datetime.now()
        execution_trace = []
        
        try:
            # 1. 规划
            self.status = AgentStatus.PLANNING
            plan = await self.plan(task, context)
            execution_trace.append({
                "phase": "plan",
                "result": plan.model_dump(),
            })
            
            # 2. 执行
            self.status = AgentStatus.EXECUTING
            output = await self.execute(plan, context)
            execution_trace.append({
                "phase": "execute",
                "result": "card_generated",
            })
            
            # 3. 反思
            self.status = AgentStatus.REFLECTING
            final_output, issues = await self.reflect(output, context)
            execution_trace.append({
                "phase": "reflect",
                "issues": issues,
            })
            
            # 4. 完成
            self.status = AgentStatus.COMPLETED
            completed_at = datetime.now()
            
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.COMPLETED,
                output_card=final_output,
                plan=plan,
                execution_trace=execution_trace,
                issues_found=issues,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )
            
        except Exception as e:
            self.status = AgentStatus.FAILED
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                execution_trace=execution_trace,
                error=str(e),
                started_at=started_at,
                completed_at=datetime.now(),
            )
    
    def get_system_prompt(self, context: AgentContext) -> str:
        """
        生成系统提示词
        
        子类可重写以自定义 prompt
        """
        return f"""你是 {self.name}，一个专注于{self.description}的 AI 助手。

{context.to_prompt_context()}

你的输出必须是结构化的，符合指定的输出格式。
"""
