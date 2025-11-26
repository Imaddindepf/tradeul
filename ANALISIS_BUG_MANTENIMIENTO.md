# 🐛 ANÁLISIS: Por Qué el Mantenimiento Falla Silenciosamente

**Problema:** El mantenimiento dice "completed: true" pero solo cargó 14 tickers en vez de 11,000

---

## 🔍 EL BUG

### Código en `task_orchestrator.py` (línea 175-176):

```python
if result.get("success", False):
    state["tasks"][task_name] = TaskStatus.COMPLETED
```

**El problema:**  
La tarea retorna `success=True` **sin validar** si realmente cargó suficientes datos.

---

## 📋 CASOS DONDE RETORNA success=True INCORRECTAMENTE

### Caso 1: Días ya completos (load_ohlc.py línea 82-89)

```python
if not trading_days:
    logger.info("all_days_complete")
    return {
        "success": True,  # ← PROBLEMA
        "records_inserted": 0
    }
```

**Cuándo pasa:**
- Si detecta que el día ya tiene >= 10,000 símbolos
- Retorna success sin cargar nada
- Pero si la detección falla, dice success con 0 records

### Caso 2: Carga parcial (cualquier task)

```python
# Si carga aunque sea 1 registro, retorna success
return {
    "success": True,  # ← PROBLEMA
    "records_inserted": 14  # Solo 14 de 11,000
}
```

**No hay validación de:**
- ❌ Cantidad mínima de records
- ❌ Porcentaje de éxito
- ❌ Comparación con días anteriores

---

## 💡 SOLUCIÓN NECESARIA

### 1. **Validar cantidad de datos en cada tarea**

```python
# En load_ohlc.py
result = await self._load_data(...)

MIN_EXPECTED_TICKERS = 10000

if result["records_inserted"] < MIN_EXPECTED_TICKERS:
    logger.error(
        "insufficient_data_loaded",
        expected_min=MIN_EXPECTED_TICKERS,
        actual=result["records_inserted"]
    )
    return {
        "success": False,  # ← MARCAR COMO FALLO
        "error": f"Only loaded {result['records_inserted']} tickers, expected >= {MIN_EXPECTED_TICKERS}",
        ...
    }

return {
    "success": True,
    ...
}
```

### 2. **Agregar health checks en task_orchestrator**

```python
# Después de ejecutar tarea
result = await task.execute(target_date)

# Validar resultado
if result.get("success"):
    # Verificar que tenga datos significativos
    records = result.get("records_inserted", 0)
    
    if task.name == "ohlc_daily" and records < 10000:
        logger.error("insufficient_ohlc_data", records=records)
        state["tasks"][task_name] = TaskStatus.FAILED
        all_success = False
    elif task.name == "volume_slots" and records < 500000:
        logger.error("insufficient_volume_data", records=records)
        state["tasks"][task_name] = TaskStatus.FAILED
        all_success = False
    else:
        state["tasks"][task_name] = TaskStatus.COMPLETED
```

### 3. **Agregar retry automático**

```python
# Si falla una tarea crítica, reintentarla
MAX_RETRIES = 3

for retry in range(MAX_RETRIES):
    result = await task.execute(target_date)
    
    if result.get("success") and self._validate_result(task, result):
        break  # Éxito
    
    if retry < MAX_RETRIES - 1:
        logger.warning(f"task_retry", task=task.name, attempt=retry+1)
        await asyncio.sleep(30)  # Esperar antes de reintentar
```

---

## 🎯 POR QUÉ ES CRÍTICO

```
Sin validación:
├─ Tarea carga 14 de 11,000 → dice "success"
├─ Orchestrator marca "completed"
├─ No se reintenta
├─ Sistema queda con datos incompletos
└─ Nadie se da cuenta hasta que fallan los cálculos

Con validación:
├─ Tarea carga 14 de 11,000 → dice "FAILED"
├─ Orchestrator marca "failed"
├─ Sistema puede reintentar automáticamente
├─ Logs muestran el problema claramente
└─ Admin puede actuar
```

---

## 📊 TAREAS AFECTADAS

Todas las tareas necesitan validación:

```
1. LoadOHLCTask → Validar >= 10,000 tickers
2. LoadVolumeSlotsTask → Validar >= 500,000 records
3. CalculateATRTask → Validar >= 10,000 tickers
4. CalculateRVOLAveragesTask → Validar >= 10,000 keys
5. EnrichMetadataTask → Validar >= 10,000 tickers
6. AutoRecoverMissingTickersTask → OK (no crítico)
7. SyncRedisTask → Validar datos sincronizados
```

---

**Implementar estas validaciones evitará que el problema vuelva a ocurrir.**

