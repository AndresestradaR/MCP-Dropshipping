"""
Servidor MCP para Dropi - v5.2 WALLET FIX
Basado en v5.0 + historial wallet corregido + filtrado local por fecha
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

# white_brand_id varía por país:
# - Guatemala: 1 (número)
# - Colombia: "df3e6b0bb66ceaadca4f84cbc371fd66e04d20fe51fc414da8d1b84d31d178de" (hash)
WHITE_BRAND_IDS = {
    "gt": 1,
    "co": "df3e6b0bb66ceaadca4f84cbc371fd66e04d20fe51fc414da8d1b84d31d178de",
}
WHITE_BRAND_ID = WHITE_BRAND_IDS.get(DROPI_COUNTRY, 1)

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
        "white_brand_id": WHITE_BRAND_ID,
        "brand": "",
        "otp": None,
        "with_cdc": False
    }
    
    headers = {
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
    """Headers con el token de autenticación y headers de navegador."""
    return {
        "Authorization": f"Bearer {current_token}" if current_token else "",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.dropi.gt",
        "Referer": "https://app.dropi.gt/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
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
        "description": "Historial de movimientos de la cartera: entradas y salidas con montos reales. Usar start_date y end_date para fechas especificas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Ultimos X dias (default 30)"},
                "type": {"type": "string", "description": "ENTRADA o SALIDA (opcional)"},
                "start_date": {"type": "string", "description": "Fecha inicio YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Fecha fin YYYY-MM-DD"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_orders",
        "description": "Lista ordenes de Dropi con estados, valores y CALCULA GANANCIAS. Usar start_date y end_date para dias especificos como ayer o hoy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de resultados (default 100)"},
                "status": {"type": "string", "description": "Filtrar por estado"},
                "days": {"type": "integer", "description": "Ultimos X dias"},
                "start_date": {"type": "string", "description": "Fecha inicio YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Fecha fin YYYY-MM-DD"}
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
    mov_type = args.get("type")  # ENTRADA o SALIDA
    
    # Priorizar fechas especificas
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    
    if start_date and end_date:
        date_from = start_date
        date_to = end_date
        period_label = start_date if start_date == end_date else f"{start_date} a {end_date}"
    else:
        days = args.get("days", 30)
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        period_label = f"ultimos {days} dias"
    
    # Asegurar que tenemos user_id
    if not current_user:
        await dropi_login()
    
    user_id = current_user.get("id") if current_user else None
    
    # Parametros exactos del navegador
    params = {
        "orderBy": "id",
        "orderDirection": "desc",
        "result_number": 100,
        "start": 0,
        "textToSearch": "",
        "type": mov_type if mov_type else "null",
        "id": "null",
        "identification_code": "null",
        "user_id": user_id,
        "from": date_from,
        "until": date_to,
        "wallet_id": 0
    }
    
    result = await dropi_get("/api/historywallet", params)
    
    if not result.get("success"):
        json_data = {"total_income": 0, "total_expenses": 0, "net": 0, "count": 0, "period": period_label}
        return f"Error obteniendo historial: {result.get('error')}\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    data = result.get("data", {})
    movements = data.get("objects", []) if isinstance(data, dict) else []
    count = data.get("count", len(movements))
    
    # Filtrar por fecha localmente si es necesario
    if start_date and end_date:
        filtered = []
        for mov in movements:
            mov_date = str(mov.get("created_at", ""))[:10]
            if start_date <= mov_date <= end_date:
                filtered.append(mov)
        movements = filtered
        count = len(movements)
    
    if not movements:
        json_data = {"total_income": 0, "total_expenses": 0, "net": 0, "count": 0, "period": period_label}
        return f"No hay movimientos en {period_label}.\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    result_text = f"HISTORIAL CARTERA ({period_label})\n"
    result_text += f"Total movimientos: {count}\n\n"
    
    total_in = 0
    total_out = 0
    entries = []
    exits = []
    
    for mov in movements:
        # El campo es "amount" no "value"
        amount = float(mov.get("amount", 0) or 0)
        mov_type_item = mov.get("type", "")
        date = str(mov.get("created_at", ""))[:10]
        order_id = mov.get("order_id", "")
        description = mov.get("description", "")
        
        if mov_type_item == "ENTRADA":
            total_in += amount
            entries.append({"order_id": order_id, "amount": amount, "date": date})
            result_text += f"+ Q{amount:,.2f} | ENTRADA"
        else:
            total_out += amount
            exits.append({"order_id": order_id, "amount": amount, "date": date})
            result_text += f"- Q{amount:,.2f} | SALIDA"
        
        if order_id:
            result_text += f" | Orden #{order_id}"
        result_text += f" | {date}\n"
    
    net = total_in - total_out
    
    result_text += f"\nRESUMEN:\n"
    result_text += f"  Entradas: Q{total_in:,.2f} ({len(entries)} movimientos)\n"
    result_text += f"  Salidas: Q{total_out:,.2f} ({len(exits)} movimientos)\n"
    result_text += f"  Neto: Q{net:,.2f}"
    
    # JSON para dashboard
    json_data = {
        "total_income": round(total_in, 2),
        "total_expenses": round(total_out, 2),
        "net": round(net, 2),
        "count": count,
        "entries": entries[:20],
        "exits": exits[:20],
        "period": period_label
    }
    
    return f"{result_text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"

async def get_dropi_orders(args: dict) -> str:
    """Obtiene las ordenes con calculo de ganancias."""
    limit = args.get("limit", 100)
    status_filter = args.get("status")
    
    # Priorizar fechas especificas sobre days
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    
    filter_locally = False
    local_start = None
    local_end = None
    
    if start_date and end_date:
        filter_locally = True
        local_start = start_date
        local_end = end_date
        period_label = start_date if start_date == end_date else f"{start_date} a {end_date}"
        # Pedir mas ordenes para filtrar localmente
        date_from = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
    else:
        days = args.get("days", 30)
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now().strftime("%Y-%m-%d")
        period_label = f"ultimos {days} dias"
    
    params = {
        "result_number": 200 if filter_locally else limit,
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
        json_data = {"total_orders": 0, "delivered": 0, "returned": 0, "net_profit": 0, "period": period_label}
        return f"Error: {result.get('error')}\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    data = result.get("data", {})
    orders = data.get("objects", []) if isinstance(data, dict) else []
    
    # Filtrado local por fecha
    if filter_locally and orders:
        filtered = []
        for order in orders:
            order_date = str(order.get("created_at", ""))[:10]
            if local_start <= order_date <= local_end:
                filtered.append(order)
        orders = filtered
    
    count = len(orders)
    
    if not orders:
        json_data = {"total_orders": 0, "delivered": 0, "returned": 0, "net_profit": 0, "period": period_label}
        return f"No hay ordenes en {period_label}.\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    # Contadores
    stats = {}
    total_value = 0
    delivered_count = 0
    delivered_profit = 0
    returned_count = 0
    return_cost = 23.0
    pending_count = 0
    pending_profit = 0
    cancelled_count = 0
    
    delivered_orders = []
    returned_orders = []
    
    for order in orders:
        status = order.get("status", "?")
        amount = float(order.get("total_order", 0) or 0)
        profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
        order_id = order.get("id")
        
        stats[status] = stats.get(status, 0) + 1
        total_value += amount
        
        status_lower = (status or "").lower()
        
        if status_lower in ["entregado", "delivered", "completado"]:
            delivered_count += 1
            delivered_profit += profit
            delivered_orders.append({"id": order_id, "profit": profit})
        elif status_lower in ["devolucion", "devuelto", "returned"]:
            returned_count += 1
            returned_orders.append({"id": order_id})
        elif status_lower in ["cancelado", "cancelled"]:
            cancelled_count += 1
        else:
            pending_count += 1
            pending_profit += profit
    
    total_return_cost = returned_count * return_cost
    net_profit = delivered_profit - total_return_cost
    
    # Texto para WhatsApp
    is_single_day = filter_locally and local_start == local_end
    
    result_text = f"ORDENES DROPI ({period_label})\n"
    result_text += f"Total: {count} ordenes\n\n"
    
    if is_single_day:
        # Formato detallado para un dia
        result_text += "ENTRADAS (Entregas):\n"
        for o in delivered_orders[:15]:
            result_text += f"  Orden #{o['id']} - Q{o['profit']:,.2f}\n"
        if not delivered_orders:
            result_text += "  (Ninguna)\n"
        
        result_text += "\nSALIDAS (Devoluciones Q23 c/u):\n"
        for o in returned_orders[:15]:
            result_text += f"  Orden #{o['id']} - Q{return_cost:.2f}\n"
        if not returned_orders:
            result_text += "  (Ninguna)\n"
        result_text += "\n"
    else:
        # Formato resumido
        for order in orders[:10]:
            oid = order.get("id")
            st = order.get("status", "?")
            profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
            result_text += f"#{oid} | {st} | Q{profit:,.2f}\n"
        if len(orders) > 10:
            result_text += f"... y {len(orders) - 10} mas\n"
        result_text += "\n"
    
    result_text += f"POR ESTADO:\n"
    for st, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        result_text += f"  {st}: {cnt}\n"
    
    result_text += f"\nRESUMEN FINANCIERO:\n"
    result_text += f"  Entregados: {delivered_count} (Ganancia: Q{delivered_profit:,.2f})\n"
    result_text += f"  Devoluciones: {returned_count} (Costo: -Q{total_return_cost:,.2f})\n"
    result_text += f"  Pendientes: {pending_count} (Proyectado: Q{pending_profit:,.2f})\n"
    result_text += f"  Cancelados: {cancelled_count}\n"
    result_text += f"  GANANCIA NETA: Q{net_profit:,.2f}"
    
    # JSON para dashboard
    json_data = {
        "total_orders": count,
        "total_sales_value": round(total_value, 2),
        "delivered": delivered_count,
        "delivered_profit": round(delivered_profit, 2),
        "delivered_orders": delivered_orders[:20],
        "returned": returned_count,
        "return_cost_per_order": return_cost,
        "total_return_cost": round(total_return_cost, 2),
        "returned_orders": returned_orders[:20],
        "pending": pending_count,
        "pending_profit": round(pending_profit, 2),
        "cancelled": cancelled_count,
        "net_profit": round(net_profit, 2),
        "stats_by_status": stats,
        "period": period_label
    }
    
    return f"{result_text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"

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