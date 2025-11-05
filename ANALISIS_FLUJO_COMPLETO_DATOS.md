# ANÁLISIS COMPLETO DEL FLUJO DE DATOS

## Sistema de Scanner en Tiempo Real - Arquitectura Profesional

**Fecha**: 3 Noviembre 2025  
**Versión**: Post-refactorización snapshot cache  
**Estado**: Producción

---

## 🎯 OBJETIVO DEL DOCUMENTO

Este documento analiza **PASO POR PASO, FUNCIÓN POR FUNCIÓN** todo el flujo de datos desde que Polygon envía información hasta que el frontend la muestra.

El objetivo es entender completamente el sistema para detectar problemas como el que tuvimos con la mezcla de snapshots.

---

## 📊 ARQUITECTURA GENERAL

```
┌─────────────────┐
│   POLYGON API   │ Snapshot cada 5s (11,905 tickers)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  DATA INGEST    │ (1) Fetch + (2) Save cache
└────────┬────────┘
         │ Key: snapshot:polygon:latest
         ▼
┌─────────────────┐
│   ANALYTICS     │ (3) Read cache + (4) Calculate RVOL + (5) Save enriched
└────────┬────────┘
         │ Key: snapshot:enriched:latest
         ▼
┌─────────────────┐
│    SCANNER      │ (6) Read enriched + (7) Filter + (8) Categorize + (9) Rank
└────────┬────────┘
         │ Keys: scanner:category:{name}
         ▼
┌─────────────────┐
│ WEBSOCKET SRV   │ (10) Broadcast deltas
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    FRONTEND     │ (11) Display + (12) Apply deltas
└─────────────────┘
```

---

## 🔍 ANÁLISIS DETALLADO POR SERVICIO

---

## 1. DATA INGEST SERVICE

### 1.1 Archivo: `services/data_ingest/main.py`

**Responsabilidad**: Orquestar la ingesta de datos desde Polygon.

#### 1.1.1 Loop Principal (`consume_snapshots_loop`)

```python
Líneas 90-117

FLUJO:
1. Verifica si is_running = True
2. Consulta Market Session Service
3. Si mercado NO CLOSED:
   - Llama a snapshot_consumer.consume_snapshot()
   - Espera settings.snapshot_interval (5 segundos)
4. Si mercado CLOSED:
   - Espera 60 segundos
```

**PUNTO CRÍTICO**: Intervalo de 5 segundos puede ser más rápido que lo que Scanner procesa.

**ANTES (PROBLEMÁTICO)**:

- Cada 5s se publicaban 11,905 mensajes INDIVIDUALES al stream
- En 30s = 6 snapshots × 11,905 = 71,424 mensajes
- Scanner leía 5,000 → Backlog +66,424 cada 30s

**AHORA (SOLUCIONADO)**:

- Cada 5s SOBRESCRIBE una key fija
- No hay acumulación
- Scanner siempre lee el más reciente

---

### 1.2 Archivo: `services/data_ingest/snapshot_consumer.py`

#### 1.2.1 Método `consume_snapshot()` (líneas 40-81)

```python
FLUJO COMPLETO:
1. Inicia timer
2. Llama _fetch_polygon_snapshot()
   └─ Retorna: List[PolygonSnapshot] (~11,905 tickers)
3. Llama _publish_snapshots(snapshots)
   └─ Guarda en Redis
4. Actualiza estadísticas
5. Loguea tiempo total
```

**TIMING OBSERVADO**:

- Fetch de Polygon: 2-10 segundos
- Publicación: < 100ms
- **Total: 2-10 segundos por ciclo**

#### 1.2.2 Método `_fetch_polygon_snapshot()` (líneas 83-122)

```python
ENDPOINT: https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers

RESPUESTA DE POLYGON:
{
  "status": "OK",
  "count": 11905,
  "tickers": [
    {
      "ticker": "AAPL",
      "day": { "o": 225.0, "h": 227.5, "l": 224.0, "c": 226.5, "v": 45678900 },
      "min": { "av": 125000, "c": 226.3, ... },
      "lastTrade": { "p": 226.3, "s": 100, ... },
      "lastQuote": { "p": 226.2, "P": 226.4, ... },
      "prevDay": { "c": 225.0, "v": 52000000 },
      ...
    },
    ... 11,904 tickers más
  ]
}

CONVERSIÓN:
- Parsea con Pydantic: PolygonSnapshotResponse
- Valida estructura
- Retorna lista de PolygonSnapshot objects
```

**CAMPOS CRÍTICOS**:

- `day.v`: Volumen del día (0 en premarket temprano)
- `min.av`: Volumen acumulado del minuto (CORRECTO para premarket)
- `prevDay.c`: Precio cierre anterior (fallback cuando day.c = 0)

#### 1.2.3 Método `_publish_snapshots()` (líneas 124-169) **NUEVO**

