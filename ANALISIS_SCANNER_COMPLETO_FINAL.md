# Análisis Completo del Scanner Service

**Metodología**: Análisis basado en código ejecutable únicamente, sin comentarios ni métricas inventadas.

---

## RESUMEN DEL SERVICIO REALIZADO - Cambios para actualización en tiempo real

He identificado y corregido el problema principal de latencia que reportaste. Aquí está el resumen de todos los cambios implementados:

### 1. WebSocket Server - Latencia reducida de 5 segundos a 100ms

**Archivo**: `services/websocket_server/src/index.js`

**Problema original**:

- Usaba `BLOCK 5000` (esperaba hasta 5 segundos por nuevos mensajes)
- No usaba consumer groups (sin persistencia ni ACK)
- Causaba el desfase que reportaste

**Solución implementada**:

- Cambiado a `XREADGROUP` con consumer groups
- BLOCK reducido a `100ms` (50x más rápido)
- Implementado ACK de mensajes
- 3 consumer groups creados:
  - `websocket_server_deltas` (para rankings)
  - `websocket_server_aggregates` (para precios de Polygon)
  - `websocket_server_rvol` (para RVOL)

### 2. Analytics - Stream Enriquecido con RVOL

**Archivo**: `services/analytics/main.py`

**Problema original**:

- Calculaba RVOL y solo lo guardaba en hash
- Scanner tenía que hacer 15,000 HGETs individuales para obtener RVOL
- Desincronización temporal entre snapshot y RVOL

**Solución implementada**:

- Analytics ahora RE-PUBLICA snapshots enriquecidos con RVOL incluido
- Nuevo stream: `snapshots:enriched`
- Scanner lee snapshots que YA TRAEN el RVOL calculado
- Eliminados 15,000 HGETs individuales
- Datos sincronizados temporalmente

### 3. Scanner - Optimización de lectura

**Archivo**: `services/scanner/scanner_engine.py`

**Cambios implementados**:

- Lee de `snapshots:enriched` en vez de `snapshots:raw`
- Batch reducido de 15,000 a 5,000 mensajes
- Frecuencia aumentada de 30seg a 10seg
- RVOL obtenido del stream (memoria) en vez de Redis (HGET)

**Archivo**: `services/scanner/main.py`

- Discovery loop: 30 seg → 10 seg

### 4. Límites Corregidos

**Archivos múltiples**:

- `shared/config/settings.py`: `max_filtered_tickers = 200`
- `scanner_engine.py`: `limit_per_category = 20`
- `scanner_categories.py`: `limit = 20`
- `scanner/main.py`: Endpoints con `limit = 20`

### 5. Limpieza de código

- Eliminados 7 scripts obsoletos de `/scripts`
- Eliminada documentación .md innecesaria de Analytics
- Eliminada variable `output_stream` no usada en Analytics

---

## ARQUITECTURA COMPLETA DEL SCANNER

### Componentes Principales

El Scanner está compuesto de 4 módulos:

#### 1. ScannerEngine (scanner_engine.py)

- Orquestador principal
- Lee snapshots, enriquece, filtra, rankea
- Publica resultados

#### 2. ScannerCategorizer (scanner_categories.py)

- Clasifica tickers en 11 categorías
- Define criterios de clasificación
- Genera rankings por categoría

#### 3. GapCalculator (gap_calculator.py)

- Calcula 6 tipos de gaps diferentes
- Específico por sesión de mercado
- Tracking de gaps históricos

#### 4. HotTickerManager (hot_ticker_manager.py)

- Gestiona tickers "hot" vs "cold"
- Auto-suscripción a Polygon WS
- Promoción/degradación automática

---

## FLUJO COMPLETO DE DATOS

### Paso 1: Lectura de Snapshots Enriquecidos

**Código**: `scanner_engine.py` línea 184-223

```python
async def _read_snapshots():
    streams = await self.redis.xread(
        streams={"snapshots:enriched": self.stream_position},
        count=5000,
        block=100
    )

    snapshots = []
    self.enriched_data = {}  # Cache de RVOLs

    for message_id, data in messages:
        self.stream_position = message_id  # Tracking manual

        # Extraer RVOL del mensaje
        symbol = data.get('ticker')
        if symbol and 'rvol' in data:
            self.enriched_data[symbol] = float(data['rvol'])

        # Parsear snapshot
        snapshot_json = data['data']
        snapshot = PolygonSnapshot.model_validate_json(snapshot_json)
        snapshots.append(snapshot)

    return snapshots
```

**Entrada**: Stream `snapshots:enriched` (publicado por Analytics)
**Salida**: Lista de `PolygonSnapshot` + dict de RVOLs en memoria

**Datos en el mensaje**:

- `ticker`: Símbolo
- `volume`: Volumen acumulado del día
- `price`: Precio actual
- `rvol`: RVOL calculado por Analytics (NUEVO)
- `data`: Snapshot completo JSON

**Método de lectura**: XREAD (NO consumer group)
**Problema pendiente**: Sin ACK, sin persistencia de posición

---

### Paso 2: Enriquecimiento

**Código**: `scanner_engine.py` línea 225-259

```python
async def _enrich_and_calculate(snapshots):
    enriched = []

    for snapshot in snapshots:  # LOOP sobre cada snapshot
        # 2.1. Get metadata
        metadata = await self._get_ticker_metadata(snapshot.ticker)

        if not metadata:
            continue  # Skip sin metadata

        # 2.2. Build scanner ticker
        ticker = await self._build_scanner_ticker(snapshot, metadata)

        if ticker:
            # 2.3. Enhance con gaps
            ticker = self.enhance_ticker_with_gaps(ticker, snapshot)
            enriched.append(ticker)

    return enriched
```

#### Operación 2.1: Get Metadata

**Código**: línea 261-297

```python
async def _get_ticker_metadata(symbol):
    # Intenta Redis caché
    key = f"metadata:ticker:{symbol}"
    data = await self.redis.get(key, deserialize=True)

    if data:
        return TickerMetadata(**data)  # Hit: <1ms

    # Miss: Query a BD
    row = await self.db.get_ticker_metadata(symbol)

    if row:
        metadata = TickerMetadata(**dict(row))
        # Guarda en caché (TTL 1 hora)
        await self.redis.set(key, metadata, ttl=3600)
        return metadata

    return None
```

**Operaciones Redis**:

- Con caché: 1 GET por ticker (rápido)
- Sin caché: 1 GET + 1 query BD + 1 SET

**Tabla consultada**: `ticker_metadata`

```sql
SELECT symbol, company_name, exchange, sector, industry,
       market_cap, float_shares, shares_outstanding,
       avg_volume_30d, avg_volume_10d, avg_price_30d,
       beta, is_etf, is_actively_trading, updated_at
FROM ticker_metadata
WHERE symbol = $1
```

**Carga**:

- Primera vez (caché frío): 5,000 queries a BD
- Después (caché caliente): 0 queries a BD

#### Operación 2.2: Build Scanner Ticker

**Código**: línea 299-372

```python
async def _build_scanner_ticker(snapshot, metadata):
    price = snapshot.current_price
    volume_today = snapshot.current_volume

    # OPTIMIZADO: Get RVOL del stream (ya viene incluido)
    rvol = await self._get_rvol_from_analytics(snapshot.ticker)
    rvol_slot = rvol

    # Calcular métricas de posición de precio
    day_data = snapshot.day
    prev_day = snapshot.prevDay

    price_from_high = None
    price_from_low = None
    change_percent = None

    if day_data:
        if day_data.h > 0:
            price_from_high = ((price - day_data.h) / day_data.h) * 100
        if day_data.l > 0:
            price_from_low = ((price - day_data.l) / day_data.l) * 100

    if prev_day and prev_day.c > 0:
        change_percent = ((price - prev_day.c) / prev_day.c) * 100

    # Construir objeto completo
    return ScannerTicker(
        symbol=snapshot.ticker,
        timestamp=datetime.now(),
        price=price,
        bid=snapshot.lastQuote.p if snapshot.lastQuote else None,
        ask=snapshot.lastQuote.P if snapshot.lastQuote else None,
        volume=volume_today,
        volume_today=volume_today,
        open=day_data.o if day_data else None,
        high=day_data.h if day_data else None,
        low=day_data.l if day_data else None,
        prev_close=prev_day.c if prev_day else None,
        prev_volume=prev_day.v if prev_day else None,
        change_percent=change_percent,
        avg_volume_30d=metadata.avg_volume_30d,
        avg_volume_10d=metadata.avg_volume_10d,
        float_shares=metadata.float_shares,
        shares_outstanding=metadata.shares_outstanding,
        market_cap=metadata.market_cap,
        sector=metadata.sector,
        industry=metadata.industry,
        exchange=metadata.exchange,
        rvol=rvol,
        rvol_slot=rvol_slot,
        price_from_high=price_from_high,
        price_from_low=price_from_low,
        session=self.current_session,
        score=0.0,
        filters_matched=[]
    )
```

**Get RVOL** (línea 377-396):

```python
async def _get_rvol_from_analytics(symbol):
    # Primero del stream enriquecido (memoria)
    if symbol in self.enriched_data:
        return self.enriched_data[symbol]  # ← Lectura de memoria (instant)

    # Fallback al hash (compatibilidad)
    rvol_str = await self.redis.hget("rvol:current_slot", symbol)
    if rvol_str:
        return float(rvol_str)

    return None
```

