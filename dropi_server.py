"""
Servidor MCP para Dropi - v2.0 CORREGIDO
Usa Starlette (igual que shopify_server.py y meta_server.py)
Para conectar la IA con logística, órdenes y billetera de Dropi.

Endpoints de Dropi Guatemala: https://app.dropi.gt/api/...
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
# Detectar el país basándose en el dominio configurado
DROPI_COUNTRY = os.getenv("DROPI_COUNTRY", "gt")  # gt, co, mx, etc.

# URLs por país
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
    """Headers para la API de Dropi."""
    return {
        "Authorization": f"Bearer {DROPI_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

async def dropi_get(endpoint: str, params: dict = None) -> dict:
    """GET request a la API de Dropi."""
    url = f"{DROPI_BASE_URL}/api/{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=get_headers(), params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                return {"error": "Token inválido o expirado. Verifica DROPI_TOKEN."}
            elif response.status_code == 403:
                return {"error": "Acceso denegado. Verifica permisos del token."}
            elif response.status_code == 404:
                return {"error": f"Endpoint no encontrado: {endpoint}"}
            else:
                return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
        except httpx.TimeoutException:
            return {"error": "Timeout conectando a Dropi"}
        except Exception as e:
            return {"error": f"Error de conexión: {str(e)}"}

async def dropi_post(endpoint: str, data: dict = None) -> dict:
    """POST request a la API de Dropi."""
    url = f"{DROPI_BASE_URL}/api/{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=get_headers(), json=data or {})
            
            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code == 401:
                return {"error": "Token inválido o expirado"}
            else:
                return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
        except Exception as e:
            return {"error": f"Error: {str(e)}"}

# ==============================================================================
# HERRAMIENTAS DISPONIBLES
# ==============================================================================

TOOLS = [
    {
        "name": "get_dropi_wallet",
        "description": "Consulta el saldo disponible en la billetera/wallet de Dropi. Muestra saldo actual, saldo pendiente y disponible para retiro.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_orders",
        "description": "Obtiene las órdenes/pedidos de Dropi. Puede filtrar por estado: pending (pendiente), in_process (en proceso), delivered (entregado), returned (devuelto), cancelled (cancelado).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Estado de las órdenes: all, pending, in_process, shipped, delivered, returned, cancelled"
                },
                "limit": {
                    "type": "integer",
                    "description": "Cantidad de órdenes a obtener (default 20)"
                },
                "days": {
                    "type": "integer",
                    "description": "Órdenes de los últimos X días (default 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_order_stats",
        "description": "Resumen estadístico de órdenes: cuántas entregadas, pendientes, devueltas, canceladas. Ideal para ver el estado general del negocio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Estadísticas de los últimos X días (default 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_payments",
        "description": "Consulta los pagos recibidos de Dropi. Muestra pedidos pagados, montos y fechas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Pagos de los últimos X días (default 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_returns",
        "description": "Consulta las devoluciones y novidades. Muestra pedidos devueltos, motivos y si hay cobros por devolución.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Devoluciones de los últimos X días (default 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_profit_analysis",
        "description": "Análisis de rentabilidad: calcula el profit considerando pedidos entregados, devoluciones cobradas y costos de envío.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Análisis de los últimos X días (default 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_account_info",
        "description": "Información de la cuenta de Dropi: datos del usuario, país, estado de la cuenta.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "search_dropi_order",
        "description": "Busca una orden específica por número de guía o ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Número de guía, ID de orden o nombre del cliente"
                }
            },
            "required": ["query"]
        }
    }
]

# ==============================================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# ==============================================================================

async def get_dropi_wallet(args: dict) -> str:
    """Consulta el saldo de la billetera."""
    
    # Intentar varios endpoints posibles
    endpoints_to_try = [
        "wallet",
        "wallet/balance",
        "user/wallet",
        "billing/wallet",
        "balance"
    ]
    
    for endpoint in endpoints_to_try:
        data = await dropi_get(endpoint)
        
        if "error" not in data:
            # Intentar extraer el balance de diferentes estructuras
            balance = data.get("balance") or data.get("saldo") or data.get("available") or data.get("data", {}).get("balance")
            pending = data.get("pending") or data.get("pendiente") or data.get("data", {}).get("pending", 0)
            available = data.get("available") or data.get("disponible") or balance
            
            if balance is not None:
                return f"""💰 BILLETERA DROPI:

💵 Saldo Disponible: ${float(available or 0):,.2f}
⏳ Saldo Pendiente: ${float(pending or 0):,.2f}
📊 Saldo Total: ${float(balance):,.2f}

💡 El saldo pendiente corresponde a pedidos entregados aún no liquidados."""
    
    # Si ningún endpoint funciona, mostrar mensaje de error con debug
    return f"""❌ No se pudo consultar la billetera.

🔍 Información de debug:
- URL Base: {DROPI_BASE_URL}
- Token configurado: {'Sí' if DROPI_TOKEN else 'No'}
- Token (primeros 20 chars): {DROPI_TOKEN[:20]}...

💡 Posibles soluciones:
1. Verifica que el DROPI_TOKEN sea válido
2. Verifica que DROPI_COUNTRY sea correcto ({DROPI_COUNTRY})
3. El token puede necesitar renovarse

Último error: {data.get('error', 'Desconocido')}"""

async def get_dropi_orders(args: dict) -> str:
    """Obtiene las órdenes de Dropi."""
    status = args.get("status", "all")
    limit = min(args.get("limit", 20), 100)
    days = args.get("days", 30)
    
    # Calcular fecha desde
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Intentar diferentes endpoints
    endpoints_to_try = [
        ("orders", {"status": status, "limit": limit, "from": date_from}),
        ("order", {"status": status, "limit": limit}),
        ("orders/list", {"status": status, "limit": limit}),
        ("user/orders", {"limit": limit}),
    ]
    
    for endpoint, params in endpoints_to_try:
        if status == "all":
            params.pop("status", None)
        
        data = await dropi_get(endpoint, params)
        
        if "error" not in data:
            orders = data.get("data") or data.get("orders") or data.get("items") or []
            
            if isinstance(orders, list):
                if not orders:
                    return f"📦 No hay órdenes en los últimos {days} días."
                
                result = f"📦 ÓRDENES DROPI (últimos {days} días):\n\n"
                
                # Contadores por estado
                stats = {}
                total_amount = 0
                
                for order in orders[:limit]:
                    order_id = order.get("id") or order.get("order_id") or order.get("tracking_number", "N/A")
                    order_status = order.get("status") or order.get("estado") or "Desconocido"
                    customer = order.get("customer_name") or order.get("cliente") or order.get("client", {}).get("name", "Sin nombre")
                    amount = float(order.get("total") or order.get("amount") or order.get("valor") or 0)
                    date = order.get("created_at") or order.get("fecha") or ""
                    
                    stats[order_status] = stats.get(order_status, 0) + 1
                    total_amount += amount
                    
                    result += f"📌 #{order_id} | {customer}\n"
                    result += f"   💵 ${amount:,.2f} | 📊 {order_status}\n"
                    if date:
                        result += f"   📅 {date[:10]}\n"
                    result += "\n"
                
                result += f"\n📊 RESUMEN:\n"
                for st, count in stats.items():
                    result += f"   • {st}: {count}\n"
                result += f"   💰 Total: ${total_amount:,.2f}\n"
                
                return result
    
    return f"❌ No se pudieron obtener las órdenes.\nError: {data.get('error', 'Desconocido')}"

async def get_dropi_order_stats(args: dict) -> str:
    """Estadísticas de órdenes."""
    days = args.get("days", 30)
    
    # Obtener todas las órdenes y calcular estadísticas
    data = await dropi_get("orders", {"limit": 500})
    
    if "error" in data:
        # Intentar endpoint alternativo
        data = await dropi_get("orders/stats")
        
        if "error" not in data:
            # Si hay un endpoint de stats directo
            return f"""📊 ESTADÍSTICAS DROPI:

{json.dumps(data, indent=2, ensure_ascii=False)}"""
    
    orders = data.get("data") or data.get("orders") or []
    
    if not orders:
        return "📊 No hay datos suficientes para generar estadísticas."
    
    # Calcular estadísticas
    stats = {
        "total": 0,
        "delivered": 0,
        "pending": 0,
        "in_process": 0,
        "returned": 0,
        "cancelled": 0,
        "total_value": 0,
        "delivered_value": 0,
        "returned_value": 0
    }
    
    status_map = {
        "entregado": "delivered",
        "delivered": "delivered",
        "pendiente": "pending",
        "pending": "pending",
        "en_proceso": "in_process",
        "in_process": "in_process",
        "shipped": "in_process",
        "devuelto": "returned",
        "returned": "returned",
        "cancelado": "cancelled",
        "cancelled": "cancelled"
    }
    
    for order in orders:
        status_raw = (order.get("status") or order.get("estado") or "").lower()
        status = status_map.get(status_raw, "pending")
        amount = float(order.get("total") or order.get("amount") or 0)
        
        stats["total"] += 1
        stats["total_value"] += amount
        stats[status] = stats.get(status, 0) + 1
        
        if status == "delivered":
            stats["delivered_value"] += amount
        elif status == "returned":
            stats["returned_value"] += amount
    
    # Calcular tasas
    delivery_rate = (stats["delivered"] / stats["total"] * 100) if stats["total"] > 0 else 0
    return_rate = (stats["returned"] / stats["total"] * 100) if stats["total"] > 0 else 0
    
    return f"""📊 ESTADÍSTICAS DE ÓRDENES DROPI:

📦 Total Órdenes: {stats['total']}

✅ Entregadas: {stats['delivered']} ({delivery_rate:.1f}%)
⏳ Pendientes: {stats['pending']}
🚚 En Proceso: {stats['in_process']}
↩️ Devueltas: {stats['returned']} ({return_rate:.1f}%)
❌ Canceladas: {stats['cancelled']}

💰 VALORES:
   Valor Total: ${stats['total_value']:,.2f}
   Entregado: ${stats['delivered_value']:,.2f}
   Devuelto: ${stats['returned_value']:,.2f}

