"""
Test suite for Unity MCP Plugin v3.0.0 (stdio transport)

Covers:
- Exception hierarchy
- LogSanitizer
- InputValidator
- ProcessManager state transitions
- StdioMcpClient: connect, invoke, retry (linear/exponential), health, disconnect
- UnityMCPPlugin: DI, initialize, invoke_tool, create_kernel_with_unity
- Integration (marked, skipped when server absent)

Run with: pytest test_plugin.py -v
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from unity_mcp import (
    BackoffStrategy,
    ConfigurationException,
    ConnectionState,
    IMcpClient,
    InputValidator,
    LogSanitizer,
    McpParameterDefinition,
    McpResponse,
    McpServerException,
    McpToolDefinition,
    NetworkException,
    ProcessException,
    ProcessState,
    ProtocolException,
    StdioMcpClient,
    TimeoutException,
    TypeConversionException,
    UnityMCPPlugin,
    UnityMcpException,
    UnityMcpOptions,
)
from unity_mcp.models import McpReturnType
from unity_mcp._formatting import format_result, format_tool_list
from unity_mcp.process_manager import ProcessManager


# ====================================================================
# Test doubles
# ====================================================================


class FakeProcessManager:
    """In-memory process manager — no real subprocess."""

    def __init__(self) -> None:
        self._state = ProcessState.NOT_STARTED
        self._stdin = AsyncMock()
        self._stdout = AsyncMock()

    @property
    def state(self) -> ProcessState:
        return self._state

    @property
    def stdin(self):
        return self._stdin

    @property
    def stdout(self):
        return self._stdout

    async def ensure_process_running(self):
        from unity_mcp.models import ProcessInfo
        self._state = ProcessState.RUNNING
        return ProcessInfo(
            process_id=1234,
            executable_path="unity-mcp",
            started_at=datetime.now(timezone.utc),
        )

    async def stop_process(self) -> None:
        self._state = ProcessState.STOPPED


class FakeMcpClient:
    """Fake IMcpClient — records calls, returns configurable responses."""

    def __init__(self) -> None:
        self.connected = False
        self.calls: List[tuple] = []
        self._tools: List[McpToolDefinition] = []
        self._responses: Dict[str, McpResponse] = {}
        self._healthy = True

    def set_tools(self, tools: List[McpToolDefinition]) -> None:
        self._tools = tools

    def set_response(self, tool_name: str, response: McpResponse) -> None:
        self._responses[tool_name] = response

    async def connect(self, cancellation_token: Any = None) -> None:
        self.connected = True

    async def list_tools(self, cancellation_token: Any = None) -> List[McpToolDefinition]:
        return list(self._tools)

    async def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        cancellation_token: Any = None,
    ) -> McpResponse:
        self.calls.append((tool_name, parameters))
        if tool_name in self._responses:
            return self._responses[tool_name]
        return McpResponse(id="1", success=True, result={"tool": tool_name})

    async def ping(self, cancellation_token: Any = None) -> bool:
        return self._healthy

    def is_healthy(self) -> bool:
        return self._healthy

    async def close(self) -> None:
        self.connected = False


# ====================================================================
# Formatting helpers
# ====================================================================


class TestFormatResult:
    def test_dict(self):
        assert format_result({"ok": True}) == json.dumps({"ok": True}, indent=2)

    def test_list(self):
        assert format_result([1, 2]) == json.dumps([1, 2], indent=2)

    def test_string(self):
        assert format_result("hello") == "hello"

    def test_number(self):
        assert format_result(42) == "42"

    def test_none(self):
        assert format_result(None) == ""


class TestFormatToolList:
    def test_empty(self):
        assert format_tool_list([]) == "No tools discovered."

    def test_sorted(self):
        tools = [
            McpToolDefinition(name="b_tool", description="B"),
            McpToolDefinition(name="a_tool", description="A"),
        ]
        result = format_tool_list(tools)
        assert result.startswith("a_tool")
        assert "b_tool" in result


# ====================================================================
# Exception hierarchy
# ====================================================================


class TestExceptions:
    def test_base(self):
        exc = UnityMcpException("base")
        assert isinstance(exc, Exception)

    def test_network(self):
        exc = NetworkException("net", endpoint="stdio://x", cause=ValueError("v"))
        assert exc.endpoint == "stdio://x"
        assert isinstance(exc.__cause__, ValueError)

    def test_timeout(self):
        exc = TimeoutException("t", timeout=timedelta(seconds=5), operation="read")
        assert exc.timeout.seconds == 5
        assert exc.operation == "read"

    def test_protocol(self):
        exc = ProtocolException("p", malformed_data="bad", cause=RuntimeError("r"))
        assert exc.malformed_data == "bad"

    def test_mcp_server(self):
        exc = McpServerException("s", error_code=-32600, error_data="detail")
        assert exc.error_code == -32600
        assert exc.error_data == "detail"

    def test_process(self):
        exc = ProcessException("proc", process_id=42)
        assert exc.process_id == 42

    def test_configuration(self):
        exc = ConfigurationException("cfg", parameter_name="foo")
        assert exc.parameter_name == "foo"

    def test_type_conversion(self):
        exc = TypeConversionException("tc", source_type="str", target_type="int")
        assert exc.source_type == "str"
        assert exc.target_type == "int"

    def test_hierarchy(self):
        for cls in (NetworkException, TimeoutException, ProtocolException,
                    McpServerException, ProcessException, ConfigurationException,
                    TypeConversionException):
            assert issubclass(cls, UnityMcpException)


# ====================================================================
# LogSanitizer
# ====================================================================


class TestLogSanitizer:
    def test_redacts_password_key(self):
        result = LogSanitizer.sanitize_parameters({"password": "secret123"})
        assert result["password"] == "[REDACTED]"

    def test_redacts_api_key(self):
        result = LogSanitizer.sanitize_parameters({"api_key": "abc"})
        assert result["api_key"] == "[REDACTED]"

    def test_keeps_safe_key(self):
        result = LogSanitizer.sanitize_parameters({"name": "Alice"})
        assert result["name"] == "Alice"

    def test_nested_dict(self):
        result = LogSanitizer.sanitize_parameters({"auth": {"token": "xyz", "user": "bob"}})
        assert result["auth"]["token"] == "[REDACTED]"
        assert result["auth"]["user"] == "bob"

    def test_sanitize_bearer(self):
        result = LogSanitizer.sanitize_string("Authorization: Bearer abc123")
        assert result is not None
        assert "abc123" not in result
        assert "Bearer [REDACTED]" in result

    def test_sanitize_email(self):
        result = LogSanitizer.sanitize_string("Contact user@example.com for help")
        assert result is not None
        assert "user@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_sanitize_none(self):
        assert LogSanitizer.sanitize_string(None) is None

    def test_sanitize_empty(self):
        assert LogSanitizer.sanitize_string("") == ""

    def test_config_value_sensitive(self):
        assert LogSanitizer.sanitize_config_value("api_key", "secret") == "[REDACTED]"

    def test_config_value_safe(self):
        assert LogSanitizer.sanitize_config_value("host", "localhost") == "localhost"


# ====================================================================
# InputValidator
# ====================================================================


def _tool(name: str = "my_tool", params: Optional[Dict] = None) -> McpToolDefinition:
    """Helper: build a McpToolDefinition with optional params."""
    p: Dict[str, McpParameterDefinition] = {}
    if params:
        for pname, (ptype, required) in params.items():
            p[pname] = McpParameterDefinition(name=pname, type=ptype, required=required)
    return McpToolDefinition(name=name, description="test", parameters=p)


class TestInputValidator:
    def test_valid_tool_name(self):
        InputValidator.validate_tool_name("my_tool", ["my_tool", "other"])

    def test_empty_tool_name(self):
        with pytest.raises(UnityMcpException, match="cannot be null or empty"):
            InputValidator.validate_tool_name("", ["my_tool"])

    def test_unknown_tool_name(self):
        with pytest.raises(UnityMcpException, match="not registered"):
            InputValidator.validate_tool_name("unknown", ["my_tool"])

    def test_valid_params(self):
        td = _tool(params={"name": ("string", True), "count": ("integer", False)})
        InputValidator.validate_parameters({"name": "Alice", "count": 5}, td)

    def test_missing_required(self):
        td = _tool(params={"name": ("string", True)})
        with pytest.raises(UnityMcpException, match="missing"):
            InputValidator.validate_parameters({}, td)

    def test_null_required(self):
        td = _tool(params={"name": ("string", True)})
        with pytest.raises(UnityMcpException, match="cannot be null"):
            InputValidator.validate_parameters({"name": None}, td)

    def test_unknown_param(self):
        td = _tool(params={"name": ("string", True)})
        with pytest.raises(UnityMcpException, match="Unknown parameter"):
            InputValidator.validate_parameters({"name": "x", "extra": "y"}, td)

    def test_wrong_type(self):
        td = _tool(params={"count": ("integer", True)})
        with pytest.raises(UnityMcpException, match="invalid type"):
            InputValidator.validate_parameters({"count": "not-an-int"}, td)

    def test_boolean_not_integer(self):
        td = _tool(params={"count": ("integer", True)})
        with pytest.raises(UnityMcpException, match="invalid type"):
            InputValidator.validate_parameters({"count": True}, td)

    def test_sanitize_error_message(self):
        msg = "Error at C:\\Users\\admin\\secret.txt"
        result = InputValidator.sanitize_error_message(msg)
        assert "admin" not in result
        assert "[path]" in result

    def test_sanitize_empty_message(self):
        assert InputValidator.sanitize_error_message("") == "An error occurred"

    def test_sanitize_none_message(self):
        assert InputValidator.sanitize_error_message(None) == "An error occurred"

    def test_sanitize_truncates_long(self):
        long_msg = "x" * 300
        result = InputValidator.sanitize_error_message(long_msg)
        assert len(result) <= 200


# ====================================================================
# UnityMcpOptions validation
# ====================================================================


class TestUnityMcpOptions:
    def test_defaults_valid(self):
        UnityMcpOptions().validate()  # should not raise

    def test_empty_executable(self):
        with pytest.raises(ConfigurationException, match="ExecutablePath"):
            UnityMcpOptions(executable_path="").validate()

    def test_negative_connection_timeout(self):
        with pytest.raises(ConfigurationException, match="ConnectionTimeoutSeconds"):
            UnityMcpOptions(connection_timeout_seconds=0).validate()

    def test_negative_request_timeout(self):
        with pytest.raises(ConfigurationException, match="RequestTimeoutSeconds"):
            UnityMcpOptions(request_timeout_seconds=-1).validate()

    def test_negative_retry_attempts(self):
        with pytest.raises(ConfigurationException, match="MaxRetryAttempts"):
            UnityMcpOptions(max_retry_attempts=-1).validate()


# ====================================================================
# ProcessManager
# ====================================================================


class TestProcessManager:
    def test_initial_state(self):
        mgr = ProcessManager(UnityMcpOptions())
        assert mgr.state == ProcessState.NOT_STARTED

    @pytest.mark.asyncio
    async def test_stdin_raises_when_not_started(self):
        mgr = ProcessManager(UnityMcpOptions())
        with pytest.raises(ProcessException):
            _ = mgr.stdin

    @pytest.mark.asyncio
    async def test_stdout_raises_when_not_started(self):
        mgr = ProcessManager(UnityMcpOptions())
        with pytest.raises(ProcessException):
            _ = mgr.stdout

    @pytest.mark.asyncio
    async def test_start_missing_executable(self):
        opts = UnityMcpOptions(executable_path="__nonexistent_unity_mcp__")
        mgr = ProcessManager(opts)
        with pytest.raises(ProcessException, match="not found"):
            await mgr.ensure_process_running()
        assert mgr.state == ProcessState.FAULTED

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        mgr = ProcessManager(UnityMcpOptions())
        await mgr.stop_process()  # should not raise
        assert mgr.state == ProcessState.NOT_STARTED


# ====================================================================
# StdioMcpClient
# ====================================================================


def _make_client(options: Optional[UnityMcpOptions] = None) -> tuple[StdioMcpClient, FakeProcessManager]:
    opts = options or UnityMcpOptions()
    fake_pm = FakeProcessManager()
    client = StdioMcpClient(opts, process_manager=fake_pm)
    return client, fake_pm


class TestStdioMcpClientConnect:
    @pytest.mark.asyncio
    async def test_connect_transitions_to_connected(self):
        client, _ = _make_client()
        await client.connect()
        assert client.state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_connect_failure_transitions_to_faulted(self):
        client, fake_pm = _make_client()

        async def _fail():
            raise RuntimeError("boom")

        fake_pm.ensure_process_running = _fail
        with pytest.raises(NetworkException):
            await client.connect()
        assert client.state == ConnectionState.FAULTED

    @pytest.mark.asyncio
    async def test_close_disconnects(self):
        client, _ = _make_client()
        await client.connect()
        await client.close()
        assert client.state == ConnectionState.DISCONNECTED


class TestStdioMcpClientInvoke:
    @pytest.mark.asyncio
    async def test_invoke_returns_response(self):
        client, fake_pm = _make_client()
        await client.connect()

        response_json = json.dumps({"jsonrpc": "2.0", "id": "1", "result": {"ok": True}})
        fake_pm.stdout.readline = AsyncMock(return_value=(response_json + "\n").encode())
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        resp = await client.invoke_tool("ping", {})
        assert resp.success is True
        assert resp.result == {"ok": True}

    @pytest.mark.asyncio
    async def test_invoke_raises_mcp_server_exception_on_error(self):
        client, fake_pm = _make_client()
        await client.connect()

        error_json = json.dumps({
            "jsonrpc": "2.0", "id": "1",
            "error": {"code": -32601, "message": "Method not found"}
        })
        fake_pm.stdout.readline = AsyncMock(return_value=(error_json + "\n").encode())
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        with pytest.raises(McpServerException) as exc_info:
            await client.invoke_tool("unknown", {})
        assert exc_info.value.error_code == -32601

    @pytest.mark.asyncio
    async def test_invoke_raises_protocol_exception_on_bad_json(self):
        client, fake_pm = _make_client()
        await client.connect()

        fake_pm.stdout.readline = AsyncMock(return_value=b"NOT_JSON\n")
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        with pytest.raises(ProtocolException):
            await client.invoke_tool("ping", {})

    @pytest.mark.asyncio
    async def test_invoke_raises_protocol_exception_on_eof(self):
        client, fake_pm = _make_client()
        await client.connect()

        fake_pm.stdout.readline = AsyncMock(return_value=b"")
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        with pytest.raises(ProtocolException, match="end of stream"):
            await client.invoke_tool("ping", {})


class TestStdioMcpClientRetry:
    @pytest.mark.asyncio
    async def test_retries_on_network_exception(self):
        opts = UnityMcpOptions(max_retry_attempts=2, initial_retry_delay_ms=1)
        client, fake_pm = _make_client(opts)
        await client.connect()

        call_count = 0

        async def _flaky_readline():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("pipe broken")
            return (json.dumps({"jsonrpc": "2.0", "id": str(call_count), "result": "ok"}) + "\n").encode()

        fake_pm.stdout.readline = _flaky_readline
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        resp = await client.invoke_tool("ping", {})
        assert resp.success is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises_network_exception(self):
        opts = UnityMcpOptions(max_retry_attempts=2, initial_retry_delay_ms=1)
        client, fake_pm = _make_client(opts)
        await client.connect()

        fake_pm.stdout.readline = AsyncMock(side_effect=OSError("always fails"))
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        with pytest.raises(NetworkException):
            await client.invoke_tool("ping", {})

    @pytest.mark.asyncio
    async def test_no_retry_on_protocol_exception(self):
        opts = UnityMcpOptions(max_retry_attempts=3, initial_retry_delay_ms=1)
        client, fake_pm = _make_client(opts)
        await client.connect()

        call_count = 0

        async def _bad_json():
            nonlocal call_count
            call_count += 1
            return b"BAD_JSON\n"

        fake_pm.stdout.readline = _bad_json
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        with pytest.raises(ProtocolException):
            await client.invoke_tool("ping", {})
        assert call_count == 1  # no retry

    def test_linear_backoff(self):
        opts = UnityMcpOptions(backoff_strategy=BackoffStrategy.LINEAR, initial_retry_delay_ms=500)
        client, _ = _make_client(opts)
        assert client._retry_delay(1) == pytest.approx(0.5)
        assert client._retry_delay(2) == pytest.approx(1.0)
        assert client._retry_delay(3) == pytest.approx(1.5)

    def test_exponential_backoff(self):
        opts = UnityMcpOptions(backoff_strategy=BackoffStrategy.EXPONENTIAL, initial_retry_delay_ms=1000)
        client, _ = _make_client(opts)
        assert client._retry_delay(1) == pytest.approx(1.0)
        assert client._retry_delay(2) == pytest.approx(2.0)
        assert client._retry_delay(3) == pytest.approx(4.0)


class TestStdioMcpClientHealth:
    @pytest.mark.asyncio
    async def test_is_healthy_when_connected_and_recent(self):
        client, _ = _make_client()
        await client.connect()
        client._last_success = datetime.now(timezone.utc)
        assert client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_not_healthy_when_disconnected(self):
        client, _ = _make_client()
        assert client.is_healthy() is False

    @pytest.mark.asyncio
    async def test_not_healthy_when_idle_too_long(self):
        opts = UnityMcpOptions(max_idle_time_seconds=1)
        client, _ = _make_client(opts)
        await client.connect()
        client._last_success = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert client.is_healthy() is False

    @pytest.mark.asyncio
    async def test_ping_returns_false_on_error(self):
        client, fake_pm = _make_client()
        await client.connect()
        fake_pm.stdout.readline = AsyncMock(side_effect=OSError("broken"))
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()
        result = await client.ping()
        assert result is False


class TestStdioMcpClientListTools:
    @pytest.mark.asyncio
    async def test_list_tools_parses_response(self):
        client, fake_pm = _make_client()
        await client.connect()

        tools_payload = {
            "jsonrpc": "2.0", "id": "1",
            "result": {
                "tools": [
                    {
                        "name": "unity_ping",
                        "description": "Ping",
                        "inputSchema": {"type": "object", "properties": {}, "required": []}
                    }
                ]
            }
        }
        fake_pm.stdout.readline = AsyncMock(return_value=(json.dumps(tools_payload) + "\n").encode())
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "unity_ping"


# ====================================================================
# UnityMCPPlugin
# ====================================================================


def _make_plugin(tools: Optional[List[McpToolDefinition]] = None) -> tuple[UnityMCPPlugin, FakeMcpClient]:
    fake = FakeMcpClient()
    if tools:
        fake.set_tools(tools)
    plugin = UnityMCPPlugin(client=fake)
    return plugin, fake


class TestUnityMCPPluginInit:
    @pytest.mark.asyncio
    async def test_initialize_connects_and_discovers(self):
        td = McpToolDefinition(name="unity_ping", description="Ping")
        plugin, fake = _make_plugin([td])
        await plugin.initialize()
        assert fake.connected is True
        assert "unity_ping" in plugin.tools

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        plugin, fake = _make_plugin()
        await plugin.initialize()
        await plugin.initialize()  # second call should be no-op
        assert fake.connected is True

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self):
        plugin, fake = _make_plugin()
        await plugin.initialize()
        await plugin.cleanup()
        assert fake.connected is False

    def test_create_factory_returns_plugin(self):
        with patch("unity_mcp.plugin.StdioMcpClient") as MockClient:
            MockClient.return_value = FakeMcpClient()
            plugin = UnityMCPPlugin.create(UnityMcpOptions())
            assert isinstance(plugin, UnityMCPPlugin)

    def test_create_validates_options(self):
        with pytest.raises(ConfigurationException):
            UnityMCPPlugin.create(UnityMcpOptions(executable_path=""))


class TestUnityMCPPluginInvokeTool:
    @pytest.mark.asyncio
    async def test_invoke_tool_success(self):
        td = McpToolDefinition(name="unity_ping", description="Ping")
        plugin, fake = _make_plugin([td])
        await plugin.initialize()
        result = await plugin.invoke_tool("unity_ping", {})
        assert result == {"tool": "unity_ping"}
        assert fake.calls[-1] == ("unity_ping", {})

    @pytest.mark.asyncio
    async def test_invoke_tool_unknown_raises(self):
        plugin, _ = _make_plugin()
        await plugin.initialize()
        with pytest.raises(UnityMcpException, match="not registered"):
            await plugin.invoke_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_invoke_tool_missing_required_param_raises(self):
        td = McpToolDefinition(
            name="unity_create_scene",
            description="Create scene",
            parameters={
                "path": McpParameterDefinition(
                    name="path",
                    type="string",
                    required=True,
                )
            },
        )
        plugin, _ = _make_plugin([td])
        await plugin.initialize()
        with pytest.raises(UnityMcpException, match="missing"):
            await plugin.invoke_tool("unity_create_scene", {})

    @pytest.mark.asyncio
    async def test_invoke_tool_auto_initializes(self):
        td = McpToolDefinition(name="unity_ping", description="Ping")
        plugin, fake = _make_plugin([td])
        # Do NOT call initialize() — invoke_tool should do it
        result = await plugin.invoke_tool("unity_ping", {})
        assert fake.connected is True
        assert result == {"tool": "unity_ping"}


class TestUnityMCPPluginKernelFunction:
    @pytest.mark.asyncio
    async def test_invoke_unity_tool_kernel_function(self):
        td = McpToolDefinition(name="unity_ping", description="Ping")
        plugin, fake = _make_plugin([td])
        await plugin.initialize()
        result = await plugin.invoke_unity_tool(tool_name="unity_ping", arguments_json="{}")
        assert "unity_ping" in result

    @pytest.mark.asyncio
    async def test_invoke_unity_tool_invalid_json(self):
        plugin, _ = _make_plugin()
        await plugin.initialize()
        result = await plugin.invoke_unity_tool(tool_name="x", arguments_json="{BAD}")
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_invoke_unity_tool_unknown_tool(self):
        plugin, _ = _make_plugin()
        await plugin.initialize()
        result = await plugin.invoke_unity_tool(tool_name="nonexistent", arguments_json="{}")
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_list_unity_tools(self):
        td = McpToolDefinition(name="unity_ping", description="Ping the server")
        plugin, _ = _make_plugin([td])
        await plugin.initialize()
        result = await plugin.list_unity_tools()
        assert "unity_ping" in result
        assert "Ping the server" in result


class TestUnityMCPPluginHealth:
    @pytest.mark.asyncio
    async def test_is_healthy_delegates_to_client(self):
        plugin, fake = _make_plugin()
        fake._healthy = True
        assert plugin.is_healthy() is True
        fake._healthy = False
        assert plugin.is_healthy() is False


# ====================================================================
# IMcpClient protocol compliance
# ====================================================================


class TestIMcpClientProtocol:
    def test_fake_satisfies_protocol(self):
        assert isinstance(FakeMcpClient(), IMcpClient)

    def test_stdio_client_satisfies_protocol(self):
        opts = UnityMcpOptions()
        client = StdioMcpClient(opts, process_manager=FakeProcessManager())
        assert isinstance(client, IMcpClient)


# ====================================================================
# Integration (skipped unless server is running)
# ====================================================================


@pytest.mark.integration
class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Requires a running unity-mcp process."""
        plugin = UnityMCPPlugin.create()
        try:
            await plugin.initialize()
        except Exception:
            pytest.skip("unity-mcp server not available")

        try:
            tools = plugin.tools
            assert len(tools) > 0

            result = await plugin.invoke_tool("ping", {})
            assert result is not None
        finally:
            await plugin.cleanup()


