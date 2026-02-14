# Unity MCP Plugin - Deployment Guide

## Overview

This guide covers deploying and using the Unity MCP Plugin for Semantic Kernel in production environments.

## Directory Structure

```
unity-mcp-plugin/
├── __init__.py                 # Package initialization
├── unity_mcp_plugin.py         # Main plugin implementation
├── example_usage.py            # Comprehensive usage examples
├── integration_test.py         # Integration test script
├── test_plugin.py              # Unit test suite
├── requirements.txt            # Python dependencies
├── setup.py                    # Package installation
├── README.md                   # Complete documentation
└── DEPLOYMENT.md               # This file
```

## Installation Methods

### Method 1: Install from Source (Development)

```bash
# Clone or copy the plugin directory
cd unity-mcp-plugin

# Install in editable mode
pip install -e .

# Or install dependencies only
pip install -r requirements.txt
```

### Method 2: Install as Package (Production)

```bash
# After building the package
pip install unity-mcp-plugin-1.0.0.tar.gz

# Or from PyPI (when published)
pip install unity-mcp-plugin
```

### Method 3: Direct Integration

Simply copy `unity_mcp_plugin.py` and `__init__.py` into your project:

```python
from unity_mcp_plugin import UnityMCPPlugin
```

## Prerequisites

### Unity Side

1. **Unity Editor**: Version 2020.3 or later
2. **Unity MCP Server**: Must be installed and running
   - Files should be in `Assets/UnityMCP/Editor/`
   - Server auto-starts with Unity Editor
   - Confirm in Console: "Unity MCP Server v1.0.0 started on port 8765"

### Python Side

1. **Python**: Version 3.8 or later
2. **Semantic Kernel**: Version 0.9.0 or later

```bash
pip install semantic-kernel>=0.9.0
```

## Quick Start

### 1. Verify Unity MCP Server

Open Unity Editor and check Console for:
```
[McpServer] Unity MCP Server v1.0.0 started on port 8765
[McpToolRegistry] Registered 5 tools
```

### 2. Test Connection

```bash
python integration_test.py
```

This will verify:
- Connection to Unity MCP Server
- All tools are accessible
- Basic operations work

### 3. Run Examples

```bash
python example_usage.py
```

Choose from:
1. Basic Example (simple operations)
2. Advanced Example (complete game scene)
3. AI-Orchestrated Example (requires OpenAI key)
4. Direct Tool Usage

## Integration with Your Project

### Basic Integration

```python
import asyncio
import semantic_kernel as sk
from unity_mcp_plugin import UnityMCPPlugin

async def main():
    # Initialize kernel
    kernel = sk.Kernel()
    
    # Create and initialize Unity plugin
    unity = UnityMCPPlugin()
    await unity.initialize()
    
    # Import into kernel
    kernel.add_plugin(unity, plugin_name="unity")
    
    # Use Unity functions
    result = await kernel.invoke(
        plugin_name="unity", 
        function_name="create_scene",
        scene_name="MyScene"
    )
    
    # Cleanup
    await unity.cleanup()

asyncio.run(main())
```

### Advanced Integration with AI

```python
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

async def ai_integration():
    kernel = sk.Kernel()
    
    # Add AI service
    kernel.add_chat_service(
        "gpt4",
        OpenAIChatCompletion("gpt-4", api_key=os.getenv("OPENAI_API_KEY"))
    )
    
    # Add Unity plugin
    unity = UnityMCPPlugin()
    await unity.initialize()
    kernel.add_plugin(unity, plugin_name="unity")
    
    # Create AI-powered Unity workflows
    semantic_func = kernel.create_semantic_function(
        prompt_template="""
You are a Unity scene designer. Create a {{$scene_type}} scene.

Use unity.create_scene and unity.create_gameobject to build it.
Return a summary of what was created.
        """,
        function_name="design_scene"
    )
    
    result = await kernel.invoke(
        semantic_func,
        scene_type="platformer level"
    )
    
    await unity.cleanup()
```

## Configuration

### Environment Variables

```bash
# Unity MCP Server connection
export UNITY_MCP_HOST="localhost"
export UNITY_MCP_PORT="8765"

# Optional: OpenAI API key for AI examples
export OPENAI_API_KEY="your-key-here"
```

### Python Configuration

```python
# Custom configuration
plugin = UnityMCPPlugin(
    host=os.getenv("UNITY_MCP_HOST", "localhost"),
    port=int(os.getenv("UNITY_MCP_PORT", 8765)),
    skill_manifest_path="path/to/unity-mcp-server.skill.json"  # Optional
)

# Adjust timeout
plugin.client.timeout = 60  # seconds
```