```python
CAMBIO CRÍTICO vs VERSIÓN ANTERIOR:

ANTES:
for snapshot in snapshots:  # 11,905 iteraciones
    await redis.xadd("snapshots:raw", {
        "ticker": snapshot.ticker,
        "data": snapshot.json()
    })
# Resultado: 11,905 mensajes individuales en stream

AHORA:
snapshot_list = []
for s in snapshots:
    ticker_dict = s.model_dump(mode='json')
    # CRÍTICO: Agregar @property fields manualmente
    ticker_dict['current_price'] = s.current_price  # Calcula: lastTrade.p > day.c > prevDay.c
    ticker_dict['current_volume'] = s.current_volume  # Calcula: min.av > day.v
    snapshot_list.append(ticker_dict)

snapshot_data = {
    "timestamp": datetime.now().isoformat(),
    "count": len(snapshots),
    "tickers": snapshot_list  # TODOS juntos
}

await redis.set("snapshot:polygon:latest", snapshot_data, ttl=60)
# Resultado: 1 key con 11,905 tickers
```

**POR QUÉ ESTO RESUELVE EL PROBLEMA**:

1. **Sin acumulación**: Key se SOBRESCRIBE cada 5s
2. **Atómico**: Todos los tickers son del MISMO momento
3. **Sin backlog**: No importa si Scanner es lento
4. **Consistente**: current_price y current_volume calculados correctamente

**ESTRUCTURA EN REDIS**:

```json
snapshot:polygon:latest = {
  "timestamp": "2025-11-03T05:30:15.123456",
  "count": 11905,
  "tickers": [
    {
      "ticker": "AAPL",
      "current_price": 226.3,  // Computed field agregado
      "current_volume": 125000, // Computed field agregado
      "day": {...},
      "min": {...},
      "prevDay": {...},
      ...
    },
    ... 11,904 más
  ]
}
```

---

## 2. ANALYTICS SERVICE

### 2.1 Archivo: `services/analytics/main.py`

**Responsabilidad**: Enriquecer snapshots con RVOL (Relative Volume).

#### 2.1.1 Loop Principal `run_analytics_processing()` (líneas 109-260)

```python
FLUJO PASO POR PASO:

1. DETECCIÓN DE CAMBIO DE DÍA (líneas 128-140)
   └─ Guarda slots del día anterior
   └─ Resetea caché de volúmenes

2. DETECCIÓN DE CAMBIO DE SLOT (líneas 142-151)
   └─ Loguea nuevo slot (ej: slot 14 = 05:10 AM)

3. LECTURA DE SNAPSHOT (líneas 153-171)
   snapshot_data = await redis.get("snapshot:polygon:latest")

   VERIFICACIÓN DE TIMESTAMP:
   - Si snapshot_timestamp == last_processed_timestamp → SKIP
   - Si es nuevo → PROCESAR

   PUNTO CLAVE: Evita procesar el mismo snapshot múltiples veces

4. ENRIQUECIMIENTO CON RVOL (líneas 177-227)

   for ticker_data in tickers_data:  # 11,905 tickers
       symbol = ticker_data.get('ticker')

       # Extraer volumen (CRÍTICO)
       min_data = ticker_data.get('min', {})
       day_data = ticker_data.get('day', {})

       volume = min_data.get('av', 0) or day_data.get('v', 0)

       if volume > 0:
           # Actualizar caché de volumen
           await rvol_calculator.update_volume_for_symbol(symbol, volume, now)

           # Calcular RVOL
           rvol = await rvol_calculator.calculate_rvol(symbol, now)

           if rvol > 0:
               ticker_data['rvol'] = round(rvol, 2)
       else:
           ticker_data['rvol'] = None

       enriched_tickers.append(ticker_data)

5. GUARDAR SNAPSHOT ENRIQUECIDO (líneas 229-240)

   enriched_snapshot = {
       "timestamp": snapshot_timestamp,  # MISMO timestamp del original
       "count": len(enriched_tickers),
       "tickers": enriched_tickers  # TODOS con RVOL agregado
   }

   await redis.set("snapshot:enriched:latest", enriched_snapshot, ttl=60)

6. MARCAR COMO PROCESADO (línea 247)

   last_processed_timestamp = snapshot_timestamp
```

**TIMING**:

- Procesar 11,905 tickers: ~1-3 segundos
- Frecuencia: Cada vez que Data Ingest actualiza el snapshot (5s)

**POR QUÉ ESTO ES CORRECTO**:

✅ **Procesa snapshot COMPLETO** - No parcial  
✅ **Detecta duplicados por timestamp** - No reprocesa  
✅ **Guarda COMPLETO** - Todos los tickers del mismo momento  
✅ **Sincronizado** - timestamp se mantiene

---

### 2.2 Archivo: `services/analytics/rvol_calculator.py`

#### 2.2.1 Método `calculate_rvol()` (líneas 131-196)

```python
LÓGICA DE CÁLCULO:

1. Obtener slot actual (línea 153)
   current_slot = slot_manager.get_current_slot(timestamp)
   # Ejemplo: 05:15 AM = slot 15

2. Obtener volumen de hoy desde caché (línea 159)
   volume_today = volume_cache.get_volume(symbol, current_slot)
   # Si no hay volumen → return None

3. Obtener promedio histórico (líneas 170-175)
   historical_avg = await _get_historical_average_volume(symbol, current_slot, date)

   FUENTES (en orden de prioridad):
   a) Caché Redis: rvol:hist:avg:{symbol}:{slot}
   b) TimescaleDB: volume_slot_averages (últimos 5 días)
   c) FALLBACK: metadata.avg_volume_30d / 192 slots

4. Calcular RVOL (línea 185)
   rvol = volume_today / historical_avg
```

