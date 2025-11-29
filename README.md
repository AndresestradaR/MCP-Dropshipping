# 🤖 Super Agente de IA para WhatsApp

Agente de IA en producción que conecta WhatsApp (via Twilio) con herramientas externas usando el protocolo MCP (Model Context Protocol).

## 🏗️ Arquitectura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    WhatsApp     │────▶│     Twilio      │────▶│    FastAPI      │
│    Usuario      │◀────│    Webhook      │◀────│    Server       │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │    LangGraph    │
                                                │    (Agente)     │
                                                └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────────────┐
                        ▼                                ▼                                ▼
               ┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
               │  Claude 3.5     │              │   MCP Client    │              │    Memory       │
               │  Sonnet         │              │  (HTTP Stream)  │              │  (Checkpointer) │
               └─────────────────┘              └────────┬────────┘              └─────────────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  Shopify MCP    │
                                                │  Server (Remoto)│
                                                └─────────────────┘
```

## 📁 Estructura de Archivos

```
super-agent/
├── server.py          # Punto de entrada FastAPI + webhook Twilio
├── agent.py           # Lógica del agente con LangGraph
├── mcp_client.py      # Cliente MCP para conexión remota (Streamable HTTP)
├── config.py          # Configuración con Pydantic Settings
├── requirements.txt   # Dependencias Python
├── Procfile           # Comando de inicio para Railway
├── railway.json       # Configuración de Railway
├── .env.example       # Plantilla de variables de entorno
└── README.md          # Esta documentación
```

## 🚀 Despliegue en Railway

### 1. Preparar el Repositorio

```bash
# Crear repo en GitHub
git init
git add .
git commit -m "Initial commit: Super Agente de IA"
git remote add origin https://github.com/tu-usuario/super-agent.git
git push -u origin main
```

### 2. Crear Proyecto en Railway

1. Ve a [railway.app](https://railway.app)
2. Click en "New Project"
3. Selecciona "Deploy from GitHub repo"
4. Conecta tu repositorio

### 3. Configurar Variables de Entorno

En Railway, ve a tu proyecto → Settings → Variables y agrega:

| Variable | Descripción |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Tu API key de Anthropic |
| `TWILIO_ACCOUNT_SID` | Account SID de Twilio |
| `TWILIO_AUTH_TOKEN` | Auth Token de Twilio |
| `TWILIO_WHATSAPP_NUMBER` | Número de WhatsApp (formato: `whatsapp:+14155238886`) |
| `SHOPIFY_MCP_URL` | URL de tu servidor MCP de Shopify |

### 4. Configurar Twilio

1. Ve a [Twilio Console](https://console.twilio.com)
2. Navega a Messaging → Try it out → Send a WhatsApp message
3. Configura el Sandbox (o tu número aprobado)
4. En "Webhook URL for incoming messages", pon:
   ```
   https://tu-app.up.railway.app/webhook/whatsapp
   ```
5. Método: `POST`

### 5. Verificar Despliegue

```bash
# Health check
curl https://tu-app.up.railway.app/health

# Ver herramientas disponibles
curl https://tu-app.up.railway.app/tools
```

## 🔧 Desarrollo Local

### Requisitos

- Python 3.11+
- Cuenta de Anthropic con API key
- Cuenta de Twilio (para WhatsApp)
- Servidor MCP remoto (para herramientas)

### Instalación

```bash
# Clonar repositorio
git clone https://github.com/tu-usuario/super-agent.git
cd super-agent

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o: venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Copiar y configurar variables de entorno
cp .env.example .env
# Edita .env con tus credenciales
```

### Ejecutar

```bash
# Modo desarrollo
python server.py

# O con uvicorn directamente
uvicorn server:app --reload --port 8000
```

### Probar con ngrok (para desarrollo local)

```bash
# En otra terminal
ngrok http 8000

# Copia la URL https://xxxx.ngrok.io y úsala en Twilio
```

## 📡 API Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/` | Health check básico |
| `GET` | `/health` | Health check detallado |
| `POST` | `/webhook/whatsapp` | Webhook para mensajes de Twilio |
| `GET` | `/tools` | Lista herramientas MCP disponibles |
| `GET` | `/conversations/{user_id}/history` | Historial de conversación |
| `DELETE` | `/conversations/{user_id}` | Limpiar conversación |

## 🔌 Agregar Más Servidores MCP

Para conectar más servicios, edita `mcp_client.py`:

```python
def _register_servers(self):
    # Servidor existente
    self.servers["shopify"] = RemoteMCPServer(
        name="shopify",
        url=self.settings.shopify_mcp_url,
        description="Operaciones de Shopify"
    )
    
    # Agregar nuevo servidor
    self.servers["inventory"] = RemoteMCPServer(
        name="inventory",
        url=os.getenv("INVENTORY_MCP_URL"),
        description="Sistema de inventario"
    )
```

## 🔒 Seguridad

- ✅ Validación de requests de Twilio (firma X-Twilio-Signature)
- ✅ Variables de entorno para credenciales
- ✅ Health checks para monitoreo
- ⚠️ En producción, considera agregar rate limiting
- ⚠️ Usa HTTPS siempre (Railway lo maneja automáticamente)

## 📝 Notas Importantes

### Sobre MCP y SSE

El código usa **Streamable HTTP** en lugar de SSE porque:
- SSE está **deprecado** en el protocolo MCP
- Streamable HTTP es el estándar moderno recomendado
- Soporta comunicación bidireccional completa
- Mejor para escenarios multi-cliente

Si tu servidor MCP usa el endpoint `/sse`, necesitarás actualizarlo a `/mcp` con Streamable HTTP.

### Memoria de Conversación

El agente usa `MemorySaver` de LangGraph que mantiene el estado en memoria. Para producción con múltiples instancias, considera usar:
- `SqliteSaver` para persistencia local
- `PostgresSaver` para persistencia distribuida

## 🐛 Troubleshooting

### "Error conectando a MCP"
- Verifica que la URL del servidor MCP sea correcta
- Asegúrate de que el servidor MCP esté corriendo
- Revisa que use Streamable HTTP (endpoint `/mcp`)

### "Invalid Twilio signature"
- Verifica `TWILIO_AUTH_TOKEN` sea correcto
- La URL del webhook debe coincidir exactamente
- En desarrollo, puedes poner `DEBUG=True`

### "No tools available"
- El servidor MCP puede no estar respondiendo
- Revisa los logs en Railway
- Verifica la conexión con `/health`

## 📄 Licencia

MIT

---

Creado con ❤️ usando Claude, LangGraph y MCP
