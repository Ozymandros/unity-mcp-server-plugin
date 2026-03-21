"""
Domain models, enums, and protocols for the Unity MCP plugin.

Follows Interface Segregation and Dependency Inversion principles.
All shared types live here; no transport or SK imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConnectionState(Enum):
    """Lifecycle state of the MCP client connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAULTED = "faulted"


class BackoffStrategy(Enum):
    """Retry delay calculation strategy."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class ProcessState(Enum):
    """Lifecycle state of the managed subprocess."""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    STOPPED = "stopped"
    FAULTED = "faulted"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class McpParameterDefinition:
    """Schema for a single MCP tool parameter."""

    name: str
    type: str  # "string" | "number" | "integer" | "boolean" | "object" | "array"
    description: Optional[str] = None
    required: bool = False
    default_value: Any = None


@dataclass(frozen=True)
class McpReturnType:
    """Schema for a tool's return value."""

    type: str
    description: Optional[str] = None


@dataclass(frozen=True)
class McpToolDefinition:
    """Full schema for a discovered MCP tool."""

    name: str
    description: str
    parameters: Dict[str, McpParameterDefinition] = field(default_factory=dict)
    return_type: Optional[McpReturnType] = None


@dataclass(frozen=True)
class McpError:
    """JSON-RPC error object."""

    code: int
    message: str
    data: Optional[str] = None


@dataclass(frozen=True)
class McpRequest:
    """JSON-RPC 2.0 request."""

    id: str
    method: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class McpResponse:
    """JSON-RPC 2.0 response."""

    id: str
    success: bool
    result: Any = None
    error: Optional[McpError] = None


@dataclass(frozen=True)
class ProcessInfo:
    """Metadata about the running unity-mcp subprocess."""

    process_id: int
    executable_path: str
    started_at: datetime


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class UnityMcpOptions:
    """
    Configuration for the Unity MCP plugin.

    All fields have sensible defaults matching the C# reference implementation.
    """

    executable_path: str = "unity-mcp"
    connection_timeout_seconds: int = 30
    request_timeout_seconds: int = 60
    max_retry_attempts: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    initial_retry_delay_ms: int = 1000
    enable_process_pooling: bool = True
    max_idle_time_seconds: int = 300
    enable_message_logging: bool = False
    tool_definitions_path: Optional[str] = None

    def validate(self) -> None:
        """Raise ``ConfigurationException`` if any field is invalid."""
        from .exceptions import ConfigurationException

        if not self.executable_path or not self.executable_path.strip():
            raise ConfigurationException("ExecutablePath must not be empty", "executable_path")
        if self.connection_timeout_seconds <= 0:
            raise ConfigurationException("ConnectionTimeoutSeconds must be positive", "connection_timeout_seconds")
        if self.request_timeout_seconds <= 0:
            raise ConfigurationException("RequestTimeoutSeconds must be positive", "request_timeout_seconds")
        if self.max_retry_attempts < 0:
            raise ConfigurationException("MaxRetryAttempts must not be negative", "max_retry_attempts")


# ---------------------------------------------------------------------------
# Protocols (Dependency Inversion)
# ---------------------------------------------------------------------------


@runtime_checkable
class IMcpClient(Protocol):
    """
    Protocol for MCP client implementations.

    Enables swapping the real stdio client for a fake/mock in tests
    without touching the plugin layer.
    """

    async def connect(self, cancellation_token: Any = None) -> None:
        """Connect to the MCP server (start subprocess)."""
        ...

    async def list_tools(self, cancellation_token: Any = None) -> List[McpToolDefinition]:
        """Discover available tools from the server."""
        ...

    async def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        cancellation_token: Any = None,
    ) -> McpResponse:
        """Execute a tool and return the response."""
        ...

    async def ping(self, cancellation_token: Any = None) -> bool:
        """Health-check ping. Returns True on success."""
        ...

    def is_healthy(self) -> bool:
        """Return True if the connection is currently healthy."""
        ...

    async def close(self) -> None:
        """Shut down the connection and release resources."""
        ...


@runtime_checkable
class IMcpToolMapper(Protocol):
    """
    Contract for mapping discovered MCP tools into SK-friendly metadata.

    Implementations are the source of truth for discovered tools after
    initialization, so registration code does not need to re-query the client.
    """

    def initialize(self, tools: List[McpToolDefinition]) -> None:
        """Cache discovered tools, replacing any previously mapped set."""
        ...

    def map_tool_definition(self, tool: McpToolDefinition) -> Dict[str, Any]:
        """Map a tool definition into metadata suitable for SK registration."""
        ...

    def get_tool_by_name(self, tool_name: str) -> Optional[McpToolDefinition]:
        """Return a tool by name, or None when not registered."""
        ...

    def get_tool_names(self) -> List[str]:
        """Return deterministic, sorted tool names."""
        ...

    def get_registered_tools(self) -> List[McpToolDefinition]:
        """Return deterministic, sorted registered tools."""
        ...


@runtime_checkable
class IProcessManager(Protocol):
    """Protocol for subprocess lifecycle management."""

    @property
    def state(self) -> ProcessState:
        ...

    async def ensure_process_running(self) -> ProcessInfo:
        """Start the process if not already running. Returns process info."""
        ...

    async def stop_process(self) -> None:
        """Gracefully stop the process."""
        ...

    @property
    def stdin(self) -> Any:
        """Write-side stream of the subprocess."""
        ...

    @property
    def stdout(self) -> Any:
        """Read-side stream of the subprocess."""
        ...
