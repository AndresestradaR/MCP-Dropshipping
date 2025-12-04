"""
Servidor MCP para Dropi - v5.0 FINAL
Basado en la documentación oficial de Dropi
Usa LOGIN con email/password para obtener token
"""

import os
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

load_dotenv()

# ==============================================================================
# CONFIGURACIÓN DE DROPI
# ==============================================================================

DROPI_EMAIL = os.getenv("DROPI_EMAIL", "")
DROPI_PASSWORD = os.getenv("DROPI_PASSWORD", "")
DROPI_COUNTRY = os.getenv("DROPI_COUNTRY", "gt").lower()

# Según documentación: white_brand_id siempre es este valor
WHITE_BRAND_ID = "df3e6b0bb66ceaadca4f84cbc371fd66e04d20fe51fc414da8d1b84d31d178de"

# URLs por país según documentación
API_URLS = {
    "gt": "https://api.dropi.gt",
    "co": "https://api.dropi.co",
    "mx": "https://api.dropi.mx",
    "cl": "https://api.dropi.cl",
    "pe": "https://api.dropi.pe",
    "ec": "https://api.dropi.ec",
}

DROPI_API_URL = API_URLS.get(DROPI_COUNTRY, "https://api.dropi.gt")

# Token guardado en memoria (se obtiene con login)
current_token = None
current_user = None
sessions = {}

# ==============================================================================
# LOGIN Y AUTENTICACIÓN
# ==============================================================================

async def dropi_login() -> dict:
    """Hace login en Dropi y obtiene el token."""
    global current_token, current_user
    
    if not DROPI_EMAIL or not DROPI_PASSWORD:
        return {"success": False, "error": "Email o password no configurados"}
    
    url = f"{DROPI_API_URL}/api/login"
    payload = {
        "email": DROPI_EMAIL,
        "password": DROPI_PASSWORD,
        "white_brand_id": WHITE_BRAND_ID
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            data = response.json()
            
            if data.get("isSuccess") and data.get("token"):
                current_token = data["token"]
                current_user = data.get("objects", {})
                return {"success": True, "token": current_token, "user": current_user}
            else:
                return {"success": False, "error": data.get("message", "Login failed")}
        except Exception as e:
            return {"success": False, "error": str(e)}

def get_headers():
    """Headers con el token de autenticación."""
    return {
        "Authorization": f"Bearer {current_token}" if current_token else "",
        "Content-Type": "application/json"
    }

async def ensure_token():
    """Asegura que hay un token válido."""
    global current_token
    if not current_token:
        result = await dropi_login()
        return result.get("success", False)
    return True

async def dropi_get(endpoint: str, params: dict = None) -> dict:
    """GET request a la API de Dropi."""
    if not await ensure_token():
        return {"success": False, "error": "No se pudo autenticar. Verifica email y password."}
    
    url = f"{DROPI_API_URL}{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=get_headers(), params=params)
            
            # Si token expiró, re-login
            if response.status_code == 401:
                global current_token
                current_token = None
                login_result = await dropi_login()
                if login_result.get("success"):
                    response = await client.get(url, headers=get_headers(), params=params)
                else:
                    return {"success": False, "error": "Token expirado y no se pudo renovar"}
            
            if response.status_code == 200:
                data = response.json()
                if data.get("isSuccess", True):  # Dropi devuelve isSuccess
                    return {"success": True, "data": data}
                else:
                    return {"success": False, "error": data.get("message", "Error desconocido")}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

async def dropi_post(endpoint: str, payload: dict) -> dict:
    """POST request a la API de Dropi."""
    if not await ensure_token():
        return {"success": False, "error": "No se pudo autenticar. Verifica email y password."}
    
    url = f"{DROPI_API_URL}{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=get_headers(), json=payload)
            
            if response.status_code == 401:
                global current_token
                current_token = None
                login_result = await dropi_login()
                if login_result.get("success"):
                    response = await client.post(url, headers=get_headers(), json=payload)
                else:
                    return {"success": False, "error": "Token expirado"}
            
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "data": data}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ==============================================================================
# HERRAMIENTAS MCP
# ==============================================================================

