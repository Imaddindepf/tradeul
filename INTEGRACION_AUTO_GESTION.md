# 🔧 GUÍA DE INTEGRACIÓN: AUTO-GESTIÓN DE MEMORIA

## RESUMEN

Esta guía explica cómo integrar las soluciones automáticas de gestión de memoria en cada servicio.

**Lo que hemos creado:**
1. ✅ **Migration SQL**: Configura TimescaleDB automáticamente (retención, compresión, aggregates)
2. ✅ **RedisStreamManager**: Gestiona streams con límites automáticos
3. ✅ **SnapshotManager**: Reemplaza snapshots de 9MB por deltas de 50-200KB

**Todo es AUTOMÁTICO**: Una vez integrado, el sistema se auto-gestiona sin intervención manual.

---

## 📁 ARCHIVOS CREADOS

```
migrations/
  └── 004_optimize_memory_usage.sql       # ← Ejecutar UNA VEZ

shared/utils/
  ├── redis_stream_manager.py             # ← Auto-trimming de streams
  └── snapshot_manager.py                 # ← Snapshots con deltas
```

---

## 🚀 PASO 1: EJECUTAR MIGRATION (UNA SOLA VEZ)

### Opción A: Desde Docker (RECOMENDADO)

```bash
cd /Users/imaddinamsif/Desktop/Tradeul-Amsif

# Ejecutar migration
docker exec tradeul_timescale psql \
  -U tradeul_user \
  -d tradeul \
  -f /path/to/004_optimize_memory_usage.sql

# Verificar que se aplicó
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "
  SELECT hypertable_name, older_than 
  FROM timescaledb_information.jobs 
  WHERE proc_name = 'policy_retention';
"
```

### Opción B: Copiar y ejecutar manualmente

```bash
# 1. Copiar migration al contenedor
docker cp migrations/004_optimize_memory_usage.sql tradeul_timescale:/tmp/

# 2. Ejecutar
docker exec tradeul_timescale psql \
  -U tradeul_user \
  -d tradeul \
  -f /tmp/004_optimize_memory_usage.sql
```

**Resultado esperado:**
```
✅ Políticas de retención configuradas
✅ Compresión automática habilitada
✅ Continuous aggregates creados
✅ Índices optimizados
```

---

## 🔧 PASO 2: INTEGRAR RedisStreamManager EN SERVICIOS

### 2.1 Data Ingest Service

**Archivo:** `services/data_ingest/main.py`

```python
# ============================================
# IMPORTS AÑADIR
# ============================================
from shared.utils.redis_stream_manager import (
    initialize_stream_manager,
    get_stream_manager
)

# ============================================
# EN LA FUNCIÓN lifespan (startup)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... código existente ...
    
    # Inicializar RedisClient
    redis_client = RedisClient(...)
    await redis_client.connect()
    
    # 🔥 AGREGAR: Inicializar StreamManager
    stream_manager = initialize_stream_manager(redis_client)
    await stream_manager.start()  # Inicia auto-trimming
    logger.info("stream_manager_started")
    
    yield
    
    # 🔥 AGREGAR: Detener StreamManager
    await stream_manager.stop()
    logger.info("stream_manager_stopped")

# ============================================
# REEMPLAZAR TODOS LOS redis.xadd POR:
# ============================================

# ANTES:
await redis.xadd("snapshots:raw", {"data": snapshot})

# DESPUÉS:
stream_manager = get_stream_manager()
await stream_manager.xadd("snapshots:raw", {"data": snapshot})

# ¡Eso es todo! El MAXLEN es automático
```

### 2.2 Scanner Service

**Archivo:** `services/scanner/scanner_engine.py`

