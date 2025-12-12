# app/tools/__init__.py
"""
工具注册中心 - Tool Registry

所有工具完全独立，可被多个 Agent 复用。
每个工具都返回结构化数据（Pydantic 模型），禁止返回长文本。

工具分类：
- RAG 工具：菜谱检索、知识查询
- 营养工具：营养计算、热量估算
- 相似度工具：菜谱相似度、食材替换
- 外部工具：网页搜索（可选）
"""

from app.tools.rag import RAGTool, RAGQueryResult
from app.tools.nutrition import NutritionTool, NutritionResult
from app.tools.similarity import SimilarityTool, SimilarityResult

__all__ = [
    # RAG
    "RAGTool",
    "RAGQueryResult",
    # Nutrition
    "NutritionTool",
    "NutritionResult",
    # Similarity
    "SimilarityTool",
    "SimilarityResult",
]
