"""
Cliente MCP para conexión remota via SSE (Server-Sent Events).

Este módulo implementa un cliente MCP que se conecta a servidores remotos
usando el protocolo SSE estándar.
"""

import json
import logging
from typing import Any
from dataclasses import dataclass

import httpx
from mcp import ClientSession
# CAMBIO 1: Importar sse_client en lugar de streamablehttp_client
from mcp.client.sse import sse_client
from mcp.types import Tool as MCPTool

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RemoteMCPServer:
    """Configuración de un servidor MCP remoto."""
    name: str
    url: str
    description: str


class MCPClientManager:
    """
    Gestiona conexiones a múltiples servidores MCP remotos.
    
    Usa SSE (Server-Sent Events) para comunicación bidireccional.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.servers: dict[str, RemoteMCPServer] = {}
        self.sessions: dict[str, ClientSession] = {}
        self.tools_cache: dict[str, list[MCPTool]] = {}
        self._initialized = False
        
        # Registrar servidores MCP configurados
        self._register_servers()
    
    def _register_servers(self):
        """Registra los servidores MCP remotos configurados."""
        # Servidor Shopify MCP
        self.servers["shopify"] = RemoteMCPServer(
            name="shopify",
            url=self.settings.shopify_mcp_url,
            description="Servidor MCP para operaciones de Shopify (productos, órdenes, clientes)"
        )
    
    async def initialize(self):
        """Inicializa las conexiones a todos los servidores MCP."""
        if self._initialized:
            return
        
        for name, server in self.servers.items():
            try:
                await self._connect_to_server(name, server)
                logger.info(f"✅ Conectado a servidor MCP: {name} ({server.url})")
            except Exception as e:
                logger.error(f"❌ Error conectando a {name}: {e}")
        
        self._initialized = True
    
    async def _connect_to_server(self, name: str, server: RemoteMCPServer):
        """
        Conecta a un servidor MCP remoto usando SSE.
        """
        # CAMBIO 2: Usar sse_client y desempaquetar solo 2 variables (read, write)
        async with sse_client(server.url) as (read_stream, write_stream):
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            
            # Obtener y cachear las herramientas disponibles
            tools_response = await session.list_tools()
            self.tools_cache[name] = tools_response.tools
            self.sessions[name] = session
            
            logger.info(f"Servidor {name} tiene {len(tools_response.tools)} herramientas disponibles")
    
    async def get_all_tools(self) -> list[dict[str, Any]]:
        """
        Obtiene todas las herramientas de todos los servidores MCP conectados.
        """
        all_tools = []
        
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({
                    "name": f"{server_name}_{tool.name}",
                    "description": tool.description or f"Herramienta {tool.name} del servidor {server_name}",
                    "input_schema": tool.inputSchema,
                    "server": server_name,
                    "original_name": tool.name
                })
        
        return all_tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Ejecuta una herramienta en un servidor MCP remoto.
        """
        if server_name not in self.sessions:
            raise ValueError(f"Servidor MCP '{server_name}' no está conectado")
        
        session = self.sessions[server_name]
        
        try:
            result = await session.call_tool(tool_name, arguments)
            
            if result.content:
                text_contents = [
                    content.text 
                    for content in result.content 
                    if hasattr(content, 'text')
                ]
                return "\n".join(text_contents) if text_contents else str(result.content)
            
            return "Herramienta ejecutada exitosamente (sin contenido de respuesta)"
            
        except Exception as e:
            logger.error(f"Error ejecutando {tool_name} en {server_name}: {e}")
            return f"Error: {str(e)}"
    
    async def close(self):
        """Cierra todas las conexiones a servidores MCP."""
        for name, session in self.sessions.items():
            try:
                # En implementaciones SSE actuales, cerrar la sesión es suficiente
                logger.info(f"Cerrando conexión: {name}")
            except Exception as e:
                logger.error(f"Error cerrando conexión {name}: {e}")
        
        self.sessions.clear()
        self._initialized = False

# Instancia global del cliente MCP
mcp_client = MCPClientManager()
