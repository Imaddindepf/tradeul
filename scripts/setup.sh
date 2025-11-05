#!/bin/bash

# =============================================
# TRADEUL SCANNER - SCRIPT DE SETUP AUTOMATIZADO
# =============================================

set -e  # Exit on error

echo "🚀 Iniciando setup de Tradeul Scanner..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================
# FUNCIONES AUXILIARES
# =============================================

check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✅ $2 instalado${NC}"
        return 0
    else
        echo -e "${RED}❌ $2 no está instalado${NC}"
        return 1
    fi
}

# Detectar si usar 'docker compose' o 'docker-compose'
detect_docker_compose() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    elif docker-compose version &> /dev/null; then
        echo "docker-compose"
    else
        echo ""
    fi
}

wait_for_service() {
    local service=$1
    local max_attempts=$2
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if docker exec $service pg_isready -U tradeul_user -d tradeul_scanner &> /dev/null 2>&1 || \
           docker exec $service redis-cli ping &> /dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        echo "Esperando $service... ($attempt/$max_attempts)"
        sleep 2
    done
    return 1
}

# =============================================
# 1. VERIFICAR PRE-REQUISITOS
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 1: VERIFICACIÓN DE PRE-REQUISITOS${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check Docker
if ! check_command docker "Docker"; then
    echo ""
    echo "📥 Instala Docker desde:"
    echo "   macOS:   https://docs.docker.com/desktop/install/mac-install/"
    echo "   Windows: https://docs.docker.com/desktop/install/windows-install/"
    echo "   Linux:   https://docs.docker.com/engine/install/"
    exit 1
fi

# Check Docker Compose (detectar versión)
DOCKER_COMPOSE=$(detect_docker_compose)
if [ -z "$DOCKER_COMPOSE" ]; then
    echo -e "${RED}❌ Docker Compose no está disponible${NC}"
    echo ""
    echo "Docker Compose debería venir con Docker Desktop"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose instalado${NC} (usando: $DOCKER_COMPOSE)"

# Check Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker no está corriendo${NC}"
    echo "Por favor, inicia Docker Desktop y vuelve a ejecutar este script"
    exit 1
fi
echo -e "${GREEN}✅ Docker está corriendo${NC}"

# Check Python (optional)
if check_command python3 "Python3"; then
    PYTHON_AVAILABLE=true
else
    echo -e "${YELLOW}⚠️  Python3 no disponible (opcional)${NC}"
    PYTHON_AVAILABLE=false
fi

echo ""

# =============================================
# 2. CONFIGURAR VARIABLES DE ENTORNO
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 2: CONFIGURACIÓN DE VARIABLES${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

if [ -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Archivo .env ya existe${NC}"
    echo ""
    read -p "¿Deseas usar el .env existente? (Y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "Creando nuevo .env..."
        rm .env
    else
        echo -e "${GREEN}✅ Usando .env existente${NC}"
    fi
fi

if [ ! -f ".env" ]; then
    echo ""
    echo -e "${YELLOW}📝 Necesitamos tus API Keys:${NC}"
    echo ""
    echo "Para obtener tus API Keys:"
    echo "  - Polygon: https://polygon.io/dashboard/api-keys"
    echo "  - FMP:     https://financialmodelingprep.com/developer/docs"
    echo ""
    
    read -p "Polygon API Key: " POLYGON_KEY
    if [ -z "$POLYGON_KEY" ]; then
        echo -e "${RED}❌ Polygon API Key es requerida${NC}"
        exit 1
    fi
    
    read -p "FMP API Key: " FMP_KEY
    if [ -z "$FMP_KEY" ]; then
        echo -e "${RED}❌ FMP API Key es requerida${NC}"
        exit 1
    fi
    
    cat > .env << EOF
# ==============================================
# API KEYS
# ==============================================
POLYGON_API_KEY=${POLYGON_KEY}
FMP_API_KEY=${FMP_KEY}

# ==============================================
# REDIS
# ==============================================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# ==============================================
# TIMESCALEDB (PostgreSQL)
# ==============================================
POSTGRES_HOST=timescaledb
POSTGRES_PORT=5432
POSTGRES_DB=tradeul_scanner
POSTGRES_USER=tradeul_user
POSTGRES_PASSWORD=tradeul_password_secure_123

# ==============================================
# SERVICIOS
# ==============================================
API_GATEWAY_PORT=8000
ORCHESTRATOR_PORT=8001
MARKET_SESSION_PORT=8002
DATA_INGEST_PORT=8003
HISTORICAL_PORT=8004
SCANNER_PORT=8005
POLYGON_WS_PORT=8006
ANALYTICS_PORT=8007
ADMIN_PANEL_PORT=8008

# ==============================================
# CONFIGURACIÓN
# ==============================================
LOG_LEVEL=INFO
ENVIRONMENT=development
TIMEZONE=America/New_York

# Scanner
SCANNER_UNIVERSE_SIZE=11000
SCANNER_FILTERED_MAX=1000
SNAPSHOT_INTERVAL_SECONDS=5

# RVOL
RVOL_HISTORY_DAYS=10
RVOL_SLOT_SIZE_MINUTES=5
RVOL_INCLUDE_EXTENDED_HOURS=true
EOF
    
    echo -e "${GREEN}✅ Archivo .env creado${NC}"
fi

echo ""

# =============================================
# 3. LIMPIAR INFRAESTRUCTURA ANTERIOR (OPCIONAL)
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 3: LIMPIEZA (OPCIONAL)${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

if docker ps -a | grep -q "tradeul"; then
    echo -e "${YELLOW}⚠️  Se detectaron contenedores existentes${NC}"
    echo ""
    read -p "¿Deseas limpiar la instalación anterior? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🧹 Limpiando contenedores anteriores..."
        $DOCKER_COMPOSE down -v
        echo -e "${GREEN}✅ Limpieza completada${NC}"
    fi
fi

echo ""

# =============================================
# 4. LEVANTAR INFRAESTRUCTURA
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 4: INFRAESTRUCTURA BASE${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

echo "🐳 Levantando Redis y TimescaleDB..."
$DOCKER_COMPOSE up -d redis timescaledb

echo ""
echo "⏳ Esperando que los servicios estén listos..."
echo "   (esto puede tomar 30-60 segundos)"
echo ""

# Wait for TimescaleDB
if wait_for_service tradeul-timescaledb 30; then
    echo -e "${GREEN}✅ TimescaleDB listo${NC}"
else
    echo -e "${RED}❌ TimescaleDB no respondió a tiempo${NC}"
    echo "Revisa los logs: docker logs tradeul-timescaledb"
    exit 1
fi

# Wait for Redis
if wait_for_service tradeul-redis 10; then
    echo -e "${GREEN}✅ Redis listo${NC}"
else
    echo -e "${RED}❌ Redis no respondió a tiempo${NC}"
    exit 1
fi

echo ""

# =============================================
# 5. INICIALIZAR BASE DE DATOS
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 5: INICIALIZACIÓN DE BASE DE DATOS${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

echo "🗄️  Ejecutando script de inicialización..."

# Copy SQL script to container
docker cp scripts/init_db.sql tradeul-timescaledb:/tmp/init_db.sql

# Execute SQL script
if docker exec tradeul-timescaledb psql -U tradeul_user -d tradeul_scanner -f /tmp/init_db.sql > /tmp/init_db.log 2>&1; then
    echo -e "${GREEN}✅ Base de datos inicializada correctamente${NC}"
    echo ""
    echo "Tablas creadas:"
    echo "  - ticks (time-series)"
    echo "  - ticker_metadata"
    echo "  - scan_results (time-series)"
    echo "  - volume_slots (para RVOL)"
    echo "  - scanner_filters"
    echo "  - market_holidays"
    echo "  - market_sessions_log"
    echo "  - ticker_universe"
else
    echo -e "${RED}❌ Error al inicializar base de datos${NC}"
    echo "Ver logs en: /tmp/init_db.log"
    cat /tmp/init_db.log
    exit 1
fi

echo ""

# =============================================
# 6. CONSTRUIR IMÁGENES
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 6: CONSTRUCCIÓN DE IMÁGENES${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

echo "🔨 Construyendo imágenes de Docker..."
echo "   (primera vez: 5-10 minutos)"
echo ""

if $DOCKER_COMPOSE build; then
    echo -e "${GREEN}✅ Imágenes construidas correctamente${NC}"
else
    echo -e "${RED}❌ Error al construir imágenes${NC}"
    exit 1
fi

echo ""

# =============================================
# 7. CARGAR UNIVERSO INICIAL (OPCIONAL)
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 7: CARGA DE UNIVERSO DE TICKERS${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

if [ "$PYTHON_AVAILABLE" = true ]; then
    echo "📦 Cargando ~11,000 tickers de Polygon..."
    echo "   Fuente: Polygon /v3/reference/tickers"
    echo "   Filtros: market=stocks, locale=us, active=true"
    echo "   (esto puede tomar 2-3 minutos)"
    echo ""
    
    if python3 scripts/load_universe_polygon.py; then
        echo -e "${GREEN}✅ Universo cargado correctamente${NC}"
    else
        echo -e "${YELLOW}⚠️  Error al cargar universo (no crítico)${NC}"
        echo "Puedes cargar manualmente después:"
        echo "  python3 scripts/load_universe_polygon.py"
    fi
else
    echo -e "${YELLOW}⚠️  Python3 no disponible${NC}"
    echo ""
    echo "Para cargar el universo de tickers manualmente:"
    echo "  python3 scripts/load_universe_polygon.py"
fi

echo ""

# =============================================
# 8. LEVANTAR TODOS LOS SERVICIOS
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 8: INICIO DE SERVICIOS${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

echo "🚀 Levantando todos los servicios..."
$DOCKER_COMPOSE up -d

echo ""
echo "⏳ Esperando que los servicios estén listos..."
echo "   (30-60 segundos)"
sleep 15

echo ""

# =============================================
# 9. VERIFICAR SALUD DEL SISTEMA
# =============================================

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  PASO 9: VERIFICACIÓN DE SERVICIOS${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

echo "🔍 Verificando health checks..."
echo ""

# Check each service
declare -A services=(
    ["API Gateway"]=8000
    ["Market Session"]=8002
    ["Data Ingest"]=8003
    ["Historical"]=8004
    ["Scanner"]=8005
    ["Analytics"]=8007
    ["Polygon WS"]=8006
)

all_healthy=true
for name in "${!services[@]}"; do
    port=${services[$name]}
    if curl -s -f http://localhost:${port}/health > /dev/null 2>&1; then
        echo -e "  ${GREEN}✅ $name${NC}"
    else
        echo -e "  ${YELLOW}⏳ $name (iniciando...)${NC}"
        all_healthy=false
    fi
done

echo ""

if [ "$all_healthy" = false ]; then
    echo -e "${YELLOW}⚠️  Algunos servicios aún están iniciando${NC}"
    echo "   Espera 1-2 minutos y verifica con:"
    echo "   curl http://localhost:8000/health"
fi

# =============================================
# 10. INFORMACIÓN FINAL
# =============================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 ¡SETUP COMPLETADO!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 ENDPOINTS DISPONIBLES:${NC}"
echo ""
echo "  🌐 API Gateway:      http://localhost:8000"
echo "  🕒 Market Session:   http://localhost:8002"
echo "  📥 Data Ingest:      http://localhost:8003"
echo "  📚 Historical:       http://localhost:8004"
echo "  🔍 Scanner:          http://localhost:8005"
echo "  📈 Analytics:        http://localhost:8007"
echo "  🔌 Polygon WS:       http://localhost:8006"
echo ""
echo "  💾 Redis:            localhost:6379"
echo "  🗄️  TimescaleDB:      localhost:5432"
echo ""
echo -e "${BLUE}🔍 VERIFICAR FUNCIONAMIENTO:${NC}"
echo ""
echo "  # Health check general"
echo "  curl http://localhost:8000/health"
echo ""
echo "  # Sesión de mercado actual"
echo "  curl http://localhost:8002/session/current | jq"
echo ""
echo "  # Tickers filtrados"
echo "  curl http://localhost:8000/api/v1/scanner/filtered | jq"
echo ""
echo "  # RVOL de un ticker específico"
echo "  curl http://localhost:8000/api/v1/rvol/AAPL | jq"
echo ""
echo -e "${BLUE}📖 COMANDOS ÚTILES:${NC}"
echo ""
echo "  # Ver logs en tiempo real"
echo "  $DOCKER_COMPOSE logs -f"
echo ""
echo "  # Ver logs de un servicio específico"
echo "  $DOCKER_COMPOSE logs -f scanner"
echo ""
echo "  # Estado de todos los servicios"
echo "  $DOCKER_COMPOSE ps"
echo ""
echo "  # Reiniciar un servicio"
echo "  $DOCKER_COMPOSE restart scanner"
echo ""
echo "  # Detener todos los servicios"
echo "  $DOCKER_COMPOSE down"
echo ""
echo "  # Ver uso de recursos"
echo "  docker stats"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANTE:${NC}"
echo ""
echo "  📝 El sistema necesita unos minutos para empezar a procesar datos"
echo "  🕐 Si el mercado está cerrado, verás pocos tickers filtrados"
echo "  📊 Los snapshots se obtienen cada 5 segundos"
echo "  🔍 RVOL se calcula por slots de 5 minutos"
echo ""
echo -e "${BLUE}📚 DOCUMENTACIÓN:${NC}"
echo ""
echo "  README.md            - Documentación principal"
echo "  ARCHITECTURE.md      - Arquitectura del sistema"
echo "  docs/QUICKSTART.md   - Guía paso a paso"
echo ""
echo -e "${GREEN}🚀 ¡Tu scanner está listo para procesar 11,000 tickers!${NC}"
echo ""
