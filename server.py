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
import json
import re
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

def parse_formatted_text(text: str) -> dict:
    """
    Parsea texto formateado de las herramientas MCP.
    Soporta múltiples formatos y monedas ($, Q, etc).
    """
    result = {}
    
    # Gasto: $13,574.00 o Gasto: Q13,574.00
    gasto_match = re.search(r'Gasto:\s*[$Q]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if gasto_match:
        result['spend'] = float(gasto_match.group(1).replace(',', ''))
    
    # Impresiones: 1,188
    impresiones_match = re.search(r'Impresiones:\s*([\d,]+)', text, re.IGNORECASE)
    if impresiones_match:
        result['impressions'] = int(impresiones_match.group(1).replace(',', ''))
    
    # Clics: 54
    clics_match = re.search(r'Clics:\s*([\d,]+)', text, re.IGNORECASE)
    if clics_match:
        result['clicks'] = int(clics_match.group(1).replace(',', ''))
    
    # Saldo Disponible: Q14,993.71 o Saldo: $1,234.56
    saldo_match = re.search(r'Saldo\s*(?:Disponible)?:\s*[$Q]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if saldo_match:
        result['balance'] = float(saldo_match.group(1).replace(',', ''))
    
    # Total: $1,234.56 o Total bruto: $X
    total_match = re.search(r'Total(?:\s+\w+)?:\s*[$Q]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if total_match:
        result['total'] = float(total_match.group(1).replace(',', ''))
    
    # Pedidos totales: 10 o Pedidos: 10
    pedidos_match = re.search(r'Pedidos(?:\s+\w+)?:\s*([\d,]+)', text, re.IGNORECASE)
    if pedidos_match:
        result['total_orders'] = int(pedidos_match.group(1).replace(',', ''))
    
    # Monto: Q440.00 o Monto: $440
    monto_match = re.search(r'Monto:\s*[$Q]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if monto_match:
        result['amount'] = float(monto_match.group(1).replace(',', ''))
    
    # Entradas/Ingresos: $X
    entradas_match = re.search(r'(?:Entradas|Ingresos):\s*[$Q]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if entradas_match:
        result['income'] = float(entradas_match.group(1).replace(',', ''))
    
    # Salidas/Egresos: $X
    salidas_match = re.search(r'(?:Salidas|Egresos):\s*[$Q]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if salidas_match:
        result['expenses'] = float(salidas_match.group(1).replace(',', ''))
    
    return result


def parse_mcp_result(result):
    """
    Parsea el resultado de una llamada MCP.
    Puede ser: JSON string, dict, o texto formateado.
    """
    if result is None:
        return None
    
    # Si ya es un dict, retornarlo
    if isinstance(result, dict):
        return result
    
    # Si es un string, intentar múltiples estrategias
    if isinstance(result, str):
        # Estrategia 1: Parsear como JSON
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            pass
        
        # Estrategia 2: Parsear texto formateado
        parsed = parse_formatted_text(result)
        if parsed:
            logger.info(f"📝 Parseado texto formateado: {parsed}")
            return parsed
        
        # Estrategia 3: Retornar como texto
        logger.warning(f"⚠️ No se pudo parsear: {result[:100]}")
        return {"raw_text": result}
    
    return result


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
        MAX_LENGTH = 1500
        
        if len(body) <= MAX_LENGTH:
            messages_to_send = [body]
        else:
            # Partir en chunks
            messages_to_send = []
            remaining = body
            while remaining:
                if len(remaining) <= MAX_LENGTH:
                    messages_to_send.append(remaining)
                    remaining = ""
                else:
                    cut_point = remaining[:MAX_LENGTH].rfind('\n')
                    if cut_point < MAX_LENGTH // 2:
                        cut_point = remaining[:MAX_LENGTH].rfind(' ')
                    if cut_point < MAX_LENGTH // 2:
                        cut_point = MAX_LENGTH
                    
                    messages_to_send.append(remaining[:cut_point])
                    remaining = remaining[cut_point:].strip()
        
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
            
            if i < len(messages_to_send) - 1:
                await asyncio.sleep(0.5)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje: {e}")
        return False


async def process_message_background(user_id: str, message: str, reply_to: str):
    """
    Procesa el mensaje en background y envía la respuesta via API.
    """
    logger.info(f"🔄 Procesando en background para {user_id}...")
    
    try:
        response_text = await conversation_manager.process_message(
            user_id=user_id,
            message=message
        )
        
        logger.info(f"✅ Respuesta generada para {user_id}: {response_text[:100]}...")
        
        await send_whatsapp_message(
            to=reply_to,
            body=response_text
        )
        
    except Exception as e:
        logger.error(f"❌ Error en background para {user_id}: {e}")
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
    """
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
    
    background_tasks.add_task(
        process_message_background,
        user_id=user_id,
        message=Body,
        reply_to=From
    )
    
    twiml_response = MessagingResponse()
    
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
    Retorna datos REALES de todas las plataformas.
    """
    try:
        body = await request.json()
        
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        period_label = body.get("period_label", "")
        
        logger.info(f"📊 Dashboard solicitando datos: {start_date} - {end_date} ({period_label})")
        
        # =================================================================
        # DROPI - CON NOMBRES CORRECTOS
        # =================================================================
        
        dropi_data = {
            "pedidos": {"total": 0, "monto": 0},
            "entregas": {"total": 0, "monto": 0},
            "devoluciones": {"total": 0, "monto": 0},
            "entradas": [],
            "salidas": [],
            "saldo": 0,
            "ingresos_totales": 0,
            "egresos_totales": 0
        }
        
        try:
            # CORRECTO: get_dropi_wallet (no get_wallet)
            wallet_raw = await mcp_client.call_tool("dropi", "get_dropi_wallet", {})
            wallet_result = parse_mcp_result(wallet_raw)
            
            if wallet_result and isinstance(wallet_result, dict):
                # Usar balance capturado del texto formateado
                dropi_data["saldo"] = float(wallet_result.get("balance", 0))
                logger.info(f"💰 Saldo Dropi: Q{dropi_data['saldo']:,.2f} (${dropi_data['saldo']*0.13:.2f} USD)")
            
            # CORRECTO: get_dropi_wallet_history (no get_wallet_history)
            history_raw = await mcp_client.call_tool("dropi", "get_dropi_wallet_history", {})
            wallet_history = parse_mcp_result(history_raw)
            
            # Wallet history puede venir como lista o dict con lista
            if isinstance(wallet_history, dict):
                # Si capturamos income/expenses del texto formateado
                if "income" in wallet_history:
                    dropi_data["ingresos_totales"] = wallet_history["income"]
                if "expenses" in wallet_history:
                    dropi_data["egresos_totales"] = wallet_history["expenses"]
                
                # Extraer lista de transacciones si existe
                if "transactions" in wallet_history:
                    wallet_history = wallet_history["transactions"]
                elif "raw_text" in wallet_history:
                    # Texto formateado - intentar parsear manualmente
                    text = wallet_history["raw_text"]
                    
                    # Buscar palabras clave para clasificar
                    if any(word in text.lower() for word in ["pago", "payment", "ingreso", "venta", "cobro"]):
                        # Es un ingreso
                        if "amount" in wallet_history or "total" in wallet_history:
                            monto = wallet_history.get("amount", wallet_history.get("total", 0))
                            dropi_data["ingresos_totales"] += monto
                            dropi_data["entradas"].append({
                                "fecha": "N/A",
                                "monto": monto,
                                "concepto": "Transacción"
                            })
                    elif any(word in text.lower() for word in ["costo", "cost", "gasto", "expense", "cargo"]):
                        # Es un egreso
                        if "amount" in wallet_history or "total" in wallet_history:
                            monto = wallet_history.get("amount", wallet_history.get("total", 0))
                            dropi_data["egresos_totales"] += monto
                            dropi_data["salidas"].append({
                                "fecha": "N/A",
                                "monto": monto,
                                "concepto": "Transacción"
                            })
            
            if wallet_history and isinstance(wallet_history, list):
                for transaction in wallet_history:
                    tipo = str(transaction.get("type", "")).lower()
                    monto = float(transaction.get("amount", 0))
                    fecha = transaction.get("date", "")
                    concepto = transaction.get("description", "Transacción")
                    
                    trans_obj = {
                        "fecha": fecha,
                        "monto": abs(monto),
                        "concepto": concepto
                    }
                    
                    if tipo in ["payment", "income", "credit"] or monto > 0:
                        dropi_data["entradas"].append(trans_obj)
                        dropi_data["ingresos_totales"] += abs(monto)
                    elif tipo in ["charge", "expense", "debit"] or monto < 0:
                        dropi_data["salidas"].append(trans_obj)
                        dropi_data["egresos_totales"] += abs(monto)
                
                if dropi_data["ingresos_totales"] > 0 or dropi_data["egresos_totales"] > 0:
                    logger.info(f"💵 Ingresos Dropi: Q{dropi_data['ingresos_totales']:,.2f}")
                    logger.info(f"💸 Egresos Dropi: Q{dropi_data['egresos_totales']:,.2f}")
            
            # CORRECTO: get_dropi_orders (no get_orders)
            orders_raw = await mcp_client.call_tool("dropi", "get_dropi_orders", {})
            orders_result = parse_mcp_result(orders_raw)
            
            # Orders puede venir como lista o dict con lista
            if isinstance(orders_result, dict) and "orders" in orders_result:
                orders_result = orders_result["orders"]
            
            if orders_result and isinstance(orders_result, list):
                dropi_data["pedidos"]["total"] = len(orders_result)
                
                for order in orders_result:
                    status = str(order.get("status", "")).lower()
                    monto_order = float(order.get("total", order.get("amount", 0)))
                    
                    # Sumar al monto total
                    dropi_data["pedidos"]["monto"] += monto_order
                    
                    if status in ["delivered", "entregado"]:
                        dropi_data["entregas"]["total"] += 1
                        dropi_data["entregas"]["monto"] += monto_order
                    elif status in ["returned", "devuelto"]:
                        dropi_data["devoluciones"]["total"] += 1
                        dropi_data["devoluciones"]["monto"] += monto_order
                
                logger.info(f"📦 Pedidos: {dropi_data['pedidos']['total']}, Entregas: {dropi_data['entregas']['total']}")
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Dropi: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # =================================================================
        # META ADS
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
            # Determinar período
            if "7" in period_label:
                period = "last_7d"
            elif "30" in period_label:
                period = "last_30d"
            elif "Hoy" in period_label or "Today" in period_label:
                period = "today"
            elif "Ayer" in period_label or "Yesterday" in period_label:
                period = "yesterday"
            else:
                period = "last_7d"
            
            spend_raw = await mcp_client.call_tool("meta", "get_ad_spend_by_period", {
                "period": period
            })
            spend_result = parse_mcp_result(spend_raw)
            
            if spend_result and isinstance(spend_result, dict):
                meta_data["gasto"] = float(spend_result.get("spend", 0))
                meta_data["cpm"] = float(spend_result.get("cpm", 0))
                meta_data["ctr"] = float(spend_result.get("ctr", 0))
                
                if dropi_data["pedidos"]["total"] > 0:
                    meta_data["cpa"] = meta_data["gasto"] / dropi_data["pedidos"]["total"]
                
                logger.info(f"📢 Gasto Meta: ${meta_data['gasto']:.2f}")
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Meta: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # =================================================================
        # TIKTOK (Mock)
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
        
        # =================================================================
        # SHOPIFY
        # =================================================================
        
        shopify_data = {
            "pedidos": 0,
            "historico": []
        }
        
        try:
            # Determinar período Shopify
            if "Hoy" in period_label or "Today" in period_label:
                period_shopify = "today"
            elif "Ayer" in period_label or "Yesterday" in period_label:
                period_shopify = "yesterday"
            elif "7" in period_label:
                period_shopify = "week"
            elif "30" in period_label or "Mes" in period_label:
                period_shopify = "month"
            else:
                period_shopify = "week"
            
            sales_raw = await mcp_client.call_tool("shopify", "get_sales_by_period", {
                "period": period_shopify
            })
            sales_result = parse_mcp_result(sales_raw)
            
            if sales_result and isinstance(sales_result, dict):
                shopify_data["pedidos"] = int(sales_result.get("total_orders", 0))
                logger.info(f"🛒 Pedidos Shopify: {shopify_data['pedidos']}")
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Shopify: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # =================================================================
        # CALCULAR MÉTRICAS MASTER
        # =================================================================
        
        gastos_ads = meta_data["gasto"] + tiktok_data["gasto"]
        ingresos_dropi = dropi_data["ingresos_totales"]
        egresos_dropi = dropi_data["egresos_totales"]
        profit_neto = ingresos_dropi - egresos_dropi - gastos_ads
        roi = (profit_neto / gastos_ads * 100) if gastos_ads > 0 else 0
        roas = (ingresos_dropi / gastos_ads) if gastos_ads > 0 else 0
        
        meta_data["roas"] = roas
        tiktok_data["roas"] = roas
        
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


@app.post("/send")
async def send_message(to: str, body: str):
    """
    Endpoint de prueba para enviar mensajes de WhatsApp.
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
    

