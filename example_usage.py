"""
Example usage of Unity MCP Plugin with Semantic Kernel

This script demonstrates how to:
1. Initialize the Semantic Kernel
2. Load the Unity MCP plugin
3. Use Unity tools through SK functions
4. Create complex workflows combining multiple tools
"""

import asyncio
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from unity_mcp_plugin import UnityMCPPlugin


async def basic_example():
    """Basic example: Test connectivity and create a simple scene."""
    
    print("=" * 60)
    print("Basic Example: Unity MCP Plugin with Semantic Kernel")
    print("=" * 60)
    print()
    
    # Initialize Semantic Kernel
    kernel = sk.Kernel()
    
    # Optional: Add AI service for intelligent orchestration
    # Uncomment if you have an OpenAI API key
    # kernel.add_chat_service(
    #     "chat",
    #     OpenAIChatCompletion("gpt-4", api_key="your-api-key")
    # )
    
    # Create and initialize Unity MCP plugin
    print("1. Initializing Unity MCP Plugin...")
    unity_plugin = UnityMCPPlugin(
        skill_manifest_path="unity-mcp-server.skill.json",  # Optional
        host="localhost",
        port=8765
    )
    
    # Initialize connection
    if not await unity_plugin.initialize():
        print("✗ Failed to connect to Unity MCP Server")
        print("  Make sure Unity Editor is running with the MCP Server active")
        return
    
    print()
    
    # Import plugin into kernel
    print("2. Importing plugin into Semantic Kernel...")
    kernel.add_plugin(unity_plugin, plugin_name="unity")
    print("✓ Plugin imported successfully")
    print()
    
    # Test connectivity
    print("3. Testing connectivity...")
    result = await kernel.invoke(
        plugin_name="unity", 
        function_name="ping", 
        message="Hello Unity!"
    )
    print(f"   Result: {result}")
    print()
    
    # Create a new scene
    print("4. Creating a new scene...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_scene",
        scene_name="DemoScene", 
        setup="default"
    )
    print(f"   Result: {result}")
    print()
    
    # Get scene information
    print("5. Getting scene information...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="get_scene_info",
        include_hierarchy=False
    )
    print(f"   Result: {result}")
    print()
    
    # Cleanup
    await unity_plugin.cleanup()
    print("✓ Example completed successfully")


async def advanced_example():
    """Advanced example: Create a complete game scene with multiple objects."""
    
    print("=" * 60)
    print("Advanced Example: Creating a Game Scene")
    print("=" * 60)
    print()
    
    # Initialize kernel and plugin
    kernel = sk.Kernel()
    unity_plugin = UnityMCPPlugin(host="localhost", port=8765)
    
    if not await unity_plugin.initialize():
        print("✗ Failed to connect to Unity MCP Server")
        return
    
    kernel.add_plugin(unity_plugin, plugin_name="unity")
    
    # Step 1: Create a new game scene
    print("1. Creating game scene 'PlatformerLevel'...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_scene",
        scene_name="PlatformerLevel", 
        setup="default"
    )
    print(f"   {result}")
    print()
    
    # Step 2: Create ground platform
    print("2. Creating ground platform...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_gameobject",
        name="Ground",
        object_type="plane",
        position_x=0,
        position_y=0,
        position_z=0
    )
    print(f"   {result}")
    print()
    
    # Step 3: Create player object
    print("3. Creating player...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_gameobject",
        name="Player",
        object_type="cube",
        position_x=0,
        position_y=1,
        position_z=0
    )
    print(f"   {result}")
    print()
    
    # Step 4: Create enemy objects
    print("4. Creating enemies...")
    for i in range(3):
        x_pos = (i + 1) * 3
        result = await kernel.invoke(
            plugin_name="unity",
            function_name="create_gameobject",
            name=f"Enemy{i+1}",
            object_type="sphere",
            position_x=x_pos,
            position_y=1,
            position_z=0
        )
        print(f"   Created Enemy{i+1} at x={x_pos}")
    print()
    
    # Step 5: Create collectible items
    print("5. Creating collectibles...")
    for i in range(5):
        x_pos = i * 2
        y_pos = 0.5
        result = await kernel.invoke(
            plugin_name="unity",
            function_name="create_gameobject",
            name=f"Coin{i+1}",
            object_type="cylinder",
            position_x=x_pos,
            position_y=y_pos,
            position_z=2
        )
        print(f"   Created Coin{i+1}")
    print()
    
    # Step 6: Generate player controller script
    print("6. Generating PlayerController script...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_script",
        script_name="PlayerController",
        script_type="monobehaviour",
        namespace="Game.Player"
    )
    print(f"   {result}")
    print()
    
    # Step 7: Generate enemy AI script
    print("7. Generating EnemyAI script...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_script",
        script_name="EnemyAI",
        script_type="monobehaviour",
        namespace="Game.Enemies"
    )
    print(f"   {result}")
    print()
    
    # Step 8: Get final scene info
    print("8. Final scene statistics...")
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="get_scene_info",
        include_hierarchy=False
    )
    print(f"   {result}")
    print()
    
    # Cleanup
    await unity_plugin.cleanup()
    print("✓ Advanced example completed successfully")


