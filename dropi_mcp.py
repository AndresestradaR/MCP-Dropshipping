"""
Servidor MCP para Dropi - v5.3 FINANCIAL DATA
Basado en v5.2 + datos financieros completos por orden + herramienta batch
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
        return {"success": False, "error": "No se pudo autenticar"}
    
    url = f"{DROPI_API_URL}{endpoint}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=get_headers(), params=params)
            
            if response.status_code == 401:
                global current_token
                current_token = None
                login_result = await dropi_login()
                if login_result.get("success"):
                    response = await client.get(url, headers=get_headers(), params=params)
                else:
                    return {"success": False, "error": "Token expirado"}
            
            if response.status_code == 200:
                data = response.json()
                if data.get("isSuccess", True):
                    return {"success": True, "data": data}
                else:
                    return {"success": False, "error": data.get("message", "Error")}
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
        "description": "Obtiene el saldo disponible en la billetera de Dropi.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_dropi_wallet_history",
        "description": "Historial de movimientos de la cartera: entradas y salidas con montos reales.",
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
        "description": "Lista ordenes de Dropi con estados y valores.",
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
        "description": "Obtiene TODOS los detalles financieros de una orden: ganancia, costo envío real, si ya fue pagada, productos con precios.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "ID de la orden en Dropi"}
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "get_orders_financial_details",
        "description": "Obtiene detalles financieros completos de múltiples órdenes para análisis. Incluye ganancia real, costo envío, estado de pago por cada orden.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Lista de IDs de órdenes a consultar (máximo 50)"
                },
                "start_date": {"type": "string", "description": "Fecha inicio YYYY-MM-DD (alternativa a order_ids)"},
                "end_date": {"type": "string", "description": "Fecha fin YYYY-MM-DD"}
            },
            "required": []
        }
    },
    {
        "name": "get_dropi_user_info",
        "description": "Información del usuario autenticado.",
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
    wallet_amount = user.get("wallet", {}).get("amount") if isinstance(user.get("wallet"), dict) else None
    
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
🆔 ID: {user.get('id', 'N/A')}

✅ Conexión exitosa"""
    
    return f"👤 Usuario: {user.get('email', DROPI_EMAIL)}\n✅ Conexión exitosa"

async def get_dropi_wallet_history(args: dict) -> str:
    """Historial de movimientos de cartera."""
    mov_type = args.get("type")
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
    
    if not current_user:
        await dropi_login()
    
    user_id = current_user.get("id") if current_user else None
    
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
        return f"Error: {result.get('error')}\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    data = result.get("data", {})
    movements = data.get("objects", []) if isinstance(data, dict) else []
    
    # Filtrar por fecha localmente
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
    
    result_text = f"HISTORIAL CARTERA ({period_label})\nTotal: {count}\n\n"
    
    total_in = 0
    total_out = 0
    entries = []
    exits = []
    
    for mov in movements:
        amount = float(mov.get("amount", 0) or 0)
        mov_type_item = mov.get("type", "")
        date = str(mov.get("created_at", ""))[:10]
        order_id = mov.get("order_id", "")
        
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
    result_text += f"  Entradas: Q{total_in:,.2f} ({len(entries)})\n"
    result_text += f"  Salidas: Q{total_out:,.2f} ({len(exits)})\n"
    result_text += f"  Neto: Q{net:,.2f}"
    
    json_data = {
        "total_income": round(total_in, 2),
        "total_expenses": round(total_out, 2),
        "net": round(net, 2),
        "count": count,
        "entries": entries[:30],
        "exits": exits[:30],
        "period": period_label
    }
    
    return f"{result_text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"

