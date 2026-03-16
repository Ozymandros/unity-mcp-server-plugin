"""
Stdio/JSON-RPC 2.0 MCP client.

Single Responsibility: transport + serialisation only.
No Semantic Kernel imports, no tool definitions.
Implements the ``IMcpClient`` protocol from ``models.py``.

Key features (mirrors C# StdioMcpClient):
- Subprocess stdio transport
- Configurable retry with linear/exponential backoff
- Periodic health-check monitoring
- Log sanitization
- Structured logging
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .exceptions import (
    McpServerException,
    NetworkException,
    ProtocolException,
    TimeoutException,
    UnityMcpException,
)
from .models import (
    BackoffStrategy,
    ConnectionState,
    McpError,
    McpParameterDefinition,
    McpRequest,
    McpResponse,
    McpToolDefinition,
    UnityMcpOptions,
)
from .process_manager import ProcessManager
from .security import LogSanitizer

logger = logging.getLogger(__name__)


class StdioMcpClient:
    """
    MCP client that communicates with the ``unity-mcp`` process via stdio.

    Usage::

        options = UnityMcpOptions()
        client = StdioMcpClient(options)
        await client.connect()
        response = await client.invoke_tool("ping", {})
        await client.close()

    Dependency injection (testing)::

        client = StdioMcpClient(options, process_manager=FakeProcessManager())
    """

    def __init__(
        self,
        options: UnityMcpOptions,
        process_manager: Optional[Any] = None,
    ) -> None:
        self._options = options
        self._process_manager: Any = process_manager or ProcessManager(options)
        self._state = ConnectionState.DISCONNECTED
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._last_success: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._last_health: bool = False
        self._health_task: Optional[asyncio.Task] = None
        self._health_stop = asyncio.Event()

    # ------------------------------------------------------------------
    # IMcpClient
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConnectionState:
        return self._state

    async def connect(self, cancellation_token: Any = None) -> None:
        """Start the subprocess and transition to CONNECTED."""
        self._state = ConnectionState.CONNECTING
        try:
            logger.info("Connecting to Unity-MCP server via stdio")
            await self._process_manager.ensure_process_running()
            self._state = ConnectionState.CONNECTED
            self._last_success = datetime.now(timezone.utc)
            self._start_health_monitoring()
            logger.info("Connected to Unity-MCP server via stdio")
        except Exception as exc:
            self._state = ConnectionState.FAULTED
            logger.error("Failed to connect to Unity-MCP server: %s", exc)
            raise NetworkException("Failed to connect to Unity-MCP server", cause=exc) from exc

    async def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        cancellation_token: Any = None,
    ) -> McpResponse:
        """
        Invoke a tool with automatic retry on transient failures.

        Retries on ``NetworkException`` and ``TimeoutException``.
        Does NOT retry on ``ProtocolException`` or ``McpServerException``.
        """
        await self._ensure_connected()

        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt <= self._options.max_retry_attempts:
            try:
                return await self._invoke_internal(tool_name, parameters)
            except (NetworkException, TimeoutException) as exc:
                if attempt >= self._options.max_retry_attempts:
                    raise
                last_exc = exc
                attempt += 1
                delay = self._retry_delay(attempt)
                logger.warning(
                    "Retrying tool '%s' (attempt %d/%d) after %.0fms: %s",
                    tool_name, attempt, self._options.max_retry_attempts,
                    delay * 1000, exc,
                )
                await asyncio.sleep(delay)
            except (ProtocolException, McpServerException):
                raise  # non-transient — no retry

        raise last_exc or NetworkException(f"Failed to invoke tool '{tool_name}' after {self._options.max_retry_attempts} retries")

    async def list_tools(self, cancellation_token: Any = None) -> List[McpToolDefinition]:
        """Discover available tools from the server."""
        await self._ensure_connected()
        response = await self.invoke_tool("tools/list", {})
        tools = self._parse_tool_definitions(response.result)
        logger.info("Discovered %d tools from Unity-MCP server", len(tools))
        return tools

    async def ping(self, cancellation_token: Any = None) -> bool:
        """Health-check ping. Returns True on success."""
        try:
            response = await self.invoke_tool("ping", {})
            if response.success:
                self._last_success = datetime.now(timezone.utc)
            return response.success
        except Exception:
            return False

    def is_healthy(self) -> bool:
        """Return True if connected and a successful request occurred recently."""
        if self._state != ConnectionState.CONNECTED:
            return False
        idle = datetime.now(timezone.utc) - self._last_success
        return idle < timedelta(seconds=self._options.max_idle_time_seconds)

    async def close(self) -> None:
        """Stop health monitoring and shut down the subprocess."""
        self._stop_health_monitoring()
        await self._process_manager.stop_process()
        self._state = ConnectionState.DISCONNECTED
        logger.debug("Unity-MCP client closed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        """Connect if not already connected."""
        if self._state not in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
            await self.connect()

    # ------------------------------------------------------------------
    # Internal transport
    # ------------------------------------------------------------------

    async def _invoke_internal(self, tool_name: str, parameters: Dict[str, Any]) -> McpResponse:
        async with self._lock:
            self._request_id += 1
            req_id = str(self._request_id)
            request = McpRequest(id=req_id, method=tool_name, parameters=parameters)

            payload = json.dumps({
                "jsonrpc": "2.0",
                "id": request.id,
                "method": request.method,
                "params": {k: v for k, v in request.parameters.items() if v is not None},
            })

            if self._options.enable_message_logging:
                logger.debug("Request: %s", LogSanitizer.sanitize_string(payload))

            await self._write_line(payload)
            raw = await self._read_line()

            if self._options.enable_message_logging:
                logger.debug("Response: %s", LogSanitizer.sanitize_string(raw))

            response = self._deserialize(raw)

            if not response.success and response.error is not None:
                raise McpServerException(
                    response.error.message,
                    response.error.code,
                    response.error.data,
                )

            self._last_success = datetime.now(timezone.utc)
            return response

    async def _write_line(self, message: str) -> None:
        try:
            stdin = self._process_manager.stdin
            stdin.write((message + "\n").encode("utf-8"))
            await stdin.drain()
        except Exception as exc:
            raise NetworkException("Failed to write to Unity-MCP server stdin", cause=exc) from exc

    async def _read_line(self) -> str:
        try:
            stdout = self._process_manager.stdout
            line = await asyncio.wait_for(
                stdout.readline(),
                timeout=self._options.request_timeout_seconds,
            )
            if not line:
                raise ProtocolException("Unexpected end of stream from Unity-MCP server")
            return line.decode("utf-8").rstrip("\n")
        except asyncio.TimeoutError as exc:
            raise TimeoutException(
                "Request timed out",
                timedelta(seconds=self._options.request_timeout_seconds),
                "ReadResponse",
            ) from exc
        except (ProtocolException, UnityMcpException):
            raise
        except Exception as exc:
            raise NetworkException("Failed to read from Unity-MCP server stdout", cause=exc) from exc

    def _deserialize(self, raw: str) -> McpResponse:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolException("Failed to deserialize MCP response", malformed_data=raw, cause=exc) from exc

        resp_id = data.get("id", "")
        if "error" in data and data["error"] is not None:
            err = data["error"]
            return McpResponse(
                id=resp_id,
                success=False,
                error=McpError(
                    code=err.get("code", -1),
                    message=err.get("message", "Unknown error"),
                    data=err.get("data"),
                ),
            )
        return McpResponse(id=resp_id, success=True, result=data.get("result"))

    # ------------------------------------------------------------------
    # Retry helpers
    # ------------------------------------------------------------------

    def _retry_delay(self, attempt: int) -> float:
        """Return delay in seconds for the given attempt number (1-based)."""
        base = self._options.initial_retry_delay_ms / 1000.0
        if self._options.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            return base * (2 ** (attempt - 1))
        return base * attempt  # LINEAR

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def _start_health_monitoring(self) -> None:
        self._stop_health_monitoring()
        self._health_stop.clear()
        self._health_task = asyncio.ensure_future(self._health_loop())
        logger.info("Health check monitoring started (interval: 30s)")

    def _stop_health_monitoring(self) -> None:
        self._health_stop.set()
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
        self._health_task = None

    async def _health_loop(self) -> None:
        try:
            while not self._health_stop.is_set():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(asyncio.sleep(30)),
                        timeout=31,
                    )
                except asyncio.TimeoutError:
                    pass
                if self._health_stop.is_set():
                    break
                healthy = await self.ping()
                if healthy != self._last_health:
                    self._last_health = healthy
                    logger.info("Connection health status changed to: %s", "healthy" if healthy else "unhealthy")
        except asyncio.CancelledError:
            logger.debug("Health check monitoring stopped")
        except Exception as exc:
            logger.error("Error in health check loop: %s", exc)

    # ------------------------------------------------------------------
    # Tool definition parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tool_definitions(result: Any) -> List[McpToolDefinition]:
        if result is None:
            return []
        try:
            raw = result if isinstance(result, dict) else json.loads(json.dumps(result))
            tools_raw = raw.get("tools", [])
            tools: List[McpToolDefinition] = []
            for t in tools_raw:
                name = t.get("name", "")
                description = t.get("description", "")
                schema = t.get("inputSchema", {})
                props = schema.get("properties", {})
                required_set = set(schema.get("required", []))
                params: Dict[str, McpParameterDefinition] = {}
                for pname, pdef in props.items():
                    params[pname] = McpParameterDefinition(
                        name=pname,
                        type=pdef.get("type", "string"),
                        description=pdef.get("description"),
                        required=pname in required_set,
                    )
                tools.append(McpToolDefinition(name=name, description=description, parameters=params))
            return tools
        except Exception as exc:
            raise ProtocolException("Failed to parse tool definitions", cause=exc) from exc


# ---------------------------------------------------------------------------
# Backward-compatible alias (old code used UnityMCPClient)
# ---------------------------------------------------------------------------

UnityMCPClient = StdioMcpClient
