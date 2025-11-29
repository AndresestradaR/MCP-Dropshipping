"""
Servidor MCP para Shopify.
Conecta la IA con los datos reales de tu tienda.
VERSION CORREGIDA (FastMCP + Uvicorn)
"""

import httpx
import os
import uvicorn
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

SHOPIFY_SHOP_URL = os.getenv("SHOPIFY_SHOP_URL")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")

# Inicializar el servidor usando FastMCP
mcp = FastMCP("Shopify MCP")

# --- HERRAMIENTAS (TOOLS) ---

@mcp.tool()
async def get_total_sales_today() -> str:
    """Obtiene el total de ventas del día de hoy en Shopify."""
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
                return f"Error consultando Shopify: {response.status_code} - {response.text}"
                
            data = response.json()
            orders = data.get("orders", [])
            
            total_sales = 0.0
            order_count = len(orders)
            
            for order in orders:
                total_sales += float(order.get("total_price", 0))
                
            return f"Resumen de ventas HOY ({today}):\n💰 Total Vendido: ${total_sales:,.2f}\n📦 Pedidos: {order_count}"
        except Exception as e:
            return f"Error de conexión: {str(e)}"


@mcp.tool()
async def check_product_inventory(product_name: str) -> str:
    """Busca un producto por nombre y dice cuánto inventario tiene."""
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
            
            found_products = []
            
            for p in products:
                if product_name.lower() in p["title"].lower():
                    variants = p.get("variants", [])
                    total_inventory = sum(v.get("inventory_quantity", 0) for v in variants)
                    found_products.append(f"- {p['title']}: {total_inventory} unidades disponibles.")
            
            if not found_products:
                return f"No encontré productos que se llamen '{product_name}'."
                
            return "Inventario encontrado:\n" + "\n".join(found_products)
        except Exception as e:
            return f"Error buscando productos: {str(e)}"


# --- ARRANQUE ---

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    # FastMCP crea una app ASGI, la corremos con uvicorn
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=port)
