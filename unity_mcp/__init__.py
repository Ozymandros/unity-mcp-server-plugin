"""
Unity MCP Plugin for Semantic Kernel — v3.0.0

Migrated to stdio transport (subprocess) to match the new mcp-unity server.

Public API::

    from unity_mcp import (
        UnityMCPPlugin,
        StdioMcpClient,
        UnityMCPClient,   # backward-compat alias
        IMcpClient,
        UnityMcpOptions,
        BackoffStrategy,
    )

Quick start (simple)::

    plugin = UnityMCPPlugin.create()
    await plugin.initialize()
    result = await plugin.invoke_tool("unity_create_scene", {"path": "Assets/Scenes/New.unity"})
    await plugin.cleanup()

Quick start (full kernel with per-tool functions)::

    kernel = await UnityMCPPlugin.create_kernel_with_unity()
    result = await kernel.invoke("unity", "unity_create_scene", path="Assets/Scenes/New.unity")
"""

from .client import StdioMcpClient, UnityMCPClient
from .exceptions import (
    ConfigurationException,
    McpServerException,
    NetworkException,
    ProcessException,
    ProtocolException,
    TimeoutException,
    TypeConversionException,
    UnityMcpException,
)
from .models import (
    BackoffStrategy,
    ConnectionState,
    IMcpClient,
    IProcessManager,
    McpError,
    McpParameterDefinition,
    McpRequest,
    McpResponse,
    McpReturnType,
    McpToolDefinition,
    ProcessInfo,
    ProcessState,
    UnityMcpOptions,
)
from .plugin import UnityMCPPlugin
from .security import InputValidator, LogSanitizer

__version__ = "3.0.0"
__author__ = "Andreu"

__all__ = [
    # Plugin
    "UnityMCPPlugin",
    # Client
    "StdioMcpClient",
    "UnityMCPClient",
    # Protocols / interfaces
    "IMcpClient",
    "IProcessManager",
    # Configuration
    "UnityMcpOptions",
    "BackoffStrategy",
    # Models
    "ConnectionState",
    "ProcessState",
    "McpToolDefinition",
    "McpParameterDefinition",
    "McpReturnType",
    "McpRequest",
    "McpResponse",
    "McpError",
    "ProcessInfo",
    # Security
    "LogSanitizer",
    "InputValidator",
    # Exceptions
    "UnityMcpException",
    "NetworkException",
    "TimeoutException",
    "ProtocolException",
    "McpServerException",
    "ProcessException",
    "ConfigurationException",
    "TypeConversionException",
]
