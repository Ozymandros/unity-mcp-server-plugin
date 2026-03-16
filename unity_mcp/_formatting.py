"""
Result formatting helpers.

Centralises the dict→JSON / other→str logic used across the plugin layer.
"""

from __future__ import annotations

import json
from typing import Any, List

from .models import McpToolDefinition


def format_result(result: Any) -> str:
    """
    Convert an MCP tool result to a string suitable for SK return values.

    Dicts and lists are serialised as indented JSON; everything else uses
    ``str()``.  ``None`` returns an empty string.
    """
    if result is None:
        return ""
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2)
    return str(result)


def format_tool_list(tools: List[McpToolDefinition]) -> str:
    """
    Return a human-readable summary of discovered tools.

    Each line: ``<name> — <description>``
    """
    if not tools:
        return "No tools discovered."
    lines = [f"{t.name} — {t.description}" for t in sorted(tools, key=lambda t: t.name)]
    return "\n".join(lines)