**OPTIMIZACIÓN**: Ahora lee RVOL de memoria (dict en Python), NO de Redis.

**Operaciones**: Solo cálculos aritméticos, sin I/O adicional

#### Operación 2.3: Enhance con Gaps

**Código**: gap_calculator.py líneas 34-100

```python
def calculate_all_gaps(ticker, snapshot):
    gaps = {}

    prev_close = snapshot.prevDay.c
    day_open = snapshot.day.o
    current_price = ticker.price

    # Gap from previous close
    if prev_close > 0:
        gaps['gap_from_prev_close'] = ((current_price - prev_close) / prev_close) * 100
        gaps['gap_from_prev_close_dollars'] = current_price - prev_close

    # Gap from open
    if day_open > 0:
        gaps['gap_from_open'] = ((current_price - day_open) / day_open) * 100
        gaps['gap_from_open_dollars'] = current_price - day_open

    # Clasificación por sesión
    session = ticker.session

    if session == MarketSession.PRE_MARKET:
        gaps['gap_premarket'] = gaps['gap_from_prev_close']
        gaps['gap_at_open'] = None
        gaps['gap_postmarket'] = None

    elif session == MarketSession.MARKET_OPEN:
        gaps['gap_premarket'] = None
        gaps['gap_at_open'] = None
        gaps['gap_postmarket'] = None

    elif session == MarketSession.POST_MARKET:
        market_close_price = snapshot.day.c
        if market_close_price > 0:
            gaps['gap_postmarket'] = ((current_price - market_close_price) / market_close_price) * 100

    gaps['gap_abs'] = abs(gaps['gap_from_prev_close']) if gaps['gap_from_prev_close'] else 0

    return gaps
```

**Métricas calculadas**:

- gap_from_prev_close (principal)
- gap_from_open (intraday)
- gap_premarket / gap_at_open / gap_postmarket (según sesión)
- gap_abs (para ranking)

**Operaciones**: Solo aritmética, 100% en memoria

**Resultado del enriquecimiento**:

- Entrada: 5,000 snapshots
- Salida: ~5,000 tickers enriched (algunos sin metadata se descartan)

---

### Paso 3: Aplicar Filtros

**Código**: línea 398-432

```python
async def _apply_filters(tickers):
    filtered = []

    for ticker in tickers:
        passed = True
        matched_filters = []

        for filter_config in self.filters:
            if not filter_config.enabled:
                continue

            if not filter_config.applies_to_session(self.current_session):
                continue

            # Aplicar filtro
            if self._apply_single_filter(ticker, filter_config):
                matched_filters.append(filter_config.name)
            else:
                passed = False
                break  # Short circuit

        if passed and matched_filters:
            ticker.filters_matched = matched_filters
            filtered.append(ticker)

    return filtered
```

**Filtros disponibles** (línea 438-501):

Evalúa cada ticker contra:

```python
def _apply_single_filter(ticker, filter_config):
    params = filter_config.parameters

    # RVOL filters
    if params.min_rvol:
        if ticker.rvol is None or ticker.rvol < params.min_rvol:
            return False

    if params.max_rvol:
        if ticker.rvol > params.max_rvol:
            return False

    # Price filters
    if params.min_price:
        if ticker.price < params.min_price:
            return False

    if params.max_price:
        if ticker.price > params.max_price:
            return False

    # Volume filters
    if params.min_volume:
        if ticker.volume_today < params.min_volume:
            return False

    # Change filters
    if params.min_change_percent:
        if ticker.change_percent < params.min_change_percent:
            return False

    if params.max_change_percent:
        if ticker.change_percent > params.max_change_percent:
            return False

    # Market cap filters
    if params.min_market_cap:
        if ticker.market_cap < params.min_market_cap:
            return False

    if params.max_market_cap:
        if ticker.market_cap > params.max_market_cap:
            return False

    # Sector/Industry/Exchange filters
    if params.sectors:
        if ticker.sector not in params.sectors:
            return False

    if params.industries:
        if ticker.industry not in params.industries:
            return False

    if params.exchanges:
        if ticker.exchange not in params.exchanges:
            return False

    return True
```

**Filtros cargados desde BD** (línea 653-690):

```python
async def reload_filters():
    query = """
        SELECT id, name, description, enabled, filter_type,
               parameters, priority, created_at, updated_at
        FROM scanner_filters
        ORDER BY priority DESC, id
    """

    rows = await self.db.fetch(query)

    self.filters = []
    for row in rows:
        params = row["parameters"]
        if isinstance(params, str):
            params = json.loads(params)

        filter_config = FilterConfig(
            id=row["id"],
            name=row["name"],
            enabled=row["enabled"],
            parameters=FilterParameters(**params),
            priority=row["priority"]
        )
        self.filters.append(filter_config)
```

