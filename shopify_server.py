"""
Servidor MCP para Shopify - COMPLETO v2
Corregido para obtener nombres de clientes correctamente.
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

SHOPIFY_SHOP_URL = os.getenv("SHOPIFY_SHOP_URL", "").replace("https://", "").replace("/", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"

sessions = {}

def get_base_url():
    return f"https://{SHOPIFY_SHOP_URL}/admin/api/{API_VERSION}"

def get_headers():
    return {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

def get_customer_name(order):
    """Obtiene el nombre del cliente de donde esté disponible."""
    # Primero intentar billing_address
    billing = order.get("billing_address", {})
    if billing:
        name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        if name:
            return name
    
    # Luego shipping_address
    shipping = order.get("shipping_address", {})
    if shipping:
        name = f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip()
        if name:
            return name
    
    # Finalmente customer
    customer = order.get("customer", {})
    if customer:
        name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        if name:
            return name
    
    return "Sin nombre"

def get_customer_contact(order):
    """Obtiene email y teléfono del cliente."""
    email = order.get("email") or order.get("contact_email") or ""
    phone = ""
    
    # Buscar teléfono en billing o shipping
    billing = order.get("billing_address", {})
    shipping = order.get("shipping_address", {})
    
    phone = billing.get("phone") or shipping.get("phone") or order.get("phone") or ""
    
    if not email:
        customer = order.get("customer", {})
        email = customer.get("email", "")
    
    return email or "Sin email", phone or "Sin teléfono"

# ========== HERRAMIENTAS ==========

TOOLS = [
    # VENTAS Y PEDIDOS
    {
        "name": "get_total_sales_today",
        "description": "Obtiene el total de ventas del dia de hoy (monto total y cantidad de pedidos)",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_recent_orders",
        "description": "Obtiene los pedidos recientes con detalles: nombre del cliente, productos comprados, valor, estado de pago. Usa limit para controlar cuantos (default 10)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de pedidos a mostrar (default 10, max 50)"},
                "status": {"type": "string", "description": "Filtrar por estado: any, open, closed, cancelled (default: any)"}
            },
            "required": []
        }
    },
    {
        "name": "get_order_details",
        "description": "Obtiene los detalles completos de un pedido especifico por su numero o ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Numero o ID del pedido"}
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "get_sales_by_period",
        "description": "Obtiene ventas de un periodo: today, yesterday, week, month",
        "inputSchema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "Periodo: today, yesterday, week, month"}
            },
            "required": ["period"]
        }
    },
    # PRODUCTOS E INVENTARIO
    {
        "name": "get_all_products",
        "description": "Lista todos los productos de la tienda con precio, inventario y estado",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de productos (default 50)"}
            },
            "required": []
        }
    },
    {
        "name": "check_product_inventory",
        "description": "Busca un producto por nombre y muestra su inventario detallado",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Nombre del producto a buscar"}
            },
            "required": ["product_name"]
        }
    },
    {
        "name": "get_low_stock_products",
        "description": "Lista productos con inventario bajo (menos de X unidades)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "description": "Umbral de inventario bajo (default 5)"}
            },
            "required": []
        }
    },
    # CLIENTES
    {
        "name": "get_recent_customers",
        "description": "Lista los clientes mas recientes con sus datos de contacto y total de compras",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de clientes (default 10)"}
            },
            "required": []
        }
    },
    {
        "name": "search_customer",
        "description": "Busca un cliente por nombre, email o telefono",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre, email o telefono del cliente"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_top_customers",
        "description": "Lista los mejores clientes por total de compras",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de clientes (default 10)"}
            },
            "required": []
        }
    },
    # INFORMACION DE LA TIENDA
    {
        "name": "get_shop_info",
        "description": "Obtiene informacion general de la tienda: nombre, dominio, email, moneda, plan, etc",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_shop_balance",
        "description": "Obtiene el balance financiero de la tienda (si debes dinero, pagos pendientes)",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    # ANALYTICS
    {
        "name": "get_best_selling_products",
        "description": "Lista los productos mas vendidos",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Cantidad de productos (default 10)"}
            },
            "required": []
        }
    }
]

# ========== IMPLEMENTACION DE HERRAMIENTAS ==========

async def api_get(endpoint: str, params: dict = None):
    """Helper para hacer GET a la API de Shopify"""
    url = f"{get_base_url()}/{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=get_headers(), params=params)
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text}"}
        return response.json()

async def get_total_sales_today(args: dict) -> str:
    import datetime
    today = datetime.date.today().isoformat()
    data = await api_get("orders.json", {"created_at_min": today, "status": "any"})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    orders = data.get("orders", [])
    total = sum(float(o.get("total_price", 0)) for o in orders)
    paid = len([o for o in orders if o.get("financial_status") == "paid"])
    pending = len([o for o in orders if o.get("financial_status") == "pending"])
    
    return f"""📊 VENTAS DE HOY ({today}):