## Production Deployment

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "your_app.py"]
```

**Note**: Unity Editor must be accessible from the container. Typically, you'll run Unity on the host and expose port 8765.

### Server Deployment

For production servers:

1. **Run Unity in Batch Mode** (headless):
   ```bash
   Unity.exe -batchmode -nographics -executeMethod YourSetup.StartMCPServer
   ```

2. **Configure Firewall**:
   ```bash
   # Allow port 8765 (local only)
   sudo ufw allow from 127.0.0.1 to any port 8765
   ```

3. **Process Management** (systemd, supervisord, etc.):
   ```ini
   [program:unity-mcp]
   command=/path/to/unity -batchmode -nographics -executeMethod Setup.StartMCP
   autostart=true
   autorestart=true
   ```

### Cloud Deployment

#### AWS

- Run Unity on EC2 instance
- Use security groups to restrict port 8765 to localhost
- Consider using AWS Batch for large-scale operations

#### Azure

- Deploy on Azure VM
- Use Network Security Groups for port control
- Consider Azure Container Instances for isolated workloads

#### GCP

- Use Compute Engine instances
- Configure firewall rules
- Consider Cloud Run for containerized deployments

## Error Handling

### Production Error Handling

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def safe_unity_operation():
    plugin = UnityMCPPlugin()
    
    try:
        # Initialize with timeout
        if not await asyncio.wait_for(
            plugin.initialize(),
            timeout=10.0
        ):
            logger.error("Failed to initialize Unity plugin")
            return None
        
        # Execute operation
        result = await plugin.create_scene(scene_name="ProdScene")
        
        # Parse and validate result
        import json
        result_dict = json.loads(result)
        
        if not result_dict.get("success"):
            logger.error(f"Scene creation failed: {result_dict.get('error')}")
            return None
        
        logger.info(f"Scene created: {result_dict['path']}")
        return result_dict
        
    except asyncio.TimeoutError:
        logger.error("Operation timed out")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return None
    finally:
        await plugin.cleanup()
```

### Retry Logic

```python
async def retry_unity_operation(operation, max_retries=3):
    """Retry Unity operation with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await operation()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            wait_time = 2 ** attempt
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
```

## Monitoring

### Health Checks

```python
async def health_check():
    """Check if Unity MCP Server is responsive."""
    try:
        plugin = UnityMCPPlugin()
        
        # Quick connection test
        if not await asyncio.wait_for(plugin.initialize(), timeout=5.0):
            return False
        
        # Quick ping
        result = await asyncio.wait_for(
            plugin.ping(message="health"),
            timeout=2.0
        )
        
        await plugin.cleanup()
        return "pong" in result.lower()
        
    except Exception:
        return False

# Use in production
is_healthy = await health_check()
```

### Metrics

```python
import time
from prometheus_client import Counter, Histogram

unity_operations = Counter('unity_operations_total', 'Total Unity operations')
unity_duration = Histogram('unity_operation_duration_seconds', 'Duration of Unity operations')

async def monitored_operation():
    unity_operations.inc()
    
    start_time = time.time()
    try:
        result = await plugin.create_scene(scene_name="Scene")
        return result
    finally:
        unity_duration.observe(time.time() - start_time)
```

## Performance Optimization

### Connection Pooling

```python
class UnityMCPPool:
    """Connection pool for Unity MCP clients."""
    
    def __init__(self, pool_size=5):
        self.pool = []
        self.pool_size = pool_size
        self._lock = asyncio.Lock()
    
    async def get_client(self):
        async with self._lock:
            if self.pool:
                return self.pool.pop()
            return UnityMCPPlugin()
    
    async def release_client(self, client):
        async with self._lock:
            if len(self.pool) < self.pool_size:
                self.pool.append(client)
            else:
                await client.cleanup()
```

### Batch Operations

```python
async def batch_create_objects(objects):
    """Create multiple GameObjects efficiently."""
    plugin = UnityMCPPlugin()
    await plugin.initialize()
    
    tasks = [
        plugin.create_gameobject(
            name=obj["name"],
            object_type=obj["type"],
            position_x=obj["x"],
            position_y=obj["y"],
            position_z=obj["z"]
        )
        for obj in objects
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await plugin.cleanup()
    
    return results
```

## Security Considerations

### Network Security

1. **Localhost Only**: Unity MCP Server binds to 127.0.0.1 by default
2. **No Encryption**: TCP connection is unencrypted (localhost only)
3. **No Authentication**: No auth mechanism (trusted local environment)

### Production Security

For production deployments exposing Unity MCP Server:

1. **Add Authentication**:
   ```python
   # Extend UnityMCPClient with auth
   class AuthenticatedMCPClient(UnityMCPClient):
       def __init__(self, api_key, *args, **kwargs):
           super().__init__(*args, **kwargs)
           self.api_key = api_key
       
       async def send_request(self, method, params=None):
           params = params or {}
           params["auth_token"] = self.api_key
           return await super().send_request(method, params)
   ```

2. **Use TLS/SSL**:
   - Run Unity MCP Server behind nginx with SSL
   - Configure client to use wss:// or https://

3. **Rate Limiting**:
   ```python
   from ratelimit import limits, sleep_and_retry
   
   @sleep_and_retry
   @limits(calls=10, period=60)
   async def rate_limited_operation():
       return await plugin.create_scene(scene_name="Scene")
   ```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Unity Editor not running
   - MCP Server not started
   - Port conflict

2. **Timeout Errors**
   - Increase timeout: `plugin.client.timeout = 120`
   - Check Unity Editor responsiveness
   - Verify operations aren't blocked

3. **Parameter Validation Errors**
   - Check parameter types
   - Verify required parameters
   - Review input schemas

### Debug Mode

```python
import logging

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Plugin will log all operations
plugin = UnityMCPPlugin()
await plugin.initialize()
```

## Support

- **GitHub Issues**: Report bugs and request features
- **Documentation**: See README.md for detailed API docs
- **Examples**: See example_usage.py for working code
- **Tests**: Run integration_test.py to verify setup

## License

MIT License - see LICENSE file for details