📈 Tasa de Entrega: {delivery_rate:.1f}%
📉 Tasa de Devolución: {return_rate:.1f}%"""

async def get_dropi_payments(args: dict) -> str:
    """Consulta los pagos recibidos."""
    days = args.get("days", 30)
    
    endpoints_to_try = ["payments", "wallet/payments", "billing/payments", "liquidations"]
    
    for endpoint in endpoints_to_try:
        data = await dropi_get(endpoint)
        
        if "error" not in data:
            payments = data.get("data") or data.get("payments") or data.get("items") or []
            
            if not payments:
                return "💳 No hay pagos registrados en el periodo."
            
            result = f"💳 PAGOS DROPI (últimos {days} días):\n\n"
            total = 0
            
            for payment in payments[:20]:
                amount = float(payment.get("amount") or payment.get("monto") or 0)
                date = payment.get("date") or payment.get("fecha") or payment.get("created_at", "")
                status = payment.get("status") or payment.get("estado") or "Procesado"
                
                total += amount
                result += f"💵 ${amount:,.2f} | {date[:10] if date else 'N/A'} | {status}\n"
            
            result += f"\n💰 TOTAL RECIBIDO: ${total:,.2f}"
            return result
    
    return "💳 No se pudo obtener información de pagos."

async def get_dropi_returns(args: dict) -> str:
    """Consulta devoluciones."""
    days = args.get("days", 30)
    
    # Obtener órdenes y filtrar devueltas
    data = await dropi_get("orders", {"status": "returned", "limit": 100})
    
    if "error" in data:
        data = await dropi_get("returns")
    
    if "error" in data:
        return f"❌ No se pudo obtener devoluciones: {data.get('error')}"
    
    returns = data.get("data") or data.get("orders") or data.get("returns") or []
    
    if not returns:
        return "↩️ No hay devoluciones registradas. ¡Excelente!"
    
    result = "↩️ DEVOLUCIONES DROPI:\n\n"
    total_loss = 0
    total_charged = 0
    
    for ret in returns[:20]:
        order_id = ret.get("id") or ret.get("order_id") or "N/A"
        reason = ret.get("return_reason") or ret.get("motivo") or ret.get("reason") or "Sin especificar"
        amount = float(ret.get("total") or ret.get("amount") or 0)
        charge = float(ret.get("return_charge") or ret.get("cobro_devolucion") or 0)
        
        total_loss += amount
        total_charged += charge
        
        result += f"📌 #{order_id}\n"
        result += f"   💵 Valor: ${amount:,.2f}\n"
        result += f"   📝 Motivo: {reason}\n"
        if charge > 0:
            result += f"   ⚠️ Cobro por devolución: ${charge:,.2f}\n"
        result += "\n"
    
    result += f"\n📊 RESUMEN DEVOLUCIONES:\n"
    result += f"   Total Devoluciones: {len(returns)}\n"
    result += f"   Valor Perdido: ${total_loss:,.2f}\n"
    result += f"   Cobros por Devolución: ${total_charged:,.2f}"
    
    return result

async def get_dropi_profit_analysis(args: dict) -> str:
    """Análisis de rentabilidad."""
    days = args.get("days", 30)
    
    # Obtener todas las órdenes
    orders_data = await dropi_get("orders", {"limit": 500})
    orders = orders_data.get("data") or orders_data.get("orders") or []
    
    # Obtener wallet para ver saldo
    wallet_data = await dropi_get("wallet")
    wallet_balance = float(wallet_data.get("balance") or wallet_data.get("data", {}).get("balance") or 0)
    
    # Calcular métricas
    delivered = {"count": 0, "value": 0}
    pending = {"count": 0, "value": 0}
    returned = {"count": 0, "value": 0, "charges": 0}
    cancelled = {"count": 0, "value": 0}
    
    for order in orders:
        status = (order.get("status") or order.get("estado") or "").lower()
        amount = float(order.get("total") or order.get("amount") or 0)
        
        if "entreg" in status or "delivered" in status:
            delivered["count"] += 1
            delivered["value"] += amount
        elif "devuel" in status or "return" in status:
            returned["count"] += 1
            returned["value"] += amount
            returned["charges"] += float(order.get("return_charge") or 0)
        elif "cancel" in status:
            cancelled["count"] += 1
            cancelled["value"] += amount
        else:
            pending["count"] += 1
            pending["value"] += amount
    
    total_orders = delivered["count"] + pending["count"] + returned["count"] + cancelled["count"]
    
    # Calcular tasas
    delivery_rate = (delivered["count"] / total_orders * 100) if total_orders > 0 else 0
    return_rate = (returned["count"] / total_orders * 100) if total_orders > 0 else 0
    
    # Estimar profit (esto es aproximado sin conocer costos)
    revenue = delivered["value"]
    losses = returned["charges"]  # Solo los cobros por devolución como pérdida directa
    
    return f"""📈 ANÁLISIS DE RENTABILIDAD DROPI:

📦 ÓRDENES (últimos {days} días):
   Total: {total_orders}
   ✅ Entregadas: {delivered['count']} (${delivered['value']:,.2f})
   ⏳ Pendientes: {pending['count']} (${pending['value']:,.2f})
   ↩️ Devueltas: {returned['count']} (${returned['value']:,.2f})
   ❌ Canceladas: {cancelled['count']}

📊 TASAS:
   Tasa de Entrega: {delivery_rate:.1f}%
   Tasa de Devolución: {return_rate:.1f}%

💰 FINANCIERO:
   Ingresos por Entregas: ${revenue:,.2f}
   Cobros por Devoluciones: ${returned['charges']:,.2f}
   Saldo en Wallet: ${wallet_balance:,.2f}

