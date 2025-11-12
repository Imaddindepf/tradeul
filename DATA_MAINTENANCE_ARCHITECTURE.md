# 🔧 Data Maintenance Architecture

## 📋 Resumen

El **Data Maintenance Service** es un servicio dedicado y autónomo que se encarga de todas las tareas de mantenimiento de datos históricos, ejecutándose automáticamente al cierre del mercado cada día.

---

## 🎯 Problema que Resuelve

**Antes**: La carga de datos estaba dispersa entre múltiples servicios:

- `Historical`: Warmup de metadata (market cap, float, sector)
- Scripts manuales: OHLC para ATR, volume slots para RVOL
- Sin automatización consistente
- Sin tolerancia a fallos
- Sin coordinación entre tareas

**Ahora**: Un solo servicio centralizado que:

- ✅ Ejecuta **automáticamente** al cierre del mercado
- ✅ **Tolerante a fallos**: Reanuda donde quedó si se reinicia
- ✅ **Coordinado**: Ejecuta tareas en orden lógico
- ✅ **Monitoreable**: Logs estructurados + endpoints de estado
- ✅ **Independiente**: No sobrecarga otros servicios

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                  DATA MAINTENANCE SERVICE                    │
│                   (Puerto 8008, Siempre activo)             │
└───────────────────────────┬─────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐ ┌──────────────┐ ┌───────────────┐
│ Maintenance     │ │     Task     │ │  Individual   │
│   Scheduler     │ │ Orchestrator │ │    Tasks      │
└─────────────────┘ └──────────────┘ └───────────────┘
         │                  │                  │
         │                  │         ┌────────┴────────┐
         │                  │         │                 │
         │                  │    ┌────▼────┐     ┌─────▼────┐
         │                  │    │ OHLC    │     │ Volume   │
         │                  │    │ Daily   │     │ Slots    │
         │                  │    └─────────┘     └──────────┘
         │                  │         │                 │
         │                  │    ┌────▼────┐     ┌─────▼────┐
         │                  │    │Metadata │     │  Redis   │
         │                  │    │ Enrich  │     │  Sync    │
         │                  │    └─────────┘     └──────────┘
         │                  │
         ▼                  ▼
┌──────────────────────────────────────────────────┐
│              MARKET SESSION MONITOR              │
│  - Detecta: MARKET_OPEN → POST_MARKET → CLOSED  │
│  - Trigger: 17:00 ET (1h después del cierre)    │
└──────────────────────────────────────────────────┘
```

---

## ⏰ Flujo de Ejecución

### **1. Monitoreo Continuo**

```
Scheduler ejecuta loop cada 60 segundos:
├─ Obtener hora actual en ET (America/New_York)
├─ Determinar sesión: PRE_MARKET | MARKET_OPEN | POST_MARKET | CLOSED
└─ Si es 17:00 ET y día de semana → Ejecutar mantenimiento
```

### **2. Ejecución de Mantenimiento**

```
17:00 ET - INICIO
│
├─ [1] Load OHLC Daily (5-10 min)
│   ├─ Obtener símbolos activos de ticker_universe
│   ├─ Cargar últimos 30 días de OHLC desde Polygon
│   ├─ Insertar/actualizar en market_data_daily
│   └─ ✅ Completado
│
├─ [2] Load Volume Slots (3-5 min)
│   ├─ Cargar últimos 10 días de agregados 1-min desde Polygon
│   ├─ Convertir a slots de 5 minutos
│   ├─ Insertar/actualizar en volume_slots
│   └─ ✅ Completado
│
├─ [3] Enrich Metadata (10-15 min)
│   ├─ Identificar símbolos sin metadata o desactualizados
│   ├─ Obtener market cap, float, sector, industry desde Polygon
│   ├─ Insertar/actualizar en ticker_metadata
│   └─ ✅ Completado
│
├─ [4] Sync Redis (1-2 min)
│   ├─ Sincronizar metadata a Redis (ticker:metadata:{symbol})
│   ├─ Calcular y actualizar promedios de volumen
│   ├─ Limpiar caches obsoletos
│   └─ ✅ Completado
│
└─ 17:30 ET - FINALIZADO
    ├─ Guardar estado en Redis: maintenance:last_run = 2025-11-11
    ├─ Log con estadísticas completas
    └─ Esperar al próximo día
