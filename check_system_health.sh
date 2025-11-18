#!/bin/bash

# Script de diagnóstico rápido del sistema
# Verifica el estado de Redis, servicios, y datos críticos

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para verificar
check() {
    local value=$1
    local threshold=$2
    local name=$3
    
    if [ "$value" -ge "$threshold" ]; then
        echo -e "  ${GREEN}✅ $name: $value${NC}"
        return 0
    else
        echo -e "  ${RED}❌ $name: $value (esperado: ≥$threshold)${NC}"
        return 1
    fi
}

echo ""
echo "══════════════════════════════════════════════════════"
echo "🏥 DIAGNÓSTICO RÁPIDO DEL SISTEMA"
echo "══════════════════════════════════════════════════════"
echo ""

# 1. REDIS
echo -e "${BLUE}📦 REDIS${NC}"
DBSIZE=$(docker exec tradeul_redis redis-cli DBSIZE 2>/dev/null | grep -o '[0-9]*' || echo "0")
check "$DBSIZE" 10000 "DBSIZE"

UNIVERSE=$(docker exec tradeul_redis redis-cli SCARD 'ticker:universe' 2>/dev/null || echo "0")
check "$UNIVERSE" 10000 "Universe"

METADATA=$(docker exec tradeul_redis redis-cli KEYS 'metadata:ticker:*' 2>/dev/null | wc -l | tr -d ' ')
check "$METADATA" 10000 "Metadata"

ATR=$(docker exec tradeul_redis redis-cli HLEN 'atr:daily' 2>/dev/null || echo "0")
check "$ATR" 10000 "ATR"

RVOL=$(docker exec tradeul_redis redis-cli KEYS 'rvol:hist:avg:*' 2>/dev/null | wc -l | tr -d ' ')
check "$RVOL" 10000 "RVOL"

echo ""

# 2. SERVICIOS
echo -e "${BLUE}🐳 SERVICIOS DOCKER${NC}"
for service in tradeul_data_maintenance tradeul_scanner tradeul_polygon_ws tradeul_websocket_server tradeul_ingest tradeul_analytics; do
    STATUS=$(docker inspect -f '{{.State.Status}}' $service 2>/dev/null || echo "not_found")
    if [ "$STATUS" == "running" ]; then
        echo -e "  ${GREEN}✅ $service: running${NC}"
    else
        echo -e "  ${RED}❌ $service: $STATUS${NC}"
    fi
done

echo ""

# 3. POLYGON WS
echo -e "${BLUE}🔌 POLYGON WEBSOCKET${NC}"
POLYGON_LOG=$(docker logs tradeul_polygon_ws --tail 50 --since 60s 2>&1)
POLYGON_SUBS=$(echo "$POLYGON_LOG" | grep "subscribed_to_tickers" | tail -1 | grep -o "tickers_count\":[0-9]*" | grep -o '[0-9]*' || echo "0")
check "$POLYGON_SUBS" 400 "Suscripciones activas"

POLYGON_CONNECTED=$(echo "$POLYGON_LOG" | grep -c "WebSocket connected" || echo "0")
if [ "$POLYGON_CONNECTED" -gt 0 ]; then
    echo -e "  ${GREEN}✅ WebSocket conectado${NC}"
else
    echo -e "  ${RED}❌ WebSocket desconectado${NC}"
fi

echo ""

# 4. SCANNER
echo -e "${BLUE}🔍 SCANNER${NC}"
SCANNER_STATUS=$(curl -s "http://localhost:8005/api/scanner/status" 2>/dev/null)
if echo "$SCANNER_STATUS" | grep -q "\"is_running\":true"; then
    echo -e "  ${GREEN}✅ Scanner: activo${NC}"
else
    echo -e "  ${YELLOW}⚠️  Scanner: inactivo${NC}"
fi

