# app/tools/base.py
"""
工具基类

所有工具的抽象基类，定义：
- 统一的输入输出接口
- 工具元信息（名称、描述）
- LangChain Tool 适配
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, Type, TypeVar
from pydantic import BaseModel, Field

# 输入输出类型参数
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolMetadata(BaseModel):
    """工具元信息"""
    name: str = Field(..., description="工具名称，用于注册和调用")
    description: str = Field(..., description="工具描述，供 LLM 理解工具用途")
    version: str = Field(default="1.0.0")
    
    # 使用提示
    usage_hint: Optional[str] = Field(None, description="使用提示，如参数说明")
    examples: list[str] = Field(default_factory=list, description="使用示例")


class BaseTool(ABC, Generic[InputT, OutputT]):
    """
    工具抽象基类
    
    所有工具都必须：
    1. 定义明确的输入 Schema (Pydantic)
    2. 定义明确的输出 Schema (Pydantic)
    3. 实现 execute 方法
    """
    
    # 子类必须定义这些
    input_schema: Type[InputT]
    output_schema: Type[OutputT]
    metadata: ToolMetadata
    
    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """
        执行工具
        
        Args:
            input_data: 符合 input_schema 的输入数据
        
        Returns:
            符合 output_schema 的输出数据
        """
        pass
    
    def validate_input(self, raw_input: Dict[str, Any]) -> InputT:
        """验证并解析输入"""
        return self.input_schema(**raw_input)
    
    async def run(self, **kwargs) -> OutputT:
        """
        便捷运行方法
        
        接受关键字参数，自动验证并执行
        """
        input_data = self.validate_input(kwargs)
        return await self.execute(input_data)
    
    def to_langchain_tool(self):
        """
        转换为 LangChain Tool
        
        用于阶段一的 LangChain Agent 集成
        """
        from langchain_core.tools import StructuredTool
        import asyncio
        
        def sync_wrapper(**kwargs) -> dict:
            """同步包装器"""
            input_data = self.validate_input(kwargs)
            result = asyncio.run(self.execute(input_data))
            return result.model_dump()
        
        return StructuredTool.from_function(
            func=sync_wrapper,
            name=self.metadata.name,
            description=self.metadata.description,
            args_schema=self.input_schema,
            return_direct=False,
        )
    
    def to_openai_function(self) -> Dict[str, Any]:
        """
        转换为 OpenAI Function Calling 格式
        """
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "parameters": self.input_schema.model_json_schema(),
        }
