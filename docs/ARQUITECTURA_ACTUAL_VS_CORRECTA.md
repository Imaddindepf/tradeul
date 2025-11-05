# 🚨 ANÁLISIS CRÍTICO: Arquitectura Actual vs. Arquitectura Correcta

**Fecha**: 30 de Octubre, 2025  
**Estado**: ❌ SISTEMA MAL DISEÑADO - NECESITA REFACTOR COMPLETO

---

## 🎯 RESUMEN EJECUTIVO

**El problema**: El código actual implementa un **patrón de polling REST + WebSocket híbrido** que NO es lo que se diseñó. Esto causa:

- ❌ Filas que desaparecen/reaparecen innecesariamente
- ❌ Re-renders completos cada 10 segundos
- ❌ Frontend calculando qué suscribir/desuscribir
- ❌ No hay snapshot inicial + deltas incrementales
- ❌ Ineficiencia masiva: procesar 11,000 tickers cada 3 segundos

**La solución**: Implementar **arquitectura snapshot + deltas** donde:

- ✅ Backend calcula rankings y emite snapshot inicial
- ✅ Backend emite deltas incrementales: "añadir", "actualizar", "eliminar", "rerank"
- ✅ Frontend SOLO renderiza, no calcula ni compara
- ✅ Backend gestiona auto-suscripción de tickers "hot"
- ✅ Discovery loop lento (30 seg) + Hot loop rápido (100ms)

---

## 📋 TABLA DE CONTENIDOS

