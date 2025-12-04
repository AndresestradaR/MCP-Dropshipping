# 🧠 Super Agente de IA - El Cerebro v2.0

Agente de IA para WhatsApp que analiza rentabilidad de tu negocio de Dropshipping.
Conecta con Meta Ads, Shopify y Dropi para darte análisis financieros en tiempo real.

## 🎯 ¿Qué puede hacer?

Pregúntale por WhatsApp:
- "¿Estoy ganando plata?" → Análisis completo de rentabilidad
- "¿Cuánto gasté en Meta hoy?" → Gasto en publicidad
- "¿Cuántas ventas tengo?" → Pedidos de Shopify
- "¿Cuántos pedidos se han entregado?" → Estado de Dropi
- "¿Cuál es mi CPA real?" → CPA considerando devoluciones

## 🏗️ Arquitectura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  WhatsApp   │────▶│   Twilio    │────▶│   Cerebro   │
│   Usuario   │◀────│   Webhook   │◀────│  (FastAPI)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
           ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
           │  META ADS   │            │   SHOPIFY   │            │    DROPI    │
           │   Server    │            │   Server    │            │   Server    │
           │  (Railway)  │            │  (Railway)  │            │  (Railway)  │
           └─────────────┘            └─────────────┘            └─────────────┘
                 │                          │                          │
                 ▼                          ▼                          ▼
           Gasto en Ads              Ventas/Pedidos              Entregas/Pagos
```

## 📁 Archivos

```
cerebro/
├── server.py          # FastAPI + webhook Twilio
├── agent.py           # LangGraph + prompt inteligente
├── mcp_client.py      # Cliente para conectar a servidores MCP
├── config.py          # Configuración (INCLUYE DROPI)
├── requirements.txt   # Dependencias Python
├── Procfile           # Comando para Railway
└── .env.example       # Variables de entorno
```

## 🚀 Despliegue en Railway

### 1. Subir a GitHub

```bash
git add .
git commit -m "v2.0: Agregado Dropi + prompt inteligente"
git push
```

### 2. Agregar Variable de Entorno en Railway

En Railway → Tu proyecto Cerebro → Settings → Variables:

```
DROPI_MCP_URL=https://server-dropi-production.up.railway.app
```

Las otras variables ya deberían estar:
- `ANTHROPIC_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`
- `SHOPIFY_MCP_URL`
- `META_MCP_URL`

### 3. Redesplegar

Railway debería redesplegar automáticamente. Si no, haz clic en "Redeploy".

### 4. Verificar

```bash
# Health check
curl https://tu-cerebro.up.railway.app/health

# Ver herramientas disponibles (ahora debería mostrar ~23)
curl https://tu-cerebro.up.railway.app/tools
```

## 🔧 Herramientas Disponibles

### Meta Ads (5 herramientas)
- `meta_get_ad_spend_today` - Gasto de hoy
- `meta_get_ad_spend_by_period` - Gasto por período
- `meta_get_campaign_performance` - Rendimiento de campañas
- `meta_get_adset_performance` - Rendimiento de adsets
- `meta_get_ad_account_info` - Info de cuenta

### Shopify (13 herramientas)
- `shopify_get_total_sales_today` - Ventas de hoy
- `shopify_get_sales_by_period` - Ventas por período
- `shopify_get_recent_orders` - Últimos pedidos
- `shopify_get_order_details` - Detalle de pedido
- `shopify_get_all_products` - Todos los productos
- `shopify_get_low_stock_products` - Bajo inventario
- `shopify_get_best_selling_products` - Más vendidos
- Y más...

### Dropi (5 herramientas)
- `dropi_get_dropi_wallet` - Saldo en cartera
- `dropi_get_dropi_wallet_history` - Historial de pagos
- `dropi_get_dropi_orders` - Lista de órdenes
- `dropi_get_dropi_order` - Detalle de orden
- `dropi_get_dropi_user_info` - Info de usuario

## 📊 Ejemplo de Análisis

Pregunta: "¿Estoy ganando plata esta semana?"

Respuesta del Cerebro:
```
📊 ANÁLISIS SEMANAL

💸 GASTOS:
- Meta Ads: $150,000 COP
- Devoluciones cobradas: $25,000 COP
- Total costos: $175,000 COP

📦 PEDIDOS:
- Shopify: 45 pedidos ($450,000 COP)
- Subidos a Dropi: 42
- Entregados: 30
- Devueltos: 5
- En tránsito: 7

💰 INGRESOS:
- Pagos recibidos: $280,000 COP

📈 MÉTRICAS:
- CPA Inicial: $3,333 (150k ÷ 45)
- CPA Real: $5,000 (150k ÷ 30 entregados)
- Tasa de entrega: 71%
- ROAS: 1.87

✅ VEREDICTO: Vas ganando $105,000 COP
Si se entregan los 7 pendientes → Ganancia: $175,000 COP
```

## 📝 Notas

- El Cerebro usa Claude Sonnet 4 para análisis
- La memoria de conversación es en RAM (se pierde al reiniciar)
- Para persistencia, considera usar PostgresSaver
- TikTok Ads está pendiente de implementar

---
Creado con 💪 para dominar tu negocio de Dropshipping
