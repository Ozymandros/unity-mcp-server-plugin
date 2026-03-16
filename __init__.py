"""
Unity MCP Plugin for Semantic Kernel — v3.0.0

Re-exports from the ``unity_mcp`` package for convenience.
"""

from unity_mcp import (
    UnityMCPPlugin,
    StdioMcpClient,
    UnityMCPClient,
    IMcpClient,
    UnityMcpOptions,
    BackoffStrategy,
    ConnectionState,
)

__version__ = "3.0.0"
__author__ = "Andreu"

__all__ = [
    "UnityMCPPlugin",
    "StdioMcpClient",
    "UnityMCPClient",
    "IMcpClient",
    "UnityMcpOptions",
    "BackoffStrategy",
    "ConnectionState",
]
