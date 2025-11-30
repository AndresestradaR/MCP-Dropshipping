"""
Cliente MCP - Conecta con multiples servidores MCP via HTTP
"""
import httpx
import logging
from config import MCP_SERVERS

logger = logging.getLogger(__name__)

class MCPClient:
    def __init__(self):
        self.tools_cache = {}
        self.servers = MCP_SERVERS
    
    async def initialize(self):
        """Conecta con todos los servidores MCP y obtiene sus herramientas."""
        for name, server in self.servers.items():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"{server['url']}/tools")
                    if response.status_code == 200:
                        data = response.json()
                        tools = data.get("tools", [])
                        self.tools_cache[name] = tools
                        logger.info(f"✅ {name}: {len(tools)} herramientas")
                    else:
                        logger.error(f"❌ {name}: HTTP {response.status_code}")
                        self.tools_cache[name] = []
            except Exception as e:
                logger.error(f"❌ {name}: {str(e)}")
                self.tools_cache[name] = []
    
    def get_all_tools(self):
        """Devuelve todas las herramientas de todos los servidores."""
        all_tools = []
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({
                    "server": server_name,
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {})
                })
        return all_tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict = None):
        """Ejecuta una herramienta en un servidor MCP especifico."""
        if server_name not in self.servers:
            return f"Servidor {server_name} no encontrado"
        
        server = self.servers[server_name]
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{server['url']}/call",
                    json={
                        "name": tool_name,
                        "arguments": arguments or {}
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("result", "OK")
                else:
                    return f"Error HTTP {response.status_code}"
        except Exception as e:
            return f"Error llamando {tool_name}: {str(e)}"

# Instancia global
mcp_client = MCPClient()