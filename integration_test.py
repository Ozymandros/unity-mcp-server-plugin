"""
Simple integration test to verify the plugin works with a running Unity MCP Server.

Run this script to quickly test the plugin without pytest.

Prerequisites:
- Unity Editor must be running
- Unity MCP Server must be active on localhost:8765
"""

import asyncio
import sys
from unity_mcp_plugin import UnityMCPPlugin


async def test_connection():
    """Test basic connection to server."""
    print("Testing connection to Unity MCP Server...")
    
    plugin = UnityMCPPlugin()
    
    if not await plugin.initialize():
        print("✗ Failed to connect to Unity MCP Server")
        print("\nMake sure:")
        print("  1. Unity Editor is running")
        print("  2. Unity MCP Server is active (check Console)")
        print("  3. Server is listening on localhost:8765")
        return False
    
    print("✓ Connected successfully")
    await plugin.cleanup()
    return True


async def test_ping():
    """Test ping functionality."""
    print("\nTesting ping...")
    
    plugin = UnityMCPPlugin()
    if not await plugin.initialize():
        print("✗ Connection failed, skipping ping test")
        return False
    
    result = await plugin.ping(message="Integration test")
    print(f"✓ Ping result: {result}")
    
    await plugin.cleanup()
    return True


async def test_create_scene():
    """Test scene creation."""
    print("\nTesting scene creation...")
    
    plugin = UnityMCPPlugin()
    if not await plugin.initialize():
        print("✗ Connection failed, skipping scene creation test")
        return False
    
    result = await plugin.create_scene(
        scene_name="IntegrationTestScene",
        setup="empty"
    )
    print(f"✓ Scene creation result: {result}")
    
    await plugin.cleanup()
    return True


async def test_create_gameobject():
    """Test GameObject creation."""
    print("\nTesting GameObject creation...")
    
    plugin = UnityMCPPlugin()
    if not await plugin.initialize():
        print("✗ Connection failed, skipping GameObject creation test")
        return False
    
    result = await plugin.create_gameobject(
        name="TestCube",
        object_type="cube",
        position_x=1.0,
        position_y=2.0,
        position_z=3.0
    )
    print(f"✓ GameObject creation result: {result}")
    
    await plugin.cleanup()
    return True


async def test_get_scene_info():
    """Test scene info retrieval."""
    print("\nTesting scene info retrieval...")
    
    plugin = UnityMCPPlugin()
    if not await plugin.initialize():
        print("✗ Connection failed, skipping scene info test")
        return False
    
    result = await plugin.get_scene_info(include_hierarchy=False)
    print(f"✓ Scene info result: {result}")
    
    await plugin.cleanup()
    return True


async def test_create_script():
    """Test script creation."""
    print("\nTesting script creation...")
    
    plugin = UnityMCPPlugin()
    if not await plugin.initialize():
        print("✗ Connection failed, skipping script creation test")
        return False
    
    result = await plugin.create_script(
        script_name="IntegrationTestScript",
        script_type="monobehaviour",
        namespace="Test"
    )
    print(f"✓ Script creation result: {result}")
    
    await plugin.cleanup()
    return True


async def run_all_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("Unity MCP Plugin - Integration Tests")
    print("=" * 60)
    print()
    
    tests = [
        ("Connection", test_connection),
        ("Ping", test_ping),
        ("Create Scene", test_create_scene),
        ("Create GameObject", test_create_gameobject),
        ("Get Scene Info", test_get_scene_info),
        ("Create Script", test_create_script),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if await test_func():
                passed += 1
            else:
                failed += 1
                print(f"✗ {test_name} test failed")
        except Exception as e:
            failed += 1
            print(f"✗ {test_name} test failed with error: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


async def main():
    """Main entry point."""
    try:
        success = await run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