1. [Errores Críticos en el Código Actual](#1-errores-críticos-en-el-código-actual)
2. [Arquitectura Actual (Incorrecta)](#2-arquitectura-actual-incorrecta)
3. [Arquitectura Correcta (Diseño Original)](#3-arquitectura-correcta-diseño-original)
4. [Comparación Punto por Punto](#4-comparación-punto-por-punto)
5. [Plan de Refactor](#5-plan-de-refactor)

---

## 1. 🚨 ERRORES CRÍTICOS EN EL CÓDIGO ACTUAL

### Error #1: Frontend hace POLLING cada 10 segundos

**Archivo**: `frontend/components/scanner/GappersTable.tsx`  
**Líneas**: 99-105

```typescript
// ❌ ESTO NO DEBERÍA EXISTIR
useEffect(() => {
  const interval = setInterval(() => {
    fetchFilteredTickers(); // ← REEMPLAZA TODA LA TABLA
  }, 10000); // Cada 10 segundos

  return () => clearInterval(interval);
}, [ws.isConnected]);
```

**Por qué está mal**:

- Reemplaza completamente `tickersMap` y `tickerOrder` cada 10 segundos
- Causa que filas desaparezcan y reaparezcan aunque NO hayan salido del ranking
- React compara por referencia: nuevo Map = re-render completo
- Frontend está haciendo el trabajo que debería hacer el backend

**Lo correcto**:

- Fetch SOLO al montar (snapshot inicial)
- Después, TODO por WebSocket (deltas incrementales)

---

### Error #2: Scanner NO emite deltas, solo guarda estado completo

**Archivo**: `services/scanner/scanner_engine.py`  
**Líneas**: 130-150

```python
# Scanner hace esto:
async def run_scan():
    # 1. Procesa ~11,000 snapshots
    enriched = await _enrich_and_calculate(snapshots)

    # 2. Filtra
    filtered = await _apply_filters(enriched)

    # 3. Rankea
    scored = await _score_and_rank(filtered)

    # 4. Guarda en Redis (COMPLETO, no deltas)
    await redis.set('scanner:category:gappers_up', scored)

    # 5. Publica a stream (SOLO top 50, sin contexto de cambios)
    await redis.xadd('tickers:filtered', ...)
```

**Por qué está mal**:

- No calcula QUÉ cambió vs. el ranking anterior
- No emite mensajes tipo:
  - `{"action": "add", "symbol": "TSLA", "rank": 1}`
  - `{"action": "remove", "symbol": "NVDA"}`
  - `{"action": "rerank", "symbol": "AAPL", "old_rank": 5, "new_rank": 2}`
- Frontend tiene que comparar arrays completos para detectar cambios

**Lo correcto**:

```python
async def run_scan():
    new_ranking = await calculate_ranking()
    old_ranking = self.last_ranking

    # Calcular deltas
    deltas = calculate_deltas(old_ranking, new_ranking)
    # → [
    #     {"action": "add", "symbol": "TSLA", "rank": 1, "data": {...}},
    #     {"action": "remove", "symbol": "NVDA"},
    #     {"action": "update", "symbol": "AAPL", "rank": 2, "data": {...}}
    #   ]

    # Emitir deltas a stream
    await emit_ranking_deltas(deltas)

    # Guardar para próxima comparación
    self.last_ranking = new_ranking
```

---

### Error #3: WebSocket Server solo transmite aggregates individuales

**Archivo**: `services/websocket_server/src/index.js`  
**Líneas**: 136-243

```javascript
// WebSocket Server hace esto:
async function processRedisStreams() {
  // Solo lee aggregates individuales
  const messages = await redis.xreadgroup(
    'GROUP', 'websocket_server_agg', 'ws_consumer_1',
    'STREAMS', 'stream:realtime:aggregates', '>'
  );

  // Broadcast ticker por ticker
  for (const [messageId, fields] of messages) {
    const symbol = data.symbol;
    broadcastToSubscribers(symbol, {
      type: 'aggregate',
      symbol: symbol,
      data: {...}  // Solo precio, volumen
    });
  }
}
```

**Por qué está mal**:

- No transmite cambios en el RANKING
- No envía snapshot inicial al conectar
- No tiene número de secuencia
- Frontend recibe 100 mensajes/seg pero no sabe si el ranking cambió

**Lo correcto**:

```javascript
// Al conectar cliente:
ws.on('connection', async (ws) => {
  // 1. Enviar snapshot inicial
  const snapshot = await getInitialSnapshot('gappers_up');
  ws.send(JSON.stringify({
    type: 'snapshot',
    list: 'gappers_up',
    sequence: 12345,
    rows: [
      {rank: 1, symbol: 'TSLA', price: 250.5, gap: 5.8, ...},
      {rank: 2, symbol: 'AAPL', price: 178.5, gap: 5.6, ...},
      // ... top 200
    ]
  }));
});

// Después, solo deltas:
async function processRankingChanges() {
  const deltas = await redis.xreadgroup(
    'STREAMS', 'stream:ranking:deltas', '>'
  );

  for (const delta of deltas) {
    ws.send(JSON.stringify({
      type: 'delta',
      list: 'gappers_up',
      sequence: 12346,
      changes: [
        {action: 'add', rank: 1, symbol: 'TSLA', data: {...}},
        {action: 'remove', symbol: 'NVDA'},
        {action: 'update', rank: 2, symbol: 'AAPL', data: {...}}
      ]
    }));
  }
}
```

---

### Error #4: Frontend gestiona suscripciones manualmente

**Archivo**: `frontend/components/scanner/GappersTable.tsx`  
**Líneas**: 67-87

```typescript
// Frontend hace esto:
const fetchFilteredTickers = async () => {
  const data = await getCategoryTickers("gappers_up", 200);

  // ❌ Frontend compara arrays
  const oldSymbols = new Set(tickerOrder);
  const newSymbols = new Set(newOrder);

  const symbolsToRemove = Array.from(oldSymbols).filter(
    (s) => !newSymbols.has(s)
  );
  const symbolsToAdd = Array.from(newSymbols).filter((s) => !oldSymbols.has(s));

  // ❌ Frontend decide qué suscribir
  if (symbolsToRemove.length > 0) {
    ws.unsubscribe(symbolsToRemove);
  }
  if (symbolsToAdd.length > 0) {
    ws.subscribe(symbolsToAdd);
  }
};
```

**Por qué está mal**:

- Frontend NO debería saber qué tickers suscribir
- Lógica de suscripción está en el cliente (debería estar en servidor)
- Causa race conditions y estado inconsistente

**Lo correcto**:

```typescript
// Frontend NO gestiona suscripciones
// Backend auto-suscribe tickers "hot" cuando entran al ranking
// Frontend solo RECIBE deltas y los aplica
```

---

### Error #5: Discovery Loop demasiado agresivo (3 segundos, 11,000 tickers)

**Archivo**: `services/data_ingest/snapshot_consumer.py`  
**Archivo**: `services/scanner/main.py`

```python
# data_ingest hace esto:
await asyncio.sleep(3)  # ❌ Cada 3 segundos, 11,000 tickers

# scanner hace esto:
await asyncio.sleep(settings.snapshot_interval)  # ❌ 10 segundos
```

**Por qué está mal**:

- Procesar 11,000 tickers cada 3 segundos es LOCURA
- Scanner procesa TODO cada 10 segundos
- No hay distinción entre "discovery" (lento) y "mantenimiento" (rápido)
- Enorme desperdicio de CPU para tickers que NO están en rankings

**Lo correcto**:

```python
# DISCOVERY LOOP (30 segundos)
async def discovery_loop():
    while True:
        # Procesar TODOS los tickers del mercado
        # Para DETECTAR nuevos líderes
        await process_full_universe()
        await asyncio.sleep(30)

# HOT LOOP (100ms - 1 segundo)
async def hot_loop():
    while True:
        # Procesar SOLO tickers en rankings activos
        # Para mantener datos frescos
        await process_hot_tickers()
        await asyncio.sleep(0.1)  # 100ms
```

---

### Error #6: No hay número de secuencia ni manejo de reconexión

**Archivos**: Todos

**Por qué está mal**:

- Si el WebSocket se desconecta, no hay forma de resincronizar
- No se detectan mensajes perdidos
- Al reconectar, frontend no sabe desde qué punto continuar

**Lo correcto**:

```javascript
// Cada mensaje debe tener sequence number
{
  type: 'delta',
  sequence: 12346,  // ← Monotónicamente creciente
  changes: [...]
}

// Frontend detecta gap:
if (message.sequence !== lastSequence + 1) {
  // Salto detectado, solicitar resync
  ws.send({action: 'resync', last_sequence: lastSequence});
}
```

---

## 2. 🏗️ ARQUITECTURA ACTUAL (INCORRECTA)

### Flujo Actual

```
┌─────────────────────────────────────────────────────────────────┐
│  PASO 1: Polygon Snapshots (cada 3 seg)                         │
│  data_ingest → stream:ingest:snapshots                           │
│  📊 ~11,000 tickers                                              │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 2: Scanner Procesa TODO (cada 10 seg)                     │
│  1. Lee 11,000 snapshots                                         │
│  2. Enriquece con metadata                                       │
│  3. Filtra                                                       │
│  4. Rankea                                                       │
│  5. Guarda COMPLETO en Redis                                     │
│  ❌ NO calcula deltas                                            │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 3: Frontend POLLING (cada 10 seg)                         │
│  GET /api/categories/gappers_up                                  │
│  ❌ REEMPLAZA toda la tabla                                      │
│  ❌ Compara arrays para detectar cambios                         │
│  ❌ Decide qué suscribir/desuscribir                             │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 4: Polygon WS                                              │
│  Frontend → suscribe manualmente                                 │
│  Polygon WS → emite aggregates                                   │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 5: WebSocket Server                                        │
│  Transmite aggregates individuales                               │
│  ❌ NO transmite cambios de ranking                              │
│  ❌ NO envía snapshot inicial                                    │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 6: Frontend Actualiza Celdas                              │
│  Actualiza precio, volumen                                       │
│  ❌ Cada 10 seg: REEMPLAZA todo                                  │
│  ❌ Filas desaparecen/reaparecen                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Problemas

1. **Demasiado trabajo**: 11,000 tickers cada 3 seg
2. **Re-renders innecesarios**: Reemplaza tabla cada 10 seg
3. **Lógica en cliente**: Frontend calcula cambios
4. **Sin deltas**: No hay sistema incremental
5. **Sin reconexión**: No hay sequence numbers
6. **Ineficiente**: No distingue hot/cold

---

## 3. ✅ ARQUITECTURA CORRECTA (DISEÑO ORIGINAL)

### Flujo Correcto

```
┌─────────────────────────────────────────────────────────────────┐
│  DISCOVERY LOOP (cada 30 seg) - FRÍO                            │
│  ───────────────────────────────────────────────────────────────│
│  1. Polygon Snapshots: ~11,000 tickers                           │
│  2. Scanner procesa TODO el universo                             │
│  3. Detecta NUEVOS líderes que entran a rankings                 │
│  4. PROMOCIONA tickers a "hot set"                               │
│  5. DEGRADA tickers que salen de rankings                        │
│  6. Emite DELTAS: añadir/remover/rerank                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  HOT LOOP (cada 100ms - 1 seg) - CALIENTE                       │
│  ───────────────────────────────────────────────────────────────│
│  1. Polygon WS: SOLO tickers hot (~50-200)                       │
│  2. Scanner actualiza SOLO hot tickers                           │
│  3. Recalcula rankings rápidamente                               │
│  4. Emite DELTAS incrementales (si hay cambios)                  │
│  5. Auto-gestiona suscripciones Polygon WS                       │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  EMISIÓN DE DELTAS                                               │
│  ───────────────────────────────────────────────────────────────│
│  stream:ranking:deltas → WebSocket Server                        │
│                                                                   │
│  Tipos de mensajes:                                              │
│  • snapshot (inicial, o después de reconexión)                   │
│  • delta (cambios incrementales)                                 │
│                                                                   │
│  Cada mensaje tiene:                                             │
│  • type: 'snapshot' | 'delta'                                    │
│  • list: 'gappers_up' | 'momentum_up' | ...                      │
│  • sequence: número monotónicamente creciente                    │
│  • changes: [{action, rank, symbol, data}, ...]                  │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  WEBSOCKET SERVER                                                │
│  ───────────────────────────────────────────────────────────────│
│  Al conectar:                                                    │
│  1. Envía snapshot inicial con top 200                           │
│  2. Incluye sequence number inicial                              │
│                                                                   │
│  Continuamente:                                                  │
│  3. Lee stream:ranking:deltas                                    │
│  4. Conflation: agrupa cambios en ventanas de 100ms              │
│  5. Broadcast a clientes suscritos                               │
│                                                                   │
│  Manejo de reconexión:                                           │
│  6. Cliente envía last_sequence conocido                         │
│  7. Servidor envía snapshot si gap > threshold                   │
│  8. Servidor envía deltas pendientes si gap pequeño              │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (React)                                                │
│  ───────────────────────────────────────────────────────────────│
│  Al montar:                                                      │
│  1. Conecta WebSocket                                            │
│  2. Recibe snapshot inicial                                      │
│  3. Renderiza tabla (UNA VEZ)                                    │
│                                                                   │
│  Continuamente:                                                  │
│  4. Recibe deltas por WebSocket                                  │
│  5. ACUMULA cambios en buffer (RAF o setInterval 16ms)           │
│  6. Aplica cambios en lote:                                      │
│     • action: 'add' → Inserta fila en posición rank             │
│     • action: 'remove' → Remueve fila                            │
│     • action: 'update' → Actualiza datos de fila                 │
│     • action: 'rerank' → Mueve fila a nueva posición            │
│  7. React re-renderiza SOLO filas afectadas                      │
│                                                                   │
│  Reconexión:                                                     │
│  8. Detecta desconexión                                          │
│  9. Al reconectar, envía last_sequence                           │
│  10. Recibe snapshot o deltas pendientes                         │
│  11. Resincroniza estado                                         │
│                                                                   │
│  ❌ NUNCA hace polling REST                                      │
│  ❌ NUNCA compara arrays                                         │
│  ❌ NUNCA calcula rankings                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 📊 COMPARACIÓN PUNTO POR PUNTO

| Aspecto                | Actual (❌ Mal)           | Correcto (✅ Bien)           |
| ---------------------- | ------------------------- | ---------------------------- |
| **Frontend fetch**     | Polling cada 10 seg       | SOLO snapshot inicial        |
| **Actualizaciones**    | Reemplaza tabla completa  | Aplica deltas incrementales  |
| **Cálculo de cambios** | Frontend compara arrays   | Backend calcula deltas       |
| **Suscripciones**      | Frontend decide           | Backend auto-gestiona        |
| **Discovery**          | 11,000 tickers cada 3 seg | 11,000 tickers cada 30 seg   |
| **Hot loop**           | No existe                 | 100ms para hot tickers       |
| **Mensajes WS**        | Solo aggregates           | snapshot + deltas + sequence |
| **Reconexión**         | No hay manejo             | Resync con sequence numbers  |
| **Re-renders**         | Toda tabla cada 10 seg    | Solo filas afectadas         |
| **CPU Backend**        | 100% todo el tiempo       | 20% discovery + 10% hot loop |
| **CPU Frontend**       | Alto (comparaciones)      | Bajo (solo aplicar deltas)   |

---

## 5. 📝 PLAN DE REFACTOR

### Fase 1: Backend - Sistema de Deltas

#### 1.1 Modificar Scanner Engine

**Archivo**: `services/scanner/scanner_engine.py`

```python
class ScannerEngine:
    def __init__(...):
        # Nuevo: tracking de rankings anteriores
        self.last_rankings: Dict[str, List[ScannerTicker]] = {}
        self.sequence_numbers: Dict[str, int] = {}

    async def run_scan(self):
        # Calcular nuevo ranking
        new_ranking = await calculate_ranking()

        # Obtener ranking anterior
        old_ranking = self.last_rankings.get('gappers_up', [])

        # Calcular deltas
        deltas = self.calculate_ranking_deltas(
            old_ranking,
            new_ranking,
            list_name='gappers_up'
        )

        # Emitir deltas a stream
        if deltas:
            await self.emit_ranking_deltas('gappers_up', deltas)

        # Guardar para próxima iteración
        self.last_rankings['gappers_up'] = new_ranking

    def calculate_ranking_deltas(
        self,
        old: List[ScannerTicker],
        new: List[ScannerTicker],
        list_name: str
    ) -> List[Dict]:
        """
        Calcula cambios entre rankings

        Returns:
            [
                {"action": "add", "rank": 1, "symbol": "TSLA", "data": {...}},
                {"action": "remove", "symbol": "NVDA"},
                {"action": "update", "rank": 2, "symbol": "AAPL", "data": {...}},
                {"action": "rerank", "symbol": "GOOGL", "old_rank": 5, "new_rank": 3}
            ]
        """
        deltas = []

        # Convertir a dicts para comparación
        old_dict = {t.symbol: (i, t) for i, t in enumerate(old)}
        new_dict = {t.symbol: (i, t) for i, t in enumerate(new)}

        # Tickers nuevos (añadidos)
        for symbol in new_dict:
            if symbol not in old_dict:
                rank, ticker = new_dict[symbol]
                deltas.append({
                    "action": "add",
                    "rank": rank,
                    "symbol": symbol,
                    "data": ticker.model_dump(mode='json')
                })

        # Tickers removidos
        for symbol in old_dict:
            if symbol not in new_dict:
                deltas.append({
                    "action": "remove",
                    "symbol": symbol
                })

        # Tickers que cambiaron de posición o datos
        for symbol in new_dict:
            if symbol in old_dict:
                old_rank, old_ticker = old_dict[symbol]
                new_rank, new_ticker = new_dict[symbol]

                # Cambio de rank
                if old_rank != new_rank:
                    deltas.append({
                        "action": "rerank",
                        "symbol": symbol,
                        "old_rank": old_rank,
                        "new_rank": new_rank
                    })

                # Cambio de datos (precio, gap, etc)
                if self.ticker_data_changed(old_ticker, new_ticker):
                    deltas.append({
                        "action": "update",
                        "rank": new_rank,
                        "symbol": symbol,
                        "data": new_ticker.model_dump(mode='json')
                    })

        return deltas

    async def emit_ranking_deltas(
        self,
        list_name: str,
        deltas: List[Dict]
    ):
        """Emite deltas a Redis stream"""
        # Incrementar sequence number
        self.sequence_numbers[list_name] = \
            self.sequence_numbers.get(list_name, 0) + 1

        await self.redis.xadd(
            'stream:ranking:deltas',
            {
                'type': 'delta',
                'list': list_name,
                'sequence': self.sequence_numbers[list_name],
                'deltas': json.dumps(deltas),
                'timestamp': datetime.now().isoformat()
            }
        )
```

#### 1.2 Crear Hot Ticker Manager

**Archivo**: `services/scanner/hot_ticker_manager.py` (NUEVO)

```python
class HotTickerManager:
    """
    Gestiona tickers "hot" (activos en rankings) vs "cold" (universo completo)
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        self.hot_tickers: Set[str] = set()
        self.cold_tickers: Set[str] = set()

    async def promote_to_hot(self, symbols: List[str]):
        """
        Promociona tickers a hot set
        - Auto-suscribe a Polygon WS
        - Añade a hot tracking
        """
        new_hot = set(symbols) - self.hot_tickers

        if new_hot:
            # Suscribir a Polygon WS
            for symbol in new_hot:
                await self.redis.xadd(
                    'polygon_ws:subscriptions',
                    {'symbol': symbol, 'action': 'subscribe'}
                )

            self.hot_tickers.update(new_hot)
            logger.info(f"Promoted {len(new_hot)} tickers to hot")

    async def degrade_to_cold(self, symbols: List[str]):
        """
        Degrada tickers a cold set
        - Desuscribe de Polygon WS
        - Remueve de hot tracking
        """
        to_degrade = set(symbols) & self.hot_tickers

        if to_degrade:
            # Desuscribir de Polygon WS
            for symbol in to_degrade:
                await self.redis.xadd(
                    'polygon_ws:subscriptions',
                    {'symbol': symbol, 'action': 'unsubscribe'}
                )

            self.hot_tickers -= to_degrade
            logger.info(f"Degraded {len(to_degrade)} tickers to cold")

    async def update_hot_set(self, current_rankings: Dict[str, List[str]]):
        """
        Actualiza hot set basado en rankings actuales

        Args:
            current_rankings: {'gappers_up': ['TSLA', 'AAPL', ...], ...}
        """
        # Todos los tickers en TODOS los rankings activos
        all_hot = set()
        for symbols in current_rankings.values():
            all_hot.update(symbols[:200])  # Top 200 de cada lista

        # Promocionar nuevos
        to_promote = all_hot - self.hot_tickers
        if to_promote:
            await self.promote_to_hot(list(to_promote))

        # Degradar antiguos
        to_degrade = self.hot_tickers - all_hot
        if to_degrade:
            await self.degrade_to_cold(list(to_degrade))
```

#### 1.3 Separar Discovery Loop y Hot Loop

**Archivo**: `services/scanner/main.py`

```python
# Dos loops independientes

async def discovery_loop():
    """
    Loop LENTO para descubrir nuevos líderes
    Procesa TODO el universo cada 30 segundos
    """
    while True:
        try:
            # Procesar TODO el universo (11,000 tickers)
            result = await scanner_engine.run_full_scan()

            # Actualizar hot set
            await hot_ticker_manager.update_hot_set(result.rankings)

            logger.info(f"Discovery scan completed: {result.filtered_count} filtered")

            # Esperar 30 segundos
            await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Error in discovery loop: {e}")
            await asyncio.sleep(30)

async def hot_loop():
    """
    Loop RÁPIDO para mantener hot tickers actualizados
    Procesa SOLO hot tickers cada 100ms - 1 segundo
    """
    while True:
        try:
            # Procesar SOLO hot tickers (~50-200)
            hot_symbols = list(hot_ticker_manager.hot_tickers)

            if hot_symbols:
                result = await scanner_engine.run_hot_scan(hot_symbols)

                # Emitir deltas si hay cambios
                # (ya se hace dentro de run_hot_scan)

            # Esperar 1 segundo (o 100ms si queremos más frecuencia)
            await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"Error in hot loop: {e}")
            await asyncio.sleep(1.0)

# Iniciar ambos loops en paralelo
await asyncio.gather(
    discovery_loop(),
    hot_loop()
)
```

---

### Fase 2: WebSocket Server - Snapshot + Deltas

#### 2.1 Modificar WebSocket Server

**Archivo**: `services/websocket_server/src/index.js`

```javascript
// Al conectar cliente
wss.on("connection", async (ws) => {
  const connectionId = uuidv4();

  // Enviar snapshot inicial
  const snapshot = await getInitialSnapshot("gappers_up");

  ws.send(JSON.stringify({
    type: "snapshot",
    list: "gappers_up",
    sequence: snapshot.sequence,
    rows: snapshot.rows,
    timestamp: new Date().toISOString()
  }));

  // Guardar conexión
  connections.set(connectionId, {
    ws,
    lists: ["gappers_up"],  // Listas suscritas
    lastSequence: snapshot.sequence
  });
});

// Procesar deltas de rankings
async function processRankingDeltas() {
  const consumerGroup = "websocket_server_deltas";
  const stream = "stream:ranking:deltas";

  // Crear consumer group
  try {
    await redis.xgroup("CREATE", stream, consumerGroup, "0", "MKSTREAM");
  } catch (err) {
    // Ya existe
  }

  while (true) {
    try {
      const messages = await redis.xreadgroup(
        "GROUP",
        consumerGroup,
        "ws_consumer",
        "COUNT",
        50,
        "BLOCK",
        100,
        "STREAMS",
        stream,
        ">"
      );

      if (messages && messages[0]) {
        const [, streamMessages] = messages[0];

        for (const [messageId, fields] of streamMessages) {
          const data = parseFields(fields);

          // Broadcast a clientes suscritos a esta lista
          broadcastRankingDelta({
            type: data.type,  // 'delta'
            list: data.list,  // 'gappers_up'
            sequence: parseInt(data.sequence),
            changes: JSON.parse(data.deltas),
            timestamp: data.timestamp
          });

          // ACK
          await redis.xack(stream, consumerGroup, messageId);
        }
      }
    } catch (err) {
      logger.error({ err }, "Error processing ranking deltas");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

function broadcastRankingDelta(delta) {
  for (const [connectionId, conn] of connections.entries()) {
    // Verificar si está suscrito a esta lista
    if (conn.lists.includes(delta.list)) {
      // Verificar sequence (detectar gaps)
      if (delta.sequence > conn.lastSequence + 1) {
        // Gap detectado, enviar snapshot
        sendSnapshot(connectionId, delta.list);
      } else {
        // Enviar delta normal
        sendMessage(connectionId, delta);
        conn.lastSequence = delta.sequence;
      }
    }
  }
}

async function getInitialSnapshot(listName) {
  // Obtener ranking actual de Redis
  const data = await redis.get(`scanner:category:${listName}`);
  const tickers = JSON.parse(data);

  // Obtener sequence number actual
  const sequence = await redis.get(`scanner:sequence:${listName}`);

  return {
    sequence: parseInt(sequence || 0),
    rows: tickers.slice(0, 200).map((t, i) => ({
      rank: i,
      symbol: t.symbol,
      price: t.price,
      gap: t.change_percent,
      volume: t.volume_today,
      rvol: t.rvol,
      market_cap: t.market_cap,
      sector: t.sector,
      ...
    }))
  };
}
```

---

### Fase 3: Frontend - Aplicar Deltas

#### 3.1 Modificar GappersTable

**Archivo**: `frontend/components/scanner/GappersTable.tsx`

```typescript
export default function GappersTable() {
  const [rows, setRows] = useState<Ticker[]>([]);
  const [lastSequence, setLastSequence] = useState<number>(0);
  const deltaBuffer = useRef<any[]>([]);

  const wsUrl = "ws://localhost:9000/ws/scanner";
  const ws = useWebSocket(wsUrl);

  // ✅ Cargar snapshot inicial (UNA VEZ al montar)
  useEffect(() => {
    // El snapshot viene por WebSocket automáticamente al conectar
    // NO hacer fetch REST
  }, []);

  // ❌ ELIMINAR ESTE useEffect (polling cada 10 seg)
  // useEffect(() => {
  //   const interval = setInterval(() => {
  //     fetchFilteredTickers();
  //   }, 10000);
  //   return () => clearInterval(interval);
  // }, []);

  // ✅ Procesar mensajes del WebSocket
  useEffect(() => {
    if (!ws.lastMessage) return;

    const message = ws.lastMessage;

    if (message.type === "snapshot") {
      // Snapshot inicial o resync
      console.log(`📸 Snapshot recibido: ${message.rows.length} filas`);
      setRows(message.rows);
      setLastSequence(message.sequence);
    } else if (message.type === "delta") {
      // Delta incremental

      // Verificar sequence
      if (message.sequence !== lastSequence + 1) {
        console.warn(
          `⚠️ Gap de sequence detectado: esperado ${
            lastSequence + 1
          }, recibido ${message.sequence}`
        );
        // Solicitar resync
        ws.send(
          JSON.stringify({
            action: "resync",
            list: "gappers_up",
            last_sequence: lastSequence,
          })
        );
        return;
      }

      // Añadir a buffer
      deltaBuffer.current.push(message);

      // Programar aplicación de deltas
      if (!applyDeltasScheduled.current) {
        applyDeltasScheduled.current = true;
        requestAnimationFrame(() => {
          applyDeltasBatch();
        });
      }
    } else if (message.type === "aggregate") {
      // Update de celda individual (precio, volumen)
      updateCell(message.symbol, message.data);
    }
  }, [ws.lastMessage]);

  // ✅ Aplicar deltas en lote
  const applyDeltasBatch = () => {
    const batch = deltaBuffer.current;
    deltaBuffer.current = [];
    applyDeltasScheduled.current = false;

    if (batch.length === 0) return;

    setRows((prevRows) => {
      let newRows = [...prevRows];

      for (const delta of batch) {
        for (const change of delta.changes) {
          if (change.action === "add") {
            // Añadir fila en posición rank
            newRows.splice(change.rank, 0, {
              ...change.data,
              rank: change.rank,
            });
          } else if (change.action === "remove") {
            // Remover fila
            newRows = newRows.filter((r) => r.symbol !== change.symbol);
          } else if (change.action === "update") {
            // Actualizar datos de fila
            const index = newRows.findIndex((r) => r.symbol === change.symbol);
            if (index !== -1) {
              newRows[index] = {
                ...newRows[index],
                ...change.data,
                rank: change.rank,
              };
            }
          } else if (change.action === "rerank") {
            // Mover fila a nueva posición
            const index = newRows.findIndex((r) => r.symbol === change.symbol);
            if (index !== -1) {
              const row = newRows.splice(index, 1)[0];
              newRows.splice(change.new_rank, 0, {
                ...row,
                rank: change.new_rank,
              });
            }
          }
        }

        setLastSequence(delta.sequence);
      }

      return newRows;
    });
  };

  // ✅ Actualizar celda individual (precio, volumen)
  const updateCell = (symbol: string, data: any) => {
    setRows((prevRows) => {
      const index = prevRows.findIndex((r) => r.symbol === symbol);
      if (index === -1) return prevRows;

      const newRows = [...prevRows];
      newRows[index] = {
        ...newRows[index],
        price: data.c !== undefined ? data.c : newRows[index].price,
        volume_today:
          data.av !== undefined ? data.av : newRows[index].volume_today,
        // ... otros campos
      };

      return newRows;
    });
  };

  return (
    <div>
      <table>
        {/* Renderizar rows normalmente */}
        {rows.map((row, i) => (
          <tr key={row.symbol}>
            <td>{row.rank}</td>
            <td>{row.symbol}</td>
            <td>{row.price}</td>
            {/* ... */}
          </tr>
        ))}
      </table>
    </div>
  );
}
```

---

## 6. ✅ CHECKLIST DE IMPLEMENTACIÓN

### Backend

- [ ] Implementar `calculate_ranking_deltas()` en ScannerEngine
- [ ] Implementar `emit_ranking_deltas()` para publicar a stream
- [ ] Crear `HotTickerManager` para gestión hot/cold
- [ ] Separar `discovery_loop()` (30 seg) y `hot_loop()` (1 seg)
- [ ] Añadir sequence numbers a rankings
- [ ] Modificar data_ingest para reducir frecuencia a 30 seg
- [ ] Implementar auto-suscripción de hot tickers a Polygon WS

### WebSocket Server

- [ ] Implementar envío de snapshot inicial al conectar
- [ ] Implementar procesamiento de `stream:ranking:deltas`
- [ ] Implementar detección de gaps en sequence
- [ ] Implementar endpoint de resync
- [ ] Separar mensajes de ranking vs aggregates

### Frontend

- [ ] ELIMINAR polling `setInterval` de fetchFilteredTickers
- [ ] Implementar aplicación de deltas incrementales
- [ ] Implementar buffer y batching con RAF
- [ ] Implementar detección de gaps y solicitud de resync
- [ ] ELIMINAR lógica de comparación de arrays
- [ ] ELIMINAR gestión manual de suscripciones

---

## 7. 📊 MÉTRICAS ESPERADAS

| Métrica           | Actual               | Después del Refactor      |
| ----------------- | -------------------- | ------------------------- |
| CPU Backend       | 80-100%              | 20-30%                    |
| CPU Frontend      | 40-60%               | 5-10%                     |
| Re-renders/seg    | 10+ (tabla completa) | 1-5 (filas afectadas)     |
| Latencia visual   | 10 seg (polling)     | 100ms - 1 seg             |
| Memoria Frontend  | Alta (comparaciones) | Baja (solo deltas)        |
| Tráfico de red    | Alto (polling REST)  | Bajo (solo WS)            |
| Filas desaparecen | Sí (cada 10 seg)     | No (solo si salen de top) |

---

**FIN DEL ANÁLISIS** 📋

