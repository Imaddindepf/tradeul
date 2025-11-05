# SCANNER: FLUJO COMPLETO POST-FILTRADO
## Análisis Exhaustivo - Qué hace Scanner después de filtrar

**Fecha**: 3 Noviembre 2025  
**Archivo**: `services/scanner/scanner_engine.py`

---

## 🎯 PUNTO DE PARTIDA

Scanner ejecutó `_process_snapshots_optimized()` y tiene:

```python
scored_tickers = [
    ScannerTicker(symbol="CRBU", price=1.51, rvol=2493.73, change_percent=204.55, score=2500, rank=1),
    ScannerTicker(symbol="MSPR", price=5.20, rvol=2787.5, change_percent=122.64, score=2200, rank=2),
    ... (335 tickers más)
    # Total: 337 tickers filtrados y rankeados
]
```

Ahora sigue **7 PASOS CRÍTICOS**...

---

## PASO 1: LIMITAR RESULTADOS (líneas 129-131)

```python
if len(scored_tickers) > settings.max_filtered_tickers:
    scored_tickers = scored_tickers[:settings.max_filtered_tickers]
```

**CONFIGURACIÓN**:
- `max_filtered_tickers` = 1000 (settings.py)

**LÓGICA**:
```
Si filtered = 337:  → No hace nada (337 < 1000)
Si filtered = 1,500: → Recorta a 1,000
Si filtered = 50:    → No hace nada (50 < 1000)
```

**POR QUÉ**:
- Evitar sobrecarga de memoria
- Limitar procesamiento posterior (categorización, BD)
- Solo los top N por score continúan

**RESULTADO**: 337 tickers (sin cambios)

---

## PASO 2: GUARDADO EN 3 CACHÉS (líneas 134-143)

Scanner guarda los tickers filtrados en **3 ubicaciones diferentes**:

### 2.1 CACHÉ EN MEMORIA (líneas 135-137)

```python
self.last_filtered_tickers = scored_tickers
self.last_filtered_time = datetime.now()
```

**UBICACIÓN**: Atributos de la clase `ScannerEngine`

**CARACTERÍSTICAS**:
- ✅ Acceso instantáneo (0ms)
- ✅ Sin operaciones I/O
- ❌ Se pierde si servicio se reinicia
- ❌ No compartido con otros servicios

**USADO POR**:
- API endpoint `GET /api/filtered` (consultas rápidas)
- Comparaciones internas del scanner
- No persiste entre reinicios

**EJEMPLO**:
```python
# Otro lugar del código puede hacer:
latest_tickers = scanner_engine.last_filtered_tickers
# Retorna los 337 tickers inmediatamente
```

---

### 2.2 CACHÉ EN REDIS - COMPLETO (líneas 140 → función 750-783)

```python
await self._save_filtered_tickers_to_cache(scored_tickers)
```

**IMPLEMENTACIÓN** (`_save_filtered_tickers_to_cache`, líneas 750-783):

```python
# Clave dinámica por sesión
cache_key = f"scanner:filtered_complete:{self.current_session.value}"
# Ejemplo: "scanner:filtered_complete:PRE_MARKET"

# Serializar TODOS los tickers completos
tickers_data = [ticker.model_dump(mode='json') for ticker in tickers]

# Guardar en Redis con TTL
await self.redis.set(
    cache_key,
    tickers_data,
    ttl=60,  # 60 segundos
    serialize=True
)
```

**ESTRUCTURA EN REDIS**:
```json
Key: scanner:filtered_complete:PRE_MARKET
TTL: 60 segundos
Value: [
  {
    "symbol": "CRBU",
    "timestamp": "2025-11-03T05:30:00Z",
    "price": 1.51,
    "bid": 1.50,
    "ask": 1.52,
    "volume": 13856866,
    "volume_today": 13856866,
    "open": 0.50,
    "high": 1.60,
    "low": 0.48,
    "prev_close": 0.50,
    "change": 1.01,
    "change_percent": 204.55,
    "rvol": 2493.73,
    "rvol_slot": 2493.73,
    "price_from_high": -5.63,
    "price_from_low": 108.33,
    "market_cap": 5000000,
    "float_shares": 3000000,
    "sector": "Healthcare",
    "industry": "Biotechnology",
    "exchange": "NASDAQ",
    "score": 2500.5,
    "rank": 1,
    "filters_matched": ["rvol_high", "price_range"],
    "session": "PRE_MARKET",
    "metadata": {
      "gaps": {...},
      "gap_size_classification": "EXTREME",
      ...
    }
  },
  ... 336 tickers más
]
```

**CARACTERÍSTICAS**:
- ✅ Persiste 60 segundos
- ✅ Compartido entre instancias
- ✅ Tickers COMPLETOS con todos los campos
- ✅ Se refresca cada scan (cada 30s)

**USADO POR**:
- Otros servicios que necesitan acceder a tickers filtrados
- API Gateway para consultas
- Debugging y monitoring

**KEYS POR SESIÓN**:
```
scanner:filtered_complete:PRE_MARKET
scanner:filtered_complete:MARKET_OPEN
scanner:filtered_complete:POST_MARKET
scanner:filtered_complete:CLOSED
```

---

### 2.3 CACHÉ EN REDIS - SORTED SET (DESACTIVADO pero existe en código)

**Función** (`_publish_filtered_tickers`, líneas 785-815):

```python
# DESACTIVADO en línea 146 del flujo principal
# await self._publish_filtered_tickers(scored_tickers)

# Pero el código existe:
for ticker in tickers:
    await self.redis.xadd(
        "stream:scanner:filtered",
        {
            "symbol": ticker.symbol,
            "price": ticker.price,
            "score": ticker.score,
            ...
        }
    )
```

**POR QUÉ ESTÁ DESACTIVADO**:
- Stream sin consumidores (huérfano)
- Ya no se usa después del refactor
- Comentado en línea 145-146

---

## PASO 3: CATEGORIZACIÓN (línea 143)

```python
await self.categorize_filtered_tickers(scored_tickers)
```

**QUÉ HACE**: El proceso MÁS COMPLEJO del scanner. Vamos línea por línea...

### 3.1 Función `categorize_filtered_tickers()` (líneas 928-989)

```python
async def categorize_filtered_tickers(
    self,
    tickers: List[ScannerTicker],
    emit_deltas: bool = True
) -> Dict[str, List[ScannerTicker]]:
```

**ENTRADA**:
- `tickers`: Los 337 tickers filtrados
- `emit_deltas`: True (emite cambios incrementales)

**FLUJO COMPLETO**:

#### 3.1.1 Obtener categorías (línea 945)

```python
categories = self.categorizer.get_all_categories(tickers, limit_per_category=20)
```

Esto llama a `scanner_categories.py` → `get_all_categories()`:

```python
results = {}

for category in ScannerCategory:  # 11 categorías
    ranked = get_category_rankings(tickers, category, limit=20)
    
    if ranked:
        results[category.value] = ranked

return results
```

**PROCESO PARA CADA CATEGORÍA**:

```python
# EJEMPLO: gappers_up

1. FILTRAR tickers que califican (scanner_categories.py líneas 169-175)
   
   categorized = []
   for ticker in tickers:  # Los 337 filtrados
       categories = categorize_ticker(ticker)  # Retorna ["gappers_up", "winners", ...]
       
       if ScannerCategory.GAPPERS_UP in categories:
           categorized.append(ticker)
   
   # Resultado: 97 tickers con change_percent >= 2.0

2. ORDENAR por criterio específico (líneas 186-188)
   
   categorized.sort(key=lambda t: t.change_percent or 0, reverse=True)
   
   # Ordenados:
   # 1. CRBU: +204.55%
   # 2. MSPR: +122.64%
   # 3. RAY: +53.76%
   # ...
   # 97. (último con change >= 2%)

3. LIMITAR a top 20 (línea 219)
   
   return categorized[:20]
```

**CATEGORIZACIÓN DE UN TICKER** (líneas 76-156 de scanner_categories.py):

```python
def categorize_ticker(ticker: ScannerTicker) -> List[ScannerCategory]:
    categories = []
    
    # 1. GAPPERS (change desde cierre anterior)
    if change_percent >= 2.0:
        categories.append(GAPPERS_UP)
    elif change_percent <= -2.0:
        categories.append(GAPPERS_DOWN)
    
    # 2. MOMENTUM (solo durante market open)
    if session == MARKET_OPEN and change >= 3.0:
        categories.append(MOMENTUM_UP)
    
    # 3. WINNERS/LOSERS (cambios extremos)
    if change_percent >= 5.0:
        categories.append(WINNERS)
    elif change_percent <= -5.0:
        categories.append(LOSERS)
    
    # 4. ANOMALIES (RVOL extremo)
    if rvol >= 3.0:
        categories.append(ANOMALIES)
    
    # 5. HIGH_VOLUME (alto RVOL)
    if rvol >= 2.0:
        categories.append(HIGH_VOLUME)
    
    # 6. NEW_HIGHS/LOWS (posición en rango)
    if price_from_high <= 0.5:  # Dentro de 0.5% del high
        categories.append(NEW_HIGHS)
    if price_from_low <= 0.5:
        categories.append(NEW_LOWS)
    
    # 7. REVERSALS (gap tracker)
    if is_reversal:
        categories.append(REVERSALS)
    
    return categories
```

**EJEMPLO REAL - Ticker CRBU**:

```
CRBU: change=+204.55%, rvol=2493.73x, price_from_high=-5.63%

Categorías donde entra:
✅ gappers_up (204.55 >= 2.0)
✅ winners (204.55 >= 5.0)
✅ anomalies (2493.73 >= 3.0)
✅ high_volume (2493.73 >= 2.0)
❌ new_highs (5.63% desde high, requiere <= 0.5%)
❌ momentum_up (no es MARKET_OPEN)
❌ reversals (no cumple condiciones)

Total: 4 categorías
```

**RETORNO DE `get_all_categories()`**:

```python
{
    "gappers_up": [
        ScannerTicker(CRBU, rank=1),
        ScannerTicker(MSPR, rank=2),
        ScannerTicker(RAY, rank=3),
        ... (17 más, total 20)
    ],
    "gappers_down": [... 20 tickers],
    "winners": [
        ScannerTicker(CRBU, rank=1),
        ScannerTicker(MSPR, rank=2),
        ... (18 más, total 20)
    ],
    "anomalies": [... 20 tickers],
    "high_volume": [... 20 tickers],
    "new_highs": [... 15 tickers],
    "new_lows": [... 8 tickers],
    "reversals": [... 3 tickers],
    # No hay momentum_up/down (solo en MARKET_OPEN)
}
```

---

#### 3.1.2 GENERAR Y EMITIR DELTAS (líneas 948-973)

```python
for category_name, new_ranking in categories.items():
    # PASO A: Obtener ranking anterior
    old_ranking = self.last_rankings.get(category_name, [])
    
    if not old_ranking:
        # PRIMERA VEZ - Emitir snapshot completo
        logger.info(f"📸 First time for {category_name}, emitting snapshot")
        await self.emit_full_snapshot(category_name, new_ranking)
    
    else:
        # ITERACIONES SIGUIENTES - Calcular deltas
        deltas = self.calculate_ranking_deltas(old_ranking, new_ranking, category_name)
        
        if deltas:
            await self.emit_ranking_deltas(category_name, deltas)
    
    # PASO B: Guardar ranking en Redis
    await self._save_ranking_to_redis(category_name, new_ranking)
    
    # PASO C: Actualizar último ranking en memoria
    self.last_rankings[category_name] = new_ranking
```

**FLUJO VISUAL**:

```
ITERACIÓN 1:
old_rankings = {}
new_rankings = {"gappers_up": [20 tickers]}
→ NO hay old → emit_full_snapshot()
→ Guarda en Redis
→ last_rankings["gappers_up"] = [20 tickers]

ITERACIÓN 2:
old_rankings = {"gappers_up": [A,B,C,D,E...]} (20 tickers)
new_rankings = {"gappers_up": [A,C,E,F,G...]} (20 tickers)
→ SÍ hay old → calculate_ranking_deltas()
   → Deltas: remove B,D | add F,G | rerank C,E
→ emit_ranking_deltas(deltas)
→ Guarda en Redis
→ last_rankings["gappers_up"] = [A,C,E,F,G...]
```

---

### 3.2 CÁLCULO DE DELTAS (líneas 1085-1236)

```python
def calculate_ranking_deltas(
    self,
    old_ranking: List[ScannerTicker],
    new_ranking: List[ScannerTicker],
    category_name: str
) -> List[Dict]:
```

**ALGORITMO COMPLETO**:

#### PASO 3.2.1: Crear mapas de búsqueda (líneas 1097-1109)

```python
old_map = {ticker.symbol: ticker for ticker in old_ranking}
new_map = {ticker.symbol: ticker for ticker in new_ranking}

old_symbols = set(old_map.keys())  # {A, B, C, D, E}
new_symbols = set(new_map.keys())  # {A, C, E, F, G}
```

#### PASO 3.2.2: Detectar ADDS (líneas 1111-1126)

```python
added_symbols = new_symbols - old_symbols
# {F, G} - Tickers nuevos

for symbol in added_symbols:
    ticker = new_map[symbol]
    new_rank = next(
        i + 1 for i, t in enumerate(new_ranking) 
        if t.symbol == symbol
    )
    
    deltas.append({
        "type": "add",
        "ticker": ticker.model_dump(mode='json'),
        "rank": new_rank
    })
```

**EJEMPLO**:
```json
{
  "type": "add",
  "ticker": {
    "symbol": "ETHZW",
    "price": 0.05,
    "change_percent": 32.55,
    "rvol": 2.39,
    ...
  },
  "rank": 6
}
```

#### PASO 3.2.3: Detectar REMOVES (líneas 1128-1150)

```python
removed_symbols = old_symbols - new_symbols
# {B, D} - Tickers que salieron

for symbol in removed_symbols:
    deltas.append({
        "type": "remove",
        "ticker": symbol
    })
```

