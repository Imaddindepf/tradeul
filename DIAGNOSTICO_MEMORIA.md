# 🚨 DIAGNÓSTICO: FUGA DE MEMORIA EN DOCKER

## RESUMEN EJECUTIVO

Tu sistema está acumulando datos sin límites de retención, causando:

- **10 GB en TimescaleDB** (scan_results)
- **674 MB en Redis** (streams sin límite)
- **Crecimiento continuo**: ~1.5 GB por día
- **CPU al 671%** en TimescaleDB (sobrecarga de queries)

---

## 🔴 PROBLEMAS IDENTIFICADOS

### 1. **TimescaleDB: `scan_results` - 10 GB / 12.5M filas**

```
Tabla: scan_results
Tamaño: 10,012 MB (10 GB)
Filas: 12,536,682 filas
Período: 29-oct-2025 → 11-nov-2025 (13 días)
Tasa: ~965,000 filas/día
```

**Problema**: Guarda TODOS los resultados del scanner sin política de retención.

**Impacto**:

- Queries cada vez más lentas
- Consumo creciente de RAM
- CPU al 671% (6.7 cores trabajando constantemente)

---

### 2. **TimescaleDB: `volume_slots` - 1.6 GB**

```
Tabla: volume_slots
Tamaño: 1,620 MB
```

**Problema**: Acumula slots de volumen históricos sin límite.

---

### 3. **Redis Streams sin MAXLEN**

```
snapshots:raw:              50,003 mensajes
stream:ranking:deltas:      20,000 mensajes
stream:realtime:aggregates: 10,042 mensajes
```

**Problema**: Los streams crecen infinitamente sin MAXLEN, consumiendo RAM.

---

## ✅ SOLUCIONES INMEDIATAS

### SOLUCIÓN 1: Políticas de Retención en TimescaleDB

**A. Para `scan_results` (retener solo 7 días):**

```sql
-- Agregar política de retención: mantener solo últimos 7 días
SELECT add_retention_policy('scan_results', INTERVAL '7 days');

-- Limpiar datos viejos AHORA
DELETE FROM scan_results WHERE time < NOW() - INTERVAL '7 days';

-- Hacer VACUUM para recuperar espacio
VACUUM FULL scan_results;
```

**Ahorro esperado**: ~8 GB (mantener solo 7 días vs 13 días actuales)

---

**B. Para `volume_slots` (retener solo 30 días):**

```sql
-- Agregar política de retención
SELECT add_retention_policy('volume_slots', INTERVAL '30 days');

-- Limpiar datos viejos
DELETE FROM volume_slots WHERE time < NOW() - INTERVAL '30 days';

-- VACUUM
VACUUM FULL volume_slots;
```

---

### SOLUCIÓN 2: Límites en Redis Streams

**Modificar los servicios para usar MAXLEN:**

En `data_ingest`, `scanner`, `analytics`:

```python
# ANTES (sin límite):
await redis_client.xadd("snapshots:raw", {"data": ...})

# DESPUÉS (con límite de 10,000 mensajes):
await redis_client.xadd(
    "snapshots:raw",
    {"data": ...},
    maxlen=10000,
    approximate=True  # Más eficiente
)
```

**Streams a modificar:**

- `snapshots:raw`: MAXLEN 10,000
- `stream:ranking:deltas`: MAXLEN 5,000
- `stream:realtime:aggregates`: MAXLEN 5,000
- `tickers:filtered`: MAXLEN 1,000

---

### SOLUCIÓN 3: Límites de Memoria en Docker Compose

**Actualizar `docker-compose.yml`:**

```yaml
services:
  timescaledb:
    # ... resto de configuración
    deploy:
      resources:
        limits:
          memory: 4G # Máximo 4GB
        reservations:
          memory: 2G # Mínimo 2GB

  redis:
    # ... resto de configuración
    deploy:
      resources:
        limits:
          memory: 2G # Ya está configurado
        reservations:
          memory: 512M

  scanner:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M

  analytics:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

---

## 🔧 SCRIPT DE LIMPIEZA INMEDIATA

```bash
#!/bin/bash
# cleanup_memory.sh

