# 📁 Scripts - Herramientas de Mantenimiento

Esta carpeta contiene scripts útiles para operaciones manuales y de emergencia.

## ⚙️ **Scripts de Producción**

### ✅ **init_db.sql**
**Propósito:** Inicialización de esquema de base de datos

```bash
# Se ejecuta automáticamente en docker-compose al iniciar TimescaleDB
# Crea todas las tablas: volume_slots, market_data_daily, ticker_universe, etc.
```

**Cuándo usar:** Setup inicial o reset completo de BD

---

### ✅ **setup.sh**
**Propósito:** Script de setup inicial del sistema completo

```bash
./scripts/setup.sh
```

**Cuándo usar:** Primera instalación del sistema

---

## 🚨 **Scripts de Emergencia**

### 🔥 **load_massive_parallel.py**
**Propósito:** Carga masiva ultra-rápida de `volume_slots` (12K+ tickers)

```bash
docker exec tradeul_data_maintenance python /app/scripts/load_massive_parallel.py
```

**Características:**
- Concurrencia masiva: 1000 tickers simultáneos
- Velocidad: ~100 tickers/segundo
- Detección automática de días faltantes
- Solo carga días que NO existen en BD

**Cuándo usar:**
- Re-población completa de `volume_slots`
- Recuperación de datos después de pérdida
- Carga inicial de histórico
- **NO usar** para mantenimiento diario (usa `data_maintenance`)

**Tiempo estimado:** ~2-3 minutos para 12K tickers × 10 días

---

### 📊 **load_universe_polygon.py**
**Propósito:** Cargar universo completo de tickers desde Polygon

```bash
docker exec tradeul_historical python /app/scripts/load_universe_polygon.py
```

**Cuándo usar:**
- Actualización manual del universo
- Agregar nuevos tickers listados
- **Alternativa:** `POST http://localhost:8004/api/universe/load` (recomendado)

---

### 🔄 **repopulate_metadata.py**
**Propósito:** Re-poblar metadata de tickers (market cap, float, sector)

```bash
docker exec tradeul_historical python /app/scripts/repopulate_metadata.py
```

**Cuándo usar:**
- Actualización masiva de metadata
- Después de cambios en Polygon/FMP APIs
- **Alternativa:** `POST http://localhost:8004/api/warmup/premarket` (recomendado)

---

## 🔍 **Scripts de Verificación**

### ✅ **check_event_filter_parity.py**
**Propósito:** Garantizar paridad exacta de filtros entre frontend y websocket backend

```bash
python3 /opt/tradeul/scripts/check_event_filter_parity.py
# o desde packages:
# cd frontend && npm run check:event-filter-parity
# cd services/websocket_server && npm run check:event-filter-parity
```

**Qué verifica:**
- Que `NUMERIC_FILTER_DEFS`/`STRING_FILTER_DEFS` coinciden con el catálogo compartido
- Que frontend subscribe/update envía todas las claves necesarias
- Que no existan claves wire no parseables por backend

**Cuándo usar:**
- Antes de deploy
- Después de agregar/renombrar filtros
- En troubleshooting de falsos positivos/negativos

---

### ✅ **verify_historical_data.py**
**Propósito:** Verificar integridad de datos históricos

```bash
docker exec tradeul_data_maintenance python /app/scripts/verify_historical_data.py
```

**Qué verifica:**
- Fechas faltantes en `volume_slots`
- Fechas faltantes en `market_data_daily`
- Inconsistencias en datos
- Gaps en histórico

**Cuándo usar:**
- Después de mantenimiento
- Troubleshooting de datos
- Auditorías periódicas

---

### 🔧 **sync_universe_only.py**
**Propósito:** Sincronizar `ticker_universe` BD → Redis sin ejecutar todo el mantenimiento

```bash
docker exec tradeul_data_maintenance python -c "
import asyncio
import sys
sys.path.append('/app')
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

async def sync():
    redis = RedisClient()
    db = TimescaleClient()
    await redis.connect()
    await db.connect()
    rows = await db.fetch('SELECT symbol FROM ticker_universe WHERE is_active = true')
    symbols = [row['symbol'] for row in rows]
    await redis.client.delete('ticker:universe')
    for i in range(0, len(symbols), 1000):
        batch = symbols[i:i + 1000]
        if batch:
            await redis.client.sadd('ticker:universe', *batch)
    after = await redis.client.scard('ticker:universe')
    print(f'✅ Sincronizado: {after} símbolos')
    await redis.disconnect()
    await db.disconnect()

asyncio.run(sync())
"
```

**Cuándo usar:**
- Corregir desincronización BD/Redis
- Después de actualizar `ticker_universe` manualmente

---

## ❌ **Scripts Eliminados (Redundantes)**

Los siguientes scripts fueron eliminados porque `data_maintenance` los hace automáticamente:

- ~~audit_auto_refresh_system.py~~ → `data_maintenance` auto-ejecuta
- ~~bulk_update_metadata.py~~ → `EnrichMetadataTask`
- ~~cache_metadata_to_redis.py~~ → `SyncRedisTask`
- ~~check_daily_reset.py~~ → `MaintenanceScheduler`
- ~~load_atr_massive.py~~ → `CalculateATRTask`
- ~~load_daily_ohlc.py~~ → `LoadOHLCTask`
- ~~update_all_historical_data.sh~~ → `data_maintenance`
- ~~update_all_metadata.py~~ → `EnrichMetadataTask`
- ~~update_metadata_parallel.py~~ → `EnrichMetadataTask`
- ~~update_metadata_simple.sh~~ → `data_maintenance`

---

## 📋 **Cuándo Usar Scripts vs Services**

### ✅ **Usa Services (Automático)**

```bash
# Mantenimiento diario automático
# NO necesitas ejecutar nada, se hace solo cada noche
data_maintenance → Ejecuta TODAS las tareas automáticamente
```

### 🔧 **Usa Scripts (Manual/Emergencia)**

| Situación | Script |
|-----------|--------|
| **Pérdida de datos completa** | `load_massive_parallel.py` |
| **Universo desactualizado** | `load_universe_polygon.py` o API |
| **Metadata faltante** | `repopulate_metadata.py` o API |
| **Verificar integridad** | `verify_historical_data.py` |
| **Desincronización BD/Redis** | `sync_universe_only.py` |
| **Setup inicial** | `setup.sh` |

---

## 🎯 **Regla General**

**99% del tiempo:** `data_maintenance` se encarga de todo automáticamente.

**1% del tiempo:** Scripts manuales para casos especiales (emergencias, verificación, re-población).

**NO ejecutar scripts de carga si `data_maintenance` está funcionando correctamente.**



