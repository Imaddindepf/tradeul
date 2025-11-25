#!/bin/bash

# Script para reconstruir servicios con SEC Real-Time Filings
# Uso: ./rebuild-sec-realtime.sh

set -e

echo "🚀 Reconstruyendo servicios para SEC Real-Time Filings..."
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cd /opt/tradeul

# Verificar que tenemos SEC_API_IO
if [ -z "$SEC_API_IO" ]; then
    echo -e "${YELLOW}⚠️  WARNING: SEC_API_IO no está configurado en .env${NC}"
    echo "El servicio se iniciará pero el stream no funcionará sin API key"
    echo ""
fi

echo "📋 Paso 1: Detener servicios afectados..."
docker compose stop sec-filings websocket_server

echo ""
echo "🔨 Paso 2: Rebuild SEC Filings Service..."
docker compose build --no-cache sec-filings

echo ""
echo "🔨 Paso 3: Rebuild WebSocket Server..."
docker compose build --no-cache websocket_server

echo ""
echo "🚀 Paso 4: Recrear y arrancar servicios..."
docker compose up -d --force-recreate sec-filings websocket_server

echo ""
echo "⏳ Esperando 5 segundos para que los servicios inicien..."
sleep 5

echo ""
echo "📊 Estado de los servicios:"
docker compose ps | grep -E "NAME|sec-filings|websocket_server"

echo ""
echo -e "${GREEN}✅ Rebuild completado!${NC}"
echo ""
echo "📝 Para ver los logs:"
echo "   docker logs -f tradeul_sec_filings"
echo "   docker logs -f tradeul_websocket_server"
echo ""
echo "🧪 Para probar, busca en los logs:"
echo "   SEC Filings: '✅ Connected to Redis for SEC Stream'"
echo "   SEC Filings: '📡 Starting SEC Stream API WebSocket...'"
echo "   WebSocket: '📋 Starting SEC Filings stream processor'"
echo ""


