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
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

# ========================================
# CORS - PARA DASHBOARD
# ========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dashboard-empresarial-mcp-production.up.railway.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "async_mode": True,
        "endpoints": {
            "whatsapp_webhook": "/webhook/whatsapp",
            "dashboard_data": "/api/dashboard-data",
            "health": "/health",
            "tools": "/tools"
        }
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


# ========================================
# ENDPOINT DASHBOARD CON DATOS REALES
# ========================================
@app.post("/api/dashboard-data")
async def get_dashboard_data(request: Request):
    """
    Endpoint para el dashboard empresarial.
    Retorna datos REALES de todas las plataformas (Meta, Shopify, Dropi).
    """
    try:
        body = await request.json()
        
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        period_label = body.get("period_label", "")
        
        logger.info(f"📊 Dashboard solicitando datos: {start_date} - {end_date} ({period_label})")
        
        # =================================================================
        # PASO 1: OBTENER DATOS DE DROPI
        # =================================================================
        
        dropi_data = {
            "pedidos": 0,
            "entregas": 0,
            "devoluciones": 0,
            "entradas": [],
            "salidas": [],
            "saldo": 0,
            "ingresos_totales": 0,
            "egresos_totales": 0
        }
        
        try:
            # Obtener wallet actual
            wallet_result = await mcp_client.call_tool("dropi", "get_wallet", {})
            if wallet_result:
                dropi_data["saldo"] = float(wallet_result.get("balance", 0))
            
            # Obtener historial de transacciones
            wallet_history = await mcp_client.call_tool("dropi", "get_wallet_history", {
                "start_date": start_date,
                "end_date": end_date
            })
            
            if wallet_history and isinstance(wallet_history, list):
                for transaction in wallet_history:
                    tipo = transaction.get("type", "").lower()
                    monto = float(transaction.get("amount", 0))
                    fecha = transaction.get("date", "")
                    concepto = transaction.get("description", "")
                    
                    trans_obj = {
                        "fecha": fecha,
                        "monto": monto,
                        "concepto": concepto
                    }
                    
                    # Clasificar entrada vs salida
                    if tipo in ["payment", "income", "credit"]:
                        dropi_data["entradas"].append(trans_obj)
                        dropi_data["ingresos_totales"] += monto
                    elif tipo in ["charge", "expense", "debit"]:
                        dropi_data["salidas"].append(trans_obj)
                        dropi_data["egresos_totales"] += monto
            
            # Obtener órdenes del período
            orders_result = await mcp_client.call_tool("dropi", "get_orders", {
                "start_date": start_date,
                "end_date": end_date
            })
            
            if orders_result and isinstance(orders_result, list):
                dropi_data["pedidos"] = len(orders_result)
                
                for order in orders_result:
                    status = order.get("status", "").lower()
                    if status in ["delivered", "entregado"]:
                        dropi_data["entregas"] += 1
                    elif status in ["returned", "devuelto"]:
                        dropi_data["devoluciones"] += 1
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Dropi: {e}")
        
        # =================================================================
        # PASO 2: OBTENER DATOS DE META ADS
        # =================================================================
        
        meta_data = {
            "gasto": 0,
            "presupuesto": 0,
            "roas": 0,
            "cpm": 0,
            "ctr": 0,
            "cpa": 0,
            "historico": []
        }
        
        try:
            # Determinar el período para Meta
            if period_label in ["Hoy", "Today"]:
                period = "today"
            elif period_label in ["Ayer", "Yesterday"]:
                period = "yesterday"
            elif "7" in period_label:
                period = "last_7d"
            elif "30" in period_label:
                period = "last_30d"
            else:
                period = "custom"
            
            # Obtener gasto publicitario
            if period == "custom":
                spend_result = await mcp_client.call_tool("meta", "get_ad_spend_by_period", {
                    "period": period,
                    "start_date": start_date,
                    "end_date": end_date
                })
            else:
                spend_result = await mcp_client.call_tool("meta", "get_ad_spend_by_period", {
                    "period": period
                })
            
            if spend_result:
                meta_data["gasto"] = float(spend_result.get("spend", 0))
                meta_data["cpm"] = float(spend_result.get("cpm", 0))
                meta_data["ctr"] = float(spend_result.get("ctr", 0))
                
                # Calcular CPA (si hay pedidos)
                if dropi_data["pedidos"] > 0:
                    meta_data["cpa"] = meta_data["gasto"] / dropi_data["pedidos"]
            
            # Obtener rendimiento de campañas
            campaigns_result = await mcp_client.call_tool("meta", "get_campaign_performance", {
                "period": period if period != "custom" else None,
                "start_date": start_date if period == "custom" else None,
                "end_date": end_date if period == "custom" else None
            })
            
            if campaigns_result and isinstance(campaigns_result, list):
                for campaign in campaigns_result:
                    meta_data["historico"].append({
                        "fecha": campaign.get("date", ""),
                        "gasto": float(campaign.get("spend", 0)),
                        "impresiones": int(campaign.get("impressions", 0)),
                        "clics": int(campaign.get("clicks", 0))
                    })
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Meta: {e}")
        
        # =================================================================
        # PASO 3: OBTENER DATOS DE TIKTOK (Si existe)
        # =================================================================
        
        tiktok_data = {
            "gasto": 0,
            "presupuesto": 0,
            "roas": 0,
            "cpm": 0,
            "ctr": 0,
            "cpa": 0,
            "historico": []
        }
        
        # TikTok por ahora queda mock hasta que agregues el servidor
        
        # =================================================================
        # PASO 4: OBTENER DATOS DE SHOPIFY
        # =================================================================
        
        shopify_data = {
            "pedidos": 0,
            "historico": []
        }
        
        try:
            # Obtener ventas del período
            sales_result = await mcp_client.call_tool("shopify", "get_sales_by_period", {
                "start_date": start_date,
                "end_date": end_date
            })
            
            if sales_result:
                shopify_data["pedidos"] = int(sales_result.get("total_orders", 0))
                
                # Si hay datos diarios
                if "daily_sales" in sales_result:
                    for day in sales_result["daily_sales"]:
                        shopify_data["historico"].append({
                            "fecha": day.get("date", ""),
                            "pedidos": int(day.get("orders", 0)),
                            "monto": float(day.get("amount", 0))
                        })
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Shopify: {e}")
        
        # =================================================================
        # PASO 5: CALCULAR MÉTRICAS MASTER
        # =================================================================
        
        # Gastos totales en publicidad
        gastos_ads = meta_data["gasto"] + tiktok_data["gasto"]
        
        # Ingresos y egresos de Dropi
        ingresos_dropi = dropi_data["ingresos_totales"]
        egresos_dropi = dropi_data["egresos_totales"]
        
        # Profit Neto = Ingresos - Egresos - Gastos Ads
        profit_neto = ingresos_dropi - egresos_dropi - gastos_ads
        
        # ROI = (Profit / Gastos Ads) * 100
        roi = (profit_neto / gastos_ads * 100) if gastos_ads > 0 else 0
        
        # ROAS = Ingresos / Gastos Ads
        roas = (ingresos_dropi / gastos_ads) if gastos_ads > 0 else 0
        
        # Actualizar ROAS en Meta y TikTok
        meta_data["roas"] = roas
        tiktok_data["roas"] = roas
        
        # =================================================================
        # PASO 6: CONSTRUIR RESPUESTA
        # =================================================================
        
        response_data = {
            "success": True,
            "period": {
                "start": start_date,
                "end": end_date,
                "label": period_label
            },
            "master": {
                "gastosAds": round(gastos_ads, 2),
                "ingresosDropi": round(ingresos_dropi, 2),
                "egresosDropi": round(egresos_dropi, 2),
                "profitNeto": round(profit_neto, 2),
                "roi": round(roi, 2)
            },
            "dropi": dropi_data,
            "meta": meta_data,
            "tiktok": tiktok_data,
            "shopify": shopify_data
        }
        
        logger.info(f"✅ Datos procesados - Profit: ${profit_neto:.2f}, ROI: {roi:.1f}%")
        
        return JSONResponse(response_data)
        
    except Exception as e:
        logger.error(f"❌ Error en dashboard-data: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": "Error procesando datos del dashboard"
        }, status_code=500)


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