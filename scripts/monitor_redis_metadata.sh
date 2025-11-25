#!/bin/bash
# Monitoreo continuo de metadata en Redis

echo "🔍 Monitoreando metadata en Redis (Ctrl+C para detener)..."
echo "Timestamp,Metadata_Count,Total_Keys,Uptime_Seconds" > /tmp/redis_metadata_monitor.csv

while true; do
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    METADATA_COUNT=$(docker exec tradeul_redis redis-cli --scan --pattern "metadata:ticker:*" | wc -l)
    TOTAL_KEYS=$(docker exec tradeul_redis redis-cli DBSIZE | grep -o '[0-9]*')
    UPTIME=$(docker exec tradeul_redis redis-cli INFO server | grep uptime_in_seconds | cut -d: -f2 | tr -d '\r')
    
    echo "$TIMESTAMP,$METADATA_COUNT,$TOTAL_KEYS,$UPTIME" | tee -a /tmp/redis_metadata_monitor.csv
    
    # Alertar si caen los metadata
    if [ "$METADATA_COUNT" -lt 10000 ]; then
        echo "🚨 ALERTA: Metadata count bajo ($METADATA_COUNT)" | tee -a /tmp/redis_metadata_alerts.log
        
        # Capturar estadísticas para debugging
        docker exec tradeul_redis redis-cli INFO commandstats | grep -E "flushall|flushdb|del" >> /tmp/redis_metadata_alerts.log
    fi
    
    sleep 30
done