```

### **3. Tolerancia a Fallos**

```
Redis Tracking:
maintenance:status:2025-11-11 = {
  "date": "2025-11-11",
  "started_at": "2025-11-11T17:00:00Z",
  "tasks": {
    "ohlc_daily": "completed",
    "volume_slots": "completed",
    "metadata_enrich": "in_progress",  ← Se cayó aquí
    "redis_sync": "pending"
  }
}

Al reiniciar:
1. Leer estado desde Redis
2. Identificar última tarea completada
3. Reanudar desde "metadata_enrich"
4. NO repetir "ohlc_daily" ni "volume_slots"
```

---

## 📊 Tareas en Detalle

### **1. LoadOHLCTask**

**Propósito**: Cargar OHLC diario para cálculo de ATR (Average True Range)

**Fuente**: Polygon API `v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}`

**Destino**: TimescaleDB `market_data_daily` (hypertable)

**Datos**:

- `date`, `symbol`
- `open`, `high`, `low`, `close`
- `volume`, `vwap`, `trades_count`

**Ventana**: Últimos 30 días (para ATR-14)

**Tasa de requests**: Max 10 concurrentes (Polygon rate limit)

---

### **2. LoadVolumeSlotsTask**

**Propósito**: Cargar volume slots de 5 minutos para cálculo de RVOL (Relative Volume)

**Fuente**: Polygon API `v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}`

**Proceso**:

1. Obtener agregados de 1 minuto
2. Agrupar en slots de 5 minutos
3. Calcular slot_index (0-191 para extended hours)

**Destino**: TimescaleDB `volume_slots` (hypertable)

**Datos**:

- `date`, `symbol`, `slot_index`
- `volume` (acumulado para el slot)

**Ventana**: Últimos 10 días

**Tasa de requests**: Max 10 concurrentes

---

### **3. EnrichMetadataTask**

**Propósito**: Enriquecer metadata financiera de tickers

**Fuente**: Polygon API `v3/reference/tickers/{symbol}`

**Destino**: TimescaleDB `ticker_metadata`

**Datos**:

- `market_cap`: Capitalización de mercado
- `float_shares`: Float (acciones disponibles)
- `shares_outstanding`: Acciones totales
- `sector`: Sector económico (e.g., Technology)
- `industry`: Industria específica (e.g., Software)
- `description`: Descripción de la empresa

**Criterios de prioridad**:

1. Tickers sin `market_cap`
2. Tickers sin `sector`
3. Metadata actualizada hace > 7 días

**Límite**: 500 símbolos por ejecución (prioriza más importantes)

**Tasa de requests**: Max 5 concurrentes + 200ms delay (rate limit estricto)

---

### **4. SyncRedisTask**

**Propósito**: Sincronizar caches de Redis con datos actualizados de TimescaleDB

**Operaciones**:

1. **Sincronizar Metadata**:

   ```
   ticker:metadata:{symbol} = {
     "market_cap": 50000000000,
     "float_shares": 100000000,
     "sector": "Technology",
     ...
   }
   TTL: 24 horas
   ```

2. **Sincronizar Promedios de Volumen**:

   ```
   ticker:avg_volume:{symbol} = {
     "avg_volume_30d": 5000000,
     "avg_volume_10d": 6000000,
     "avg_volume_5d": 7000000
   }
   TTL: 24 horas
   ```

3. **Limpiar Caches Obsoletos**:
   - Eliminar metadata de tickers inactivos
   - Eliminar keys huérfanos

**Beneficio**: Lecturas ultrarrápidas en runtime (Redis vs PostgreSQL)

---

## 🔗 Integración con Otros Servicios

### **Historical Service**

- **ANTES**: Ejecutaba warmup automático de metadata al cierre
- **AHORA**: Solo SIRVE datos a través de endpoints (read-only)
- **Cambio**: Warmup automático desactivado, delegado a `data_maintenance`

```python
# Historical solo sirve datos:
GET /api/metadata/{symbol}        # Lee de Redis/TimescaleDB
GET /api/metadata/bulk?symbols=...  # Batch read
POST /api/warmup                   # Manual trigger (testing only)
```

### **Analytics Service**

- **No cambia**: Ya usa datos de TimescaleDB sin cargarlos
- **Beneficio**: Datos siempre actualizados para cálculos de RVOL, ATR

### **Scanner Service**

- **No cambia**: Lee metadata desde Historical endpoints
- **Beneficio**: Metadata actualizada para filtros (market cap, sector)

---

## 🛡️ Tolerancia a Fallos

### **Escenarios Cubiertos**

1. **Servicio se cae durante ejecución**:

   - Estado guardado en Redis después de cada tarea
   - Al reiniciar: Lee estado, continúa desde última tarea pendiente

2. **Tarea individual falla**:

   - Marca como `failed`, continúa con las demás
   - Log detallado del error
   - Reporte final indica éxito parcial

3. **Rate limiting de Polygon**:

   - Semaphores para limitar concurrencia
   - Delays configurables entre requests
   - Retry automático si falla (max 3 intentos)

4. **Conexión a BD se pierde**:

   - Excepciones capturadas
   - Log estructurado
   - Tarea marcada como `failed`
   - Resto de tareas continúa

5. **Servicio se reinicia antes de ejecutar**:
   - Al arrancar, NO ejecuta nada inmediatamente
   - Espera hasta las 17:00 ET del día siguiente
   - Si detecta que falta mantenimiento de ayer → ejecuta inmediatamente

---

## 📊 Monitoreo

### **Logs Estructurados**

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

{
  "event": "task_completed",
  "task": "ohlc_daily",
  "duration_seconds": 340,
  "symbols_processed": 8543,
  "records_inserted": 256290
}
```

