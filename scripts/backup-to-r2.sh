#!/usr/bin/env bash
# =============================================================================
# Tradeul - Backup Diario a Cloudflare R2
# =============================================================================
# Hace backup de: TimescaleDB, Redis, .env, docker-compose.yml
# Sube a: Cloudflare R2 (bucket tradeul-data, carpeta backups/)
# Rotación: 7 diarios + 4 semanales (últimos domingos)
#
# Uso manual:  ./scripts/backup-to-r2.sh
# Cron diario: 0 3 * * * /opt/tradeul/scripts/backup-to-r2.sh >> /var/log/tradeul-backup.log 2>&1
# =============================================================================

set -euo pipefail

# --- Configuración ---
BACKUP_DIR="/tmp/tradeul-backup"
PROJECT_DIR="/opt/tradeul"
R2_REMOTE="r2:tradeul-data/backups"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)  # 1=lunes, 7=domingo
DAILY_RETENTION=7
WEEKLY_RETENTION=4

# Contenedores
TIMESCALE_CONTAINER="tradeul_timescale"
REDIS_CONTAINER="tradeul_redis"

# Credenciales (del .env)
PG_USER="tradeul_user"
PG_DB="tradeul"
REDIS_PASS="tradeul_redis_secure_2024"

# Colores para log
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}✅${NC} $1"; }
warn() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}⚠️${NC} $1"; }
error() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}❌${NC} $1"; }

# --- Inicio ---
echo "============================================================"
log "INICIO BACKUP TRADEUL - $DATE"
echo "============================================================"
START_TIME=$(date +%s)

# Crear directorio temporal
rm -rf "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# =============================================================================
# 1. TIMESCALEDB (lo más crítico - ~13GB → ~70MB comprimido)
# =============================================================================
log "Dumping TimescaleDB..."
PGDUMP_FILE="$BACKUP_DIR/timescaledb_${TIMESTAMP}.sql.gz"

docker exec "$TIMESCALE_CONTAINER" pg_dump \
    -U "$PG_USER" \
    -d "$PG_DB" \
    --no-owner \
    --no-privileges \
    --verbose \
    2>/dev/null | pigz -p 4 > "$PGDUMP_FILE"

PGDUMP_SIZE=$(du -sh "$PGDUMP_FILE" | cut -f1)
log "TimescaleDB dump completado: $PGDUMP_SIZE"

# =============================================================================
# 2. REDIS (dump.rdb - ~192MB → ~60MB comprimido)
# =============================================================================
log "Copiando Redis dump..."

# Forzar un BGSAVE para tener el RDB más fresco
docker exec "$REDIS_CONTAINER" redis-cli --no-auth-warning -a "$REDIS_PASS" BGSAVE > /dev/null 2>&1
sleep 3  # Esperar a que termine el BGSAVE

REDIS_FILE="$BACKUP_DIR/redis_${TIMESTAMP}.rdb.gz"
docker cp "$REDIS_CONTAINER":/data/dump.rdb - 2>/dev/null | pigz -p 4 > "$REDIS_FILE"

REDIS_SIZE=$(du -sh "$REDIS_FILE" | cut -f1)
log "Redis dump completado: $REDIS_SIZE"

# =============================================================================
# 3. CONFIGURACIÓN (.env, docker-compose.yml, scripts críticos)
# =============================================================================
log "Copiando configuración..."
CONFIG_FILE="$BACKUP_DIR/config_${TIMESTAMP}.tar.gz"

tar czf "$CONFIG_FILE" \
    -C "$PROJECT_DIR" \
    .env \
    docker-compose.yml \
    scripts/init_db.sql \
    2>/dev/null

CONFIG_SIZE=$(du -sh "$CONFIG_FILE" | cut -f1)
log "Config backup completado: $CONFIG_SIZE"

# =============================================================================
# 4. CREAR MANIFIESTO
# =============================================================================
cat > "$BACKUP_DIR/MANIFEST_${TIMESTAMP}.txt" <<EOF
=== TRADEUL BACKUP MANIFEST ===
Date: $DATE
Timestamp: $TIMESTAMP
Server: $(hostname) ($(curl -s ifconfig.me 2>/dev/null || echo "unknown"))

