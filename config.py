"""
Configuracion del Super Agente de IA - v2.0
Ahora con Meta, Shopify y Dropi
"""
import os
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

class Settings:
    # API Keys
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_number: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
    
    # Servidores MCP
    shopify_mcp_url: str = os.getenv("SHOPIFY_MCP_URL", "https://mcp-dropshipping-production.up.railway.app")
    meta_mcp_url: str = os.getenv("META_MCP_URL", "https://server-meta-production-4773.up.railway.app")
    dropi_mcp_url: str = os.getenv("DROPI_MCP_URL", "https://server-dropi-production.up.railway.app")
    n8n_mcp_url: str = os.getenv("N8N_MCP_URL", "https://server-n8n-production.up.railway.app")
    
    # Modelo
    model_name: str = "claude-sonnet-4-20250514"
    
    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", 8000))
    
    # Debug
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

@lru_cache()
def get_settings():
    return Settings()

# Variables directas
settings = get_settings()
ANTHROPIC_API_KEY = settings.anthropic_api_key
TWILIO_ACCOUNT_SID = settings.twilio_account_sid
TWILIO_AUTH_TOKEN = settings.twilio_auth_token
TWILIO_WHATSAPP_NUMBER = settings.twilio_whatsapp_number
SHOPIFY_MCP_URL = settings.shopify_mcp_url
META_MCP_URL = settings.meta_mcp_url
DROPI_MCP_URL = settings.dropi_mcp_url
N8N_MCP_URL = settings.n8n_mcp_url
MODEL_NAME = settings.model_name

# Lista de servidores MCP - CON N8N PARA GRÁFICOS
MCP_SERVERS = {
    "shopify": {
        "url": SHOPIFY_MCP_URL,
        "name": "Shopify",
        "description": "Ventas, pedidos, productos, clientes, inventario de la tienda online"
    },
    "meta": {
        "url": META_MCP_URL,
        "name": "Meta Ads", 
        "description": "Publicidad en Facebook e Instagram: gastos, CPA, campañas, rendimiento"
    },
    "dropi": {
        "url": DROPI_MCP_URL,
        "name": "Dropi",
        "description": "Fulfillment y logística: órdenes enviadas, entregas, devoluciones, pagos, cartera"
    },
    "n8n": {
        "url": N8N_MCP_URL,
        "name": "N8N",
        "description": "Automatizaciones y gráficos: genera visualizaciones de datos, charts, reportes visuales"
    }
}
