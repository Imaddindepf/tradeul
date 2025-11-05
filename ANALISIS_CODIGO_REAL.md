# Análisis de Código Real - Data Ingest, Analytics y Scanner

**Metodología**: Análisis basado SOLO en código ejecutable, sin usar comentarios ni inventar métricas.

---

## 1. DATA INGEST SERVICE

### 1.1. Entrada (De dónde obtiene datos)

**API Externa - Polygon.io**:
```python
# services/data_ingest/snapshot_consumer.py línea 29
self.base_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"

# línea 90-91
response = await client.get(self.base_url, params=params)
```

**Parámetros enviados**:
```python
# línea 86-88
params = {
    "apiKey": self.api_key,
}
```

**Sin filtros** - Pide TODOS los tickers activos de US stocks

**Respuesta de Polygon**:
```python
# línea 97-99
if "tickers" in data:
    snapshot_response = PolygonSnapshotResponse(**data)
    return snapshot_response.tickers
```

Retorna lista de objetos `PolygonSnapshot`

**Consulta a Market Session Service**:
```python
# services/data_ingest/main.py línea 99-100
session = await get_current_market_session()

if session and session != MarketSession.CLOSED:
    # Solo fetch si mercado abierto
```

### 1.2. Procesamiento

**Datos extraídos del snapshot**:
```python
# services/data_ingest/snapshot_consumer.py línea 138-150
volume_day_accumulated = snapshot.min.av if snapshot.min else 0

snapshot_data = {
    "ticker": snapshot.ticker,
    "price": snapshot.current_price,
    "volume": volume_day_accumulated,  # min.av
    "updated": snapshot.updated,
    "data": snapshot.model_dump_json()
}
```

**Campo crítico**: `volume` contiene `snapshot.min.av` (volumen acumulado del día)

### 1.3. Salida (A dónde publica)

**Redis Stream**: `snapshots:raw`
```python
# línea 152-157
await self.redis.xadd(
    settings.stream_raw_snapshots,  # "snapshots:raw"
    snapshot_data,
    maxlen=50000
)
```

**Configuración del stream**:
- Método: XADD
- Max length: 50,000 mensajes
- Cuando llega a 50K, descarta mensajes antiguos

### 1.4. Frecuencia

```python
# services/data_ingest/main.py línea 106
await asyncio.sleep(settings.snapshot_interval)  # Default: 5 segundos
```

**Si mercado abierto**: Fetch cada 5 segundos  
**Si mercado cerrado**: Sleep 60 segundos (sin fetch)

### 1.5. Sin Consumer Groups

Data Ingest es **SOLO productor**, no consume ningún stream.

---

## 2. ANALYTICS SERVICE

### 2.1. Entrada (De dónde lee)

**Redis Stream**: `snapshots:raw`
```python
# services/analytics/main.py línea 120
input_stream = settings.stream_raw_snapshots  # "snapshots:raw"

# línea 166-172
messages = await redis_client.read_stream(
    stream_name=input_stream,
    consumer_group="analytics_group",
    consumer_name="analytics_consumer_1",
    count=2000,
    block=100
)
```

**Usa consumer group**: SÍ (`analytics_group`)

**Datos que extrae**:
```python
# línea 184-198
symbol = data.get('ticker') or data.get('symbol')
volume_str = data.get('volume') or '0'
volume_accumulated = int(float(volume_str))

symbols_data[symbol] = volume_accumulated
```

**TimescaleDB - Tabla**: `volume_slots`
```python
# services/analytics/rvol_calculator.py línea 399-408
query = """
    SELECT COALESCE(SUM(volume_accumulated), 0) as total_volume
    FROM volume_slots
    WHERE symbol = $1 
      AND date = $2 
      AND slot_number <= $3
"""
result = await self.db.fetchrow(query, symbol, date, slot_number)
```

Consulta volúmenes históricos acumulados por slot.

**Caché en Redis**:
```python
# línea 311-315
cache_key = f"rvol:hist:avg:{symbol}:{slot_number}"
cached_avg = await self.redis.get(cache_key)

if cached_avg is not None:
    return float(cached_avg)  # Lee de caché si existe
```

