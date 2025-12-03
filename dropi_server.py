"""
Servidor MCP para Dropi.
Conecta la IA con la logística y billetera.
"""

import os
import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Cargar variables
load_dotenv()

DROPI_TOKEN = os.getenv("DROPI_TOKEN")
# Usamos el dominio que vimos en el token (app.dropi.gt)
DROPI_API_URL = "https://app.dropi.gt/api"

mcp = FastMCP("Dropi Logistics MCP")

@mcp.tool()
async def get_dropi_wallet() -> str:
    """Consulta el saldo disponible en la billetera de Dropi."""
    url = f"{DROPI_API_URL}/wallet"
    headers = {
        "Authorization": f"Bearer {DROPI_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # Ajusta estos campos según lo que veas en la respuesta real
                saldo = data.get("balance", "No disponible")
                return f"💰 **Billetera Dropi:**\nSaldo Actual: ${saldo}"
            else:
                return f"Error leyendo billetera: {response.status_code}"
        except Exception as e:
            return f"Error de conexión: {str(e)}"

@mcp.tool()
async def get_recent_orders() -> str:
    """Consulta los últimos pedidos."""
    url = f"{DROPI_API_URL}/orders"
    headers = {
        "Authorization": f"Bearer {DROPI_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                # Aquí intentamos leer, si falla devolvemos aviso
                try:
                    data = response.json()
                    orders = data.get("data", [])
                    return f"📦 **Pedidos Recientes:**\nSe encontraron {len(orders)} pedidos."
                except:
                    return "Dropi respondió pero no se pudieron leer los pedidos."
            else:
                return f"Error leyendo pedidos: {response.status_code}"
        except Exception as e:
            return f"Error de conexión: {str(e)}"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)