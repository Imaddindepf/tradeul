#!/bin/bash

echo "🔄 ACTUALIZANDO TODOS LOS DATOS HISTÓRICOS"
echo "=========================================="
echo ""

echo "1️⃣ Ejecutando warmup de Polygon (todos los tickers):"
curl -X POST "http://localhost:8004/api/warmup/premarket?calculate_avg_volume=true&max_concurrent=80"
echo ""
echo ""

echo "⏳ Este proceso tomará ~5-8 minutos..."
echo "   Monitorea el progreso con:"
echo "   docker logs tradeul_historical --follow | grep -i 'progress\|warmup\|loaded'"
echo ""

echo "✅ Una vez completado, verifica con:"
echo "   python3 scripts/verify_historical_data.py"
echo ""

