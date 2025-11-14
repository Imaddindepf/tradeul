#!/bin/bash
# Script para exportar tickers con 404 a CSV

echo "🔍 Analizando tickers con 404..."
echo ""

OUTPUT_FILE="tickers_404_$(date +%Y%m%d_%H%M%S).csv"

# Extraer tickers únicos de los logs
TICKERS=$(docker logs tradeul_analytics --tail 2000 2>&1 | grep "404 Not Found" | grep -o "symbol=[A-Z]*" | cut -d= -f2 | sort | uniq)

if [ -z "$TICKERS" ]; then
    echo "❌ No se encontraron tickers con 404 en los logs"
    exit 1
fi

TOTAL=$(echo "$TICKERS" | wc -l | tr -d ' ')
echo "Encontrados $TOTAL tickers únicos con 404"
echo ""

# Crear CSV
echo "symbol,in_universe,has_volume_slots,exists_in_polygon,polygon_name,classification" > "$OUTPUT_FILE"

i=0
for ticker in $TICKERS; do
    i=$((i+1))
    echo "Procesando $ticker ($i/$TOTAL)..."
    
    # Verificar en BD
    IN_UNIVERSE=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -t -c "SELECT EXISTS(SELECT 1 FROM ticker_universe WHERE symbol='$ticker');" | tr -d ' \n')
    
    HAS_SLOTS=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -t -c "SELECT COUNT(*) > 0 FROM volume_slots WHERE symbol='$ticker';" | tr -d ' \n')
    
    # Verificar en Polygon (con rate limiting)
    POLYGON_DATA=$(curl -s "https://api.polygon.io/v3/reference/tickers/$ticker?apiKey=vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
    
    EXISTS_POLYGON="false"
    POLYGON_NAME="N/A"
    CLASSIFICATION="UNKNOWN"
    
    if echo "$POLYGON_DATA" | grep -q '"status":"OK"'; then
        EXISTS_POLYGON="true"
        POLYGON_NAME=$(echo "$POLYGON_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('results',{}).get('name','N/A'))" 2>/dev/null || echo "N/A")
        
        if [ "$IN_UNIVERSE" = "f" ]; then
            CLASSIFICATION="NUEVO_O_FALTANTE"
        else
            CLASSIFICATION="EN_UNIVERSO_SIN_DATOS"
        fi
    else
        CLASSIFICATION="FANTASMA"
    fi
    
    # Limpiar nombre para CSV
    POLYGON_NAME=$(echo "$POLYGON_NAME" | sed 's/,/-/g' | sed 's/"/-/g')
    
    # Guardar en CSV
    echo "$ticker,$IN_UNIVERSE,$HAS_SLOTS,$EXISTS_POLYGON,\"$POLYGON_NAME\",$CLASSIFICATION" >> "$OUTPUT_FILE"
    
    # Rate limiting (5 req/seg)
    sleep 0.21
done

echo ""
echo "=" >&2
echo "RESUMEN" >&2
echo "========================================" >&2
echo "Total tickers: $TOTAL" >&2
echo "" >&2
grep "FANTASMA" "$OUTPUT_FILE" | wc -l | xargs echo "Fantasma:" >&2
grep "NUEVO_O_FALTANTE" "$OUTPUT_FILE" | wc -l | xargs echo "Nuevos/Faltantes:" >&2
grep "EN_UNIVERSO_SIN_DATOS" "$OUTPUT_FILE" | wc -l | xargs echo "En universo sin datos:" >&2
echo "" >&2
echo "✅ Archivo guardado: $OUTPUT_FILE" >&2
echo "" >&2
echo "Ver archivo:" >&2
echo "  cat $OUTPUT_FILE" >&2
echo "  open $OUTPUT_FILE" >&2

