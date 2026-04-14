# Data Maintenance Service

Servicio dedicado al mantenimiento automático de datos históricos.

## 🎯 Responsabilidades

1. **OHLC Diario**: Cargar últimos 30 días de OHLC para cálculo de ATR
2. **Volume Slots**: Cargar slots de 5 minutos para cálculo de RVOL
3. **Metadata**: Enriquecer market cap, float, sector, industry
4. **Redis Sync**: Sincronizar caches de Redis con TimescaleDB

## ⏰ Ejecución

- **Automática**: Todos los días a las 17:00 ET (1 hora después del cierre)
- **Manual**: `POST /trigger` para ejecutar inmediatamente

## 🛡️ Tolerancia a Fallos

El servicio rastrea el estado de cada tarea en Redis:

```json
{
  "date": "2025-11-11",
  "started_at": "2025-11-11T17:00:00Z",
  "tasks": {
    "ohlc_daily": "completed",
    "volume_slots": "completed",
    "metadata_enrich": "in_progress",  // ← Si se cae aquí
    "redis_sync": "pending"
  }
}
```

**Al reiniciar**: Reanuda desde la última tarea completada.

##  Endpoints

- `GET /health` - Health check
- `GET /status` - Estado detallado del último mantenimiento
- `POST /trigger` - Ejecutar mantenimiento manual (testing)

## 🚀 Uso

### Docker Compose

```bash
# Iniciar servicio
docker compose up -d data_maintenance

# Ver logs
docker logs -f tradeul_data_maintenance

# Ver estado
curl http://localhost:8008/status
```

### Manual

```bash
cd services/data_maintenance
pip install -r requirements.txt
python main.py
```

## 🔧 Configuración

Variables de entorno:

- `TIMEZONE`: Zona horaria (default: `America/New_York`)
- `MAINTENANCE_SCHEDULE`: Horario de ejecución (default: `MARKET_CLOSE`)
- `REDIS_HOST`: Host de Redis
- `TIMESCALE_HOST`: Host de TimescaleDB
- `POLYGON_API_KEY`: API key de Polygon

## 📝 Logs

```json
{
  "event": "maintenance_cycle_finished",
  "date": "2025-11-11",
  "duration_seconds": 1114.5,
  "duration_human": "18.6m",
  "completed": 4,
  "failed": 0,
  "total": 4,
  "success": true
}
```

## 🔄 Tareas

### 1. LoadOHLCTask
- Carga OHLC diario de Polygon
- Actualiza `market_data_daily`
- ~5-10 minutos

### 2. LoadVolumeSlotsTask
- Carga agregados de 1 minuto
- Convierte a slots de 5 minutos
- Actualiza `volume_slots`
- ~3-5 minutos

### 3. EnrichMetadataTask
- Obtiene market cap, float, sector de Polygon
- Actualiza `ticker_metadata`
- ~10-15 minutos (rate limiting)

### 4. SyncRedisTask
- Sincroniza caches de Redis
- Actualiza promedios de volumen
- Limpia caches obsoletos
- ~1-2 minutos

## 🧹 Mantenimiento

### Limpiar estado antiguo

```bash
# Eliminar estados de más de 7 días
redis-cli KEYS "maintenance:status:*" | xargs redis-cli DEL
```

### Verificar última ejecución

```bash
redis-cli GET maintenance:last_run
# Output: 2025-11-11
```

## 🐛 Troubleshooting

### Servicio no ejecuta mantenimiento

1. Verificar logs: `docker logs tradeul_data_maintenance`
2. Verificar zona horaria: debe ser `America/New_York`
3. Verificar que sea día de semana (lunes-viernes)

### Tareas fallan

1. Verificar conexión a Redis/TimescaleDB
2. Verificar API key de Polygon
3. Revisar estado en Redis: `redis-cli GET maintenance:status:{date}`

### Rate limiting de Polygon

El servicio tiene rate limiting integrado:
- OHLC: max 10 requests concurrentes
- Volume Slots: max 10 requests concurrentes
- Metadata: max 5 requests concurrentes + 200ms delay

Si aún así falla, reducir `Semaphore` en cada tarea.
