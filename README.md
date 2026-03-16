# Unity MCP Plugin for Semantic Kernel

Python plugin that bridges Semantic Kernel agents with the [Unity MCP Server](https://github.com/Ozymandros/Unity-MCP-SK-Plugin) via **stdio transport** (subprocess).

## Architecture

```text
UnityMCPPlugin
  └── StdioMcpClient          # JSON-RPC 2.0 over stdio
        └── ProcessManager    # asyncio subprocess lifecycle
              └── unity-mcp   # .NET global tool (subprocess)

unity_mcp/
├── exceptions.py      # Full exception hierarchy
├── models.py          # Enums, value objects, protocols (IMcpClient, IProcessManager)
├── security.py        # LogSanitizer, InputValidator
├── process_manager.py # Subprocess lifecycle (start / stop / restart)
├── client.py          # StdioMcpClient — retry, health monitoring, JSON-RPC
├── plugin.py          # UnityMCPPlugin — SK kernel functions, dynamic tool discovery
├── _formatting.py     # format_result, format_tool_list
└── __init__.py        # Public API
```

SOLID principles applied:

- Single Responsibility — each module has one job
- Dependency Inversion — `UnityMCPPlugin` accepts any `IMcpClient` via constructor injection
- Open/Closed — new tools require no code changes; they are discovered at runtime

## Installation

```bash
pip install -e .
# dev extras (pytest, mypy, black, flake8)
pip install -e ".[dev]"
```

Prerequisites:

- Python 3.10+
- `semantic-kernel >= 1.0.0`
- `unity-mcp` .NET global tool: `dotnet tool install -g unity-mcp`

## Quick Start

```python
import asyncio
from unity_mcp import UnityMCPPlugin

async def main():
    plugin = UnityMCPPlugin.create()
    await plugin.initialize()

    result = await plugin.invoke_tool("unity_create_scene", {"path": "Assets/Scenes/Level1.unity"})
    print(result)

    await plugin.cleanup()

asyncio.run(main())
```

### Full kernel — per-tool functions (best for planners)

```python
kernel = await UnityMCPPlugin.create_kernel_with_unity()
result = await kernel.invoke("unity", "unity_create_scene", path="Assets/Scenes/Level1.unity")
```

### Custom options

```python
from unity_mcp import UnityMCPPlugin, UnityMcpOptions, BackoffStrategy

options = UnityMcpOptions(
    executable_path="unity-mcp",
    max_retry_attempts=5,
    backoff_strategy=BackoffStrategy.EXPONENTIAL,
    initial_retry_delay_ms=500,
    request_timeout_seconds=30,
    enable_message_logging=True,
)
plugin = UnityMCPPlugin.create(options)
```

### Dependency injection (testing)

```python
from unity_mcp import UnityMCPPlugin, McpResponse

class FakeMcpClient:
    async def connect(self, cancellation_token=None): ...
    async def list_tools(self, cancellation_token=None): return []
    async def invoke_tool(self, tool_name, parameters, cancellation_token=None):
        return McpResponse(id="1", success=True, result={"ok": True})
    async def ping(self, cancellation_token=None): return True
    def is_healthy(self): return True
    async def close(self): ...

plugin = UnityMCPPlugin(client=FakeMcpClient())
```

## Key Features

- **Dynamic tool discovery** — tools are discovered at runtime via `list_tools()`; no hardcoded wrappers
- **Retry with backoff** — configurable linear or exponential backoff on transient failures
- **Health monitoring** — periodic ping loop; `is_healthy()` reflects connection state
- **Security** — `LogSanitizer` redacts secrets from logs; `InputValidator` validates all tool calls
- **Backward compat** — `UnityMCPClient` alias kept for existing code

## Public API

```python
from unity_mcp import (
    # Plugin
    UnityMCPPlugin,
    # Client
    StdioMcpClient,
    UnityMCPClient,       # backward-compat alias for StdioMcpClient
    # Protocols
    IMcpClient,
    IProcessManager,
    # Configuration
    UnityMcpOptions,
    BackoffStrategy,
    # State enums
    ConnectionState,
    ProcessState,
    # Models
    McpToolDefinition,
    McpParameterDefinition,
    McpReturnType,
    McpRequest,
    McpResponse,
    McpError,
    ProcessInfo,
    # Security
    LogSanitizer,
    InputValidator,
    # Exceptions
    UnityMcpException,
    NetworkException,
    TimeoutException,
    ProtocolException,
    McpServerException,
    ProcessException,
    ConfigurationException,
    TypeConversionException,
)
```

### UnityMcpOptions fields

| Field | Type | Default | Description |
|:---|:---|:---|:---|
| `executable_path` | `str` | `"unity-mcp"` | Path or name of the unity-mcp executable |
| `connection_timeout_seconds` | `int` | `30` | Timeout for initial process start |
| `request_timeout_seconds` | `int` | `60` | Per-request read timeout |
| `max_retry_attempts` | `int` | `3` | Retries on transient failures (0 = no retry) |
| `backoff_strategy` | `BackoffStrategy` | `EXPONENTIAL` | `LINEAR` or `EXPONENTIAL` |
| `initial_retry_delay_ms` | `int` | `1000` | Base delay for first retry |
| `max_idle_time_seconds` | `int` | `300` | Max idle before `is_healthy()` returns False |
| `enable_message_logging` | `bool` | `False` | Log sanitized request/response payloads at DEBUG |
| `tool_definitions_path` | `str \| None` | `None` | Optional path to a static tool definitions file |

### Parameter types

`McpParameterDefinition.type` follows JSON Schema conventions:
`"string"`, `"number"`, `"integer"`, `"boolean"`, `"object"`, `"array"`

### Exception hierarchy

```text
UnityMcpException
├── NetworkException        — transport / pipe failure
├── TimeoutException        — request exceeded timeout
├── ProtocolException       — malformed JSON-RPC message
├── McpServerException      — server returned a JSON-RPC error
├── ProcessException        — subprocess start/stop failure
├── ConfigurationException  — invalid UnityMcpOptions
└── TypeConversionException — parameter type mismatch
```

## Testing

```bash
# Unit tests (no server needed)
pytest test_plugin.py -v -m "not integration"

# Integration tests (requires running unity-mcp)
pytest test_plugin.py -v -m integration
```

## Changelog

### v3.0.0

- **Breaking**: Migrated from TCP to **stdio transport** (subprocess)
- **Breaking**: `UnityMCPPlugin.create()` no longer takes `host`/`port`; accepts `UnityMcpOptions`
- **New**: `ProcessManager` — asyncio subprocess lifecycle management
- **New**: `StdioMcpClient` — JSON-RPC 2.0 over stdio with retry and health monitoring
- **New**: `LogSanitizer` + `InputValidator` security layer
- **New**: Full exception hierarchy (`NetworkException`, `TimeoutException`, `ProtocolException`, etc.)
- **New**: `UnityMcpOptions` configuration dataclass with validation
- **New**: Dynamic tool discovery — no hardcoded wrappers
- **New**: `create_kernel_with_unity()` static factory registers each tool as its own `KernelFunction`
- **New**: `invoke_unity_tool` + `list_unity_tools` generic kernel functions
- **New**: `McpReturnType` model for tool return value schemas

### v2.0.0

- Refactored monolith into `unity_mcp/` package
- Added `IMCPClient` protocol for dependency injection
- Added `UnityMCPPlugin.create()` factory
- 22 hardcoded tool wrappers

### v1.0.0

- Initial release with TCP transport

## License

MIT