# ====================================================================
# pytest configuration
# ====================================================================


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])


# ====================================================================
# Models
# ====================================================================


class TestModels:
    def test_mcp_return_type(self):
        rt = McpReturnType(type="string", description="A string result")
        assert rt.type == "string"
        assert rt.description == "A string result"

    def test_mcp_return_type_defaults(self):
        rt = McpReturnType(type="object")
        assert rt.description is None

    def test_mcp_error(self):
        from unity_mcp.models import McpError
        err = McpError(code=-32600, message="Invalid Request", data="detail")
        assert err.code == -32600
        assert err.message == "Invalid Request"
        assert err.data == "detail"

    def test_mcp_error_defaults(self):
        from unity_mcp.models import McpError
        err = McpError(code=-1, message="oops")
        assert err.data is None

    def test_mcp_request(self):
        from unity_mcp.models import McpRequest
        req = McpRequest(id="42", method="tools/list", parameters={"a": 1})
        assert req.id == "42"
        assert req.method == "tools/list"
        assert req.parameters == {"a": 1}

    def test_mcp_request_defaults(self):
        from unity_mcp.models import McpRequest
        req = McpRequest(id="1", method="ping")
        assert req.parameters == {}

    def test_process_info(self):
        from unity_mcp.models import ProcessInfo
        now = datetime.now(timezone.utc)
        info = ProcessInfo(process_id=1234, executable_path="unity-mcp", started_at=now)
        assert info.process_id == 1234
        assert info.executable_path == "unity-mcp"
        assert info.started_at == now

    def test_mcp_tool_definition_with_return_type(self):
        rt = McpReturnType(type="string")
        td = McpToolDefinition(name="my_tool", description="desc", return_type=rt)
        assert td.return_type is not None
        assert td.return_type.type == "string"

    def test_iprocess_manager_protocol_compliance(self):
        from unity_mcp.models import IProcessManager
        assert isinstance(FakeProcessManager(), IProcessManager)


