#!/bin/bash

# Script para probar el sistema de Auto-Recovery
# Simula un FLUSHDB y verifica que el sistema se recupere automáticamente

set -e

echo "══════════════════════════════════════════════════════"
echo "🧪 TEST: SISTEMA DE AUTO-RECOVERY"
echo "══════════════════════════════════════════════════════"
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para verificar
check() {
    if [ $1 -gt 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
        return 0
    else
        echo -e "${RED}❌ $2${NC}"
        return 1
    fi
}

# Paso 1: Estado inicial
echo "📊 PASO 1: Verificando estado inicial..."
INITIAL_DBSIZE=$(docker exec tradeul_redis redis-cli DBSIZE | grep -o '[0-9]*')
echo "   DBSIZE inicial: $INITIAL_DBSIZE"
echo ""

# Paso 2: Simular FLUSHDB
echo "💥 PASO 2: Simulando FLUSHDB..."
docker exec tradeul_redis redis-cli FLUSHDB > /dev/null
AFTER_FLUSH=$(docker exec tradeul_redis redis-cli DBSIZE | grep -o '[0-9]*')
check $((AFTER_FLUSH == 0)) "Redis vaciado (DBSIZE=$AFTER_FLUSH)"
echo ""

# Paso 3: Reiniciar data_maintenance (debería auto-recuperar)
echo "🔄 PASO 3: Reiniciando data_maintenance (auto-recovery)..."
docker restart tradeul_data_maintenance > /dev/null
echo "   Esperando 60 segundos para recovery..."
sleep 60
echo ""

# Paso 4: Verificar recuperación
echo "🔍 PASO 4: Verificando recuperación..."

# Verificar DBSIZE
DBSIZE_AFTER=$(docker exec tradeul_redis redis-cli DBSIZE | grep -o '[0-9]*')
check $((DBSIZE_AFTER > 10000)) "DBSIZE recuperado (actual: $DBSIZE_AFTER)"

# Verificar Universe
UNIVERSE_SIZE=$(docker exec tradeul_redis redis-cli SCARD 'ticker:universe')
check $((UNIVERSE_SIZE > 10000)) "Universe recuperado ($UNIVERSE_SIZE tickers)"

# Verificar Metadata
METADATA_COUNT=$(docker exec tradeul_redis redis-cli KEYS 'metadata:ticker:*' | wc -l | tr -d ' ')
check $((METADATA_COUNT > 10000)) "Metadata recuperado ($METADATA_COUNT claves)"

# Verificar ATR
ATR_COUNT=$(docker exec tradeul_redis redis-cli HLEN 'atr:daily')
check $((ATR_COUNT > 10000)) "ATR recuperado ($ATR_COUNT tickers)"

# Verificar RVOL
RVOL_COUNT=$(docker exec tradeul_redis redis-cli KEYS 'rvol:hist:avg:*' | wc -l | tr -d ' ')
check $((RVOL_COUNT > 10000)) "RVOL recuperado ($RVOL_COUNT hashes)"

echo ""

# Paso 5: Verificar logs de recovery
echo "📋 PASO 5: Verificando logs de recovery..."
docker logs tradeul_data_maintenance --tail 100 | grep -i "recovery" | tail -5
echo ""

# Paso 6: Reiniciar servicios dependientes
echo "🔄 PASO 6: Reiniciando servicios dependientes..."
docker restart tradeul_scanner > /dev/null 2>&1
echo "   ✅ Scanner reiniciado"
docker restart tradeul_websocket_server > /dev/null 2>&1
echo "   ✅ WebSocket Server reiniciado"
echo "   Esperando 15 segundos..."
sleep 15
echo ""

# Paso 7: Iniciar Scanner
echo "🚀 PASO 7: Iniciando Scanner..."
curl -s -X POST "http://localhost:8005/api/scanner/start" > /dev/null
echo "   ✅ Scanner iniciado"
sleep 10
echo ""

# Paso 8: Verificar estado final
echo "📊 PASO 8: Verificando estado final del sistema..."

# Verificar suscripciones en Polygon WS
POLYGON_SUBS=$(docker logs tradeul_polygon_ws --tail 50 --since 30s 2>&1 | grep "subscribed_to_tickers" | tail -1 | grep -o "tickers_count\":[0-9]*" | grep -o '[0-9]*' || echo "0")
check $((POLYGON_SUBS > 400)) "Polygon WS suscripciones ($POLYGON_SUBS tickers)"

# Verificar Scanner categorías
GAPPERS=$(docker exec tradeul_redis redis-cli GET "scanner:category:gappers_up" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")
check $((GAPPERS > 10)) "Scanner categorías (gappers_up: $GAPPERS)"

# Verificar WebSocket Server
WS_BROADCASTING=$(docker logs tradeul_websocket_server --tail 30 --since 30s 2>&1 | grep -c "Broadcasting delta" || echo "0")
check $((WS_BROADCASTING > 0)) "WebSocket Server emitiendo ($WS_BROADCASTING broadcasts)"

echo ""
echo "══════════════════════════════════════════════════════"
echo "🎉 TEST COMPLETADO"
echo "══════════════════════════════════════════════════════"
echo ""
echo "Estado final:"
echo "  - DBSIZE: $DBSIZE_AFTER"
echo "  - Universe: $UNIVERSE_SIZE tickers"
echo "  - Metadata: $METADATA_COUNT claves"
echo "  - ATR: $ATR_COUNT tickers"
echo "  - RVOL: $RVOL_COUNT hashes"
echo "  - Polygon WS: $POLYGON_SUBS suscripciones"
echo "  - Scanner: $GAPPERS gappers"
echo "  - WebSocket: Broadcasting activo"
echo ""

if [ $DBSIZE_AFTER -gt 10000 ] && [ $UNIVERSE_SIZE -gt 10000 ] && [ $POLYGON_SUBS -gt 400 ]; then
    echo -e "${GREEN}✅ AUTO-RECOVERY EXITOSO${NC}"
    exit 0
else
    echo -e "${RED}❌ AUTO-RECOVERY INCOMPLETO - Revisar logs${NC}"
    exit 1
fi

