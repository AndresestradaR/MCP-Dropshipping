"""
Configuración del Super Agente de IA
Versión con soporte para Dropi
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
    dropi_mcp_url: str = os.getenv("DROPI_MCP_URL", "")  # NUEVO: URL del servidor Dropi
    tiktok_mcp_url: str = os.getenv("TIKTOK_MCP_URL", "")  # FUTURO: TikTok Ads
    
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
TIKTOK_MCP_URL = settings.tiktok_mcp_url
MODEL_NAME = settings.model_name

# Lista de servidores MCP
MCP_SERVERS = {
    "shopify": {
        "url": SHOPIFY_MCP_URL,
        "name": "Shopify",
        "description": "Ventas, pedidos, productos, clientes, inventario"
    },
    "meta": {
        "url": META_MCP_URL,
        "name": "Meta Ads", 
        "description": "Publicidad en Facebook e Instagram, gastos, campañas"
    }
}

# Agregar Dropi solo si está configurado
if DROPI_MCP_URL:
    MCP_SERVERS["dropi"] = {
        "url": DROPI_MCP_URL,
        "name": "Dropi",
        "description": "Logística, órdenes, billetera, devoluciones, pagos"
    }

# Agregar TikTok solo si está configurado (para futuro)
if TIKTOK_MCP_URL:
    MCP_SERVERS["tiktok"] = {
        "url": TIKTOK_MCP_URL,
        "name": "TikTok Ads",
        "description": "Publicidad en TikTok, gastos, campañas"
    }
