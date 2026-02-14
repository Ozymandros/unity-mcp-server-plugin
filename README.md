# Unity MCP Plugin for Semantic Kernel

A production-ready Semantic Kernel plugin that bridges Python applications with the Unity Editor through the Unity MCP Server. This plugin exposes Unity operations as SK kernel functions, enabling AI-powered Unity workflows.

## Features

✅ **Seamless Integration**: Works directly with Semantic Kernel  
✅ **Async/Await Support**: Full async operations for non-blocking execution  
✅ **Type-Safe**: Parameter validation against MCP schemas  
✅ **Auto-Discovery**: Loads tools from skill manifest or server discovery  
✅ **Production-Ready**: Comprehensive error handling and logging  
✅ **Well-Documented**: Complete examples and API documentation  

## Architecture

```text
┌─────────────────────────────────────────────────┐
│         Python Application (SK)                 │
│  ┌───────────────────────────────────────────┐  │
│  │      Semantic Kernel                      │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │    Unity MCP Plugin                 │  │  │
│  │  │  • ping()                           │  │  │
│  │  │  • create_scene()                   │  │  │
│  │  │  • create_gameobject()              │  │  │
│  │  │  • get_scene_info()                 │  │  │
│  │  │  • create_script()                  │  │  │
│  │  └──────────┬──────────────────────────┘  │  │
│  │             │                              │  │
│  │  ┌──────────▼──────────────────────────┐  │  │
│  │  │    UnityMCPClient                   │  │  │
│  │  │  • JSON-RPC 2.0 Protocol            │  │  │
│  │  │  • Async TCP Communication          │  │  │
│  │  └──────────┬──────────────────────────┘  │  │
│  └─────────────┼─────────────────────────────┘  │
└────────────────┼─────────────────────────────────┘
                 │ TCP (localhost:8765)
                 │ JSON-RPC 2.0
┌────────────────▼─────────────────────────────────┐
│           Unity Editor                           │
│  ┌───────────────────────────────────────────┐   │
│  │       Unity MCP Server                    │   │
│  │  • Scene Management                       │   │
│  │  • GameObject Creation                    │   │
│  │  • Script Generation                      │   │
│  │  • Scene Inspection                       │   │
│  └───────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.8 or later
- Unity Editor 2020.3+ with Unity MCP Server installed
- Semantic Kernel 0.9.0+

### Install from Source

```bash
# Clone or download the plugin
git clone https://github.com/yourusername/unity-mcp-plugin.git
cd unity-mcp-plugin

# Install dependencies
pip install -r requirements.txt

# Install the plugin
pip install -e .
```

### Install via pip (when published)

```bash
pip install unity-mcp-plugin
```

## Quick Start

### 1. Start Unity MCP Server

1. Open Unity Editor
2. Verify Unity MCP Server is running (check Console)
3. Confirm server is on `localhost:8765`

### 2. Basic Usage

```python
import asyncio
import semantic_kernel as sk
from unity_mcp_plugin import UnityMCPPlugin

async def main():
    # Initialize Semantic Kernel
    kernel = sk.Kernel()
    
    # Create Unity MCP plugin
    unity_plugin = UnityMCPPlugin(
        host="localhost",
        port=8765
    )
    
    # Initialize connection
    await unity_plugin.initialize()
    
    # Import into kernel
    kernel.add_plugin(unity_plugin, plugin_name="unity")
    
    # Use Unity functions
    result = await kernel.invoke(
        plugin_name="unity", 
        function_name="ping"
    )
    print(result)
    
    # Create a scene
    result = await kernel.invoke(
        plugin_name="unity",
        function_name="create_scene",
        scene_name="MyScene"
    )
    print(result)
    
    # Cleanup
    await unity_plugin.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Direct Tool Usage (Without SK)

```python
import asyncio
from unity_mcp_plugin import UnityMCPPlugin

async def main():
    plugin = UnityMCPPlugin()
    await plugin.initialize()
    
    # Call tools directly
    result = await plugin.ping(message="Hello")
    print(result)
    
    result = await plugin.create_scene(scene_name="DirectScene")
    print(result)
    
    result = await plugin.create_gameobject(
        name="Player",
        object_type="cube",
        position_x=0,
        position_y=1,
        position_z=0
    )
    print(result)
    
    await plugin.cleanup()

asyncio.run(main())
```

## Available Functions

### ping