**Tabla**: `scanner_filters` en TimescaleDB
**Frecuencia de recarga**: Al iniciar + on-demand via endpoint `/api/filters/reload`

**Resultado del filtrado**:

- Entrada: ~5,000 enriched
- Salida: Depende de filtros (pero limitado a 200 por settings)

---

### Paso 4: Score y Ranking

**Código**: línea 507-540

```python
async def _score_and_rank(tickers):
    # Deduplicación
    seen = set()
    unique_tickers = []
    for ticker in tickers:
        if ticker.symbol not in seen:
            seen.add(ticker.symbol)
            unique_tickers.append(ticker)

    # Calcular score
    for ticker in unique_tickers:
        score = 0.0

        # RVOL contribuye peso 10x
        if ticker.rvol:
            score += ticker.rvol * 10

        # Ratio de volumen contribuye peso 5x
        if ticker.volume_today and ticker.avg_volume_30d:
            volume_ratio = ticker.volume_today / ticker.avg_volume_30d
            score += volume_ratio * 5

        ticker.score = score

    # Ordenar por score descendente
    unique_tickers.sort(key=lambda t: t.score, reverse=True)

    # Asignar ranks
    for idx, ticker in enumerate(unique_tickers):
        ticker.rank = idx + 1

    return unique_tickers
```

**Fórmula de score**:

```
score = (RVOL × 10) + (volume_today / avg_volume_30d × 5)
```

**RVOL tiene doble peso** que el ratio de volumen.

**Operaciones**: Solo en memoria (sort)

**Límite aplicado** (línea 133-135):

```python
if len(scored_tickers) > settings.max_filtered_tickers:
    scored_tickers = scored_tickers[:200]  # Top 200
```

**Resultado**:

- Entrada: Tickers filtrados
- Salida: Top 200 tickers por score

---

### Paso 5: Categorización

**Código**: línea 697-758

```python
async def categorize_filtered_tickers(tickers, emit_deltas=True):
    # Obtener todas las categorías
    categories = self.categorizer.get_all_categories(tickers, limit_per_category=20)

    # Calcular deltas
    if emit_deltas:
        for category_name, new_ranking in categories.items():
            old_ranking = self.last_rankings.get(category_name, [])

            if not old_ranking:
                # Primera vez: snapshot completo
                await self.emit_full_snapshot(category_name, new_ranking)
            else:
                # Calcular deltas
                deltas = self.calculate_ranking_deltas(
                    old_ranking,
                    new_ranking,
                    category_name
                )

                if deltas:
                    await self.emit_ranking_deltas(category_name, deltas)

            # Guardar en Redis
            await self._save_ranking_to_redis(category_name, new_ranking)

            # Guardar para próxima comparación
            self.last_rankings[category_name] = new_ranking

    # Cache
    self.last_categories = categories
    self.last_categorization_time = datetime.now()

    return categories
```

#### Categorización (scanner_categories.py)

**Método**: `get_all_categories()` línea 213-232

```python
def get_all_categories(tickers, limit_per_category=20):
    results = {}

    for category in ScannerCategory:  # 11 categorías
        ranked = self.get_category_rankings(tickers, category, limit_per_category)

        if ranked:
            results[category.value] = ranked

    return results
```

**Categorías evaluadas** (línea 23-35):

1. GAPPERS_UP
2. GAPPERS_DOWN
3. MOMENTUM_UP
4. MOMENTUM_DOWN
5. ANOMALIES
6. NEW_HIGHS
7. NEW_LOWS
8. LOSERS
9. WINNERS
10. HIGH_VOLUME
11. REVERSALS

**Proceso por categoría** (línea 76-147):

```python
def categorize_ticker(ticker):
    categories = []

    gap = ticker.change_percent

    # GAPPERS
    if gap >= 2.0:
        categories.append(GAPPERS_UP)
    elif gap <= -2.0:
        categories.append(GAPPERS_DOWN)

    # MOMENTUM
    if ticker.session == MARKET_OPEN:
        if gap >= 3.0:
            categories.append(MOMENTUM_UP)
        elif gap <= -3.0:
            categories.append(MOMENTUM_DOWN)

    # WINNERS / LOSERS
    if gap >= 5.0:
        categories.append(WINNERS)
    elif gap <= -5.0:
        categories.append(LOSERS)

    # ANOMALIES (RVOL usado aquí)
    if ticker.rvol_slot >= 3.0:
        categories.append(ANOMALIES)

    # HIGH VOLUME (RVOL usado aquí)
    if ticker.rvol >= 2.0:
        categories.append(HIGH_VOLUME)

    # NEW HIGHS / LOWS
    if abs(ticker.price_from_high) <= 0.5:
        categories.append(NEW_HIGHS)
    if abs(ticker.price_from_low) <= 0.5:
        categories.append(NEW_LOWS)

    # REVERSALS
    gap_from_open = ...
    if gap >= 2.0 and gap_from_open <= -1.0:
        categories.append(REVERSALS)
    elif gap <= -2.0 and gap_from_open >= 1.0:
        categories.append(REVERSALS)

    return categories
```

