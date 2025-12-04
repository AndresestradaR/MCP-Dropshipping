"""
Servidor MCP para Dropi - v3.0 CON ENDPOINTS REALES
Endpoints descubiertos via DevTools de app.dropi.gt
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

# URLs por país - La app usa app.dropi.XX para la UI y parece usar la misma para API
DROPI_DOMAINS = {
    "gt": "https://app.dropi.gt",
    "co": "https://app.dropi.co", 
    "mx": "https://app.dropi.mx",
    "cl": "https://app.dropi.cl",
    "pe": "https://app.dropi.pe",
    "ec": "https://app.dropi.ec",
}

DROPI_BASE_URL = os.getenv("DROPI_API_URL", DROPI_DOMAINS.get(DROPI_COUNTRY, "https://app.dropi.gt"))

sessions = {}

# ==============================================================================
# CLIENTE HTTP PARA DROPI
# ==============================================================================

def get_headers():
    """Headers para la API de Dropi - Simula el navegador."""
    return {
        "Authorization": f"Bearer {DROPI_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": DROPI_BASE_URL,
        "Referer": f"{DROPI_BASE_URL}/dashboard/orders",
    }

async def dropi_request(method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
    """Request genérico a la API de Dropi."""
    # Construir URL - los endpoints van directo después del dominio
    if endpoint.startswith("http"):
        url = endpoint
    elif endpoint.startswith("/"):
        url = f"{DROPI_BASE_URL}{endpoint}"
    else:
        url = f"{DROPI_BASE_URL}/{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=get_headers(), params=params)
            else:
                response = await client.post(url, headers=get_headers(), json=data or {}, params=params)
            
            # Debug info
            content_type = response.headers.get("content-type", "")
            
            if response.status_code == 200:
                if "application/json" in content_type:
                    return {"success": True, "data": response.json()}
                else:
                    # Puede ser HTML - intentar parsear como JSON de todos modos
                    try:
                        return {"success": True, "data": response.json()}
                    except:
                        # Es HTML, extraer info si es posible
                        text = response.text[:500]
                        return {"success": False, "error": "Response is HTML, not JSON", "preview": text}
            elif response.status_code == 401:
                return {"success": False, "error": "Token inválido o expirado"}
            elif response.status_code == 403:
                return {"success": False, "error": "Acceso denegado"}
            elif response.status_code == 404:
                return {"success": False, "error": f"Endpoint no encontrado: {endpoint}"}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}", "body": response.text[:200]}
                
        except httpx.TimeoutException:
            return {"success": False, "error": "Timeout conectando a Dropi"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

async def dropi_get(endpoint: str, params: dict = None) -> dict:
    return await dropi_request("GET", endpoint, params=params)

async def dropi_post(endpoint: str, data: dict = None, params: dict = None) -> dict:
    return await dropi_request("POST", endpoint, params=params, data=data)

# ==============================================================================
# FUNCIONES PARA EXTRAER USER_ID DEL TOKEN
# ==============================================================================

def decode_jwt_payload(token: str) -> dict:
    """Decodifica el payload de un JWT sin verificar firma."""
    try:
        import base64
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        
        # Decodificar payload (parte 2)
        payload = parts[1]
        # Agregar padding si es necesario
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        return {"error": str(e)}

def get_user_id_from_token() -> str:
    """Extrae el user_id del token JWT."""
    if not DROPI_TOKEN:
        return ""
    
    payload = decode_jwt_payload(DROPI_TOKEN)
    # El user_id puede estar en diferentes campos
    user_id = payload.get("sub") or payload.get("user_id") or payload.get("id") or payload.get("userId")
    return str(user_id) if user_id else ""

# ==============================================================================
# HERRAMIENTAS DISPONIBLES
# ==============================================================================

TOOLS = [
    {
        "name": "get_dropi_wallet",
        "description": "Consulta el saldo disponible en la billetera/wallet de Dropi. Muestra saldo actual y disponible.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_wallet_history",
        "description": "Historial de movimientos de la billetera de Dropi: entradas, salidas, pagos recibidos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Historial de los últimos X días (default 30)"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_orders",
        "description": "Obtiene las órdenes/pedidos de Dropi con sus estados y valores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de órdenes (default 50)"},
                "status": {"type": "string", "description": "Filtrar por estado si es posible"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_order_stats",
        "description": "Estadísticas de órdenes: entregadas, pendientes, devueltas, canceladas.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_dropi_user_info",
        "description": "Información del usuario de Dropi: datos de cuenta, credenciales, estado.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_statuses",
        "description": "Lista los estados disponibles para órdenes en Dropi según el país.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "debug_dropi_api",
        "description": "Herramienta de debug para probar endpoints específicos de la API de Dropi.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint": {"type": "string", "description": "Endpoint a probar (ej: status, 424, credentials)"}
            },
            "required": ["endpoint"]
        }
    }
]

# ==============================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# ==============================================================================

async def get_dropi_wallet(args: dict) -> str:
    """Consulta el saldo de la billetera."""
    user_id = get_user_id_from_token()
    
    # Probar varios endpoints posibles para wallet
    endpoints_to_try = [
        f"status",  # Endpoint que vimos en DevTools
        f"consultconstantshistorywallets",
        f"wallet/balance",
        f"api/wallet",
        f"api/v1/wallet",
        f"api/user/wallet",
    ]
    
    results = []
    for endpoint in endpoints_to_try:
        result = await dropi_get(endpoint)
        if result.get("success"):
            data = result.get("data", {})
            results.append({"endpoint": endpoint, "data": data})
    
    if results:
        # Intentar extraer balance de los resultados
        for r in results:
            data = r["data"]
            if isinstance(data, dict):
                # Buscar campos comunes de balance
                balance = data.get("balance") or data.get("saldo") or data.get("available") or data.get("wallet")
                if balance is not None:
                    return f"""💰 BILLETERA DROPI:

