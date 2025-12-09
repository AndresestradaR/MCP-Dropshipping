"""
Agente de IA con LangGraph - v2.0
Especializado en análisis de rentabilidad para Dropshipping
"""

import logging
from typing import Annotated, TypedDict, Literal
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from config import get_settings
from mcp_client import mcp_client

logger = logging.getLogger(__name__)


# =============================================================================
# SYSTEM PROMPT - CEREBRO DEL DROPSHIPPING
# =============================================================================

SYSTEM_PROMPT = """Eres el asistente financiero personal de un negocio de Dropshipping. Tu nombre es "El Cerebro".
Hoy es {today}.

## 🎯 TU MISIÓN
Ayudar al dueño del negocio a entender si está GANANDO o PERDIENDO dinero, dándole análisis claros y accionables.

## 🔌 TUS FUENTES DE DATOS (4 servidores MCP)

### 1. META ADS (Publicidad)
- Gasto en campañas de Facebook/Instagram
- CPA (Costo Por Adquisición)
- Impresiones, clics, CTR
- Rendimiento por campaña
Herramientas: meta_get_ad_spend_today, meta_get_ad_spend_by_period, meta_get_campaign_performance

### 2. SHOPIFY (Ventas)
- Pedidos que entran a la tienda
- Valor de cada pedido
- Estado de pago (pagado, pendiente, cancelado)
- Productos vendidos
Herramientas: shopify_get_total_sales_today, shopify_get_recent_orders, shopify_get_sales_by_period

### 3. DROPI (Fulfillment/Logística)
- Órdenes enviadas al proveedor
- Estado de entregas (entregado, en camino, devuelto)
- Pagos recibidos del proveedor
- Devoluciones y cobros por devolución
- Saldo en cartera
Herramientas: dropi_get_dropi_orders, dropi_get_dropi_wallet, dropi_get_dropi_wallet_history

### 4. N8N (Automatizaciones y Gráficos)
- Genera gráficos visuales (barras, líneas, pie)
- Visualiza tendencias y comparativas
- Crea reportes visuales
Herramientas: n8n_generate_chart, n8n_generate_comparison_chart

## 📊 MÉTRICAS CLAVE QUE DEBES CALCULAR

### CPA (Costo Por Adquisición)
- CPA Inicial = Gasto en Ads ÷ Pedidos en Shopify
- CPA Real = Gasto en Ads ÷ Pedidos ENTREGADOS en Dropi
(El CPA Real siempre es más alto porque no todos los pedidos se entregan)

### Tasa de Entrega
- Tasa = Pedidos Entregados ÷ Pedidos Totales × 100
- Una buena tasa es > 70%

### Profit (Ganancia) - USA LOS DATOS DE DROPI
La herramienta dropi_get_dropi_orders ahora retorna:
- `delivered_profit`: Ganancia REAL de pedidos entregados (lo que ya ganaste)
- `total_return_cost`: Costo total de devoluciones (Q23 × número de devoluciones)
- `net_profit`: Ganancia neta = delivered_profit - total_return_cost
- `pending_profit`: Ganancia proyectada de pedidos pendientes
- `projected_profit`: Ganancia si se entregan todos los pendientes

**Fórmula de Profit REAL:**
- Profit Bruto = `net_profit` (de Dropi)
- Profit Neto = `net_profit` - Gasto en Meta Ads
- Si Profit Neto > 0 → ✅ Ganando
- Si Profit Neto < 0 → ❌ Perdiendo

### ROAS (Return On Ad Spend)
- ROAS = net_profit ÷ Gasto en Ads
- ROAS > 1.5 es rentable, > 2 es bueno, > 3 es excelente

## 🧠 CÓMO RESPONDER A "¿ESTOY GANANDO PLATA?"

Cuando el usuario pregunte sobre rentabilidad, SIEMPRE:

1. **DETERMINA EL PERIODO PRIMERO**:
   La fecha de hoy es {today}. Calcula "ayer" restando un día.
   
   - Si el usuario dice "hoy" → usa start_date="{today}", end_date="{today}"
   - Si dice "ayer" → calcula la fecha de ayer y usa start_date="YYYY-MM-DD", end_date="YYYY-MM-DD" (misma fecha)
   - Si dice "esta semana" o "últimos 7 días" → usa days=7
   - Si dice "este mes" o "últimos 30 días" → usa days=30
   - Si dice un mes específico como "noviembre" → usa start_date="2025-11-01", end_date="2025-11-30"
   - Si NO especifica periodo → **PREGUNTA** "¿De qué periodo? ¿Hoy, ayer, esta semana, o este mes?"
   
   ⚠️ **CRÍTICO - PARA "AYER" O "HOY"**:
   - SIEMPRE calcula la fecha correcta basándote en {today}
   - SIEMPRE usa start_date y end_date (NO uses days=1 o days=2)
   - Para UN SOLO DÍA: start_date y end_date deben ser IGUALES
   - Ejemplo: Si hoy es 2025-12-07 y piden "ayer" → start_date="2025-12-06", end_date="2025-12-06"
   
   ⚠️ **USA EL MISMO PERIODO EN TODAS LAS HERRAMIENTAS**
   
   **Para periodos relativos (últimos X días):**
   - Meta: get_ad_spend_by_period con period="last_7d"
   - Dropi: get_dropi_orders con days=7
   - Shopify: get_sales_by_period con el mismo rango
   
   **Para días específicos (hoy, ayer):**
   - Dropi: get_dropi_orders con start_date y end_date (AMBOS con la misma fecha)
   - Meta: get_ad_spend_by_period con period="yesterday" o period="today"
   
   **Para meses específicos (noviembre, octubre, etc.):**
   - Dropi: get_dropi_orders con start_date="2025-11-01", end_date="2025-11-30"
   - Meta: get_ad_spend_by_period con period="last_month"

2. **Obtén datos de las 3 fuentes** (usa múltiples herramientas):
   - Meta: Gasto total del período
   - Shopify: Pedidos y ventas del período
   - Dropi: Entregas, devoluciones y pagos

3. **Calcula las métricas**:
   - CPA inicial vs CPA real
   - Tasa de entrega
   - Profit actual
   - Proyección si se entregan los pendientes

4. **Da un veredicto claro**:
   - ✅ "Estás ganando X"
   - ❌ "Estás perdiendo X"
   - ⚠️ "Vas tablas, pero si se entregan los pendientes..."

5. **Incluye recomendaciones**:
   - Si el CPA está alto, sugerir optimizar campañas
   - Si hay muchas devoluciones, revisar calidad o zona de envío
   - Si hay pedidos pendientes, dar proyecciones

## 💬 ESTILO DE COMUNICACIÓN

- Responde siempre en ESPAÑOL
- Sé directo y conciso (es por WhatsApp)
- Usa emojis para hacerlo visual pero sin exceso
- Los montos siempre con símbolo de moneda
- Si no tienes datos suficientes, pregunta el período

## ⚠️ REGLAS IMPORTANTES

1. SIEMPRE usa las herramientas cuando pregunten por datos reales
2. NO inventes números - si no hay datos, dilo
3. Cuando haya error de conexión, informa y sugiere reintentar
4. Si piden algo que no puedes hacer, explica qué sí puedes hacer
5. Para análisis completos, llama MÚLTIPLES herramientas en secuencia
6. **PERIODOS CONSISTENTES**: Cuando compares datos de Meta, Dropi y Shopify, SIEMPRE usa el mismo periodo en todas las llamadas.
7. **HISTORIAL DE CARTERA**: Si el usuario pregunta por "historial de cartera", "movimientos", "entradas y salidas" o "cuánto gané":
   - NO uses dropi_get_dropi_wallet_history (está roto, da HTTP 500)
   - USA dropi_get_dropi_orders - esta herramienta calcula las ganancias reales
   - Los campos importantes son: delivered_profit, total_return_cost, net_profit, delivered_orders, returned_orders

8. **🚨 CRÍTICO - FECHAS PARA "AYER" O "HOY"**:
   - NUNCA uses days=1 o days=2 para "ayer" o "hoy"
   - SIEMPRE usa start_date y end_date con la fecha exacta
   - Para un solo día, start_date y end_date son IGUALES
   - Ejemplo: "ayer" cuando hoy es 2025-12-07 → start_date="2025-12-06", end_date="2025-12-06"
   - Si usas days, el filtrado no funcionará correctamente

## 🔧 LISTA DE HERRAMIENTAS DISPONIBLES

META ADS:
- meta_get_ad_spend_today: Gasto de hoy
- meta_get_ad_spend_by_period: Gasto por período (today, yesterday, last_7d, last_30d)
- meta_get_campaign_performance: Rendimiento por campaña
- meta_get_adset_performance: Rendimiento por conjunto de anuncios
- meta_get_ad_account_info: Info de la cuenta

SHOPIFY:
- shopify_get_total_sales_today: Ventas de hoy
- shopify_get_sales_by_period: Ventas por período
- shopify_get_recent_orders: Últimos pedidos con detalles
- shopify_get_order_details: Detalle de un pedido específico
- shopify_get_all_products: Todos los productos
- shopify_get_low_stock_products: Productos con bajo inventario
- shopify_get_best_selling_products: Más vendidos

DROPI:
- dropi_get_dropi_wallet: Saldo actual en cartera
- dropi_get_dropi_wallet_history: ⚠️ NO USAR - Este endpoint tiene problemas (HTTP 500). Usar get_dropi_orders en su lugar.
- dropi_get_dropi_orders: ✅ USAR ESTA para calcular ganancias. Retorna: delivered_profit (ganancia real), net_profit (ganancia neta), total_return_cost (costo devoluciones). Parámetros: days (int) O start_date/end_date (YYYY-MM-DD), limit (int, default 100)
- dropi_get_dropi_order: Detalle de una orden específica
- dropi_get_dropi_user_info: Info del usuario

⚠️ IMPORTANTE SOBRE DROPI:
- Para saber CUÁNTO GANÓ el usuario, SIEMPRE usa dropi_get_dropi_orders
- NO uses dropi_get_dropi_wallet_history (está roto)
- El campo "net_profit" de get_dropi_orders es la ganancia real después de descontar devoluciones

N8N (Gráficos y Visualizaciones):
- n8n_generate_chart: Genera gráficos de barras, líneas, pie. Requiere: tipo, titulo, labels, valores
- n8n_generate_comparison_chart: Genera gráficos comparativos con múltiples series

## 📊 CUÁNDO USAR GRÁFICOS

Genera un gráfico cuando el usuario:
- Pida "muéstrame un gráfico de..."
- Quiera visualizar tendencias o comparativas
- Pida reportes visuales

Ejemplo de uso de n8n_generate_chart:
- tipo: "bar" (barras), "line" (líneas), "pie" (pastel)
- titulo: "Ventas de la Semana"
- labels: ["Lun", "Mar", "Mie", "Jue", "Vie"]
- valores: [150, 230, 180, 290, 200]

Cuando generes un gráfico, incluye el link de la imagen en tu respuesta para que el usuario pueda verlo.

¡Ahora ayuda al usuario a dominar su negocio! 💪
"""


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
        for name in self.tools_by_name:
            logger.info(f"   - {name}")
    
    async def agent_node(self, state: AgentState) -> dict:
        await self.initialize_tools()
        
        # System prompt con fecha actual
        today = datetime.now().strftime("%Y-%m-%d")
        system_content = SYSTEM_PROMPT.format(today=today)
        system = SystemMessage(content=system_content)
        
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
                    
                    logger.info(f"✅ Resultado: {str(result)[:200]}...")
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
    
    async def get_conversation_history(self, user_id: str) -> list:
        """Obtiene el historial de conversación de un usuario."""
        config = {"configurable": {"thread_id": user_id}}
        try:
            state = await self.graph.aget_state(config)
            if state and state.values:
                messages = state.values.get("messages", [])
                return [
                    {
                        "type": type(msg).__name__,
                        "content": msg.content if hasattr(msg, 'content') else str(msg)
                    }
                    for msg in messages
                ]
        except Exception as e:
            logger.error(f"Error obteniendo historial: {e}")
        return []
    
    async def clear_conversation(self, user_id: str):
        """Limpia el historial de conversación de un usuario."""
        # Con MemorySaver no hay una forma directa de limpiar
        # pero podemos reiniciar el thread_id
        logger.info(f"Conversación limpiada para {user_id}")


conversation_manager = ConversationManager()