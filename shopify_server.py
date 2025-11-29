"""
Servidor MCP para Meta Ads (Facebook/Instagram).
Conecta la IA con tus campañas publicitarias.
"""

import os
import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Cargar variables
load_dotenv()

# Tus llaves maestras
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID") # Debe ser formato: act_123456789

mcp = FastMCP("Meta Ads MCP")

@mcp.tool()
async def get_ad_spend_today() -> str:
    """
    Obtiene el gasto publicitario de HOY en Meta Ads.
    Devuelve: Gasto, Impresiones, Clics y CPC promedio.
    """
    import datetime
    today = datetime.date.today().isoformat()
    
    # Asegurar formato act_
    account_id = META_AD_ACCOUNT_ID if META_AD_ACCOUNT_ID.startswith("act_") else f"act_{META_AD_ACCOUNT_ID}"
    
    url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "date_preset": "today",
        "fields": "spend,impressions,clicks,cpc,ctr",
        "level": "account"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if "error" in data:
                return f"Error de Meta: {data['error']['message']}"
                
            if not data.get("data"):
                return "Hoy no has gastado nada en publicidad (o Meta no ha actualizado todavía)."
                
            stats = data["data"][0]
            spend = float(stats.get('spend', 0))
            clicks = int(stats.get('clicks', 0))
            
            return f"""
📊 **Reporte de Meta Ads (HOY {today}):**
💸 **Gasto:** ${spend:,.2f}
👀 **Impresiones:** {stats.get('impressions', 0)}
👆 **Clics:** {clicks}
📉 **CPC Promedio:** ${stats.get('cpc', '0')}
            """
        except Exception as e:
            return f"Error de conexión con Meta: {str(e)}"

@mcp.tool()
async def get_campaign_performance() -> str:
    """
    Revisa qué campañas están activas y cómo van hoy.
    Ideal para saber cuál apagar o cuál escalar.
    """
    account_id = META_AD_ACCOUNT_ID if META_AD_ACCOUNT_ID.startswith("act_") else f"act_{META_AD_ACCOUNT_ID}"
    url = f"https://graph.facebook.com/v19.0/{account_id}/insights"
    
    params = {
        "access_token": META_ACCESS_TOKEN,
        "date_preset": "today",
        "fields": "campaign_name,spend,roas,cpa,actions,inline_link_clicks",
        "level": "campaign"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if not data.get("data"):
                return "No hay campañas activas con gasto hoy."
                
            report = "🔥 **Rendimiento por Campaña (HOY):**\n"
            
            for campaign in data["data"]:
                spend = float(campaign.get('spend', 0))
                # Intentamos calcular compras si Meta las reporta
                purchases = 0
                if 'actions' in campaign:
                    for action in campaign['actions']:
                        if action['action_type'] == 'purchase' or action['action_type'] == 'omni_purchase':
                            purchases = int(action['value'])
                
                # Calcular CPA manual
                cpa = f"${spend/purchases:,.2f}" if purchases > 0 else "N/A"
                
                report += f"\n👉 {campaign['campaign_name']}\n"
                report += f"   - Gasto: ${spend:,.2f}\n"
                report += f"   - Compras: {purchases}\n"
                report += f"   - CPA: {cpa}\n"
                
            return report
        except Exception as e:
            return f"Error analizando campañas: {str(e)}"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)