```python
# ============================================
# IMPORTS AÑADIR AL INICIO
# ============================================
from shared.utils.redis_stream_manager import get_stream_manager

# ============================================
# EN __init__ DEL ScannerEngine
# ============================================
class ScannerEngine:
    def __init__(self, ...):
        # ... código existente ...
        self.stream_manager = get_stream_manager()  # Obtener instancia

# ============================================
# ACTUALIZAR emit_full_snapshot (línea ~1540)
# ============================================
async def emit_full_snapshot(self, list_name: str, tickers: List[ScannerTicker]):
    # ... código existente hasta message = {...} ...
    
    # REEMPLAZAR:
    # await self.redis.xadd(
    #     settings.stream_ranking_deltas,
    #     message,
    #     maxlen=20000,  # ← ESTO ERA HARDCODED
    #     approximate=True
    # )
    
    # POR:
    await self.stream_manager.xadd(
        settings.stream_ranking_deltas,
        message
        # maxlen es automático según config
    )

# ============================================
# ACTUALIZAR emit_ranking_deltas (línea ~1450)
# ============================================
async def emit_ranking_deltas(self, list_name: str, deltas: List[Dict]):
    # ... código existente hasta message = {...} ...
    
    # REEMPLAZAR:
    # await self.redis.xadd(...)
    
    # POR:
    await self.stream_manager.xadd(
        settings.stream_ranking_deltas,
        message
    )
```

### 2.3 Analytics Service

**Archivo:** `services/analytics/main.py`

```python
# Similar al Data Ingest:
# 1. Initialize stream_manager en lifespan
# 2. Reemplazar redis.xadd por stream_manager.xadd
```

---

## 📸 PASO 3: INTEGRAR SnapshotManager EN SCANNER

### 3.1 Inicializar SnapshotManager

**Archivo:** `services/scanner/scanner_engine.py`

```python
# ============================================
# IMPORTS AÑADIR
# ============================================
from shared.utils.snapshot_manager import SnapshotManager

# ============================================
# EN __init__ DEL ScannerEngine
# ============================================
class ScannerEngine:
    def __init__(self, redis_client: RedisClient, ...):
        # ... código existente ...
        
        # 🔥 AGREGAR: Snapshot Manager
        self.snapshot_manager = SnapshotManager(
            redis_client=redis_client,
            full_snapshot_interval=300,  # 5 minutos
            delta_compression_threshold=100,
            min_price_change_percent=0.001,  # 0.1%
            min_rvol_change_percent=0.05     # 5%
        )
        
        logger.info("snapshot_manager_initialized")
```

### 3.2 Usar SnapshotManager en lugar de guardar JSON completo

**Archivo:** `services/scanner/scanner_engine.py`

```python
# ============================================
# ACTUALIZAR _save_ranking_to_redis (línea ~1480)
# ============================================
async def _save_ranking_to_redis(
    self,
    list_name: str,
    tickers: List[ScannerTicker]
):
    """
    Guarda ranking usando snapshot inteligente (full o delta)
    """
    try:
        # Convertir tickers a dict
        ranking_dict = {
            t.symbol: t.model_dump(mode='json')
            for t in tickers
        }
        
        # 🔥 USAR SNAPSHOT MANAGER en lugar de JSON directo
        result = await self.snapshot_manager.save_snapshot(ranking_dict)
        
        # Guardar sequence number
        current_sequence = self.sequence_numbers.get(list_name, 0)
        await self.redis.set(
            f"scanner:sequence:{list_name}",
            current_sequence,
            ttl=86400
        )
        
        logger.debug(
            "ranking_saved_with_snapshot_manager",
            list=list_name,
            snapshot_type=result["type"],  # "full" o "delta"
            count=len(tickers),
            size_kb=result.get("compressed_size", result.get("size", 0)) / 1024
        )
        
    except Exception as e:
        logger.error("save_ranking_error", error=str(e), list=list_name)
```

### 3.3 Frontend: Consumir Deltas (OPCIONAL, puede esperar)

El frontend actualmente consume snapshots completos. Puede seguir funcionando mientras migras:

```typescript
// frontend/lib/api.ts

// Opción 1: Obtener snapshot completo (backward compatible)
export async function getFullSnapshot() {
  const res = await fetch(`${API}/snapshot/full/latest`);
  // Descomprimir en backend y retornar JSON
}

// Opción 2: Obtener delta (nueva funcionalidad)
export async function getSnapshotDelta() {
  const res = await fetch(`${API}/snapshot/delta/latest`);
  // Aplicar delta al estado local
}
```

**Por ahora, puedes seguir usando snapshots completos cada 5 minutos**. El ahorro ya es enorme (9MB → 200KB-1MB comprimido).

---

## 📊 PASO 4: AGREGAR ENDPOINT DE MÉTRICAS

### 4.1 API Gateway: Endpoint de Monitoreo