💰 Total: ${total:,.2f}
📦 Pedidos: {len(orders)}
✅ Pagados: {paid}
⏳ Pendientes: {pending}"""

async def get_recent_orders(args: dict) -> str:
    limit = min(args.get("limit", 10), 50)
    status = args.get("status", "any")
    
    data = await api_get("orders.json", {"limit": limit, "status": status})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    orders = data.get("orders", [])
    if not orders:
        return "No hay pedidos recientes."
    
    result = f"📦 ULTIMOS {len(orders)} PEDIDOS:\n\n"
    
    for o in orders:
        order_num = o.get("order_number", o.get("id"))
        name = get_customer_name(o)
        email, phone = get_customer_contact(o)
        total = float(o.get("total_price", 0))
        fin_status = o.get("financial_status", "unknown")
        created = o.get("created_at", "")[:10]
        
        # Productos
        items = o.get("line_items", [])
        products = ", ".join([f"{i.get('name', 'Producto')} x{i.get('quantity', 1)}" for i in items[:3]])
        if len(items) > 3:
            products += f" (+{len(items)-3} mas)"
        
        result += f"""🔹 Pedido #{order_num} - {created}
   👤 {name}
   📧 {email} | 📱 {phone}
   🛒 {products}
   💵 ${total:,.2f} - {fin_status}

"""
    
    return result

async def get_order_details(args: dict) -> str:
    order_id = args.get("order_id", "")
    
    # Buscar por numero de orden
    data = await api_get("orders.json", {"name": order_id, "status": "any"})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    orders = data.get("orders", [])
    if not orders:
        # Intentar buscar por ID directo
        data = await api_get(f"orders/{order_id}.json")
        if "error" in data:
            return f"No encontre el pedido #{order_id}"
        order = data.get("order", {})
    else:
        order = orders[0]
    
    name = get_customer_name(order)
    email, phone = get_customer_contact(order)
    shipping = order.get("shipping_address", {})
    
    result = f"""📋 DETALLE PEDIDO #{order.get('order_number', order.get('id'))}

👤 CLIENTE:
   Nombre: {name}
   Email: {email}
   Telefono: {phone}

📍 DIRECCION DE ENVIO:
   {shipping.get('address1', 'N/A')}
   {shipping.get('city', '')}, {shipping.get('province', '')} {shipping.get('zip', '')}
   {shipping.get('country', '')}

🛒 PRODUCTOS:
"""
    
    for item in order.get("line_items", []):
        result += f"   - {item.get('name')} x{item.get('quantity')} = ${float(item.get('price', 0)):,.2f}\n"
    
    result += f"""
💰 RESUMEN:
   Subtotal: ${float(order.get('subtotal_price', 0)):,.2f}
   Envio: ${float(order.get('total_shipping_price_set', {}).get('shop_money', {}).get('amount', 0)):,.2f}
   Impuestos: ${float(order.get('total_tax', 0)):,.2f}
   TOTAL: ${float(order.get('total_price', 0)):,.2f}

📊 ESTADO:
   Pago: {order.get('financial_status', 'N/A')}
   Envio: {order.get('fulfillment_status', 'No enviado')}
   Fecha: {order.get('created_at', '')[:19].replace('T', ' ')}
"""
    
    return result

async def get_sales_by_period(args: dict) -> str:
    import datetime
    period = args.get("period", "today")
    today = datetime.date.today()
    
    if period == "today":
        start_date = today.isoformat()
        label = "HOY"
    elif period == "yesterday":
        start_date = (today - datetime.timedelta(days=1)).isoformat()
        label = "AYER"
    elif period == "week":
        start_date = (today - datetime.timedelta(days=7)).isoformat()
        label = "ULTIMOS 7 DIAS"
    elif period == "month":
        start_date = (today - datetime.timedelta(days=30)).isoformat()
        label = "ULTIMOS 30 DIAS"
    else:
        start_date = today.isoformat()
        label = "HOY"
    
    data = await api_get("orders.json", {"created_at_min": start_date, "status": "any", "limit": 250})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    orders = data.get("orders", [])
    total = sum(float(o.get("total_price", 0)) for o in orders)
    paid_orders = [o for o in orders if o.get("financial_status") == "paid"]
    paid_total = sum(float(o.get("total_price", 0)) for o in paid_orders)
    
    return f"""📊 VENTAS {label}:

💰 Total bruto: ${total:,.2f}
✅ Total pagado: ${paid_total:,.2f}
📦 Pedidos totales: {len(orders)}
✅ Pedidos pagados: {len(paid_orders)}
📈 Ticket promedio: ${(total/len(orders) if orders else 0):,.2f}"""

async def get_all_products(args: dict) -> str:
    limit = min(args.get("limit", 50), 250)
    data = await api_get("products.json", {"limit": limit})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    products = data.get("products", [])
    if not products:
        return "No hay productos en la tienda."
    
    result = f"🏪 PRODUCTOS EN LA TIENDA ({len(products)}):\n\n"
    
    for p in products:
        title = p.get("title", "Sin nombre")
        status = p.get("status", "unknown")
        variants = p.get("variants", [])
        
        if variants:
            price = variants[0].get("price", "0")
            total_inv = sum(v.get("inventory_quantity", 0) for v in variants)
        else:
            price = "0"
            total_inv = 0
        
        status_emoji = "✅" if status == "active" else "⏸️"
        inv_warning = "⚠️" if total_inv < 5 else ""
        
        result += f"{status_emoji} {title}\n   💵 ${price} | 📦 {total_inv} unidades {inv_warning}\n\n"
    
    return result

async def check_product_inventory(args: dict) -> str:
    product_name = args.get("product_name", "")
    data = await api_get("products.json")
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    products = data.get("products", [])
    found = []
    
    for p in products:
        if product_name.lower() in p["title"].lower():
            variants = p.get("variants", [])
            variant_info = []
            for v in variants:
                variant_info.append(f"   - {v.get('title', 'Default')}: {v.get('inventory_quantity', 0)} unidades (${v.get('price', 0)})")
            
            found.append(f"📦 {p['title']}\n" + "\n".join(variant_info))
    
    if not found:
        return f"No encontre productos con '{product_name}'"
    
    return "🔍 INVENTARIO ENCONTRADO:\n\n" + "\n\n".join(found)

async def get_low_stock_products(args: dict) -> str:
    threshold = args.get("threshold", 5)
    data = await api_get("products.json", {"limit": 250})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    products = data.get("products", [])
    low_stock = []
    
    for p in products:
        if p.get("status") != "active":
            continue
        variants = p.get("variants", [])
        total_inv = sum(v.get("inventory_quantity", 0) for v in variants)
        if total_inv < threshold:
            low_stock.append(f"⚠️ {p['title']}: {total_inv} unidades")
    
    if not low_stock:
        return f"✅ No hay productos con menos de {threshold} unidades."
    
    return f"🚨 PRODUCTOS CON STOCK BAJO (menos de {threshold}):\n\n" + "\n".join(low_stock)

async def get_recent_customers(args: dict) -> str:
    limit = min(args.get("limit", 10), 50)
    data = await api_get("customers.json", {"limit": limit, "order": "created_at desc"})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    customers = data.get("customers", [])
    if not customers:
        return "No hay clientes registrados."
    
    result = f"👥 CLIENTES RECIENTES ({len(customers)}):\n\n"
    
    for c in customers:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "Sin nombre"
        email = c.get("email", "Sin email")
        phone = c.get("phone", "Sin telefono")
        orders = c.get("orders_count", 0)
        total = float(c.get("total_spent", 0))
        
        result += f"""👤 {name}
   📧 {email}
   📱 {phone}
   🛒 {orders} pedidos | 💰 ${total:,.2f} total

"""
    
    return result

async def search_customer(args: dict) -> str:
    query = args.get("query", "")
    data = await api_get("customers/search.json", {"query": query})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    customers = data.get("customers", [])
    if not customers:
        return f"No encontre clientes con '{query}'"
    
    result = f"🔍 CLIENTES ENCONTRADOS:\n\n"
    
    for c in customers:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        result += f"""👤 {name}
   📧 {c.get('email', 'N/A')}
   📱 {c.get('phone', 'N/A')}
   🛒 {c.get('orders_count', 0)} pedidos
   💰 ${float(c.get('total_spent', 0)):,.2f} total