💵 Saldo: ${float(balance):,.2f}
📊 Endpoint: {r['endpoint']}

✅ Conexión exitosa con Dropi"""
        
        # Si no encontramos balance específico, mostrar lo que encontramos
        return f"""💰 BILLETERA DROPI:

📊 Datos encontrados en {len(results)} endpoints:

{json.dumps(results[0]['data'], indent=2, ensure_ascii=False)[:1000]}

💡 Los datos están disponibles pero el formato puede variar."""
    
    # Si nada funcionó, dar info de debug
    return f"""❌ No se pudo obtener el saldo de la billetera.

🔍 Info de debug:
- Base URL: {DROPI_BASE_URL}
- User ID del token: {user_id or 'No detectado'}
- Token configurado: {'Sí' if DROPI_TOKEN else 'No'}

💡 La API de Dropi puede requerir endpoints específicos.
Usa la herramienta 'debug_dropi_api' para probar endpoints manualmente."""

async def get_dropi_wallet_history(args: dict) -> str:
    """Historial de la billetera."""
    user_id = get_user_id_from_token()
    days = args.get("days", 30)
    
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")
    
    # Endpoint visto en DevTools: historywallet?orderBy=id&orderDirection=desc&resul...=424&from=...
    params = {
        "orderBy": "id",
        "orderDirection": "desc",
        "user_id": user_id,
        "from": date_from,
        "to": date_to,
        "results": 50
    }
    
    result = await dropi_get("historywallet", params)
    
    if result.get("success"):
        data = result.get("data", {})
        
        # Puede ser una lista o un objeto con data
        movements = data if isinstance(data, list) else data.get("data", [])
        
        if not movements:
            return f"📊 No hay movimientos en los últimos {days} días."
        
        total_in = 0
        total_out = 0
        result_text = f"📊 HISTORIAL DE BILLETERA (últimos {days} días):\n\n"
        
        for mov in movements[:20]:
            amount = float(mov.get("amount", 0) or mov.get("value", 0) or 0)
            mov_type = mov.get("type", "") or mov.get("tipo", "") or "?"
            date = mov.get("created_at", "") or mov.get("date", "")
            description = mov.get("description", "") or mov.get("concept", "") or ""
            
            if amount > 0:
                total_in += amount
                emoji = "💵"
            else:
                total_out += abs(amount)
                emoji = "💸"
            
            result_text += f"{emoji} ${abs(amount):,.2f} | {mov_type} | {date[:10] if date else 'N/A'}\n"
            if description:
                result_text += f"   📝 {description[:50]}\n"
        
        result_text += f"\n📈 RESUMEN:\n"
        result_text += f"   Entradas: ${total_in:,.2f}\n"
        result_text += f"   Salidas: ${total_out:,.2f}\n"
        result_text += f"   Neto: ${total_in - total_out:,.2f}"
        
        return result_text
    
    return f"❌ No se pudo obtener el historial: {result.get('error', 'Error desconocido')}"

async def get_dropi_orders(args: dict) -> str:
    """Obtiene las órdenes."""
    user_id = get_user_id_from_token()
    limit = args.get("limit", 50)
    
    # Endpoint visto: v2?exportAs=orderByRow&orderBy=id&orderDirection=d...
    params = {
        "orderBy": "id",
        "orderDirection": "desc",
        "results": limit,
        "user_id": user_id,
    }
    
    # Probar varios endpoints
    endpoints = ["v2", "orders", "api/orders", "api/v1/orders", f"index/?user_id={user_id}"]
    
    for endpoint in endpoints:
        result = await dropi_get(endpoint, params if "v2" in endpoint or "orders" in endpoint else None)
        
        if result.get("success"):
            data = result.get("data", {})
            orders = data if isinstance(data, list) else data.get("data", []) or data.get("orders", [])
            
            if orders and isinstance(orders, list) and len(orders) > 0:
                result_text = f"📦 ÓRDENES DROPI ({len(orders)} encontradas):\n\n"
                
                # Contadores
                stats = {}
                total_value = 0
                
                for order in orders[:20]:
                    order_id = order.get("id") or order.get("order_id") or "N/A"
                    status = order.get("status") or order.get("estado") or order.get("state") or "?"
                    customer = order.get("customer_name") or order.get("client_name") or order.get("nombre") or "Sin nombre"
                    amount = float(order.get("total") or order.get("value") or order.get("amount") or 0)
                    product = order.get("product_name") or order.get("producto") or ""
                    
                    stats[status] = stats.get(status, 0) + 1
                    total_value += amount
                    
                    result_text += f"📌 #{order_id} | {customer[:20]}\n"
                    result_text += f"   💵 ${amount:,.2f} | 📊 {status}\n"
                    if product:
                        result_text += f"   📦 {product[:30]}\n"
                    result_text += "\n"
                
                result_text += f"📊 RESUMEN POR ESTADO:\n"
                for st, count in stats.items():
                    result_text += f"   • {st}: {count}\n"
                result_text += f"\n💰 Valor Total: ${total_value:,.2f}"
                
                return result_text
    
    return f"""❌ No se pudieron obtener las órdenes.

