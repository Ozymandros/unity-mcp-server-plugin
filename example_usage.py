"""
Example usage of Unity MCP Plugin v3.0.0 with Semantic Kernel.

Transport: stdio (subprocess) — the unity-mcp executable must be installed.
Install:   dotnet tool install -g unity-mcp

Demonstrates:
1. Simple plugin usage (generic invoke_tool)
2. Full kernel with per-tool functions (best for planners)
3. Custom options (retry, backoff, timeouts)
"""

from __future__ import annotations

import asyncio
import json

import semantic_kernel as sk

from unity_mcp import (
    BackoffStrategy,
    UnityMCPPlugin,
    UnityMcpOptions,
)


# ---------------------------------------------------------------------------
# Example 1 — Simple: one generic entry point
# ---------------------------------------------------------------------------


async def simple_example() -> None:
    print("=" * 60)
    print("Example 1: Simple plugin usage")
    print("=" * 60)

    plugin = UnityMCPPlugin.create()

    try:
        await plugin.initialize()
    except Exception as exc:
        print(f"  Could not connect: {exc}")
        print("  Make sure unity-mcp is installed and on PATH.")
        return

    kernel = sk.Kernel()
    kernel.add_plugin(plugin, plugin_name="unity")

    # List available tools
    tools_result = await kernel.invoke("unity", "list_unity_tools")
    print("Available tools:\n", tools_result)

    # Invoke a tool generically
    result = await kernel.invoke(
        "unity", "invoke_unity_tool",
        tool_name="unity_create_scene",
        arguments_json=json.dumps({"path": "Assets/Scenes/Demo.unity"}),
    )
    print("create_scene result:", result)

    await plugin.cleanup()


# ---------------------------------------------------------------------------
# Example 2 — Full kernel: per-tool functions (planner-friendly)
# ---------------------------------------------------------------------------


async def full_kernel_example() -> None:
    print("=" * 60)
    print("Example 2: Full kernel with per-tool functions")
    print("=" * 60)

    try:
        kernel = await UnityMCPPlugin.create_kernel_with_unity()
    except Exception as exc:
        print(f"  Could not build kernel: {exc}")
        return

    # Each discovered tool is now a first-class kernel function
    result = await kernel.invoke("unity", "unity_create_scene", path="Assets/Scenes/New.unity")
    print("create_scene:", result)

    result = await kernel.invoke("unity", "unity_list_assets", path="Assets", pattern="*.unity")
    print("list_assets:", result)


# ---------------------------------------------------------------------------
# Example 3 — Custom options
# ---------------------------------------------------------------------------


async def custom_options_example() -> None:
    print("=" * 60)
    print("Example 3: Custom options (exponential backoff, 5 retries)")
    print("=" * 60)

    options = UnityMcpOptions(
        executable_path="unity-mcp",
        connection_timeout_seconds=15,
        request_timeout_seconds=30,
        max_retry_attempts=5,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        initial_retry_delay_ms=500,
        enable_message_logging=True,
    )

    plugin = UnityMCPPlugin.create(options)

    try:
        await plugin.initialize()
    except Exception as exc:
        print(f"  Could not connect: {exc}")
        return

    print(f"  Connected. Tools discovered: {len(plugin.tools)}")
    print(f"  Healthy: {plugin.is_healthy()}")

    await plugin.cleanup()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + "  Unity MCP Plugin v3.0.0 — Semantic Kernel Examples  " + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    print("Prerequisites:")
    print("  dotnet tool install -g unity-mcp")
    print()

    choice = input(
        "Choose example:\n"
        "  1. Simple plugin (generic invoke_unity_tool)\n"
        "  2. Full kernel (per-tool functions, planner-friendly)\n"
        "  3. Custom options (retry / backoff)\n"
        "  4. Run all\n"
        "Choice (1-4): "
    ).strip()

    print()
    try:
        if choice == "1":
            await simple_example()
        elif choice == "2":
            await full_kernel_example()
        elif choice == "3":
            await custom_options_example()
        elif choice == "4":
            await simple_example()
            await full_kernel_example()
            await custom_options_example()
        else:
            print("Invalid choice.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as exc:
        import traceback
        print(f"\nError: {exc}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
