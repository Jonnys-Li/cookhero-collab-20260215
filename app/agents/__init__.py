# app/agents/__init__.py
"""
Agent 模块 - 智能体注册中心

每个 Agent 都是"结构+工具+小模型提示"的组合：
- 继承统一的基类
- 实现 plan(), execute(), reflect() 方法
- 使用 Tool 完成具体任务
- 输出 Structure Card

Agent 类型：
- DietPlannerAgent: 饮食规划
- TrainingPlannerAgent: 训练规划  
- NutritionCalculatorAgent: 营养计算
- RAGAgent: 知识检索
"""

from app.agents.base import BaseAgent, AgentContext, AgentResult
from app.agents.diet_planner import DietPlannerAgent
from app.agents.rag_agent import RAGAgent

__all__ = [
    "BaseAgent",
    "AgentContext",
    "AgentResult",
    "DietPlannerAgent",
    "RAGAgent",
]