"""
    
    return result

async def get_top_customers(args: dict) -> str:
    limit = min(args.get("limit", 10), 50)
    data = await api_get("customers.json", {"limit": 250})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    customers = data.get("customers", [])
    customers.sort(key=lambda c: float(c.get("total_spent", 0)), reverse=True)
    top = customers[:limit]
    
    if not top:
        return "No hay clientes con compras."
    
    result = f"🏆 TOP {len(top)} MEJORES CLIENTES:\n\n"
    
    for i, c in enumerate(top, 1):
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        result += f"{i}. {name}: ${float(c.get('total_spent', 0)):,.2f} ({c.get('orders_count', 0)} pedidos)\n"
    
    return result

async def get_shop_info(args: dict) -> str:
    data = await api_get("shop.json")
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    shop = data.get("shop", {})
    
    return f"""🏪 INFORMACION DE LA TIENDA:

📛 Nombre: {shop.get('name', 'N/A')}
🌐 Dominio: {shop.get('domain', 'N/A')}
🔗 URL Shopify: {shop.get('myshopify_domain', 'N/A')}
📧 Email: {shop.get('email', 'N/A')}
📱 Telefono: {shop.get('phone', 'N/A')}

📍 Direccion:
   {shop.get('address1', '')}
   {shop.get('city', '')}, {shop.get('province', '')} {shop.get('zip', '')}
   {shop.get('country_name', '')}

💰 Moneda: {shop.get('currency', 'N/A')}
🌍 Zona horaria: {shop.get('timezone', 'N/A')}
📊 Plan: {shop.get('plan_name', 'N/A')}

📅 Creada: {shop.get('created_at', 'N/A')[:10]}
"""

async def get_shop_balance(args: dict) -> str:
    # Shopify Payments balance (si esta disponible)
    data = await api_get("shopify_payments/balance.json")
    
    if "error" in data:
        # Intentar obtener transacciones pendientes
        return """💳 BALANCE FINANCIERO:

Para ver el balance completo y pagos pendientes,
revisa tu panel de Shopify en:
Configuracion > Pagos > Ver pagos

La API tiene acceso limitado a informacion financiera sensible."""
    
    balance = data.get("balance", [])
    
    result = "💳 BALANCE SHOPIFY PAYMENTS:\n\n"
    for b in balance:
        result += f"   {b.get('currency', 'USD')}: ${float(b.get('amount', 0)):,.2f}\n"
    
    return result

async def get_best_selling_products(args: dict) -> str:
    limit = min(args.get("limit", 10), 50)
    
    # Obtener pedidos recientes para calcular productos mas vendidos
    data = await api_get("orders.json", {"limit": 250, "status": "any"})
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    orders = data.get("orders", [])
    product_sales = {}
    
    for order in orders:
        for item in order.get("line_items", []):
            name = item.get("name", "Producto")
            qty = item.get("quantity", 1)
            product_sales[name] = product_sales.get(name, 0) + qty
    
    sorted_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    if not sorted_products:
        return "No hay datos de ventas suficientes."
    
    result = f"🏆 TOP {len(sorted_products)} PRODUCTOS MAS VENDIDOS:\n\n"
    for i, (name, qty) in enumerate(sorted_products, 1):
        result += f"{i}. {name}: {qty} vendidos\n"
    
    return result

# ========== DISPATCHER ==========

TOOL_HANDLERS = {
    "get_total_sales_today": get_total_sales_today,
    "get_recent_orders": get_recent_orders,
    "get_order_details": get_order_details,
    "get_sales_by_period": get_sales_by_period,
    "get_all_products": get_all_products,
    "check_product_inventory": check_product_inventory,
    "get_low_stock_products": get_low_stock_products,
    "get_recent_customers": get_recent_customers,
    "search_customer": search_customer,
    "get_top_customers": get_top_customers,
    "get_shop_info": get_shop_info,
    "get_shop_balance": get_shop_balance,
    "get_best_selling_products": get_best_selling_products,
}

async def execute_tool(name: str, args: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler:
        try:
            return await handler(args)
        except Exception as e:
            return f"Error ejecutando {name}: {str(e)}"
    return f"Herramienta {name} no encontrada"

# ========== ENDPOINTS HTTP ==========

async def http_tools(request):
    return JSONResponse({"tools": TOOLS})

async def http_call_tool(request):
    body = await request.json()
    name = body.get("name", "")
    args = body.get("arguments", {})
    result = await execute_tool(name, args)
    return JSONResponse({"result": result})

# ========== ENDPOINTS SSE ==========

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
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "shopify-mcp", "version": "2.0.0"}}}
    elif method == "tools/list":
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        result = await execute_tool(name, args)
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