**Archivo:** `services/api_gateway/main.py`

```python
from shared.utils.redis_stream_manager import get_stream_manager
from shared.utils.snapshot_manager import SnapshotManager

@app.get("/api/v1/internal/memory-metrics")
async def get_memory_metrics():
    """
    Endpoint interno para monitorear uso de memoria
    """
    try:
        stream_manager = get_stream_manager()
        
        # Stats de streams
        stream_stats = stream_manager.get_stats()
        all_streams = await stream_manager.get_all_streams_info()
        
        # Stats de snapshots (si el scanner expone su snapshot_manager)
        # snapshot_stats = snapshot_manager.get_stats()
        
        return {
            "streams": {
                "stats": stream_stats,
                "details": all_streams
            },
            "timescaledb": {
                "retention_policies": "active",  # Configurado en migration
                "compression": "enabled"          # Automático cada 2h
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error("memory_metrics_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

### 4.2 Verificar Métricas

```bash
# Ver métricas de memoria
curl http://localhost:8000/api/v1/internal/memory-metrics | jq

# Resultado esperado:
{
  "streams": {
    "stats": {
      "is_running": true,
      "active_trim_tasks": 5,
      "total_adds": 12450,
      "total_trims": 23,
      "bytes_trimmed": 1250000
    },
    "details": [
      {
        "stream": "snapshots:raw",
        "length": 998,
        "maxlen": 1000,
        "usage_percent": 99.8
      },
      ...
    ]
  }
}
```

---

## ✅ VERIFICACIÓN POST-INTEGRACIÓN

### 1. TimescaleDB (después de 24h)

```sql
-- Verificar que retention está funcionando
SELECT 
  hypertable_name,
  COUNT(*) as chunk_count,
  pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass)) as size
FROM timescaledb_information.hypertables
GROUP BY hypertable_name, hypertable_schema;

-- Debería ver:
-- scan_results: ~2-3 GB (vs 10 GB antes)
-- Chunks comprimidos después de 2 horas
```

### 2. Redis Streams

```bash
# Verificar tamaños de streams
docker exec tradeul_redis redis-cli --scan --pattern "stream:*" | \
  xargs -I {} docker exec tradeul_redis redis-cli XLEN {}

# Debería ver:
# snapshots:raw: ~1000 (vs 50,003 antes)
# stream:ranking:deltas: ~5000 (vs 20,000 antes)
```

### 3. Redis Memory

```bash
docker exec tradeul_redis redis-cli INFO memory | grep used_memory_human

# Debería ver:
# used_memory_human: 150-200MB (vs 743MB antes)
```

### 4. Snapshots

```bash
# Ver tamaño de snapshots
docker exec tradeul_redis redis-cli --bigkeys | grep snapshot

# Debería ver:
# snapshot:full:latest: ~200KB-1MB comprimido (vs 9MB antes)
# snapshot:delta:latest: ~50-200KB
```

### 5. CPU y RAM General

```bash
docker stats --no-stream

# Debería ver:
# timescaledb: 100-200% CPU (vs 691% antes)
# redis: 30-50% CPU (vs 156% antes)
# RAM total: ~2.5-3.5 GB (vs 6-16 GB antes)
```

---

## 🎯 CHECKLIST DE INTEGRACIÓN

### Fase 1: Setup Inicial (30 min)
- [ ] Ejecutar migration `004_optimize_memory_usage.sql`
- [ ] Verificar policies activas en TimescaleDB
- [ ] Reiniciar servicios para aplicar configuración

### Fase 2: Data Ingest (15 min)
- [ ] Agregar imports de `RedisStreamManager`
- [ ] Inicializar en `lifespan()`
- [ ] Reemplazar `redis.xadd` por `stream_manager.xadd`
- [ ] Verificar logs de auto-trimming

### Fase 3: Scanner (30 min)
- [ ] Agregar imports de ambos managers
- [ ] Inicializar `SnapshotManager`
- [ ] Actualizar `_save_ranking_to_redis`
- [ ] Actualizar `emit_full_snapshot`
- [ ] Actualizar `emit_ranking_deltas`
- [ ] Verificar logs de snapshots (full vs delta)

### Fase 4: Analytics (15 min)
- [ ] Similar a Data Ingest
- [ ] Actualizar streams de RVOL

### Fase 5: Monitoreo (15 min)
- [ ] Agregar endpoint de métricas
- [ ] Verificar con `curl`
- [ ] Monitorear por 24-48 horas

### Fase 6: Validación (24-48h)
- [ ] Verificar retención automática funcionando
- [ ] Verificar compresión aplicándose
- [ ] Verificar streams mantienen límites
- [ ] Verificar snapshots usando deltas
- [ ] Confirmar RAM estable < 3.5 GB
- [ ] Confirmar CPU estable < 200%

---

## 🆘 TROUBLESHOOTING

### Problema: Migration falla con "relation already exists"

**Solución:**
```sql
-- Verificar si ya existe
SELECT * FROM timescaledb_information.continuous_aggregates;

