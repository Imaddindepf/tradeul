#!/usr/bin/env bash
# ============================================================
# Tradeul Frontend FAST Deploy — corte mínimo (~3-5 s)
#
# Usage:  ./scripts/deploy-frontend-fast.sh
#
# El deploy clásico (deploy-frontend.sh) para el servicio ANTES de compilar:
# ~80-180 s de caída, y cualquier usuario activo ve celdas TVC blancas y
# assets 502 (incidente 2026-07-26). Este script compila FUERA de producción
# y solo para el servicio para el swap del build:
#   1. Checks de contrato (sin downtime)
#   2. rsync del código a /opt/tradeul/frontend-staging (node_modules symlink)
#   3. npm run build en staging — prod sigue sirviendo el build viejo
#   4. Reload de Caddy (aún sin downtime)
#   5. stop → rsync .next staging→prod (mismo disco, ~1-2 s) → start
#   6. Health check
# ============================================================

set -euo pipefail

FRONTEND_DIR="/opt/tradeul/frontend"
STAGING_DIR="/opt/tradeul/frontend-staging"
SERVICE_NAME="tradeul-frontend"
HEALTH_URL="https://tradeul.com"
MAX_HEALTH_RETRIES=15
HEALTH_INTERVAL=2

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[deploy]${NC} $1"; }
ok()    { echo -e "${GREEN}[  ok  ]${NC} $1"; }
warn()  { echo -e "${YELLOW}[ warn ]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL!]${NC} $1"; exit 1; }

cd "$FRONTEND_DIR"

OLD_BUILD_ID="(none)"
[ -f ".next/BUILD_ID" ] && OLD_BUILD_ID=$(cat .next/BUILD_ID)
log "Current build ID: $OLD_BUILD_ID"

# ── Step 0: Contract checks (sin downtime) ──────────────────
log "Running filter parity check..."
if ! npm run check:event-filter-parity >/dev/null 2>&1; then
    fail "Parity check failed. Aborting (service untouched)."
fi
ok "Filter parity check passed"

# ── Step 1: Sync a staging ──────────────────────────────────
log "Syncing source to staging ($STAGING_DIR)..."
mkdir -p "$STAGING_DIR"
rsync -a --delete --exclude .next --exclude node_modules "$FRONTEND_DIR/" "$STAGING_DIR/"
ln -sfn "$FRONTEND_DIR/node_modules" "$STAGING_DIR/node_modules"
ok "Staging synced"

# ── Step 2: Build en staging (prod sigue arriba) ────────────
log "Building in staging (service stays UP)..."
BUILD_START=$(date +%s)
cd "$STAGING_DIR"
rm -rf .next
if ! npm run build 2>&1; then
    fail "Build failed. Production untouched and still serving $OLD_BUILD_ID."
fi
BUILD_END=$(date +%s)
NEW_BUILD_ID=$(cat "$STAGING_DIR/.next/BUILD_ID")
ok "Build completed in $((BUILD_END - BUILD_START))s — Build ID: $NEW_BUILD_ID"

# ── Step 3: Reload Caddy (sin downtime) ─────────────────────
log "Reloading Caddy..."
if timeout 10 systemctl reload caddy 2>/dev/null; then
    ok "Caddy reloaded"
else
    warn "Caddy reload timed out or failed (non-critical, continuing)"
fi

# ── Step 4: Swap con corte mínimo ───────────────────────────
# Limpiezas NO críticas fuera de la ventana de corte.
rm -rf "$FRONTEND_DIR/node_modules/.cache"
log "Swapping build (minimal downtime window starts now)..."
SWAP_START=$(date +%s)
# next-server ignora SIGTERM y systemd esperaría su timeout de 90 s
# ("State 'final-sigterm' timed out", visto 2026-07-26): stop SIN bloquear,
# espera breve y SIGKILL — next start es stateless, matarlo es seguro.
systemctl stop --no-block "$SERVICE_NAME" 2>/dev/null || true
sleep 2
# SIGKILL al CGROUP de la unidad: mata next-server aunque haya cerrado ya el
# puerto pero siga vivo ignorando SIGTERM (visto 2026-07-26: el chequeo por
# puerto no disparaba y el stop esperaba los 90 s de systemd). A diferencia de
# lsof+kill, no puede tocar procesos ajenos (Caddy).
systemctl kill -s SIGKILL "$SERVICE_NAME" 2>/dev/null || true
# Con el cgroup vacío este stop es inmediato y deja la unidad lista para start.
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
# --exclude cache: .next/cache son packs de build de webpack (GBs) que
# next start no usa — copiarlos dentro de la ventana costó 92 s el 2026-07-26.
rsync -a --delete --exclude cache "$STAGING_DIR/.next/" "$FRONTEND_DIR/.next/"
systemctl start "$SERVICE_NAME"
SWAP_END=$(date +%s)
ok "Swap done — service window: $((SWAP_END - SWAP_START))s"

# ── Step 5: Health check ────────────────────────────────────
log "Running health check..."
HEALTH_PASSED=false
for i in $(seq 1 $MAX_HEALTH_RETRIES); do
    sleep "$HEALTH_INTERVAL"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "307" ]; then
        ok "Health check passed (HTTP $HTTP_CODE)"
        HEALTH_PASSED=true
        break
    else
        log "Attempt $i/$MAX_HEALTH_RETRIES: HTTP $HTTP_CODE..."
    fi
done

if [ "$HEALTH_PASSED" = false ]; then
    fail "Health check failed! Recover with: cd $FRONTEND_DIR && ./scripts/deploy-frontend.sh"
fi

CACHE_HEADER=$(curl -sI "$HEALTH_URL" 2>/dev/null | grep -i "^cache-control:" | head -1)
if echo "$CACHE_HEADER" | grep -qi "no-cache"; then
    ok "Cache headers correct: $CACHE_HEADER"
else
    warn "Cache headers may need review: $CACHE_HEADER"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Fast deploy complete!${NC}"
echo -e "${GREEN}  Build:    $OLD_BUILD_ID → $NEW_BUILD_ID${NC}"
echo -e "${GREEN}  Downtime: $((SWAP_END - SWAP_START))s (build corrió con el servicio arriba)${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
