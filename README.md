# 🚚 Dropi MCP Server v2.0

Servidor MCP (Model Context Protocol) para conectar tu agente de IA con la plataforma Dropi.

## 📋 Características

- ✅ Consultar billetera/wallet
- ✅ Ver órdenes y estadísticas
- ✅ Consultar pagos recibidos
- ✅ Ver devoluciones
- ✅ Análisis de rentabilidad
- ✅ Buscar órdenes específicas
- ✅ Información de cuenta

## 🚀 Despliegue en Railway

### 1. Crear nuevo proyecto en Railway

```bash
# Si tienes Railway CLI
railway login
railway init
```

O usa la interfaz web de Railway.

### 2. Configurar variables de entorno

En Railway, agrega estas variables:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `DROPI_TOKEN` | Tu token de API de Dropi | `eyJ0eXAiOiJKV1...` |
| `DROPI_COUNTRY` | Código de país | `gt`, `co`, `mx`, `cl`, `pe`, `ec` |
| `PORT` | (Automático) Puerto del servidor | Railway lo asigna |

### 3. Obtener el token de Dropi

1. Inicia sesión en tu cuenta de Dropi (ej: app.dropi.gt)
2. Ve a **Configuración** → **API** o **Integraciones**
3. Genera un nuevo token de API
4. Copia el token completo

### 4. Desplegar

Railway desplegará automáticamente desde GitHub, o puedes:

```bash
railway up
```

## 🔍 Endpoint de Diagnóstico

Una vez desplegado, visita:

```
https://tu-app.railway.app/discover
```

Este endpoint te mostrará qué endpoints de la API de Dropi funcionan con tu token. Esto es útil para debug.

## 📡 Endpoints del servidor

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/health` | Estado detallado |
| GET | `/discover` | Diagnóstico de API Dropi |
| GET | `/tools` | Lista de herramientas |
| POST | `/call` | Ejecutar herramienta |
| GET | `/sse` | Conexión SSE (MCP) |

## 🔧 Herramientas disponibles

| Herramienta | Descripción |
|-------------|-------------|
| `get_dropi_wallet` | Consulta saldo de billetera |
| `get_dropi_orders` | Lista órdenes con filtros |
| `get_dropi_order_stats` | Estadísticas de órdenes |
| `get_dropi_payments` | Pagos recibidos |
| `get_dropi_returns` | Devoluciones |
| `get_dropi_profit_analysis` | Análisis de rentabilidad |
| `get_dropi_account_info` | Info de cuenta |
| `search_dropi_order` | Buscar orden específica |

## 🔗 Integrar con tu agente

Una vez desplegado, agrega la URL a tu `config.py`:

```python
DROPI_MCP_URL = "https://tu-server-dropi.railway.app"
```

Y en `MCP_SERVERS`:

```python
MCP_SERVERS["dropi"] = {
    "url": DROPI_MCP_URL,
    "name": "Dropi",
    "description": "Logística, órdenes, billetera, devoluciones"
}
```

## ⚠️ Notas importantes

### Si el servidor no conecta con Dropi:

1. **Verifica el token**: Usa el endpoint `/discover` para verificar
2. **Verifica el país**: Asegúrate de que `DROPI_COUNTRY` sea correcto
3. **Token expirado**: Algunos tokens expiran, genera uno nuevo
4. **API no documentada**: Dropi no tiene documentación pública de su API, los endpoints se descubrieron por ingeniería inversa

### Para encontrar los endpoints correctos:

1. Abre la consola de desarrollador de tu navegador (F12)
2. Ve a la pestaña "Network"
3. Navega por Dropi (billetera, órdenes, etc.)
4. Observa las llamadas XHR/Fetch que hace la aplicación
5. Esos son los endpoints reales que puedes agregar al servidor

## 📝 Próximos pasos

- [ ] TikTok Ads server
- [ ] Análisis cruzado (Meta + Dropi + Shopify)
- [ ] Alertas automáticas
- [ ] Proyecciones de profit

---

Creado para el proyecto de Super Agente de IA 🤖
