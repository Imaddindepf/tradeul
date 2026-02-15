#!/usr/bin/env bash
# =============================================================================
# Tradeul - Restaurar Backup desde Cloudflare R2
# =============================================================================
# Uso:
#   ./scripts/restore-from-r2.sh                  # Lista backups disponibles
#   ./scripts/restore-from-r2.sh 2026-02-15       # Restaura backup de esa fecha
#   ./scripts/restore-from-r2.sh 2026-02-15 db    # Solo restaura TimescaleDB
#   ./scripts/restore-from-r2.sh 2026-02-15 redis # Solo restaura Redis
#   ./scripts/restore-from-r2.sh 2026-02-15 config # Solo restaura config
# =============================================================================

set -euo pipefail

R2_REMOTE="r2:tradeul-data/backups"
RESTORE_DIR="/tmp/tradeul-restore"
PROJECT_DIR="/opt/tradeul"

TIMESCALE_CONTAINER="tradeul_timescale"
REDIS_CONTAINER="tradeul_redis"
PG_USER="tradeul_user"
PG_DB="tradeul"
REDIS_PASS="tradeul_redis_secure_2024"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${GREEN}✅${NC} $1"; }
warn() { echo -e "${YELLOW}⚠️${NC} $1"; }
error() { echo -e "${RED}❌${NC} $1"; }
info() { echo -e "${CYAN}ℹ️${NC} $1"; }

