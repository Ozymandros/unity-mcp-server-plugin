"""
Unity MCP Server Plugin for Semantic Kernel

A bridge plugin that exposes Unity Editor operations through the Unity MCP Server
as Semantic Kernel functions.
"""

from unity_mcp_plugin import UnityMCPPlugin, UnityMCPClient, MCPToolSchema

__version__ = "1.0.0"
__author__ = "Unity MCP Contributors"

__all__ = [
    "UnityMCPPlugin",
    "UnityMCPClient",
    "MCPToolSchema"
]
