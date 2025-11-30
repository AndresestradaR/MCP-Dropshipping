"""
Configuracion del Super Agente de IA
"""
import os
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

class Settings:
    # API Keys
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
    
    # Servidores MCP
    SHOPIFY_MCP_URL: str = os.getenv("SHOPIFY_MCP_URL", "https://mcp-dropshipping-production.up.railway.app")
    META_MCP_URL: str = os.getenv("META_MCP_URL", "https://server-meta-production-4773.up.railway.app")
    
    # Modelo
    MODEL_NAME: str = "claude-sonnet-4-20250514"

@lru_cache()
def get_settings():
    return Settings()

# Variables directas para compatibilidad
settings = get_settings()
ANTHROPIC_API_KEY = settings.ANTHROPIC_API_KEY
TWILIO_ACCOUNT_SID = settings.TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILIO_AUTH_TOKEN
TWILIO_WHATSAPP_NUMBER = settings.TWILIO_WHATSAPP_NUMBER
SHOPIFY_MCP_URL = settings.SHOPIFY_MCP_URL
META_MCP_URL = settings.META_MCP_URL
MODEL_NAME = settings.MODEL_NAME

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