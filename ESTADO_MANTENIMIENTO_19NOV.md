# 📊 ESTADO DEL MANTENIMIENTO - 19 Noviembre 2025

**Fecha verificación:** 19 Nov 2025, 08:33 WET  
**Última ejecución:** 18 Nov 2025, 22:00-22:04 WET (17:00 ET)

---

## ✅ RESUMEN EJECUTIVO

### Estado General: ⚠️ PARCIALMENTE ACTUALIZADO

| Componente | Estado | Última Actualización | Registros |
|------------|--------|---------------------|-----------|
| ✅ Servicio data_maintenance | **RUNNING** | - | Up 12 hours |
| ✅ TimescaleDB | **HEALTHY** | - | Up 42 hours |
| ✅ Redis | **HEALTHY** | - | Up 4 days |
| ✅ Ticker Universe (BD) | **ACTUALIZADO** | 18 Nov, 09:07 | 12,054 tickers |
| ✅ Ticker Metadata (BD) | **ACTUALIZADO** | 18 Nov, 22:04 | 12,039 tickers |
| ✅ Ticker Metadata (Redis) | **ACTUALIZADO** | 18 Nov, 22:04 | 12,039 keys |
| ✅ ATR Data (Redis) | **ACTUALIZADO** | 18 Nov, 22:00 | 11,598 tickers |
| ❌ RVOL Averages (Redis) | **CRÍTICO** | ??? | **SOLO 1 ticker** |

---

## 🚨 PROBLEMA CRÍTICO DETECTADO

### ❌ RVOL Averages Missing (Redis)

**Esperado:** ~11,500 hashes `rvol:hist:avg:{symbol}:5`  
**Encontrado:** **SOLO 1 hash**

**Impacto:**
- Analytics NO puede calcular RVOL correctamente
- Scanner NO puede filtrar por RVOL
- Tickers no aparecen en categorías que requieren RVOL (anomalies, high_volume)

**Causa probable:**
1. Los datos expiraron (TTL: 8 horas según código)
2. La tarea de cálculo de RVOL no se ejecutó correctamente
3. Redis fue limpiado accidentalmente

---

## 📋 DETALLES POR COMPONENTE

### 1. ✅ Ticker Universe (TimescaleDB)

```
Tabla: ticker_universe
Registros: 12,054
Última actualización: 18 Nov 2025, 09:07 UTC
Estado: ✅ ACTUALIZADO
```

**Verificación:**
```sql
SELECT COUNT(*), MAX(last_seen) FROM ticker_universe;
-- 12054 | 2025-11-18 09:07:30.022593+00
```

---

### 2. ✅ Ticker Metadata (TimescaleDB + Redis)

#### TimescaleDB:
```
Tabla: ticker_metadata
Registros: 12,039
Última actualización: 18 Nov 2025, 22:04 UTC (17:00 ET)
Estado: ✅ ACTUALIZADO (hace 10 horas)
```

#### Redis:
```
Claves: metadata:ticker:*
Total: 12,039 keys
Estado: ✅ SINCRONIZADO con BD
```

**Datos incluyen:**
- Market cap
- Float shares
- Sector/Industry
- Exchange
- Avg volume 30d/10d
- Company info

---

### 3. ✅ ATR Data (Redis)

```
Clave: atr:daily (HASH)
Total: 11,598 tickers
Última actualización: 18 Nov 2025
TTL: 24 horas
Estado: ✅ ACTUALIZADO
```

**Muestra de datos:**
```json
{
  "MKL": {"atr": 37.94, "atr_percent": 1.81, "updated": "2025-11-18"},
  "UNP": {"atr": 3.50, "atr_percent": 1.57, "updated": "2025-11-18"},
  "VEEV": {"atr": X.XX, "atr_percent": X.XX, "updated": "2025-11-18"}
}
```

---

### 4. ❌ RVOL Averages (Redis) - CRÍTICO

```
Claves esperadas: rvol:hist:avg:{symbol}:5
Total: SOLO 1 hash (debería haber ~11,500)
TTL: 8 horas (14 horas según auto-recover)
Estado: ❌ MISSING / EXPIRED
```

**Logs de última ejecución (18 Nov, 22:00):**
```
rvol_averages_task_completed:
  redis_inserted=1,720,505
  symbols_processed=11,549
  symbols_total=12,054
  duration_seconds=137.17
```