### **Health Endpoints**

```bash
# Health check (Docker healthcheck)
curl http://localhost:8008/health
{
  "status": "healthy",
  "service": "data_maintenance",
  "redis": "connected",
  "timescaledb": "connected",
  "last_maintenance": "2025-11-11",
  "scheduler_running": true
}

# Estado detallado
curl http://localhost:8008/status
{
  "status": "ok",
  "last_maintenance": "2025-11-11",
  "details": {
    "date": "2025-11-11",
    "started_at": "2025-11-11T17:00:00Z",
    "completed_at": "2025-11-11T17:18:34Z",
    "duration_seconds": 1114.5,
    "all_success": true,
    "tasks": {
      "ohlc_daily": "completed",
      "volume_slots": "completed",
      "metadata_enrich": "completed",
      "redis_sync": "completed"
    }
  }
}

# Trigger manual (testing)
curl -X POST http://localhost:8008/trigger
{
  "status": "triggered",
  "message": "Maintenance cycle started"
}
```

### **Redis Keys**

```bash
# Última ejecución
redis-cli GET maintenance:last_run
# Output: "2025-11-11"

# Estado detallado
redis-cli GET maintenance:status:2025-11-11
# Output: JSON con estado completo

# Listar todos los estados históricos
redis-cli KEYS "maintenance:status:*"
```

---

## 🚀 Deployment

### **Iniciar Servicio**

```bash
# Build + start
docker compose up -d data_maintenance

# Ver logs
docker logs -f tradeul_data_maintenance

# O usar script helper
./start-data-maintenance.sh
```

### **Verificar Estado**

```bash
# Health check
curl http://localhost:8008/health | jq

# Estado detallado
curl http://localhost:8008/status | jq

# Logs en tiempo real
docker logs -f tradeul_data_maintenance --tail 100
```

### **Testing Manual**

