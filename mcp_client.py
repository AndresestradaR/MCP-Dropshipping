"""
Cliente MCP simplificado para SSE.
"""

import json
import logging
import asyncio
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
        self.servers["shopify"] = RemoteMCPServer(
            name="shopify",
            url=self.settings.shopify_mcp_url
        )
    
    async def initialize(self):
        if self._initialized:
            return
        
        for name, server in self.servers.items():
            try:
                tools = await self._fetch_tools(server.url)
                self.tools_cache[name] = tools
                logger.info(f"✅ {name}: {len(tools)} herramientas")
            except Exception as e:
                logger.error(f"❌ Error {name}: {e}")
                self.tools_cache[name] = []
        
        self._initialized = True
    
    async def _fetch_tools(self, sse_url: str) -> list[dict]:
        base_url = sse_url.replace("/sse", "")
        tools = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Conectar SSE y obtener endpoint
            response = await client.get(sse_url, headers={"Accept": "text/event-stream"})
            lines = response.text.strip().split("\n")
            
            endpoint = None
            for line in lines:
                if line.startswith("data: "):
                    endpoint = line[6:].strip()
                    break
            
            if not endpoint:
                raise Exception("No se recibió endpoint del SSE")
            
            messages_url = f"{base_url}{endpoint}"
            logger.info(f"Endpoint: {messages_url}")
            
            # 2. Initialize
            init_resp = await client.post(messages_url, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "agent", "version": "1.0"}}
            })
            
            # 3. Notification
            await client.post(messages_url, json={
                "jsonrpc": "2.0", "method": "notifications/initialized"
            })
            
            # 4. List tools
            await client.post(messages_url, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
            })
            
            # 5. Leer respuestas del SSE (nueva conexión)
            await asyncio.sleep(0.5)  # Dar tiempo al servidor
            
            sse_resp = await client.get(sse_url, headers={"Accept": "text/event-stream"})
            # El servidor ya no tiene esa sesión, pero las tools están en cache del servidor
            
            # Intentar obtener tools directamente via POST
            tools_resp = await client.post(messages_url, json={
                "jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}
            })
            
            # Reconectar SSE para leer respuesta
            async with client.stream("GET", sse_url, headers={"Accept": "text/event-stream"}) as stream:
                # Obtener nuevo endpoint
                new_endpoint = None
                async for line in stream.aiter_lines():
                    if line.startswith("data: "):
                        new_endpoint = line[6:].strip()
                        break
                
                if new_endpoint:
                    new_messages_url = f"{base_url}{new_endpoint}"
                    
                    # Enviar tools/list
                    await client.post(new_messages_url, json={
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "agent", "version": "1.0"}}
                    })
                    await client.post(new_messages_url, json={
                        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
                    })
                    
                    # Leer respuesta
                    async for line in stream.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if "result" in data and "tools" in data.get("result", {}):
                                    tools = data["result"]["tools"]
                                    break
                            except:
                                pass
        
        return tools
    
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
                async with client.stream("GET", server.url, headers={"Accept": "text/event-stream"}) as stream:
                    endpoint = None
                    async for line in stream.aiter_lines():
                        if line.startswith("data: "):
                            endpoint = line[6:].strip()
                            break
                    
                    if not endpoint:
                        return "Error: No endpoint"
                    
                    messages_url = f"{base_url}{endpoint}"
                    
                    # Initialize
                    await client.post(messages_url, json={
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "agent", "version": "1.0"}}
                    })
                    
                    # Call tool
                    await client.post(messages_url, json={
                        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments}
                    })
                    
                    # Leer respuesta
                    async for line in stream.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if "result" in data and "content" in data.get("result", {}):
                                    contents = data["result"]["content"]
                                    texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
                                    return "\n".join(texts) if texts else "OK"
                            except:
                                pass
                    
                    return "Sin respuesta"
        except Exception as e:
            logger.error(f"Error: {e}")
            return f"Error: {str(e)}"
    
    async def close(self):
        self.tools_cache.clear()
        self._initialized = False


mcp_client = MCPClientManager()