**EJEMPLO REAL**:

```
Ticker: CRBU
- volume_today (slot 14): 13,856,866
- historical_avg (fallback): 5,555 (avg_30d / 192)
- RVOL = 13,856,866 / 5,555 = 2,493x
```

#### 2.2.2 Método `_get_historical_average_volume()` (líneas 288-376) **CON FALLBACK NUEVO**

```python
FLUJO COMPLETO:

1. Intentar caché Redis (líneas 311-315)
   cache_key = f"rvol:hist:avg:{symbol}:{slot_number}"
   cached_avg = await redis.get(cache_key)
   if cached_avg: return float(cached_avg)

2. Si no hay caché, buscar en TimescaleDB (líneas 318-342)

   for days_ago in range(1, lookback_days + 1):  # 5 días
       hist_date = target_date - timedelta(days=days_ago)
       volume = await _get_volume_for_slot(symbol, hist_date, slot_number)

       if volume > 0:
           historical_volumes.append(volume)

3. NUEVO: Si no hay datos históricos → FALLBACK (líneas 344-376)

   if not historical_volumes:
       # Buscar metadata
       metadata = await redis.get(f"metadata:ticker:{symbol}")

       if metadata and metadata.get('avg_volume_30d'):
           avg_daily = metadata['avg_volume_30d']
           estimated_avg_per_slot = avg_daily / 192

           logger.info("using_fallback_avg_volume_30d")
           return estimated_avg_per_slot

       return None  # Sin datos

4. Calcular promedio (líneas 378-379)
   avg_volume = sum(historical_volumes) / len(historical_volumes)

5. Guardar en caché (líneas 381-386)
   await redis.set(cache_key, str(avg_volume), ttl=3600)
```

**POR QUÉ EL FALLBACK ES CRÍTICO**:

Antes: Sin datos históricos por slot → RVOL = None → Ticker descartado  
Ahora: Usa avg_volume_30d como estimación → RVOL calculado → Ticker procesado

**PRECISIÓN**:

- Con datos por slot: **EXACTO** (volumen acumulado del mismo slot histórico)
- Con fallback avg_30d/192: **APROXIMADO** (asume distribución uniforme)

---

## 3. SCANNER SERVICE

### 3.1 Archivo: `services/scanner/main.py`

#### 3.1.1 Discovery Loop (líneas 115-159)

```python
LOOP PRINCIPAL (cada 30 segundos):

while is_running:
    1. Actualiza market session
    2. Llama scanner_engine.run_discovery_scan()
    3. Espera 30 segundos
```

**TIMING**:

- Scanner procesa cada 30s
- Data Ingest actualiza cada 5s
- Resultado: Scanner procesa 1 de cada 6 snapshots

**¿ES ESTO UN PROBLEMA?**

❌ ANTES (con streams): SÍ - Se acumulaban 5 snapshots sin procesar  
✅ AHORA (con cache): NO - Solo importa el más reciente

---

### 3.2 Archivo: `services/scanner/scanner_engine.py`

#### 3.2.1 Método `run_discovery_scan()` (líneas 104-176)

```python
FLUJO COMPLETO DEL SCAN:

1. ACTUALIZAR SESIÓN (línea 115)
   await _update_market_session()

2. LEER SNAPSHOTS ENRIQUECIDOS (línea 118)
   enriched_snapshots = await _read_snapshots()

   RETORNA: List[(PolygonSnapshot, rvol)]

3. SI NO HAY SNAPSHOTS NUEVOS (líneas 120-122)
   if not enriched_snapshots:
       logger.debug("No new snapshots")
       return None

   PUNTO CLAVE: Si ya procesamos este snapshot, retorna vacío

4. PROCESAR SNAPSHOTS (línea 127)
   scored_tickers = await _process_snapshots_optimized(enriched_snapshots)

   RETORNA: List[ScannerTicker] filtrados y con score

5. LIMITAR RESULTADOS (líneas 129-131)
   if len(scored_tickers) > max_filtered_tickers:
       scored_tickers = scored_tickers[:max_filtered_tickers]

6. CATEGORIZAR (línea 143)
   await categorize_filtered_tickers(scored_tickers)

   GENERA: Rankings por categoría (gappers_up, winners, etc.)

7. GUARDAR RESULTADOS (línea 148)
   await _save_scan_results(scored_tickers)
```

#### 3.2.2 Método `_read_snapshots()` (líneas 180-243) **NUEVO**

