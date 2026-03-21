"""
Semantic Kernel plugin exposing Unity MCP tools.

Design
------
* **Dynamic discovery** — tools are discovered at runtime via ``list_tools()``;
  no hardcoded wrappers.  A single ``@kernel_function`` entry point
  (``invoke_unity_tool``) handles all tool calls.
* **Static factory** — ``create_kernel_with_unity()`` builds a ``Kernel`` and
  registers every discovered tool as an individual ``KernelFunction``, so SK
  planners can reason about them by name.
* **Dependency Inversion** — constructor accepts any ``IMcpClient``; the
  ``create()`` classmethod wires up the default ``StdioMcpClient``.
* **Lifecycle** — ``initialize()`` / ``cleanup()`` bracket the session.
* **Validation** — ``InputValidator`` guards every invocation.
* **Backward compat** — ``UnityMCPPlugin`` alias kept; old ``create()``
  signature still works.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Dict, Optional

from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function

from .client import StdioMcpClient
from ._formatting import format_result, format_tool_list
from .exceptions import UnityMcpException
from .kernel_registration import register_unity_tools_as_functions
from .models import IMcpClient, IMcpToolMapper, McpToolDefinition, UnityMcpOptions
from .security import InputValidator, LogSanitizer
from .tool_mapper import McpToolMapper

logger = logging.getLogger(__name__)


class UnityMCPPlugin:
    """
    Semantic Kernel plugin for the Unity MCP server.

    Provides a generic ``invoke_unity_tool`` kernel function plus a static
    factory (``create_kernel_with_unity``) that registers every discovered
    tool as its own ``KernelFunction``.

    Typical usage::

        # Simple — one generic entry point
        plugin = await UnityMCPPlugin.create()
        kernel.add_plugin(plugin, plugin_name="unity")
        result = await plugin.invoke_tool("unity_create_scene", {"path": "Assets/Scenes/New.unity"})

        # Rich — individual functions per tool (best for planners)
        kernel = await UnityMCPPlugin.create_kernel_with_unity()
        result = await kernel.invoke("unity", "unity_create_scene", path="Assets/Scenes/New.unity")
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        client: IMcpClient,
        options: Optional[UnityMcpOptions] = None,
        tool_mapper: Optional[IMcpToolMapper] = None,
    ) -> None:
        self._client = client
        self._options = options or UnityMcpOptions()
        self._tool_mapper = tool_mapper or McpToolMapper()
        self._initialized = False

    @classmethod
    def create(cls, options: Optional[UnityMcpOptions] = None) -> "UnityMCPPlugin":
        """
        Factory that wires up the default ``StdioMcpClient``.

        Args:
            options: Configuration; defaults to ``UnityMcpOptions()``.
        """
        opts = options or UnityMcpOptions()
        opts.validate()
        client = StdioMcpClient(opts)
        return cls(client, opts)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Connect to the server and discover available tools.

        Raises ``NetworkException`` / ``ProcessException`` on failure.
        """
        if self._initialized:
            return
        logger.info("Initializing Unity MCP plugin")
        await self._client.connect()
        tools = await self._client.list_tools()
        self._tool_mapper.initialize(tools)
        self._initialized = True
        logger.info("Unity MCP plugin initialized with %d tools", len(self.get_registered_tools()))

    async def cleanup(self) -> None:
        """Close the client connection and release resources."""
        await self._client.close()
        self._initialized = False
        logger.debug("Unity MCP plugin cleaned up")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def tools(self) -> Dict[str, McpToolDefinition]:
        """Discovered tool definitions, keyed by tool name."""
        return {tool.name: tool for tool in self.get_registered_tools()}

    def map_tool_definition(self, tool: McpToolDefinition) -> Dict[str, Any]:
        """Map one MCP tool definition into SK metadata primitives."""
        return self._tool_mapper.map_tool_definition(tool)

    def get_tool_by_name(self, tool_name: str) -> Optional[McpToolDefinition]:
        """Return one registered tool by name, or None."""
        return self._tool_mapper.get_tool_by_name(tool_name)

    def get_tool_names(self) -> list[str]:
        """Return deterministic sorted tool names."""
        return self._tool_mapper.get_tool_names()

    def get_registered_tools(self) -> list[McpToolDefinition]:
        """Return all mapped tools in deterministic order."""
        return self._tool_mapper.get_registered_tools()

    def is_healthy(self) -> bool:
        """Delegate to the underlying client health check."""
        return self._client.is_healthy()

    async def invoke_tool(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Invoke a Unity MCP tool by name.

        Validates the tool name and parameters before sending.
        Returns the raw result value from the MCP response.

        Args:
            tool_name: Exact tool name as reported by the server.
            parameters: Key/value arguments for the tool.

        Raises:
            ``UnityMcpException`` on validation failure.
            ``McpServerException`` on server-side errors.
            ``NetworkException`` / ``TimeoutException`` on transport errors.
        """
        await self._ensure_initialized()
        params = parameters or {}

        InputValidator.validate_tool_name(tool_name, self.get_tool_names())
        tool_def = self.get_tool_by_name(tool_name)
        if tool_def is None:
            raise UnityMcpException(f"Tool '{tool_name}' is not registered")
        InputValidator.validate_parameters(params, tool_def)

        if self._options.enable_message_logging:
            safe_params = LogSanitizer.sanitize_parameters(params)
            logger.debug("Invoking tool '%s' with params: %s", tool_name, safe_params)

        response = await self._client.invoke_tool(tool_name, params)
        return response.result

    # ------------------------------------------------------------------
    # Kernel function — generic entry point
    # ------------------------------------------------------------------

    @kernel_function(
        name="invoke_unity_tool",
        description=(
            "Invoke any Unity MCP tool by name. "
            "Pass the exact tool name and a JSON string of arguments."
        ),
    )
    async def invoke_unity_tool(
        self,
        tool_name: Annotated[str, "Exact name of the Unity MCP tool to invoke"],
        arguments_json: Annotated[
            str,
            "JSON object of arguments for the tool (use '{}' for no arguments)",
        ] = "{}",
    ) -> str:
        """Generic SK entry point — delegates to ``invoke_tool``."""
        try:
            params = json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in arguments_json: {exc}"})
        try:
            result = await self.invoke_tool(tool_name, params)
            return format_result(result)
        except UnityMcpException as exc:
            safe = InputValidator.sanitize_error_message(str(exc))
            return json.dumps({"error": safe})

    @kernel_function(
        name="list_unity_tools",
        description="List all available Unity MCP tools with their descriptions.",
    )
    async def list_unity_tools(self) -> str:
        """Return a formatted list of all discovered tools."""
        await self._ensure_initialized()
        return format_tool_list(self.get_registered_tools())

    # ------------------------------------------------------------------
    # Static factory — full kernel with per-tool functions
    # ------------------------------------------------------------------

    @staticmethod
    async def create_kernel_with_unity(
        options: Optional[UnityMcpOptions] = None,
        plugin_name: str = "unity",
    ) -> Kernel:
        """
        Build a ``Kernel`` and register every discovered Unity tool as an
        individual ``KernelFunction``.

        This is the recommended entry point for SK planners, because each
        tool appears as a first-class function with its own name, description,
        and parameter schema.

        Args:
            options: Plugin configuration; defaults to ``UnityMcpOptions()``.
            plugin_name: Name under which the plugin is registered.

        Returns:
            A configured ``Kernel`` instance.

        Example::

            kernel = await UnityMCPPlugin.create_kernel_with_unity()
            result = await kernel.invoke("unity", "unity_create_scene",
                                         path="Assets/Scenes/New.unity")
        """
        plugin = UnityMCPPlugin.create(options)
        await plugin.initialize()

        kernel = Kernel()

        # Register router mode for backward compatibility.
        kernel.add_plugin(plugin, plugin_name=plugin_name)
        register_unity_tools_as_functions(kernel=kernel, plugin=plugin, plugin_name=plugin_name)
        logger.info(
            "Registered %d Unity tools as kernel functions under plugin '%s'",
            len(plugin.get_registered_tools()),
            plugin_name,
        )

        return kernel

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()
