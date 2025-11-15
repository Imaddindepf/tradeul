#!/bin/bash
# Script para monitorear CONTINUAMENTE todos los tickers con 404
# Captura en tiempo real y los va agregando al CSV

OUTPUT_FILE="tickers_404_continuous_$(date +%Y%m%d_%H%M%S).csv"
TEMP_FILE="/tmp/404_tickers_seen.txt"

echo "🔍 Monitoreando tickers con 404 EN TIEMPO REAL..."
echo "Archivo: $OUTPUT_FILE"
echo "Presiona Ctrl+C para detener"
echo ""

# Crear CSV con headers
echo "timestamp,symbol,in_universe,has_volume_slots,exists_in_polygon,polygon_name,classification" > "$OUTPUT_FILE"

# Crear archivo temporal para tracking
touch "$TEMP_FILE"

# Contador
TOTAL=0

# Función para procesar un ticker
process_ticker() {
    local ticker=$1
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Verificar si ya lo procesamos
    if grep -q "^${ticker}$" "$TEMP_FILE" 2>/dev/null; then
        return
    fi
    
    echo "[$(date '+%H:%M:%S')] Nuevo ticker con 404: $ticker"
    
    # Marcar como visto
    echo "$ticker" >> "$TEMP_FILE"
    TOTAL=$((TOTAL+1))
    
    # Verificar en BD
    IN_UNIVERSE=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -t -c "SELECT EXISTS(SELECT 1 FROM ticker_universe WHERE symbol='$ticker');" 2>/dev/null | tr -d ' \n')
    
    HAS_SLOTS=$(docker exec tradeul_timescale psql -U tradeul_user -d tradeul -t -c "SELECT COUNT(*) > 0 FROM volume_slots WHERE symbol='$ticker';" 2>/dev/null | tr -d ' \n')
    
    # Verificar en Polygon (con timeout)
    POLYGON_DATA=$(timeout 5 curl -s "https://api.polygon.io/v3/reference/tickers/$ticker?apiKey=vjzI76TMiepqrMZKphpfs3SA54JFkhEx" 2>/dev/null)
    
    EXISTS_POLYGON="false"
    POLYGON_NAME="N/A"
    CLASSIFICATION="UNKNOWN"
    
    if echo "$POLYGON_DATA" | grep -q '"status":"OK"'; then
        EXISTS_POLYGON="true"
        POLYGON_NAME=$(echo "$POLYGON_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('results',{}).get('name','N/A')[:50])" 2>/dev/null || echo "N/A")
        
        if [ "$IN_UNIVERSE" = "f" ]; then
            CLASSIFICATION="NUEVO_O_FALTANTE"
        else
            CLASSIFICATION="EN_UNIVERSO_SIN_DATOS"
        fi
    else
        CLASSIFICATION="FANTASMA"
    fi
    
    # Limpiar nombre
    POLYGON_NAME=$(echo "$POLYGON_NAME" | sed 's/,/-/g' | sed 's/"//g')
    
    # Guardar en CSV
    echo "$timestamp,$ticker,$IN_UNIVERSE,$HAS_SLOTS,$EXISTS_POLYGON,\"$POLYGON_NAME\",$CLASSIFICATION" >> "$OUTPUT_FILE"
    
    echo "  → $CLASSIFICATION ($POLYGON_NAME)"
}

# Monitorear logs continuamente
echo "Iniciando monitoreo (siguiendo logs en tiempo real)..."
echo ""

docker logs -f tradeul_analytics 2>&1 | while read line; do
    # Buscar 404 Not Found
    if echo "$line" | grep -q "404 Not Found"; then
        # Extraer símbolo
        TICKER=$(echo "$line" | grep -o "symbol=[A-Z]*" | cut -d= -f2)
        
        if [ -n "$TICKER" ]; then
            process_ticker "$TICKER"
        fi
    fi
done

echo ""
echo "========================================="
echo "MONITOREO FINALIZADO"
echo "========================================="
echo "Total tickers únicos encontrados: $TOTAL"
echo "Archivo: $OUTPUT_FILE"
echo ""
echo "Ver resultados:"
echo "  cat $OUTPUT_FILE | column -t -s,"