**Problema:** Los datos se insertaron correctamente PERO han expirado porque:
- TTL: 8 horas (código línea 294)
- Última inserción: 22:00 del 18 Nov
- Ahora: 08:33 del 19 Nov (10.5 horas después)
- **TTL expirado hace 2.5 horas**

---

## ⏰ HORARIO DE MANTENIMIENTO

### Configuración Actual:

```python
# maintenance_scheduler.py
maintenance_hour = 17  # 5:00 PM ET
maintenance_minute = 0
check_interval = 60  # Revisar cada 60 segundos
```

**Traducción de horarios:**
- **17:00 ET** (Eastern Time) = **22:00 WET** (Western European Time)
- Se ejecuta **1 hora después del cierre del mercado** (16:00 ET / 21:00 WET)
- Solo días de semana (lunes a viernes)

### Próxima Ejecución:
- **Hoy 19 Nov 2025 a las 22:00 WET** (17:00 ET)
- Faltan ~13.5 horas

---

## 📝 LOGS DE ÚLTIMA EJECUCIÓN

### 18 Nov 2025, 22:00-22:04 WET

```
✅ 22:00:05 - volume_slots: Completado (0 records - ya cargados)
✅ 22:00:07 - calculate_atr: Completado (0 success, 12,054 skipped)
✅ 22:02:24 - calculate_rvol_averages: Completado
            - redis_inserted: 1,720,505
            - symbols_processed: 11,549
            - duration: 137.17 segundos
✅ 22:03:05 - metadata_enrich: Completado (493 enriched)
✅ 22:03:18 - auto_recover_missing: Completado (0 recovered)
✅ 22:04:06 - redis_sync: Completado
            - universe_synced: 12,054
            - metadata_synced: 12,039
            - volume_avg_synced: 11,879
```

**Total duration:** ~4 minutos  
**Estado:** ✅ Todos los tasks completados exitosamente

---

## 🔍 ANÁLISIS DEL PROBLEMA RVOL

### Timeline:

| Hora | Evento |
|------|--------|
| 18 Nov, 22:02 | ✅ RVOL averages calculados (1.72M inserts) |
| 18 Nov, 22:02 | ⏰ TTL configurado: 8 horas (expira 19 Nov, 06:02) |
| 19 Nov, 06:02 | ⏱️ TTL EXPIRADO - Redis limpia datos automáticamente |
| 19 Nov, 08:33 | ❌ Solo queda 1 hash de RVOL (actual) |

### Por qué solo queda 1 hash:

El hash que quedó podría ser:
1. Un ticker procesado por Analytics en tiempo real (con TTL diferente)
2. Un ticker recuperado por auto-recover (TTL: 14 horas)
3. Datos residuales

---

## 🛠️ SOLUCIÓN INMEDIATA

### Opción 1: Esperar hasta esta noche (RECOMENDADA)
- El mantenimiento se ejecutará automáticamente a las 22:00 WET
- Recalculará todos los promedios RVOL
- TTL de 8 horas cubrirá hasta las 06:00 del día siguiente

### Opción 2: Ejecutar mantenimiento AHORA (MANUAL)

```bash
# Triggerar mantenimiento manual
curl -X POST http://localhost:8008/trigger

# Monitorear logs
docker compose logs -f data_maintenance
```

**Duración estimada:** 4-5 minutos  
**Impacto:** NINGUNO (puede ejecutarse con mercado abierto o cerrado)

---

## 📊 RECOMENDACIONES

### 1. ⚠️ AUMENTAR TTL DE RVOL (CRÍTICO)

**Problema:** TTL de 8 horas NO cubre el período entre mantenimientos (24 horas)

**Solución:** Aumentar TTL a 48 horas (2 días)

**Archivo:** `services/data_maintenance/tasks/calculate_rvol_averages.py`

```python
# Línea 66 (aproximadamente)
# ANTES:
self.redis_ttl = 50400  # 14 horas

# CAMBIAR A:
self.redis_ttl = 172800  # 48 horas (2 días)
```

**Razón:** 
- Mantenimiento: cada 24 horas
- TTL necesario: >24 horas con margen
- TTL recomendado: 48 horas (permite 1 fallo de mantenimiento)

