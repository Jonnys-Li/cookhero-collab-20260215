# app/tools/similarity.py
"""
相似度工具

提供：
- 菜谱相似度计算
- 食材替换建议
- 相似菜谱推荐
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolMetadata


# ============== 食材替换知识库 ==============
INGREDIENT_SUBSTITUTES: Dict[str, List[Dict[str, Any]]] = {
    "牛奶": [
        {"name": "燕麦奶", "ratio": 1.0, "notes": "适合乳糖不耐受"},
        {"name": "豆浆", "ratio": 1.0, "notes": "蛋白质相近"},
        {"name": "杏仁奶", "ratio": 1.0, "notes": "热量较低"},
        {"name": "椰奶", "ratio": 0.5, "notes": "风味不同，酌情使用"},
    ],
    "鸡蛋": [
        {"name": "豆腐", "ratio": 0.25, "notes": "60g豆腐≈1个鸡蛋（烘焙）"},
        {"name": "香蕉", "ratio": 0.5, "notes": "半根香蕉≈1个鸡蛋（烘焙）"},
        {"name": "亚麻籽粉+水", "ratio": 1.0, "notes": "1勺+3勺水≈1个鸡蛋"},
    ],
    "猪肉": [
        {"name": "鸡肉", "ratio": 1.0, "notes": "更低脂"},
        {"name": "牛肉", "ratio": 1.0, "notes": "更高蛋白"},
        {"name": "豆腐", "ratio": 1.5, "notes": "素食替代"},
    ],
    "面粉": [
        {"name": "杏仁粉", "ratio": 1.0, "notes": "低碳水"},
        {"name": "燕麦粉", "ratio": 1.0, "notes": "更多纤维"},
        {"name": "椰子粉", "ratio": 0.25, "notes": "吸水性强，需调整"},
    ],
    "白糖": [
        {"name": "蜂蜜", "ratio": 0.75, "notes": "甜度更高"},
        {"name": "赤藓糖醇", "ratio": 1.3, "notes": "零热量"},
        {"name": "枫糖浆", "ratio": 0.75, "notes": "风味不同"},
    ],
    "香菜": [
        {"name": "芹菜叶", "ratio": 1.0, "notes": "装饰用"},
        {"name": "葱花", "ratio": 1.0, "notes": "提香"},
        {"name": "九层塔", "ratio": 0.5, "notes": "风味不同"},
    ],
}


class SimilarityQueryInput(BaseModel):
    """相似度查询输入"""
    recipe_name: str = Field(..., description="菜谱名称")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")
    
    # 约束
    exclude_ingredients: List[str] = Field(
        default_factory=list, 
        description="排除包含这些食材的菜谱"
    )


class SimilarRecipe(BaseModel):
    """相似菜谱"""
    name: str
    similarity_score: float
    shared_ingredients: List[str] = Field(default_factory=list)
    different_ingredients: List[str] = Field(default_factory=list)


class SimilarityResult(BaseModel):
    """相似度查询结果"""
    query_recipe: str
    similar_recipes: List[SimilarRecipe]
    total_found: int


class SubstituteQueryInput(BaseModel):
    """食材替换查询输入"""
    ingredient: str = Field(..., description="需要替换的食材")
    reason: Optional[str] = Field(None, description="替换原因：allergy/preference/diet")


class SubstituteItem(BaseModel):
    """替换建议"""
    original: str
    substitute: str
    ratio: float = Field(..., description="替换比例，如1.0表示等量替换")
    notes: Optional[str] = None


class SubstituteResult(BaseModel):
    """食材替换结果"""
    original_ingredient: str
    substitutes: List[SubstituteItem]
    found: bool


class SimilarityTool(BaseTool[SubstituteQueryInput, SubstituteResult]):
    """
    食材替换工具
    
    根据食材查询可替代的食材，支持过敏、偏好、饮食限制等原因。
    """
    
    input_schema = SubstituteQueryInput
    output_schema = SubstituteResult
    metadata = ToolMetadata(
        name="ingredient_substitute",
        description="查询食材的替代品。输入需要替换的食材名称，返回可替代的食材列表及替换比例。适用于过敏、不喜欢或饮食限制场景。",
        usage_hint="ingredient 使用中文食材名，如'牛奶'、'鸡蛋'",
        examples=[
            "查询牛奶的替代品（乳糖不耐受）",
            "查询鸡蛋的替代品（素食）",
        ],
    )
    
    def __init__(self, substitutes_db: Optional[Dict] = None):
        self.substitutes_db = substitutes_db or INGREDIENT_SUBSTITUTES
    
    async def execute(self, input_data: SubstituteQueryInput) -> SubstituteResult:
        """查询食材替换"""
        ingredient = input_data.ingredient
        
        # 精确匹配
        if ingredient in self.substitutes_db:
            substitutes = [
                SubstituteItem(
                    original=ingredient,
                    substitute=sub["name"],
                    ratio=sub["ratio"],
                    notes=sub.get("notes"),
                )
                for sub in self.substitutes_db[ingredient]
            ]
            return SubstituteResult(
                original_ingredient=ingredient,
                substitutes=substitutes,
                found=True,
            )
        
        # 模糊匹配
        for key, subs in self.substitutes_db.items():
            if key in ingredient or ingredient in key:
                substitutes = [
                    SubstituteItem(
                        original=key,
                        substitute=sub["name"],
                        ratio=sub["ratio"],
                        notes=sub.get("notes"),
                    )
                    for sub in subs
                ]
                return SubstituteResult(
                    original_ingredient=ingredient,
                    substitutes=substitutes,
                    found=True,
                )
        
        # 未找到
        return SubstituteResult(
            original_ingredient=ingredient,
            substitutes=[],
            found=False,
        )
    
    async def find_similar_recipes(
        self, 
        recipe_name: str,
        top_k: int = 5,
        exclude_ingredients: Optional[List[str]] = None,
    ) -> SimilarityResult:
        """
        查找相似菜谱
        
        TODO: 接入向量检索实现真正的语义相似度
        当前为简化实现
        """
        # 这里应该调用 RAG 进行向量检索
        # 阶段一简化实现：返回空结果
        return SimilarityResult(
            query_recipe=recipe_name,
            similar_recipes=[],
            total_found=0,
        )
