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

### Install from packaged wheel (production-style)

```bash
# Build artifacts in dist/
python -m pip install build
python -m build

# Install exact built wheel
pip install dist/unity_mcp_plugin-<version>-py3-none-any.whl
```

### Localhost package + install automation (cross-platform)

Use the helper script to automate local packaging + install:

```bash
# Full local flow: deps, tests, build, twine check, install wheel into .venv
python scripts/package_install.py

# Fast path (skip tests), recreate both build and target virtualenvs
python scripts/package_install.py --skip-tests --recreate-venvs

# Use a custom target venv
python scripts/package_install.py --venv .venv-local
```

What the script does:

- creates a build venv (`.venv-build` by default)
- installs project/dev dependencies and release tooling (`build`, `twine`)
- runs unit tests (`-m "not integration"`) unless `--skip-tests`
- builds wheel + sdist into `dist/`
- validates artifacts via `twine check`
- installs the built wheel into your target venv (`.venv` by default)

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

## Integration Example

The plugin requires the `unity-mcp` executable available in your environment.
Install once:

```bash
dotnet tool install -g unity-mcp
```

Then integrate from Python:

```python
import asyncio
from unity_mcp import UnityMCPPlugin, UnityMcpOptions

async def main():
    options = UnityMcpOptions(
        executable_path="unity-mcp",  # or absolute path to the executable
        request_timeout_seconds=60,
    )
    plugin = UnityMCPPlugin.create(options)
    await plugin.initialize()
    try:
        tools = await plugin.list_unity_tools()
        print("Discovered tools:")
        print(tools)

        ping_result = await plugin.invoke_tool("ping", {})
        print("Ping:", ping_result)
    finally:
        await plugin.cleanup()

asyncio.run(main())
```

### Expanded mode (recommended) — per-tool functions

```python
kernel = await UnityMCPPlugin.create_kernel_with_unity()
result = await kernel.invoke("unity", "unity_create_scene", path="Assets/Scenes/Level1.unity")
```

Expanded mode is best for autonomous agents/planners because each discovered MCP tool is exposed as a separate SK function with tool-level metadata.

### Router mode (backward compatible) — single generic function

```python
plugin = UnityMCPPlugin.create()
await plugin.initialize()

# Add only the generic router/list functions
kernel = Kernel()
kernel.add_plugin(plugin, plugin_name="unity")

result = await kernel.invoke(
    "unity",
    "invoke_unity_tool",
    tool_name="unity_create_scene",
    arguments_json='{"path":"Assets/Scenes/Level1.unity"}',
)
```

Router mode keeps a smaller tool-definition footprint (single generic entry point), but discoverability and tool-calling reliability are lower than expanded mode.

### Expanded vs Router tradeoffs

- **Expanded mode**: registers one plugin namespace (`unity` by default) with one SK function per MCP tool; this improves discoverability and tool-calling reliability for planners/autonomous agents.
- **Router mode**: keeps tool definitions compact in context (single generic function), but agents must infer tool names/arguments manually, which is less reliable.
- **Recommendation**: use expanded mode for agentic workflows and router mode only when minimizing tool-definition footprint is the priority.

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
- **Deterministic registration** — discovered tools are sorted by name before exposure to SK
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

### Metadata fidelity notes

Expanded mode propagates MCP parameter metadata into SK function metadata, including:

- exact parameter names
- descriptions
- required vs optional
- default values (when provided by MCP schema)
- JSON-schema-like type mapping (`string`, `number`, `integer`, `boolean`, `array`, `object`)

Current Python Semantic Kernel APIs do not fully preserve every JSON Schema construct (for example, `oneOf`, nested object schemas with full constraints, and all schema keywords) as first-class metadata fields. This plugin forwards the richest metadata currently supported via `KernelParameterMetadata` (`type`, `description`, `default_value`, `is_required`, and `schema_data`).

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
