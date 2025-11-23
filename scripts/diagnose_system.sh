#!/bin/bash
# Script de diagnóstico completo
# Identifica si el problema está en: Redis, Backend, Frontend, o Red

echo "🔍 Diagnóstico Completo del Sistema Tradeul"
echo "=========================================="
echo ""

EXIT_CODE=0

# ============================================================================
# 1. REDIS - Fuente de verdad
# ============================================================================
echo "📊 1. VERIFICANDO REDIS..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REDIS_PING=$(docker exec tradeul_redis redis-cli PING 2>/dev/null)
if [ "$REDIS_PING" != "PONG" ]; then
    echo "❌ Redis NO responde"
    EXIT_CODE=1
else
    echo "✅ Redis responde: $REDIS_PING"
fi

METADATA_COUNT=$(docker exec tradeul_redis redis-cli --scan --pattern "metadata:ticker:*" 2>/dev/null | wc -l | tr -d ' ')
echo "   Metadata keys: $METADATA_COUNT"
if [ "$METADATA_COUNT" -lt 10000 ]; then
    echo "   ❌ PROBLEMA: Metadata bajo (esperado >12,000)"
    EXIT_CODE=2
else
    echo "   ✅ Metadata OK"
fi

SNAPSHOT_ENRICHED=$(docker exec tradeul_redis redis-cli GET "snapshot:enriched:latest" 2>/dev/null | jq -r '.count' 2>/dev/null || echo "0")
echo "   Enriched snapshot: $SNAPSHOT_ENRICHED tickers"
if [ "$SNAPSHOT_ENRICHED" -lt 1000 ]; then
    echo "   ❌ PROBLEMA: Snapshot enriched vacío o bajo"
    EXIT_CODE=3
else
    echo "   ✅ Enriched snapshot OK"
fi

CATEGORIES=$(docker exec tradeul_redis redis-cli --scan --pattern "scanner:category:*" 2>/dev/null | wc -l | tr -d ' ')
echo "   Scanner categories: $CATEGORIES"
if [ "$CATEGORIES" -lt 5 ]; then
    echo "   ❌ PROBLEMA: Pocas categorías guardadas (esperado ~11)"
    EXIT_CODE=4
else
    echo "   ✅ Categorías OK"
fi

echo ""