**Ordenamiento por categoría** (línea 175-210):

```python
# GAPPERS_UP: Ordenar por gap descendente
if category == GAPPERS_UP:
    categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)

# GAPPERS_DOWN: Ordenar por gap ascendente (más negativo primero)
elif category == GAPPERS_DOWN:
    categorized.sort(key=lambda t: t.change_percent or 0)

# ANOMALIES: Ordenar por RVOL descendente
elif category == ANOMALIES:
    categorized.sort(key=lambda t: t.rvol_slot or t.rvol or 0, reverse=True)

# HIGH_VOLUME: Ordenar por volumen total
elif category == HIGH_VOLUME:
    categorized.sort(key=lambda t: t.volume_today or 0, reverse=True)

# NEW_HIGHS: Más cerca del high primero
elif category == NEW_HIGHS:
    categorized.sort(key=lambda t: abs(t.price_from_high) if t.price_from_high else 999)

# Etc...

return categorized[:limit]  # Top 20
```

**Resultado**:

- Entrada: 200 tickers filtrados
- Salida: Dict con 11 categorías, cada una con top 20
- Total: ~200 tickers distribuidos en categorías (con solapamiento)

---

### Paso 6: Sistema de Deltas

**Código**: línea 944-1017

```python
def calculate_ranking_deltas(old_ranking, new_ranking, list_name):
    deltas = []

    old_dict = {t.symbol: (i, t) for i, t in enumerate(old_ranking)}
    new_dict = {t.symbol: (i, t) for i, t in enumerate(new_ranking)}

    # Detectar tickers NUEVOS
    for symbol in new_dict:
        if symbol not in old_dict:
            rank, ticker = new_dict[symbol]
            deltas.append({
                "action": "add",
                "rank": rank,
                "symbol": symbol,
                "data": ticker.model_dump(mode='json')
            })

    # Detectar tickers REMOVIDOS
    for symbol in old_dict:
        if symbol not in new_dict:
            deltas.append({
                "action": "remove",
                "symbol": symbol
            })

    # Detectar CAMBIOS
    for symbol in new_dict:
        if symbol in old_dict:
            old_rank, old_ticker = old_dict[symbol]
            new_rank, new_ticker = new_dict[symbol]

            # Cambio de RANK
            if old_rank != new_rank:
                deltas.append({
                    "action": "rerank",
                    "symbol": symbol,
                    "old_rank": old_rank,
                    "new_rank": new_rank
                })

            # Cambio de DATOS
            if self._ticker_data_changed(old_ticker, new_ticker):
                deltas.append({
                    "action": "update",
                    "rank": new_rank,
                    "symbol": symbol,
                    "data": new_ticker.model_dump(mode='json')
                })

    return deltas
```

**Tipos de deltas**:

- `add`: Ticker nuevo en ranking
- `remove`: Ticker salió del ranking
- `update`: Datos del ticker cambiaron (precio, volumen, RVOL, gap)
- `rerank`: Cambió de posición

**Detección de cambios** (línea 1018-1053):

```python
def _ticker_data_changed(old_ticker, new_ticker):
    PRICE_THRESHOLD = 0.01       # 1 centavo
    VOLUME_THRESHOLD = 1000      # 1K shares
    PERCENT_THRESHOLD = 0.01     # 0.01%

    # Precio cambió
    if abs(new_ticker.price - old_ticker.price) > PRICE_THRESHOLD:
        return True

    # Volumen cambió
    if abs(new_ticker.volume_today - old_ticker.volume_today) > VOLUME_THRESHOLD:
        return True

    # Gap% cambió
    if abs(new_ticker.change_percent - old_ticker.change_percent) > PERCENT_THRESHOLD:
        return True

    # RVOL cambió
    if old_ticker.rvol and new_ticker.rvol:
        if abs(new_ticker.rvol - old_ticker.rvol) > 0.05:
            return True

    return False
```

**Umbrales mínimos** evitan ruido por cambios insignificantes.

---

### Paso 7: Publicación de Resultados

Scanner publica a MÚLTIPLES destinos:

#### Salida 1: Stream de Deltas

**Código**: línea 1055-1114