-- Si existe, skip esa parte o usar IF NOT EXISTS
```

### Problema: Stream Manager no inicia

**Error:**
```
RedisStreamManager not initialized
```

**Solución:**
```python
# Asegurarse de llamar initialize_stream_manager() en lifespan
stream_manager = initialize_stream_manager(redis_client)
await stream_manager.start()  # ← NO OLVIDAR .start()
```

### Problema: Snapshots siguen siendo grandes

**Verificar:**
```python
# En logs, buscar:
"delta_snapshot_saved"  # Debería aparecer cada 5s
"full_snapshot_saved"   # Debería aparecer cada 5 min

# Si solo ves full_snapshot_saved:
# - Verificar que snapshot_manager está inicializado
# - Verificar que previous_snapshot no está vacío
```

### Problema: Compression policy no funciona

**Verificar:**
```sql
-- Ver jobs de compresión
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_compression';

-- Ver chunks comprimidos
SELECT 
  chunk_name,
  compressed_chunk_name,
  before_compression_total_bytes,
  after_compression_total_bytes
FROM timescaledb_information.compressed_chunk_stats
LIMIT 10;
```

---

## 📈 RESULTADOS ESPERADOS

### Día 0 (Antes):
```
RAM: 6 GB → 16 GB en 24h
CPU TimescaleDB: 691%
Redis Memory: 743 MB
scan_results: 10 GB / 12.5M filas
Snapshots: 9 MB cada 5s
```

### Día 1 (Después de integrar):
```
RAM: 3-4 GB estable
CPU TimescaleDB: 150-200%
Redis Memory: 150-200 MB
scan_results: 2-3 GB / ~2M filas
Snapshots: 50-200 KB deltas, 200KB-1MB full
```

### Día 7 (Estable):
```
RAM: 2.5-3 GB estable
CPU TimescaleDB: 80-150%
Redis Memory: 150 MB estable
scan_results: 2 GB / ~2M filas (3 días)
Sistema auto-gestionado
```

---

## 🎓 CONCEPTOS CLAVE

### ¿Por qué funciona?

1. **Retention Policies**: TimescaleDB borra datos > 3 días AUTOMÁTICAMENTE
2. **Compression**: Datos > 2h se comprimen 80-90% AUTOMÁTICAMENTE
3. **Continuous Aggregates**: Pre-cálculos se mantienen frescos AUTOMÁTICAMENTE
4. **Stream Trimming**: Redis limita streams AUTOMÁTICAMENTE (inline + background)
5. **Snapshot Deltas**: Solo envía cambios, no datos completos

### ¿Qué pasa si falla algo?

- **Retention**: Los datos viejos se mantienen (no se pierden) hasta el próximo job
- **Compression**: Chunks sin comprimir funcionan normal (solo ocupan más)
- **Stream Trimming**: Si falla, siguiente trim cleanup corrige
- **Snapshots**: Si falla delta, envía full snapshot (fallback automático)

**TODO ES RESILIENTE Y AUTO-RECUPERABLE**

---

## 🚀 PRÓXIMOS PASOS

1. ✅ **Ejecutar migration** → 5 min
2. ✅ **Integrar en data_ingest** → 15 min
3. ✅ **Integrar en scanner** → 30 min
4. ✅ **Integrar en analytics** → 15 min
5. ✅ **Agregar métricas** → 15 min
6. ⏳ **Monitorear 24-48h** → validar
7. 🎉 **Sistema auto-gestionado permanentemente**

---

**¿Listo para empezar? ¿Por dónde quieres comenzar?**