### 2.2. Procesamiento

**Deduplicación en memoria**:
```python
# main.py línea 195-197
if symbol and volume_accumulated > 0:
    symbols_data[symbol] = volume_accumulated  # Sobrescribe duplicados
```

Si un ticker aparece múltiples veces en el batch, solo guarda el último valor.

**Actualización de volúmenes**:
```python
# línea 204-210
for symbol, volume_accumulated in symbols_data.items():
    await rvol_calculator.update_volume_for_symbol(
        symbol=symbol,
        volume_accumulated=volume_accumulated,
        timestamp=now
    )
```

Guarda en caché en memoria (VolumeSlotCache) el volumen actual de cada ticker.

**Cálculo de RVOL**:
```python
# línea 212-216
rvol_results = await rvol_calculator.calculate_rvol_batch(
    symbols=list(symbols_data.keys()),
    timestamp=now
)
```

**Dentro de calculate_rvol_batch** (rvol_calculator.py línea 275-278):
```python
for symbol in symbols:
    rvol = await self.calculate_rvol(symbol, timestamp)
    if rvol is not None:
        results[symbol] = rvol
```

**LOOP individual** - NO es batch real.

**Dentro de calculate_rvol** (línea 169-174):
```python
historical_avg = await self._get_historical_average_volume(
    symbol=symbol,
    slot_number=current_slot,
    target_date=timestamp.date()
)
```

**Dentro de _get_historical_average_volume** (línea 322-342):
```python
for days_ago in range(1, self.lookback_days + 1):  # Loop de 5 días
    volume = await self._get_volume_for_slot(...)  # Query a BD
    
    if volume == 0:
        volume = await self._find_nearest_previous_slot(...)  # Otra query
```

**Total de queries por símbolo**:
- Sin caché: hasta 10 queries (5 días × 2 queries)
- Con caché: 0 queries

**Fórmula RVOL**:
```python
# línea 185
rvol = volume_today / historical_avg
```

### 2.3. Salida (A dónde escribe)

**Redis Hash**: `rvol:current_slot`
```python
# main.py línea 227-228
await redis_client.client.hset("rvol:current_slot", mapping=rvol_mapping)
await redis_client.client.expire("rvol:current_slot", 300)
```

**Estructura**:
```
HSET rvol:current_slot
  "AAPL" "1.45"
  "TSLA" "2.34"
  ...
```

**TTL**: 300 segundos (5 minutos) - Se borra automáticamente si no se refresca

**Caché de promedios históricos**:
```python
# rvol_calculator.py línea 358-362
await self.redis.set(
    cache_key,  # "rvol:hist:avg:{symbol}:{slot}"
    str(avg_volume),
    ttl=self.hist_cache_ttl,  # 86400 = 24 horas
    serialize=False
)
```

### 2.4. Coordinación

**Consumer group con ACK**:
```python
# main.py línea 239-248
if message_ids_to_ack:
    await redis_client.client.xack(
        input_stream,
        consumer_group,
        *message_ids_to_ack
    )
```

Hace ACK de mensajes procesados.

**Loop infinito independiente**:
```python
# línea 138
while True:
    # Lee mensajes
    # Procesa
    # Hace ACK
    # Vuelve a leer
```

NO espera a otros servicios.

---

## 3. SCANNER SERVICE

### 3.1. Entrada (De dónde lee)

**Redis Stream**: `snapshots:raw`
```python
# services/scanner/scanner_engine.py línea 188-192
streams = await self.redis.xread(
    streams={settings.stream_raw_snapshots: self.stream_position},
    count=15000,
    block=100
)
```

**NO usa consumer group** - Usa XREAD simple con tracking manual:
```python
# línea 203
self.stream_position = message_id  # Actualiza posición manualmente
```

**Problema**: Si se reinicia, pierde la posición (empieza desde "0").

**Parseo de snapshot**:
```python
# línea 206-209
if 'data' in data:
    snapshot_json = data['data']
    snapshot = PolygonSnapshot.model_validate_json(snapshot_json)
    snapshots.append(snapshot)
```