```python
ANÁLISIS LÍNEA POR LÍNEA:

Línea 193-194:
    enriched_data = await redis.get("snapshot:enriched:latest")
    # Lee el snapshot COMPLETO enriquecido

Líneas 196-198:
    if not enriched_data:
        return []
    # Si Analytics aún no procesó, espera

Líneas 200-208:
    snapshot_timestamp = enriched_data.get('timestamp')

    if snapshot_timestamp == self.last_snapshot_timestamp:
        return []  # Ya procesado

    # PUNTO CRÍTICO: Evita procesar el mismo snapshot 2 veces
    # Si Scanner corre cada 30s pero Analytics actualiza cada 5s,
    # Scanner puede ver el mismo snapshot múltiples veces

Líneas 210-214:
    tickers_data = enriched_data.get('tickers', [])
    # COMPLETO: 11,905 tickers

Líneas 220-234:
    for ticker_data in tickers_data:
        snapshot = PolygonSnapshot(**ticker_data)
        rvol = ticker_data.get('rvol')
        enriched_snapshots.append((snapshot, rvol))

    # Convierte dict a tuplas (PolygonSnapshot, rvol)

Línea 237:
    self.last_snapshot_timestamp = snapshot_timestamp
    # Marca como procesado
```

**POR QUÉ ESTA IMPLEMENTACIÓN ES CORRECTA**:

✅ **Evita reprocesar**: Verifica timestamp antes de procesar  
✅ **Snapshot completo**: Procesa TODOS los 11,905 tickers  
✅ **Sincronizado**: Usa timestamp para coordinación  
✅ **Sin mezcla**: Todos del mismo momento

**PROBLEMA QUE HABÍA ANTES**:

```python
# VERSIÓN ANTERIOR (BUGGY):
streams = await redis.xread(
    streams={"snapshots:enriched": stream_position},
    count=5000  # ⚠️ PROBLEMA: Solo lee 5,000
)

# Stream tiene: [Snapshot#1: 11,905 msgs] [Snapshot#2: 11,905 msgs] [Snapshot#3...]
# Scanner lee: Mensajes 10,000-15,000
# Resultado: 5,000 del Snapshot#1 + primeros del Snapshot#2
# ❌ MEZCLA DE DATOS DE DIFERENTES MOMENTOS
```

---

#### 3.2.3 Método `_process_snapshots_optimized()` (líneas 245-338)

```python
PROCESAMIENTO EN UN SOLO BUCLE:

FASE 1: DEDUPLICACIÓN (líneas 258-267)
    unique_snapshots = []
    seen_symbols = set()

    for snapshot, rvol in enriched_snapshots:
        if snapshot.ticker not in seen_symbols:
            seen_symbols.add(snapshot.ticker)
            unique_snapshots.append((snapshot, rvol))

    # Elimina duplicados (por si Polygon envía mismo ticker 2 veces)

FASE 2: FETCH METADATAS EN BATCH (líneas 269-284)
    symbols = [s.ticker for s, r in unique_snapshots]
    keys = [f"metadata:ticker:{sym}" for sym in symbols]

    # OPTIMIZACIÓN CRÍTICA: UNA sola operación
    metadata_results = await redis.client.mget(keys)

    # Parsear resultados
    metadatas = {}
    for symbol, result in zip(symbols, metadata_results):
        if result:
            metadatas[symbol] = TickerMetadata(**result)

    # ANTES: 11,905 llamadas GET individuales
    # AHORA: 1 llamada MGET con 11,905 keys
    # Mejora: 100x más rápido

FASE 3: PROCESAMIENTO INLINE (líneas 286-329)
    for snapshot, rvol in unique_snapshots:
        symbol = snapshot.ticker

        # VALIDACIONES BÁSICAS
        if not snapshot.current_price or snapshot.current_price <= 0:
            continue

        if not snapshot.current_volume or snapshot.current_volume <= 0:
            continue

        # METADATA REQUERIDA
        metadata = metadatas.get(symbol)
        if not metadata:
            continue  # ⚠️ SIN METADATA = DESCARTADO

        # BUILD TICKER
        ticker = _build_scanner_ticker_inline(snapshot, metadata, rvol)

        # ENHANCE CON GAPS
        ticker = enhance_ticker_with_gaps(ticker, snapshot)

        # FILTRAR INMEDIATAMENTE
        if not _passes_all_filters(ticker):
            continue

        # CALCULAR SCORE
        ticker.score = _calculate_score_inline(ticker)

        filtered_and_scored.append(ticker)

FASE 4: ORDENAR Y RANKEAR (líneas 324-332)
    filtered_and_scored.sort(key=lambda t: t.score, reverse=True)

    for idx, ticker in enumerate(filtered_and_scored):
        ticker.rank = idx + 1
```

**OPTIMIZACIONES CLAVE**:

1. **Un solo bucle**: Todo en una pasada (no múltiples iteraciones)
2. **Early exit**: Si no pasa filtro, no calcula score
3. **MGET batch**: Fetch metadatas en una operación
4. **Inline**: No crea objetos intermedios innecesarios

---

#### 3.2.4 Método `_passes_all_filters()` (líneas 634-678)

```python
FILTROS APLICADOS (en orden):

1. RVOL (líneas 645-654) **MODIFICADO**

   ANTES:
   if params.min_rvol:
       if ticker.rvol is None or ticker.rvol < params.min_rvol:
           return False

   AHORA:
   if params.min_rvol is not None and ticker.rvol is not None:
       if ticker.rvol < params.min_rvol:
           return False

   CAMBIO CRÍTICO:
   - Si rvol = None (sin volumen) → NO FILTRAR
   - Antes: None < 1.5 → False → Descartado
   - Ahora: None → Skip filtro → Continúa a otros filtros

2. PRECIO (líneas 656-661)
   min_price: $1.00
   max_price: $500.00

3. VOLUMEN (líneas 663-665)
   min_volume: 100,000

4. MARKET CAP, SECTOR, EXCHANGE, etc.

CONFIGURACIÓN ACTUAL:
- rvol_high: min_rvol = 1.5, enabled = true
- price_range: $1-$500, enabled = true
- volume_min: 100,000, enabled = false (DESACTIVADO)
```

