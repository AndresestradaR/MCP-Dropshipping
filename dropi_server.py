"""
Servidor MCP para Dropi - v6.2 DEBUG
Headers completos + JSON estructurado + Fechas específicas + Debug wallet
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

WHITE_BRAND_IDS = {
    "gt": 1,
    "co": "df3e6b0bb66ceaadca4f84cbc371fd66e04d20fe51fc414da8d1b84d31d178de",
}
WHITE_BRAND_ID = WHITE_BRAND_IDS.get(DROPI_COUNTRY, 1)

API_URLS = {
    "gt": "https://api.dropi.gt",
    "co": "https://api.dropi.co",
    "mx": "https://api.dropi.mx",
    "cl": "https://api.dropi.cl",
    "pe": "https://api.dropi.pe",
    "ec": "https://api.dropi.ec",
}

DROPI_API_URL = API_URLS.get(DROPI_COUNTRY, "https://api.dropi.gt")

current_token = None
current_user = None
sessions = {}

# ==============================================================================
# LOGIN Y AUTENTICACIÓN - HEADERS COMPLETOS
# ==============================================================================

def get_browser_headers():
    """Headers completos que simulan un navegador real."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.dropi.gt",
        "Referer": "https://app.dropi.gt/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }

async def dropi_login() -> dict:
    """Hace login en Dropi y obtiene el token."""
    global current_token, current_user
    
    if not DROPI_EMAIL or not DROPI_PASSWORD:
        return {"success": False, "error": "Email o password no configurados"}
    
    url = f"{DROPI_API_URL}/api/login"
    payload = {
        "email": DROPI_EMAIL,
        "password": DROPI_PASSWORD,
        "white_brand_id": WHITE_BRAND_ID,
        "brand": "",
        "otp": None,
        "with_cdc": False
    }
    
    headers = get_browser_headers()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
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
    headers = get_browser_headers()
    if current_token:
        headers["Authorization"] = f"Bearer {current_token}"
    return headers

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
                if data.get("isSuccess", True):
                    return {"success": True, "data": data}
                else:
                    return {"success": False, "error": data.get("message", "Error desconocido")}
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
        "description": "Obtiene el saldo disponible en la billetera/cartera de Dropi.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_wallet_history",
        "description": "Historial de movimientos de la cartera: entradas, salidas, pagos. Puedes filtrar por días O por fechas específicas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Últimos X días (default 30). Ignorado si se usan start_date/end_date"},
                "type": {"type": "string", "description": "ENTRADA o SALIDA (opcional)"},
                "start_date": {"type": "string", "description": "Fecha inicio formato YYYY-MM-DD (ej: 2025-11-01)"},
                "end_date": {"type": "string", "description": "Fecha fin formato YYYY-MM-DD (ej: 2025-11-30)"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_orders",
        "description": "Lista las órdenes/pedidos de Dropi con estados y valores. Puedes filtrar por días O por fechas específicas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de resultados (default 100)"},
                "status": {"type": "string", "description": "Filtrar por estado"},
                "days": {"type": "integer", "description": "Últimos X días (default 30). Ignorado si se usan start_date/end_date"},
                "start_date": {"type": "string", "description": "Fecha inicio formato YYYY-MM-DD (ej: 2025-11-01)"},
                "end_date": {"type": "string", "description": "Fecha fin formato YYYY-MM-DD (ej: 2025-11-30)"}
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
                "order_id": {"type": "integer", "description": "ID de la orden"}
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
    if not current_user:
        login_result = await dropi_login()
        if not login_result.get("success"):
            return f"❌ Error: {login_result.get('error')}"
    
    user = current_user or {}
    wallet_amount = None
    
    # Buscar wallet amount en diferentes ubicaciones
    if isinstance(user.get("wallet"), dict):
        wallet_amount = user["wallet"].get("amount")
    
    wallets = user.get("wallets", [])
    if wallets and isinstance(wallets, list):
        for w in wallets:
            if w.get("amount"):
                wallet_amount = w.get("amount")
                break
    
    balance = float(wallet_amount) if wallet_amount else 0
    
    # Texto formateado para WhatsApp
    text = f"""💰 BILLETERA DROPI

💵 Saldo Disponible: Q{balance:,.2f}
👤 Usuario: {user.get('name', '')} {user.get('surname', '')}
📧 Email: {user.get('email', DROPI_EMAIL)}
🆔 ID: {user.get('id', 'N/A')}
🌍 País: {DROPI_COUNTRY.upper()}

✅ Conexión exitosa"""

    # JSON estructurado al final para el dashboard
    json_data = {
        "balance": balance,
        "user_id": user.get('id'),
        "user_name": f"{user.get('name', '')} {user.get('surname', '')}".strip(),
        "country": DROPI_COUNTRY.upper()
    }
    
    return f"{text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"