💡 PROYECCIÓN:
   Si entregas los {pending['count']} pedidos pendientes:
   → Ingreso potencial adicional: ${pending['value']:,.2f}
   → Considerando devolución del {return_rate:.1f}%:
   → Ingreso estimado real: ${pending['value'] * (1 - return_rate/100):,.2f}

⚠️ Nota: Para un análisis completo de profit, necesito también:
- Gasto en Meta/TikTok Ads (del servidor Meta)
- Costo de producto
- Costo de envío"""

async def get_dropi_account_info(args: dict) -> str:
    """Información de la cuenta."""
    
    endpoints_to_try = ["user", "me", "account", "profile", "user/profile"]
    
    for endpoint in endpoints_to_try:
        data = await dropi_get(endpoint)
        
        if "error" not in data:
            user = data.get("data") or data.get("user") or data
            
            name = user.get("name") or user.get("nombre") or "N/A"
            email = user.get("email") or "N/A"
            phone = user.get("phone") or user.get("telefono") or "N/A"
            country = user.get("country") or user.get("pais") or DROPI_COUNTRY.upper()
            status = user.get("status") or user.get("estado") or "Activo"
            
            return f"""👤 CUENTA DROPI:

📛 Nombre: {name}
📧 Email: {email}
📱 Teléfono: {phone}
🌍 País: {country}
📊 Estado: {status}

🔗 Plataforma: {DROPI_BASE_URL}"""
    
    return f"""👤 CUENTA DROPI:

🔗 Plataforma: {DROPI_BASE_URL}
🌍 País: {DROPI_COUNTRY.upper()}
✅ Token configurado: {'Sí' if DROPI_TOKEN else 'No'}

⚠️ No se pudo obtener más detalles de la cuenta."""

async def search_dropi_order(args: dict) -> str:
    """Busca una orden específica."""
    query = args.get("query", "")
    
    if not query:
        return "❌ Debes proporcionar un número de guía, ID o nombre para buscar."
    
    # Intentar buscar por ID directo
    data = await dropi_get(f"orders/{query}")
    
    if "error" not in data:
        order = data.get("data") or data
        
        return f"""📦 ORDEN ENCONTRADA:

📌 ID: {order.get('id', 'N/A')}
🔢 Guía: {order.get('tracking_number', 'N/A')}
👤 Cliente: {order.get('customer_name', 'N/A')}
💵 Valor: ${float(order.get('total', 0)):,.2f}
📊 Estado: {order.get('status', 'N/A')}
📅 Fecha: {order.get('created_at', 'N/A')[:10] if order.get('created_at') else 'N/A'}"""
    
    # Si no, buscar en lista
    data = await dropi_get("orders", {"search": query, "limit": 10})
    orders = data.get("data") or data.get("orders") or []
    
    if not orders:
        return f"❌ No se encontró ninguna orden con '{query}'"
    
    result = f"🔍 Resultados para '{query}':\n\n"
    for order in orders[:5]:
        result += f"📌 #{order.get('id', 'N/A')} | {order.get('customer_name', 'N/A')}\n"
        result += f"   💵 ${float(order.get('total', 0)):,.2f} | {order.get('status', 'N/A')}\n\n"
    
    return result

# ==============================================================================
# DISPATCHER DE HERRAMIENTAS
# ==============================================================================

TOOL_HANDLERS = {
    "get_dropi_wallet": get_dropi_wallet,
    "get_dropi_orders": get_dropi_orders,
    "get_dropi_order_stats": get_dropi_order_stats,
    "get_dropi_payments": get_dropi_payments,
    "get_dropi_returns": get_dropi_returns,
    "get_dropi_profit_analysis": get_dropi_profit_analysis,
    "get_dropi_account_info": get_dropi_account_info,
    "search_dropi_order": search_dropi_order,
}

async def execute_tool(name: str, args: dict) -> str:
    """Ejecuta una herramienta."""
    handler = TOOL_HANDLERS.get(name)
    if handler:
        try:
            return await handler(args)
        except Exception as e:
            return f"Error ejecutando {name}: {str(e)}"
    return f"Herramienta '{name}' no encontrada"

# ==============================================================================
# ENDPOINTS HTTP (compatibles con mcp_client.py)
# ==============================================================================

async def http_tools(request):
    """Lista las herramientas disponibles."""
    return JSONResponse({"tools": TOOLS})

async def http_call_tool(request):
    """Ejecuta una herramienta."""
    body = await request.json()
    name = body.get("name", "")
    args = body.get("arguments", {})
    result = await execute_tool(name, args)
    return JSONResponse({"result": result})

async def sse_endpoint(request):
    """Endpoint SSE para compatibilidad MCP."""
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
    """Endpoint para mensajes MCP."""
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
                "serverInfo": {"name": "dropi-mcp", "version": "2.0.0"}
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
    """Health check."""
    return JSONResponse({
        "status": "ok",
        "service": "dropi-mcp",
        "version": "2.0.0",
        "country": DROPI_COUNTRY,
        "base_url": DROPI_BASE_URL,
        "token_configured": bool(DROPI_TOKEN)
    })

async def discover_endpoints(request):
    """
    Endpoint de diagnóstico para descubrir qué endpoints funcionan en Dropi.
    Útil para debug y configuración inicial.
    """
    endpoints_to_test = [
        # Usuarios/Cuenta
        "user", "me", "profile", "account", "user/profile", "auth/me",
        # Wallet/Billetera
        "wallet", "wallet/balance", "billing/wallet", "balance", "user/wallet",
        # Órdenes
        "orders", "order", "orders/list", "user/orders", "pedidos",
        # Pagos
        "payments", "wallet/payments", "billing/payments", "liquidations",
        # Devoluciones
        "returns", "devoluciones", "orders/returns",
        # Estadísticas
        "stats", "dashboard", "orders/stats", "analytics",
        # Info general
        "shop", "store", "config"
    ]
    
    results = {"working": [], "not_found": [], "auth_error": [], "other_error": []}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in endpoints_to_test:
            try:
                url = f"{DROPI_BASE_URL}/api/{endpoint}"
                response = await client.get(url, headers=get_headers())
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        # Si tiene data, es exitoso
                        results["working"].append({
                            "endpoint": endpoint,
                            "keys": list(data.keys()) if isinstance(data, dict) else "list"
                        })
                    except:
                        results["working"].append({"endpoint": endpoint, "keys": "raw_response"})
                elif response.status_code == 401:
                    results["auth_error"].append(endpoint)
                elif response.status_code == 404:
                    results["not_found"].append(endpoint)
                else:
                    results["other_error"].append({
                        "endpoint": endpoint, 
                        "status": response.status_code
                    })
            except Exception as e:
                results["other_error"].append({
                    "endpoint": endpoint,
                    "error": str(e)
                })
    
    return JSONResponse({
        "dropi_base_url": DROPI_BASE_URL,
        "token_first_20_chars": DROPI_TOKEN[:20] + "..." if DROPI_TOKEN else "NOT SET",
        "results": results,
        "summary": {
            "working": len(results["working"]),
            "auth_errors": len(results["auth_error"]),
            "not_found": len(results["not_found"]),
            "other_errors": len(results["other_error"])
        }
    })

# ==============================================================================
# APLICACIÓN STARLETTE
# ==============================================================================

app = Starlette(routes=[
    Route("/", health),
    Route("/health", health),
    Route("/discover", discover_endpoints),  # Endpoint de diagnóstico
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"🚀 Dropi MCP Server v2.0 iniciando en puerto {port}")
    print(f"🌍 País: {DROPI_COUNTRY.upper()}")
    print(f"🔗 Base URL: {DROPI_BASE_URL}")
    print(f"🔑 Token: {'Configurado' if DROPI_TOKEN else '❌ NO CONFIGURADO'}")
    uvicorn.run(app, host="0.0.0.0", port=port)