Retorna lista de `PolygonSnapshot` (objeto completo de Polygon).

### 3.2. Enriquecimiento de Datos

**Por cada snapshot** (línea 235-249):
```python
for snapshot in snapshots:  # LOOP sobre todos los snapshots leídos
    # 1. Get metadata
    metadata = await self._get_ticker_metadata(snapshot.ticker)
    
    if not metadata:
        continue  # Skip si no hay metadata
    
    # 2. Build scanner ticker
    ticker = await self._build_scanner_ticker(snapshot, metadata)
    
    if ticker:
        # 3. Enhance con gaps
        ticker = self.enhance_ticker_with_gaps(ticker, snapshot)
        enriched.append(ticker)
```

**Operación 1 - Get Metadata** (línea 266-286):
```python
# Intenta Redis
key = f"metadata:ticker:{symbol}"
data = await self.redis.get(key, deserialize=True)

if data:
    return TickerMetadata(**data)

# Fallback a BD
row = await self.db.get_ticker_metadata(symbol)

if row:
    metadata = TickerMetadata(**dict(row))
    # Guarda en caché
    await self.redis.set(key, metadata.model_dump(mode='json'), ttl=3600)
    return metadata
```

**Por cada ticker sin caché**: 1 query a TimescaleDB + 1 SET a Redis

**Operación 2 - Build Scanner Ticker** (línea 307-309):
```python
# Get RVOL from Analytics
rvol = await self._get_rvol_from_analytics(snapshot.ticker)
rvol_slot = rvol
```

**Lee de Analytics** (línea 380-382):
```python
rvol_str = await self.redis.hget("rvol:current_slot", symbol)
if rvol_str:
    return float(rvol_str)
```

**Un HGET por ticker** al hash de Analytics.

**Operación 3 - Enhance Gaps** (línea 809-831):
```python
gaps = self.gap_calculator.calculate_all_gaps(ticker, snapshot)

ticker.metadata.update({
    'gaps': gaps,
    'gap_size_classification': ...,
    'gap_metrics': ...
})

self.gap_tracker.track_gap(...)
```

Solo cálculos en memoria, sin I/O.

### 3.3. Filtrado

```python
# línea 393-427
filtered = []

for ticker in tickers:
    passed = True
    matched_filters = []
    
    for filter_config in self.filters:
        if not filter_config.enabled:
            continue
        
        if self._apply_single_filter(ticker, filter_config):
            matched_filters.append(filter_config.name)
        else:
            passed = False
            break
    
    if passed and matched_filters:
        ticker.filters_matched = matched_filters
        filtered.append(ticker)
```

**Filtros evaluados** (línea 438-490):
- `min_rvol` / `max_rvol`
- `min_price` / `max_price`
- `min_volume`
- `min_change_percent` / `max_change_percent`
- `min_market_cap` / `max_market_cap`
- `sectors` / `industries` / `exchanges`

**RVOL usado para filtrar** (línea 439-445):
```python
if params.min_rvol is not None:
    if ticker.rvol is None or ticker.rvol < params.min_rvol:
        return False  # Rechaza el ticker
```

### 3.4. Scoring y Ranking

```python
# línea 507-535
# Deduplicar
seen = set()
unique_tickers = []
for ticker in tickers:
    if ticker.symbol not in seen:
        seen.add(ticker.symbol)
        unique_tickers.append(ticker)

# Calcular score
for ticker in unique_tickers:
    score = 0.0
    
    if ticker.rvol:
        score += ticker.rvol * 10  # RVOL contribuye al score
    
    if ticker.volume_today and ticker.avg_volume_30d:
        volume_ratio = ticker.volume_today / ticker.avg_volume_30d
        score += volume_ratio * 5
    
    ticker.score = score

# Ordenar por score
unique_tickers.sort(key=lambda t: t.score, reverse=True)

# Asignar ranks
for idx, ticker in enumerate(unique_tickers):
    ticker.rank = idx + 1
```

**RVOL usado para scoring**: Peso de 10x

### 3.5. Limitación

