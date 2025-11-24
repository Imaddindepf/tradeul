#!/bin/bash
# =====================================================
# Commit Changes - Ejecutar SOLO después de probar
# =====================================================

echo "⚠️  ¿Probaste el buscador y funciona correctamente?"
echo ""
read -p "¿Hacer commit? (s/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "❌ Commit cancelado"
    exit 0
fi

cd /opt/tradeul

echo "📝 Staging archivos..."
git add frontend/components/common/TickerSearch.tsx
git add frontend/components/sec-filings/SECFilingsContent.tsx
git add services/ticker-metadata-service/api/metadata_router.py
git add services/api_gateway/main.py
git add QUICK_START_TICKER_SEARCH.sh
git add TICKER_SEARCH_SETUP.md
git add docs/TICKER_SEARCH_OPTIMIZATION.md
git add scripts/add_ticker_search_indexes.sql
git add scripts/setup_ticker_search.sh
git add frontend/__tests__/TickerSearch.test.tsx

echo ""
echo "📋 Archivos staged:"
git status --short

echo ""
echo "💾 Haciendo commit..."
git commit -m "feat: optimizar búsqueda de tickers con índices PostgreSQL + API Gateway proxy

- Frontend: Mejorado TickerSearch con debouncing, request cancellation, estados visuales
  * Ahora usa API Gateway (puerto 8000) en vez de servicio directo (evita firewall issues)
  * SECFilingsContent: Solo busca al seleccionar ticker o presionar Enter (no mientras escribes)
- Backend: Query optimizado con priorización inteligente y métricas de performance
- API Gateway: Agregado endpoint proxy /api/v1/metadata/search para centralizar acceso
- Database: Índices B-tree, GIN y pg_trgm para búsquedas ultrarrápidas (<30ms)
- Docs: Guía completa de optimización y scripts de setup
- Performance: 3x más rápido que antes (target <50ms superado)

UX Improvements:
- Búsqueda de tickers: Muestra sugerencias pero NO busca hasta seleccionar
- Enter o clic en Search también dispara búsqueda
- Clear limpia input y resultados

Arquitectura:
Frontend → API Gateway (:8000) → ticker_metadata (:8010 interno)

Tests desde IP pública (157.180.45.153:8000):
- Búsqueda exacta (AAPL): 30.3ms ✅
- Búsqueda prefijo (AA): 26.5ms ✅
- Company name (Apple): 19.9ms ✅"

echo ""
echo "✅ Commit realizado!"
echo ""
echo "🚀 Para hacer push:"
echo "   git push origin main"