Files:
  - timescaledb_${TIMESTAMP}.sql.gz  ($PGDUMP_SIZE) - PostgreSQL/TimescaleDB full dump
  - redis_${TIMESTAMP}.rdb.gz        ($REDIS_SIZE) - Redis RDB snapshot
  - config_${TIMESTAMP}.tar.gz       ($CONFIG_SIZE) - .env + docker-compose.yml + init_db.sql

Docker containers at backup time:
$(docker ps --format "  - {{.Names}}: {{.Status}}" 2>/dev/null)

TimescaleDB tables:
$(docker exec "$TIMESCALE_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -c "SELECT tablename, pg_size_pretty(pg_total_relation_size('public.'||tablename)) as size FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size('public.'||tablename) DESC LIMIT 10;" 2>/dev/null)

Redis info:
  Keys: $(docker exec "$REDIS_CONTAINER" redis-cli --no-auth-warning -a "$REDIS_PASS" DBSIZE 2>/dev/null)
  Memory: $(docker exec "$REDIS_CONTAINER" redis-cli --no-auth-warning -a "$REDIS_PASS" INFO memory 2>/dev/null | grep used_memory_human)

Restore instructions:
  See /opt/tradeul/scripts/restore-from-r2.sh
EOF

# =============================================================================
# 5. SUBIR A CLOUDFLARE R2
# =============================================================================
log "Subiendo a Cloudflare R2..."

# Subir como backup diario
DAILY_PATH="${R2_REMOTE}/daily/${DATE}"
rclone copy "$BACKUP_DIR/" "$DAILY_PATH/" --progress --transfers 4 2>&1 | tail -5

log "Subido a R2: $DAILY_PATH"

# Si es domingo, copiar también como backup semanal
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    WEEKLY_PATH="${R2_REMOTE}/weekly/${DATE}"
    rclone copy "$BACKUP_DIR/" "$WEEKLY_PATH/" --transfers 4 2>&1 | tail -3
    log "Backup semanal creado: $WEEKLY_PATH"
fi

# =============================================================================
# 6. ROTACIÓN - Eliminar backups antiguos
# =============================================================================
log "Rotando backups antiguos..."

# Obtener lista de backups diarios y eliminar los más antiguos
DAILY_DIRS=$(rclone lsd "${R2_REMOTE}/daily/" 2>/dev/null | awk '{print $NF}' | sort -r)
DAILY_COUNT=0
for dir in $DAILY_DIRS; do
    DAILY_COUNT=$((DAILY_COUNT + 1))
    if [ "$DAILY_COUNT" -gt "$DAILY_RETENTION" ]; then
        rclone purge "${R2_REMOTE}/daily/${dir}" 2>/dev/null
        warn "Eliminado backup diario antiguo: $dir"
    fi
done

# Rotar backups semanales
WEEKLY_DIRS=$(rclone lsd "${R2_REMOTE}/weekly/" 2>/dev/null | awk '{print $NF}' | sort -r)
WEEKLY_COUNT=0
for dir in $WEEKLY_DIRS; do
    WEEKLY_COUNT=$((WEEKLY_COUNT + 1))
    if [ "$WEEKLY_COUNT" -gt "$WEEKLY_RETENTION" ]; then
        rclone purge "${R2_REMOTE}/weekly/${dir}" 2>/dev/null
        warn "Eliminado backup semanal antiguo: $dir"
    fi
done

# =============================================================================
# 7. LIMPIEZA LOCAL
# =============================================================================
rm -rf "$BACKUP_DIR"
log "Directorio temporal limpiado"

# --- Resumen ---
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "============================================================"
log "BACKUP COMPLETADO en ${DURATION}s"
echo "  📦 TimescaleDB: $PGDUMP_SIZE"
echo "  📦 Redis:       $REDIS_SIZE"
echo "  📦 Config:      $CONFIG_SIZE"
echo "  ☁️  Destino:     $DAILY_PATH"
echo "  🗓️  Retención:   ${DAILY_RETENTION} diarios + ${WEEKLY_RETENTION} semanales"
echo "============================================================"
