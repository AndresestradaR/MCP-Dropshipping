"""
Servidor MCP para Dropi - v4.0 FINAL
Usa api.dropi.gt (NO app.dropi.gt)
Endpoints descubiertos via DevTools
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

DROPI_TOKEN = os.getenv("DROPI_TOKEN", "")
DROPI_COUNTRY = os.getenv("DROPI_COUNTRY", "gt").lower()

# ¡IMPORTANTE! La API usa api.dropi.XX, NO app.dropi.XX
API_DOMAINS = {
    "gt": "https://api.dropi.gt",
    "co": "https://api.dropi.co",
    "mx": "https://api.dropi.mx",
    "cl": "https://api.dropi.cl",
    "pe": "https://api.dropi.pe",
    "ec": "https://api.dropi.ec",
}

APP_DOMAINS = {
    "gt": "https://app.dropi.gt",
    "co": "https://app.dropi.co",
    "mx": "https://app.dropi.mx",
    "cl": "https://app.dropi.cl",
    "pe": "https://app.dropi.pe",
    "ec": "https://app.dropi.ec",
}

DROPI_API_URL = os.getenv("DROPI_API_URL", API_DOMAINS.get(DROPI_COUNTRY, "https://api.dropi.gt"))
DROPI_APP_URL = APP_DOMAINS.get(DROPI_COUNTRY, "https://app.dropi.gt")

sessions = {}

# ==============================================================================
# FUNCIONES PARA JWT
# ==============================================================================

def decode_jwt_payload(token: str) -> dict:
    """Decodifica el payload de un JWT sin verificar firma."""
    try:
        import base64
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except:
        return {}

def get_user_id_from_token() -> str:
    """Extrae el user_id del token JWT."""
    if not DROPI_TOKEN:
        return ""
    payload = decode_jwt_payload(DROPI_TOKEN)
    user_id = payload.get("sub") or payload.get("user_id") or payload.get("id") or payload.get("userId")
    return str(user_id) if user_id else ""

USER_ID = get_user_id_from_token()

# ==============================================================================
# CLIENTE HTTP PARA DROPI
# ==============================================================================

def get_headers():
    """Headers para la API de Dropi - Simula el navegador."""
    return {
        "Authorization": f"Bearer {DROPI_TOKEN}",
        "X-Authorization": f"Bearer {DROPI_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": DROPI_APP_URL,
        "Referer": f"{DROPI_APP_URL}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

async def dropi_get(endpoint: str, params: dict = None) -> dict:
    """GET request a la API de Dropi."""
    # Construir URL
    if endpoint.startswith("http"):
        url = endpoint
    elif endpoint.startswith("/"):
        url = f"{DROPI_API_URL}{endpoint}"
    else:
        url = f"{DROPI_API_URL}/{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=get_headers(), params=params)
            content_type = response.headers.get("content-type", "")
            
            if response.status_code == 200:
                if "application/json" in content_type:
                    return {"success": True, "data": response.json()}
                else:
                    try:
                        return {"success": True, "data": response.json()}
                    except:
                        return {"success": False, "error": "Response is HTML, not JSON", "status": response.status_code}
            elif response.status_code == 401:
                return {"success": False, "error": "Token inválido o expirado (401)"}
            elif response.status_code == 403:
                return {"success": False, "error": "Acceso denegado (403)"}
            elif response.status_code == 404:
                return {"success": False, "error": f"No encontrado (404): {endpoint}"}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ==============================================================================
# HERRAMIENTAS
# ==============================================================================

TOOLS = [
    {
        "name": "get_dropi_wallet",
        "description": "Consulta el saldo disponible en la billetera/wallet de Dropi.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_wallet_history",
        "description": "Historial de movimientos de la billetera: entradas, salidas, pagos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Últimos X días (default 30)"}
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
                "limit": {"type": "integer", "description": "Cantidad (default 50)"},
                "status": {"type": "string", "description": "Filtrar por estado"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_user_info",
        "description": "Información del usuario de Dropi.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_billing_status",
        "description": "Estado de facturación y billing del usuario.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "debug_dropi_endpoint",
        "description": "Debug: probar un endpoint específico de la API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint": {"type": "string", "description": "Endpoint (ej: /api/users/424)"}
            },
            "required": ["endpoint"]
        }
    }
]

# ==============================================================================
# IMPLEMENTACIÓN
# ==============================================================================

async def get_dropi_wallet(args: dict) -> str:
    """Consulta el saldo de la billetera."""
    
    # Endpoint: /api/users/billing/status
    result = await dropi_get(f"/api/users/billing/status")
    
    if result.get("success"):
        data = result.get("data", {})
        
        # Intentar extraer el balance
        if isinstance(data, dict):
            balance = data.get("balance") or data.get("saldo") or data.get("wallet") or data.get("available")
            pending = data.get("pending") or data.get("pendiente") or 0
            
            if balance is not None:
                return f"""💰 BILLETERA DROPI:

💵 Saldo Disponible: ${float(balance):,.2f}
⏳ Pendiente: ${float(pending):,.2f}