**EJEMPLO**:
```json
{
  "type": "remove",
  "ticker": "LGCL"
}
```

**POR QUÉ SALEN TICKERS**:

1. **Cayó su RVOL** < 1.5 → No pasa filtro
2. **Ya no tiene volumen** → RVOL = None
3. **Cambió su change_percent** → Ya no califica para categoría
4. **Desplazado del top 20** → Hay mejores

#### PASO 3.2.4: Detectar UPDATES (líneas 1152-1191)

```python
common_symbols = old_symbols & new_symbols
# {A, C, E} - Tickers en ambos rankings

for symbol in common_symbols:
    old_ticker = old_map[symbol]
    new_ticker = new_map[symbol]
    
    # Verificar si CAMBIÓ algún dato importante
    if _ticker_data_changed(old_ticker, new_ticker):
        deltas.append({
            "type": "update",
            "ticker": symbol,
            "data": {
                "price": new_ticker.price,
                "volume": new_ticker.volume_today,
                "change_percent": new_ticker.change_percent,
                "rvol": new_ticker.rvol,
                ...
            }
        })
```

**Función `_ticker_data_changed()` (líneas 1238-1273)**:

```python
COMPARA CAMPOS CRÍTICOS:

if old_ticker.price != new_ticker.price:
    return True

if old_ticker.volume_today != new_ticker.volume_today:
    return True

if old_ticker.change_percent != new_ticker.change_percent:
    return True

if old_ticker.rvol != new_ticker.rvol:
    return True

# También verifica: bid, ask, high, low, score

return False
```

**EJEMPLO**:
```json
{
  "type": "update",
  "ticker": "CRBU",
  "data": {
    "price": 1.52,        // cambió de 1.51
    "volume": 14000000,   // cambió de 13856866
    "rvol": 2520.5,       // cambió de 2493.73
    "change_percent": 206.0  // cambió de 204.55
  }
}
```

#### PASO 3.2.5: Detectar RERANKS (líneas 1193-1213)

```python
for symbol in common_symbols:
    old_rank = next(i + 1 for i, t in enumerate(old_ranking) if t.symbol == symbol)
    new_rank = next(i + 1 for i, t in enumerate(new_ranking) if t.symbol == symbol)
    
    if old_rank != new_rank:
        deltas.append({
            "type": "rerank",
            "ticker": symbol,
            "old_rank": old_rank,
            "new_rank": new_rank
        })
```

**EJEMPLO**:
```json
{
  "type": "rerank",
  "ticker": "RAY",
  "old_rank": 3,
  "new_rank": 2
}
```

**POR QUÉ CAMBIA EL RANK**:
- Su score aumentó/disminuyó
- Otros tickers superaron/cayeron
- Cambió su change_percent o rvol

---

### 3.3 EMISIÓN DE DELTAS (líneas 1275-1333)

```python
async def emit_ranking_deltas(
    self,
    list_name: str,
    deltas: List[Dict]
):
```

**PASO A PASO**:

#### Línea 1291: Incrementar sequence number

```python
self.sequence_numbers[list_name] = self.sequence_numbers.get(list_name, 0) + 1
```

**QUÉ ES**:
- Contador incremental por categoría
- Empieza en 0, aumenta en cada emisión
- Usado para detectar gaps en frontend/websocket

**EJEMPLO**:
```python
Iteración 1: gappers_up sequence = 1
Iteración 2: gappers_up sequence = 2
Iteración 3: gappers_up sequence = 3
...
Iteración 120: gappers_up sequence = 120
```

#### Líneas 1293-1300: Crear mensaje delta

```python
delta_message = {
    "list": list_name,                        # "gappers_up"
    "sequence": self.sequence_numbers[list_name],  # 120
    "timestamp": datetime.now().isoformat(),  # "2025-11-03T05:30:00Z"
    "changes": len(deltas),                   # 7
    "deltas": json.dumps(deltas)              # "[{type: add, ...}, ...]"
}
```

#### Líneas 1303-1309: Publicar al stream

```python
await self.redis.xadd(
    "stream:ranking:deltas",  # ← Stream que consume WebSocket
    delta_message,
    maxlen=10000  # Mantiene solo últimos 10,000 deltas
)
```

**ESTRUCTURA EN STREAM**:

```
stream:ranking:deltas:
  [mensaje_id_1] {list: "gappers_up", sequence: 118, deltas: "[...]"}
  [mensaje_id_2] {list: "winners", sequence: 45, deltas: "[...]"}
  [mensaje_id_3] {list: "gappers_up", sequence: 119, deltas: "[...]"}
  [mensaje_id_4] {list: "anomalies", sequence: 102, deltas: "[...]"}
  ...
  [mensaje_id_10000] (límite alcanzado, se elimina el más viejo)
```

**MAXLEN = 10,000**:
- Mantiene historial de ~1 hora de deltas (si se emite cada 30s)
- Evita crecimiento infinito
- Permite a WebSocket recuperarse si se cae

#### Líneas 1312-1327: Logging y estadísticas

```python
adds = sum(1 for d in deltas if d['type'] == 'add')
removes = sum(1 for d in deltas if d['type'] == 'remove')  
updates = sum(1 for d in deltas if d['type'] == 'update')
reranks = sum(1 for d in deltas if d['type'] == 'rerank')

logger.info("✅ Emitted ranking deltas",
    list=list_name,
    sequence=self.sequence_numbers[list_name],
    changes=len(deltas),
    adds=adds,
    removes=removes,
    updates=updates,
    reranks=reranks
)
```

**LOG EJEMPLO**:
```
✅ Emitted ranking deltas: gappers_up, sequence=120, changes=7, adds=1, removes=1, updates=2, reranks=3
```

---

### 3.4 GUARDAR SNAPSHOT DE RANKING EN REDIS (líneas 1346-1391)

```python
await self._save_ranking_to_redis(category_name, new_ranking)
```

**IMPLEMENTACIÓN**:

```python
async def _save_ranking_to_redis(
    self,
    list_name: str,
    tickers: List[ScannerTicker]
):
    # Convertir tickers a JSON
    ranking_data = [t.model_dump(mode='json') for t in tickers]
    
    # Obtener sequence number actual
    current_sequence = self.sequence_numbers.get(list_name, 0)
    
    # GUARDAR RANKING COMPLETO
    await self.redis.set(
        f"scanner:category:{list_name}",  # "scanner:category:gappers_up"
        json.dumps(ranking_data),
        ttl=3600  # 1 hora
    )
    
    # GUARDAR SEQUENCE NUMBER
    await self.redis.set(
        f"scanner:sequence:{list_name}",  # "scanner:sequence:gappers_up"
        current_sequence,
        ttl=86400  # 24 horas
    )
```

**KEYS EN REDIS**:

```
scanner:category:gappers_up
TTL: 3600s (1 hora)
Value: [
  {"symbol": "CRBU", "price": 1.51, "rvol": 2493.73, ...},
  {"symbol": "MSPR", ...},
  ... (18 más, total 20)
]

scanner:sequence:gappers_up
TTL: 86400s (24 horas)
Value: 120
```