Test connectivity with Unity MCP Server.

**Parameters:**
- `message` (str, optional): Message to echo back

**Example:**
```python
result = await plugin.ping(message="Hello Unity!")
```

### create_scene

Create a new Unity scene.

**Parameters:**
- `scene_name` (str): Name of the scene
- `path` (str, optional): Save path (default: "Assets/Scenes")
- `setup` (str, optional): "default" or "empty" (default: "default")

**Example:**
```python
result = await plugin.create_scene(
    scene_name="Level1",
    setup="default"
)
```

### create_gameobject

Create a GameObject in the active scene.

**Parameters:**
- `name` (str): GameObject name
- `object_type` (str, optional): Type - "empty", "cube", "sphere", "capsule", "cylinder", "plane", "quad"
- `position_x` (float, optional): X position
- `position_y` (float, optional): Y position
- `position_z` (float, optional): Z position
- `parent` (str, optional): Parent GameObject name

**Example:**
```python
result = await plugin.create_gameobject(
    name="Player",
    object_type="cube",
    position_x=0,
    position_y=1,
    position_z=0
)
```

### get_scene_info

Get information about the active scene.

**Parameters:**
- `include_hierarchy` (bool, optional): Include full hierarchy (default: True)
- `include_components` (bool, optional): Include components (default: False)

**Example:**
```python
result = await plugin.get_scene_info(
    include_hierarchy=True,
    include_components=False
)
```

### create_script

Generate a C# script file.

**Parameters:**
- `script_name` (str): Script class name
- `script_type` (str, optional): Type - "monobehaviour", "scriptableobject", "plain", "interface"
- `path` (str, optional): Save path (default: "Assets/Scripts")
- `namespace` (str, optional): Namespace for the script

**Example:**
```python
result = await plugin.create_script(
    script_name="PlayerController",
    script_type="monobehaviour",
    namespace="Game.Player"
)
```

## Advanced Usage

### With AI Orchestration

```python
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from unity_mcp_plugin import UnityMCPPlugin

async def ai_example():
    kernel = sk.Kernel()
    
    # Add AI service
    kernel.add_chat_service(
        "chat",
        OpenAIChatCompletion("gpt-4", api_key="your-key")
    )
    
    # Add Unity plugin
    unity_plugin = UnityMCPPlugin()
    await unity_plugin.initialize()
    kernel.add_plugin(unity_plugin, plugin_name="unity")
    
    # Create semantic function that uses Unity
    semantic_func = kernel.create_semantic_function(
        prompt_template="""
Create a Unity scene based on this request: {{$input}}

Use the unity.create_scene and unity.create_gameobject functions
to build the scene as described.
        """,
        function_name="scene_designer"
    )
    
    # Use AI to create scenes
    result = await kernel.invoke(
        semantic_func,
        input="Create a simple platformer level"
    )
    
    await unity_plugin.cleanup()
```

### Creating Complex Scenes

```python
async def create_game_level():
    plugin = UnityMCPPlugin()
    await plugin.initialize()
    
    # Create scene
    await plugin.create_scene(scene_name="GameLevel")
    
    # Create ground
    await plugin.create_gameobject(
        name="Ground",
        object_type="plane",
        position_y=0
    )
    
    # Create player
    await plugin.create_gameobject(
        name="Player",
        object_type="cube",
        position_y=1
    )
    
    # Create enemies
    for i in range(5):
        await plugin.create_gameobject(
            name=f"Enemy{i}",
            object_type="sphere",
            position_x=i * 3,
            position_y=1
        )
    
    # Generate scripts
    await plugin.create_script(
        script_name="PlayerController",
        script_type="monobehaviour"
    )
    
    await plugin.create_script(
        script_name="EnemyAI",
        script_type="monobehaviour"
    )
    
    # Get final scene stats
    info = await plugin.get_scene_info()
    print(f"Created scene with {info['object_count']} objects")
    
    await plugin.cleanup()
```

## Configuration

### Using Skill Manifest

You can provide a `unity-mcp-server.skill.json` file for tool definitions:

```python
plugin = UnityMCPPlugin(
    skill_manifest_path="path/to/unity-mcp-server.skill.json",
    host="localhost",
    port=8765
)
```

If not provided, the plugin will discover tools from the server.

### Custom Connection Settings

```python
plugin = UnityMCPPlugin(
    host="localhost",      # Server host
    port=8765,             # Server port
)

# Customize client timeout
plugin.client.timeout = 60  # seconds
```

