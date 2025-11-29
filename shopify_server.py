"""
Servidor MCP para Shopify - HTTP + SSE
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

SHOPIFY_SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

sessions = {}

TOOLS = [
    {
        "name": "get_total_sales_today",
        "description": "Obtiene el total de ventas del dia de hoy en Shopify",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "check_product_inventory",
        "description": "Busca un producto por nombre y dice cuanto inventario tiene",
        "inputSchema": {
            "type": "object",
            "properties": {"product_name": {"type": "string", "description": "Nombre del producto"}},
            "required": ["product_name"]
        }
    }
]

async def get_sales_today():
    import datetime
    today = datetime.date.today().isoformat()
    shop_url = SHOPIFY_SHOP_URL.replace("https://", "").replace("/", "")
    url = f"https://{shop_url}/admin/api/2024-01/orders.json?created_at_min={today}&status=any"
    
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return f"Error: {response.status_code}"
            data = response.json()
            orders = data.get("orders", [])
            total = sum(float(o.get("total_price", 0)) for o in orders)
            return f"Ventas HOY ({today}): ${total:,.2f} en {len(orders)} pedidos"
        except Exception as e:
            return f"Error: {str(e)}"

async def check_inventory(product_name: str):
    shop_url = SHOPIFY_SHOP_URL.replace("https://", "").replace("/", "")
    url = f"https://{shop_url}/admin/api/2024-01/products.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    
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
                return f"No encontre '{product_name}'"
            return "Inventario:\n" + "\n".join(found)
        except Exception as e:
            return f"Error: {str(e)}"

# ===== ENDPOINTS HTTP DIRECTOS (SIMPLES) =====

async def http_tools(request):
    """Devuelve lista de herramientas via HTTP GET"""
    return JSONResponse({"tools": TOOLS})

async def http_call_tool(request):
    """Ejecuta una herramienta via HTTP POST"""
    body = await request.json()
    name = body.get("name", "")
    args = body.get("arguments", {})
    
    if name == "get_total_sales_today":
        result = await get_sales_today()
    elif name == "check_product_inventory":
        result = await check_inventory(args.get("product_name", ""))
    else:
        result = f"Herramienta {name} no encontrada"
    
    return JSONResponse({"result": result})

# ===== ENDPOINTS SSE (para compatibilidad MCP) =====

async def sse_endpoint(request):
    queue = asyncio.Queue()
    session_id = str(id(queue))
    sessions[session_id] = queue
    
    async def event_generator():
        try:
            yield {"event": "endpoint", "data": f"/messages/{session_id}"}
            while True:
                data = await queue.get()
                yield {"event": "message", "data": json.dumps(data)}
        except asyncio.CancelledError:
            pass
        finally:
            sessions.pop(session_id, None)
    
    return EventSourceResponse(event_generator())

async def messages_endpoint(request):
    session_id = request.path_params["session_id"]
    if session_id not in sessions:
        return Response("Session not found", status_code=404)
    
    body = await request.json()
    method = body.get("method", "")
    msg_id = body.get("id")
    
    if method == "initialize":
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "shopify-mcp", "version": "1.0.0"}}}
    elif method == "tools/list":
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name == "get_total_sales_today":
            result = await get_sales_today()
        elif name == "check_product_inventory":
            result = await check_inventory(args.get("product_name", ""))
        else:
            result = f"Tool {name} not found"
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": result}]}}
    else:
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    
    if response and msg_id:
        await sessions[session_id].put(response)
    
    return Response("OK")

async def health(request):
    return Response("OK")

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
    uvicorn.run(app, host="0.0.0.0", port=port)