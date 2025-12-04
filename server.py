"""
Super Agente de IA - Servidor FastAPI

Punto de entrada principal que expone:
- Webhook para Twilio WhatsApp
- Endpoints de health check
- API para gestión de conversaciones
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

from config import get_settings
from agent import conversation_manager
from mcp_client import mcp_client

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# LIFECYCLE DEL SERVIDOR
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación.
    
    - Startup: Inicializa conexiones MCP
    - Shutdown: Cierra conexiones limpiamente
    """
    logger.info("🚀 Iniciando Super Agente de IA...")
    
    try:
        # Inicializar cliente MCP
        await mcp_client.initialize()
        logger.info("✅ Cliente MCP inicializado")
    except Exception as e:
        logger.warning(f"⚠️ Error inicializando MCP (continuando sin herramientas): {e}")
    
    yield
    
    # Cleanup
    logger.info("🛑 Cerrando conexiones...")
    await mcp_client.close()
    logger.info("✅ Servidor cerrado correctamente")


# =============================================================================
# APLICACIÓN FASTAPI
# =============================================================================

app = FastAPI(
    title="Super Agente de IA",
    description="Agente de IA para WhatsApp con herramientas MCP",
    version="1.0.0",
    lifespan=lifespan
)

settings = get_settings()


# =============================================================================
# VALIDACIÓN DE TWILIO
# =============================================================================

def validate_twilio_request(request: Request, form_data: dict) -> bool:
    """
    Valida que la request venga realmente de Twilio.
    
    En producción, SIEMPRE debes validar las requests.
    """
    if settings.debug:
        return True  # Skip en desarrollo
    
    validator = RequestValidator(settings.twilio_auth_token)
    
    # Obtener la URL completa
    url = str(request.url)
    
    # Obtener la firma de Twilio
    signature = request.headers.get("X-Twilio-Signature", "")
    
    return validator.validate(url, form_data, signature)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Health check básico."""
    return {
        "status": "online",
        "service": "Super Agente de IA",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check detallado para Railway."""
    mcp_status = "connected" if mcp_client._initialized else "disconnected"
    tools_count = sum(len(tools) for tools in mcp_client.tools_cache.values())
    
    return {
        "status": "healthy",
        "mcp_client": mcp_status,
        "tools_available": tools_count,
        "servers_connected": list(mcp_client.sessions.keys())
    }


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    To: str = Form(None),
    MessageSid: str = Form(None),
):
    """
    Webhook principal para mensajes de WhatsApp via Twilio.
    
    Recibe mensajes entrantes, los procesa con el agente,
    y retorna la respuesta en formato TwiML.
    
    Args:
        From: Número de WhatsApp del remitente (whatsapp:+1234567890)
        Body: Contenido del mensaje
        To: Número de WhatsApp del destinatario (tu número Twilio)
        MessageSid: ID único del mensaje en Twilio
    """
    # Validar request de Twilio
    form_data = {
        "From": From,
        "Body": Body,
        "To": To or "",
        "MessageSid": MessageSid or ""
    }
    
    if not validate_twilio_request(request, form_data):
        logger.warning(f"Request inválida rechazada desde {From}")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    
    # Extraer el user_id (número de WhatsApp sin el prefijo)
    user_id = From.replace("whatsapp:", "")
    
    logger.info(f"📩 Mensaje de {user_id}: {Body[:50]}...")
    
    try:
        # Procesar mensaje con el agente
        response_text = await conversation_manager.process_message(
            user_id=user_id,
            message=Body
        )
        
        logger.info(f"📤 Respuesta para {user_id}: {response_text[:50]}...")
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        response_text = "Lo siento, ocurrió un error. Por favor intenta de nuevo en unos momentos."
    
    # Crear respuesta TwiML
    twiml_response = MessagingResponse()
    twiml_response.message(response_text)
    
    return Response(
        content=str(twiml_response),
        media_type="application/xml"
    )


@app.get("/conversations/{user_id}/history")
async def get_conversation_history(user_id: str):
    """
    Obtiene el historial de conversación de un usuario.
    
    Útil para debugging y análisis.
    """
    history = await conversation_manager.get_conversation_history(user_id)
    return {
        "user_id": user_id,
        "message_count": len(history),
        "messages": history
    }


@app.delete("/conversations/{user_id}")
async def clear_conversation(user_id: str):
    """Limpia el historial de conversación de un usuario."""
    await conversation_manager.clear_conversation(user_id)
    return {"status": "cleared", "user_id": user_id}


@app.get("/tools")
async def list_tools():
    """Lista todas las herramientas MCP disponibles."""
    tools = await mcp_client.get_all_tools()
    return {
        "total": len(tools),
        "tools": [
            {
                "name": t["name"],
                "description": t["description"],
                "server": t["server"]
            }
            for t in tools
        ]
    }


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