## Error Handling

The plugin provides comprehensive error handling:

```python
try:
    result = await plugin.create_scene(scene_name="TestScene")
    
    # Check result
    import json
    result_dict = json.loads(result)
    
    if result_dict.get("success"):
        print(f"Scene created: {result_dict['path']}")
    else:
        print(f"Error: {result_dict['error']}")
        
except RuntimeError as e:
    print(f"Connection error: {e}")
except ValueError as e:
    print(f"Validation error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Examples

See `example_usage.py` for comprehensive examples:

```bash
python example_usage.py
```

Examples include:
1. Basic operations (ping, create scene)
2. Advanced scene creation (complete game level)
3. AI-orchestrated workflows (requires OpenAI key)
4. Direct tool usage (without SK)

## Troubleshooting

### Connection Refused

**Problem**: Cannot connect to Unity MCP Server

**Solution**:
- Ensure Unity Editor is running
- Check Unity Console for "Unity MCP Server v1.0.0 started on port 8765"
- Verify port 8765 is not in use by another application

### Tool Not Found

**Problem**: SK cannot find Unity functions

**Solution**:
- Ensure plugin is initialized: `await plugin.initialize()`
- Verify plugin is imported: `kernel.add_plugin(plugin, plugin_name="unity")`
- Check tool names match exactly (case-sensitive)

### Parameter Validation Errors

**Problem**: Invalid parameter errors

**Solution**:
- Check parameter types match schema (string, number, boolean)
- Ensure required parameters are provided
- Verify parameter names match exactly

### Timeout Errors

**Problem**: Operations time out

**Solution**:
- Increase timeout: `plugin.client.timeout = 60`
- Check Unity Editor is responsive
- Verify operation isn't blocked in Unity

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black unity_mcp_plugin.py
```

### Type Checking

```bash
mypy unity_mcp_plugin.py
```

## Project Structure

```text
unity-mcp-plugin/
├── Core Implementation
│   ├── __init__.py                 # Package exports
│   └── unity_mcp_plugin.py         # Main plugin (600+ lines)
│
├── Documentation
│   ├── README.md                   # Complete guide (700+ lines)
│   ├── DEPLOYMENT.md               # Deployment guide (500+ lines)
│   └── PROJECT_SUMMARY.md          # This file
│
├── Examples & Tests
│   ├── example_usage.py            # Examples (400+ lines)
│   ├── integration_test.py         # Integration tests (200+ lines)
│   └── tests/                      # Test suite
│       ├── test_client.py
│       ├── test_plugin.py
│       └── test_integration.py
│
└── Package Files
    ├── requirements.txt            # Dependencies
    └── setup.py                    # Package setup
```

## API Reference

### UnityMCPPlugin

Main plugin class for Semantic Kernel integration.

**Constructor:**
```python
UnityMCPPlugin(
    skill_manifest_path: Optional[str] = None,
    host: str = "localhost",
    port: int = 8765
)
```

**Methods:**
- `async initialize() -> bool`: Initialize connection and load tools
- `async cleanup()`: Close connections and clean up resources

### UnityMCPClient

Low-level client for MCP communication.

**Constructor:**
```python
UnityMCPClient(
    host: str = "localhost",
    port: int = 8765,
    timeout: int = 30
)
```

**Methods:**
- `async connect() -> bool`: Connect to server
- `async send_request(method, params) -> dict`: Send JSON-RPC request
- `async call_tool(tool_name, arguments) -> dict`: Call MCP tool
- `async close()`: Close connection

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- GitHub Issues: [https://github.com/yourusername/unity-mcp-plugin/issues](https://github.com/yourusername/unity-mcp-plugin/issues)
- Documentation: [https://github.com/yourusername/unity-mcp-plugin/wiki](https://github.com/yourusername/unity-mcp-plugin/wiki)
- Unity MCP Server: [https://github.com/Ozymandros/Unity-MCP-Server](https://github.com/Ozymandros/Unity-MCP-Server)

## Changelog

### Version 1.0.0 (2025-02-14)

- Initial release
- Full Semantic Kernel integration
- 5 core Unity functions
- Async/await support
- Comprehensive examples
- Production-ready error handling

## Acknowledgments

- Semantic Kernel team at Microsoft
- Unity MCP Server contributors
- Model Context Protocol specification by Anthropic