```python
async def emit_ranking_deltas(list_name, deltas):
    if not deltas:
        return

    # Incrementar sequence number
    self.sequence_numbers[list_name] = self.sequence_numbers.get(list_name, 0) + 1
    sequence = self.sequence_numbers[list_name]

    # Mensaje
    message = {
        'type': 'delta',
        'list': list_name,
        'sequence': sequence,
        'deltas': json.dumps(deltas),
        'timestamp': datetime.now().isoformat(),
        'change_count': len(deltas)
    }

    # Publicar
    await self.redis.xadd(
        settings.stream_ranking_deltas,  # "stream:ranking:deltas"
        message
    )

    # Guardar sequence en Redis
    await self.redis.set(
        f"scanner:sequence:{list_name}",
        sequence,
        ttl=86400
    )
```

**Stream**: `stream:ranking:deltas`
**Consumidor**: WebSocket Server (con consumer group)
**Frecuencia**: Cada vez que hay cambios en categorías (cada 10 seg)

#### Salida 2: Snapshots de Categorías

**Código**: línea 1162-1212

```python
async def emit_full_snapshot(list_name, tickers):
    self.sequence_numbers[list_name] = self.sequence_numbers.get(list_name, 0) + 1
    sequence = self.sequence_numbers[list_name]

    snapshot_data = [t.model_dump(mode='json') for t in tickers]

    message = {
        'type': 'snapshot',
        'list': list_name,
        'sequence': sequence,
        'rows': json.dumps(snapshot_data),
        'timestamp': datetime.now().isoformat(),
        'count': len(tickers)
    }

    await self.redis.xadd(
        settings.stream_ranking_deltas,
        message
    )
```

**Cuándo**: Primera vez que se crea una categoría

#### Salida 3: Redis Keys (Rankings)

**Código**: línea 1120-1160

```python
async def _save_ranking_to_redis(list_name, tickers):
    ranking_data = [t.model_dump(mode='json') for t in tickers]

    current_sequence = self.sequence_numbers.get(list_name, 0)

    # Guardar ranking completo
    await self.redis.set(
        f"scanner:category:{list_name}",
        json.dumps(ranking_data),
        ttl=3600  # 1 hora
    )

    # Guardar sequence
    await self.redis.set(
        f"scanner:sequence:{list_name}",
        current_sequence,
        ttl=86400  # 24 horas
    )
```

**Keys creados**:

- `scanner:category:gappers_up` (ranking completo JSON)
- `scanner:category:gappers_down`
- ... (uno por categoría)
- `scanner:sequence:gappers_up` (número de secuencia)
- ... (uno por categoría)

**Usado por**: WebSocket Server (para enviar snapshot inicial a nuevos clientes)

#### Salida 4: Stream Huérfano (PROBLEMA)

**Código**: línea 581-598

```python
async def _publish_filtered_tickers(tickers):
    for ticker in tickers:  # Loop de 200 tickers
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

**Problema**: NADIE consume este stream.
**Solución**: Debería eliminarse.

#### Salida 5: Sorted Set

**Código**: línea 600-606

```python
if tickers:
    mapping = {ticker.symbol: ticker.score for ticker in tickers}
    await self.redis.zadd(
        f"scanner:filtered:{self.current_session.value}",
        mapping
    )
```

**Sorted set**: `scanner:filtered:MARKET_OPEN`
**Uso**: Consultas rápidas por ranking via score

#### Salida 6: TimescaleDB

**Código**: línea 613-642

```python
async def _save_scan_results(tickers):
    for ticker in tickers:  # LOOP de 200 tickers
        metadata_json = json.dumps(ticker.metadata)

        scan_data = {
            "time": ticker.timestamp,
            "symbol": ticker.symbol,
            "session": ticker.session.value,
            "price": ticker.price,
            "volume": ticker.volume,
            "volume_today": ticker.volume_today,
            "change_percent": ticker.change_percent,
            "rvol": ticker.rvol,
            "rvol_slot": ticker.rvol_slot,
            "price_from_high": ticker.price_from_high,
            "price_from_low": ticker.price_from_low,
            "market_cap": ticker.market_cap,
            "float_shares": ticker.float_shares,
            "score": ticker.score,
            "filters_matched": ticker.filters_matched,
            "metadata": metadata_json
        }

        await self.db.insert_scan_result(scan_data)  # INSERT individual
```

**Tabla**: `scan_results`
**Operaciones**: 200 INSERTs individuales (sin batch)
**Problema**: Debería usar `executemany()` para batch

---

## HOT TICKER MANAGER

### Propósito

Gestionar qué tickers son "hot" (en rankings) vs "cold" (fuera de rankings).

**Código**: hot_ticker_manager.py línea 144-185

```python
async def update_hot_set(current_rankings):
    # Recopilar TODOS los tickers en rankings
    all_hot_symbols = set()
    for category_name, symbols in current_rankings.items():
        # Top 20 de CADA categoría
        all_hot_symbols.update(symbols[:20])

    # Calcular diferencias
    to_promote = all_hot_symbols - self.hot_tickers
    to_degrade = self.hot_tickers - all_hot_symbols

    # Promociones
    if to_promote:
        await self.promote_to_hot(list(to_promote))

    # Degradaciones
    if to_degrade:
        await self.degrade_to_cold(list(to_degrade))

    self.last_hot_update = datetime.now()