async def get_dropi_orders(args: dict) -> str:
    """Obtiene las ordenes."""
    limit = args.get("limit", 100)
    status_filter = args.get("status")
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
        json_data = {"total_orders": 0, "period": period_label}
        return f"Error: {result.get('error')}\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    data = result.get("data", {})
    orders = data.get("objects", []) if isinstance(data, dict) else []
    
    if filter_locally and orders:
        filtered = []
        for order in orders:
            order_date = str(order.get("created_at", ""))[:10]
            if local_start <= order_date <= local_end:
                filtered.append(order)
        orders = filtered
    
    count = len(orders)
    
    if not orders:
        json_data = {"total_orders": 0, "period": period_label}
        return f"No hay ordenes en {period_label}.\n\n---JSON_DATA---\n{json.dumps(json_data)}"
    
    # Contadores
    stats = {}
    total_value = 0
    delivered_count = 0
    delivered_profit = 0
    returned_count = 0
    pending_count = 0
    pending_profit = 0
    cancelled_count = 0
    
    orders_summary = []
    
    for order in orders:
        status = order.get("status", "?")
        amount = float(order.get("total_order", 0) or 0)
        profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
        order_id = order.get("id")
        created = str(order.get("created_at", ""))[:10]
        
        stats[status] = stats.get(status, 0) + 1
        total_value += amount
        
        orders_summary.append({
            "id": order_id,
            "status": status,
            "total": amount,
            "profit": profit,
            "created_at": created
        })
        
        status_lower = (status or "").lower()
        
        if status_lower in ["entregado", "delivered", "completado"]:
            delivered_count += 1
            delivered_profit += profit
        elif status_lower in ["devolucion", "devuelto", "returned"]:
            returned_count += 1
        elif status_lower in ["cancelado", "cancelled"]:
            cancelled_count += 1
        else:
            pending_count += 1
            pending_profit += profit
    
    result_text = f"ORDENES DROPI ({period_label})\nTotal: {count}\n\n"
    
    for order in orders[:10]:
        oid = order.get("id")
        st = order.get("status", "?")
        profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
        result_text += f"#{oid} | {st} | Q{profit:,.2f}\n"
    if len(orders) > 10:
        result_text += f"... y {len(orders) - 10} mas\n"
    
    result_text += f"\nPOR ESTADO:\n"
    for st, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        result_text += f"  {st}: {cnt}\n"
    
    result_text += f"\nRESUMEN:\n"
    result_text += f"  Entregados: {delivered_count} (Q{delivered_profit:,.2f})\n"
    result_text += f"  Devoluciones: {returned_count}\n"
    result_text += f"  Pendientes: {pending_count} (Q{pending_profit:,.2f})\n"
    result_text += f"  Cancelados: {cancelled_count}"
    
    json_data = {
        "total_orders": count,
        "total_sales_value": round(total_value, 2),
        "delivered": delivered_count,
        "delivered_profit": round(delivered_profit, 2),
        "returned": returned_count,
        "pending": pending_count,
        "pending_profit": round(pending_profit, 2),
        "cancelled": cancelled_count,
        "stats_by_status": stats,
        "orders": orders_summary,
        "period": period_label
    }
    
    return f"{result_text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"