echo "🧹 Limpiando TimescaleDB..."

docker exec tradeul_timescale psql -U tradeul_user -d tradeul << EOF

-- 1. Agregar políticas de retención
SELECT add_retention_policy('scan_results', INTERVAL '7 days', if_not_exists => true);
SELECT add_retention_policy('volume_slots', INTERVAL '30 days', if_not_exists => true);

-- 2. Limpiar datos antiguos
DELETE FROM scan_results WHERE time < NOW() - INTERVAL '7 days';
DELETE FROM volume_slots WHERE time < NOW() - INTERVAL '30 days';

-- 3. Mostrar tamaños actuales
SELECT
  hypertable_name,
  pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass)) as size
FROM timescaledb_information.hypertables
ORDER BY hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass) DESC;

EOF

echo "🧹 Limpiando Redis streams..."

docker exec tradeul_redis redis-cli XTRIM "snapshots:raw" MAXLEN ~ 1000
docker exec tradeul_redis redis-cli XTRIM "stream:ranking:deltas" MAXLEN ~ 1000
docker exec tradeul_redis redis-cli XTRIM "stream:realtime:aggregates" MAXLEN ~ 1000

echo "✅ Limpieza completada"
echo "Revisa el uso de memoria con: docker stats --no-stream"
```

---

## 📊 RESULTADOS ESPERADOS

**Antes:**

- TimescaleDB: 10 GB + crecimiento continuo
- Redis: 674 MB
- Total: ~11 GB
- Crecimiento: ~1.5 GB/día

**Después de aplicar soluciones:**

- TimescaleDB: ~2-3 GB (estable)
- Redis: ~200 MB (estable)
- Total: ~2.5-3.5 GB (estable)
- Crecimiento: 0 GB/día (auto-limpieza)

---

## 🎯 PLAN DE ACCIÓN RECOMENDADO

### INMEDIATO (hoy):

1. ✅ Ejecutar script de limpieza `cleanup_memory.sh`
2. ✅ Agregar políticas de retención en TimescaleDB
3. ✅ Hacer VACUUM FULL para recuperar espacio

### CORTO PLAZO (esta semana):

4. ⚠️ Modificar servicios para usar MAXLEN en streams
5. ⚠️ Agregar límites de memoria en docker-compose.yml
6. ⚠️ Implementar compresión en TimescaleDB hypertables

### MEDIANO PLAZO (próximas semanas):

7. 📈 Monitoreo automático de memoria
8. 📈 Alertas cuando uso > 80%
9. 📈 Dashboard de métricas

---

## 🔍 MONITORING CONTINUO

**Comando para verificar uso de memoria:**

```bash
# Ver consumo actual
docker stats --no-stream

# Ver tamaño de tablas en TimescaleDB
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "
  SELECT
    hypertable_name,
    pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass)) as size
  FROM timescaledb_information.hypertables;
"

# Ver streams en Redis
docker exec tradeul_redis redis-cli --scan --pattern "stream:*" | \
  xargs -I {} docker exec tradeul_redis redis-cli XLEN {}
```

---

## 📝 NOTAS ADICIONALES

### ¿Por qué crece tanto `scan_results`?

El scanner está guardando resultados cada pocos segundos durante todo el día de mercado:

- **Frecuencia**: cada 5 segundos
- **Tickers**: ~1000 tickers filtrados
- **Sesiones**: pre-market, market, after-hours
- **Horas activas**: ~16 horas/día
- **Cálculo**: 1000 tickers × (16h × 3600s / 5s) = ~11.5M filas/día

### Alternativas para reducir aún más:

1. **Guardar solo top 100 por sesión** (en lugar de top 1000)
2. **Aumentar intervalo de guardado** (de 5s a 30s)
3. **Guardar snapshots agregados** (1 por minuto con promedios)
4. **Usar una tabla separada para históricos** (mover a cold storage)

---

## ⚠️ ADVERTENCIA

**NO ejecutar VACUUM FULL durante horario de mercado**, puede tardar varios minutos y bloquear la tabla.

**Mejor momento**: fines de semana o después de las 8 PM ET (1 AM Madrid).