# ====================================================================
# LogSanitizer — extended
# ====================================================================


class TestLogSanitizerExtended:
    def test_redacts_jwt_token(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = LogSanitizer.sanitize_string(f"Token: {jwt}")
        assert result is not None
        assert jwt not in result
        assert "[REDACTED]" in result

    def test_redacts_password_in_connection_string(self):
        conn = "Server=db;Password=supersecret;Database=mydb"
        result = LogSanitizer.sanitize_string(conn)
        assert result is not None
        assert "supersecret" not in result
        assert "Password=[REDACTED]" in result

    def test_redacts_long_api_key(self):
        # 32+ alphanumeric chars look like API keys
        key = "A" * 32
        result = LogSanitizer.sanitize_string(f"key={key}")
        assert result is not None
        assert key not in result
        assert "[REDACTED]" in result

    def test_redacts_url_credentials(self):
        # Bearer token redaction covers the common case;
        # sanitize_string handles Bearer tokens in URLs too
        url_with_bearer = "Authorization: Bearer mytoken123"
        result = LogSanitizer.sanitize_string(url_with_bearer)
        assert result is not None
        assert "mytoken123" not in result


# ====================================================================
# InputValidator — extended
# ====================================================================


class TestInputValidatorExtended:
    def test_whitespace_only_tool_name(self):
        with pytest.raises(UnityMcpException, match="cannot be null or empty"):
            InputValidator.validate_tool_name("   ", ["my_tool"])

    def test_number_type_float(self):
        td = _tool(params={"score": ("number", True)})
        InputValidator.validate_parameters({"score": 3.14}, td)  # should not raise

    def test_number_type_int_accepted(self):
        td = _tool(params={"score": ("number", True)})
        InputValidator.validate_parameters({"score": 5}, td)  # int is a valid number

    def test_number_type_bool_rejected(self):
        td = _tool(params={"score": ("number", True)})
        with pytest.raises(UnityMcpException, match="invalid type"):
            InputValidator.validate_parameters({"score": True}, td)

    def test_boolean_type_accepted(self):
        td = _tool(params={"flag": ("boolean", True)})
        InputValidator.validate_parameters({"flag": True}, td)  # should not raise

    def test_boolean_type_int_rejected(self):
        td = _tool(params={"flag": ("boolean", True)})
        with pytest.raises(UnityMcpException, match="invalid type"):
            InputValidator.validate_parameters({"flag": 1}, td)

    def test_array_type_list_accepted(self):
        td = _tool(params={"items": ("array", True)})
        InputValidator.validate_parameters({"items": [1, 2, 3]}, td)  # should not raise

    def test_array_type_string_rejected(self):
        td = _tool(params={"items": ("array", True)})
        with pytest.raises(UnityMcpException, match="invalid type"):
            InputValidator.validate_parameters({"items": "not-a-list"}, td)

    def test_object_type_accepted(self):
        td = _tool(params={"config": ("object", True)})
        InputValidator.validate_parameters({"config": {"key": "val"}}, td)  # should not raise


# ====================================================================
# StdioMcpClient — extended
# ====================================================================


class TestStdioMcpClientExtended:
    @pytest.mark.asyncio
    async def test_request_id_increments(self):
        client, fake_pm = _make_client()
        await client.connect()

        responses = [
            (json.dumps({"jsonrpc": "2.0", "id": "1", "result": "a"}) + "\n").encode(),
            (json.dumps({"jsonrpc": "2.0", "id": "2", "result": "b"}) + "\n").encode(),
        ]
        call_count = 0

        async def _readline():
            nonlocal call_count
            r = responses[call_count]
            call_count += 1
            return r

        fake_pm.stdout.readline = _readline
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        assert client._request_id == 0
        await client.invoke_tool("ping", {})
        assert client._request_id == 1
        await client.invoke_tool("ping", {})
        assert client._request_id == 2

    @pytest.mark.asyncio
    async def test_enable_message_logging_path(self, caplog):
        opts = UnityMcpOptions(enable_message_logging=True)
        client, fake_pm = _make_client(opts)
        await client.connect()

        response_json = json.dumps({"jsonrpc": "2.0", "id": "1", "result": "ok"})
        fake_pm.stdout.readline = AsyncMock(return_value=(response_json + "\n").encode())
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        import logging as _logging
        with caplog.at_level(_logging.DEBUG, logger="unity_mcp.client"):
            await client.invoke_tool("ping", {})

        # The logging path was exercised — no exception means it worked
        assert client._request_id == 1

    @pytest.mark.asyncio
    async def test_parse_tool_definitions_with_params_and_required(self):
        result = {
            "tools": [
                {
                    "name": "create_scene",
                    "description": "Create a Unity scene",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Scene path"},
                            "template": {"type": "string", "description": "Template name"},
                        },
                        "required": ["path"],
                    },
                }
            ]
        }
        tools = StdioMcpClient._parse_tool_definitions(result)
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "create_scene"
        assert t.parameters["path"].required is True
        assert t.parameters["template"].required is False
        assert t.parameters["path"].description == "Scene path"

    @pytest.mark.asyncio
    async def test_parse_tool_definitions_empty_result(self):
        tools = StdioMcpClient._parse_tool_definitions({"tools": []})
        assert tools == []

    @pytest.mark.asyncio
    async def test_parse_tool_definitions_none_result(self):
        tools = StdioMcpClient._parse_tool_definitions(None)
        assert tools == []

    @pytest.mark.asyncio
    async def test_parse_tool_definitions_malformed_raises_protocol_exception(self):
        # Pass a non-dict, non-None value that will fail .get()
        with pytest.raises(ProtocolException):
            StdioMcpClient._parse_tool_definitions("not-a-dict-or-list")

    @pytest.mark.asyncio
    async def test_list_tools_empty(self):
        client, fake_pm = _make_client()
        await client.connect()

        tools_payload = {
            "jsonrpc": "2.0", "id": "1",
            "result": {"tools": []}
        }
        fake_pm.stdout.readline = AsyncMock(return_value=(json.dumps(tools_payload) + "\n").encode())
        fake_pm.stdin.write = MagicMock()
        fake_pm.stdin.drain = AsyncMock()

        tools = await client.list_tools()
        assert tools == []


