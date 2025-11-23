# FASE 3: Migración de Microservicios a tickers_unified

**Fecha**: 2025-11-23  
**Estado**: En progreso  
**Objetivo**: Adaptar todos los microservicios y scripts para usar `tickers_unified` directamente

---

## 📊 ANÁLISIS DE IMPACTO

### ✅ ESTADO ACTUAL (Post FASE 1 y 2)
- `tickers_unified` creada con **35 campos** (20 base + 15 expandidos)
- **12,369 registros** migrados correctamente
- Vistas `ticker_metadata` y `ticker_universe` funcionando como capas de compatibilidad
- **0 downtime** - Todos los servicios funcionan sin cambios

### 🎯 OBJETIVO FASE 3
- Eliminar dependencias de las vistas
- Usar `tickers_unified` directamente en todos los servicios
- Deprecar tablas antiguas (`ticker_metadata_old`, `ticker_universe_old`)
- Limpiar Redis y forzar re-sincronización completa

---

## 📋 ARCHIVOS IDENTIFICADOS (29 archivos)

### 🔴 **CRÍTICOS - Servicios en producción**

#### 1. **ticker-metadata-service** (Puerto 8010)
- `services/ticker-metadata-service/metadata_manager.py`
  - **Línea 258**: `SELECT * FROM ticker_metadata WHERE symbol = $1`
  - **Línea 271**: `INSERT INTO ticker_metadata (...) VALUES (...)`
  - **Impacto**: Alto - Servicio principal de metadata
  - **Acción**: Cambiar a `tickers_unified`

#### 2. **scanner** (Puerto 8001)
- `services/scanner/scanner_engine.py`
  - **Uso indirecto** vía `TimescaleClient.get_ticker_metadata()`
  - **Impacto**: Medio - Usa el cliente genérico
  - **Acción**: Actualizar `TimescaleClient`

#### 3. **shared/utils/timescale_client.py**
- **Línea 278**: `SELECT * FROM ticker_metadata WHERE symbol = $1`
- **Línea 290**: `INSERT INTO ticker_metadata (...)`
- **Impacto**: CRÍTICO - Usado por TODOS los servicios
- **Acción**: Cambiar métodos a `tickers_unified`

### 🟡 **IMPORTANTES - Data Maintenance**

#### 4. **data_maintenance** (Puerto 8007)
- `tasks/sync_redis.py` - Sincroniza metadata a Redis
- `tasks/load_ohlc.py` - Carga datos históricos
- `tasks/enrich_metadata.py` - Enriquece metadata desde Polygon
- `tasks/calculate_atr.py` - Calcula ATR
- `tasks/calculate_rvol_averages.py` - Calcula RVOL
- `tasks/auto_recover_missing_tickers.py` - Recupera tickers faltantes
- `tasks/load_volume_slots.py` - Carga slots de volumen
- `redis_health_checker.py` - Monitoreo de Redis
- `realtime_ticker_monitor.py` - Monitor en tiempo real
- **Impacto**: Medio-Alto - Tareas programadas
- **Acción**: Cambiar queries a `tickers_unified`

#### 5. **historical** (Puerto 8004)
- `ticker_universe_loader.py` - **USA `ticker_universe`** 🚨
- `historical_loader.py` - Carga datos históricos
- `polygon_data_loader.py` - Obtiene datos de Polygon
- `main.py` - Entry point
- **Impacto**: Alto - Manejo de ticker universe
- **Acción**: Cambiar `ticker_universe` a `tickers_unified`

#### 6. **dilution-tracker** (Puerto 8009)
- `services/sec_dilution_service.py`
- `strategies/tier_manager.py`
- `services/data_aggregator.py`
- `routers/analysis_router.py`
- **Impacto**: Medio - Análisis de dilución
- **Acción**: Verificar y actualizar queries

### 🟢 **SCRIPTS DE MANTENIMIENTO**

#### 7. **Scripts**
- `scripts/sync_redis_safe.py` - **Línea 31**: `SELECT * FROM ticker_metadata` 🚨
- `scripts/populate_cik.py` - Popula CIK desde SEC
- `scripts/load_massive_parallel.py` - Carga masiva paralela
- `scripts/populate_basic_metadata.py` - Popula metadata básica
- `scripts/load_universe_polygon.py` - Carga universe desde Polygon
- `scripts/verify_historical_data.py` - Verifica datos históricos
- `scripts/repopulate_metadata.py` - Repopula metadata
- **Impacto**: Bajo - Scripts manuales
- **Acción**: Actualizar todos los queries