✅ Conexión exitosa con Dropi
🔗 Usuario ID: {USER_ID}"""
            
            # Si no hay balance directo, mostrar los datos
            return f"""💰 BILLETERA DROPI:

📊 Datos de billing:
{json.dumps(data, indent=2, ensure_ascii=False)[:1500]}

✅ Conexión exitosa
🔗 Usuario ID: {USER_ID}"""
    
    # Si falla billing/status, intentar otros endpoints
    alt_result = await dropi_get(f"/api/users/{USER_ID}")
    if alt_result.get("success"):
        data = alt_result.get("data", {})
        wallet = data.get("wallet") or data.get("balance") or data.get("saldo")
        if wallet is not None:
            return f"""💰 BILLETERA DROPI:

💵 Saldo: ${float(wallet):,.2f}

✅ Conexión exitosa (via user profile)"""
        
        return f"""👤 PERFIL DROPI:

{json.dumps(data, indent=2, ensure_ascii=False)[:1500]}"""
    
    return f"""❌ No se pudo obtener el saldo.

🔍 Debug:
- API URL: {DROPI_API_URL}
- User ID: {USER_ID}
- Error billing: {result.get('error')}
- Error user: {alt_result.get('error')}

💡 Verifica que el token esté vigente."""

async def get_dropi_wallet_history(args: dict) -> str:
    """Historial de la billetera."""
    days = args.get("days", 30)
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    
    # Endpoint real: /api/historywallet?orderBy=id&orderDirection=desc&result_number=10&...
    params = {
        "orderBy": "id",
        "orderDirection": "desc",
        "result_number": 50,
        "start": 0,
        "textToSearch": "",
        "type": "null",
        "id": "null",
        "identification_code": "null",
        "user_id": USER_ID,
        "from": date_from,
        "until": date_to,
        "wallet_id": 0
    }
    
    result = await dropi_get("/api/historywallet", params)
    
    if result.get("success"):
        data = result.get("data", {})
        
        # La respuesta puede tener diferentes estructuras
        movements = []
        if isinstance(data, list):
            movements = data
        elif isinstance(data, dict):
            movements = data.get("data", []) or data.get("items", []) or data.get("movements", [])
        
        if not movements:
            return f"📊 No hay movimientos en los últimos {days} días."
        
        result_text = f"📊 HISTORIAL BILLETERA (últimos {days} días):\n\n"
        total_in = 0
        total_out = 0
        
        for mov in movements[:25]:
            amount = float(mov.get("value", 0) or mov.get("amount", 0) or mov.get("monto", 0))
            mov_type = mov.get("type", "") or mov.get("tipo", "") or mov.get("concept", "")
            date = mov.get("created_at", "") or mov.get("date", "") or mov.get("fecha", "")
            order_id = mov.get("order_id", "") or mov.get("orden", "")
            
            if amount >= 0:
                total_in += amount
                emoji = "💵"
            else:
                total_out += abs(amount)
                emoji = "💸"
            
            result_text += f"{emoji} ${abs(amount):,.2f} | {mov_type}"
            if order_id:
                result_text += f" | Orden #{order_id}"
            if date:
                result_text += f" | {str(date)[:10]}"
            result_text += "\n"
        
        result_text += f"\n📈 RESUMEN:\n"
        result_text += f"   💵 Entradas: ${total_in:,.2f}\n"
        result_text += f"   💸 Salidas: ${total_out:,.2f}\n"
        result_text += f"   📊 Neto: ${total_in - total_out:,.2f}"
        
        return result_text
    
    return f"❌ Error obteniendo historial: {result.get('error')}"

async def get_dropi_orders(args: dict) -> str:
    """Obtiene las órdenes."""
    limit = args.get("limit", 50)
    
    # Probar el endpoint de órdenes v2
    params = {
        "exportAs": "orderByRow",
        "orderBy": "id",
        "orderDirection": "desc",
        "results": limit,
        "user_id": USER_ID
    }
    
    result = await dropi_get("/api/v2", params)
    
    if not result.get("success"):
        # Intentar endpoint alternativo
        result = await dropi_get(f"/api/orders", {"user_id": USER_ID, "limit": limit})
    
    if not result.get("success"):
        # Otro intento
        result = await dropi_get(f"/api/users/{USER_ID}/orders", {"limit": limit})
    
    if result.get("success"):
        data = result.get("data", {})
        orders = data if isinstance(data, list) else data.get("data", []) or data.get("orders", [])
        
        if not orders:
            return "📦 No hay órdenes registradas."
        
        result_text = f"📦 ÓRDENES DROPI ({len(orders)} encontradas):\n\n"
        stats = {}
        total_value = 0
        
        for order in orders[:20]:
            order_id = order.get("id") or order.get("order_id") or "N/A"
            status = order.get("status") or order.get("estado") or order.get("state", "?")
            if isinstance(status, dict):
                status = status.get("name", "?")
            customer = order.get("customer_name") or order.get("client_name") or order.get("nombre") or "Cliente"
            amount = float(order.get("total") or order.get("value") or order.get("amount") or 0)
            product = order.get("product_name") or order.get("producto") or ""
            
            stats[status] = stats.get(status, 0) + 1
            total_value += amount
            
            result_text += f"📌 #{order_id} | {customer[:25]}\n"
            result_text += f"   💵 ${amount:,.2f} | 📊 {status}\n"
            if product:
                result_text += f"   📦 {product[:35]}\n"
            result_text += "\n"
        
        result_text += f"📊 POR ESTADO:\n"
        for st, count in stats.items():
            result_text += f"   • {st}: {count}\n"
        result_text += f"\n💰 Total: ${total_value:,.2f}"
        
        return result_text
    
    return f"❌ No se pudieron obtener órdenes: {result.get('error')}"

async def get_dropi_user_info(args: dict) -> str:
    """Info del usuario."""
    result = await dropi_get(f"/api/users/{USER_ID}")
    
    if result.get("success"):
        data = result.get("data", {})
        
        name = data.get("name") or data.get("nombre") or "N/A"
        email = data.get("email") or "N/A"
        phone = data.get("phone") or data.get("telefono") or "N/A"
        wallet = data.get("wallet") or data.get("balance") or data.get("saldo")
        
        result_text = f"""👤 USUARIO DROPI:

📛 Nombre: {name}
📧 Email: {email}
📱 Teléfono: {phone}
🆔 User ID: {USER_ID}
🌍 País: {DROPI_COUNTRY.upper()}
"""
        if wallet is not None:
            result_text += f"💰 Saldo: ${float(wallet):,.2f}\n"
        
        return result_text
    
    # Mostrar info del token
    payload = decode_jwt_payload(DROPI_TOKEN)
    return f"""👤 INFO DROPI:

🆔 User ID: {USER_ID}
🌍 País: {DROPI_COUNTRY.upper()}
🔗 API: {DROPI_API_URL}

📋 Token payload:
{json.dumps(payload, indent=2)[:800]}

❌ Error consultando API: {result.get('error')}"""

async def get_dropi_billing_status(args: dict) -> str:
    """Estado de billing."""
    result = await dropi_get("/api/users/billing/status")
    
    if result.get("success"):
        return f"""💳 ESTADO DE BILLING DROPI:

{json.dumps(result.get('data', {}), indent=2, ensure_ascii=False)[:2000]}"""
    
    return f"❌ Error: {result.get('error')}"

async def debug_dropi_endpoint(args: dict) -> str:
    """Debug de endpoint."""
    endpoint = args.get("endpoint", "/api/users/billing/status")
    
    result = await dropi_get(endpoint)
    
    return f"""🔧 DEBUG DROPI:

📡 Endpoint: {endpoint}
🔗 URL completa: {DROPI_API_URL}{endpoint if endpoint.startswith('/') else '/' + endpoint}
✅ Success: {result.get('success', False)}
❌ Error: {result.get('error', 'None')}

📄 Respuesta:
{json.dumps(result.get('data', {}), indent=2, ensure_ascii=False)[:2500] if result.get('success') else 'N/A'}"""

# ==============================================================================
# DISPATCHER
# ==============================================================================

TOOL_HANDLERS = {
    "get_dropi_wallet": get_dropi_wallet,
    "get_dropi_wallet_history": get_dropi_wallet_history,
    "get_dropi_orders": get_dropi_orders,
    "get_dropi_user_info": get_dropi_user_info,
    "get_dropi_billing_status": get_dropi_billing_status,
    "debug_dropi_endpoint": debug_dropi_endpoint,
}

async def execute_tool(name: str, args: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler:
        try:
            return await handler(args)
        except Exception as e:
            return f"Error: {str(e)}"
    return f"Tool '{name}' not found"

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
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "dropi-mcp", "version": "4.0.0"}}}
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
        "version": "4.0.0",
        "api_url": DROPI_API_URL,
        "app_url": DROPI_APP_URL,
        "country": DROPI_COUNTRY.upper(),
        "user_id": USER_ID,
        "token_ok": bool(DROPI_TOKEN)
    })

async def discover(request):
    """Test endpoints."""
    endpoints = [
        "/api/users/billing/status",
        f"/api/users/{USER_ID}",
        "/api/historywallet",
        "/api/v2",
        "/api/orders"
    ]
    results = {"working": [], "failed": []}
    for ep in endpoints:
        r = await dropi_get(ep)
        if r.get("success"):
            results["working"].append({"endpoint": ep, "preview": str(r.get("data", {}))[:200]})
        else:
            results["failed"].append({"endpoint": ep, "error": r.get("error")})
    return JSONResponse({"api_url": DROPI_API_URL, "user_id": USER_ID, "results": results})

# ==============================================================================
# APP
# ==============================================================================

app = Starlette(routes=[
    Route("/", health),
    Route("/health", health),
    Route("/discover", discover),
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 Dropi MCP Server v4.0 FINAL")
    print(f"🌍 País: {DROPI_COUNTRY.upper()}")
    print(f"🔗 API URL: {DROPI_API_URL}")
    print(f"🔗 App URL: {DROPI_APP_URL}")
    print(f"👤 User ID: {USER_ID}")
    print(f"🔑 Token: {'✅' if DROPI_TOKEN else '❌'}")
    uvicorn.run(app, host="0.0.0.0", port=port)