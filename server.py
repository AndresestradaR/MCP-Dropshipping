"""
Super Agente IA - Cerebro Principal
MCP + LangGraph + FastAPI
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from agent import create_agent
from config import settings
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear app de FastAPI
app = FastAPI(
    title="Super Agente IA - Cerebro",
    description="Agente inteligente con LangGraph + MCP para dropshipping",
    version="1.0.0"
)

# ========================================
# CORS - CONFIGURACIÓN CRÍTICA
# ========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dashboard-empresarial-mcp-production.up.railway.app",  # Tu dashboard
        "http://localhost:3000",  # Para desarrollo local
        "http://localhost:5173",  # Vite dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear agente al iniciar
agent = None

@app.on_event("startup")
async def startup_event():
    """Inicializar el agente al arrancar"""
    global agent
    try:
        logger.info("🚀 Iniciando Super Agente IA...")
        agent = await create_agent()
        logger.info("✅ Agente inicializado correctamente")
    except Exception as e:
        logger.error(f"❌ Error al inicializar agente: {e}")
        raise

@app.get("/")
async def root():
    """Endpoint de health check"""
    return {
        "status": "online",
        "service": "Super Agente IA - Cerebro",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook",
            "dashboard_data": "/api/dashboard-data"
        }
    }

@app.post("/webhook")
async def webhook_twilio(request: Request):
    """
    Webhook para recibir mensajes de Twilio (WhatsApp)
    """
    try:
        form_data = await request.form()
        message = form_data.get("Body", "")
        from_number = form_data.get("From", "")
        
        logger.info(f"📩 Mensaje recibido de {from_number}: {message}")
        
        # Procesar con el agente
        if agent is None:
            return JSONResponse({
                "error": "Agente no inicializado"
            }, status_code=500)
        
        response = await agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        })
        
        # Obtener última respuesta del agente
        agent_response = response["messages"][-1].content
        
        logger.info(f"🤖 Respuesta del agente: {agent_response}")
        
        # Responder en formato TwiML
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{agent_response}</Message>
</Response>"""
        
        return JSONResponse(
            content=twiml,
            media_type="application/xml"
        )
        
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}")
        return JSONResponse({
            "error": str(e)
        }, status_code=500)

@app.post("/api/dashboard-data")
async def get_dashboard_data(request: Request):
    """
    Endpoint para el dashboard empresarial
    Retorna datos de todas las plataformas
    """
    try:
        body = await request.json()
        
        # Extraer parámetros
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        period_label = body.get("period_label", "")
        
        logger.info(f"📊 Dashboard solicitando datos: {start_date} - {end_date}")
        
        # TODO: Implementar llamadas a las herramientas MCP
        # Por ahora retornamos estructura mock
        
        # Aquí llamarías a tus herramientas MCP:
        # dropi_data = await agent.invoke_tool("dropi_get_wallet_transactions", {...})
        # meta_data = await agent.invoke_tool("meta_get_insights", {...})
        # etc.
        
        response_data = {
            "success": True,
            "period": {
                "start": start_date,
                "end": end_date,
                "label": period_label
            },
            "master": {
                "gastosAds": 0,  # Meta + TikTok
                "ingresosDropi": 0,
                "egresosDropi": 0,
                "profitNeto": 0,
                "roi": 0
            },
            "dropi": {
                "pedidos": 0,
                "entregas": 0,
                "devoluciones": 0,
                "entradas": [],  # Transacciones de entrada
                "salidas": [],   # Transacciones de salida
                "saldo": 0
            },
            "meta": {
                "gasto": 0,
                "presupuesto": 0,
                "roas": 0,
                "cpm": 0,
                "ctr": 0,
                "cpa": 0,
                "historico": []
            },
            "tiktok": {
                "gasto": 0,
                "presupuesto": 0,
                "roas": 0,
                "cpm": 0,
                "ctr": 0,
                "cpa": 0,
                "historico": []
            },
            "shopify": {
                "pedidos": 0,
                "historico": []
            }
        }
        
        return JSONResponse(response_data)
        
    except Exception as e:
        logger.error(f"❌ Error en dashboard-data: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/health")
async def health_check():
    """Health check para Railway"""
    return {"status": "healthy", "agent": "initialized" if agent else "not_initialized"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