---

## 🚀 PLAN DE EJECUCIÓN

### **FASE 3.1: Componentes Compartidos** ⏱️ 15 min
1. ✅ Actualizar `shared/utils/timescale_client.py`
   - Cambiar `get_ticker_metadata()` a `tickers_unified`
   - Cambiar `upsert_ticker_metadata()` a `tickers_unified`
   - Agregar método `get_ticker_by_symbol()` genérico

### **FASE 3.2: Servicios Críticos** ⏱️ 30 min
2. ✅ Actualizar `ticker-metadata-service`
   - `metadata_manager.py`: Cambiar todas las queries
   - Probar endpoints `/api/v1/metadata/{symbol}`

3. ✅ Actualizar `scanner`
   - Verificar que usa `TimescaleClient` actualizado
   - No requiere cambios directos

### **FASE 3.3: Historical Service** ⏱️ 20 min
4. ✅ Actualizar `historical/ticker_universe_loader.py`
   - **CRÍTICO**: Cambiar `ticker_universe` a `tickers_unified`
   - Actualizar lógica de carga

### **FASE 3.4: Data Maintenance** ⏱️ 25 min
5. ✅ Actualizar `data_maintenance/tasks/`
   - `sync_redis.py`: **CRÍTICO** - Sincronización completa
   - `enrich_metadata.py`: Cambiar queries
   - Resto de tasks: Verificar y actualizar

### **FASE 3.5: Scripts** ⏱️ 15 min
6. ✅ Actualizar todos los scripts
   - `sync_redis_safe.py`: **PRIORIDAD 1**
   - Resto de scripts de populate y verify

### **FASE 3.6: Redis Flush** ⏱️ 10 min
7. ✅ Vaciar Redis y re-sincronizar
   - Backup de Redis actual
   - FLUSHDB de database 0 (metadata, cache)
   - Ejecutar `sync_redis_safe.py` con datos de `tickers_unified`
   - Verificar keys sincronizadas

### **FASE 3.7: Verificación** ⏱️ 20 min
8. ✅ Pruebas completas
   - Verificar ticker-metadata-service
   - Verificar scanner (tablas en frontend)
   - Verificar dilution-tracker
   - Verificar logs de errores

---

## 🔄 ESTRATEGIA DE ROLLBACK

Si algo falla durante la migración:

```sql
-- 1. Revertir vistas a tablas antiguas
DROP VIEW IF EXISTS ticker_metadata CASCADE;
DROP VIEW IF EXISTS ticker_universe CASCADE;

ALTER TABLE ticker_metadata_old RENAME TO ticker_metadata;
ALTER TABLE ticker_universe_old RENAME TO ticker_universe;

-- 2. Restaurar Redis desde backup
-- (usar script de restauración)

-- 3. Reiniciar servicios
docker-compose restart ticker-metadata-service scanner data-maintenance
```

---

## ✅ CRITERIOS DE ÉXITO

- [ ] Todos los servicios usan `tickers_unified` directamente
- [ ] No hay errores en logs de servicios
- [ ] Frontend muestra tablas correctamente
- [ ] Redis tiene todos los metadata sincronizados
- [ ] Queries de metadata son más rápidas (sin overhead de vistas)
- [ ] Dilution Tracker funciona correctamente
- [ ] Scripts de mantenimiento funcionan

---

## 📊 TIEMPO ESTIMADO TOTAL

- **Desarrollo**: ~2 horas
- **Testing**: ~30 minutos
- **Despliegue**: ~15 minutos
- **TOTAL**: ~2.75 horas

---

## 🎯 PRÓXIMOS PASOS (Post-FASE 3)

### FASE 4: Limpieza (Opcional, post-verificación)
- Eliminar tablas antiguas (`ticker_metadata_old`, `ticker_universe_old`)
- Eliminar vistas de compatibilidad
- Optimizar índices en `tickers_unified`
- Agregar Foreign Keys desde otras tablas

---

**Preparado por**: AI Assistant  
**Revisado por**: [Pendiente]  
**Aprobado por**: [Pendiente]

