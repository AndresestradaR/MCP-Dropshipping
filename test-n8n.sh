#!/bin/bash
# Script de prueba para el Servidor N8N
# Verifica que el servidor esté funcionando correctamente

# Colores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 TESTS DEL SERVIDOR N8N"
echo "=========================="
echo ""

# URL del servidor (cambiar según tu despliegue)
SERVER_URL="${N8N_SERVER_URL:-https://server-n8n-production.up.railway.app}"

echo "🔗 Servidor: $SERVER_URL"
echo ""

# Test 1: Health Check
echo "1️⃣ Test: Health Check"
response=$(curl -s "$SERVER_URL/health")
if echo "$response" | grep -q "ok"; then
    echo -e "${GREEN}✅ PASS${NC} - Servidor respondiendo"
    echo "   Response: $response"
else
    echo -e "${RED}❌ FAIL${NC} - Servidor no responde"
    echo "   Response: $response"
fi
echo ""

# Test 2: Listar herramientas
echo "2️⃣ Test: Listar Herramientas"
response=$(curl -s "$SERVER_URL/tools")
if echo "$response" | grep -q "generate_chart"; then
    echo -e "${GREEN}✅ PASS${NC} - Herramientas disponibles"
    # Contar herramientas
    count=$(echo "$response" | grep -o "name" | wc -l)
    echo "   Herramientas encontradas: $count"
else
    echo -e "${RED}❌ FAIL${NC} - No se encontraron herramientas"
    echo "   Response: $response"
fi
echo ""

# Test 3: Generar gráfico simple
echo "3️⃣ Test: Generar Gráfico de Barras"
payload='{
  "name": "generate_chart",
  "arguments": {
    "tipo": "bar",
    "titulo": "Test de Ventas",
    "labels": ["Lun", "Mar", "Mie", "Jue", "Vie"],
    "valores": [150, 230, 180, 290, 200]
  }
}'

response=$(curl -s -X POST "$SERVER_URL/call" \
  -H "Content-Type: application/json" \
  -d "$payload")

if echo "$response" | grep -q "GRÁFICO GENERADO"; then
    echo -e "${GREEN}✅ PASS${NC} - Gráfico generado exitosamente"
    # Extraer URL del gráfico
    url=$(echo "$response" | grep -oP 'Ver gráfico: \K[^ ]+')
    if [ ! -z "$url" ]; then
        echo "   📊 URL del gráfico: $url"
    fi
else
    echo -e "${RED}❌ FAIL${NC} - Error generando gráfico"
    echo "   Response: $response"
fi
echo ""

# Test 4: Generar gráfico comparativo
echo "4️⃣ Test: Generar Gráfico Comparativo"
payload='{
  "name": "generate_comparison_chart",
  "arguments": {
    "titulo": "Ventas vs Gastos",
    "labels": ["Ene", "Feb", "Mar"],
    "series": [
      {"nombre": "Ventas", "valores": [1000, 1200, 1100]},
      {"nombre": "Gastos", "valores": [800, 900, 850]}
    ]
  }
}'

response=$(curl -s -X POST "$SERVER_URL/call" \
  -H "Content-Type: application/json" \
  -d "$payload")

if echo "$response" | grep -q "COMPARATIVO GENERADO"; then
    echo -e "${GREEN}✅ PASS${NC} - Gráfico comparativo generado"
    url=$(echo "$response" | grep -oP 'Ver gráfico: \K[^ ]+')
    if [ ! -z "$url" ]; then
        echo "   📊 URL del gráfico: $url"
    fi
else
    echo -e "${RED}❌ FAIL${NC} - Error generando comparativo"
    echo "   Response: $response"
fi
echo ""

# Resumen
echo "=========================="
echo "🏁 Tests completados"
echo ""
echo -e "${YELLOW}💡 Próximos pasos:${NC}"
echo "1. Verifica que tu workflow 'MCP - Graficos' en n8n esté ACTIVO"
echo "2. Agrega N8N_MCP_URL=$SERVER_URL al Cerebro en Railway"
echo "3. Prueba desde WhatsApp: 'Genera un gráfico de...'"
echo ""