async def get_dropi_order(args: dict) -> str:
    """Obtiene TODOS los detalles financieros de una orden específica."""
    order_id = args.get("order_id")
    if not order_id:
        return "❌ Se requiere order_id"
    
    # IMPORTANTE: warranty=false para obtener datos financieros completos
    result = await dropi_get(f"/api/orders/myorders/{order_id}", {"warranty": "false"})
    
    if not result.get("success"):
        return f"❌ Error: {result.get('error')}"
    
    data = result.get("data", {})
    order = data.get("objects", {}) if isinstance(data, dict) else {}
    
    if not order:
        return f"❌ Orden #{order_id} no encontrada"
    
    # Extraer datos financieros
    order_details = order.get("orderdetails", [])
    history_wallet = order.get("history_wallet", [])
    
    # Calcular totales de productos
    total_product_cost = 0
    total_shipping = 0
    products_info = []
    
    for detail in order_details:
        product = detail.get("product", {})
        qty = detail.get("quantity", 1)
        price = float(detail.get("price", 0) or 0)
        supplier_price = float(detail.get("supplier_price", 0) or 0)
        shipping = float(detail.get("shipping_amount", 0) or 0)
        
        total_product_cost += supplier_price * qty
        total_shipping += shipping
        
        products_info.append({
            "name": product.get("name", "Producto"),
            "quantity": qty,
            "sale_price": price,
            "cost": supplier_price,
            "shipping": shipping
        })
    
    # Verificar si ya fue pagada
    payment_info = None
    if history_wallet:
        for hw in history_wallet:
            if hw.get("type") == "ENTRADA":
                payment_info = {
                    "paid": True,
                    "amount": float(hw.get("amount", 0)),
                    "date": str(hw.get("created_at", ""))[:10]
                }
                break
    
    if not payment_info:
        payment_info = {"paid": False, "amount": 0, "date": None}
    
    # Construir respuesta
    profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
    total_order = float(order.get("total_order", 0) or 0)
    shipping_amount = float(order.get("shipping_amount", 0) or 0)
    
    result_text = f"""📦 ORDEN #{order.get('id')} - DETALLE FINANCIERO

👤 Cliente: {order.get('name', '')} {order.get('surname', '')}
📍 {order.get('city', '')}, {order.get('state', '')}
📊 Estado: {order.get('status', 'N/A')}
🚚 Transportadora: {order.get('shipping_company', 'N/A')}
📋 Guía: {order.get('shipping_guide', 'Sin guía')}

💰 FINANCIERO:
   Precio venta: Q{total_order:,.2f}
   Costo producto: Q{total_product_cost:,.2f}
   Costo envío: Q{shipping_amount:,.2f}
   GANANCIA: Q{profit:,.2f}

💳 PAGO DROPI:
   Estado: {'✅ PAGADO' if payment_info['paid'] else '⏳ PENDIENTE'}
   Monto: Q{payment_info['amount']:,.2f}
   Fecha: {payment_info['date'] or 'N/A'}

📦 PRODUCTOS:"""
    
    for p in products_info:
        result_text += f"\n   • {p['name']} x{p['quantity']}"
        result_text += f"\n     Venta: Q{p['sale_price']:,.2f} | Costo: Q{p['cost']:,.2f} | Envío: Q{p['shipping']:,.2f}"
    
    result_text += f"\n\n📅 Creado: {str(order.get('created_at', ''))[:19]}"
    
    # JSON estructurado para analytics
    json_data = {
        "order_id": order.get("id"),
        "status": order.get("status"),
        "created_at": str(order.get("created_at", ""))[:10],
        "customer": f"{order.get('name', '')} {order.get('surname', '')}",
        "city": order.get("city"),
        "carrier": order.get("shipping_company"),
        "guide": order.get("shipping_guide"),
        "financial": {
            "sale_price": total_order,
            "product_cost": total_product_cost,
            "shipping_cost": shipping_amount,
            "profit": profit
        },
        "payment": payment_info,
        "products": products_info
    }
    
    return f"{result_text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"

