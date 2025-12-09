"""
Servidor MCP para Meta Ads (Facebook/Instagram).
Conecta la IA con tus campañas publicitarias.
"""

import os
import json
import httpx
import asyncio
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

load_dotenv()

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")

sessions = {}

def get_account_id():
    account_id = META_AD_ACCOUNT_ID
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    return account_id

TOOLS = [
    {
        "name": "get_ad_spend_today",
        "description": "Obtiene el gasto publicitario de HOY en Meta Ads. Devuelve: Gasto, Impresiones, Clics y CPC promedio.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_ad_spend_by_period",
        "description": "Obtiene el gasto publicitario por periodo o fechas especificas. Usa start_date y end_date (YYYY-MM-DD) para rangos exactos, o period para presets (today, yesterday, last_7d, last_30d).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "Periodo predefinido: today, yesterday, last_7d, last_30d (opcional si usas start_date/end_date)"},
                "start_date": {"type": "string", "description": "Fecha inicio YYYY-MM-DD (ej: 2025-11-01)"},
                "end_date": {"type": "string", "description": "Fecha fin YYYY-MM-DD (ej: 2025-11-15)"}
            },
            "required": []
        }
    },
    {
        "name": "get_campaign_performance",
        "description": "Revisa que campañas estan activas y como van hoy. Ideal para saber cual apagar o escalar.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_adset_performance",
        "description": "Rendimiento por conjunto de anuncios (adsets) de hoy",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_ad_account_info",
        "description": "Informacion general de la cuenta de Meta Ads",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    }
]

async def get_ad_spend_today(args: dict) -> str:
    import datetime
    today = datetime.date.today().isoformat()
    
    account_id = get_account_id()
    url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "date_preset": "today",
        "fields": "spend,impressions,clicks,cpc,ctr,reach",
        "level": "account"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if "error" in data:
                return f"Error de Meta: {data['error'].get('message', 'Error desconocido')}"
            
            if not data.get("data"):
                return f"📊 META ADS HOY ({today}):\n💸 Gasto: $0.00\n👀 Impresiones: 0\n👆 Clics: 0\n\n(No hay datos o Meta no ha actualizado todavia)"
            
            stats = data["data"][0]
            spend = float(stats.get('spend', 0))
            impressions = int(stats.get('impressions', 0))
            clicks = int(stats.get('clicks', 0))
            cpc = float(stats.get('cpc', 0))
            ctr = float(stats.get('ctr', 0))
            reach = int(stats.get('reach', 0))
            
            return f"""📊 META ADS HOY ({today}):
💸 Gasto: ${spend:,.2f}
👀 Impresiones: {impressions:,}
👆 Clics: {clicks:,}
💰 CPC: ${cpc:.2f}
📈 CTR: {ctr:.2f}%
🎯 Alcance: {reach:,}"""
        except Exception as e:
            return f"Error de conexion: {str(e)}"

