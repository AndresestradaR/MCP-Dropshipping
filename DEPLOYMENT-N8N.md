# 📊 GUÍA DE DESPLIEGUE: SERVIDOR N8N EN RAILWAY

## 🎯 Objetivo
Desplegar el servidor MCP N8N en Railway para que el Cerebro pueda generar gráficos.

---

## 📁 Archivos Necesarios

Para el **servidor N8N** necesitas estos archivos en un repo separado o carpeta:

```
server-n8n/
├── n8n_server.py          # Servidor MCP con herramientas de gráficos
├── requirements.txt       # Dependencias Python
├── Procfile              # Comando: web: uvicorn n8n_server:app --host 0.0.0.0 --port $PORT
└── .env.example          # Variables de entorno (referencia)
```

---

## 🚀 PASO 1: Crear Servicio en Railway

### Opción A: Desde GitHub (Recomendado)

1. Sube estos archivos a un repo de GitHub (puede ser el mismo repo, en una carpeta `/server-n8n`)
2. Ve a Railway → **New Project**
3. Selecciona **Deploy from GitHub repo**
4. Selecciona tu repositorio
5. Si tienes los archivos en una carpeta, configura **Root Directory**: `server-n8n`

### Opción B: Desde Local

1. Ve a Railway → **New Project** → **Empty Project**
2. Click en **Deploy** → sube los archivos directamente

---

## ⚙️ PASO 2: Configurar Variables de Entorno en Railway

En Railway → Tu servicio N8N → **Variables**, agrega:

```bash
# URL de tu instancia de N8N
N8N_BASE_URL=https://n8n.srv1121056.hstgr.cloud

# Webhook para gráficos
N8N_WEBHOOK_GRAFICO=https://n8n.srv1121056.hstgr.cloud/webhook/grafico

# Puerto (Railway lo proporciona automáticamente)
PORT=3000
```

**⚠️ IMPORTANTE:** Asegúrate que la URL de N8N sea la correcta (la de tu instancia).

---

## 🔗 PASO 3: Agregar URL del Servidor N8N al Cerebro

Una vez desplegado, Railway te dará una URL como:
```
https://server-n8n-production.up.railway.app
```

Ahora ve al servicio del **Cerebro** en Railway y agrega esta variable:

```bash
N8N_MCP_URL=https://server-n8n-production.up.railway.app
```

---

## ✅ PASO 4: Verificar que Funciona

### Test 1: Health Check
```bash
curl https://server-n8n-production.up.railway.app/health
```

Debe responder:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "n8n_base_url": "https://n8n.srv1121056.hstgr.cloud",
  "webhook_grafico": "https://n8n.srv1121056.hstgr.cloud/webhook/grafico"
}
```

### Test 2: Listar Herramientas
```bash
curl https://server-n8n-production.up.railway.app/tools
```

Debe responder con 2 herramientas:
```json
{
  "tools": [
    {"name": "generate_chart", ...},
    {"name": "generate_comparison_chart", ...}
  ]
}
```

### Test 3: Generar un Gráfico de Prueba
```bash
curl -X POST https://server-n8n-production.up.railway.app/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "generate_chart",
    "arguments": {
      "tipo": "bar",
      "titulo": "Test",
      "labels": ["A", "B", "C"],
      "valores": [10, 20, 30]
    }
  }'
```

Debe responder con un link al gráfico.

---

## 🔧 PASO 5: Probar desde WhatsApp

Una vez que todo esté configurado, envía este mensaje por WhatsApp:

```
Genera un gráfico de barras con las ventas de la semana:
Lunes: 150
Martes: 230
Miércoles: 180
Jueves: 290
Viernes: 200
```

El Cerebro debería:
1. Detectar que necesita generar un gráfico
2. Llamar a `n8n_generate_chart` con los datos
3. El servidor N8N llamará al webhook de n8n
4. n8n generará la imagen del gráfico
5. Devolver el link al usuario

---

## 📊 Workflow de n8n - Configuración

Tu workflow "MCP - Graficos" debe:

1. **Nodo Webhook** (POST /webhook/grafico)
   - Responder: "Using Respond to Webhook Node"
   
2. **Nodo Code** (Generar gráfico con Chart.js o QuickChart)
   
3. **Nodo Respond to Webhook** (Devolver URL de la imagen)

**Formato de respuesta esperado:**
```json
{
  "success": true,
  "image_url": "https://quickchart.io/chart?c=..."
}
```

---

## 🐛 Troubleshooting

### Error: "No executions found" en n8n

**Causa:** El webhook nunca se está llamando.

**Solución:** 
1. Verifica que el servidor N8N esté desplegado y funcionando
2. Verifica que `N8N_MCP_URL` esté en las variables del Cerebro
3. Prueba el endpoint `/call` del servidor N8N directamente

### Error: "Webhook not registered" en n8n

**Causa:** El workflow no está activo.

**Solución:**
1. Ve al workflow en n8n
2. Asegúrate que el toggle esté en **"Active"** (verde)
3. Usa la URL de producción `/webhook/grafico`, no la de test

### Error al generar el gráfico

**Causa:** El formato de los datos no es correcto.

**Solución:**
Verifica que `labels` y `valores` tengan el mismo tamaño:
```json
{
  "labels": ["A", "B", "C"],
  "valores": [10, 20, 30]  // ✅ Mismo tamaño
}
```

---

## 🎯 Resumen de URLs

Una vez desplegado, tendrás:

- **Cerebro:** `https://mcp-cerebro-production.up.railway.app`
- **Server-Shopify:** `https://mcp-dropshipping-production.up.railway.app`
- **Server-Meta:** `https://server-meta-production-4773.up.railway.app`
- **Server-Dropi:** `https://server-dropi-production.up.railway.app`
- **Server-N8N:** `https://server-n8n-production.up.railway.app` ← NUEVO

¡Listo! Ahora tu Super Agente puede generar gráficos 📊
