"""
Servidor MCP para N8N - v1.0
Conecta el Cerebro con workflows de N8N
"""

import os
import json
import httpx
import asyncio
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

load_dotenv()

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.srv1121056.hstgr.cloud")
N8N_WEBHOOK_GRAFICO = os.getenv("N8N_WEBHOOK_GRAFICO", f"{N8N_BASE_URL}/webhook/grafico")

sessions = {}

# ==============================================================================
# HERRAMIENTAS MCP
# ==============================================================================

TOOLS = [
    {
        "name": "generate_chart",
        "description": "Genera un gráfico/chart visual (barras, líneas, pie) y devuelve la URL de la imagen. Útil para visualizar ventas, gastos, comparativas, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "description": "Tipo de gráfico: bar (barras), line (líneas), pie (pastel), doughnut (dona)",
                    "enum": ["bar", "line", "pie", "doughnut"]
                },
                "titulo": {
                    "type": "string",
                    "description": "Título del gráfico, ej: 'Ventas de la Semana'"
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Etiquetas del eje X o categorías, ej: ['Lun', 'Mar', 'Mie', 'Jue', 'Vie']"
                },
                "valores": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Valores numéricos correspondientes a cada label, ej: [150, 230, 180, 290, 200]"
                }
            },
            "required": ["tipo", "titulo", "labels", "valores"]
        }
    },
    {
        "name": "generate_comparison_chart",
        "description": "Genera un gráfico comparativo con múltiples series de datos (ej: ventas vs gastos, este mes vs mes anterior)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "titulo": {
                    "type": "string",
                    "description": "Título del gráfico"
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Etiquetas del eje X"
                },
                "series": {
                    "type": "array",
                    "description": "Lista de series de datos. Cada serie tiene: nombre y valores",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {"type": "string"},
                            "valores": {"type": "array", "items": {"type": "number"}}
                        }
                    }
                }
            },
            "required": ["titulo", "labels", "series"]
        }
    }
]

# ==============================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# ==============================================================================

async def generate_chart(args: dict) -> str:
    """Genera un gráfico simple."""
    tipo = args.get("tipo", "bar")
    titulo = args.get("titulo", "Gráfico")
    labels = args.get("labels", [])
    valores = args.get("valores", [])
    
    if not labels or not valores:
        return "❌ Error: Debes proporcionar labels y valores para el gráfico"
    
    if len(labels) != len(valores):
        return "❌ Error: La cantidad de labels debe coincidir con la cantidad de valores"
    
    payload = {
        "tipo": tipo,
        "titulo": titulo,
        "labels": labels,
        "valores": valores
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(N8N_WEBHOOK_GRAFICO, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("image_url"):
                    return f"""📊 GRÁFICO GENERADO

📌 Título: {titulo}
📈 Tipo: {tipo}
🔗 Ver gráfico: {data['image_url']}

💡 Puedes abrir el link para ver la imagen del gráfico."""
                else:
                    return f"❌ Error generando gráfico: {data}"
            else:
                return f"❌ Error HTTP {response.status_code}: {response.text}"
                
        except Exception as e:
            return f"❌ Error conectando con N8N: {str(e)}"


async def generate_comparison_chart(args: dict) -> str:
    """Genera un gráfico comparativo con múltiples series."""
    titulo = args.get("titulo", "Comparativa")
    labels = args.get("labels", [])
    series = args.get("series", [])
    
    if not labels or not series:
        return "❌ Error: Debes proporcionar labels y series para el gráfico"
    
    # Construir configuración de Chart.js para múltiples datasets
    colors = ['#4CAF50', '#2196F3', '#FF9800', '#f44336', '#9C27B0', '#00BCD4']
    
    datasets = []
    for i, serie in enumerate(series):
        datasets.append({
            "label": serie.get("nombre", f"Serie {i+1}"),
            "data": serie.get("valores", []),
            "backgroundColor": colors[i % len(colors)],
            "borderColor": colors[i % len(colors)],
            "borderWidth": 2,
            "fill": False
        })
    
    chart_config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": datasets
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": titulo, "font": {"size": 18}},
                "legend": {"display": True}
            }
        }
    }
    
    chart_url = 'https://quickchart.io/chart?c=' + json.dumps(chart_config).replace(' ', '') + '&w=600&h=400&bkg=white'
    
    # Codificar URL
    import urllib.parse
    chart_url = 'https://quickchart.io/chart?c=' + urllib.parse.quote(json.dumps(chart_config)) + '&w=600&h=400&bkg=white'
    
    series_info = "\n".join([f"   • {s.get('nombre', 'Serie')}: {s.get('valores', [])}" for s in series])
    
    return f"""📊 GRÁFICO COMPARATIVO GENERADO

📌 Título: {titulo}
📈 Series:
{series_info}

🔗 Ver gráfico: {chart_url}

💡 Puedes abrir el link para ver la imagen del gráfico."""


# ==============================================================================
# DISPATCHER
# ==============================================================================

TOOL_HANDLERS = {
    "generate_chart": generate_chart,
    "generate_comparison_chart": generate_comparison_chart,
}

async def execute_tool(name: str, args: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler:
        try:
            return await handler(args)
        except Exception as e:
            return f"Error ejecutando {name}: {str(e)}"
    return f"Herramienta '{name}' no encontrada"

# ==============================================================================
# ENDPOINTS HTTP
# ==============================================================================

async def http_tools(request):
    return JSONResponse({"tools": TOOLS})

async def http_call_tool(request):
    body = await request.json()
    result = await execute_tool(body.get("name", ""), body.get("arguments", {}))
    return JSONResponse({"result": result})

async def sse_endpoint(request):
    queue = asyncio.Queue()
    session_id = str(id(queue))
    sessions[session_id] = queue
    async def gen():
        try:
            yield {"event": "endpoint", "data": f"/messages/{session_id}"}
            while True:
                data = await queue.get()
                yield {"event": "message", "data": json.dumps(data)}
        except asyncio.CancelledError:
            pass
        finally:
            sessions.pop(session_id, None)
    return EventSourceResponse(gen())

async def messages_endpoint(request):
    session_id = request.path_params["session_id"]
    if session_id not in sessions:
        return Response("Not found", status_code=404)
    body = await request.json()
    method = body.get("method", "")
    msg_id = body.get("id")
    if method == "initialize":
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "n8n-mcp", "version": "1.0.0"}}}
    elif method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = body.get("params", {})
        result = await execute_tool(params.get("name", ""), params.get("arguments", {}))
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": result}]}}
    else:
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if resp and msg_id:
        await sessions[session_id].put(resp)
    return Response("OK")

async def health(request):
    return JSONResponse({
        "status": "ok",
        "version": "1.0.0",
        "n8n_base_url": N8N_BASE_URL,
        "webhook_grafico": N8N_WEBHOOK_GRAFICO
    })

# ==============================================================================
# APP
# ==============================================================================

app = Starlette(routes=[
    Route("/", health),
    Route("/health", health),
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 N8N MCP Server v1.0")
    print(f"🔗 N8N URL: {N8N_BASE_URL}")
    print(f"📊 Webhook Gráfico: {N8N_WEBHOOK_GRAFICO}")
    uvicorn.run(app, host="0.0.0.0", port=port)
