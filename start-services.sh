#!/bin/bash

echo "🚀 Iniciando servicios de Tradeul Scanner..."
echo ""

# Iniciar Data Ingest
echo "📥 Iniciando Data Ingest..."
curl -X POST http://localhost:8003/api/ingest/start 2>/dev/null
echo ""

# Verificar Market Session
echo "🕐 Verificando Market Session..."
curl -s http://localhost:8002/api/session/current | head -1
echo ""

# Verificar Polygon WebSocket
echo "📊 Verificando Polygon WebSocket..."
curl -s http://localhost:8006/health | head -1
echo ""

# Verificar Scanner
echo "🔍 Verificando Scanner..."
curl -s http://localhost:8005/health | head -1
echo ""

echo "✅ Todos los servicios iniciados!"
echo ""
echo "Frontend: http://localhost:3000"
echo "API Gateway: http://localhost:8000"
echo "WebSocket: ws://localhost:9000"