**RESULTADO CON FILTROS ACTUALES**:

De 11,905 tickers:

- ~2,190 tienen volumen > 0
- ~791 tienen RVOL calculado
- ~337 tienen RVOL >= 1.5
- **337 pasan todos los filtros**

---

### 3.3 Categorización (scanner_categories.py)

#### 3.3.1 Método `categorize_ticker()` (líneas 76-156)

```python
CATEGORIZA UN TICKER EN MÚLTIPLES LISTAS:

Un ticker puede estar en varias categorías simultáneamente.

EJEMPLO: CRBU (+204.55%, RVOL 2,493x)
  ✅ gappers_up (change >= 2%)
  ✅ winners (change >= 5%)
  ✅ anomalies (RVOL >= 3.0)
  ✅ high_volume (RVOL >= 2.0)

LÓGICA:

1. GAPPERS (líneas 87-96)
   gap = ticker.change_percent

   if gap >= 2.0:
       categories.append(GAPPERS_UP)
   elif gap <= -2.0:
       categories.append(GAPPERS_DOWN)

2. MOMENTUM (líneas 98-102)
   Solo si session == MARKET_OPEN
   if gap >= 3.0:
       categories.append(MOMENTUM_UP)

3. WINNERS/LOSERS (líneas 104-109)
   if gap >= 5.0:
       categories.append(WINNERS)
   elif gap <= -5.0:
       categories.append(LOSERS)

4. ANOMALIES (líneas 111-114)
   if rvol_slot >= 3.0:
       categories.append(ANOMALIES)

5. HIGH_VOLUME (líneas 116-118)
   if rvol >= 2.0:
       categories.append(HIGH_VOLUME)

6. NEW_HIGHS/LOWS (líneas 120-132)
   Verifica distance_from_high/low

7. REVERSALS (líneas 134-150)
   Gap en una dirección pero precio va en otra
```

#### 3.3.2 Método `get_category_rankings()` (líneas 158-217)

```python
GENERA RANKING PARA UNA CATEGORÍA:

1. FILTRAR tickers que pertenecen a la categoría (líneas 174-180)

   for ticker in tickers:  # tickers = Los 337 filtrados
       categories = categorize_ticker(ticker)
       if category in categories:
           categorized.append(ticker)

   # Ejemplo para gappers_up:
   # De 337 filtrados, ~97 tienen change >= 2%

2. ORDENAR según criterio de categoría (líneas 186-215)

   if category == GAPPERS_UP:
       # Mayor gap primero
       categorized.sort(key=lambda t: t.change_percent, reverse=True)

   elif category == ANOMALIES:
       # Mayor RVOL primero
       categorized.sort(key=lambda t: t.rvol, reverse=True)

   elif category == HIGH_VOLUME:
       # Mayor volumen absoluto primero
       categorized.sort(key=lambda t: t.volume_today, reverse=True)

3. LIMITAR A TOP N (línea 219)
   return categorized[:limit]  # Default: 20
```

**EJEMPLO REAL**:

```
gappers_up:
Input: 337 tickers filtrados
Categorizados: 97 tickers con change >= 2%
Top 20 ordenados por change%:
  1. CRBU: +204.55%
  2. MSPR: +122.64%
  ...
```

---

### 3.4 Sistema de Deltas

#### 3.4.1 Método `categorize_filtered_tickers()` (líneas 928-989)

```python
GENERA RANKINGS Y DELTAS:

1. OBTENER RANKINGS (línea 945)
   categories = categorizer.get_all_categories(tickers, limit=20)

   # Retorna:
   {
       "gappers_up": [top 20 tickers],
       "winners": [top 20 tickers],
       "anomalies": [top 20 tickers],
       ...
   }

2. PARA CADA CATEGORÍA (líneas 948-973):

   for category_name, new_ranking in categories.items():
       old_ranking = last_rankings.get(category_name, [])

       if not old_ranking:
           # Primera vez: snapshot completo
           await emit_full_snapshot(category_name, new_ranking)
       else:
           # Calcular diferencias
           deltas = calculate_ranking_deltas(old_ranking, new_ranking)

           # Emitir solo cambios
           await emit_ranking_deltas(category_name, deltas)

       # Guardar en Redis (para WebSocket)
       await _save_ranking_to_redis(category_name, new_ranking)

       # Guardar para próxima comparación
       last_rankings[category_name] = new_ranking
```

#### 3.4.2 Método `calculate_ranking_deltas()` (líneas 1085-1236)