async def ai_orchestrated_example():
    """
    Example using AI to orchestrate Unity operations.
    Requires OpenAI API key.
    """
    
    print("=" * 60)
    print("AI-Orchestrated Example")
    print("=" * 60)
    print()
    
    # This example requires an OpenAI API key
    api_key = input("Enter your OpenAI API key (or 'skip' to skip): ")
    
    if api_key.lower() == 'skip':
        print("Skipping AI-orchestrated example")
        return
    
    # Initialize kernel with AI
    kernel = sk.Kernel()
    kernel.add_chat_service(
        "chat",
        OpenAIChatCompletion("gpt-4", api_key=api_key)
    )
    
    # Initialize Unity plugin
    unity_plugin = UnityMCPPlugin(host="localhost", port=8765)
    
    if not await unity_plugin.initialize():
        print("✗ Failed to connect to Unity MCP Server")
        return
    
    kernel.add_plugin(unity_plugin, plugin_name="unity")
    
    # Create a semantic function that uses Unity tools
    semantic_function = kernel.create_semantic_function(
        prompt_template="""
You are a Unity game designer assistant. Based on the user's request,
create appropriate Unity scenes and objects.

Available Unity functions:
- create_scene: Create a new scene
- create_gameobject: Create GameObjects (types: cube, sphere, plane, etc.)
- create_script: Generate C# scripts

User Request: {{$input}}

Plan and execute the necessary Unity operations to fulfill this request.
Return a summary of what was created.
        """,
        function_name="design_scene",
        skill_name="designer"
    )
    
    # Use AI to create a scene based on natural language
    user_request = "Create a simple racing game scene with a track, a player car, and 3 obstacles"
    
    print(f"User Request: {user_request}")
    print()
    print("AI is planning and executing Unity operations...")
    print()
    
    result = await kernel.invoke(
        semantic_function,
        input=user_request
    )
    
    print("AI Response:")
    print(result)
    print()
    
    # Cleanup
    await unity_plugin.cleanup()
    print("✓ AI-orchestrated example completed")


async def direct_tool_usage():
    """Example of using the plugin tools directly (without SK orchestration)."""
    
    print("=" * 60)
    print("Direct Tool Usage Example")
    print("=" * 60)
    print()
    
    # Create plugin instance
    plugin = UnityMCPPlugin(host="localhost", port=8765)
    
    # Initialize
    if not await plugin.initialize():
        print("✗ Failed to connect")
        return
    
    # Use tools directly (not through SK)
    print("1. Direct ping call...")
    result = await plugin.ping(message="Direct call test")
    print(f"   {result}")
    print()
    
    print("2. Creating scene directly...")
    result = await plugin.create_scene(
        scene_name="DirectScene",
        setup="empty"
    )
    print(f"   {result}")
    print()
    
    print("3. Creating GameObject directly...")
    result = await plugin.create_gameobject(
        name="DirectCube",
        object_type="cube",
        position_x=1.0,
        position_y=2.0,
        position_z=3.0
    )
    print(f"   {result}")
    print()
    
    print("4. Getting scene info directly...")
    result = await plugin.get_scene_info(include_hierarchy=True)
    print(f"   {result}")
    print()
    
    # Cleanup
    await plugin.cleanup()
    print("✓ Direct usage example completed")


async def main():
    """Main entry point - run all examples."""
    
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 8 + "Unity MCP Plugin - Semantic Kernel Examples" + " " * 7 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    print("This script demonstrates various ways to use the Unity MCP Plugin")
    print("with Semantic Kernel.")
    print()
    print("Prerequisites:")
    print("  • Unity Editor must be running")
    print("  • Unity MCP Server must be active (check Console)")
    print("  • Server should be listening on localhost:8765")
    print()
    
    choice = input("Choose example to run:\n"
                  "  1. Basic Example (simple operations)\n"
                  "  2. Advanced Example (complete game scene)\n"
                  "  3. AI-Orchestrated Example (requires OpenAI key)\n"
                  "  4. Direct Tool Usage (without SK)\n"
                  "  5. Run all (except AI)\n"
                  "Choice (1-5): ")
    
    print()
    
    try:
        if choice == "1":
            await basic_example()
        elif choice == "2":
            await advanced_example()
        elif choice == "3":
            await ai_orchestrated_example()
        elif choice == "4":
            await direct_tool_usage()
        elif choice == "5":
            await basic_example()
            print("\n" + "=" * 60 + "\n")
            await advanced_example()
            print("\n" + "=" * 60 + "\n")
            await direct_tool_usage()
        else:
            print("Invalid choice")
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
