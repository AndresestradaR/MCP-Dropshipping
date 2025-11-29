"""
Cliente MCP via HTTP directo.
"""

import logging
from typing import Any
from dataclasses import dataclass
import httpx

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RemoteMCPServer:
    name: str
    url: str


class MCPClientManager:
    def __init__(self):
        self.settings = get_settings()
        self.servers: dict[str, RemoteMCPServer] = {}
        self.tools_cache: dict[str, list[dict]] = {}
        self._initialized = False
        self._register_servers()
    
    def _register_servers(self):
        # Cambiar /sse por base URL
        base_url = self.settings.shopify_mcp_url.replace("/sse", "")
        self.servers["shopify"] = RemoteMCPServer(name="shopify", url=base_url)
    
    async def initialize(self):
        if self._initialized:
            return
        
        for name, server in self.servers.items():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"{server.url}/tools")
                    if response.status_code == 200:
                        data = response.json()
                        self.tools_cache[name] = data.get("tools", [])
                        logger.info(f"✅ {name}: {len(self.tools_cache[name])} herramientas")
                    else:
                        logger.error(f"❌ {name}: HTTP {response.status_code}")
                        self.tools_cache[name] = []
            except Exception as e:
                logger.error(f"❌ Error {name}: {e}")
                self.tools_cache[name] = []
        
        self._initialized = True
    
    async def get_all_tools(self) -> list[dict[str, Any]]:
        all_tools = []
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({
                    "name": f"{server_name}_{tool['name']}",
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {}),
                    "server": server_name,
                    "original_name": tool["name"]
                })
        return all_tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        if server_name not in self.servers:
            return f"Error: Servidor {server_name} no encontrado"
        
        server = self.servers[server_name]
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{server.url}/call",
                    json={"name": tool_name, "arguments": arguments}
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("result", "OK")
                return f"Error: HTTP {response.status_code}"
        except Exception as e:
            logger.error(f"Error: {e}")
            return f"Error: {str(e)}"
    
    async def close(self):
        self.tools_cache.clear()
        self._initialized = False


mcp_client = MCPClientManager()