"""
Unity MCP Server Plugin for Semantic Kernel

This plugin provides a bridge between Semantic Kernel and the Unity MCP Server,
exposing Unity Editor operations as SK kernel functions.
"""

import asyncio
import json
import socket
from typing import Any, Dict, List, Optional, Callable, Annotated
from dataclasses import dataclass
from enum import Enum

from semantic_kernel.functions import kernel_function


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPToolSchema:
    """Represents an MCP tool schema."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    required_params: List[str]


class UnityMCPClient:
    """
    Client for communicating with Unity MCP Server over TCP.
    Handles JSON-RPC 2.0 message protocol.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8765, timeout: int = 30):
        """
        Initialize the MCP client.
        
        Args:
            host: Server hostname
            port: Server port
            timeout: Socket timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.request_id = 0
        self.state = ConnectionState.DISCONNECTED
        self._buffer = ""
        
    async def connect(self) -> bool:
        """
        Connect to the Unity MCP Server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.state = ConnectionState.CONNECTING
            
            # Run socket connection in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.socket = await loop.run_in_executor(
                None, 
                self._create_socket
            )
            
            self.state = ConnectionState.CONNECTED
            print(f"✓ Connected to Unity MCP Server at {self.host}:{self.port}")
            
            # Initialize MCP connection
            await self.initialize()
            
            return True
        except Exception as e:
            self.state = ConnectionState.ERROR
            print(f"✗ Connection failed: {e}")
            return False
    
    def _create_socket(self) -> socket.socket:
        """Create and connect socket (blocking operation)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        return sock
    
    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to the server.
        
        Args:
            method: RPC method name
            params: Method parameters
            
        Returns:
            Server response as dictionary
            
        Raises:
            RuntimeError: If not connected or request fails
        """
        if self.state != ConnectionState.CONNECTED:
            raise RuntimeError("Not connected to server")
        
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": str(self.request_id),
            "method": method,
            "params": params or {}
        }
        
        try:
            # Send request
            message = json.dumps(request) + "\n"
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.socket.sendall,
                message.encode('utf-8')
            )
            
            # Receive response
            response = await self._receive_response()
            
            # Check for RPC errors
            if "error" in response:
                error = response["error"]
                raise RuntimeError(
                    f"MCP Error {error['code']}: {error['message']}"
                    + (f" - {error.get('data', '')}" if 'data' in error else "")
                )
            
            return response
            
        except Exception as e:
            self.state = ConnectionState.ERROR
            raise RuntimeError(f"Request failed: {e}") from e
    
    async def _receive_response(self) -> Dict[str, Any]:
        """Receive and parse a complete JSON-RPC response."""
        loop = asyncio.get_event_loop()
        
        while "\n" not in self._buffer:
            chunk = await loop.run_in_executor(
                None,
                self.socket.recv,
                8192
            )
            
            if not chunk:
                raise RuntimeError("Connection closed by server")
            
            self._buffer += chunk.decode('utf-8')
        
        # Extract complete message
        newline_index = self._buffer.index('\n')
        message = self._buffer[:newline_index]
        self._buffer = self._buffer[newline_index + 1:]
        
        return json.loads(message)
    
    async def initialize(self) -> Dict[str, Any]:
        """
        Send MCP initialize handshake.
        
        Returns:
            Server capabilities and info
        """
        return await self.send_request("initialize", {
            "protocolVersion": "2025-11-25",
            "clientInfo": {
                "name": "Semantic Kernel Unity MCP Client",
                "version": "1.0.0"
            }
        })
    
    async def list_tools(self) -> Dict[str, Any]:
        """
        List all available tools from the server.
        
        Returns:
            List of tools with descriptions and schemas
        """
        return await self.send_request("tools/list", {})
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool using standard MCP format.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        response = await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        # Extract result from MCP content format
        if "result" in response and "content" in response["result"]:
            content = response["result"]["content"]
            if content and len(content) > 0 and content[0]["type"] == "text":
                return json.loads(content[0]["text"])
        
        return response.get("result", {})
    
    async def close(self):
        """Close the connection."""
        if self.socket:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.socket.close)
            self.socket = None
            self.state = ConnectionState.DISCONNECTED
            print("✓ Connection closed")


