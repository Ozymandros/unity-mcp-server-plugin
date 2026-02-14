"""
Test suite for Unity MCP Plugin

Run with: pytest tests/
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from unity_mcp_plugin import UnityMCPPlugin, UnityMCPClient, MCPToolSchema


class TestUnityMCPClient:
    """Test suite for UnityMCPClient."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initializes with correct defaults."""
        client = UnityMCPClient()
        
        assert client.host == "localhost"
        assert client.port == 8765
        assert client.timeout == 30
        assert client.request_id == 0
        assert client.socket is None
    
    @pytest.mark.asyncio
    async def test_client_custom_settings(self):
        """Test client with custom settings."""
        client = UnityMCPClient(host="127.0.0.1", port=9999, timeout=60)
        
        assert client.host == "127.0.0.1"
        assert client.port == 9999
        assert client.timeout == 60
    
    @pytest.mark.asyncio
    async def test_request_id_increment(self):
        """Test request ID increments correctly."""
        client = UnityMCPClient()
        
        with patch.object(client, '_create_socket'):
            with patch.object(client, '_receive_response', new_callable=AsyncMock) as mock_receive:
                mock_receive.return_value = {"jsonrpc": "2.0", "id": "1", "result": {}}
                
                # Mock socket
                mock_socket = MagicMock()
                client.socket = mock_socket
                client.state = client.state.CONNECTED
                
                # Send multiple requests
                await client.send_request("test1")
                assert client.request_id == 1
                
                await client.send_request("test2")
                assert client.request_id == 2
                
                await client.send_request("test3")
                assert client.request_id == 3