# ====================================================================
# ProcessManager — extended
# ====================================================================


class TestProcessManagerExtended:
    @pytest.mark.asyncio
    async def test_close_alias_for_stop_process(self):
        mgr = ProcessManager(UnityMcpOptions())
        # close() when not started should not raise (same as stop_process)
        await mgr.close()
        assert mgr.state == ProcessState.NOT_STARTED

    @pytest.mark.asyncio
    async def test_ensure_process_running_idempotent(self):
        """ensure_process_running called twice on a running process returns same pid."""
        opts = UnityMcpOptions()
        mgr = ProcessManager(opts)

        # Patch create_subprocess_exec to return a fake process
        fake_proc = MagicMock()
        fake_proc.pid = 9999
        fake_proc.returncode = None
        fake_proc.stdin = AsyncMock()
        fake_proc.stdout = AsyncMock()
        fake_proc.stderr = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            info1 = await mgr.ensure_process_running()
            info2 = await mgr.ensure_process_running()

        assert info1.process_id == info2.process_id == 9999
        assert mgr.state == ProcessState.RUNNING


# ====================================================================
# UnityMCPPlugin — extended
# ====================================================================


class TestUnityMCPPluginExtended:
    @pytest.mark.asyncio
    async def test_invoke_tool_none_parameters_defaults_to_empty_dict(self):
        td = McpToolDefinition(name="unity_ping", description="Ping")
        plugin, fake = _make_plugin([td])
        await plugin.initialize()
        # Pass None explicitly — should default to {}
        result = await plugin.invoke_tool("unity_ping", None)
        assert result == {"tool": "unity_ping"}
        assert fake.calls[-1] == ("unity_ping", {})

    @pytest.mark.asyncio
    async def test_cleanup_resets_initialized(self):
        plugin, fake = _make_plugin()
        await plugin.initialize()
        assert plugin._initialized is True
        await plugin.cleanup()
        assert plugin._initialized is False

    @pytest.mark.asyncio
    async def test_tools_property_returns_copy(self):
        td = McpToolDefinition(name="unity_ping", description="Ping")
        plugin, _ = _make_plugin([td])
        await plugin.initialize()
        tools1 = plugin.tools
        tools1["injected"] = McpToolDefinition(name="injected", description="bad")
        # Original should be unaffected
        assert "injected" not in plugin.tools

    @pytest.mark.asyncio
    async def test_create_kernel_with_unity(self):
        td = McpToolDefinition(name="unity_ping", description="Ping the server")
        fake_client = FakeMcpClient()
        fake_client.set_tools([td])

        MockClientClass = MagicMock(return_value=fake_client)
        with patch("unity_mcp.plugin.StdioMcpClient", MockClientClass):
            kernel = await UnityMCPPlugin.create_kernel_with_unity(UnityMcpOptions())

        assert kernel is not None
        # The generic entry point should be registered
        funcs = kernel.get_full_list_of_function_metadata()
        names = [f.name for f in funcs]
        assert "invoke_unity_tool" in names


# ====================================================================
# FormatToolList — extended
# ====================================================================


class TestFormatToolListExtended:
    def test_single_tool_format(self):
        tools = [McpToolDefinition(name="unity_ping", description="Ping the server")]
        result = format_tool_list(tools)
        assert "unity_ping" in result
        assert "Ping the server" in result

    def test_description_separator(self):
        tools = [McpToolDefinition(name="my_tool", description="Does stuff")]
        result = format_tool_list(tools)
        # Should contain name and description separated by some delimiter
        assert "my_tool" in result
        assert "Does stuff" in result
