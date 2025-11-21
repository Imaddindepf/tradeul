# 🔧 Guía de Recuperación del Sistema Tradeul

## 🚨 Problema: Frontend con precios congelados

### Síntomas:
- Precios no se actualizan en el frontend
- WebSocket recibe mensajes "error"
- Scanner muestra pocos o 0 tickers

### Causa Raíz:
Redis perdió metadata porque:
1. Sincronización en memoria sin BGSAVE inmediato
2. Reinicio de servicios antes de que Redis persista
3. Consumer groups de streams perdidos

---

## ✅ Solución Rápida (5 minutos):

### Paso 1: Sincronizar metadata a Redis
```bash
cd /opt/tradeul
docker exec tradeul_data_maintenance python scripts/sync_redis_safe.py
```

### Paso 2: Reiniciar servicios en orden
```bash
# Primero scanner y data_ingest
docker restart tradeul_scanner tradeul_data_ingest

# Esperar 15 segundos
sleep 15

# Iniciar los servicios
curl -X POST http://localhost:8005/api/scanner/start
curl -X POST http://localhost:8003/api/ingest/start

# Esperar 10 segundos
sleep 10

# Reiniciar websocket al final
docker restart tradeul_websocket_server
```

### Paso 3: Verificar que funciona
```bash
# Debe mostrar ~100 tickers
curl -s http://localhost:8005/api/categories/gappers_up | grep -o '"count":[0-9]*'

# Debe mostrar 12K+ metadata
docker exec tradeul_redis redis-cli KEYS "metadata:ticker:*" | wc -l
```

---

## 🛡️ Prevención: Evitar el problema

### 1. NO reiniciar todos los servicios juntos
```bash
# ❌ MAL (causa pérdida de datos):
docker compose restart

# ✅ BIEN (reiniciar uno a la vez):
docker restart tradeul_analytics
sleep 5
docker restart tradeul_scanner
sleep 5
docker restart tradeul_websocket_server
```

### 2. Después de sincronizar metadata, SIEMPRE forzar save
```python
await redis.set(key, data, ttl=604800)
# ... después de sincronizar todo:
await redis.client.bgsave()  # CRÍTICO
await asyncio.sleep(2)  # Esperar que inicie
```

### 3. Usar el script seguro
```bash
# En lugar de scripts manuales, usar:
docker exec tradeul_data_maintenance python scripts/sync_redis_safe.py
```

### 4. Aumentar frecuencia de saves de Redis

Editar `docker-compose.yml`:
```yaml
redis:
  command: redis-server --appendonly yes --maxmemory 4gb --maxmemory-policy allkeys-lru --save 300 10 --save 60 1000
  #                                                                              ^^^^^^^^^^  ^^^^^^^^^^^
  #                                                                              5 min/10ch  1min/1000ch
```

### 5. TTL más largos para datos críticos
```python
# Metadata: 7 días (ya aplicado)
await redis.set(key, data, ttl=604800)

# ATR: 7 días también
await redis.set(atr_key, atr_data, ttl=604800)
```

---

## 📊 Verificación de Salud

### Comando para verificar que todo está bien:
```bash
#!/bin/bash
# check_health.sh

echo "🔍 Verificando salud del sistema..."
echo ""

# 1. Redis
REDIS_KEYS=$(docker exec tradeul_redis redis-cli DBSIZE | grep -o '[0-9]*')
METADATA_KEYS=$(docker exec tradeul_redis redis-cli KEYS "metadata:ticker:*" | wc -l)
echo "Redis:"
echo "  Total keys: $REDIS_KEYS"
echo "  Metadata keys: $METADATA_KEYS"
echo ""

# 2. Scanner
FILTERED=$(curl -s http://localhost:8005/api/categories/gappers_up | grep -o '"count":[0-9]*' | cut -d: -f2)
echo "Scanner:"
echo "  Gappers Up: $FILTERED tickers"
echo ""

# 3. WebSocket
WS_ERRORS=$(docker logs tradeul_websocket_server --tail 50 2>&1 | grep -c "NOGROUP")
echo "WebSocket:"
echo "  Errores NOGROUP: $WS_ERRORS"
echo ""

# Evaluación
if [ "$METADATA_KEYS" -gt 10000 ] && [ "$FILTERED" -gt 50 ] && [ "$WS_ERRORS" -eq 0 ]; then
    echo "✅ Sistema funcionando correctamente"
else
    echo "⚠️  Sistema necesita recuperación"
    echo "Ejecutar: docker exec tradeul_data_maintenance python scripts/sync_redis_safe.py"
fi

