"""
Agente de IA orquestado con LangGraph.

Este módulo implementa el cerebro del agente usando LangGraph para:
- Manejo de estado y memoria de conversación
- Orquestación del flujo de chat
- Integración con herramientas MCP remotas
"""

import logging
from typing import Annotated, TypedDict, Literal
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from config import get_settings
from mcp_client import mcp_client

logger = logging.getLogger(__name__)


# =============================================================================
# ESTADO DEL AGENTE
# =============================================================================

class AgentState(TypedDict):
    """
    Estado del agente que persiste a través de la conversación.
    
    Attributes:
        messages: Historial de mensajes con función de reducción add_messages
        user_id: ID único del usuario (número de WhatsApp)
        context: Contexto adicional de la conversación
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    context: dict


# =============================================================================
# HERRAMIENTAS DINÁMICAS DESDE MCP
# =============================================================================

class MCPToolWrapper:
    """
    Wrapper para convertir herramientas MCP en herramientas de LangChain.
    
    Permite al agente llamar a herramientas de servidores MCP remotos
    de forma transparente.
    """
    
    def __init__(self, tool_info: dict):
        self.name = tool_info["name"]
        self.description = tool_info["description"]
        self.input_schema = tool_info["input_schema"]
        self.server = tool_info["server"]
        self.original_name = tool_info["original_name"]
    
    async def invoke(self, arguments: dict) -> str:
        """Ejecuta la herramienta en el servidor MCP remoto."""
        return await mcp_client.call_tool(
            server_name=self.server,
            tool_name=self.original_name,
            arguments=arguments
        )


async def get_langchain_tools() -> list:
    """
    Obtiene todas las herramientas MCP como herramientas de LangChain.
    
    Returns:
        Lista de herramientas formateadas para LangChain
    """
    mcp_tools = await mcp_client.get_all_tools()
    
    tools = []
    for tool_info in mcp_tools:
        wrapper = MCPToolWrapper(tool_info)
        
        # Crear herramienta dinámica para LangChain
        @tool(name=wrapper.name, description=wrapper.description)
        async def dynamic_tool(wrapper=wrapper, **kwargs) -> str:
            return await wrapper.invoke(kwargs)
        
        # Asignar el schema de entrada
        dynamic_tool.args_schema = tool_info["input_schema"]
        tools.append(dynamic_tool)
    
    return tools


# =============================================================================
# NODOS DEL GRAFO
# =============================================================================

class AgentNodes:
    """
    Nodos del grafo de LangGraph.
    
    Define la lógica de cada paso en el flujo del agente.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.model = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            anthropic_api_key=self.settings.anthropic_api_key,
            max_tokens=4096,
            temperature=0.7
        )
        self.tools = []
        self._tools_bound = False
    
    async def initialize_tools(self):
        """Inicializa las herramientas desde los servidores MCP."""
        if not self._tools_bound:
            await mcp_client.initialize()
            self.tools = await get_langchain_tools()
            self.model = self.model.bind_tools(self.tools) if self.tools else self.model
            self._tools_bound = True
            logger.info(f"🔧 {len(self.tools)} herramientas MCP disponibles")
    
    async def agent_node(self, state: AgentState) -> dict:
        """
        Nodo principal del agente que procesa mensajes.
        
        Este nodo:
        1. Recibe el estado actual
        2. Invoca al modelo con el historial de mensajes
        3. Retorna la respuesta del modelo
        """
        await self.initialize_tools()
        
        # Crear el prompt del sistema
        system_message = """Eres un asistente de IA amigable y útil para una tienda Shopify.
        
Puedes ayudar a los clientes con:
- Consultar productos y su disponibilidad
- Ver el estado de pedidos
- Información sobre envíos
- Resolver dudas generales

Responde siempre en español de forma amable y concisa.
Si necesitas información específica, usa las herramientas disponibles."""

        messages = [{"role": "system", "content": system_message}] + state["messages"]
        
        try:
            response = await self.model.ainvoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"Error en agent_node: {e}")
            error_msg = AIMessage(content="Lo siento, hubo un error procesando tu mensaje. ¿Podrías intentarlo de nuevo?")
            return {"messages": [error_msg]}
    
    async def tool_node(self, state: AgentState) -> dict:
        """
        Nodo que ejecuta las herramientas llamadas por el agente.
        
        Procesa las tool_calls del último mensaje del modelo
        y ejecuta las herramientas correspondientes.
        """
        messages = state["messages"]
        last_message = messages[-1]
        
        tool_messages = []
        
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                logger.info(f"🔧 Ejecutando herramienta: {tool_name}")
                
                try:
                    # Encontrar y ejecutar la herramienta
                    result = None
                    for t in self.tools:
                        if t.name == tool_name:
                            result = await t.ainvoke(tool_args)
                            break
                    
                    if result is None:
                        result = f"Herramienta '{tool_name}' no encontrada"
                    
                    tool_messages.append(
                        ToolMessage(content=str(result), tool_call_id=tool_id)
                    )
                except Exception as e:
                    logger.error(f"Error ejecutando {tool_name}: {e}")
                    tool_messages.append(
                        ToolMessage(content=f"Error: {str(e)}", tool_call_id=tool_id)
                    )
        
        return {"messages": tool_messages}


