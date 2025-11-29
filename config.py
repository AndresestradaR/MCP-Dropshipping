from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configuración del Super Agente de IA."""
    
    # Anthropic
    anthropic_api_key: str
    
    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str  # formato: whatsapp:+14155238886
    
    # MCP Servers (URLs de los servidores MCP remotos)
    shopify_mcp_url: str = "https://mi-shopify-mcp.railway.app/mcp"
    
    # Configuración del servidor
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Obtener configuración cacheada."""
    return Settings()