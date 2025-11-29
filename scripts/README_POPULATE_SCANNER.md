# Script: Poblar Scanner desde Polygon Snapshot

## Descripción

Este script imita el proceso del scanner pero usando snapshots de Polygon directamente. Es útil para poblar datos durante el fin de semana cuando el scanner no está ejecutándose pero Polygon tiene snapshots disponibles hasta el domingo (una hora antes del pre-market del lunes).

## Uso

### Ejecutar desde el contenedor del scanner

```bash
# Ejecutar dentro del contenedor del scanner
docker compose exec scanner python /opt/tradeul/scripts/populate_scanner_from_polygon.py
```

### O desde el host (si tienes acceso a los módulos)

```bash
cd /opt/tradeul
python scripts/populate_scanner_from_polygon.py
```

## Qué hace el script

1. **Obtiene Full Market Snapshot de Polygon**: Usa el endpoint `/v2/snapshot/locale/us/markets/stocks/tickers` para obtener todos los tickers activos.

2. **Enriquece los datos**:
   - Obtiene RVOL desde Redis (si Analytics ya lo calculó)
   - Calcula RVOL simplificado si no está en Redis (volume_today / avg_volume_30d)
   - Obtiene ATR desde Redis (si está disponible)
   - Obtiene intraday high/low desde el snapshot

3. **Aplica filtros**: Usa los mismos filtros configurados en el scanner (desde Redis o BD).

4. **Procesa y filtra**: Usa el mismo método `_process_snapshots_optimized` del scanner para:
   - Validar precios y volúmenes
   - Obtener metadata (desde Redis o BD)
   - Construir `ScannerTicker` objects
   - Aplicar filtros
   - Calcular scores
   - Asignar ranks

5. **Guarda en Redis**: Usa el mismo método `_save_filtered_tickers_to_cache` del scanner para guardar:
   - Cache por sesión con TTL de 48 horas
   - Cache permanente `scanner:filtered_complete:LAST` sin TTL

6. **Categoriza**: Opcionalmente categoriza los tickers (gappers_up, momentum_up, etc.)

## Notas

- El script **NO modifica** el código principal del scanner
- Usa la misma lógica de filtrado y procesamiento del scanner
- Los datos se guardan en Redis de la misma forma que el scanner normal
- Útil para poblar datos durante el fin de semana cuando el mercado está cerrado

## Requisitos

- Acceso a Polygon API (API key configurada)
- Redis funcionando
- TimescaleDB funcionando (para metadata fallback)
- Módulos de Python del proyecto disponibles

## Logs

El script genera logs detallados usando `structlog`:
- Total de snapshots obtenidos de Polygon
- Tickers enriquecidos
- Tickers filtrados
- Tickers guardados en Redis

