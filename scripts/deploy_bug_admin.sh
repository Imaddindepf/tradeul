#!/usr/bin/env bash
# Deploy script for the Bug Reports Admin feature.
# - Type-checks the frontend
# - Builds the Next.js bundle
# - Restarts the frontend systemd service
# - Rebuilds + recreates the api_gateway docker container
# - Runs smoke tests against the new endpoints
#
# Usage: sudo /opt/tradeul/scripts/deploy_bug_admin.sh

set -eo pipefail

ROOT="/opt/tradeul"
FRONTEND="$ROOT/frontend"

echo "=============================="
echo " STEP 1: TypeScript check"
echo "=============================="
cd "$FRONTEND"
ERRS=$(npx tsc --noEmit 2>&1 | grep -E "dashboard-toolbar|useIsAdmin|workspace/page|window-config" || true)
if [ -n "$ERRS" ]; then
  echo "TypeScript errors in modified files:"
  echo "$ERRS"
  exit 1
fi
echo "TypeScript: OK (no errors in modified files)"

echo
echo "=============================="
echo " STEP 2: Next.js production build"
echo "=============================="
npm run build 2>&1 | tail -20
BUILD_RC=${PIPESTATUS[0]}
if [ "$BUILD_RC" != "0" ]; then
  echo "Frontend build failed (exit $BUILD_RC)"
  exit 1
fi
echo "Build: OK"

echo
echo "=============================="
echo " STEP 3: Restart frontend service"
echo "=============================="
systemctl restart tradeul-frontend.service
sleep 2
systemctl status tradeul-frontend.service --no-pager | head -10

echo
echo "=============================="
echo " STEP 4: Rebuild + recreate api_gateway"
echo "=============================="
cd "$ROOT"
docker compose build api_gateway 2>&1 | tail -15
docker compose up -d --force-recreate api_gateway 2>&1 | tail -5
sleep 5
docker compose ps api_gateway

echo
echo "=== api_gateway recent logs ==="
docker compose logs --tail=30 api_gateway 2>&1 | tail -30

echo
echo "=============================="
echo " STEP 5: Smoke tests"
echo "=============================="

CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/admin/bug-reports)
echo "no-auth GET /api/v1/admin/bug-reports -> $CODE (expected 401)"

CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d '{"description":"smoke test from deploy script","images":[],"context":{"url":"http://localhost"}}' \
  http://localhost:8000/api/v1/bug-reports)
echo "anon POST  /api/v1/bug-reports         -> $CODE (expected 201)"

echo
echo "Deploy complete."