**USADO POR**:
- WebSocket Server para enviar snapshot inicial a nuevos clientes
- Frontend cuando se conecta por primera vez
- Recovery después de pérdida de conexión

---

### 3.5 Actualizar último ranking en memoria (línea 973)

```python
self.last_rankings[category_name] = new_ranking
```

**ESTRUCTURA EN MEMORIA**:

```python
self.last_rankings = {
    "gappers_up": [20 ScannerTicker objects],
    "gappers_down": [20 ScannerTicker objects],
    "winners": [20 ScannerTicker objects],
    "anomalies": [20 ScannerTicker objects],
    "high_volume": [20 ScannerTicker objects],
    "new_highs": [15 ScannerTicker objects],
    "new_lows": [8 ScannerTicker objects],
    "reversals": [3 ScannerTicker objects],
}
```

**POR QUÉ SE GUARDA**:
- Para comparar en próxima iteración
- Calcular deltas (adds, removes, reranks)
- Evitar recalcular desde Redis

---

## PASO 4: GUARDAR EN TIMESCALEDB (línea 149)

```python
await self._save_scan_results(scored_tickers)
```

**IMPLEMENTACIÓN** (líneas 817-860):

```python
async def _save_scan_results(self, tickers: List[ScannerTicker]):
    
    # BATCH INSERT - UNA SOLA QUERY
    batch_data = []
    for ticker in tickers:  # 337 tickers
        metadata_json = json.dumps(ticker.metadata) if ticker.metadata else None
        
        batch_data.append((
            ticker.timestamp,        # time
            ticker.symbol,           # symbol
            ticker.session.value,    # session (PRE_MARKET, MARKET_OPEN, etc.)
            ticker.price,            # price
            ticker.volume,           # volume (instantáneo)
            ticker.volume_today,     # volume_today (acumulado)
            ticker.change_percent,   # change_percent
            ticker.rvol,             # rvol
            ticker.rvol_slot,        # rvol_slot
            ticker.price_from_high,  # price_from_high
            ticker.price_from_low,   # price_from_low
            ticker.market_cap,       # market_cap
            ticker.float_shares,     # float_shares
            ticker.score,            # score
            ticker.filters_matched,  # filters_matched (array)
            metadata_json            # metadata (jsonb)
        ))
    
    query = """
        INSERT INTO scan_results (
            time, symbol, session, price, volume, volume_today,
            change_percent, rvol, rvol_slot, price_from_high, price_from_low,
            market_cap, float_shares, score, filters_matched, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
    """
    
    await self.db.executemany(query, batch_data)
```

**TABLA `scan_results` EN TIMESCALEDB**:

```sql
CREATE TABLE scan_results (
    time TIMESTAMPTZ NOT NULL,       -- Timestamp del scan
    symbol VARCHAR(10) NOT NULL,      -- Ticker symbol
    session VARCHAR(20),              -- Sesión de mercado
    price DOUBLE PRECISION,           -- Precio actual
    volume BIGINT,                    -- Volumen instantáneo
    volume_today BIGINT,              -- Volumen acumulado del día
    change_percent DOUBLE PRECISION,  -- Cambio %
    rvol DOUBLE PRECISION,            -- Relative Volume
    rvol_slot DOUBLE PRECISION,       -- RVOL del slot actual
    price_from_high DOUBLE PRECISION, -- % desde high
    price_from_low DOUBLE PRECISION,  -- % desde low
    market_cap BIGINT,                -- Market Cap
    float_shares BIGINT,              -- Float
    score DOUBLE PRECISION,           -- Score calculado
    filters_matched TEXT[],           -- Filtros que pasó
    metadata JSONB                    -- Datos adicionales (gaps, etc.)
);

-- TimescaleDB: Particionada por tiempo
SELECT create_hypertable('scan_results', 'time');
```

**EJEMPLO DE DATOS GUARDADOS**:

```sql
time                          | symbol | session    | price | volume_today | change_percent | rvol    | score  | rank
------------------------------|--------|------------|-------|--------------|----------------|---------|--------|-----
2025-11-03 05:30:00+00        | CRBU   | PRE_MARKET | 1.51  | 13856866     | 204.55         | 2493.73 | 2500.5 | 1
2025-11-03 05:30:00+00        | MSPR   | PRE_MARKET | 5.20  | 90815645     | 122.64         | 2787.5  | 2200.3 | 2
...
(337 rows para este scan)
```

**PROPÓSITO**:
- **Histórico**: Analizar cómo cambió un ticker en el tiempo
- **Backtesting**: Ver qué tickers aparecieron en qué momento
- **Analytics**: Calcular estadísticas de rendimiento
- **Auditoría**: Verificar funcionamiento del sistema

**QUERIES TÍPICOS**:

```sql
-- Ver todos los scans de CRBU hoy
SELECT time, price, change_percent, rvol, rank
FROM scan_results
WHERE symbol = 'CRBU'
  AND time >= CURRENT_DATE
ORDER BY time DESC;

-- Ver top gappers de hace 1 hora
SELECT symbol, change_percent, rvol
FROM scan_results
WHERE time >= NOW() - INTERVAL '1 hour'
  AND session = 'PRE_MARKET'
ORDER BY change_percent DESC
LIMIT 20;
```

---

## PASO 5: ACTUALIZAR ESTADÍSTICAS (líneas 151-157)

```python
elapsed = (time.time() - start) * 1000

self.total_scans += 1
self.total_tickers_scanned += len(enriched_snapshots)  # 11,905
self.total_tickers_filtered += len(scored_tickers)     # 337
self.last_scan_time = datetime.now()
self.last_scan_duration_ms = elapsed  # ~1,500ms
```

**ESTADÍSTICAS ACUMULADAS**:

```python
{
    "total_scans": 150,                    # Scans desde inicio
    "total_tickers_scanned": 1,785,750,    # 150 × 11,905
    "total_tickers_filtered": 50,550,      # 150 × 337
    "filter_rate": 2.8%,                   # 337/11,905 = 2.8%
    "last_scan_time": "2025-11-03T05:30:00Z",
    "last_scan_duration_ms": 1500,         # 1.5 segundos
    "current_session": "PRE_MARKET",
    "filters_loaded": 3,
    "filters_enabled": 2,
    "uptime_seconds": 4500                 # 75 minutos
}
```

**ACCESIBLE VÍA**:
- `GET /api/scanner/status` → Retorna estas stats

---

## PASO 6: CONSTRUIR RESULTADO (líneas 160-168)

```python
result = ScannerResult(
    timestamp=datetime.now(),
    session=self.current_session,
    total_universe_size=len(enriched_snapshots),  # 11,905
    filtered_count=len(scored_tickers),           # 337
    tickers=scored_tickers,
    filters_applied=[f.name for f in self.filters if f.enabled],
    scan_duration_ms=elapsed
)

return result
```

**OBJETO `ScannerResult`**:

```python
ScannerResult(
    timestamp="2025-11-03T05:30:00.500Z",
    session=MarketSession.PRE_MARKET,
    total_universe_size=11905,
    filtered_count=337,
    tickers=[... 337 ScannerTicker objects ...],
    filters_applied=["rvol_high", "price_range"],
    scan_duration_ms=1500
)
```

Este objeto se retorna al loop principal pero **NO se usa** (es solo para logging).

---

## 📤 RESUMEN: ¿A DÓNDE ENVÍA EL SCANNER?

### DESTINOS DE DATOS:

```
Scanner procesa y envía a:

1. MEMORIA (atributos de clase)
   ├─ last_filtered_tickers → 337 tickers completos
   ├─ last_rankings → Dict con 8 categorías × 20 tickers
   └─ sequence_numbers → Dict con sequence por categoría

2. REDIS - CACHÉS (Keys)
   ├─ scanner:filtered_complete:PRE_MARKET → 337 tickers completos
   ├─ scanner:category:gappers_up → Top 20
   ├─ scanner:category:winners → Top 20
   ├─ scanner:category:anomalies → Top 20
   ├─ scanner:category:high_volume → Top 20
   ├─ scanner:category:new_highs → Top 20
   ├─ scanner:category:new_lows → Top 20
   ├─ scanner:category:gappers_down → Top 20
   ├─ scanner:category:reversals → Top 20
   ├─ scanner:sequence:gappers_up → 120
   ├─ scanner:sequence:winners → 45
   └─ ... (sequence para cada categoría)

3. REDIS - STREAM (para WebSocket Server)
   └─ stream:ranking:deltas → Deltas incrementales

4. TIMESCALEDB (para histórico)
   └─ scan_results → 337 rows (un scan completo)

5. NO ENVÍA A:
   ❌ Otros servicios vía HTTP
   ❌ Message queues externos
   ❌ Event bus (aunque existe en código, no se usa)
```

---

## 🔄 FLUJO COMPLETO RESUMIDO

```
┌─────────────────────────────────────────────────────────────┐
│ SCANNER: run_scan() - FLUJO COMPLETO                        │
└─────────────────────────────────────────────────────────────┘

1. Lee snapshot:enriched:latest (11,905 tickers)
   └─ Verifica timestamp (no reprocesar)

2. Procesa tickers (líneas 127)
   └─ Filtra: 11,905 → 337 tickers

3. Limita resultados (líneas 129-131)
   └─ Max 1,000 (en este caso 337, sin cambios)

4. GUARDA EN 3 CACHÉS:
   
   A. Memoria (líneas 135-137)
      └─ self.last_filtered_tickers = [337 tickers]
   
   B. Redis Cache Completo (línea 140)
      └─ scanner:filtered_complete:PRE_MARKET = [337 tickers]
      └─ TTL: 60 segundos
   
   C. Redis por Categorías (línea 143 → 948-973)
      Para cada categoría:
      
      i. Categorizar tickers (línea 945)
         └─ gappers_up: 97 de 337 califican
         └─ Ordenar por change_percent
         └─ Top 20: [CRBU, MSPR, RAY, ...]
      
      ii. Calcular deltas (línea 959)
          └─ Comparar con last_rankings
          └─ Genera: [add, remove, update, rerank]
      
      iii. Emitir deltas (línea 967)
           └─ Incrementa sequence: 119 → 120
           └─ XADD stream:ranking:deltas
      
      iv. Guardar snapshot (línea 970)
          └─ scanner:category:gappers_up = [20 tickers]
          └─ scanner:sequence:gappers_up = 120
      
      v. Actualizar memoria (línea 973)
         └─ last_rankings["gappers_up"] = [20 tickers]

5. GUARDAR EN TIMESCALEDB (línea 149)
   └─ INSERT INTO scan_results (337 rows)
   └─ Batch insert (una sola query)

6. ACTUALIZAR ESTADÍSTICAS (líneas 151-157)
   └─ total_scans++
   └─ total_tickers_scanned += 11,905
   └─ total_tickers_filtered += 337

7. RETORNAR RESULTADO (líneas 160-168)
   └─ ScannerResult object
   └─ No se usa (solo para logging)

TIEMPO TOTAL: ~1.5 segundos
```

---

## 📊 DATOS QUE GUARDA POR CATEGORÍA

Cada categoría tiene:

### 1. Snapshot del Ranking (Redis)

```
Key: scanner:category:gappers_up
TTL: 1 hora
Contiene: Top 20 tickers COMPLETOS

[
  {
    "symbol": "CRBU",
    "timestamp": "2025-11-03T05:30:00Z",
    "price": 1.51,
    "volume_today": 13856866,
    "change_percent": 204.55,
    "rvol": 2493.73,
    "score": 2500.5,
    "rank": 1,
    "metadata": {
      "gaps": {...},
      "gap_size_classification": "EXTREME"
    },
    ... (todos los campos)
  },
  ... 19 más
]
```

### 2. Sequence Number (Redis)

```
Key: scanner:sequence:gappers_up
TTL: 24 horas
Value: 120

Usado para:
- Detectar gaps en frontend
- Sincronizar WebSocket
- Debugging
```

### 3. Último Ranking en Memoria

```python
self.last_rankings["gappers_up"] = [20 ScannerTicker objects]

Usado para:
- Calcular deltas en próxima iteración
- Evitar leer desde Redis
- Comparación rápida
```

---

## 🌊 SISTEMA DE DELTAS - ANÁLISIS PROFUNDO

### ¿POR QUÉ DELTAS Y NO SNAPSHOTS SIEMPRE?

**Escenario real**:

```
Iteración 1 (05:30:00):
gappers_up = [CRBU, MSPR, RAY, SMX, LGCL, ...]  (20 tickers)
→ WebSocket envía: SNAPSHOT completo (50KB)

Iteración 2 (05:30:30):
gappers_up = [CRBU, MSPR, RAY, SMX, ETHZW, ...]  (20 tickers)

Cambios:
- LGCL salió (rank 5)
- ETHZW entró (rank 6)
- RAY cambió de rank 3 a rank 4
- MSPR precio cambió de 5.20 a 5.25

→ WebSocket envía: DELTA (2KB)
[
  {type: "remove", ticker: "LGCL"},
  {type: "add", ticker: {...}, rank: 6},
  {type: "rerank", ticker: "RAY", old_rank: 3, new_rank: 4},
  {type: "update", ticker: "MSPR", data: {price: 5.25}}
]
```

**VENTAJAS DE DELTAS**:

1. **Bandwidth**: 2KB vs 50KB (25x menos)
2. **Procesamiento Frontend**: Solo actualiza lo que cambió
3. **UX**: Puede animar cambios suavemente
4. **Escalabilidad**: 100 clientes × 2KB vs 100 × 50KB

**DESVENTAJA**:

Si cliente pierde conexión o mensajes:
- Puede quedar desincronizado
- **Solución**: Sequence numbers + auto-resync

---

## 🔢 SEQUENCE NUMBERS - SISTEMA DE SINCRONIZACIÓN

