"""
Semantic Kernel registration helpers for Unity MCP plugin.
"""

from __future__ import annotations

from typing import Any, List

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelFunction, kernel_function
from semantic_kernel.functions.kernel_function_from_method import KernelFunctionFromMethod
from semantic_kernel.functions.kernel_parameter_metadata import KernelParameterMetadata
from semantic_kernel.functions.kernel_plugin import KernelPlugin

from ._formatting import format_result
from .exceptions import UnityMcpException


def register_unity_tools_as_functions(
    kernel: Kernel,
    plugin: Any,
    plugin_name: str = "unity",
) -> KernelPlugin:
    """
    Register discovered Unity tools as individual SK functions in one plugin.

    The plugin must already be initialized. Tool metadata and parameter schema
    are sourced from the plugin mapper, not from the MCP client.
    """
    registered_tools = plugin.get_registered_tools()
    if not registered_tools:
        raise UnityMcpException(
            "Unity MCP plugin is not initialized or no tools were discovered. "
            "Call initialize() before expanded function registration."
        )

    functions: List[KernelFunction] = []
    for tool in registered_tools:
        mapped = plugin.map_tool_definition(tool)
        function = _make_kernel_function(plugin=plugin, tool_name=tool.name, mapped=mapped, plugin_name=plugin_name)
        functions.append(function)

    return kernel.add_functions(plugin_name=plugin_name, functions=functions)


def _make_kernel_function(
    plugin: Any,
    tool_name: str,
    mapped: dict[str, Any],
    plugin_name: str,
) -> KernelFunction:
    parameters = [
        KernelParameterMetadata(
            name=param["name"],
            description=param.get("description"),
            default_value=param.get("default"),
            type=param.get("type", "string"),
            is_required=param.get("required", False),
            schema_data=param.get("schema_data"),
        )
        for param in mapped.get("parameters", [])
    ]

    return_parameter = KernelParameterMetadata(
        name="return",
        description=(mapped.get("return", {}) or {}).get("description"),
        type=(mapped.get("return", {}) or {}).get("type", "object"),
        is_required=False,
    )

    async def _fn(**kwargs: Any) -> str:
        params = {key: value for key, value in kwargs.items() if value is not None and key != "kernel"}
        result = await plugin.invoke_tool(tool_name, params)
        return format_result(result)

    _fn.__name__ = tool_name
    _fn.__doc__ = mapped.get("description", "")
    decorated = kernel_function(name=tool_name, description=mapped.get("description", ""))(_fn)
    return KernelFunctionFromMethod(
        method=decorated,
        plugin_name=plugin_name,
        parameters=parameters,
        return_parameter=return_parameter,
    )
