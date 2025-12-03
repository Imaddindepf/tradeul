# Upgrade a Mantenimiento v2.0

## Cambios Principales

### Antes (v1)
- **Mantenimiento principal**: 17:00 ET (5:00 PM, después del cierre)
- **Limpieza de caches**: 3:00 AM ET (separado)
- **Problema**: Dos schedulers separados, lógica compleja, validaciones que fallaban

### Después (v2)
- **Mantenimiento completo**: 3:00 AM ET (1 hora antes del pre-market)
- **Todo en uno**: Un solo scheduler que hace todo
- **Lógica simple**: Cada tarea es independiente y se auto-valida

## Archivos Nuevos

```
services/data_maintenance/
├── daily_maintenance_scheduler.py   # Scheduler único (3:00 AM ET)
├── maintenance_orchestrator.py      # Orquestador de tareas
├── main_new.py                      # Nueva API FastAPI
└── tasks/
    ├── ohlc_loader.py               # Carga OHLC (1 día específico)
    ├── volume_slots_loader.py       # Carga volume slots (1 día específico)
    └── atr_calculator.py            # Calcula ATR (usa cache)
```

## Tareas Existentes (sin cambios)

```
services/data_maintenance/tasks/
├── calculate_rvol_averages.py       # ✅ Compatible
├── enrich_metadata.py               # ✅ Compatible  
├── sync_redis.py                    # ✅ Compatible
└── auto_recover_missing_tickers.py  # ✅ Compatible
```

## Flujo del Mantenimiento v2

```
3:00 AM ET (cada día de trading)
    │
    ├─► 1. clear_caches          - Limpiar caches del día anterior
    │
    ├─► 2. load_ohlc             - Cargar OHLC del día anterior
    │
    ├─► 3. load_volume_slots     - Cargar volume slots del día anterior
    │
    ├─► 4. calculate_atr         - Calcular ATR para todos los tickers
    │
    ├─► 5. calculate_rvol        - Calcular RVOL historical averages
    │
    ├─► 6. enrich_metadata       - Enriquecer metadata (market cap, float)
    │
    ├─► 7. sync_redis            - Sincronizar Redis con datos frescos
    │
    └─► 8. notify_services       - Publicar evento "maintenance_completed"
```

## Pasos para Activar v2

### 1. Backup del código actual (cuando el mercado esté cerrado)
```bash
cd /opt/tradeul/services/data_maintenance
mv main.py main_v1.py
mv main_new.py main.py
```

### 2. Rebuild del contenedor
```bash
cd /opt/tradeul
docker compose build data_maintenance
docker compose up -d data_maintenance
```

### 3. Verificar logs
```bash
docker logs tradeul_data_maintenance -f
```

### 4. Verificar health
```bash
curl http://localhost:8008/health
curl http://localhost:8008/next-run
```

## API Endpoints v2

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Estado del servicio |
| `/status` | GET | Estado del último mantenimiento |
| `/next-run` | GET | Próxima ejecución programada |
| `/trigger` | POST | Trigger manual (body: `{"target_date": "2025-12-02"}`) |
| `/clear-caches` | POST | Limpiar caches manualmente |

## Rollback a v1

```bash
cd /opt/tradeul/services/data_maintenance
mv main.py main_new.py
mv main_v1.py main.py

cd /opt/tradeul
docker compose build data_maintenance
docker compose up -d data_maintenance
```

## Notas Importantes

1. **NO ejecutar durante trading hours**: El cambio debe hacerse cuando el mercado esté cerrado
2. **El nuevo scheduler es idempotente**: Si se ejecuta dos veces el mismo día, no duplica datos
3. **Logs mejorados**: Cada tarea logea su progreso y resultado
4. **Estado en Redis**: Se guarda en `maintenance:status:{date}` para debugging