async def get_dropi_wallet_history(args: dict) -> str:
    """Historial de movimientos de cartera."""
    mov_type = args.get("type")
    
    # Priorizar fechas específicas sobre days
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    
    if start_date and end_date:
        date_from = start_date
        date_to = end_date
        period_label = f"{start_date} a {end_date}"
    else:
        days = args.get("days", 30)
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        period_label = f"últimos {days} días"
    
    # Asegurar que tenemos el user_id
    if not current_user:
        await dropi_login()
    
    user_id = current_user.get("id") if current_user else None
    
    # Parámetros según la documentación de Dropi
    params = {
        "result_number": 200,
        "start": 0,
        "from": date_from,
        "until": date_to,
        "orderBy": "id",
        "orderDirection": "desc"
    }
    
    # Agregar user_id si está disponible (puede ser requerido)
    if user_id:
        params["user_id"] = user_id
        params["dropshipper_id"] = user_id
    
    if mov_type:
        params["type"] = mov_type
    
    # Intentar primero con el endpoint principal
    result = await dropi_get("/api/historywallet", params)
    
    # Si falla, intentar endpoint alternativo
    if not result.get("success"):
        # Probar sin algunos parámetros que pueden causar el error
        params_simple = {
            "result_number": 200,
            "start": 0
        }
        result = await dropi_get("/api/historywallet", params_simple)
    
    if not result.get("success"):
        # Si sigue fallando, retornar datos vacíos pero válidos
        json_data = {"total_income": 0, "total_expenses": 0, "net": 0, "count": 0, "period": period_label, "error": result.get("error")}
        return f"⚠️ No se pudo obtener historial: {result.get('error', 'Error desconocido')}\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    data = result.get("data", {})
    movements = data.get("objects", []) if isinstance(data, dict) else []
    count = data.get("count", len(movements))
    
    # Filtrar movimientos por fecha si es necesario (filtro local)
    if start_date and end_date:
        filtered_movements = []
        for mov in movements:
            mov_date = str(mov.get("created_at", ""))[:10]
            if date_from <= mov_date <= date_to:
                filtered_movements.append(mov)
        movements = filtered_movements
        count = len(movements)
    
    if not movements:
        json_data = {"total_income": 0, "total_expenses": 0, "net": 0, "count": 0, "period": period_label}
        return f"📊 No hay movimientos en {period_label}.\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    text = f"📊 HISTORIAL CARTERA (últimos {days} días)\n"
    text += f"📈 Total movimientos: {count}\n\n"
    
    total_in = 0
    total_out = 0
    
    # Procesar TODOS los movimientos para totales precisos
    for mov in movements:
        value = float(mov.get("value", 0) or 0)
        mov_type_str = mov.get("type", "")
        
        if value >= 0 or mov_type_str == "ENTRADA":
            total_in += abs(value)
        else:
            total_out += abs(value)
    
    # Mostrar solo los primeros 20 en texto
    for mov in movements[:20]:
        value = float(mov.get("value", 0) or 0)
        mov_type_str = mov.get("type", "")
        date = str(mov.get("created_at", ""))[:10]
        order_id = mov.get("order_id", "")
        
        if value >= 0 or mov_type_str == "ENTRADA":
            emoji = "💵"
        else:
            emoji = "💸"
        
        text += f"{emoji} Q{abs(value):,.2f} | {mov_type_str}"
        if order_id:
            text += f" | Orden #{order_id}"
        if date:
            text += f" | {date}"
        text += "\n"
    
    text += f"\n📈 RESUMEN:\n"
    text += f"   💵 Entradas: Q{total_in:,.2f}\n"
    text += f"   💸 Salidas: Q{total_out:,.2f}\n"
    text += f"   📊 Neto: Q{total_in - total_out:,.2f}"
    
    # JSON estructurado
    json_data = {
        "total_income": round(total_in, 2),
        "total_expenses": round(total_out, 2),
        "net": round(total_in - total_out, 2),
        "count": count,
        "days": days
    }
    
    return f"{text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"


