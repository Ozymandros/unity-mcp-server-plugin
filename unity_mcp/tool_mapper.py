"""
Mapper implementation for MCP tool definitions and SK metadata projection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import IMcpToolMapper, McpParameterDefinition, McpToolDefinition

_TYPE_MAP: Dict[str, str] = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


class McpToolMapper(IMcpToolMapper):
    """In-memory mapper with deterministic ordering by tool name."""

    def __init__(self) -> None:
        self._tools_by_name: Dict[str, McpToolDefinition] = {}

    def initialize(self, tools: List[McpToolDefinition]) -> None:
        self._tools_by_name = {tool.name: tool for tool in tools}

    def map_tool_definition(self, tool: McpToolDefinition) -> Dict[str, Any]:
        parameters = [
            self._map_parameter(param)
            for param in sorted(tool.parameters.values(), key=lambda p: p.name)
        ]
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
            "return": {
                "type": _TYPE_MAP.get(tool.return_type.type, "object") if tool.return_type else "object",
                "description": tool.return_type.description if tool.return_type else None,
            },
        }

    def get_tool_by_name(self, tool_name: str) -> Optional[McpToolDefinition]:
        return self._tools_by_name.get(tool_name)

    def get_tool_names(self) -> List[str]:
        return sorted(self._tools_by_name.keys())

    def get_registered_tools(self) -> List[McpToolDefinition]:
        return [self._tools_by_name[name] for name in self.get_tool_names()]

    @staticmethod
    def _map_parameter(param: McpParameterDefinition) -> Dict[str, Any]:
        return {
            "name": param.name,
            "description": param.description,
            "required": param.required,
            "default": param.default_value,
            "type": _TYPE_MAP.get(param.type.lower(), "string"),
            "schema_data": {
                "type": _TYPE_MAP.get(param.type.lower(), "string"),
                "description": param.description,
                "default": param.default_value,
            },
        }