# --- Sin argumentos: listar backups disponibles ---
if [ $# -eq 0 ]; then
    echo "============================================================"
    echo "  BACKUPS DISPONIBLES EN CLOUDFLARE R2"
    echo "============================================================"
    
    echo ""
    echo -e "${CYAN}📅 Backups Diarios:${NC}"
    rclone lsd "${R2_REMOTE}/daily/" 2>/dev/null | awk '{print "  " $NF}' | sort -r
    
    echo ""
    echo -e "${CYAN}📅 Backups Semanales:${NC}"
    rclone lsd "${R2_REMOTE}/weekly/" 2>/dev/null | awk '{print "  " $NF}' | sort -r
    
    echo ""
    echo "Uso: $0 <fecha> [db|redis|config|all]"
    echo "Ejemplo: $0 2026-02-15"
    exit 0
fi

TARGET_DATE="$1"
COMPONENT="${2:-all}"

# Verificar que el backup existe
BACKUP_PATH="${R2_REMOTE}/daily/${TARGET_DATE}"
if ! rclone lsd "$BACKUP_PATH" > /dev/null 2>&1; then
    # Intentar en semanales
    BACKUP_PATH="${R2_REMOTE}/weekly/${TARGET_DATE}"
    if ! rclone ls "$BACKUP_PATH/" > /dev/null 2>&1; then
        error "No se encontró backup para fecha: $TARGET_DATE"
        info "Ejecuta '$0' sin argumentos para ver backups disponibles"
        exit 1
    fi
    info "Usando backup semanal: $TARGET_DATE"
else
    info "Usando backup diario: $TARGET_DATE"
fi

echo "============================================================"
warn "RESTAURACIÓN DE BACKUP: $TARGET_DATE (componente: $COMPONENT)"
echo "============================================================"
echo ""
warn "⚠️  ESTO SOBREESCRIBIRÁ LOS DATOS ACTUALES ⚠️"
echo ""
read -p "¿Estás seguro? Escribe 'SI RESTAURAR' para continuar: " CONFIRM
if [ "$CONFIRM" != "SI RESTAURAR" ]; then
    error "Restauración cancelada."
    exit 1
fi

# Descargar backup
rm -rf "$RESTORE_DIR"
mkdir -p "$RESTORE_DIR"

log "Descargando backup de R2..."
rclone copy "$BACKUP_PATH/" "$RESTORE_DIR/" --progress

echo ""
info "Archivos descargados:"
ls -lh "$RESTORE_DIR/"

# =============================================================================
# RESTAURAR TIMESCALEDB
# =============================================================================
if [ "$COMPONENT" = "all" ] || [ "$COMPONENT" = "db" ]; then
    echo ""
    log "Restaurando TimescaleDB..."
    
    PGDUMP_FILE=$(ls "$RESTORE_DIR"/timescaledb_*.sql.gz 2>/dev/null | head -1)
    if [ -z "$PGDUMP_FILE" ]; then
        error "No se encontró archivo de TimescaleDB en el backup"
    else
        info "Archivo: $(basename $PGDUMP_FILE) ($(du -sh $PGDUMP_FILE | cut -f1))"
        
        # Detener servicios que usan la DB
        warn "Deteniendo servicios que usan TimescaleDB..."
        DEPENDENT_SERVICES=(
            tradeul_api_gateway
            tradeul_data_ingest
            tradeul_scanner
            tradeul_data_maintenance
            tradeul_websocket_server
            tradeul_ticker_metadata
            tradeul_dilution_tracker
            tradeul_dilution_worker
            tradeul_event_detector
            tradeul_sec_filings
            tradeul_benzinga_earnings
            tradeul_prediction_markets
            tradeul_analytics
            tradeul_ai_agent
        )
        
        for svc in "${DEPENDENT_SERVICES[@]}"; do
            docker stop "$svc" 2>/dev/null || true
        done
        
        # Recrear la base de datos
        warn "Recreando base de datos..."
        docker exec "$TIMESCALE_CONTAINER" psql -U "$PG_USER" -d postgres \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid <> pg_backend_pid();" 2>/dev/null || true
        docker exec "$TIMESCALE_CONTAINER" psql -U "$PG_USER" -d postgres \
            -c "DROP DATABASE IF EXISTS $PG_DB;" 2>/dev/null
        docker exec "$TIMESCALE_CONTAINER" psql -U "$PG_USER" -d postgres \
            -c "CREATE DATABASE $PG_DB OWNER $PG_USER;" 2>/dev/null
        docker exec "$TIMESCALE_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" \
            -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>/dev/null
        
        # Restaurar
        log "Importando dump (esto puede tardar unos minutos)..."
        pigz -d -c "$PGDUMP_FILE" | docker exec -i "$TIMESCALE_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" --quiet 2>/dev/null
        
        log "TimescaleDB restaurada correctamente"
        
        # Reiniciar servicios
        log "Reiniciando servicios..."
        for svc in "${DEPENDENT_SERVICES[@]}"; do
            docker start "$svc" 2>/dev/null || true
        done
    fi
fi

# =============================================================================
# RESTAURAR REDIS
# =============================================================================
if [ "$COMPONENT" = "all" ] || [ "$COMPONENT" = "redis" ]; then
    echo ""
    log "Restaurando Redis..."
    
    REDIS_FILE=$(ls "$RESTORE_DIR"/redis_*.rdb.gz 2>/dev/null | head -1)
    if [ -z "$REDIS_FILE" ]; then
        error "No se encontró archivo de Redis en el backup"
    else
        info "Archivo: $(basename $REDIS_FILE) ($(du -sh $REDIS_FILE | cut -f1))"
        
        # Descomprimir
        REDIS_RDB="$RESTORE_DIR/dump.rdb"
        pigz -d -c "$REDIS_FILE" > "$REDIS_RDB"
        
        # Detener Redis, reemplazar RDB, reiniciar
        warn "Reiniciando Redis con el backup..."
        docker stop "$REDIS_CONTAINER" 2>/dev/null
        
        # Copiar el RDB al volumen
        REDIS_DATA_PATH=$(docker inspect "$REDIS_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' 2>/dev/null)
        if [ -n "$REDIS_DATA_PATH" ]; then
            cp "$REDIS_RDB" "$REDIS_DATA_PATH/dump.rdb"
        else
            # Fallback: usar docker cp
            docker start "$REDIS_CONTAINER" 2>/dev/null
            sleep 2
            docker cp "$REDIS_RDB" "$REDIS_CONTAINER":/data/dump.rdb
            docker stop "$REDIS_CONTAINER" 2>/dev/null
        fi
        
        docker start "$REDIS_CONTAINER" 2>/dev/null
        sleep 3
        
        KEYS=$(docker exec "$REDIS_CONTAINER" redis-cli --no-auth-warning -a "$REDIS_PASS" DBSIZE 2>/dev/null)
        log "Redis restaurado - $KEYS"
    fi
fi

# =============================================================================
# RESTAURAR CONFIGURACIÓN
# =============================================================================
if [ "$COMPONENT" = "all" ] || [ "$COMPONENT" = "config" ]; then
    echo ""
    log "Restaurando configuración..."
    
    CONFIG_FILE=$(ls "$RESTORE_DIR"/config_*.tar.gz 2>/dev/null | head -1)
    if [ -z "$CONFIG_FILE" ]; then
        error "No se encontró archivo de config en el backup"
    else
        # No sobreescribir directamente, poner en directorio separado
        CONFIG_RESTORE="$RESTORE_DIR/config_extracted"
        mkdir -p "$CONFIG_RESTORE"
        tar xzf "$CONFIG_FILE" -C "$CONFIG_RESTORE"
        
        info "Archivos de configuración extraídos en: $CONFIG_RESTORE/"
        ls -la "$CONFIG_RESTORE/"
        
        echo ""
        warn "Los archivos de config se extrajeron en $CONFIG_RESTORE/"
        warn "Revísalos y cópialos manualmente a $PROJECT_DIR/ si es necesario:"
        echo "  cp $CONFIG_RESTORE/.env $PROJECT_DIR/.env"
        echo "  cp $CONFIG_RESTORE/docker-compose.yml $PROJECT_DIR/docker-compose.yml"
    fi
fi

# Limpieza
echo ""
info "Archivos de restore en: $RESTORE_DIR/ (elimina cuando termines)"
echo ""
echo "============================================================"
log "RESTAURACIÓN COMPLETADA"
echo "============================================================"