async def get_dropi_orders(args: dict) -> str:
    """Obtiene las órdenes."""
    limit = args.get("limit", 100)
    status_filter = args.get("status")
    
    # Priorizar fechas específicas sobre days
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    
    if start_date and end_date:
        # Usar fechas específicas
        date_from = start_date
        date_to = end_date
        period_label = f"{start_date} a {end_date}"
    else:
        # Usar days (default 30)
        days = args.get("days", 30)
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        period_label = f"últimos {days} días"
    
    params = {
        "result_number": limit,
        "start": 0,
        "from": date_from,
        "until": date_to,
        "orderBy": "id",
        "orderDirection": "desc",
        "filter_date_by": "FECHA DE CREADO"
    }
    if status_filter:
        params["status"] = status_filter
    
    result = await dropi_get("/api/orders/myorders", params)
    
    if not result.get("success"):
        json_data = {"total_orders": 0, "total_amount": 0, "delivered": 0, "returned": 0, "pending": 0, "period": period_label}
        return f"⚠️ Error obteniendo órdenes: {result.get('error', 'Error desconocido')}\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    data = result.get("data", {})
    orders = data.get("objects", []) if isinstance(data, dict) else []
    count = data.get("count", len(orders))
    
    if not orders:
        json_data = {"total_orders": 0, "total_amount": 0, "delivered": 0, "returned": 0, "pending": 0, "period": period_label}
        return f"📦 No hay órdenes en {period_label}.\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    text = f"📦 ÓRDENES DROPI ({period_label})\n"
    text += f"📈 Cantidad: {count} órdenes\n\n"
    
    stats = {}
    total_value = 0  # Valor total de ventas
    
    # Contadores por estado
    delivered_count = 0
    delivered_amount = 0  # Valor de ventas entregadas
    delivered_profit = 0  # GANANCIA REAL de entregadas (dropshipper_amount_to_win)
    
    returned_count = 0
    returned_amount = 0  # Valor de ventas devueltas
    return_cost_per_order = 23.0  # Costo que cobra Dropi por devolución
    
    pending_count = 0
    pending_amount = 0
    pending_profit = 0  # Ganancia proyectada de pendientes
    
    cancelled_count = 0  # Cancelados (no enviados, sin costo)
    
    # Procesar TODAS las órdenes para estadísticas
    for order in orders:
        status = order.get("status", "?")
        amount = float(order.get("total_order", 0) or 0)
        profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
        
        stats[status] = stats.get(status, 0) + 1
        total_value += amount
        
        # Clasificar por estado
        status_lower = status.lower() if status else ""
        
        if status_lower in ["entregado", "delivered", "completado", "completed"]:
            delivered_count += 1
            delivered_amount += amount
            delivered_profit += profit
            
        elif status_lower in ["devolucion", "devuelto", "returned"]:
            # Devoluciones = ya fueron enviadas pero volvieron (tienen costo)
            returned_count += 1
            returned_amount += amount
            
        elif status_lower in ["cancelado", "cancelled", "rechazado"]:
            # Cancelados = nunca se enviaron (sin costo de devolución)
            cancelled_count += 1
            
        else:
            # Pendiente, en camino, guia generada, recolectado, etc.
            pending_count += 1
            pending_amount += amount
            pending_profit += profit
    
    # Calcular ganancia neta
    total_return_cost = returned_count * return_cost_per_order
    net_profit = delivered_profit - total_return_cost
    projected_profit = net_profit + pending_profit  # Si se entregan todos los pendientes
    
    # Mostrar solo las primeras 15 órdenes en texto
    for order in orders[:15]:
        order_id = order.get("id", "N/A")
        status = order.get("status", "?")
        customer = f"{order.get('name', '')} {order.get('surname', '')}".strip() or "Cliente"
        amount = float(order.get("total_order", 0) or 0)
        city = order.get("city", "")
        date = str(order.get("created_at", ""))[:10]
        
        text += f"📌 #{order_id} | {customer[:20]}\n"
        text += f"   💵 Q{amount:,.2f} | 📊 {status}\n"
        if city:
            text += f"   📍 {city}"
        if date:
            text += f" | 📅 {date}"
        text += "\n\n"
    
    if len(orders) > 15:
        text += f"... y {len(orders) - 15} órdenes más\n\n"
    
    text += f"📊 POR ESTADO:\n"
    for st, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        text += f"   • {st}: {cnt}\n"
    
    text += f"\n💰 RESUMEN FINANCIERO:\n"
    text += f"   📦 Total pedidos: {count}\n"
    text += f"   💵 Valor total ventas: Q{total_value:,.2f}\n"
    text += f"\n   ✅ Entregados: {delivered_count}\n"
    text += f"      💰 Ganancia: Q{delivered_profit:,.2f}\n"
    text += f"\n   🔄 Devoluciones: {returned_count}\n"
    text += f"      💸 Costo (Q{return_cost_per_order:.0f} c/u): -Q{total_return_cost:,.2f}\n"
    text += f"\n   ⏳ Pendientes: {pending_count}\n"
    text += f"      💰 Ganancia proyectada: Q{pending_profit:,.2f}\n"
    text += f"\n   ❌ Cancelados: {cancelled_count} (sin costo)\n"
    text += f"\n{'='*30}\n"
    text += f"   💵 GANANCIA NETA: Q{net_profit:,.2f}\n"
    text += f"   📈 Proyectado (si entregan pendientes): Q{projected_profit:,.2f}"
    
    # JSON estructurado para el dashboard y el bot
    json_data = {
        "total_orders": count,
        "total_sales_value": round(total_value, 2),
        
        "delivered": delivered_count,
        "delivered_sales": round(delivered_amount, 2),
        "delivered_profit": round(delivered_profit, 2),
        
        "returned": returned_count,
        "return_cost_per_order": return_cost_per_order,
        "total_return_cost": round(total_return_cost, 2),
        
        "pending": pending_count,
        "pending_sales": round(pending_amount, 2),
        "pending_profit": round(pending_profit, 2),
        
        "cancelled": cancelled_count,
        
        "net_profit": round(net_profit, 2),
        "projected_profit": round(projected_profit, 2),
        
        "stats_by_status": stats,
        "period": period_label
    }
    
    return f"{text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"


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
    
    text = f"""📦 ORDEN #{order.get('id')}

👤 Cliente: {order.get('name', '')} {order.get('surname', '')}
📱 Teléfono: {order.get('phone', 'N/A')}
📍 Dirección: {order.get('dir', 'N/A')}
🏙️ Ciudad: {order.get('city', 'N/A')}, {order.get('state', '')}

💵 Total: Q{float(order.get('total_order', 0)):,.2f}
🚚 Envío: Q{float(order.get('shipping_amount', 0)):,.2f}
💰 Ganancia: Q{float(order.get('dropshipper_amount_to_win', 0)):,.2f}

📊 Estado: {order.get('status', 'N/A')}
🚚 Guía: {order.get('shipping_guide', 'Sin guía')}
🚛 Transportadora: {order.get('shipping_company', 'N/A')}

📅 Creado: {str(order.get('created_at', ''))[:19]}"""
    
    details = order.get("orderdetails", [])
    if details:
        text += "\n\n📦 PRODUCTOS:\n"
        for d in details:
            product = d.get("product", {})
            text += f"   • {product.get('name', 'Producto')} x{d.get('quantity', 1)} = Q{float(d.get('price', 0)):,.2f}\n"
    
    json_data = {
        "order_id": order.get('id'),
        "status": order.get('status'),
        "total": float(order.get('total_order', 0)),
        "shipping": float(order.get('shipping_amount', 0)),
        "profit": float(order.get('dropshipper_amount_to_win', 0))
    }
    
    return f"{text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"


