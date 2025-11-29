"""
Servidor MCP para Shopify con SSE manual.
"""

import os
import json
import httpx
import asyncio
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response
from sse_starlette.sse import EventSourceResponse
from mcp.server import Server
from mcp.types import Tool, TextContent
import uvicorn

load_dotenv()

SHOPIFY_SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

# Crear servidor MCP
server = Server("shopify-mcp")

# Registrar herramientas
@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="get_total_sales_today",
            description="Obtiene el total de ventas del dia de hoy en Shopify",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="check_product_inventory",
            description="Busca un producto por nombre y dice cuanto inventario tiene",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "Nombre del producto a buscar"}
                },
                "required": ["product_name"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_total_sales_today":
        return await get_sales_today()
    elif name == "check_product_inventory":
        return await check_inventory(arguments.get("product_name", ""))
    return [TextContent(type="text", text=f"Herramienta {name} no encontrada")]

async def get_sales_today():
    import datetime
    today = datetime.date.today().isoformat()
    shop_url = SHOPIFY_SHOP_URL.replace("https://", "").replace("/", "")
    url = f"https://{shop_url}/admin/api/2024-01/orders.json?created_at_min={today}&status=any"
    
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return [TextContent(type="text", text=f"Error: {response.status_code}")]
            
            data = response.json()
            orders = data.get("orders", [])
            total = sum(float(o.get("total_price", 0)) for o in orders)
            
            return [TextContent(type="text", text=f"Ventas HOY ({today}): ${total:,.2f} en {len(orders)} pedidos")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

async def check_inventory(product_name: str):
    shop_url = SHOPIFY_SHOP_URL.replace("https://", "").replace("/", "")
    url = f"https://{shop_url}/admin/api/2024-01/products.json"
    
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            data = response.json()
            products = data.get("products", [])
            
            found = []
            for p in products:
                if product_name.lower() in p["title"].lower():
                    variants = p.get("variants", [])
                    inv = sum(v.get("inventory_quantity", 0) for v in variants)
                    found.append(f"- {p['title']}: {inv} unidades")
            
            if not found:
                return [TextContent(type="text", text=f"No encontre '{product_name}'")]
            
            return [TextContent(type="text", text="Inventario:\n" + "\n".join(found))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

# Cola de mensajes para SSE
message_queues = {}

async def sse_endpoint(request):
    queue = asyncio.Queue()
    session_id = id(queue)
    message_queues[session_id] = queue
    
    async def event_generator():
        try:
            # Enviar endpoint para mensajes
            yield {"event": "endpoint", "data": f"/messages/{session_id}"}
            
            while True:
                message = await queue.get()
                yield {"event": "message", "data": json.dumps(message)}
        except asyncio.CancelledError:
            pass
        finally:
            message_queues.pop(session_id, None)
    
    return EventSourceResponse(event_generator())

async def messages_endpoint(request):
    session_id = int(request.path_params["session_id"])
    
    if session_id not in message_queues:
        return Response("Session not found", status_code=404)
    
    body = await request.json()
    
    # Procesar mensaje MCP
    if body.get("method") == "tools/list":
        tools = await list_tools()
        response = {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"tools": [t.model_dump() for t in tools]}
        }
    elif body.get("method") == "tools/call":
        params = body.get("params", {})
        result = await call_tool(params.get("name"), params.get("arguments", {}))
        response = {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"content": [c.model_dump() for c in result]}
        }
    elif body.get("method") == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "shopify-mcp", "version": "1.0.0"}
            }
        }
    else:
        response = {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {}
        }
    
    # Enviar respuesta por SSE
    await message_queues[session_id].put(response)
    
    return Response("OK", status_code=200)

async def health(request):
    return Response("OK")

app = Starlette(
    routes=[
        Route("/sse", sse_endpoint),
        Route("/messages/{session_id:int}", messages_endpoint, methods=["POST"]),
        Route("/health", health),
        Route("/", health),
    ]
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)