```python
CALCULA DIFERENCIAS ENTRE RANKINGS:

old_ranking = [A, B, C, D, E]  # Iteración anterior
new_ranking = [A, C, E, F, G]  # Iteración nueva

DELTAS GENERADOS:

1. ADDS (líneas 1111-1126)
   Tickers en new pero no en old:
   - F (nuevo)
   - G (nuevo)

   Delta: {"type": "add", "ticker": F, "rank": 4}

2. REMOVES (líneas 1128-1150)
   Tickers en old pero no en new:
   - B (removido)
   - D (removido)

   Delta: {"type": "remove", "ticker": B}

3. UPDATES (líneas 1152-1191)
   Tickers en ambos con datos cambiados:
   - Si price, volume, o rvol cambió

   Delta: {"type": "update", "ticker": A, "data": {...}}

4. RERANKS (líneas 1193-1213)
   Tickers que cambiaron de posición:
   - C: rank 3 → 2
   - E: rank 5 → 3

   Delta: {"type": "rerank", "ticker": C, "old_rank": 3, "new_rank": 2}

EJEMPLO REAL:
Old: [CRBU, MSPR, RAY, SMX, LGCL]
New: [CRBU, RAY, MSPR, SMX, ETHZW]

Deltas:
- remove: LGCL
- add: ETHZW (rank 5)
- rerank: RAY (3→2), MSPR (2→3)
```

**POR QUÉ LOS DELTAS SON CRÍTICOS**:

✅ **Eficiencia**: Solo envía cambios (no 20 tickers completos cada vez)  
✅ **Bandwidth**: Delta ~1KB vs Snapshot ~50KB  
✅ **UX**: Frontend puede animar cambios suavemente

---

#### 3.4.3 Método `_save_ranking_to_redis()` (líneas 1346-1391)

```python
GUARDA SNAPSHOT DE RANKING:

Líneas 1369-1380:
    ranking_data = [t.model_dump(mode='json') for t in tickers]

    current_sequence = sequence_numbers.get(list_name, 0)

    await redis.set(
        f"scanner:category:{list_name}",
        json.dumps(ranking_data),
        ttl=3600
    )

    await redis.set(
        f"scanner:sequence:{list_name}",
        current_sequence,
        ttl=86400
    )

KEYS GUARDADOS:
- scanner:category:gappers_up → Lista completa de tickers
- scanner:sequence:gappers_up → Número de secuencia actual

USADO POR:
- WebSocket Server para enviar snapshot inicial a nuevos clientes
```

---

#### 3.4.4 Método `emit_ranking_deltas()` (líneas 1275-1333)

```python
PUBLICA DELTAS AL STREAM:

Líneas 1291-1300:
    sequence_numbers[list_name] = sequence_numbers.get(list_name, 0) + 1

    delta_message = {
        "list": list_name,
        "sequence": sequence_numbers[list_name],
        "timestamp": datetime.now().isoformat(),
        "changes": len(deltas),
        "deltas": json.dumps(deltas)
    }

Líneas 1303-1309:
    await redis.xadd(
        "stream:ranking:deltas",
        delta_message,
        maxlen=10000
    )

    # WebSocket Server consume este stream

Líneas 1312-1327:
    # Contar tipos de cambios
    adds = sum(1 for d in deltas if d['type'] == 'add')
    removes = sum(1 for d in deltas if d['type'] == 'remove')
    updates = sum(1 for d in deltas if d['type'] == 'update')
    reranks = sum(1 for d in deltas if d['type'] == 'rerank')

    logger.info("✅ Emitted ranking deltas",
                list=list_name,
                sequence=sequence_numbers[list_name],
                changes=len(deltas),
                adds=adds,
                removes=removes,
                updates=updates,
                reranks=reranks)
```

**ESTRUCTURA DEL DELTA EN STREAM**:

```json
stream:ranking:deltas mensaje:
{
  "list": "gappers_up",
  "sequence": 121,
  "timestamp": "2025-11-03T05:35:10.123Z",
  "changes": 7,
  "deltas": "[
    {\"type\": \"add\", \"ticker\": {...}, \"rank\": 15},
    {\"type\": \"remove\", \"ticker\": \"LGCL\"},
    {\"type\": \"rerank\", \"ticker\": \"RAY\", \"old_rank\": 3, \"new_rank\": 2},
    ...
  ]"
}
```

---

## 4. WEBSOCKET SERVER

### 4.1 Archivo: `services/websocket_server/src/index.js`

#### 4.1.1 Función `getInitialSnapshot()` (líneas 69-109)

```python
// Obtiene snapshot inicial para nuevo cliente

FLUJO:

1. Verificar caché en memoria (líneas 72-80)
   if (lastSnapshots.has(listName)) {
       const cached = lastSnapshots.get(listName);
       const age = Date.now() - new Date(cached.timestamp).getTime();

       if (age < 60000) {  // < 1 minuto
           return cached;  // Usar caché
       }
   }

2. Leer desde Redis (líneas 83-85)
   const key = `scanner:category:${listName}`;
   const data = await redisCommands.get(key);

   // Lee el snapshot guardado por Scanner

3. Parsear y preparar (líneas 92-104)
   const rows = JSON.parse(data);
   const sequenceKey = `scanner:sequence:${listName}`;
   const sequence = await redisCommands.get(sequenceKey);

   const snapshot = {
       type: "snapshot",
       list: listName,
       sequence: parseInt(sequence) || 0,
       timestamp: new Date().toISOString(),
       data: rows
   };

   lastSnapshots.set(listName, snapshot);  // Caché en memoria
   return snapshot;
```