TOOLS = [
    {
        "name": "get_dropi_wallet",
        "description": "Obtiene el saldo disponible en la billetera/cartera de Dropi del usuario.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_wallet_history",
        "description": "Historial de movimientos de la cartera: entradas, salidas, pagos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Últimos X días (default 30)"},
                "type": {"type": "string", "description": "ENTRADA o SALIDA (opcional)"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_orders",
        "description": "Lista las órdenes/pedidos de Dropi con estados y valores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de resultados (default 20)"},
                "status": {"type": "string", "description": "Filtrar por estado: PENDIENTE, GUIA_GENERADA, ENTREGADO, etc."},
                "days": {"type": "integer", "description": "Últimos X días"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_order",
        "description": "Obtiene los detalles de una orden específica por su ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "ID de la orden en Dropi"}
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "get_dropi_user_info",
        "description": "Información del usuario autenticado de Dropi.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    }
]

# ==============================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# ==============================================================================

async def get_dropi_wallet(args: dict) -> str:
    """Obtiene el saldo de la cartera."""
    # El saldo viene en el login, en current_user
    if not current_user:
        login_result = await dropi_login()
        if not login_result.get("success"):
            return f"❌ Error: {login_result.get('error')}"
    
    # También probamos el historial para ver el balance actual
    result = await dropi_get("/api/historywallet", {"result_number": 1})
    
    user = current_user or {}
    wallet_amount = user.get("wallet", {}).get("amount") if isinstance(user.get("wallet"), dict) else None
    
    # Buscar en wallets si existe
    wallets = user.get("wallets", [])
    if wallets and isinstance(wallets, list):
        for w in wallets:
            if w.get("amount"):
                wallet_amount = w.get("amount")
                break
    
    if wallet_amount is not None:
        return f"""💰 BILLETERA DROPI

💵 Saldo Disponible: Q{float(wallet_amount):,.2f}

👤 Usuario: {user.get('name', '')} {user.get('surname', '')}
📧 Email: {user.get('email', DROPI_EMAIL)}
🆔 ID: {user.get('id', 'N/A')}
🌍 País: {DROPI_COUNTRY.upper()}

✅ Conexión exitosa con Dropi"""
    
    # Si no hay wallet en user, mostrar lo que tenemos
    return f"""👤 USUARIO DROPI

📧 Email: {user.get('email', DROPI_EMAIL)}
📛 Nombre: {user.get('name', '')} {user.get('surname', '')}
🆔 ID: {user.get('id', 'N/A')}

💡 Para ver el saldo, consulta el historial de cartera.
✅ Conexión exitosa"""

async def get_dropi_wallet_history(args: dict) -> str:
    """Historial de movimientos de cartera."""
    days = args.get("days", 30)
    mov_type = args.get("type")  # ENTRADA o SALIDA
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    
    params = {
        "result_number": 50,
        "start": 0,
        "from": date_from,
        "until": date_to,
        "orderBy": "id",
        "orderDirection": "desc"
    }
    if mov_type:
        params["type"] = mov_type
    
    result = await dropi_get("/api/historywallet", params)
    
    if not result.get("success"):
        return f"❌ Error: {result.get('error')}"
    
    data = result.get("data", {})
    movements = data.get("objects", []) if isinstance(data, dict) else []
    count = data.get("count", len(movements))
    
    if not movements:
        return f"📊 No hay movimientos en los últimos {days} días."
    
    result_text = f"📊 HISTORIAL CARTERA (últimos {days} días)\n"
    result_text += f"📈 Total movimientos: {count}\n\n"
    
    total_in = 0
    total_out = 0
    
    for mov in movements[:20]:
        value = float(mov.get("value", 0) or 0)
        mov_type = mov.get("type", "")
        date = str(mov.get("created_at", ""))[:10]
        concept = mov.get("concept", "") or mov.get("description", "")
        order_id = mov.get("order_id", "")
        
        if value >= 0 or mov_type == "ENTRADA":
            total_in += abs(value)
            emoji = "💵"
        else:
            total_out += abs(value)
            emoji = "💸"
        
        result_text += f"{emoji} Q{abs(value):,.2f} | {mov_type}"
        if order_id:
            result_text += f" | Orden #{order_id}"
        if date:
            result_text += f" | {date}"
        result_text += "\n"
    
    result_text += f"\n📈 RESUMEN:\n"
    result_text += f"   💵 Entradas: Q{total_in:,.2f}\n"
    result_text += f"   💸 Salidas: Q{total_out:,.2f}\n"
    result_text += f"   📊 Neto: Q{total_in - total_out:,.2f}"
    
    return result_text

async def get_dropi_orders(args: dict) -> str:
    """Obtiene las órdenes."""
    limit = args.get("limit", 20)
    status = args.get("status")
    days = args.get("days", 30)
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    
    params = {
        "result_number": limit,
        "start": 0,
        "from": date_from,
        "until": date_to,
        "orderBy": "id",
        "orderDirection": "desc",
        "filter_date_by": "FECHA DE CREADO"
    }
    if status:
        params["status"] = status
    
    result = await dropi_get("/api/orders/myorders", params)
    
    if not result.get("success"):
        return f"❌ Error: {result.get('error')}"
    
    data = result.get("data", {})
    orders = data.get("objects", []) if isinstance(data, dict) else []
    count = data.get("count", len(orders))
    
    if not orders:
        return f"📦 No hay órdenes en los últimos {days} días."
    
    result_text = f"📦 ÓRDENES DROPI\n"
    result_text += f"📈 Total: {count} | Mostrando: {len(orders)}\n\n"
    
    stats = {}
    total_value = 0
    
    for order in orders[:20]:
        order_id = order.get("id", "N/A")
        status = order.get("status", "?")
        customer = f"{order.get('name', '')} {order.get('surname', '')}".strip() or "Cliente"
        amount = float(order.get("total_order", 0) or 0)
        city = order.get("city", "")
        date = str(order.get("created_at", ""))[:10]
        guide = order.get("shipping_guide", "")
        
        stats[status] = stats.get(status, 0) + 1
        total_value += amount
        
        result_text += f"📌 #{order_id} | {customer[:20]}\n"
        result_text += f"   💵 Q{amount:,.2f} | 📊 {status}\n"
        if city:
            result_text += f"   📍 {city}"
        if guide:
            result_text += f" | 🚚 {guide}"
        if date:
            result_text += f" | 📅 {date}"
        result_text += "\n\n"
    
    result_text += f"📊 POR ESTADO:\n"
    for st, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        result_text += f"   • {st}: {cnt}\n"
    result_text += f"\n💰 Valor Total: Q{total_value:,.2f}"
    
    return result_text

async def get_dropi_order(args: dict) -> str:
    """Obtiene una orden específica."""
    order_id = args.get("order_id")
    if not order_id:
        return "❌ Se requiere order_id"
    
    result = await dropi_get(f"/api/orders/myorders/{order_id}")
    
    if not result.get("success"):
        return f"❌ Error: {result.get('error')}"
    
    data = result.get("data", {})
    order = data.get("objects", {}) if isinstance(data, dict) else {}
    
    if not order:
        return f"❌ Orden #{order_id} no encontrada"
    
    result_text = f"""📦 ORDEN #{order.get('id')}

👤 Cliente: {order.get('name', '')} {order.get('surname', '')}
📱 Teléfono: {order.get('phone', 'N/A')}
📧 Email: {order.get('client_email', 'N/A')}
📍 Dirección: {order.get('dir', 'N/A')}
🏙️ Ciudad: {order.get('city', 'N/A')}, {order.get('state', '')}

💵 Total: Q{float(order.get('total_order', 0)):,.2f}
🚚 Envío: Q{float(order.get('shipping_amount', 0)):,.2f}
💰 Ganancia: Q{float(order.get('dropshipper_amount_to_win', 0)):,.2f}

📊 Estado: {order.get('status', 'N/A')}
📋 Tipo: {order.get('rate_type', 'N/A')}
🚚 Guía: {order.get('shipping_guide', 'Sin guía')}
🚛 Transportadora: {order.get('shipping_company', 'N/A')}

📅 Creado: {str(order.get('created_at', ''))[:19]}
📅 Actualizado: {str(order.get('updated_at', ''))[:19]}
"""
    
    # Productos
    details = order.get("orderdetails", [])
    if details:
        result_text += "\n📦 PRODUCTOS:\n"
        for d in details:
            product = d.get("product", {})
            result_text += f"   • {product.get('name', 'Producto')} x{d.get('quantity', 1)} = Q{float(d.get('price', 0)):,.2f}\n"
    
    return result_text

async def get_dropi_user_info(args: dict) -> str:
    """Info del usuario."""
    if not current_user:
        login_result = await dropi_login()
        if not login_result.get("success"):
            return f"❌ Error: {login_result.get('error')}"
    
    user = current_user or {}
    
    return f"""👤 USUARIO DROPI

📛 Nombre: {user.get('name', '')} {user.get('surname', '')}
📧 Email: {user.get('email', DROPI_EMAIL)}
📱 Teléfono: {user.get('phone', 'N/A')}
🆔 ID: {user.get('id', 'N/A')}
🌍 País: {DROPI_COUNTRY.upper()}

📊 Estado: {user.get('status', 'N/A')}
🏢 Tienda: {user.get('store_phone', 'N/A')}

✅ Autenticado correctamente"""

# ==============================================================================
# DISPATCHER
# ==============================================================================

TOOL_HANDLERS = {
    "get_dropi_wallet": get_dropi_wallet,
    "get_dropi_wallet_history": get_dropi_wallet_history,
    "get_dropi_orders": get_dropi_orders,
    "get_dropi_order": get_dropi_order,
    "get_dropi_user_info": get_dropi_user_info,
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
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "dropi-mcp", "version": "5.0.0"}}}
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
        "version": "5.0.0",
        "api_url": DROPI_API_URL,
        "country": DROPI_COUNTRY.upper(),
        "email_configured": bool(DROPI_EMAIL),
        "password_configured": bool(DROPI_PASSWORD),
        "authenticated": bool(current_token),
        "user_id": current_user.get("id") if current_user else None
    })

