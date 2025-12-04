"""
Super Agente de IA - Servidor FastAPI v2.0
CON RESPUESTA ASÍNCRONA para evitar timeout de Twilio (15s)

Flujo:
1. Twilio envía mensaje → Webhook responde "⏳" en <1 segundo
2. Procesa en background (puede tardar 30+ segundos)
3. Envía respuesta real via Twilio API
"""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient

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
    """Gestiona el ciclo de vida de la aplicación."""
    logger.info("🚀 Iniciando Super Agente de IA v2.0...")
    
    try:
        await mcp_client.initialize()
        logger.info("✅ Cliente MCP inicializado")
    except Exception as e:
        logger.warning(f"⚠️ Error inicializando MCP: {e}")
    
    yield
    
    logger.info("🛑 Cerrando conexiones...")
    await mcp_client.close()
    logger.info("✅ Servidor cerrado correctamente")


# =============================================================================
# APLICACIÓN FASTAPI
# =============================================================================

app = FastAPI(
    title="Super Agente de IA",
    description="Agente de IA para WhatsApp con herramientas MCP",
    version="2.0.0",
    lifespan=lifespan
)

settings = get_settings()

# Cliente de Twilio para enviar mensajes de forma proactiva
twilio_client = None
if settings.twilio_account_sid and settings.twilio_auth_token:
    try:
        twilio_client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        logger.info("✅ Cliente Twilio inicializado")
    except Exception as e:
        logger.error(f"❌ Error inicializando Twilio: {e}")


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def validate_twilio_request(request: Request, form_data: dict) -> bool:
    """Valida que la request venga realmente de Twilio."""
    if settings.debug:
        return True
    
    validator = RequestValidator(settings.twilio_auth_token)
    url = str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    
    return validator.validate(url, form_data, signature)


async def send_whatsapp_message(to: str, body: str, from_number: str = None):
    """
    Envía un mensaje de WhatsApp usando la API de Twilio.
    
    Args:
        to: Número destino (formato: whatsapp:+1234567890)
        body: Contenido del mensaje
        from_number: Número de origen (default: el configurado en settings)
    """
    if not twilio_client:
        logger.error("❌ Cliente Twilio no disponible")
        return False
    
    from_number = from_number or settings.twilio_whatsapp_number
    
    try:
        # Twilio tiene límite de ~1600 caracteres por mensaje
        # Si es muy largo, lo partimos
        MAX_LENGTH = 1500
        
        if len(body) <= MAX_LENGTH:
            messages_to_send = [body]
        else:
            # Partir en chunks
            messages_to_send = []
            remaining = body
            part = 1
            while remaining:
                if len(remaining) <= MAX_LENGTH:
                    messages_to_send.append(remaining)
                    remaining = ""
                else:
                    # Buscar un buen punto de corte (salto de línea o espacio)
                    cut_point = remaining[:MAX_LENGTH].rfind('\n')
                    if cut_point < MAX_LENGTH // 2:
                        cut_point = remaining[:MAX_LENGTH].rfind(' ')
                    if cut_point < MAX_LENGTH // 2:
                        cut_point = MAX_LENGTH
                    
                    messages_to_send.append(remaining[:cut_point])
                    remaining = remaining[cut_point:].strip()
                part += 1
        
        # Enviar cada parte
        for i, msg in enumerate(messages_to_send):
            if len(messages_to_send) > 1:
                prefix = f"[{i+1}/{len(messages_to_send)}] "
                msg = prefix + msg
            
            twilio_client.messages.create(
                body=msg,
                from_=from_number,
                to=to
            )
            logger.info(f"📤 Mensaje enviado a {to}: {msg[:50]}...")
            
            # Pequeña pausa entre mensajes para mantener orden
            if i < len(messages_to_send) - 1:
                await asyncio.sleep(0.5)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje: {e}")
        return False


async def process_message_background(user_id: str, message: str, reply_to: str):
    """
    Procesa el mensaje en background y envía la respuesta via API.
    
    Esta función se ejecuta DESPUÉS de responder al webhook,
    por lo que puede tardar todo lo que necesite.
    """
    logger.info(f"🔄 Procesando en background para {user_id}...")
    
    try:
        # Procesar con el agente (esto puede tardar 30+ segundos)
        response_text = await conversation_manager.process_message(
            user_id=user_id,
            message=message
        )
        
        logger.info(f"✅ Respuesta generada para {user_id}: {response_text[:100]}...")
        
        # Enviar respuesta via Twilio API
        await send_whatsapp_message(
            to=reply_to,
            body=response_text
        )
        
    except Exception as e:
        logger.error(f"❌ Error en background para {user_id}: {e}")
        # Intentar enviar mensaje de error
        await send_whatsapp_message(
            to=reply_to,
            body="Lo siento, ocurrió un error procesando tu mensaje. Por favor intenta de nuevo."
        )


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Health check básico."""
    return {
        "status": "online",
        "service": "Super Agente de IA",
        "version": "2.0.0",
        "async_mode": True
    }


@app.get("/health")
async def health_check():
    """Health check detallado."""
    mcp_status = "connected" if mcp_client._initialized else "disconnected"
    tools_count = sum(len(tools) for tools in mcp_client.tools_cache.values())
    
    return {
        "status": "healthy",
        "mcp_client": mcp_status,
        "tools_available": tools_count,
        "servers_connected": list(mcp_client.sessions.keys()),
        "twilio_client": "ready" if twilio_client else "not configured"
    }


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(...),
    To: str = Form(None),
    MessageSid: str = Form(None),
):
    """
    Webhook para mensajes de WhatsApp via Twilio.
    
    VERSIÓN ASÍNCRONA:
    - Responde inmediatamente a Twilio (evita timeout de 15s)
    - Procesa el mensaje en background
    - Envía la respuesta real via Twilio API
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
    
    user_id = From.replace("whatsapp:", "")
    logger.info(f"📩 Mensaje de {user_id}: {Body[:50]}...")
    
    # Agregar tarea en background
    background_tasks.add_task(
        process_message_background,
        user_id=user_id,
        message=Body,
        reply_to=From  # whatsapp:+1234567890
    )
    
    # Responder INMEDIATAMENTE a Twilio con mensaje vacío
    # Esto evita el timeout de 15 segundos
    # La respuesta real se enviará via API en el background task
    twiml_response = MessagingResponse()
    # NO agregamos mensaje - respuesta vacía
    # twiml_response.message("⏳ Procesando...")  # Opcional: descomentar para feedback
    
    return Response(
        content=str(twiml_response),
        media_type="application/xml"
    )


@app.get("/conversations/{user_id}/history")
async def get_conversation_history(user_id: str):
    """Obtiene el historial de conversación de un usuario."""
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


# Endpoint de prueba para enviar mensajes manualmente
@app.post("/send")
async def send_message(to: str, body: str):
    """
    Endpoint de prueba para enviar mensajes de WhatsApp.
    
    Uso: POST /send?to=whatsapp:+1234567890&body=Hola
    """
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    
    success = await send_whatsapp_message(to=to, body=body)
    return {"success": success, "to": to}


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