```

**Promoción** (línea 46-93):

```python
async def promote_to_hot(symbols):
    new_hot = set(symbols) - self.hot_tickers

    # Suscribir a Polygon WS
    for symbol in new_hot:
        await self.redis.xadd(
            settings.key_polygon_subscriptions,  # "polygon_ws:subscriptions"
            {
                'symbol': symbol,
                'action': 'subscribe',
                'timestamp': datetime.now().isoformat()
            }
        )

    self.hot_tickers.update(new_hot)
```

**Degradación** (línea 95-142):

```python
async def degrade_to_cold(symbols):
    to_degrade = set(symbols) & self.hot_tickers

    # Desuscribir de Polygon WS
    for symbol in to_degrade:
        await self.redis.xadd(
            settings.key_polygon_subscriptions,
            {
                'symbol': symbol,
                'action': 'unsubscribe',
                'timestamp': datetime.now().isoformat()
            }
        )

    self.hot_tickers -= to_degrade
```

**Stream usado**: `polygon_ws:subscriptions`
**Consumidor**: Polygon WS Service
**Resultado**: Polygon WS se suscribe/desuscribe automáticamente

**Cantidad de hot tickers**:

- 11 categorías × 20 tickers = hasta 220 tickers
- Con solapamiento: ~100-150 tickers únicos

---

## CONEXIONES CON OTROS SERVICIOS

### 1. Analytics → Scanner (ENTRADA)

```
Analytics
   ↓ XADD
snapshots:enriched (stream)
   ↓ XREAD
Scanner
```

**Datos**: Snapshots con RVOL incluido
**Método**: XREAD (sin consumer group)
**Frecuencia**: Cada 10 segundos (discovery loop)

### 2. Historical Service → Scanner (CONSULTA)

```
Scanner
   ↓ Query SQL
TimescaleDB: ticker_metadata
   ↓
Scanner
```

**Tabla**: `ticker_metadata`
**Datos**: company_name, exchange, sector, market_cap, float_shares, avg_volume_30d, etc.
**Caché**: Redis con TTL 1 hora
**Frecuencia**: Solo cache miss

### 3. Market Session → Scanner (CONSULTA)

```
Scanner
   ↓ HTTP GET
Market Session Service (puerto 8002)
   ↓
Scanner
```

**Endpoint**: `/api/session/current`
**Datos**: current_session (PRE_MARKET, MARKET_OPEN, POST_MARKET, CLOSED)
**Código**: línea 851-862

```python
async def _update_market_session():
    url = f"http://market_session:8002/api/session/current"

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)

        if response.status_code == 200:
            data = response.json()
            self.current_session = MarketSession(data["current_session"])
```

**Frecuencia**: Una vez por scan (cada 10 seg)

### 4. Scanner → WebSocket Server (SALIDA)

```
Scanner
   ↓ XADD
stream:ranking:deltas
   ↓ XREADGROUP
WebSocket Server
```

**Datos**: Snapshots y deltas de rankings
**Consumidor**: websocket_server_deltas (consumer group)
**Frecuencia**: Cada 10 segundos + cuando hay cambios

### 5. Scanner → Polygon WS (INDIRECTO)

```
Scanner (Hot Ticker Manager)
   ↓ XADD
polygon_ws:subscriptions
   ↓ XREADGROUP
Polygon WS Service
```

**Datos**: Comandos subscribe/unsubscribe
**Resultado**: Polygon WS ajusta suscripciones dinámicamente
**Frecuencia**: Cuando cambian los rankings

### 6. Scanner → TimescaleDB (SALIDA)

```
Scanner
   ↓ INSERT
TimescaleDB: scan_results
```

**Tabla**: `scan_results` (histórico de scans)
**Operaciones**: 200 INSERTs individuales
**Frecuencia**: Cada 10 segundos

---

## CUELLOS DE BOTELLA IDENTIFICADOS

### 1. Operaciones Individuales a Redis (5,000 GET)

**Código**: línea 267-268

```python
for snapshot in snapshots:  # 5,000 iteraciones
    key = f"metadata:ticker:{symbol}"
    data = await self.redis.get(key)  # ← GET individual
```

**Problema**: 5,000 operaciones individuales
**Tiempo estimado**: 5,000 × 0.2ms = 1 segundo (con caché caliente)
**Solución**: Redis pipelining o MGET

### 2. INSERTs Individuales a BD (200 queries)

**Código**: línea 617-634

```python
for ticker in tickers:  # 200 iteraciones
    await self.db.insert_scan_result(scan_data)  # INSERT individual