```python
# línea 133-135
if len(scored_tickers) > settings.max_filtered_tickers:
    scored_tickers = scored_tickers[:settings.max_filtered_tickers]
```

`settings.max_filtered_tickers = 200` (recién cambiado de 1000)

### 3.6. Categorización

```python
# línea 709
categories = self.categorizer.get_all_categories(tickers, limit_per_category=20)
```

**En categorizer** (scanner_categories.py línea 226-230):
```python
for category in ScannerCategory:
    ranked = self.get_category_rankings(tickers, category, limit_per_category)
    
    if ranked:
        results[category.value] = ranked
```

**Categorías evaluadas** (línea 23-35):
- GAPPERS_UP / GAPPERS_DOWN
- MOMENTUM_UP / MOMENTUM_DOWN
- ANOMALIES
- NEW_HIGHS / NEW_LOWS
- LOSERS / WINNERS
- HIGH_VOLUME
- REVERSALS

**RVOL usado en categorías** (línea 112-122):
```python
# ANOMALIES
if ticker.rvol_slot >= 3.0:
    categories.append(ScannerCategory.ANOMALIES)

# HIGH_VOLUME
if rvol >= 2.0:
    categories.append(ScannerCategory.HIGH_VOLUME)
```

**Ordenamiento por categoría** (línea 191-193):
```python
elif category == ScannerCategory.ANOMALIES:
    categorized.sort(key=lambda t: t.rvol_slot or t.rvol or 0, reverse=True)
```

### 3.7. Salidas (A dónde escribe)

**Salida 1 - Stream**: `stream:ranking:deltas`
```python
# scanner_engine.py línea 1084-1087
await self.redis.xadd(
    settings.stream_ranking_deltas,  # "stream:ranking:deltas"
    message
)
```

Publica snapshots y deltas de cada categoría.

**Salida 2 - Redis Keys**: Rankings por categoría
```python
# línea 1133-1137
await self.redis.set(
    f"scanner:category:{list_name}",
    json.dumps(ranking_data),
    ttl=3600
)
```

**Salida 3 - Stream**: `tickers:filtered`
```python
# línea 581-593
for ticker in tickers:  # Loop de todos los filtrados
    await self.redis.xadd(
        settings.stream_filtered_tickers,  # "tickers:filtered"
        {
            "symbol": ticker.symbol,
            "price": ticker.price,
            "volume_accumulated": ticker.volume_today,
            "vwap": ticker.price,
            "rvol": ticker.rvol or 0,
            "score": ticker.score,
            "data": ticker.model_dump_json()
        },
        maxlen=10000
    )
```

**Pregunta**: ¿Quién consume `tickers:filtered`? Verificado: NADIE (stream huérfano)

**Salida 4 - Sorted Set**: Rankings
```python
# línea 597-601
mapping = {ticker.symbol: ticker.score for ticker in tickers}
await self.redis.zadd(
    f"scanner:filtered:{self.current_session.value}",
    mapping
)
```

**Salida 5 - TimescaleDB**: `scan_results`
```python
# línea 611-634
for ticker in tickers:  # LOOP individual
    scan_data = {...}
    await self.db.insert_scan_result(scan_data)  # INSERT individual
```

**Sin batch** - Un INSERT por ticker.

### 3.8. Frecuencia

```python
# services/scanner/main.py línea 152
await asyncio.sleep(30)  # Discovery loop cada 30 segundos
```

**Hot loop** (línea 184):
```python
await asyncio.sleep(1)  # Pero NO ESTÁ IMPLEMENTADO (solo sleep)
```

### 3.9. Sin Consumer Group

```python
# scanner_engine.py línea 188
streams = await self.redis.xread(...)  # XREAD simple, NO XREADGROUP
```

NO usa consumer group - tracking manual de posición.

---

## 4. RELACIONES ENTRE SERVICIOS

### 4.1. Data Ingest → Analytics

```
Data Ingest
   ↓ XADD
snapshots:raw (stream)
   ↓ XREADGROUP
Analytics
```

**Conexión**: Asíncrona via stream  
**Consumer group**: analytics_group  
**Acoplamiento**: Débil