# ============================================================================
# 2. BACKEND - Servicios procesando
# ============================================================================
echo "🚀 2. VERIFICANDO BACKEND SERVICES..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# data_ingest
INGEST_HEALTH=$(curl -s http://localhost:8003/health 2>/dev/null | jq -r '.is_running' 2>/dev/null || echo "false")
echo "   data_ingest: $INGEST_HEALTH"
if [ "$INGEST_HEALTH" != "true" ]; then
    echo "   ❌ PROBLEMA: data_ingest no está corriendo"
    EXIT_CODE=5
fi

# analytics
ANALYTICS_HEALTH=$(curl -s http://localhost:8007/health 2>/dev/null | jq -r '.status' 2>/dev/null || echo "unhealthy")
echo "   analytics: $ANALYTICS_HEALTH"
if [ "$ANALYTICS_HEALTH" != "healthy" ]; then
    echo "   ❌ PROBLEMA: analytics no está healthy"
    EXIT_CODE=6
fi

# scanner
SCANNER_HEALTH=$(curl -s http://localhost:8005/health 2>/dev/null | jq -r '.is_running' 2>/dev/null || echo "false")
echo "   scanner: $SCANNER_HEALTH"
if [ "$SCANNER_HEALTH" != "true" ]; then
    echo "   ❌ PROBLEMA: scanner no está corriendo"
    EXIT_CODE=7
fi

# Scanner filters
SCANNER_FILTERED=$(curl -s http://localhost:8005/api/scanner/status 2>/dev/null | jq -r '.stats.total_tickers_filtered' 2>/dev/null || echo "0")
echo "   scanner filtered: $SCANNER_FILTERED tickers"
if [ "$SCANNER_FILTERED" -lt 10 ]; then
    echo "   ⚠️  AVISO: Scanner filtrando pocos tickers (puede ser fin de semana)"
fi

echo ""

# ============================================================================
# 3. API - Endpoints devolviendo datos
# ============================================================================
echo "📡 3. VERIFICANDO API ENDPOINTS..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

API_WINNERS=$(curl -s "http://localhost:8005/api/categories/winners?limit=10" 2>/dev/null | jq -r '.count' 2>/dev/null || echo "0")
echo "   /api/categories/winners: $API_WINNERS tickers"
if [ "$API_WINNERS" -eq 0 ]; then
    echo "   ❌ PROBLEMA: API no devuelve tickers"
    EXIT_CODE=8
else
    echo "   ✅ API devuelve datos"
    
    # Verificar que incluye RVOL y ATR
    SAMPLE_TICKER=$(curl -s "http://localhost:8005/api/categories/winners?limit=1" 2>/dev/null | jq -r '.tickers[0]' 2>/dev/null)
    HAS_RVOL=$(echo "$SAMPLE_TICKER" | jq -r '.rvol' 2>/dev/null)
    HAS_ATR=$(echo "$SAMPLE_TICKER" | jq -r '.atr' 2>/dev/null)
    
    echo "   Sample ticker RVOL: $HAS_RVOL"
    echo "   Sample ticker ATR: $HAS_ATR"
    
    if [ "$HAS_RVOL" == "null" ]; then
        echo "   ⚠️  AVISO: Tickers sin RVOL"
    fi
    if [ "$HAS_ATR" == "null" ]; then
        echo "   ⚠️  AVISO: Tickers sin ATR"
    fi
fi

echo ""

# ============================================================================
# 4. WEBSOCKET - Broadcasting
# ============================================================================
echo "📡 4. VERIFICANDO WEBSOCKET SERVER..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

WS_RUNNING=$(docker ps --filter "name=websocket_server" --filter "status=running" --format "{{.Names}}" | wc -l)
if [ "$WS_RUNNING" -eq 0 ]; then
    echo "❌ WebSocket server NO está corriendo"
    EXIT_CODE=9
else
    echo "✅ WebSocket server corriendo"
    
    WS_BROADCASTING=$(docker logs tradeul_websocket_server --tail 50 2>&1 | grep -c "Broadcasting" || echo "0")
    echo "   Broadcasting en últimos logs: ${WS_BROADCASTING}x"
    
    if [ "$WS_BROADCASTING" -eq 0 ]; then
        echo "   ⚠️  AVISO: No hay broadcasting reciente (puede ser fin de semana)"
    fi
    
    WS_NOGROUP=$(docker logs tradeul_websocket_server --tail 100 2>&1 | grep -c "NOGROUP" || echo "0")
    echo "   Errores NOGROUP: $WS_NOGROUP"
    if [ "$WS_NOGROUP" -gt 10 ]; then
        echo "   ❌ PROBLEMA: Consumer groups perdidos"
        EXIT_CODE=10
    fi
fi

echo ""

# ============================================================================
# 5. FRONTEND - Verificación HTTP
# ============================================================================
echo "🌐 5. VERIFICANDO FRONTEND..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

FRONTEND_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/scanner 2>/dev/null || echo "000")
echo "   HTTP status /scanner: $FRONTEND_HTTP"
if [ "$FRONTEND_HTTP" != "200" ]; then
    echo "   ❌ PROBLEMA: Frontend no responde o error"
    EXIT_CODE=11
else
    echo "   ✅ Frontend responde"
fi

# Verificar que worker existe
WORKER_EXISTS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/workers/websocket-shared.js 2>/dev/null || echo "000")
echo "   SharedWorker existe: $WORKER_EXISTS"
if [ "$WORKER_EXISTS" != "200" ]; then
    echo "   ❌ PROBLEMA: SharedWorker no accesible"
    EXIT_CODE=12
else
    echo "   ✅ SharedWorker accesible"
fi

echo ""

# ============================================================================
# 6. RESUMEN Y DIAGNÓSTICO
# ============================================================================
echo "📋 6. DIAGNÓSTICO FINAL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ SISTEMA FUNCIONANDO CORRECTAMENTE"
    echo ""
    echo "Todas las verificaciones pasaron:"
    echo "  ✅ Redis con metadata completos"
    echo "  ✅ Backend services healthy"
    echo "  ✅ API devolviendo datos"
    echo "  ✅ WebSocket broadcasting"
    echo "  ✅ Frontend accesible"
    echo ""
    echo "Frontend debería mostrar datos en tiempo real."
    
elif [ $EXIT_CODE -le 4 ]; then
    echo "🔴 PROBLEMA EN REDIS"
    echo ""
    echo "El problema está en la capa de datos:"
    echo "  - Metadata faltantes o snapshot vacío"
    echo "  - Ejecutar: docker exec tradeul_data_maintenance python scripts/sync_redis_safe.py"
    echo "  - Luego: docker restart tradeul_scanner tradeul_websocket_server"
    
elif [ $EXIT_CODE -le 7 ]; then
    echo "🔴 PROBLEMA EN BACKEND SERVICES"
    echo ""
    echo "Uno o más servicios no están corriendo:"
    echo "  - Verificar: docker ps"
    echo "  - Iniciar: curl -X POST http://localhost:8003/api/ingest/start"
    echo "  - Iniciar: curl -X POST http://localhost:8005/api/scanner/start"
    
elif [ $EXIT_CODE -le 10 ]; then
    echo "🔴 PROBLEMA EN WEBSOCKET"
    echo ""
    echo "WebSocket no está broadcasting o tiene errores:"
    echo "  - Verificar: docker logs tradeul_websocket_server --tail 100"
    echo "  - Reiniciar: docker restart tradeul_websocket_server"
    
else
    echo "🔴 PROBLEMA EN FRONTEND"
    echo ""
    echo "El frontend no carga o SharedWorker no funciona:"
    echo "  - Verificar: ps aux | grep 'next dev'"
    echo "  - Reiniciar: cd frontend && pkill -f 'next dev' && npm run dev"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Timestamp: $(date)"
echo "Exit code: $EXIT_CODE"

exit $EXIT_CODE