### ¿Cómo Funcionan?

```python
# Scanner mantiene un contador por categoría
self.sequence_numbers = {
    "gappers_up": 120,
    "winners": 45,
    "anomalies": 102,
    ...
}

# Cada vez que emite deltas
sequence_numbers["gappers_up"] += 1  # 120 → 121

# Se incluye en el mensaje
delta_message = {
    "list": "gappers_up",
    "sequence": 121,
    "deltas": [...]
}
```

### Detección de Gaps en Frontend

```typescript
// Frontend mantiene último sequence recibido
lastSequence = {
  "gappers_up": 119
}

// Llega nuevo delta
message = {
  sequence: 121,  // ⚠️ Esperaba 120
  deltas: [...]
}

if (message.sequence !== lastSequence + 1) {
  // GAP DETECTADO (perdió mensaje 120)
  console.log("⚠️ Gap detected, requesting resync");
  sendMessage({action: "resync", list: "gappers_up"});
}
```

### Recovery Process

```
1. Frontend detecta gap (esperaba 120, recibió 121)
2. Envía mensaje: {action: "resync", list: "gappers_up"}
3. WebSocket Server recibe resync request
4. Lee scanner:category:gappers_up desde Redis
5. Envía snapshot COMPLETO con sequence actual (121)
6. Frontend reemplaza todos los datos
7. lastSequence = 121
8. Sincronizado ✅
```

---

## 📡 COMUNICACIÓN CON OTROS SERVICIOS

### ¿A qué servicios envía Scanner?

```
DIRECTAMENTE (via Redis):
✅ WebSocket Server
   └─ Lee: stream:ranking:deltas
   └─ Lee: scanner:category:{name}
   └─ Lee: scanner:sequence:{name}

INDIRECTAMENTE (via Redis cache):
✅ API Gateway (si existe)
   └─ Lee: scanner:filtered_complete:{session}
   └─ Para endpoints de consulta

✅ Frontend (via WebSocket)
   └─ Recibe deltas vía WebSocket Server

ALMACENAMIENTO:
✅ TimescaleDB
   └─ Tabla: scan_results
   └─ Para histórico y analytics

NO ENVÍA A:
❌ Analytics (Analytics → Scanner, no viceversa)
❌ Data Ingest (unidireccional)
❌ Historical Service
❌ Market Session
```

---

## 🗂️ METADATA - ¿DÓNDE SE GUARDA Y USA?

### ¿Scanner guarda metadatas?

**NO**. Scanner **CONSUME** metadatas pero **NO las crea ni modifica**.

**FLUJO DE METADATAS**:

```
Historical Service:
  └─ Carga desde Polygon: ticker details, market cap, sector
  └─ GUARDA en:
      ├─ TimescaleDB: ticker_metadata (persistente)
      └─ Redis: metadata:ticker:{symbol} (caché 24h)

Scanner:
  └─ LEE de Redis: metadata:ticker:{symbol}
  └─ MGET batch (11,905 metadatas en una operación)
  └─ USA para:
      ├─ Filtrar por sector/industry
      ├─ Enriquecer ScannerTicker
      └─ Guardar en scan_results (campo metadata JSONB)
```

**METADATA ENRICHMENT EN SCANNER**:

Cuando Scanner construye un `ScannerTicker`:

```python
ticker = ScannerTicker(
    symbol="CRBU",
    price=1.51,
    rvol=2493.73,
    ...
    sector=metadata.sector,        # De metadata
    industry=metadata.industry,    # De metadata
    market_cap=metadata.market_cap, # De metadata
    float_shares=metadata.float_shares,
    metadata={                     # Metadata ADICIONAL generada
        "gaps": {
            "gap_from_prev_close": 204.55,
            "gap_from_open": -6.25,
            ...
        },
        "gap_size_classification": "EXTREME",
        "gap_metrics": {...}
    }
)
```

**ENTONCES**:

✅ Scanner usa metadatas de Historical  
✅ Scanner AGREGA su propia metadata (gaps, etc.)  
✅ Scanner guarda TODO en scan_results  
❌ Scanner NO modifica las metadatas originales

---

## 🔄 ITERACIONES: CÓMO SE ACUMULA

### Iteración 1 (05:30:00)

```
1. Procesa snapshot → 337 tickers filtrados
2. Categoriza:
   - gappers_up: 20 tickers (CRBU, MSPR, RAY...)
   - winners: 20 tickers
   - anomalies: 20 tickers
   - ... (8 categorías con datos)

3. NO hay last_rankings → Emite SNAPSHOT completo
   └─ XADD stream:ranking:deltas: {type: "snapshot", list: "gappers_up", data: [20 tickers]}
   └─ Sequence = 1

4. Guarda en Redis:
   └─ scanner:category:gappers_up = [20 tickers]
   └─ scanner:sequence:gappers_up = 1

5. Guarda en memoria:
   └─ last_rankings["gappers_up"] = [20 tickers]
```

### Iteración 2 (05:30:30)

```
1. Procesa snapshot → 341 tickers filtrados (+4)
2. Categoriza:
   - gappers_up: 20 tickers (CRBU, MSPR, ETHZW, RAY...)

3. SÍ hay last_rankings → Calcula DELTAS
   
   Old: [CRBU, MSPR, RAY, SMX, LGCL, ...]
   New: [CRBU, MSPR, ETHZW, RAY, SMX, ...]
   
   Deltas:
   - remove: LGCL (salió del top 20)
   - add: ETHZW (entró al top 20)
   - rerank: RAY (3→4)

4. Emite DELTAS:
   └─ XADD stream:ranking:deltas: {sequence: 2, deltas: [remove, add, rerank]}

5. Guarda en Redis:
   └─ scanner:category:gappers_up = [20 tickers nuevos] (SOBRESCRIBE)
   └─ scanner:sequence:gappers_up = 2 (SOBRESCRIBE)

6. Actualiza memoria:
   └─ last_rankings["gappers_up"] = [20 tickers nuevos]
```

### Iteración 3 (05:31:00)

```
1. Procesa snapshot → 339 tickers (-2)
2. Categoriza → gappers_up: 20 tickers
3. Calcula deltas (basado en iteración 2)
4. Emite: sequence = 3
5. Guarda y actualiza
```

**OBSERVACIÓN IMPORTANTE**:

Cada iteración es **INDEPENDIENTE** del snapshot de Polygon:
- No depende de qué tickers llegaron en iteraciones pasadas
- Siempre procesa el snapshot COMPLETO más reciente
- Rankings se recalculan desde cero cada vez

---

## ⚙️ CONFIGURACIONES CRÍTICAS

### TTLs en Redis

```
scanner:filtered_complete:{session}  → 60 segundos
  Razón: Se refresca cada 30s, 60s da margen

scanner:category:{name}              → 3600 segundos (1 hora)
  Razón: Para recovery si WebSocket cae

scanner:sequence:{name}              → 86400 segundos (24 horas)
  Razón: Sequence debe persistir más tiempo

stream:ranking:deltas                → maxlen 10,000 mensajes
  Razón: ~5 horas de historial (si se emite cada 30s)
```