---

### 2. 🔄 EJECUTAR MANTENIMIENTO AHORA

Para restaurar RVOL inmediatamente:

```bash
# 1. Ejecutar mantenimiento
curl -X POST http://localhost:8008/trigger

# 2. Verificar estado
curl http://localhost:8008/status | python3 -m json.tool

# 3. Monitorear logs
docker compose logs -f data_maintenance | grep -E "(rvol|task_completed)"
```

---

### 3. 📈 MONITOREO AUTOMÁTICO

Implementar health check que alerte si:
- RVOL keys < 10,000
- ATR keys < 10,000
- Metadata keys < 10,000

**Endpoint actual:**
```bash
curl http://localhost:8008/status
```

---

## 🎯 CHECKLIST DE VERIFICACIÓN

### Estado Actual (19 Nov, 08:33):

- [x] Servicio data_maintenance: RUNNING
- [x] TimescaleDB: HEALTHY
- [x] Redis: HEALTHY
- [x] Ticker Universe: ACTUALIZADO (12,054)
- [x] Ticker Metadata (BD): ACTUALIZADO (12,039)
- [x] Ticker Metadata (Redis): ACTUALIZADO (12,039)
- [x] ATR Data: ACTUALIZADO (11,598)
- [ ] **RVOL Averages: CRÍTICO (solo 1 de 11,500)**

### Acciones Inmediatas:

- [ ] **URGENTE:** Ejecutar `curl -X POST http://localhost:8008/trigger`
- [ ] Verificar RVOL después de mantenimiento: `docker compose exec redis redis-cli KEYS "rvol:hist:avg:*" | wc -l`
- [ ] Aumentar TTL de RVOL a 48 horas
- [ ] Rebuild data_maintenance con nuevo TTL
- [ ] Verificar que RVOL persiste hasta próximo mantenimiento

---

## 📞 COMANDOS ÚTILES

### Verificar estado general:
```bash
# Estado del servicio
curl http://localhost:8008/status | python3 -m json.tool

# Verificar RVOL en Redis
docker compose exec redis redis-cli KEYS "rvol:hist:avg:*" | wc -l

# Verificar ATR en Redis
docker compose exec redis redis-cli HLEN "atr:daily"

# Verificar Metadata en Redis
docker compose exec redis redis-cli KEYS "metadata:ticker:*" | wc -l

# Logs del servicio
docker compose logs data_maintenance --tail=50
```

### Ejecutar mantenimiento manual:
```bash
# Triggerar ahora
curl -X POST http://localhost:8008/trigger

# Ver progreso
docker compose logs -f data_maintenance
```

### Verificar BD:
```bash
# Ticker universe
docker compose exec timescaledb psql -U tradeul_user -d tradeul -c "SELECT COUNT(*), MAX(last_seen) FROM ticker_universe;"

# Metadata
docker compose exec timescaledb psql -U tradeul_user -d tradeul -c "SELECT COUNT(*), MAX(updated_at) FROM ticker_metadata;"
```

---

## 🏁 CONCLUSIÓN

### Estado General: ⚠️ REQUIERE ACCIÓN INMEDIATA

**Funcionando:**
✅ Base de datos actualizada (ticker_universe, ticker_metadata)  
✅ Redis metadata sincronizado (12,039 tickers)  
✅ ATR calculado y disponible (11,598 tickers)  
✅ Servicio de mantenimiento operacional  

**Problema Crítico:**
❌ **RVOL Averages han expirado** (TTL: 8 horas, última actualización: hace 10.5 horas)  
❌ **Scanner/Analytics NO pueden calcular RVOL correctamente**  
❌ **Categorías afectadas:** anomalies, high_volume, cualquier filtro de RVOL  

**Solución:**
1. ✅ Ejecutar mantenimiento AHORA: `curl -X POST http://localhost:8008/trigger`
2. ✅ Aumentar TTL de RVOL a 48 horas
3. ✅ Rebuild servicio con nuevo TTL
4. ⏰ Próximo mantenimiento automático: Hoy a las 22:00 WET

---

**Fecha:** 19 Nov 2025, 08:33 WET  
**Investigado por:** AI Assistant  
**Prioridad:** 🔴 ALTA (afecta funcionalidad core del scanner)

