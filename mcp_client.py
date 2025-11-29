"""
Cliente MCP para conexión remota via SSE.
"""

import json
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
    description: str


class MCPClientManager:
    def __init__(self):
        self.settings = get_settings()
        self.servers: dict[str, RemoteMCPServer] = {}
        self.tools_cache: dict[str, list[dict]] = {}
        self._initialized = False
        self._register_servers()
    
    def _register_servers(self):
        self.servers["shopify"] = RemoteMCPServer(
            name="shopify",
            url=self.settings.shopify_mcp_url,
            description="Servidor MCP para Shopify"
        )
    
    async def initialize(self):
        if self._initialized:
            return
        
        for name, server in self.servers.items():
            try:
                await self._fetch_tools(name, server)
                logger.info(f"✅ Conectado a {name}: {len(self.tools_cache.get(name, []))} herramientas")
            except Exception as e:
                logger.error(f"❌ Error conectando a {name}: {e}")
                self.tools_cache[name] = []
        
        self._initialized = True
    
    async def _fetch_tools(self, name: str, server: RemoteMCPServer):
        """Obtiene las herramientas del servidor MCP."""
        base_url = server.url.replace("/sse", "")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Conectar al SSE y obtener el endpoint
            async with client.stream("GET", server.url) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        endpoint = line[6:].strip()
                        messages_url = f"{base_url}{endpoint}"
                        
                        # Enviar initialize
                        init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "web-agent", "version": "1.0.0"}}}
                        await client.post(messages_url, json=init_msg)
                        
                        # Enviar notifications/initialized
                        notif_msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                        await client.post(messages_url, json=notif_msg)
                        
                        # Pedir tools/list
                        tools_msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
                        await client.post(messages_url, json=tools_msg)
                        
                        # La respuesta viene por el stream, la leemos
                        break
                
                # Leer respuestas del stream
                tools = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "result" in data and "tools" in data["result"]:
                            tools = data["result"]["tools"]
                            break
                
                self.tools_cache[name] = tools
    
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
        base_url = server.url.replace("/sse", "")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("GET", server.url) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            endpoint = line[6:].strip()
                            messages_url = f"{base_url}{endpoint}"
                            
                            # Initialize
                            init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "web-agent", "version": "1.0.0"}}}
                            await client.post(messages_url, json=init_msg)
                            
                            # Call tool
                            call_msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}}
                            await client.post(messages_url, json=call_msg)
                            break
                    
                    # Leer respuesta
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if "result" in data and "content" in data["result"]:
                                contents = data["result"]["content"]
                                texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
                                return "\n".join(texts) if texts else "OK"
                    
                    return "Sin respuesta"
        except Exception as e:
            logger.error(f"Error llamando {tool_name}: {e}")
            return f"Error: {str(e)}"
    
    async def close(self):
        self.tools_cache.clear()
        self._initialized = False


mcp_client = MCPClientManager()