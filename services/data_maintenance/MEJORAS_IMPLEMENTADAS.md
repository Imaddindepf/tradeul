# Mejoras Implementadas en el Servicio de Mantenimiento

## 📅 Fecha: 25 de Noviembre 2025

## 🔴 Problemas Identificados

### 1. **Estado en Redis mal gestionado**
- El estado se guardaba incluso cuando fallaban tareas
- No se verificaba si `all_success` era verdadero antes de marcar como completado

### 2. **Ventana de ejecución muy estrecha** 
- Solo 5 minutos (17:00-17:05 ET)
- Si el servicio se reiniciaba en ese período, se perdía la ejecución del día

### 3. **Falta de persistencia del flag de ejecución**
- La variable `maintenance_run_today` era solo en memoria
- Se perdía con reinicios del contenedor

### 4. **Sin logs persistentes**
- Solo stdout/stderr del contenedor
- Los logs se perdían al reiniciar el contenedor
- Sin archivo dedicado de errores

### 5. **Sin recovery automático**
- No detectaba días faltantes
- Requería intervención manual

---

## ✅ Mejoras Implementadas

### 1. **Verificación Mejorada del Estado en Redis** (`task_orchestrator.py`)

**Antes:**
```python
if all_completed:
    return True  # ← Se saltaba sin verificar éxito
```

**Ahora:**
```python
if all_completed and all_success and completed_at:
    return True
else:
    logger.warning("maintenance_incomplete_or_failed", action="re_executing")
    # Re-ejecuta automáticamente
```

**Beneficios:**
- Solo marca como completado si TODAS las tareas terminaron exitosamente
- Re-ejecuta automáticamente si hubo fallos parciales

---

### 2. **Ventana de Ejecución Ampliada** (`maintenance_scheduler.py`)

**Antes:**
```python
current_minute <= 5  # 5 minutos de ventana
```

**Ahora:**
```python
current_minute < 30  # 30 minutos de ventana (17:00-17:30 ET)
```

**Beneficios:**
- 6x más tiempo para ejecutar
- Tolera reinicios del servicio
- Menos probabilidad de perder un día

---

### 3. **Persistencia del Flag en Redis** (`maintenance_scheduler.py`)

**Nuevo sistema:**
```python
# Al detectar nuevo día, verificar Redis
run_flag_key = f"maintenance:executed:{date.isoformat()}"
already_executed = await self.redis.get(run_flag_key)

# Al completar exitosamente, guardar en Redis
await self.redis.set(run_flag_key, "1", ttl=86400 * 7)
```

**Beneficios:**
- Estado persiste entre reinicios
- TTL de 7 días para limpieza automática
- Fuente única de verdad

---

### 4. **Logs con Rotación Automática** (`maintenance_logger.py`)

**Nuevo sistema:**
- **maintenance.log**: Todos los eventos (máx 10MB x 5 archivos = 50MB)
- **maintenance_errors.log**: Solo errores (máx 10MB x 5 archivos = 50MB)
- Rotación automática cuando alcanzan 10MB
- Mantiene últimos 5 archivos de cada tipo

**Ubicación:**
```
/var/log/tradeul/maintenance.log
/var/log/tradeul/maintenance_errors.log
```

**Beneficios:**
- Logs permanentes para debugging
- No consumen todo el espacio en disco
- Archivo dedicado para errores (más fácil de monitorear)

---

### 5. **Recovery Automático de Días Faltantes** (`maintenance_scheduler.py`)

**Nueva función `check_missing_days()`:**
- Se ejecuta al iniciar el scheduler
- Verifica últimos 7 días de trading
- Detecta días sin mantenimiento o con fallos
- Ejecuta automáticamente para cada día faltante (del más antiguo al más reciente)

**Logs:**
```python
logger.warning(
    "missing_maintenance_days_detected",
    count=2,
    dates=["2025-11-21", "2025-11-24"]
)

logger.info(
    "executing_recovery_maintenance",
    date="2025-11-21"
)
```

**Beneficios:**
- Auto-recovery sin intervención manual
- Se ejecuta al reiniciar el servicio
- Mantiene datos siempre actualizados

---

## 📊 Comparación Antes vs Después

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Ventana de ejecución** | 5 minutos | 30 minutos |
| **Persistencia** | En memoria | Redis |
| **Logs** | Solo stdout | Archivos + rotación |
| **Recovery** | Manual | Automático |
| **Verificación estado** | Solo completado | Completado + exitoso |
| **Tolerancia a fallos** | Baja | Alta |

---

## 🧪 Testing

### Probar logs:
```bash
docker exec -it tradeul_data_maintenance ls -lh /var/log/tradeul/
docker exec -it tradeul_data_maintenance tail -f /var/log/tradeul/maintenance.log
docker exec -it tradeul_data_maintenance tail -f /var/log/tradeul/maintenance_errors.log
```

### Probar recovery automático:
```bash
# Eliminar estado de un día para simular fallo
docker exec -i tradeul_redis redis-cli -a tradeul_redis_secure_2024 --no-auth-warning DEL "maintenance:status:2025-11-21"

# Reiniciar servicio
docker restart tradeul_data_maintenance

# Ver logs - debe detectar y ejecutar recovery
docker logs -f tradeul_data_maintenance | grep "missing_maintenance"
```

### Verificar ventana ampliada:
```bash
# El maintenance puede ejecutarse entre 17:00-17:30 ET (22:00-22:30 UTC)
# Simular ejecución manual en cualquier momento de esa ventana
curl -X POST http://localhost:8008/trigger -H "Content-Type: application/json" -d '{"target_date": "2025-11-25"}'
```

---

## 🚀 Próximos Pasos

1. **Rebuild del contenedor**:
   ```bash
   cd /opt/tradeul
   docker-compose build data_maintenance
   docker-compose up -d data_maintenance
   ```

2. **Verificar que inicia correctamente**:
   ```bash
   docker logs -f tradeul_data_maintenance
   ```

3. **Monitorear logs de errores**:
   ```bash
   watch -n 5 'docker exec tradeul_data_maintenance tail -20 /var/log/tradeul/maintenance_errors.log'
   ```

---

## 📝 Notas

- Los logs se mantienen dentro del contenedor. Para persistirlos, considerar agregar un volumen en `docker-compose.yml`
- El recovery automático se ejecuta solo al iniciar el servicio
- La ventana de 30 minutos es configurable en `self.maintenance_window_minutes`

