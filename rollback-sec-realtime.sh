#!/bin/bash

# Script para hacer rollback de SEC Real-Time Filings
# Uso: ./rollback-sec-realtime.sh

set -e

echo "🔄 Rollback de SEC Real-Time Filings..."
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cd /opt/tradeul

echo -e "${YELLOW}⚠️  Este script detendrá los servicios y revertirá los cambios${NC}"
echo ""
read -p "¿Estás seguro? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Cancelado."
    exit 1
fi

echo ""
echo "📋 Paso 1: Detener servicios..."
docker compose stop sec-filings websocket_server

echo ""
echo "🔄 Paso 2: Revertir cambios de Git (archivos modificados)..."
git checkout -- services/sec-filings/main.py
git checkout -- services/websocket_server/src/index.js

echo ""
echo "🗑️  Paso 3: Eliminar archivos nuevos..."
rm -f services/sec-filings/tasks/sec_stream_ws_client.py
rm -f services/sec-filings/tasks/sec_stream_manager.py
rm -f frontend/components/sec-filings/SECFilingsRealtime.tsx

echo ""
echo "🔨 Paso 4: Rebuild servicios con código original..."
docker compose build --no-cache sec-filings websocket_server

echo ""
echo "🚀 Paso 5: Arrancar servicios..."
docker compose up -d --force-recreate sec-filings websocket_server

echo ""
echo "⏳ Esperando 5 segundos..."
sleep 5

echo ""
echo "📊 Estado de los servicios:"
docker compose ps | grep -E "NAME|sec-filings|websocket_server"

echo ""
echo -e "${GREEN}✅ Rollback completado!${NC}"
echo "El sistema debería estar funcionando con el código original."
echo ""


