#!/bin/bash
# Script para repoblar Redis con metadatos de tickers
# Ejecutar: ./scripts/repopulate_redis.sh

set -e

echo "🚀 Repoblando Redis con metadatos de tickers..."

# Cargar variables de entorno
source /opt/tradeul/.env

# Obtener password de Redis
REDIS_PASS="${REDIS_PASSWORD}"

# Contador
count=0

# Leer tickers de TimescaleDB e insertar en Redis
echo "📥 Obteniendo tickers de TimescaleDB..."

docker exec -i tradeul_timescale psql -U tradeul_user -d tradeul -t -A -F'|' -c "
SELECT 
    symbol,
    COALESCE(company_name, ''),
    COALESCE(exchange, ''),
    COALESCE(sector, ''),
    COALESCE(industry, ''),
    COALESCE(market_cap::text, ''),
    COALESCE(float_shares::text, ''),
    COALESCE(shares_outstanding::text, ''),
    COALESCE(avg_volume_30d::text, ''),
    COALESCE(avg_volume_10d::text, ''),
    COALESCE(avg_price_30d::text, ''),
    COALESCE(beta::text, ''),
    COALESCE(is_etf::text, 'false'),
    COALESCE(is_actively_trading::text, 'true'),
    COALESCE(updated_at::text, NOW()::text)
FROM tickers_unified
WHERE is_active = true
ORDER BY symbol;
" | while IFS='|' read -r symbol company_name exchange sector industry market_cap float_shares shares_outstanding avg_volume_30d avg_volume_10d avg_price_30d beta is_etf is_actively_trading updated_at; do
    
    # Crear JSON manualmente
    json=$(cat <<EOF
{
  "symbol": "$symbol",
  "company_name": "$company_name",
  "exchange": "$exchange",
  "sector": "$sector",
  "industry": "$industry",
  "market_cap": ${market_cap:-null},
  "float_shares": ${float_shares:-null},
  "shares_outstanding": ${shares_outstanding:-null},
  "avg_volume_30d": ${avg_volume_30d:-null},
  "avg_volume_10d": ${avg_volume_10d:-null},
  "avg_price_30d": ${avg_price_30d:-null},
  "beta": ${beta:-null},
  "is_etf": $is_etf,
  "is_actively_trading": $is_actively_trading,
  "updated_at": "$updated_at"
}
EOF
)
    
    # Insertar en Redis con TTL de 24 horas (86400 segundos)
    echo "$json" | docker exec -i tradeul_redis redis-cli -a "$REDIS_PASS" --no-auth-warning -x SETEX "metadata:ticker:$symbol" 86400 > /dev/null
    
    count=$((count + 1))
    
    # Mostrar progreso cada 100 tickers
    if [ $((count % 100)) -eq 0 ]; then
        echo "  ⏳ Procesados $count tickers..."
    fi
done

echo ""
echo "✅ ¡Completado! Se insertaron $count metadatos en Redis"
echo "⏰ TTL configurado: 86400 segundos (24 horas)"
echo ""
echo "🔍 Verificando algunos tickers de ejemplo:"

for ticker in AAPL TSLA MSFT NVDA; do
    ttl=$(docker exec -i tradeul_redis redis-cli -a "$REDIS_PASS" --no-auth-warning TTL "metadata:ticker:$ticker" 2>/dev/null)
    if [ "$ttl" != "-2" ]; then
        hours=$(echo "scale=1; $ttl / 3600" | bc)
        echo "  ✓ $ticker: OK (TTL: ${ttl}s / ${hours}h)"
    else
        echo "  ✗ $ticker: NO ENCONTRADO"
    fi
done

echo ""
echo "🏁 Script finalizado"


