#!/bin/bash
# Script para verificar la salud del sistema Tradeul

echo "🔍 Verificando salud del sistema Tradeul..."
echo ""

# 1. Redis
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 REDIS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
REDIS_KEYS=$(docker exec tradeul_redis redis-cli DBSIZE 2>/dev/null | grep -o '[0-9]*')
METADATA_KEYS=$(docker exec tradeul_redis redis-cli KEYS "metadata:ticker:*" 2>/dev/null | wc -l)
echo "  Total keys: $REDIS_KEYS"
echo "  Metadata keys: $METADATA_KEYS"
echo "  Esperado: >20,000 keys totales, >12,000 metadata"
echo ""

# 2. Base de Datos
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗄️  BASE DE DATOS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
DB_METADATA=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -tAc "SELECT COUNT(*) FROM ticker_metadata" 2>/dev/null)
DB_UNIVERSE=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -tAc "SELECT COUNT(*) FROM ticker_universe WHERE is_active = true" 2>/dev/null)
DB_VOLUME_SLOTS=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -tAc "SELECT COUNT(DISTINCT symbol) FROM volume_slots" 2>/dev/null)
echo "  ticker_metadata: $DB_METADATA"
echo "  ticker_universe: $DB_UNIVERSE"
echo "  volume_slots (tickers): $DB_VOLUME_SLOTS"
echo "  Esperado: ~12,000 metadata, ~12,000 universe, ~11,900 volume_slots"
echo ""

# 3. Scanner
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 SCANNER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
FILTERED=$(curl -s http://localhost:8005/api/categories/gappers_up 2>/dev/null | grep -o '"count":[0-9]*' | cut -d: -f2)
SCANNER_HEALTH=$(curl -s http://localhost:8005/health 2>/dev/null | grep -o '"is_running":[a-z]*' | cut -d: -f2)
echo "  Estado: $SCANNER_HEALTH"
echo "  Gappers Up: $FILTERED tickers"
echo "  Esperado: running=true, >50 tickers"
echo ""

# 4. WebSocket
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📡 WEBSOCKET"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
WS_ERRORS=$(docker logs tradeul_websocket_server --tail 100 2>&1 | grep -c "NOGROUP")
WS_BROADCASTING=$(docker logs tradeul_websocket_server --tail 20 2>&1 | grep -c "Broadcasting")
echo "  Errores NOGROUP: $WS_ERRORS"
echo "  Broadcasting: $WS_BROADCASTING deltas recientes"
echo "  Esperado: 0 errores, >0 broadcasts"
echo ""

# 5. Servicios
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 SERVICIOS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
DATA_INGEST=$(curl -s http://localhost:8003/health 2>/dev/null | grep -o '"is_running":[a-z]*' | cut -d: -f2)
ANALYTICS=$(curl -s http://localhost:8007/health 2>/dev/null | grep -o '"status":"[a-z]*' | cut -d'"' -f4)
echo "  data_ingest: $DATA_INGEST"
echo "  analytics: $ANALYTICS"
echo "  Esperado: Ambos 'healthy' o 'true'"
echo ""

# Evaluación final
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 EVALUACIÓN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ISSUES=0

if [ "$METADATA_KEYS" -lt 10000 ]; then
    echo "⚠️  Redis tiene pocos metadata ($METADATA_KEYS)"
    ISSUES=$((ISSUES + 1))
fi

if [ "$FILTERED" -lt 20 ]; then
    echo "⚠️  Scanner filtra pocos tickers ($FILTERED)"
    ISSUES=$((ISSUES + 1))
fi

if [ "$WS_ERRORS" -gt 10 ]; then
    echo "⚠️  WebSocket tiene errores ($WS_ERRORS)"
    ISSUES=$((ISSUES + 1))
fi

if [ "$ISSUES" -eq 0 ]; then
    echo "✅ SISTEMA FUNCIONANDO CORRECTAMENTE"
    echo ""
    echo "Todo está operativo. Frontend debería mostrar datos en tiempo real."
else
    echo "🔴 SISTEMA NECESITA RECUPERACIÓN"
    echo ""
    echo "Ejecutar recuperación:"
    echo "  1. docker exec tradeul_data_maintenance python scripts/sync_redis_safe.py"
    echo "  2. docker restart tradeul_scanner tradeul_websocket_server"
    echo "  3. curl -X POST http://localhost:8005/api/scanner/start"
fi

echo ""

