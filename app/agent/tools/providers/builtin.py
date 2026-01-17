"""Builtin tool provider."""

from __future__ import annotations

import logging
from typing import Optional

from app.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)


class BuiltinToolProvider:
    name = "builtin"

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.info(f"Registered builtin tool: {tool.name}")

    def unregister_tool(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool_schema(self, name: str) -> Optional[dict]:
        tool = self._tools.get(name)
        if not tool:
            return None
        return tool.to_openai_schema()

    def get_tool_schemas(self, names: Optional[list[str]] = None) -> list[dict]:
        if names is None:
            return [t.to_openai_schema() for t in self._tools.values()]
        return [self._tools[n].to_openai_schema() for n in names if n in self._tools]

    def list_tool_infos(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "type": "builtin",
                "source": None,
            }
            for t in self._tools.values()
        ]
