"""
Cliente MCP para conexión remota via SSE (Server-Sent Events).

Este módulo implementa un cliente MCP que se conecta a servidores remotos
usando SSE para recibir eventos del servidor.
"""

import json
import logging
from typing import Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RemoteMCPServer:
    """Configuración de un servidor MCP remoto."""
    name: str
    url: str
    description: str


class MCPToolInfo:
    """Información de una herramienta MCP."""
    def __init__(self, name: str, description: str, input_schema: dict, server: str):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.server = server
        self.original_name = name.replace(f"{server}_", "", 1) if name.startswith(f"{server}_") else name


class MCPClientManager:
    """
    Gestiona conexiones a múltiples servidores MCP remotos.
    
    Usa SSE (Server-Sent Events) para comunicación con servidores remotos.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.servers: dict[str, RemoteMCPServer] = {}
        self.tools_cache: dict[str, list[MCPToolInfo]] = {}
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
        """Inicializa las conexiones y obtiene las herramientas de los servidores MCP."""
        if self._initialized:
            return
        
        for name, server in self.servers.items():
            try:
                await self._fetch_tools_from_server(name, server)
                logger.info(f"✅ Herramientas obtenidas de: {name} ({server.url})")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo conectar a {name}: {e}")
                # Continuar sin este servidor - el agente funcionará sin sus herramientas
        
        self._initialized = True
    
    async def _fetch_tools_from_server(self, name: str, server: RemoteMCPServer):
        """
        Conecta temporalmente a un servidor MCP para obtener sus herramientas.
        """
        try:
            async with sse_client(server.url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    # Obtener las herramientas disponibles
                    tools_response = await session.list_tools()
                    
                    self.tools_cache[name] = [
                        MCPToolInfo(
                            name=f"{name}_{tool.name}",
                            description=tool.description or f"Herramienta {tool.name}",
                            input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                            server=name
                        )
                        for tool in tools_response.tools
                    ]
                    
                    logger.info(f"Servidor {name}: {len(tools_response.tools)} herramientas disponibles")
        except Exception as e:
            logger.error(f"Error conectando a {name} ({server.url}): {e}")
            self.tools_cache[name] = []
            raise
    
    async def get_all_tools(self) -> list[dict[str, Any]]:
        """
        Obtiene todas las herramientas de todos los servidores MCP.
        
        Retorna las herramientas en formato compatible con LangChain.
        """
        all_tools = []
        
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "server": tool.server,
                    "original_name": tool.original_name
                })
        
        return all_tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Ejecuta una herramienta en un servidor MCP remoto.
        
        Abre una conexión, ejecuta la herramienta, y cierra la conexión.
        
        Args:
            server_name: Nombre del servidor (ej: "shopify")
            tool_name: Nombre original de la herramienta (sin prefijo)
            arguments: Argumentos para la herramienta
            
        Returns:
            Resultado de la ejecución de la herramienta
        """
        if server_name not in self.servers:
            return f"Error: Servidor MCP '{server_name}' no está configurado"
        
        server = self.servers[server_name]
        
        try:
            async with sse_client(server.url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    result = await session.call_tool(tool_name, arguments)
                    
                    # Procesar el resultado
                    if result.content:
                        text_contents = [
                            content.text 
                            for content in result.content 
                            if hasattr(content, 'text')
                        ]
                        return "\n".join(text_contents) if text_contents else str(result.content)
                    
                    return "Herramienta ejecutada exitosamente"
                    
        except Exception as e:
            logger.error(f"Error ejecutando {tool_name} en {server_name}: {e}")
            return f"Error ejecutando herramienta: {str(e)}"
    
    async def close(self):
        """Limpia recursos (las conexiones SSE se cierran automáticamente)."""
        self.tools_cache.clear()
        self._initialized = False
        logger.info("Cliente MCP cerrado")


# Instancia global del cliente MCP
mcp_client = MCPClientManager()
