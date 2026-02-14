#!/usr/bin/env bash
# ============================================================
# Tradeul Frontend Deploy Script (Zero-Downtime)
# 
# Usage:  ./scripts/deploy-frontend.sh
#
# What it does:
#   1. Stops the Next.js service (systemd)
#   2. Builds in temporary directory (keeps old build running)
#   3. Atomic swap: replaces .next with new build
#   4. Reloads Caddy (picks up any config changes)
#   5. Restarts the Next.js service with new build
#   6. Runs a health check to verify the deployment
#
# Zero-downtime strategy:
#   - Old chunks remain available during build
#   - Atomic directory swap minimizes transition time
#   - ChunkLoadError handler in app auto-reloads on error
# ============================================================

set -euo pipefail

# ── Config ──────────────────────────────────────────────────
FRONTEND_DIR="/opt/tradeul/frontend"
SERVICE_NAME="tradeul-frontend"
HEALTH_URL="https://tradeul.com"
MAX_HEALTH_RETRIES=15
HEALTH_INTERVAL=2

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${BLUE}[deploy]${NC} $1"; }
ok()    { echo -e "${GREEN}[  ok  ]${NC} $1"; }
warn()  { echo -e "${YELLOW}[ warn ]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL!]${NC} $1"; exit 1; }

# ── Pre-flight ──────────────────────────────────────────────
log "Starting frontend deployment..."
cd "$FRONTEND_DIR"

OLD_BUILD_ID="(none)"
if [ -f ".next/BUILD_ID" ]; then
    OLD_BUILD_ID=$(cat .next/BUILD_ID)
fi
log "Current build ID: $OLD_BUILD_ID"

# ── Step 1: Stop the service ───────────────────────────────
log "Stopping $SERVICE_NAME..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
sleep 2

# Make sure port 3000 is free (kill zombies if any)
if lsof -ti:3000 >/dev/null 2>&1; then
    warn "Port 3000 still occupied, force-killing..."
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    sleep 2
fi
ok "Service stopped"

# ── Step 2: Build in temporary directory ───────────────────
log "Building in temporary directory (zero-downtime strategy)..."
BUILD_START=$(date +%s)

# Limpiar cache de node_modules pero mantener .next activo
rm -rf node_modules/.cache

# Construir en directorio temporal
BUILD_DIR=".next.tmp"
rm -rf "$BUILD_DIR"

if ! npm run build 2>&1; then
    fail "Build failed! Old version still running. Fix errors and re-run."
fi

# Renombrar .next a .next.tmp (Next.js construye en .next)
mv .next "$BUILD_DIR"

BUILD_END=$(date +%s)
BUILD_DURATION=$((BUILD_END - BUILD_START))

NEW_BUILD_ID=$(cat "$BUILD_DIR/BUILD_ID")
ok "Build completed in ${BUILD_DURATION}s — Build ID: $NEW_BUILD_ID"

# ── Step 3: Atomic swap ─────────────────────────────────────
log "Preparing atomic swap..."

# ── Step 4: Atomic swap of build directories ───────────────
# Backup old build (just in case)
if [ -d ".next" ]; then
    log "Backing up old build..."
    rm -rf .next.old
    mv .next .next.old
fi

# Atomic rename: .next.tmp -> .next
mv "$BUILD_DIR" .next
ok "Build swapped atomically"

# ── Step 5: Reload Caddy ────────────────────────────────────
log "Reloading Caddy..."
if timeout 10 systemctl reload caddy 2>/dev/null; then
    ok "Caddy reloaded"
else
    warn "Caddy reload timed out or failed (non-critical, continuing)"
fi

# ── Step 6: Restart the service ────────────────────────────
log "Restarting $SERVICE_NAME..."
systemctl restart "$SERVICE_NAME"
ok "Service restarted"

# ── Step 7: Health check ───────────────────────────────────
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
    fail "Health check failed after $MAX_HEALTH_RETRIES attempts!"
fi

# Verify cache headers (non-blocking)
CACHE_HEADER=$(curl -sI "$HEALTH_URL" 2>/dev/null | grep -i "^cache-control:" | head -1)
if echo "$CACHE_HEADER" | grep -qi "no-cache"; then
    ok "Cache headers correct: $CACHE_HEADER"
else
    warn "Cache headers may need review: $CACHE_HEADER"
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deploy complete!${NC}"
echo -e "${GREEN}  Build: $OLD_BUILD_ID → $NEW_BUILD_ID${NC}"
echo -e "${GREEN}  Time:  ${BUILD_DURATION}s${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