async def get_dropi_user_info(args: dict) -> str:
    """Info del usuario."""
    if not current_user:
        login_result = await dropi_login()
        if not login_result.get("success"):
            return f"❌ Error: {login_result.get('error')}"
    
    user = current_user or {}
    
    text = f"""👤 USUARIO DROPI

📛 Nombre: {user.get('name', '')} {user.get('surname', '')}
📧 Email: {user.get('email', DROPI_EMAIL)}
📱 Teléfono: {user.get('phone', 'N/A')}
🆔 ID: {user.get('id', 'N/A')}
🌍 País: {DROPI_COUNTRY.upper()}

✅ Autenticado correctamente"""
    
    json_data = {
        "user_id": user.get('id'),
        "name": f"{user.get('name', '')} {user.get('surname', '')}".strip(),
        "email": user.get('email', DROPI_EMAIL),
        "country": DROPI_COUNTRY.upper()
    }
    
    return f"{text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"


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
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "dropi-mcp", "version": "6.2.0"}}}
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
        "version": "6.2.0",
        "api_url": DROPI_API_URL,
        "country": DROPI_COUNTRY.upper(),
        "email_configured": bool(DROPI_EMAIL),
        "authenticated": bool(current_token)
    })

async def login_endpoint(request):
    result = await dropi_login()
    return JSONResponse(result)