async def get_ad_spend_by_period(args: dict) -> str:
    # DEBUG
    print(f"📊 META get_ad_spend_by_period - Args recibidos: {args}")
    
    # Extraer argumentos - pueden venir directos o dentro de 'arguments'
    if "arguments" in args:
        args = args["arguments"]
    
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    period = args.get("period", "today")
    
    print(f"📊 start_date: {start_date}, end_date: {end_date}, period: {period}")
    
    account_id = get_account_id()
    url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "fields": "spend,impressions,clicks,cpc,ctr,reach,actions",
        "level": "account"
    }
    
    # Si se proporcionan fechas específicas, usar time_range
    if start_date and end_date:
        params["time_range"] = json.dumps({"since": start_date, "until": end_date})
        if start_date == end_date:
            label = start_date
        else:
            label = f"{start_date} a {end_date}"
    elif start_date:
        # Solo fecha inicio, hasta hoy
        import datetime
        today = datetime.date.today().isoformat()
        params["time_range"] = json.dumps({"since": start_date, "until": today})
        label = f"desde {start_date}"
    else:
        # Usar period predefinido
        period_map = {
            "today": "today",
            "yesterday": "yesterday",
            "last_7d": "last_7d",
            "last_30d": "last_30d",
            "week": "last_7d",
            "month": "last_30d"
        }
        date_preset = period_map.get(period, "today")
        params["date_preset"] = date_preset
        label = period.upper()
    
    print(f"📊 Query Meta: {params}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            print(f"📊 Meta response: {data}")
            
            if "error" in data:
                return f"Error de Meta: {data['error'].get('message', 'Error desconocido')}"
            
            if not data.get("data"):
                return f"📊 META ADS ({label}):\n💸 Sin datos para este periodo"
            
            stats = data["data"][0]
            spend = float(stats.get('spend', 0))
            impressions = int(stats.get('impressions', 0))
            clicks = int(stats.get('clicks', 0))
            
            # Buscar conversiones
            purchases = 0
            leads = 0
            if 'actions' in stats:
                for action in stats['actions']:
                    if action['action_type'] in ['purchase', 'omni_purchase']:
                        purchases = int(action['value'])
                    if action['action_type'] == 'lead':
                        leads = int(action['value'])
            
            result = f"""📊 META ADS ({label}):
💸 Gasto: ${spend:,.2f}
👀 Impresiones: {impressions:,}
👆 Clics: {clicks:,}"""
            
            if purchases > 0:
                cpa = spend / purchases
                result += f"\n🛒 Compras: {purchases}\n💰 CPA: ${cpa:.2f}"
            
            if leads > 0:
                cpl = spend / leads
                result += f"\n📝 Leads: {leads}\n💰 CPL: ${cpl:.2f}"
            
            # Agregar datos JSON para el dashboard
            result_json = {
                "period": label,
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "purchases": purchases,
                "leads": leads,
                "cpa": spend / purchases if purchases > 0 else None
            }
            
            result += f"\n\n---JSON_DATA---\n{json.dumps(result_json)}"
            
            return result
        except Exception as e:
            return f"Error: {str(e)}"

async def get_campaign_performance(args: dict) -> str:
    account_id = get_account_id()
    url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "date_preset": "today",
        "fields": "campaign_name,spend,impressions,clicks,cpc,actions",
        "level": "campaign",
        "limit": 50
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if "error" in data:
                return f"Error de Meta: {data['error'].get('message', 'Error desconocido')}"
            
            if not data.get("data"):
                return "📊 No hay campañas activas con gasto hoy."
            
            result = "🔥 RENDIMIENTO POR CAMPAÑA (HOY):\n\n"
            
            for campaign in data["data"]:
                spend = float(campaign.get('spend', 0))
                clicks = int(campaign.get('clicks', 0))
                
                purchases = 0
                if 'actions' in campaign:
                    for action in campaign['actions']:
                        if action['action_type'] in ['purchase', 'omni_purchase']:
                            purchases = int(action['value'])
                
                cpa = f"${spend/purchases:.2f}" if purchases > 0 else "N/A"
                
                result += f"📌 {campaign['campaign_name']}\n"
                result += f"   💸 Gasto: ${spend:.2f}\n"
                result += f"   👆 Clics: {clicks}\n"
                result += f"   🛒 Compras: {purchases}\n"
                result += f"   💰 CPA: {cpa}\n\n"
            
            return result
        except Exception as e:
            return f"Error: {str(e)}"

async def get_adset_performance(args: dict) -> str:
    account_id = get_account_id()
    url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "date_preset": "today",
        "fields": "adset_name,campaign_name,spend,impressions,clicks,actions",
        "level": "adset",
        "limit": 50
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if "error" in data:
                return f"Error de Meta: {data['error'].get('message', 'Error desconocido')}"
            
            if not data.get("data"):
                return "📊 No hay adsets activos con gasto hoy."
            
            result = "📊 RENDIMIENTO POR ADSET (HOY):\n\n"
            
            for adset in data["data"]:
                spend = float(adset.get('spend', 0))
                
                result += f"📌 {adset.get('adset_name', 'Sin nombre')}\n"
                result += f"   📢 Campaña: {adset.get('campaign_name', 'N/A')}\n"
                result += f"   💸 Gasto: ${spend:.2f}\n"
                result += f"   👀 Impresiones: {adset.get('impressions', 0)}\n\n"
            
            return result
        except Exception as e:
            return f"Error: {str(e)}"

async def get_ad_account_info(args: dict) -> str:
    account_id = get_account_id()
    url = f"https://graph.facebook.com/v19.0/{account_id}"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "fields": "name,account_status,currency,timezone_name,amount_spent,balance,spend_cap"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if "error" in data:
                return f"Error de Meta: {data['error'].get('message', 'Error desconocido')}"
            
            status_map = {1: "Activa", 2: "Deshabilitada", 3: "Sin configurar", 7: "Pendiente"}
            status = status_map.get(data.get('account_status', 0), "Desconocido")
            
            amount_spent = float(data.get('amount_spent', 0)) / 100  # Meta lo devuelve en centavos
            
            return f"""📱 CUENTA DE META ADS:
📛 Nombre: {data.get('name', 'N/A')}
📊 Estado: {status}
💰 Moneda: {data.get('currency', 'N/A')}
🌍 Zona horaria: {data.get('timezone_name', 'N/A')}
💸 Gastado total: ${amount_spent:,.2f}
🆔 ID: {account_id}"""
        except Exception as e:
            return f"Error: {str(e)}"

# ========== DISPATCHER ==========

TOOL_HANDLERS = {
    "get_ad_spend_today": get_ad_spend_today,
    "get_ad_spend_by_period": get_ad_spend_by_period,
    "get_campaign_performance": get_campaign_performance,
    "get_adset_performance": get_adset_performance,
    "get_ad_account_info": get_ad_account_info,
}

async def execute_tool(name: str, args: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler:
        try:
            return await handler(args)
        except Exception as e:
            return f"Error: {str(e)}"
    return f"Herramienta {name} no encontrada"

# ========== ENDPOINTS ==========

async def http_tools(request):
    return JSONResponse({"tools": TOOLS})

async def http_call_tool(request):
    body = await request.json()
    name = body.get("name", "")
    args = body.get("arguments", {})
    result = await execute_tool(name, args)
    return JSONResponse({"result": result})

async def sse_endpoint(request):
    queue = asyncio.Queue()
    session_id = str(id(queue))
    sessions[session_id] = queue
    async def event_generator():
        try:
            yield {"event": "endpoint", "data": f"/messages/{session_id}"}
            while True:
                data = await queue.get()
                yield {"event": "message", "data": json.dumps(data)}
        except asyncio.CancelledError:
            pass
        finally:
            sessions.pop(session_id, None)
    return EventSourceResponse(event_generator())

async def messages_endpoint(request):
    session_id = request.path_params["session_id"]
    if session_id not in sessions:
        return Response("Session not found", status_code=404)
    body = await request.json()
    method = body.get("method", "")
    msg_id = body.get("id")
    if method == "initialize":
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "meta-mcp", "version": "1.0.0"}}}
    elif method == "tools/list":
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = body.get("params", {})
        result = await execute_tool(params.get("name", ""), params.get("arguments", {}))
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": result}]}}
    else:
        response = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if response and msg_id:
        await sessions[session_id].put(response)
    return Response("OK")

async def health(request):
    return Response("OK")

app = Starlette(routes=[
    Route("/", health),
    Route("/health", health),
    Route("/tools", http_tools),
    Route("/call", http_call_tool, methods=["POST"]),
    Route("/sse", sse_endpoint),
    Route("/messages/{session_id}", messages_endpoint, methods=["POST"]),
])

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)