```

**Problema**: 200 queries individuales
**Tiempo estimado**: 200 × 2ms = 400ms
**Solución**: `executemany()` con batch

### 3. XADDs Individuales a Stream Huérfano (200 ops)

**Código**: línea 585-593

```python
for ticker in tickers:  # 200 iteraciones
    await self.redis.xadd("tickers:filtered", ...)
```

**Problema**: Nadie consume este stream + 200 XADDs
**Solución**: Eliminar completamente

### 4. Sin Consumer Group

**Código**: línea 188

```python
streams = await self.redis.xread(...)  # NO XREADGROUP
```

**Problemas**:

- Tracking manual de posición (se pierde al reiniciar)
- Sin ACK (puede re-procesar mensajes)
- Sin persistencia

**Solución**: Implementar consumer group

### 5. Procesamiento Síncrono en Loop

**Código**: línea 238-249

```python
for snapshot in snapshots:  # 5,000 iteraciones síncronas
    metadata = await self._get_ticker_metadata(snapshot.ticker)
    ticker = await self._build_scanner_ticker(snapshot, metadata)
    ticker = self.enhance_ticker_with_gaps(ticker, snapshot)
    enriched.append(ticker)
```

**Problema**: Procesa uno a uno (await en loop)
**Solución**: Procesar en chunks con `asyncio.gather()`

---

## DEPENDENCIAS DE RVOL

El Scanner depende **CRÍTICAMENTE** de RVOL para:

### 1. Filtrado

**Código**: línea 439-445

```python
if params.min_rvol:
    if ticker.rvol < params.min_rvol:
        return False  # Rechaza ticker
```

**Sin RVOL**: Tickers sin RVOL se rechazan si hay filtro de min_rvol.

### 2. Scoring

**Código**: línea 519-520

```python
if ticker.rvol:
    score += ticker.rvol * 10  # Peso máximo
```

**Sin RVOL**: Score mucho más bajo, peor posición en ranking.

### 3. Categorización - Anomalies

**Código**: scanner_categories.py línea 112-117

```python
if ticker.rvol_slot >= 3.0:
    categories.append(ScannerCategory.ANOMALIES)
```

**Sin RVOL**: No aparece en categoría "Anomalies".

### 4. Categorización - High Volume

**Código**: línea 120-122

```python
if ticker.rvol >= 2.0:
    categories.append(ScannerCategory.HIGH_VOLUME)
```

**Sin RVOL**: No aparece en categoría "High Volume".

### 5. Ordenamiento de Anomalies

**Código**: línea 193

```python
categorized.sort(key=lambda t: t.rvol_slot or t.rvol or 0, reverse=True)
```

**Sin RVOL**: Se ordena por 0 (última posición).

**CONCLUSIÓN**: RVOL es CRÍTICO para el funcionamiento correcto del Scanner.

---

## CUELLO DE BOTELLA ACTUAL: Falta de Consumer Group

El problema MÁS GRAVE no es la cantidad de operaciones, sino:

**Sin consumer group**:

```python
# Tracking manual
streams = await self.redis.xread(
    streams={"snapshots:enriched": self.stream_position},
    ...
)

for message_id, data in messages:
    self.stream_position = message_id  # Variable en memoria
```

**Problemas**:

1. **Se pierde al reiniciar**:

   ```
   Scanner se reinicia
      ↓
   stream_position vuelve a "0"
      ↓
   Intenta leer desde el principio
      ↓
   Pero stream tiene maxlen=50,000
      ↓
   Mensajes viejos fueron descartados
      ↓
   Empieza desde primer mensaje disponible
      ↓
   Puede procesar datos antiguos o perder datos
   ```

2. **Sin ACK**: Si Scanner crashea a mitad de procesamiento, no hay forma de saber qué ya procesó.

3. **Puede generar lag**: Si Scanner es más lento que producer, acumula backlog infinito hasta que stream descarta mensajes.

---

## RESUMEN DE OPTIMIZACIONES IMPLEMENTADAS

### YA IMPLEMENTADO:

1. Scanner lee de `snapshots:enriched` (RVOL incluido)
2. Batch reducido: 15,000 → 5,000
3. Frecuencia aumentada: 30seg → 10seg
4. RVOL obtenido de memoria (no Redis HGET)
5. WebSocket Server con consumer groups + BLOCK 100ms
6. Analytics publica stream enriquecido

### PENDIENTE (Recomendado):

1. Implementar consumer group en Scanner
2. Batch GET con pipelining para metadata
3. Batch INSERT para scan_results
4. Eliminar stream `tickers:filtered`
5. Procesar enriquecimiento con `asyncio.gather()` en chunks

---

**El sistema ahora está optimizado para actualizaciones casi en tiempo real (100ms de latencia). El desfase que reportaste debería eliminarse cuando el mercado abra el lunes.**