```bash
# Ejecutar mantenimiento inmediatamente (sin esperar al cierre)
curl -X POST http://localhost:8008/trigger

# Monitorear progreso
watch -n 2 'curl -s http://localhost:8008/status | jq'
```

---

## ⚙️ Configuración

### **Variables de Entorno**

```yaml
# docker-compose.yml
environment:
  - TIMEZONE=America/New_York # Zona horaria para scheduler
  - MAINTENANCE_SCHEDULE=MARKET_CLOSE # Horario de ejecución
  - REDIS_HOST=redis
  - TIMESCALE_HOST=timescale
  - POLYGON_API_KEY=${POLYGON_API_KEY}
```

### **Ajustar Horario**

Por defecto ejecuta a las **17:00 ET** (1 hora después del cierre). Para cambiar:

```python
# services/data_maintenance/maintenance_scheduler.py
self.maintenance_hour = 17  # Cambiar a hora deseada (ET)
self.maintenance_minute = 0
```

### **Ajustar Rate Limits**

Si Polygon limita requests, reducir concurrencia:

```python
# En cada task (load_ohlc.py, load_volume_slots.py, etc.)
semaphore = asyncio.Semaphore(5)  # Reducir de 10 a 5
```

---

## 🧹 Mantenimiento

### **Limpiar Estados Antiguos**

Redis acumula estados históricos (TTL 7 días). Para limpiar manualmente:

```bash
# Eliminar estados de más de 7 días
redis-cli KEYS "maintenance:status:*" | grep "2024-" | xargs redis-cli DEL

# O todo
redis-cli DEL $(redis-cli KEYS "maintenance:status:*")
```

### **Re-ejecutar Mantenimiento**

Si una tarea falló o necesitas actualizar datos:

```bash
# Trigger manual
curl -X POST http://localhost:8008/trigger

# Verificar progreso
curl http://localhost:8008/status | jq '.details.tasks'
```

### **Debugging**

```bash
# Ver logs completos
docker logs tradeul_data_maintenance --since 1h

# Ver solo errores
docker logs tradeul_data_maintenance 2>&1 | grep -i error

# Conectar a Redis para ver estado
docker exec -it tradeul_redis redis-cli
127.0.0.1:6379> GET maintenance:last_run
127.0.0.1:6379> GET maintenance:status:2025-11-11
```

---

## 📈 Beneficios

### **1. Centralización**

- ✅ Una sola responsabilidad: mantenimiento de datos
- ✅ Código limpio y mantenible
- ✅ Fácil de testear y debuggear

### **2. Automatización**

- ✅ Se ejecuta automáticamente sin intervención manual
- ✅ Tolerante a fallos
- ✅ No requiere cron jobs externos

### **3. Observabilidad**

- ✅ Logs estructurados con contexto completo
- ✅ Endpoints de health y status
- ✅ Estado persistente en Redis

### **4. Escalabilidad**

- ✅ Paralelización interna (semaphores)
- ✅ Rate limiting configurable
- ✅ Puede ejecutarse en servidor dedicado

### **5. Independencia**

- ✅ No sobrecarga otros servicios
- ✅ No compite por recursos CPU/RAM
- ✅ Puede reiniciarse sin afectar otros servicios

---

## 🔮 Futuro

### **Mejoras Potenciales**

1. **Notificaciones**:

   - Alertas Slack/Email si mantenimiento falla
   - Webhook al completar

2. **Dashboard**:

   - UI simple con estado visual
   - Histórico de ejecuciones

3. **Métricas**:

   - Prometheus metrics endpoint
   - Grafana dashboards

4. **Scheduling Avanzado**:

   - Múltiples horarios (pre-market + after hours)
   - Diferentes ventanas por tarea

5. **Priorización Inteligente**:
   - Metadata solo para tickers activos en scanner
   - Skip tickers con volumen = 0

---

## 📚 Referencias

- **Código**: `services/data_maintenance/`
- **Docker**: `docker-compose.yml` (servicio `data_maintenance`)
- **Documentación**: `services/data_maintenance/README.md`
- **Market Session**: `shared/enums/market_session.py`