async def get_orders_financial_details(args: dict) -> str:
    """Obtiene detalles financieros de múltiples órdenes para análisis."""
    order_ids = args.get("order_ids", [])
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    
    # Si no hay order_ids, obtener de un rango de fechas
    if not order_ids and start_date and end_date:
        orders_result = await get_dropi_orders({
            "start_date": start_date,
            "end_date": end_date,
            "limit": 100
        })
        
        # Extraer IDs del JSON
        try:
            json_part = orders_result.split("---JSON_DATA---")[1] if "---JSON_DATA---" in orders_result else "{}"
            orders_data = json.loads(json_part)
            order_ids = [o["id"] for o in orders_data.get("orders", [])]
        except:
            return "❌ Error obteniendo lista de órdenes"
    
    if not order_ids:
        return "❌ Se requiere order_ids o start_date/end_date"
    
    # Limitar a 50 órdenes máximo
    order_ids = order_ids[:50]
    
    results = []
    total_profit = 0
    total_shipping = 0
    paid_count = 0
    paid_amount = 0
    pending_payment = 0
    
    result_text = f"📊 ANÁLISIS FINANCIERO - {len(order_ids)} órdenes\n\n"
    
    for oid in order_ids:
        try:
            order_result = await dropi_get(f"/api/orders/myorders/{oid}", {"warranty": "false"})
            
            if not order_result.get("success"):
                continue
            
            data = order_result.get("data", {})
            order = data.get("objects", {}) if isinstance(data, dict) else {}
            
            if not order:
                continue
            
            # Extraer datos
            profit = float(order.get("dropshipper_amount_to_win", 0) or 0)
            shipping = float(order.get("shipping_amount", 0) or 0)
            status = order.get("status", "")
            
            # Verificar pago
            history_wallet = order.get("history_wallet", [])
            paid = False
            payment_amount = 0
            
            for hw in history_wallet:
                if hw.get("type") == "ENTRADA":
                    paid = True
                    payment_amount = float(hw.get("amount", 0))
                    break
            
            total_profit += profit
            total_shipping += shipping
            
            if paid:
                paid_count += 1
                paid_amount += payment_amount
            else:
                pending_payment += profit
            
            results.append({
                "order_id": oid,
                "status": status,
                "profit": profit,
                "shipping_cost": shipping,
                "paid": paid,
                "payment_amount": payment_amount
            })
            
        except Exception as e:
            continue
    
    # Resumen
    result_text += f"💰 GANANCIA TOTAL: Q{total_profit:,.2f}\n"
    result_text += f"🚚 COSTO ENVÍOS: Q{total_shipping:,.2f}\n\n"
    result_text += f"💳 PAGOS:\n"
    result_text += f"   ✅ Pagados: {paid_count} órdenes (Q{paid_amount:,.2f})\n"
    result_text += f"   ⏳ Pendientes: {len(results) - paid_count} órdenes (Q{pending_payment:,.2f})\n\n"
    
    result_text += "📋 DETALLE POR ORDEN:\n"
    for r in results[:20]:
        status_icon = "✅" if r["paid"] else "⏳"
        result_text += f"   #{r['order_id']} | {r['status']} | Q{r['profit']:,.2f} | {status_icon}\n"
    
    if len(results) > 20:
        result_text += f"   ... y {len(results) - 20} más\n"
    
    json_data = {
        "total_orders": len(results),
        "total_profit": round(total_profit, 2),
        "total_shipping_cost": round(total_shipping, 2),
        "paid_count": paid_count,
        "paid_amount": round(paid_amount, 2),
        "pending_payment": round(pending_payment, 2),
        "orders": results
    }
    
    return f"{result_text}\n\n---JSON_DATA---\n{json.dumps(json_data)}"

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
🆔 ID: {user.get('id', 'N/A')}
🌍 País: {DROPI_COUNTRY.upper()}

✅ Autenticado correctamente"""

# ==============================================================================
# DISPATCHER
# ==============================================================================

TOOL_HANDLERS = {
    "get_dropi_wallet": get_dropi_wallet,
    "get_dropi_wallet_history": get_dropi_wallet_history,
    "get_dropi_orders": get_dropi_orders,
    "get_dropi_order": get_dropi_order,
    "get_orders_financial_details": get_orders_financial_details,
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
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "dropi-mcp", "version": "5.3.0"}}}
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
        "version": "5.3.0",
        "api_url": DROPI_API_URL,
        "country": DROPI_COUNTRY.upper(),
        "authenticated": bool(current_token)
    })

async def login_endpoint(request):
    result = await dropi_login()
    return JSONResponse(result)

async def discover(request):
    login_result = await dropi_login()
    
    if not login_result.get("success"):
        return JSONResponse({
            "success": False,
            "error": login_result.get("error")
        })
    
    return JSONResponse({
        "success": True,
        "user": {
            "id": current_user.get("id"),
            "name": f"{current_user.get('name', '')} {current_user.get('surname', '')}"
        }
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
    print(f"🚀 Dropi MCP Server v5.3 - FINANCIAL DATA")
    print(f"🌍 País: {DROPI_COUNTRY.upper()}")
    print(f"🔗 API: {DROPI_API_URL}")
    uvicorn.run(app, host="0.0.0.0", port=port)