#### 4.1.2 Consumer de Deltas (líneas 283-357)

```python
// Consume stream:ranking:deltas y broadcast a clientes

async function consumeRankingDeltas() {
  while (true) {
    const messages = await redis.xread(
      "BLOCK", 1000,
      "STREAMS", "stream:ranking:deltas", lastDeltaId
    );

    for (message of messages) {
      const delta = JSON.parse(message.data.deltas);

      // Broadcast a TODOS los clientes suscritos a esa lista
      broadcastDelta(message.data.list, delta, message.data.sequence);
    }
  }
}

function broadcastDelta(listName, deltas, sequence) {
  for (connection of connections.values()) {
    if (connection.subscriptions.has(listName)) {

      // Verificar sequence gaps
      const clientSeq = connection.sequence_numbers.get(listName) || 0;

      if (sequence > clientSeq + 1) {
        // GAP DETECTADO → Enviar snapshot completo
        sendSnapshot(connection, listName);
      } else {
        // Enviar delta
        ws.send(JSON.stringify({
          type: "delta",
          list: listName,
          sequence: sequence,
          changes: deltas
        }));

        connection.sequence_numbers.set(listName, sequence);
      }
    }
  }
}
```

**MANEJO DE GAPS**:

Si cliente tiene sequence 100 pero llega mensaje 103:

- Hay un gap (perdió mensajes 101, 102)
- WebSocket envía snapshot COMPLETO
- Cliente se resincroniza

---

## 5. FRONTEND

### 5.1 Archivo: `frontend/components/scanner/GappersTable.tsx`

#### 5.1.1 Manejo de Deltas (líneas 280-400)

```typescript
useEffect(() => {
  if (!lastMessage) return;

  const message = JSON.parse(lastMessage.data);

  if (message.type === "snapshot") {
    // SNAPSHOT INICIAL
    setTickers(message.data);
    setLastSequence(message.sequence);
    setIsReady(true);
  } else if (message.type === "delta") {
    // APLICAR DELTA

    // Verificar secuencia
    if (message.sequence !== lastSequence + 1) {
      // GAP → Solicitar resync
      sendJsonMessage({ action: "resync", list: selectedList });
      return;
    }

    // Aplicar cada cambio
    setTickers((prevTickers) => {
      let newTickers = [...prevTickers];

      for (const delta of message.changes) {
        if (delta.type === "add") {
          newTickers.push(delta.ticker);
        } else if (delta.type === "remove") {
          newTickers = newTickers.filter((t) => t.symbol !== delta.ticker);
        } else if (delta.type === "update") {
          const idx = newTickers.findIndex((t) => t.symbol === delta.ticker);
          if (idx >= 0) {
            newTickers[idx] = { ...newTickers[idx], ...delta.data };
          }
        } else if (delta.type === "rerank") {
          const idx = newTickers.findIndex((t) => t.symbol === delta.ticker);
          if (idx >= 0) {
            newTickers[idx].rank = delta.new_rank;
          }
        }
      }

      return newTickers;
    });

    setLastSequence(message.sequence);
  }
}, [lastMessage]);
```

---

## 🔴 PROBLEMA ANTERIOR Y SOLUCIÓN

### PROBLEMA: Mezcla de Snapshots

**ANTES (Sistema con Streams)**:

```
Tiempo: 10:00:00 - Data Ingest publica Snapshot #1
  └─ 11,905 mensajes individuales al stream "snapshots:raw"
  └─ Stream position: 0 - 11,905

Tiempo: 10:00:05 - Data Ingest publica Snapshot #2
  └─ 11,905 mensajes individuales al stream "snapshots:raw"
  └─ Stream position: 11,905 - 23,810

Tiempo: 10:00:10 - Data Ingest publica Snapshot #3
  └─ 11,905 mensajes individuales al stream "snapshots:raw"
  └─ Stream position: 23,810 - 35,715

...

Tiempo: 10:00:30 - Scanner lee:
  stream_position = 10,000 (donde se quedó)
  count = 5,000

  └─ Lee mensajes 10,000 - 15,000
  └─ Contiene: Últimos 1,905 del Snapshot #1 + Primeros 3,095 del Snapshot #2

  ❌ PROBLEMA: Mezclando datos de diferentes momentos!
      - AAPL del 10:00:00
      - TSLA del 10:00:05
      - Comparando precios de diferentes timestamps
```

**SÍNTOMAS**:

- Tickers aparecen/desaparecen aleatoriamente
- MNOV presente en una iteración, ausente en otra
- Rankings inconsistentes

---

### SOLUCIÓN: Snapshot Cache

**AHORA (Sistema con Cache)**:

```
Tiempo: 10:00:00 - Data Ingest recibe Snapshot #1
  └─ Guarda en snapshot:polygon:latest (SOBRESCRIBE)

Tiempo: 10:00:05 - Data Ingest recibe Snapshot #2
  └─ Guarda en snapshot:polygon:latest (SOBRESCRIBE)
  └─ Snapshot #1 se pierde (ya no importa)

Tiempo: 10:00:10 - Data Ingest recibe Snapshot #3
  └─ Guarda en snapshot:polygon:latest (SOBRESCRIBE)

...

Tiempo: 10:00:30 - Scanner lee:
  snapshot = redis.get("snapshot:enriched:latest")

  └─ Lee snapshot COMPLETO más reciente
  └─ Todos los 11,905 tickers del timestamp 10:00:30

  ✅ SOLUCIÓN: Todos los datos del MISMO momento!
      - AAPL, TSLA, MNOV, todos del 10:00:30
      - Comparaciones válidas
      - Rankings consistentes
```

---

## 📈 MÉTRICAS Y VERIFICACIÓN

### Estado Actual del Sistema:

```
Data Ingest:
- Frecuencia: Cada 5 segundos
- Tickers por snapshot: 11,905
- Key: snapshot:polygon:latest
- TTL: 60 segundos

Analytics:
- Procesa: Snapshot completo
- Calcula RVOL: ~791 tickers (con volumen)
- Usa fallback: avg_volume_30d / 192 slots
- Key: snapshot:enriched:latest
- TTL: 60 segundos

Scanner:
- Frecuencia: Cada 30 segundos
- Procesa: 11,905 tickers completos
- Filtra: ~337 tickers (RVOL >= 1.5)
- Categoriza: ~97 en gappers_up
- Top 20 por categoría
- Keys: scanner:category:{name}

WebSocket:
- Consume: stream:ranking:deltas
- Broadcast: Deltas incrementales
- Snapshot inicial: Desde scanner:category:{name}
- Manejo de gaps: Auto-resync

Frontend:
- Recibe: Snapshot inicial
- Aplica: Deltas incrementales
- Verifica: Sequence numbers
- Resync: Si detecta gap
```

---

## ✅ VENTAJAS DE LA ARQUITECTURA ACTUAL

1. **Sin backlog**: Cache se sobrescribe, no acumula
2. **Sin mezcla de datos**: Snapshot completo atómico
3. **Sincronización por timestamp**: Cada servicio verifica si ya procesó
4. **Eficiente**: MGET para metadatas, un solo bucle de procesamiento
5. **Robusto**: Manejo de gaps, fallbacks, TTLs apropiados
6. **Escalable**: Procesa 11,905 tickers en ~1 segundo

---

## ⚠️ PUNTOS CRÍTICOS A MONITOREAR

### 1. Metadatas en Redis

**Problema**: Se borran si warmup se ejecuta
**Solución aplicada**: Comentado el delete_pattern
**Verificación**: `redis-cli KEYS "metadata:ticker:*" | wc -l`

### 2. Datos históricos de volumen

**Problema**: RVOL = None sin datos de slots
**Solución aplicada**: Fallback a avg_volume_30d / 192
**Verificación**: Logs "using_fallback_avg_volume_30d"

### 3. Timestamp synchronization

**Problema**: Scanner podría procesar mismo snapshot 2 veces
**Solución**: last_snapshot_timestamp comparación
**Verificación**: Logs "Reading complete enriched snapshot" no se repiten

### 4. Sequence numbers

**Problema**: Frontend puede perder deltas
**Solución**: WebSocket detecta gaps y envía snapshot
**Verificación**: Frontend logs "⚠️ Sequence gap detected"

---

## 🔬 COMANDOS DE DIAGNÓSTICO

```bash
# Ver snapshot actual de Polygon
docker exec tradeul_redis redis-cli GET "snapshot:polygon:latest" | python3 -m json.tool | head -50

# Ver snapshot enriquecido
docker exec tradeul_redis redis-cli GET "snapshot:enriched:latest" | python3 -m json.tool | head -50

# Contar tickers con RVOL
docker exec tradeul_redis redis-cli GET "snapshot:enriched:latest" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len([t for t in d['tickers'] if t.get('rvol')]))"

# Ver gappers_up actual
docker exec tradeul_redis redis-cli GET "scanner:category:gappers_up" | python3 -m json.tool

# Ver metadatas cargadas
docker exec tradeul_redis redis-cli KEYS "metadata:ticker:*" | wc -l

# Ver logs de cada servicio
docker logs tradeul_data_ingest --tail 50
docker logs tradeul_analytics --tail 50
docker logs tradeul_scanner --tail 50
docker logs tradeul_websocket_server --tail 50
```

---

## 📝 PRÓXIMOS PASOS RECOMENDADOS

1. **Cargar datos históricos completos**:

   - Ejecutar load_massive_parallel.py para slots precisos
   - O esperar que el warmup cargue avg_volume_30d para todos

2. **Monitorear estabilidad**:

   - Verificar que sequence numbers avanzan sin saltos grandes
   - Confirmar que filtered_count es consistente (±5%)

3. **Optimizaciones futuras**:
   - Caché de metadatas con auto-refresh
   - Compresión de snapshots en Redis
   - Particionamiento de tickers por actividad

---

**Documento generado**: 3 Noviembre 2025  
**Sistema operacional**: ✅ Funcional y estable  
**Tickers procesados**: 11,905  
**Tickers filtrados**: 337 (RVOL >= 1.5)