async def login_endpoint(request):
    """Endpoint para hacer login manualmente."""
    result = await dropi_login()
    return JSONResponse(result)

async def discover(request):
    """Test de conexión."""
    # Primero hacer login
    login_result = await dropi_login()
    
    if not login_result.get("success"):
        return JSONResponse({
            "success": False,
            "error": login_result.get("error"),
            "config": {
                "api_url": DROPI_API_URL,
                "email": DROPI_EMAIL[:3] + "***" if DROPI_EMAIL else "NOT SET",
                "password": "***" if DROPI_PASSWORD else "NOT SET"
            }
        })
    
    # Probar endpoints
    tests = {}
    
    # Test historial
    r = await dropi_get("/api/historywallet", {"result_number": 1})
    tests["historywallet"] = "✅" if r.get("success") else f"❌ {r.get('error')}"
    
    # Test órdenes
    r = await dropi_get("/api/orders/myorders", {"result_number": 1})
    tests["orders"] = "✅" if r.get("success") else f"❌ {r.get('error')}"
    
    return JSONResponse({
        "success": True,
        "user": {
            "id": current_user.get("id"),
            "name": f"{current_user.get('name', '')} {current_user.get('surname', '')}",
            "email": current_user.get("email")
        },
        "tests": tests
    })

# ==============================================================================
# APP
# ==============================================================================

app = Starlette(routes=[
    Route("/", health),
    Route("/health", health),
    Route("/login", login_endpoint),
    Route("/discover", discover),
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 Dropi MCP Server v5.0 - LOGIN MODE")
    print(f"🌍 País: {DROPI_COUNTRY.upper()}")
    print(f"🔗 API: {DROPI_API_URL}")
    print(f"📧 Email: {DROPI_EMAIL[:3]}***" if DROPI_EMAIL else "📧 Email: NOT SET")
    print(f"🔑 Password: {'***' if DROPI_PASSWORD else 'NOT SET'}")
    uvicorn.run(app, host="0.0.0.0", port=port)