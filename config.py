"""
Configuracion del Super Agente de IA
"""
import os
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

class Settings:
    # API Keys (minusculas para compatibilidad con agent.py)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_number: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
    
    # Servidores MCP
    shopify_mcp_url: str = os.getenv("SHOPIFY_MCP_URL", "https://mcp-dropshipping-production.up.railway.app")
    meta_mcp_url: str = os.getenv("META_MCP_URL", "https://server-meta-production-4773.up.railway.app")
    
    # Modelo
    model_name: str = "claude-sonnet-4-20250514"
    
    # Aliases en mayusculas por si acaso
    ANTHROPIC_API_KEY = anthropic_api_key
    TWILIO_ACCOUNT_SID = twilio_account_sid
    TWILIO_AUTH_TOKEN = twilio_auth_token
    TWILIO_WHATSAPP_NUMBER = twilio_whatsapp_number
    SHOPIFY_MCP_URL = shopify_mcp_url
    META_MCP_URL = meta_mcp_url
    MODEL_NAME = model_name

@lru_cache()
def get_settings():
    return Settings()

# Variables directas para compatibilidad
settings = get_settings()
ANTHROPIC_API_KEY = settings.anthropic_api_key
TWILIO_ACCOUNT_SID = settings.twilio_account_sid
TWILIO_AUTH_TOKEN = settings.twilio_auth_token
TWILIO_WHATSAPP_NUMBER = settings.twilio_whatsapp_number
SHOPIFY_MCP_URL = settings.shopify_mcp_url
META_MCP_URL = settings.meta_mcp_url
MODEL_NAME = settings.model_name

# Lista de servidores MCP disponibles
MCP_SERVERS = {
    "shopify": {
        "url": SHOPIFY_MCP_URL,
        "name": "Shopify",
        "description": "Ventas, pedidos, productos, clientes, inventario"
    },
    "meta": {
        "url": META_MCP_URL,
        "name": "Meta Ads", 
        "description": "Publicidad en Facebook e Instagram, gastos, campanas"
    }
}