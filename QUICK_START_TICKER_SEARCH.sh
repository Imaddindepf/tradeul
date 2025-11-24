#!/bin/bash
# =====================================================
# QUICK START: Fix Ticker Search (1 comando)
# =====================================================

echo "🚀 Arreglando búsqueda de tickers..."
echo ""

# Ejecutar setup
cd /opt/tradeul && ./scripts/setup_ticker_search.sh

# Resultado
echo ""
echo "✅ COMPLETADO!"
echo ""
echo "🌐 Abre en tu browser: http://localhost:3000/sec-filings"
echo "⌨️  Escribe 'AA' o 'Apple' en el buscador"
echo "⚡ Deberías ver sugerencias en < 200ms"
echo ""
echo "📖 Documentación: cat TICKER_SEARCH_SETUP.md"