### Por qué estos TTLs

**TTL corto (60s)**:
- Datos que cambian rápido
- Se regeneran constantemente
- Queremos que expiren si servicio cae

**TTL largo (1h - 24h)**:
- Datos para recovery
- Sequence numbers (no queremos resetear)
- Snapshots para nuevos clientes WebSocket

---

## 🔍 VERIFICACIÓN DEL FLUJO

### Comandos para Verificar Cada Paso

```bash
# 1. Ver tickers filtrados completos
docker exec tradeul_redis redis-cli GET "scanner:filtered_complete:PRE_MARKET" | python3 -m json.tool | head -100

# 2. Ver cada categoría
for cat in gappers_up winners anomalies high_volume; do
  echo "=== $cat ==="
  docker exec tradeul_redis redis-cli GET "scanner:category:$cat" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total: {len(d)}'); [print(f'{i+1}. {t[\"symbol\"]}') for i,t in enumerate(d[:5])]"
done

# 3. Ver sequence numbers
docker exec tradeul_redis redis-cli MGET \
  "scanner:sequence:gappers_up" \
  "scanner:sequence:winners" \
  "scanner:sequence:anomalies"

# 4. Ver últimos deltas emitidos
docker exec tradeul_redis redis-cli XREVRANGE stream:ranking:deltas + - COUNT 5

# 5. Ver datos en TimescaleDB
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c \
  "SELECT time, symbol, change_percent, rvol, rank FROM scan_results WHERE time > NOW() - INTERVAL '5 minutes' ORDER BY time DESC LIMIT 10;"

# 6. Ver logs del scanner
docker logs tradeul_scanner --tail 100 | grep -E "Emitted ranking deltas|Discovery scan completed"
```

---

## 🎭 EJEMPLO COMPLETO: UN SCAN DE PRINCIPIO A FIN

### T=0: Inicio del Scan

```
05:30:00.000 - Scanner inicia run_scan()
```

### T+100ms: Lee snapshot

```
05:30:00.100 - Lee snapshot:enriched:latest
Resultado: 11,905 tickers del timestamp 2025-11-03T05:29:58Z
```

### T+200ms: Verifica timestamp

```
05:30:00.200 - Compara timestamp
last_snapshot_timestamp = "2025-11-03T05:29:28Z"
nuevo_timestamp = "2025-11-03T05:29:58Z"
→ DIFERENTE → Continúa procesamiento
```

### T+300ms - T+1200ms: Procesa snapshots

```
05:30:00.300 - Inicia _process_snapshots_optimized()

  05:30:00.350 - MGET 11,905 metadatas
  Resultado: 5,823 metadatas encontradas
  
  05:30:00.400 - Procesa ticker por ticker
  
  TICKER 1: CRBU
    ✓ Tiene metadata
    ✓ Price = 1.51 (> $1)
    ✓ Volume = 13,856,866 (> 100,000)
    ✓ RVOL = 2493.73 (> 1.5)
    ✓ PASA filtros
    → Score = 2500.5
    → Agrega a filtered_and_scored
  
  TICKER 2: XYZ
    ✗ No tiene metadata
    → Descartado (continue)
  
  TICKER 3: ABC
    ✓ Tiene metadata
    ✓ Price = 5.00
    ✓ Volume = 50,000
    ✗ RVOL = 0.8 (< 1.5)
    ✗ NO PASA filtros
    → Descartado (continue)
  
  ... (11,902 tickers más)
  
  05:30:01.100 - Completa procesamiento
  Resultado: 337 tickers filtrados
  
  05:30:01.150 - Ordena por score
  05:30:01.200 - Asigna ranks (1-337)
```

### T+1250ms: Guarda cachés

```
05:30:01.250 - Guarda en memoria
  self.last_filtered_tickers = [337 tickers]
  
05:30:01.300 - Guarda en Redis
  SET scanner:filtered_complete:PRE_MARKET = [337 tickers]
```

### T+1300ms - T+1450ms: Categoriza

```
05:30:01.300 - Categoriza 337 tickers
  
  Procesa cada categoría:
  
  GAPPERS_UP:
    - Filtra: 97 tickers con change >= 2%
    - Ordena por change_percent desc
    - Top 20: [CRBU +204%, MSPR +122%, RAY +53%, ...]
  
  WINNERS:
    - Filtra: 45 tickers con change >= 5%
    - Ordena por change_percent desc
    - Top 20: [CRBU, MSPR, RAY, ...]
  
  ANOMALIES:
    - Filtra: 89 tickers con RVOL >= 3.0
    - Ordena por RVOL desc
    - Top 20: [MSPR 2787x, CRBU 2493x, ...]
  
  ... (8 categorías más)
  
  05:30:01.450 - Categorización completa
```

### T+1450ms - T+1480ms: Calcula y emite deltas

```
05:30:01.450 - Para cada categoría:

  GAPPERS_UP:
    Old (seq 119): [CRBU, MSPR, RAY, SMX, LGCL, ...]
    New (seq 120): [CRBU, MSPR, RAY, SMX, ETHZW, ...]
    
    Deltas calculados:
    - remove: LGCL
    - add: ETHZW (rank 6)
    - rerank: RAY (3→4)
    
    05:30:01.455 - XADD stream:ranking:deltas
    Mensaje: {
      list: "gappers_up",
      sequence: 120,
      timestamp: "2025-11-03T05:30:01.455Z",
      changes: 3,
      deltas: "[{remove LGCL}, {add ETHZW}, {rerank RAY}]"
    }
    
    05:30:01.460 - SET scanner:category:gappers_up = [20 tickers]
    05:30:01.462 - SET scanner:sequence:gappers_up = 120
    05:30:01.465 - last_rankings["gappers_up"] = [20 tickers]
  
  WINNERS:
    [mismo proceso...]
  
  ... (7 categorías más)

05:30:01.480 - Emisión de deltas completa
```

### T+1500ms: Guarda en TimescaleDB

```
05:30:01.500 - Batch INSERT
  INSERT INTO scan_results VALUES (...), (...), ... (337 rows)
  
05:30:01.520 - Insert completo
```

### T+1530ms: Finaliza

```
05:30:01.530 - Actualiza estadísticas
  total_scans = 120
  total_tickers_scanned = 1,428,600
  total_tickers_filtered = 40,440
  
05:30:01.540 - Retorna ScannerResult

05:30:01.550 - Log final:
  "🔍 Discovery scan completed: filtered_count=337, total_scanned=11905, duration_sec=1.55"
```

---

## 🌊 PROPAGACIÓN A WEBSOCKET Y FRONTEND

### WebSocket Server (consume deltas)