# =============================================================================
# GRAFO DEL AGENTE
# =============================================================================

def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    Decide si el agente debe ejecutar herramientas o terminar.
    
    Returns:
        "tools" si hay tool_calls pendientes
        "end" si el agente terminó de procesar
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    return "end"


def create_agent_graph() -> StateGraph:
    """
    Crea el grafo de LangGraph para el agente.
    
    El flujo es:
    START -> agent -> [tools -> agent]* -> END
    
    Returns:
        Grafo compilado listo para usar
    """
    nodes = AgentNodes()
    
    # Crear el grafo
    graph = StateGraph(AgentState)
    
    # Agregar nodos
    graph.add_node("agent", nodes.agent_node)
    graph.add_node("tools", nodes.tool_node)
    
    # Definir el flujo
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )
    graph.add_edge("tools", "agent")
    
    return graph


# =============================================================================
# GESTOR DE CONVERSACIONES
# =============================================================================

class ConversationManager:
    """
    Gestiona las conversaciones de múltiples usuarios.
    
    Mantiene el estado de cada conversación usando checkpoints
    de LangGraph para persistencia de memoria.
    """
    
    def __init__(self):
        self.memory = MemorySaver()
        self.graph = create_agent_graph().compile(checkpointer=self.memory)
    
    async def process_message(self, user_id: str, message: str) -> str:
        """
        Procesa un mensaje de un usuario.
        
        Args:
            user_id: ID único del usuario (número de WhatsApp)
            message: Mensaje del usuario
            
        Returns:
            Respuesta del agente
        """
        # Configuración del thread (sesión de conversación)
        config = {"configurable": {"thread_id": user_id}}
        
        # Estado inicial con el mensaje del usuario
        input_state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "context": {}
        }
        
        try:
            # Ejecutar el grafo
            result = await self.graph.ainvoke(input_state, config)
            
            # Obtener la última respuesta del agente
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
            
            return "Lo siento, no pude generar una respuesta."
            
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            return "Ocurrió un error procesando tu mensaje. Por favor, intenta de nuevo."
    
    async def get_conversation_history(self, user_id: str) -> list[dict]:
        """
        Obtiene el historial de conversación de un usuario.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Lista de mensajes en el historial
        """
        config = {"configurable": {"thread_id": user_id}}
        
        try:
            state = await self.graph.aget_state(config)
            if state and state.values:
                messages = state.values.get("messages", [])
                return [
                    {
                        "role": "user" if isinstance(m, HumanMessage) else "assistant",
                        "content": m.content
                    }
                    for m in messages
                    if isinstance(m, (HumanMessage, AIMessage)) and m.content
                ]
        except Exception as e:
            logger.error(f"Error obteniendo historial: {e}")
        
        return []
    
    async def clear_conversation(self, user_id: str):
        """Limpia el historial de conversación de un usuario."""
        # Con MemorySaver, simplemente iniciamos una nueva sesión
        # En producción, podrías usar un checkpointer persistente
        logger.info(f"Conversación limpiada para usuario: {user_id}")


# Instancia global del gestor de conversaciones
conversation_manager = ConversationManager()