🔍 Endpoints probados: {', '.join(endpoints)}

💡 Usa 'debug_dropi_api' con endpoint 'v2' para ver la respuesta raw."""

async def get_dropi_order_stats(args: dict) -> str:
    """Estadísticas de órdenes."""
    # Primero obtener los estados disponibles
    statuses_result = await dropi_get("getStatusesByCountry", {"country": DROPI_COUNTRY.upper()})
    
    # Luego obtener órdenes para calcular stats
    orders_result = await get_dropi_orders({"limit": 200})
    
    return f"""📊 ESTADÍSTICAS DE ÓRDENES DROPI:

{orders_result}

🌍 País: {DROPI_COUNTRY.upper()}"""

async def get_dropi_user_info(args: dict) -> str:
    """Información del usuario."""
    user_id = get_user_id_from_token()
    
    # Decodificar token para info básica
    payload = decode_jwt_payload(DROPI_TOKEN)
    
    # Probar endpoint de credenciales
    creds_result = await dropi_get("credentials")
    
    result_text = f"""👤 INFORMACIÓN DE USUARIO DROPI:

🔑 Info del Token:
   User ID: {user_id or 'No detectado'}
   Payload: {json.dumps(payload, indent=2, ensure_ascii=False)[:500]}

🌍 Configuración:
   País: {DROPI_COUNTRY.upper()}
   Base URL: {DROPI_BASE_URL}
