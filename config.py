"""
Configuracion del Super Agente de IA
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# Servidores MCP
SHOPIFY_MCP_URL = os.getenv("SHOPIFY_MCP_URL", "https://mcp-dropshipping-production.up.railway.app")
META_MCP_URL = os.getenv("META_MCP_URL", "https://server-meta-production-4773.up.railway.app")

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

# Modelo de IA
MODEL_NAME = "claude-sonnet-4-20250514"