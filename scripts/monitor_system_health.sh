#!/bin/bash
# Monitor continuo del sistema Tradeul
# Captura: Redis, Scanner, WebSocket, Analytics
# Detecta: Pérdida de metadata, streams vacíos, errores

DURATION_HOURS=${1:-24}
DURATION_SECONDS=$((DURATION_HOURS * 3600))
LOG_FILE="/tmp/tradeul_health_monitor_$(date +%Y%m%d_%H%M%S).log"
CSV_FILE="/tmp/tradeul_health_monitor_$(date +%Y%m%d_%H%M%S).csv"

echo "🔍 Monitoreando sistema Tradeul por $DURATION_HOURS horas..."
echo "📝 Log: $LOG_FILE"
echo "📊 CSV: $CSV_FILE"
echo ""
echo "Presiona Ctrl+C para detener antes"
echo ""

# CSV Header
echo "Timestamp,Metadata_Keys,Total_Keys,Redis_Memory_MB,Scanner_Filtered,Snapshot_Enriched_Count,WS_Broadcasting,Redis_Uptime,Evicted_Keys,Expired_Keys,FLUSHALL_Calls,FLUSHDB_Calls,DEL_Calls" > "$CSV_FILE"

START_TIME=$(date +%s)
ITERATION=0

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    
    if [ $ELAPSED -ge $DURATION_SECONDS ]; then
        echo "✅ Monitoreo completado ($DURATION_HOURS horas)"
        break
    fi
    
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    ITERATION=$((ITERATION + 1))
    
    # ============================================================================
    # REDIS METRICS
    # ============================================================================
    
    METADATA_KEYS=$(docker exec tradeul_redis redis-cli --scan --pattern "metadata:ticker:*" 2>/dev/null | wc -l | tr -d ' ')
    TOTAL_KEYS=$(docker exec tradeul_redis redis-cli DBSIZE 2>/dev/null | grep -o '[0-9]*' | tr -d ' ')
    
    REDIS_MEMORY=$(docker exec tradeul_redis redis-cli INFO memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | sed 's/M//' | tr -d '\r')
    REDIS_UPTIME=$(docker exec tradeul_redis redis-cli INFO server 2>/dev/null | grep uptime_in_seconds | cut -d: -f2 | tr -d '\r')
    
    EVICTED=$(docker exec tradeul_redis redis-cli INFO stats 2>/dev/null | grep "evicted_keys:" | cut -d: -f2 | tr -d '\r')
    EXPIRED=$(docker exec tradeul_redis redis-cli INFO stats 2>/dev/null | grep "expired_keys:" | cut -d: -f2 | tr -d '\r')
    
    FLUSHALL=$(docker exec tradeul_redis redis-cli INFO commandstats 2>/dev/null | grep "cmdstat_flushall:calls=" | grep -o 'calls=[0-9]*' | cut -d= -f2 | tr -d ' \n' || echo "0")
    FLUSHDB=$(docker exec tradeul_redis redis-cli INFO commandstats 2>/dev/null | grep "cmdstat_flushdb:calls=" | grep -o 'calls=[0-9]*' | cut -d= -f2 | tr -d ' \n' || echo "0")
    DEL_CALLS=$(docker exec tradeul_redis redis-cli INFO commandstats 2>/dev/null | grep "cmdstat_del:calls=" | grep -o 'calls=[0-9]*' | cut -d= -f2 | tr -d ' \n' || echo "0")
    
    # ============================================================================
    # SCANNER METRICS
    # ============================================================================
    
    SCANNER_FILTERED=$(docker logs tradeul_scanner --tail 20 2>&1 | grep "filtered_count" | tail -1 | grep -o '"filtered_count": [0-9]*' | cut -d: -f2 | tr -d ' ' || echo "0")
    
    # ============================================================================
    # ANALYTICS METRICS
    # ============================================================================
    
    SNAPSHOT_COUNT=$(docker exec tradeul_redis redis-cli GET "snapshot:enriched:latest" 2>/dev/null | jq -r '.count' 2>/dev/null || echo "0")
    
    # ============================================================================
    # WEBSOCKET METRICS
    # ============================================================================
    
    WS_BROADCASTING=$(docker logs tradeul_websocket_server --tail 20 2>&1 | grep -c "Broadcasting" || echo "0")
    
    # ============================================================================
    # CSV OUTPUT
    # ============================================================================
    
    echo "$TIMESTAMP,$METADATA_KEYS,$TOTAL_KEYS,$REDIS_MEMORY,$SCANNER_FILTERED,$SNAPSHOT_COUNT,$WS_BROADCASTING,$REDIS_UPTIME,$EVICTED,$EXPIRED,$FLUSHALL,$FLUSHDB,$DEL_CALLS" >> "$CSV_FILE"
    
    # ============================================================================
    # CONSOLE OUTPUT (cada 10 iteraciones)
    # ============================================================================
    
    if [ $((ITERATION % 10)) -eq 0 ]; then
        echo "[$TIMESTAMP] Metadata: $METADATA_KEYS | Redis: ${REDIS_MEMORY}MB | Scanner: $SCANNER_FILTERED filtered | WS: ${WS_BROADCASTING}x broadcasting"
    fi
    
    # ============================================================================
    # ALERTAS
    # ============================================================================
    
    # ALERTA: Metadata count bajo
    if [ "$METADATA_KEYS" -lt 10000 ]; then
        ALERT="🚨 ALERTA: Metadata bajo ($METADATA_KEYS)"
        echo "$TIMESTAMP - $ALERT" | tee -a "$LOG_FILE"
        
        # Capturar snapshot de comandos Redis
        echo "=== Redis CommandStats ===" >> "$LOG_FILE"
        docker exec tradeul_redis redis-cli INFO commandstats >> "$LOG_FILE"
        
        # Capturar SlowLog (últimos 100 comandos lentos)
        echo "=== Redis SlowLog (últimos comandos) ===" >> "$LOG_FILE"
        docker exec tradeul_redis redis-cli SLOWLOG GET 100 >> "$LOG_FILE"
        
        # Capturar persistencia
        echo "=== Redis Persistence Info ===" >> "$LOG_FILE"
        docker exec tradeul_redis redis-cli INFO persistence >> "$LOG_FILE"
        
        # Capturar últimos logs de servicios
        echo "=== data_maintenance logs ===" >> "$LOG_FILE"
        docker logs tradeul_data_maintenance --tail 50 >> "$LOG_FILE"
        
        echo "=== scanner logs ===" >> "$LOG_FILE"
        docker logs tradeul_scanner --tail 50 >> "$LOG_FILE"
        
        # Capturar estado de contenedores
        echo "=== Docker container status ===" >> "$LOG_FILE"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.State}}" >> "$LOG_FILE"
        
        # Trigger recovery automático
        echo "💾 Ejecutando recovery automático..." | tee -a "$LOG_FILE"
        docker exec tradeul_data_maintenance python scripts/sync_redis_safe.py >> "$LOG_FILE" 2>&1
    fi
    
    # ALERTA: Scanner no filtra nada
    if [ ! -z "$SCANNER_FILTERED" ] && [ "$SCANNER_FILTERED" -eq 0 ]; then
        if [ $((ITERATION % 20)) -eq 0 ]; then  # Solo cada 20 iteraciones (10 min)
            echo "$TIMESTAMP - ⚠️ Scanner filtering 0 tickers" >> "$LOG_FILE"
        fi
    fi
    
    # ALERTA: FLUSHALL detectado
    if [ ! -z "$FLUSHALL" ] && [ "$FLUSHALL" -gt 0 ]; then
        if [ ! -f "/tmp/flushall_detected_${FLUSHALL}.flag" ]; then
            ALERT="🔥 FLUSHALL DETECTADO: $FLUSHALL llamadas totales"
            echo "$TIMESTAMP - $ALERT" | tee -a "$LOG_FILE"
            touch "/tmp/flushall_detected_${FLUSHALL}.flag"
            
            # Capturar estado completo
            echo "=== Full Redis INFO ===" >> "$LOG_FILE"
            docker exec tradeul_redis redis-cli INFO >> "$LOG_FILE"
        fi
    fi
    
    # ALERTA: Metadata desaparecieron (delta significativo)
    if [ ! -z "$PREV_METADATA" ] && [ ! -z "$METADATA_KEYS" ]; then
        DELTA=$((PREV_METADATA - METADATA_KEYS))
        if [ $DELTA -gt 1000 ]; then
            ALERT="📉 PÉRDIDA DE METADATA: $PREV_METADATA → $METADATA_KEYS (delta: -$DELTA)"
            echo "$TIMESTAMP - $ALERT" | tee -a "$LOG_FILE"
            
            # Capturar logs inmediatamente
            echo "=== Scanner logs ===" >> "$LOG_FILE"
            docker logs tradeul_scanner --tail 100 >> "$LOG_FILE"
            
            echo "=== Analytics logs ===" >> "$LOG_FILE"
            docker logs tradeul_analytics --tail 100 >> "$LOG_FILE"
            
            echo "=== Redis persistence ===" >> "$LOG_FILE"
            docker exec tradeul_redis redis-cli INFO persistence >> "$LOG_FILE"
        fi
    fi
    
    PREV_METADATA=$METADATA_KEYS
    
    # Esperar 30 segundos
    sleep 30
done

echo ""
echo "✅ Monitoreo finalizado"
echo "📊 Resultados en: $CSV_FILE"
echo "📝 Alertas en: $LOG_FILE"
echo ""
echo "Análisis rápido:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
tail -20 "$CSV_FILE" | column -t -s,