class UnityMCPPlugin:
    """
    Semantic Kernel plugin for Unity MCP Server.
    
    Dynamically creates SK functions from MCP tool definitions,
    providing a bridge between SK and Unity Editor operations.
    """
    
    def __init__(
        self, 
        skill_manifest_path: Optional[str] = None,
        host: str = "localhost",
        port: int = 8765
    ):
        """
        Initialize the Unity MCP plugin.
        
        Args:
            skill_manifest_path: Path to unity-mcp-server.skill.json
            host: MCP server host
            port: MCP server port
        """
        self.client = UnityMCPClient(host, port)
        self.tools: Dict[str, MCPToolSchema] = {}
        self.skill_manifest_path = skill_manifest_path
        self._initialized = False
        
    async def initialize(self) -> bool:
        """
        Initialize connection and load tool schemas.
        
        Returns:
            True if successful
        """
        if self._initialized:
            return True
        
        # Connect to server
        if not await self.client.connect():
            return False
        
        # Load skill manifest if provided
        if self.skill_manifest_path:
            await self._load_skill_manifest()
        else:
            # Query server for available tools
            await self._discover_tools()
        
        self._initialized = True
        return True
    
    async def _load_skill_manifest(self):
        """Load and parse skill manifest file."""
        try:
            with open(self.skill_manifest_path, 'r') as f:
                manifest = json.load(f)
            
            for tool in manifest.get("tools", []):
                schema = MCPToolSchema(
                    name=tool["name"],
                    description=tool["description"],
                    input_schema=tool["input_schema"],
                    required_params=tool["input_schema"].get("required", [])
                )
                self.tools[schema.name] = schema
                
            print(f"✓ Loaded {len(self.tools)} tools from skill manifest")
        except Exception as e:
            print(f"⚠ Failed to load skill manifest: {e}")
            print("  Falling back to server discovery...")
            await self._discover_tools()
    
    async def _discover_tools(self):
        """Discover tools from the MCP server."""
        try:
            response = await self.client.list_tools()
            server_tools = response.get("result", {}).get("tools", [])
            
            for tool in server_tools:
                schema = MCPToolSchema(
                    name=tool["name"],
                    description=tool["description"],
                    input_schema=tool.get("inputSchema", {}),
                    required_params=tool.get("inputSchema", {}).get("required", [])
                )
                self.tools[schema.name] = schema
            
            print(f"✓ Discovered {len(self.tools)} tools from server")
        except Exception as e:
            print(f"✗ Failed to discover tools: {e}")
    
    def _validate_params(self, tool_name: str, params: Dict[str, Any]) -> None:
        """
        Validate parameters against tool schema.
        
        Args:
            tool_name: Name of the tool
            params: Parameters to validate
            
        Raises:
            ValueError: If validation fails
        """
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        schema = self.tools[tool_name]
        
        # Check required parameters
        for required in schema.required_params:
            if required not in params:
                raise ValueError(f"Missing required parameter: {required}")
        
        # Validate types (basic validation)
        properties = schema.input_schema.get("properties", {})
        for param_name, param_value in params.items():
            if param_name in properties:
                expected_type = properties[param_name].get("type")
                actual_type = type(param_value).__name__
                
                # Basic type mapping
                type_map = {
                    "string": "str",
                    "number": ("int", "float"),
                    "boolean": "bool",
                    "array": "list",
                    "object": "dict"
                }
                
                if expected_type in type_map:
                    valid_types = type_map[expected_type]
                    if isinstance(valid_types, tuple):
                        if actual_type not in valid_types:
                            raise ValueError(
                                f"Parameter '{param_name}' expected {expected_type}, "
                                f"got {actual_type}"
                            )
                    elif actual_type != valid_types:
                        raise ValueError(
                            f"Parameter '{param_name}' expected {expected_type}, "
                            f"got {actual_type}"
                        )
    
    async def _execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an MCP tool with the given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool parameters
            
        Returns:
            Tool execution result
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()
        
        # Filter out None values and context
        params = {k: v for k, v in kwargs.items() if v is not None and k != 'context'}
        
        # Validate parameters
        self._validate_params(tool_name, params)
        
        # Execute tool
        try:
            result = await self.client.call_tool(tool_name, params)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== SK Functions ====================
    # These are the actual Semantic Kernel functions that will be exposed
    
    @kernel_function(
        description="Test connectivity with the Unity MCP Server",
        name="ping"
    )
    async def ping(
        self, 
        message: Annotated[str, "Optional message to echo back"] = ""
    ) -> str:
        """Test connectivity with Unity MCP Server."""
        result = await self._execute_tool("ping", message=message)
        
        if result.get("success", True):
            return json.dumps({
                "status": "connected",
                "message": result.get("message", "pong"),
                "echo": result.get("echo"),
                "timestamp": result.get("timestamp")
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)
    
    @kernel_function(
        description="Create a new Unity scene with the specified name",
        name="create_scene"
    )
    async def create_scene(
        self, 
        scene_name: Annotated[str, "Name of the scene to create"] = "NewScene",
        path: Annotated[str, "Optional path to save the scene (default: Assets/Scenes)"] = "Assets/Scenes",
        setup: Annotated[str, "Scene setup type: 'default' or 'empty' (default: default)"] = "default"
    ) -> str:
        """Create a new Unity scene."""
        # Map parameter names to MCP schema
        result = await self._execute_tool(
            "create_scene",
            name=scene_name,
            path=path,
            setup=setup
        )
        
        if result.get("success", False):
            return json.dumps({
                "success": True,
                "scene_name": result.get("name"),
                "path": result.get("path"),
                "message": result.get("message")
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)
    
    @kernel_function(
        description="Create a GameObject in the active Unity scene",
        name="create_gameobject"
    )
    async def create_gameobject(
        self,
        name: Annotated[str, "Name of the GameObject"] = "GameObject",
        object_type: Annotated[str, "Type: empty, cube, sphere, capsule, cylinder, plane, quad"] = "empty",
        position_x: Annotated[float, "X position (default: 0)"] = 0.0,
        position_y: Annotated[float, "Y position (default: 0)"] = 0.0,
        position_z: Annotated[float, "Z position (default: 0)"] = 0.0,
        parent: Annotated[Optional[str], "Optional parent GameObject name"] = None
    ) -> str:
        """Create a GameObject in Unity."""
        # Build position object
        params = {
            "name": name,
            "type": object_type,
            "position": {
                "x": float(position_x),
                "y": float(position_y),
                "z": float(position_z)
            }
        }
        
        if parent:
            params["parent"] = parent
        
        result = await self._execute_tool("create_gameobject", **params)
        
        if result.get("success", False):
            return json.dumps({
                "success": True,
                "name": result.get("name"),
                "type": result.get("type"),
                "position": result.get("position"),
                "instance_id": result.get("instanceId"),
                "message": result.get("message")
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)
    
    @kernel_function(
        description="Get detailed information about the currently active Unity scene",
        name="get_scene_info"
    )
    async def get_scene_info(
        self,
        include_hierarchy: Annotated[bool, "Include full GameObject hierarchy (default: true)"] = True,
        include_components: Annotated[bool, "Include component information (default: false)"] = False
    ) -> str:
        """Get information about the active Unity scene."""
        result = await self._execute_tool(
            "get_scene_info",
            includeHierarchy=include_hierarchy,
            includeComponents=include_components
        )
        
        if result.get("success", True):
            return json.dumps({
                "scene_name": result.get("name"),
                "path": result.get("path"),
                "is_loaded": result.get("isLoaded"),
                "object_count": result.get("totalObjectCount"),
                "root_count": result.get("rootCount"),
                "root_objects": result.get("rootObjects", [])
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)
    
    @kernel_function(
        description="Create a C# script file in the Unity project",
        name="create_script"
    )
    async def create_script(
        self,
        script_name: Annotated[str, "Name of the script class"] = "NewScript",
        script_type: Annotated[str, "Type: monobehaviour, scriptableobject, plain, interface"] = "monobehaviour",
        path: Annotated[str, "Path to save the script (default: Assets/Scripts)"] = "Assets/Scripts",
        namespace: Annotated[Optional[str], "Optional namespace for the script"] = None
    ) -> str:
        """Create a C# script in Unity."""
        params = {
            "name": script_name,
            "type": script_type,
            "path": path
        }
        
        if namespace:
            params["namespace"] = namespace
        
        result = await self._execute_tool("create_script", **params)
        
        if result.get("success", False):
            return json.dumps({
                "success": True,
                "script_name": result.get("name"),
                "path": result.get("path"),
                "type": result.get("type"),
                "message": result.get("message")
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)
    
    async def cleanup(self):
        """Clean up resources and close connections."""
        await self.client.close()