### 4.2. Data Ingest → Scanner

```
Data Ingest
   ↓ XADD
snapshots:raw (stream)
   ↓ XREAD (sin consumer group)
Scanner
```

**Conexión**: Asíncrona via stream  
**Consumer group**: NO (usa tracking manual)  
**Acoplamiento**: Débil

**Problema**: Analytics y Scanner leen del MISMO stream pero Scanner no usa consumer group. Ambos reciben los mismos mensajes.

### 4.3. Analytics → Scanner

```
Analytics
   ↓ HSET
rvol:current_slot (hash)
   ↓ HGET (por cada ticker)
Scanner
```

**Conexión**: Caché compartido  
**Acoplamiento**: Muy débil  
**Problema potencial**: Scanner lee RVOL mientras procesa snapshot antiguo (desincronización temporal)

### 4.4. Scanner → WebSocket Server

```
Scanner
   ↓ XADD
stream:ranking:deltas
   ↓ XREADGROUP
WebSocket Server
```

**Conexión**: Asíncrona via stream  
**Consumer group**: websocket_server_deltas  
**Acoplamiento**: Débil

### 4.5. Scanner → ??? (stream huérfano)

```
Scanner
   ↓ XADD
tickers:filtered (stream)
   ↓ ???
NADIE (huérfano)
```

**Problema**: Scanner publica a `tickers:filtered` pero ningún servicio lo consume. Desperdicio de recursos.

---

## 5. CUELLOS DE BOTELLA IDENTIFICADOS (Solo Código)

### 5.1. Scanner - Operaciones Individuales a Redis

**Metadata** (1 GET por ticker):
```python
for snapshot in snapshots:  # 15,000 iteraciones
    metadata = await self._get_ticker_metadata(snapshot.ticker)  # GET
```

**RVOL** (1 HGET por ticker):
```python
for snapshot in snapshots:  # 15,000 iteraciones
    rvol = await self._get_rvol_from_analytics(snapshot.ticker)  # HGET
```

**Total**: 30,000 operaciones individuales a Redis

**Solución**: Pipelining o MGET/HMGET

### 5.2. Scanner - INSERTs Individuales a BD

```python
for ticker in tickers:  # 1,000 iteraciones
    await self.db.insert_scan_result(scan_data)  # INSERT individual
```

**Sin batch** - 1,000 queries individuales.

**Solución**: `executemany()` para batch insert

### 5.3. Scanner - Stream Huérfano

```python
# Publica a tickers:filtered
for ticker in tickers:  # 1,000 iteraciones
    await self.redis.xadd(settings.stream_filtered_tickers, ...)
```

**Nadie consume este stream** - Desperdicio.

**Solución**: Eliminar esta publicación o encontrar quién debería consumirlo

### 5.4. Scanner - Sin Consumer Group

```python
streams = await self.redis.xread(...)  # NO XREADGROUP
```

**Problemas**:
- Sin ACK
- Sin persistencia de posición
- Puede re-procesar mensajes
- Se pierde posición al reiniciar

**Solución**: Usar XREADGROUP como Analytics

### 5.5. Analytics - Queries Individuales en Loop

```python
# rvol_calculator.py línea 275-278
for symbol in symbols:  # LOOP
    rvol = await self.calculate_rvol(symbol)  # Dentro hace queries a BD
```

**Dentro** hace hasta 10 queries por símbolo (con caché frío).

**Solución**: Una query SQL con `WHERE symbol = ANY($1)` para batch real

### 5.6. Analytics - Stream Definido Pero No Usado

```python
# main.py línea 125 (ELIMINADO en mis cambios)
output_stream = "stream:analytics:rvol"  # Nunca se usa
```

Ya lo eliminé.

---

## 6. LÓGICA QUE NO CORRESPONDE

### Analytics: CORRECTO

- Calcula RVOL (indicador técnico genérico)
- NO filtra ni rankea
- Solo provee datos

### Scanner: CORRECTO

- NO calcula RVOL (lo obtiene de Analytics)
- SÍ calcula gaps (lógica de negocio del scanner)
- SÍ filtra y rankea (su propósito)