```javascript
// Consumer corriendo en background

XREAD stream:ranking:deltas BLOCK 1000

Mensaje recibido:
{
  list: "gappers_up",
  sequence: 120,
  deltas: "[...]"
}

// Broadcast a todos los clientes suscritos
for (connection of connections.values()) {
  if (connection.subscriptions.has("gappers_up")) {
    
    // Verificar sequence
    clientSeq = connection.sequence_numbers.get("gappers_up")
    
    if (sequence > clientSeq + 1) {
      // Gap → Enviar snapshot completo
      sendSnapshot(connection, "gappers_up")
    } else {
      // Enviar delta
      ws.send(JSON.stringify({
        type: "delta",
        list: "gappers_up",
        sequence: 120,
        changes: JSON.parse(deltas)
      }))
      
      connection.sequence_numbers.set("gappers_up", 120)
    }
  }
}
```

### Frontend (aplica deltas)

```typescript
// Recibe mensaje WebSocket
message = {
  type: "delta",
  list: "gappers_up",
  sequence: 120,
  changes: [
    {type: "remove", ticker: "LGCL"},
    {type: "add", ticker: {...}, rank: 6},
    {type: "rerank", ticker: "RAY", old_rank: 3, new_rank: 4}
  ]
}

// Verificar sequence
if (message.sequence !== lastSequence + 1) {
  requestResync()
  return
}

// Aplicar cada delta
setTickers(prevTickers => {
  let newTickers = [...prevTickers]
  
  for (delta of message.changes) {
    if (delta.type === "remove") {
      newTickers = newTickers.filter(t => t.symbol !== "LGCL")
      console.log("➖ Removed LGCL")
    }
    
    if (delta.type === "add") {
      newTickers.push(delta.ticker)
      console.log("➕ Added ETHZW at rank 6")
    }
    
    if (delta.type === "rerank") {
      const idx = newTickers.findIndex(t => t.symbol === "RAY")
      newTickers[idx].rank = 4
      console.log("↕️ Reranked RAY: 3 → 4")
    }
  }
  
  return newTickers
})

setLastSequence(120)
```

---

## 📊 MÉTRICAS DE PERFORMANCE

### Por Scan (cada 30 segundos)

```
Lectura snapshot:           100ms
Procesamiento 11,905:       900ms
  ├─ MGET metadatas:        50ms
  ├─ Filtrado inline:       800ms
  └─ Ordenar + rank:        50ms
Categorización:             150ms
  ├─ 337 tickers → 8 cats:  100ms
  └─ Ordenar × 8:           50ms
Cálculo deltas:             80ms (8 categorías)
Emisión deltas:             70ms (8 XADD)
Guardar Redis:              100ms (16 SETs)
Guardar TimescaleDB:        100ms (1 batch INSERT)

TOTAL: ~1,500ms (1.5 segundos)
```

### Throughput

```
Tickers procesados/segundo: 11,905 / 1.5 = 7,937 tickers/s
Tickers filtrados/scan: 337
Categorías generadas/scan: 8
Rankings guardados/scan: 8 × 20 = 160 tickers
Deltas emitidos/scan: 8 mensajes
Rows en BD/scan: 337
```

---

## 🔧 PUNTOS CRÍTICOS Y POSIBLES PROBLEMAS

### 1. Metadatas Faltantes

**Problema**:
```
Si metadata:ticker:MNOV no existe en Redis:
→ Línea 275: if not metadata: continue
→ MNOV se descarta aunque tenga buen RVOL
```

**Solución Actual**:
- Warmup carga 11,899 metadatas con TTL 24h
- NO se borran después (bug arreglado)

**Verificación**:
```bash
# Ver cuántas metadatas hay
docker exec tradeul_redis redis-cli KEYS "metadata:ticker:*" | wc -l

# Ver metadata específica
docker exec tradeul_redis redis-cli GET "metadata:ticker:MNOV"
```

### 2. Timestamp Synchronization

**Problema Potencial**:
```
Si Scanner procesa MUY rápido:
- Analytics guarda snapshot a las 05:30:00.500
- Scanner lo procesa a las 05:30:00.600
- Data Ingest actualiza a las 05:30:01.000
- Scanner corre otra vez a las 05:30:30.000
- Snapshot sigue siendo 05:30:01.000
- ¿Procesa el mismo snapshot?
```

**Solución Implementada**:
```python
if snapshot_timestamp == self.last_snapshot_timestamp:
    return []  # No procesar
```

**Verificación**:
```bash
# Logs deben mostrar "Reading complete enriched snapshot" solo cuando hay nuevo
docker logs tradeul_scanner | grep "Reading complete" | uniq -c
# No debe repetirse el mismo timestamp
```

### 3. Sequence Number Gaps

**Problema Potencial**:
```
Scanner emite: seq 118, 119, 120
WebSocket recibe: 118, 119, (se pierde 120)
Cliente recibe: 118, 119, 121
→ Gap detectado
```

**Solución**:
- Frontend detecta gap (121 !== 119 + 1)
- Solicita resync
- WebSocket envía snapshot completo
- Cliente se sincroniza

**Verificación**:
```
Frontend logs:
✅ "🔄 Received DELTA {sequence: 119}"
✅ "🔄 Received DELTA {sequence: 120}"
❌ "⚠️ Sequence gap detected (expected 120, got 122)"
→ Si ves esto, hay problema en WebSocket
```

### 4. Categorías Vacías

**Problema**:
```
En premarket temprano:
- No hay tickers con change >= 5% → winners = []
- No hay new_highs → new_highs = []
```

**Comportamiento**:
```python
Línea 232 (scanner_categories.py):
if ranked:  # Solo si hay tickers
    results[category.value] = ranked
```

Si categoría vacía → NO se incluye en results

**Verificación**:
```bash
# Ver qué categorías tienen datos
docker exec tradeul_redis redis-cli KEYS "scanner:category:*"
```

---

## 📝 CONCLUSIONES

### ¿Qué hace Scanner POST-filtrado?

1. ✅ **Guarda en 3 cachés** (memoria, Redis completo, Redis por categoría)
2. ✅ **Categoriza** en 8-11 listas diferentes
3. ✅ **Calcula deltas** comparando con iteración anterior
4. ✅ **Emite deltas** al stream para WebSocket
5. ✅ **Guarda snapshots** en Redis para recovery
6. ✅ **Persiste en BD** para histórico
7. ✅ **Actualiza estadísticas** para monitoring

### Servicios que consumen sus datos

```
CONSUMERS:
✅ WebSocket Server → Lee deltas y snapshots
✅ Frontend → Recibe vía WebSocket
✅ API Gateway → Lee caché completo
✅ TimescaleDB → Para queries históricos

NO CONSUMERS:
❌ Analytics (no lee de Scanner)
❌ Data Ingest (no lee de Scanner)
```

### Metadata: ¿Quién crea qué?

```
Historical Service CREA:
- ticker_metadata (BD)
- metadata:ticker:{symbol} (Redis)
Campos: sector, industry, market_cap, avg_volume_30d

Scanner AGREGA:
- metadata.gaps (calculado)
- metadata.gap_size_classification
- metadata.gap_metrics

Scanner GUARDA TODO en:
- scan_results.metadata (JSONB)
```

---

**Documento completo**: Scanner Post-Filtrado  
**Versión**: Post-refactor snapshot cache  
**Estado**: Producción funcional