async def debug_wallet(request):
    """Endpoint de debug para investigar el historial de wallet."""
    results = {
        "login": None,
        "user_id": None,
        "tests": []
    }
    
    # Paso 1: Login
    login_result = await dropi_login()
    results["login"] = "✅" if login_result.get("success") else f"❌ {login_result.get('error')}"
    results["user_id"] = current_user.get("id") if current_user else None
    
    if not login_result.get("success"):
        return JSONResponse(results)
    
    # Paso 2: Probar diferentes configuraciones
    test_configs = [
        {
            "name": "Sin parámetros",
            "params": {}
        },
        {
            "name": "Solo result_number",
            "params": {"result_number": 10, "start": 0}
        },
        {
            "name": "Con fechas simples",
            "params": {
                "result_number": 10,
                "start": 0,
                "from": "2025-12-01",
                "until": "2025-12-06"
            }
        },
        {
            "name": "Con user_id",
            "params": {
                "result_number": 10,
                "start": 0,
                "user_id": current_user.get("id") if current_user else None
            }
        },
        {
            "name": "Con dropshipper_id",
            "params": {
                "result_number": 10,
                "start": 0,
                "dropshipper_id": current_user.get("id") if current_user else None
            }
        }
    ]
    
    for config in test_configs:
        test_result = {
            "name": config["name"],
            "params": config["params"],
            "status": None,
            "count": 0,
            "sample": None,
            "error": None
        }
        
        try:
            result = await dropi_get("/api/historywallet", config["params"])
            
            if result.get("success"):
                data = result.get("data", {})
                objects = data.get("objects", []) if isinstance(data, dict) else []
                test_result["status"] = "✅"
                test_result["count"] = len(objects)
                if objects:
                    # Muestra el primer movimiento como ejemplo
                    first = objects[0]
                    test_result["sample"] = {
                        "id": first.get("id"),
                        "type": first.get("type"),
                        "value": first.get("value"),
                        "created_at": str(first.get("created_at", ""))[:19],
                        "order_id": first.get("order_id")
                    }
            else:
                test_result["status"] = "❌"
                test_result["error"] = result.get("error")
        except Exception as e:
            test_result["status"] = "❌"
            test_result["error"] = str(e)
        
        results["tests"].append(test_result)
    
    return JSONResponse(results)