"""
    
    if creds_result.get("success"):
        result_text += f"\n📋 Credenciales:\n{json.dumps(creds_result.get('data', {}), indent=2, ensure_ascii=False)[:500]}"
    
    return result_text

async def get_dropi_statuses(args: dict) -> str:
    """Estados disponibles."""
    result = await dropi_get("getStatusesByCountry", {"country": DROPI_COUNTRY.upper()})
    
    if result.get("success"):
        data = result.get("data", {})
        statuses = data if isinstance(data, list) else data.get("data", []) or data.get("statuses", [])
        
        if statuses:
            result_text = f"📋 ESTADOS DISPONIBLES EN DROPI ({DROPI_COUNTRY.upper()}):\n\n"
            for status in statuses:
                if isinstance(status, dict):
                    name = status.get("name") or status.get("nombre") or str(status)
                    code = status.get("code") or status.get("id") or ""
                    result_text += f"   • {name} ({code})\n"
                else:
                    result_text += f"   • {status}\n"
            return result_text
    
    return f"❌ No se pudieron obtener los estados: {result.get('error', 'Error')}"

async def debug_dropi_api(args: dict) -> str:
    """Debug de API."""
    endpoint = args.get("endpoint", "status")
    
    result = await dropi_get(endpoint)
    
    return f"""🔧 DEBUG API DROPI:

📡 Endpoint: {endpoint}
🔗 URL: {DROPI_BASE_URL}/{endpoint}
✅ Success: {result.get('success', False)}

📄 Respuesta:
{json.dumps(result, indent=2, ensure_ascii=False)[:2000]}"""

# ==============================================================================
# DISPATCHER
# ==============================================================================

TOOL_HANDLERS = {
    "get_dropi_wallet": get_dropi_wallet,
    "get_dropi_wallet_history": get_dropi_wallet_history,
    "get_dropi_orders": get_dropi_orders,
    "get_dropi_order_stats": get_dropi_order_stats,
    "get_dropi_user_info": get_dropi_user_info,
    "get_dropi_statuses": get_dropi_statuses,
    "debug_dropi_api": debug_dropi_api,
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
    name = body.get("name", "")
    args = body.get("arguments", {})
    result = await execute_tool(name, args)
    return JSONResponse({"result": result})

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
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dropi-mcp", "version": "3.0.0"}
            }
        }
    elif method == "tools/list":
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        result = await execute_tool(name, args)
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": result}]}
        }
    else:
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    
    if response and msg_id:
        await sessions[session_id].put(response)
    
    return Response("OK")

async def health(request):
    user_id = get_user_id_from_token()
    return JSONResponse({
        "status": "ok",
        "service": "dropi-mcp",
        "version": "3.0.0",
        "country": DROPI_COUNTRY.upper(),
        "base_url": DROPI_BASE_URL,
        "token_configured": bool(DROPI_TOKEN),
        "user_id_from_token": user_id
    })

async def discover_endpoints(request):
    """Endpoint de diagnóstico."""
    endpoints_to_test = [
        "status", "credentials", "424",
        "historywallet", "consultconstantshistorywallets",
        "v2", "orders", "index",
        "getStatusesByCountry?country=GT",
        "wallet", "balance",
        "api/wallet", "api/orders", "api/user"
    ]
    
    results = {"working": [], "failed": []}
    
    for endpoint in endpoints_to_test:
        result = await dropi_get(endpoint)
        if result.get("success"):
            results["working"].append({
                "endpoint": endpoint,
                "data_preview": str(result.get("data", {}))[:200]
            })
        else:
            results["failed"].append({
                "endpoint": endpoint,
                "error": result.get("error", "Unknown")
            })
    
    return JSONResponse({
        "dropi_base_url": DROPI_BASE_URL,
        "user_id": get_user_id_from_token(),
        "results": results,
        "summary": {
            "working": len(results["working"]),
            "failed": len(results["failed"])
        }
    })

# ==============================================================================
# APP
# ==============================================================================

app = Starlette(routes=[
    Route("/", health),
    Route("/health", health),
    Route("/discover", discover_endpoints),
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    user_id = get_user_id_from_token()
    print(f"🚀 Dropi MCP Server v3.0 iniciando en puerto {port}")
    print(f"🌍 País: {DROPI_COUNTRY.upper()}")
    print(f"🔗 Base URL: {DROPI_BASE_URL}")
    print(f"🔑 Token: {'Configurado' if DROPI_TOKEN else '❌ NO CONFIGURADO'}")
    print(f"👤 User ID: {user_id or 'No detectado en token'}")
    uvicorn.run(app, host="0.0.0.0", port=port)