class TestUnityMCPPlugin:
    """Test suite for UnityMCPPlugin."""
    
    @pytest.mark.asyncio
    async def test_plugin_initialization(self):
        """Test plugin initializes correctly."""
        plugin = UnityMCPPlugin()
        
        assert plugin.client.host == "localhost"
        assert plugin.client.port == 8765
        assert plugin.tools == {}
        assert plugin._initialized == False
    
    @pytest.mark.asyncio
    async def test_plugin_with_manifest(self):
        """Test plugin with skill manifest path."""
        plugin = UnityMCPPlugin(skill_manifest_path="test.json")
        
        assert plugin.skill_manifest_path == "test.json"
    
    @pytest.mark.asyncio
    async def test_load_skill_manifest(self):
        """Test loading skill manifest."""
        manifest_data = {
            "tools": [
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string"}
                        },
                        "required": ["param1"]
                    }
                }
            ]
        }
        
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(manifest_data)
            
            plugin = UnityMCPPlugin(skill_manifest_path="test.json")
            await plugin._load_skill_manifest()
            
            assert "test_tool" in plugin.tools
            assert plugin.tools["test_tool"].name == "test_tool"
            assert plugin.tools["test_tool"].description == "Test tool"
    
    @pytest.mark.asyncio
    async def test_validate_params_success(self):
        """Test parameter validation succeeds with valid params."""
        plugin = UnityMCPPlugin()
        
        # Add test tool
        plugin.tools["test"] = MCPToolSchema(
            name="test",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "number"}
                },
                "required": ["name"]
            },
            required_params=["name"]
        )
        
        # Should not raise
        plugin._validate_params("test", {"name": "test", "count": 5})
    
    @pytest.mark.asyncio
    async def test_validate_params_missing_required(self):
        """Test parameter validation fails with missing required param."""
        plugin = UnityMCPPlugin()
        
        plugin.tools["test"] = MCPToolSchema(
            name="test",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            },
            required_params=["name"]
        )
        
        with pytest.raises(ValueError, match="Missing required parameter"):
            plugin._validate_params("test", {})
    
    @pytest.mark.asyncio
    async def test_validate_params_wrong_type(self):
        """Test parameter validation fails with wrong type."""
        plugin = UnityMCPPlugin()
        
        plugin.tools["test"] = MCPToolSchema(
            name="test",
            description="Test",
            input_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "number"}
                },
                "required": []
            },
            required_params=[]
        )
        
        with pytest.raises(ValueError, match="expected number"):
            plugin._validate_params("test", {"count": "not a number"})
    
    @pytest.mark.asyncio
    async def test_ping_function(self):
        """Test ping function."""
        plugin = UnityMCPPlugin()
        plugin._initialized = True
        plugin.tools["ping"] = MCPToolSchema("ping", "ping", {}, [])
        
        with patch.object(plugin.client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "message": "pong",
                "timestamp": "2025-01-01T00:00:00Z"
            }
            
            result = await plugin.ping(message="test")
            result_dict = json.loads(result)
            
            assert result_dict["status"] == "connected"
            assert result_dict["message"] == "pong"
            assert mock_call.called
    
    @pytest.mark.asyncio
    async def test_create_scene_function(self):
        """Test create_scene function."""
        plugin = UnityMCPPlugin()
        plugin._initialized = True
        plugin.tools["create_scene"] = MCPToolSchema("create_scene", "create_scene", {}, [])
        
        with patch.object(plugin.client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "name": "TestScene",
                "path": "Assets/Scenes/TestScene.unity",
                "message": "Scene created"
            }
            
            result = await plugin.create_scene(scene_name="TestScene")
            result_dict = json.loads(result)
            
            assert result_dict["success"] == True
            assert result_dict["scene_name"] == "TestScene"
            assert "Assets/Scenes" in result_dict["path"]
    
    @pytest.mark.asyncio
    async def test_create_gameobject_function(self):
        """Test create_gameobject function."""
        plugin = UnityMCPPlugin()
        plugin._initialized = True
        plugin.tools["create_gameobject"] = MCPToolSchema("create_gameobject", "create_gameobject", {}, [])
        
        with patch.object(plugin.client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "name": "Cube",
                "type": "cube",
                "position": {"x": 0, "y": 1, "z": 0},
                "instanceId": 12345
            }
            
            result = await plugin.create_gameobject(
                name="Cube",
                object_type="cube",
                position_x=0.0,
                position_y=1.0,
                position_z=0.0
            )
            result_dict = json.loads(result)
            
            assert result_dict["success"] == True
            assert result_dict["name"] == "Cube"
            assert result_dict["type"] == "cube"
            assert result_dict["position"]["y"] == 1.0
    
    @pytest.mark.asyncio
    async def test_get_scene_info_function(self):
        """Test get_scene_info function."""
        plugin = UnityMCPPlugin()
        plugin._initialized = True
        plugin.tools["get_scene_info"] = MCPToolSchema("get_scene_info", "get_scene_info", {}, [])
        
        with patch.object(plugin.client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "name": "SampleScene",
                "path": "Assets/Scenes/SampleScene.unity",
                "isLoaded": True,
                "totalObjectCount": 5,
                "rootCount": 3
            }
            
            result = await plugin.get_scene_info()
            result_dict = json.loads(result)
            
            assert result_dict["scene_name"] == "SampleScene"
            assert result_dict["object_count"] == 5
            assert result_dict["is_loaded"] == True
    
    @pytest.mark.asyncio
    async def test_create_script_function(self):
        """Test create_script function."""
        plugin = UnityMCPPlugin()
        plugin._initialized = True
        plugin.tools["create_script"] = MCPToolSchema("create_script", "create_script", {}, [])
        
        with patch.object(plugin.client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "name": "PlayerController",
                "path": "Assets/Scripts/PlayerController.cs",
                "type": "monobehaviour"
            }
            
            result = await plugin.create_script(
                script_name="PlayerController",
                script_type="monobehaviour"
            )
            result_dict = json.loads(result)
            
            assert result_dict["success"] == True
            assert result_dict["script_name"] == "PlayerController"
            assert result_dict["type"] == "monobehaviour"


class TestIntegration:
    """Integration tests (require running Unity MCP Server)."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_workflow(self):
        """Test complete workflow (requires running server)."""
        plugin = UnityMCPPlugin()
        
        # This will fail if server is not running
        try:
            initialized = await plugin.initialize()
            if not initialized:
                pytest.skip("Unity MCP Server not running")
            
            # Ping
            result = await plugin.ping(message="Integration test")
            assert "pong" in result.lower()
            
            # Create scene
            result = await plugin.create_scene(scene_name="IntegrationTestScene")
            result_dict = json.loads(result)
            assert result_dict.get("success", False) or "path" in result_dict
            
            # Cleanup
            await plugin.cleanup()
            
        except RuntimeError:
            pytest.skip("Unity MCP Server not running")


# Pytest configuration
@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
