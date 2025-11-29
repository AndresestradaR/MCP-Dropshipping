"""
Agente de IA con LangGraph.
"""

import logging
from typing import Annotated, TypedDict, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from config import get_settings
from mcp_client import mcp_client

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str


class AgentNodes:
    def __init__(self):
        self.settings = get_settings()
        self.model = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            anthropic_api_key=self.settings.anthropic_api_key,
            max_tokens=4096
        )
        self.tools = []
        self.tools_by_name = {}
        self._initialized = False
    
    async def initialize_tools(self):
        if self._initialized:
            return
        
        await mcp_client.initialize()
        mcp_tools = await mcp_client.get_all_tools()
        
        for tool_info in mcp_tools:
            tool_name = tool_info["name"]
            server = tool_info["server"]
            original_name = tool_info["original_name"]
            
            # Crear función para este tool
            async def call_mcp(arguments: dict = {}, _server=server, _name=original_name):
                return await mcp_client.call_tool(_server, _name, arguments)
            
            tool = StructuredTool.from_function(
                coroutine=call_mcp,
                name=tool_name,
                description=tool_info["description"],
                args_schema=None
            )
            self.tools.append(tool)
            self.tools_by_name[tool_name] = {"server": server, "original_name": original_name}
        
        if self.tools:
            self.model = self.model.bind_tools(self.tools)
        
        self._initialized = True
        logger.info(f"🔧 {len(self.tools)} herramientas MCP disponibles")
    
    async def agent_node(self, state: AgentState) -> dict:
        await self.initialize_tools()
        
        system = SystemMessage(content="""Eres un asistente de IA para una tienda Shopify.
Tienes acceso a herramientas para consultar ventas e inventario.
Responde siempre en español de forma amable y concisa.
IMPORTANTE: Cuando el usuario pregunte sobre ventas o inventario, USA las herramientas disponibles.""")
        
        messages = [system] + state["messages"]
        
        try:
            response = await self.model.ainvoke(messages)
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"Error en agent: {e}")
            return {"messages": [AIMessage(content="Lo siento, hubo un error. Intenta de nuevo.")]}
    
    async def tool_node(self, state: AgentState) -> dict:
        messages = state["messages"]
        last_message = messages[-1]
        tool_messages = []
        
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})
                tool_id = tool_call["id"]
                
                logger.info(f"🔧 Llamando: {tool_name} con args: {tool_args}")
                
                try:
                    if tool_name in self.tools_by_name:
                        info = self.tools_by_name[tool_name]
                        result = await mcp_client.call_tool(info["server"], info["original_name"], tool_args)
                    else:
                        result = f"Herramienta {tool_name} no encontrada"
                    
                    logger.info(f"✅ Resultado: {result[:100]}...")
                    tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))
                except Exception as e:
                    logger.error(f"Error tool {tool_name}: {e}")
                    tool_messages.append(ToolMessage(content=f"Error: {str(e)}", tool_call_id=tool_id))
        
        return {"messages": tool_messages}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


def create_agent_graph():
    nodes = AgentNodes()
    graph = StateGraph(AgentState)
    
    graph.add_node("agent", nodes.agent_node)
    graph.add_node("tools", nodes.tool_node)
    
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")
    
    return graph


class ConversationManager:
    def __init__(self):
        self.memory = MemorySaver()
        self.graph = create_agent_graph().compile(checkpointer=self.memory)
    
    async def process_message(self, user_id: str, message: str) -> str:
        config = {"configurable": {"thread_id": user_id}}
        
        input_state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id
        }
        
        try:
            result = await self.graph.ainvoke(input_state, config)
            messages = result.get("messages", [])
            
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                    return msg.content
            
            return "No pude generar una respuesta."
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            return "Ocurrió un error procesando tu mensaje. Por favor, intenta de nuevo."


conversation_manager = ConversationManager()