# app/tools/rag.py
"""
RAG 工具 - 菜谱和知识检索

封装现有的 RAG 模块，提供结构化的查询接口。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolMetadata


class RAGQueryInput(BaseModel):
    """RAG 查询输入"""
    query: str = Field(..., description="查询问题或需求描述")
    
    # 过滤条件
    category: Optional[str] = Field(None, description="菜谱分类：meat_dish, vegetable_dish, soup, staple等")
    difficulty: Optional[int] = Field(None, ge=1, le=5, description="难度等级 1-5")
    max_cooking_time: Optional[int] = Field(None, description="最大烹饪时间（分钟）")
    
    # 饮食限制
    exclude_ingredients: List[str] = Field(default_factory=list, description="需排除的食材")
    
    # 检索参数
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量")


class RecipeItem(BaseModel):
    """单个菜谱结果"""
    recipe_id: str = Field(..., description="菜谱ID")
    name: str = Field(..., description="菜谱名称")
    description: Optional[str] = Field(None, description="简短描述")
    category: Optional[str] = Field(None, description="分类")
    
    # 核心信息
    ingredients: List[str] = Field(default_factory=list, description="主要食材")
    cooking_time_minutes: Optional[int] = None
    difficulty: Optional[int] = None
    
    # 来源
    source: str = Field(default="HowToCook")
    source_url: Optional[str] = None
    
    # 相关性
    relevance_score: float = Field(0.0, description="检索相关性分数")
    
    # 原始内容（用于进一步处理）
    raw_content: Optional[str] = Field(None, description="原始 Markdown 内容")


class RAGQueryResult(BaseModel):
    """RAG 查询结果"""
    query: str
    total_found: int = Field(0, description="找到的结果总数")
    recipes: List[RecipeItem] = Field(default_factory=list)
    
    # 元信息
    search_time_ms: Optional[float] = None
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    
    # 辅助信息
    suggestions: List[str] = Field(default_factory=list, description="相关搜索建议")


class RAGTool(BaseTool[RAGQueryInput, RAGQueryResult]):
    """
    RAG 检索工具
    
    用于从知识库中检索菜谱和烹饪知识。
    """
    
    input_schema = RAGQueryInput
    output_schema = RAGQueryResult
    metadata = ToolMetadata(
        name="rag_query",
        description="从菜谱知识库中检索菜谱。输入查询描述（如'适合减脂的低卡午餐'），返回匹配的菜谱列表。支持按分类、难度、烹饪时间过滤，可排除特定食材。",
        usage_hint="query 应该是自然语言描述，如'高蛋白、低脂肪、适合健身的鸡胸肉做法'",
        examples=[
            "查询：'简单快手的早餐'",
            "查询：'适合乳糖不耐受的高蛋白菜谱'，排除：['牛奶', '奶酪']",
        ],
    )
    
    def __init__(self, rag_service=None):
        """
        Args:
            rag_service: RAGService 实例，如果不提供则延迟加载
        """
        self._rag_service = rag_service
    
    @property
    def rag_service(self):
        """延迟加载 RAG 服务"""
        if self._rag_service is None:
            from app.rag.rag_service import RAGService
            self._rag_service = RAGService()
        return self._rag_service
    
    async def execute(self, input_data: RAGQueryInput) -> RAGQueryResult:
        """执行 RAG 查询"""
        import time
        start_time = time.time()
        
        # 构建元数据过滤器
        metadata_filter = {}
        if input_data.category:
            metadata_filter["category"] = input_data.category
        
        # 调用 RAG 服务
        try:
            # 使用现有的 RAG 服务接口
            rag_response = await self.rag_service.query(
                query=input_data.query,
                top_k=input_data.top_k,
                metadata_filter=metadata_filter if metadata_filter else None,
            )
            
            # 转换结果
            recipes = []
            for doc in rag_response.get("documents", []):
                # 检查是否包含需排除的食材
                content = doc.get("content", "").lower()
                should_exclude = any(
                    ing.lower() in content 
                    for ing in input_data.exclude_ingredients
                )
                if should_exclude:
                    continue
                
                recipe = RecipeItem(
                    recipe_id=doc.get("id", ""),
                    name=doc.get("metadata", {}).get("title", doc.get("id", "未知菜谱")),
                    description=doc.get("content", "")[:200],
                    category=doc.get("metadata", {}).get("category"),
                    source=doc.get("metadata", {}).get("source", "HowToCook"),
                    relevance_score=doc.get("score", 0.0),
                    raw_content=doc.get("content"),
                )
                recipes.append(recipe)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return RAGQueryResult(
                query=input_data.query,
                total_found=len(recipes),
                recipes=recipes[:input_data.top_k],
                search_time_ms=elapsed_ms,
                filters_applied={
                    "category": input_data.category,
                    "exclude_ingredients": input_data.exclude_ingredients,
                },
            )
            
        except Exception as e:
            # 返回空结果而不是抛出异常
            return RAGQueryResult(
                query=input_data.query,
                total_found=0,
                recipes=[],
                suggestions=[f"查询失败：{str(e)}，请尝试简化查询条件"],
            )