**Separación de responsabilidades es correcta**.

---

## 7. PROBLEMA DE ASINCRONÍA

**Código revela**:

```python
# Scanner lee snapshot antiguo (lag 50K)
snapshot = ... # De hace X tiempo

# Scanner lee RVOL actual
rvol = await self._get_rvol_from_analytics(snapshot.ticker)

# Construye ticker mezclando tiempos
ticker = ScannerTicker(
    price=snapshot.price,  # Tiempo T-X
    rvol=rvol,            # Tiempo T (actual)
)
```

**Desincronización temporal**: Datos no corresponden al mismo momento.

**Causa**: Scanner usa XREAD (no consumer group) y procesa lento, se atrasa.

---

## 8. RESUMEN DE CAMBIOS IMPLEMENTADOS

Verificables en el código:

1. `services/websocket_server/src/index.js`:
   - Línea 394-405: XREADGROUP con BLOCK 100
   - Línea 428: ACK de mensajes
   - Consumer groups: websocket_server_deltas, websocket_server_aggregates, websocket_server_rvol

2. `services/analytics/main.py`:
   - Línea 170: count=2000, block=100
   - Línea 239-248: ACK de mensajes
   - Código muerto eliminado

3. `shared/config/settings.py`:
   - Línea 134: max_filtered_tickers=200

4. `services/scanner/main.py`:
   - Línea 443: limit=20

**NO implementé**: Consumer group en Scanner (pendiente)

---

## 9. OPTIMIZACIONES IMPLEMENTADAS

### Stream Enriquecido (IMPLEMENTADO)

**Analytics ahora RE-PUBLICA** snapshots enriquecidos con RVOL:

```python
# services/analytics/main.py línea 230-256
for message_id, original_data in stream_messages:
    symbol = original_data.get('ticker')
    
    if symbol and symbol in rvol_results:
        enriched_data = {
            **original_data,  # Datos originales
            'rvol': str(round(rvol_results[symbol], 2))  # RVOL añadido
        }
        
        await redis_client.client.xadd(
            "snapshots:enriched",
            enriched_data,
            maxlen=50000
        )
```

**Nuevo flujo**:
```
Data Ingest → snapshots:raw → Analytics → snapshots:enriched → Scanner
```

**Scanner ahora lee de** `snapshots:enriched`:

```python
# services/scanner/scanner_engine.py línea 188-189
streams = await self.redis.xread(
    streams={"snapshots:enriched": self.stream_position},
    count=5000,  # Reducido de 15K a 5K
    ...
)
```

**Scanner extrae RVOL del stream**:

```python
# línea 206-208
if symbol and 'rvol' in data:
    self.enriched_data[symbol] = float(data['rvol'])
```

**Scanner ya NO hace HGET por cada ticker**:

```python
# línea 385-386
if symbol in self.enriched_data:
    return self.enriched_data[symbol]  # ← Lectura de memoria, no Redis
```

**Mejora**: 15,000 HGETs → 0 HGETs

### Discovery Loop más frecuente (IMPLEMENTADO)

```python
# services/scanner/main.py línea 152
await asyncio.sleep(10)  # Cambiado de 30 a 10 segundos
```

**Mejora**: Rankings actualizados cada 10 seg (en vez de 30)

### Batch Size Reducido (IMPLEMENTADO)

```python
# scanner_engine.py línea 190
count=5000,  # Reducido de 15,000 a 5,000
```

**Mejora**: Menos lag, procesa más frecuente

---

## 10. OPTIMIZACIONES PENDIENTES

### Prioridad Alta:

1. **Scanner - Consumer Group** (eliminar tracking manual)
2. **Scanner - Batch GET para metadata** (pipelining)
3. **Scanner - Batch INSERT a BD** (`executemany()`)
4. **Eliminar stream `tickers:filtered`** (huérfano)

### Prioridad Media:

5. **Analytics - Batch queries SQL real** (reescribir `calculate_rvol_batch()`)

---

**Análisis basado en código ejecutable. Optimizaciones implementadas verificables en el código.**