async def debug_orders(request):
    """Endpoint de debug para ver los campos de las órdenes."""
    results = {
        "login": None,
        "orders_count": 0,
        "sample_delivered": None,
        "sample_returned": None,
        "sample_pending": None,
        "all_fields": []
    }
    
    # Login
    login_result = await dropi_login()
    results["login"] = "✅" if login_result.get("success") else f"❌ {login_result.get('error')}"
    
    if not login_result.get("success"):
        return JSONResponse(results)
    
    # Obtener órdenes recientes
    params = {
        "result_number": 50,
        "start": 0,
        "orderBy": "id",
        "orderDirection": "desc"
    }
    
    result = await dropi_get("/api/orders/myorders", params)
    
    if not result.get("success"):
        results["error"] = result.get("error")
        return JSONResponse(results)
    
    data = result.get("data", {})
    orders = data.get("objects", []) if isinstance(data, dict) else []
    results["orders_count"] = len(orders)
    
    # Encontrar una orden de cada tipo
    for order in orders:
        status = (order.get("status", "") or "").lower()
        
        # Campos importantes para el cálculo financiero
        sample = {
            "id": order.get("id"),
            "status": order.get("status"),
            "total_order": order.get("total_order"),
            "dropshipper_amount_to_win": order.get("dropshipper_amount_to_win"),
            "shipping_amount": order.get("shipping_amount"),
            "product_cost": order.get("product_cost"),
            "profit": order.get("profit"),
            "commission": order.get("commission"),
            "created_at": str(order.get("created_at", ""))[:10]
        }
        
        if status == "entregado" and not results["sample_delivered"]:
            results["sample_delivered"] = sample
        elif status in ["devolucion", "devuelto"] and not results["sample_returned"]:
            results["sample_returned"] = sample
        elif status not in ["entregado", "devolucion", "devuelto", "cancelado"] and not results["sample_pending"]:
            results["sample_pending"] = sample
    
    # Mostrar todos los campos de la primera orden
    if orders:
        results["all_fields"] = list(orders[0].keys())
    
    return JSONResponse(results)

async def discover(request):
    login_result = await dropi_login()
    
    if not login_result.get("success"):
        return JSONResponse({
            "success": False,
            "error": login_result.get("error"),
            "config": {
                "api_url": DROPI_API_URL,
                "email": DROPI_EMAIL[:3] + "***" if DROPI_EMAIL else "NOT SET"
            }
        })
    
    tests = {}
    
    # Test historial - puede fallar con 500, no es crítico
    r = await dropi_get("/api/historywallet", {"result_number": 1})
    tests["historywallet"] = "✅" if r.get("success") else f"❌ {r.get('error', 'Error')}"
    
    # Test órdenes
    r = await dropi_get("/api/orders/myorders", {"result_number": 1})
    tests["orders"] = "✅" if r.get("success") else f"❌ {r.get('error', 'Error')}"
    
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
    Route("/debug-wallet", debug_wallet),
    Route("/debug-orders", debug_orders),
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 Dropi MCP Server v6.2 - DEBUG")
    print(f"🌍 País: {DROPI_COUNTRY.upper()}")
    print(f"🔗 API: {DROPI_API_URL}")
    print(f"📧 Email: {DROPI_EMAIL[:3]}***" if DROPI_EMAIL else "📧 Email: NOT SET")
    print(f"🔍 Debug: /debug-wallet")
    uvicorn.run(app, host="0.0.0.0", port=port)