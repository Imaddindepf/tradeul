#!/bin/bash
# =====================================================
# Setup Script: Búsqueda de Tickers Ultrarrápida
# =====================================================
# Este script configura índices de BD para búsqueda < 50ms

set -e  # Exit on error

echo "🔍 TradeUL - Ticker Search Optimization Setup"
echo "=============================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: docker-compose no está instalado${NC}"
    echo "Instalar con: apt install docker-compose"
    exit 1
fi

# Use docker compose (new) or docker-compose (old)
DOCKER_COMPOSE="docker-compose"
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
fi

echo -e "${BLUE}📦 Verificando servicios de Docker...${NC}"
if ! $DOCKER_COMPOSE ps | grep -q timescaledb; then
    echo -e "${YELLOW}⚠️  TimescaleDB no está corriendo${NC}"
    echo "Iniciar con: $DOCKER_COMPOSE up -d timescaledb"
    exit 1
fi

echo -e "${GREEN}✅ TimescaleDB está corriendo${NC}"
echo ""

# Check if tickers_unified table exists
echo -e "${BLUE}🔍 Verificando tabla tickers_unified...${NC}"
TABLE_EXISTS=$($DOCKER_COMPOSE exec -T timescaledb psql -U tradeul_user -d tradeul -tAc \
    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tickers_unified');")

if [ "$TABLE_EXISTS" != "t" ]; then
    echo -e "${RED}❌ Error: Tabla tickers_unified no existe${NC}"
    echo "Crear primero con: $DOCKER_COMPOSE exec timescaledb psql -U tradeul_user -d tradeul < scripts/init_db.sql"
    exit 1
fi

echo -e "${GREEN}✅ Tabla tickers_unified existe${NC}"

# Check row count
ROW_COUNT=$($DOCKER_COMPOSE exec -T timescaledb psql -U tradeul_user -d tradeul -tAc \
    "SELECT COUNT(*) FROM tickers_unified;")

echo -e "${BLUE}📊 Tickers en BD: ${GREEN}${ROW_COUNT}${NC}"

if [ "$ROW_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  No hay tickers en la BD. El buscador no devolverá resultados.${NC}"
    echo "Cargar tickers con: docker-compose exec data_maintenance python -m tasks.load_ohlc"
fi

echo ""
echo -e "${BLUE}🚀 Creando índices optimizados...${NC}"

# Execute SQL script
$DOCKER_COMPOSE exec -T timescaledb psql -U tradeul_user -d tradeul < scripts/add_ticker_search_indexes.sql

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Índices creados correctamente${NC}"
else
    echo -e "${RED}❌ Error al crear índices${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}🧪 Ejecutando tests de performance...${NC}"

# Test 1: Búsqueda exacta
echo -e "${BLUE}  Test 1: Búsqueda exacta (AAPL)${NC}"
EXEC_TIME=$($DOCKER_COMPOSE exec -T timescaledb psql -U tradeul_user -d tradeul -tAc \
    "EXPLAIN ANALYZE SELECT symbol, company_name FROM tickers_unified WHERE symbol = 'AAPL' AND is_actively_trading = true;" \
    2>/dev/null | grep "Execution Time" | awk '{print $3}')

if [ ! -z "$EXEC_TIME" ]; then
    echo -e "    Execution Time: ${GREEN}${EXEC_TIME} ms${NC}"
    
    # Check if < 50ms
    if (( $(echo "$EXEC_TIME < 50" | bc -l 2>/dev/null || echo 0) )); then
        echo -e "    ${GREEN}✅ < 50ms target${NC}"
    else
        echo -e "    ${YELLOW}⚠️  > 50ms (puede mejorar con más datos)${NC}"
    fi
fi

# Test 2: Búsqueda por prefijo
echo -e "${BLUE}  Test 2: Búsqueda por prefijo (AA%)${NC}"
EXEC_TIME=$($DOCKER_COMPOSE exec -T timescaledb psql -U tradeul_user -d tradeul -tAc \
    "EXPLAIN ANALYZE SELECT symbol, company_name FROM tickers_unified WHERE symbol ILIKE 'AA%' AND is_actively_trading = true LIMIT 10;" \
    2>/dev/null | grep "Execution Time" | awk '{print $3}')

if [ ! -z "$EXEC_TIME" ]; then
    echo -e "    Execution Time: ${GREEN}${EXEC_TIME} ms${NC}"
    
    if (( $(echo "$EXEC_TIME < 50" | bc -l 2>/dev/null || echo 0) )); then
        echo -e "    ${GREEN}✅ < 50ms target${NC}"
    else
        echo -e "    ${YELLOW}⚠️  > 50ms${NC}"
    fi
fi

echo ""
echo -e "${BLUE}🔄 Reiniciando servicio ticker_metadata...${NC}"
$DOCKER_COMPOSE restart ticker_metadata > /dev/null 2>&1

# Wait for service to be ready
echo -e "${BLUE}⏳ Esperando que el servicio esté listo...${NC}"
sleep 3

# Test endpoint
echo -e "${BLUE}🌐 Testeando endpoint HTTP...${NC}"
HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" "http://157.180.45.153:8010/api/v1/metadata/search?q=AA&limit=5" 2>/dev/null || echo "000")
HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -1)
HTTP_BODY=$(echo "$HTTP_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    RESULTS_COUNT=$(echo "$HTTP_BODY" | grep -o '"total":[0-9]*' | cut -d':' -f2)
    ELAPSED_MS=$(echo "$HTTP_BODY" | grep -o '"elapsed_ms":[0-9.]*' | cut -d':' -f2)
    
    echo -e "    Status: ${GREEN}HTTP $HTTP_CODE ✅${NC}"
    echo -e "    Resultados: ${GREEN}$RESULTS_COUNT${NC}"
    
    if [ ! -z "$ELAPSED_MS" ]; then
        echo -e "    Tiempo: ${GREEN}${ELAPSED_MS} ms${NC}"
        
        if (( $(echo "$ELAPSED_MS < 100" | bc -l 2>/dev/null || echo 0) )); then
            echo -e "    ${GREEN}✅ Excelente performance (<100ms)${NC}"
        fi
    fi
else
    echo -e "    Status: ${RED}HTTP $HTTP_CODE ❌${NC}"
    echo -e "${YELLOW}⚠️  El endpoint no responde correctamente${NC}"
    echo "    Verificar logs: docker-compose logs ticker_metadata"
fi

echo ""
echo -e "${GREEN}=============================================="
echo "✅ Setup Completado"
echo "==============================================   ${NC}"
echo ""
echo -e "${BLUE}📋 Próximos pasos:${NC}"
echo ""
echo "1. Abrir en browser: http://localhost:3000/sec-filings"
echo "2. Escribir en el buscador: 'AA' o 'Apple'"
echo "3. Deberías ver sugerencias en < 200ms"
echo ""
echo -e "${BLUE}📖 Documentación completa:${NC}"
echo "   cat docs/TICKER_SEARCH_OPTIMIZATION.md"
echo ""
echo -e "${BLUE}🐛 Si hay problemas:${NC}"
echo "   - Ver logs: docker-compose logs ticker_metadata"
echo "   - Verificar BD: docker-compose exec timescaledb psql -U tradeul_user -d tradeul"
echo "   - Test manual: curl 'http://157.180.45.153:8010/api/v1/metadata/search?q=AA'"
echo ""