GAPPERS=$(docker exec tradeul_redis redis-cli GET "scanner:category:gappers_up" 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")
echo -e "  ${BLUE}ℹ️  Gappers Up: $GAPPERS${NC}"

WINNERS=$(docker exec tradeul_redis redis-cli GET "scanner:category:winners" 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")
echo -e "  ${BLUE}ℹ️  Winners: $WINNERS${NC}"

echo ""

# 5. WEBSOCKET SERVER
echo -e "${BLUE}📡 WEBSOCKET SERVER${NC}"
WS_LOG=$(docker logs tradeul_websocket_server --tail 30 --since 60s 2>&1)
WS_BROADCASTING=$(echo "$WS_LOG" | grep -c "Broadcasting delta" || echo "0")
if [ "$WS_BROADCASTING" -gt 0 ]; then
    echo -e "  ${GREEN}✅ Broadcasting activo (últimos 60s: $WS_BROADCASTING)${NC}"
else
    echo -e "  ${YELLOW}⚠️  Sin broadcasts recientes${NC}"
fi

WS_ERRORS=$(echo "$WS_LOG" | grep -c "NOGROUP" || echo "0")
if [ "$WS_ERRORS" -gt 0 ]; then
    echo -e "  ${RED}❌ NOGROUP errors detectados: $WS_ERRORS${NC}"
fi

echo ""

# 6. STREAMS EN REDIS
echo -e "${BLUE}🌊 REDIS STREAMS${NC}"
STREAM_AGG=$(docker exec tradeul_redis redis-cli XLEN 'stream:realtime:aggregates' 2>/dev/null || echo "0")
echo -e "  ${BLUE}ℹ️  stream:realtime:aggregates: $STREAM_AGG mensajes${NC}"

STREAM_DELTAS=$(docker exec tradeul_redis redis-cli XLEN 'stream:ranking:deltas' 2>/dev/null || echo "0")
echo -e "  ${BLUE}ℹ️  stream:ranking:deltas: $STREAM_DELTAS mensajes${NC}"

STREAM_SUBS=$(docker exec tradeul_redis redis-cli XLEN 'polygon_ws:subscriptions' 2>/dev/null || echo "0")
echo -e "  ${BLUE}ℹ️  polygon_ws:subscriptions: $STREAM_SUBS mensajes${NC}"

echo ""

# 7. ÚLTIMO SNAPSHOT
echo -e "${BLUE}📸 ÚLTIMO SNAPSHOT${NC}"
LAST_SNAPSHOT=$(docker exec tradeul_redis redis-cli GET 'snapshot:polygon:latest' 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"{len(data)} tickers, {data[0].get('timestamp', 'N/A')}\")" 2>/dev/null || echo "Sin datos")
echo -e "  ${BLUE}ℹ️  $LAST_SNAPSHOT${NC}"

echo ""

# RESUMEN
echo "══════════════════════════════════════════════════════"

TOTAL_CHECKS=5
PASSED_CHECKS=0

[ "$DBSIZE" -ge 10000 ] && ((PASSED_CHECKS++))
[ "$UNIVERSE" -ge 10000 ] && ((PASSED_CHECKS++))
[ "$ATR" -ge 10000 ] && ((PASSED_CHECKS++))
[ "$RVOL" -ge 10000 ] && ((PASSED_CHECKS++))
[ "$POLYGON_SUBS" -ge 400 ] && ((PASSED_CHECKS++))

if [ "$PASSED_CHECKS" -eq "$TOTAL_CHECKS" ]; then
    echo -e "${GREEN}✅ SISTEMA: 100% OPERATIVO${NC}"
    exit 0
elif [ "$PASSED_CHECKS" -ge 3 ]; then
    echo -e "${YELLOW}⚠️  SISTEMA: OPERATIVO CON ALERTAS${NC}"
    exit 0
else
    echo -e "${RED}❌ SISTEMA: REQUIERE ATENCIÓN${NC}"
    echo ""
    echo "Sugerencias:"
    echo "  1. Verificar logs: docker logs tradeul_data_maintenance"
    echo "  2. Ejecutar recovery: docker restart tradeul_data_maintenance"
    echo "  3. Probar recovery completo: ./test_auto_recovery.sh"
    exit 1
fi

