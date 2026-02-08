# TradeUL - Arquitectura Completa del Sistema

> Documento actualizado: 2026-02-06

---

## 1. Vision General

TradeUL es una plataforma de trading en tiempo real que procesa +11,000 tickers del mercado americano. El sistema tiene dos pilares:

| Pilar | Servicio | Pregunta que responde | Paradigma |
|-------|----------|----------------------|-----------|
| **Scanner** (Estrategias) | `scanner` | "Quien cumple esta condicion AHORA?" | Snapshot-based (10s) |
| **Event Detector** (Eventos) | `event_detector` | "Que PASO y CUANDO?" | Stream-based (~1s) |

**Diferencias clave:**

| Aspecto | Scanner | Event Detector |
|---------|---------|----------------|
| Cardinalidad | 1 ticker = max 1 fila | 1 ticker = N filas (historial) |
| Actualizacion | DELTAS (entra/sale/actualiza) | APPEND-ONLY (cada evento = nueva fila) |
| Ordenamiento | Por metricas (RVOL, change%) | Por TIMESTAMP (mas reciente primero) |
| Frontend | CategoryTableV2 (rankings) | EventTableContent (timeline) |
| Comando | `SC` | `EVN` |

---

## 2. Microservicios

### 2.1 Infraestructura

| Servicio | Puerto | Container | Funcion |
|----------|--------|-----------|---------|
| Redis 7 | 6379 | `tradeul_redis` | Streams, cache, pub/sub |
| TimescaleDB | 5432 | `tradeul_timescale` | Series temporales, datos historicos |

### 2.2 Pipeline de Datos

| Servicio | Puerto | Container | Funcion |
|----------|--------|-----------|---------|
| market_session | 8002 | `tradeul_market_session` | Sesiones de mercado (PRE, REGULAR, POST, CLOSED) |
| data_ingest | 8003 | `tradeul_data_ingest` | Ingestion de snapshots de Polygon REST API |
| polygon_ws | 8006 | `tradeul_polygon_ws` | WebSocket a Polygon.io (aggregates, quotes, LULD) |
| analytics | 8007 | `tradeul_analytics` | RVOL, ATR, ventanas de volumen/precio, VWAP, Z-Score |

### 2.3 Core de Negocio

| Servicio | Puerto | Container | Funcion |
|----------|--------|-----------|---------|
| scanner | 8005 | `tradeul_scanner` | Motor RETE, categorizacion, deltas, reglas de usuario |
| event_detector | 8040 | `tradeul_event_detector` | Deteccion de eventos en tiempo real (25 tipos) |
| screener | 8026 | `tradeul_screener` | Screener basado en DuckDB |

### 2.4 Entrega al Frontend

| Servicio | Puerto | Container | Funcion |
|----------|--------|-----------|---------|
| websocket_server | 9000 | `tradeul_websocket_server` | WebSocket (rankings, eventos, aggregates, quotes) |
| api_gateway | 8000 | `tradeul_api_gateway` | REST API gateway |

### 2.5 Servicios de Datos

| Servicio | Puerto | Container | Funcion |
|----------|--------|-----------|---------|
| ticker_metadata | 8010 | `tradeul_ticker_metadata` | Metadata de tickers |
| financials | 8020 | `tradeul_financials` | Datos financieros |
| historical | 8004 | `tradeul_historical` | Datos historicos |
| polygon_data | 8027 | `tradeul_polygon_data` | Gestion de datos de Polygon |
| today_bars_worker | 8035 | `tradeul_today_bars_worker` | Barras intradiarias del dia |

### 2.6 Noticias y Datos Externos

| Servicio | Puerto | Container |
|----------|--------|-----------|
| benzinga-news | 8015 | `tradeul_benzinga_news` |
| benzinga-earnings | 8022 | `tradeul_benzinga_earnings` |
| sec-filings | 8012 | `tradeul_sec_filings` |
| prediction-markets | 8021 | `tradeul_prediction_markets` |

### 2.7 AI y Social

| Servicio | Puerto | Container |
|----------|--------|-----------|
| ai_agent | 8030 | `tradeul_ai_agent` |
| financial_analyst | - | `tradeul_financial_analyst` |
| dilution_tracker | 8009 | `tradeul_dilution_tracker` |
| chat_service | 8016 | `tradeul_chat_service` |
| websocket_chat | 9001 | `tradeul_websocket_chat` |

---

## 3. Flujo de Datos Completo

```
                                  POLYGON.IO
                           -----------+-----------
                           |                     |
                     REST API              WebSocket
                     (snapshots)           (realtime)
                           |                     |
                           v                     v
                    +-----------+    +------------------+
                    |data_ingest|    |    polygon_ws    |
                    +-----+-----+    +--------+---------+
                          |                   |
                          v         +---------+----------+--------+
                 snapshot:polygon   |         |          |        |
                 :latest            v         v          v        v
                          |   aggregates  halt:events  quotes  luld
                          |        |          |          |
                          v        v          |          |
                    +-----------+--+          |          |
                    |   analytics  |          |          |
                    | RVOL,ATR,etc |          |          |
                    +------+-------+          |          |
                           |                  |          |
                  snapshot:enriched            |          |
                  :latest                      |          |
                           |                  |          |
                  +--------+---+              |          |
                  |            |              |          |
                  v            v              v          |
         +----------+  +------------------+             |
         | SCANNER  |  | EVENT DETECTOR   |             |
         | 12 cats  |  | 27 event types   |             |
         | RETE     |  | 6 plugins        |             |
         +----+-----+  +--------+---------+             |
              |                  |                       |
    ranking:deltas     events:market                     |
              |                  |                       |
              +--------+---------+-----------------------+
                       |
                       v
            +------------------+
            | websocket_server |
            | Consumer groups  |
            | Server filtering |
            | Backpressure     |
            | Rate limiting    |
            +--------+---------+
                     |
                     v
            +------------------+
            |    FRONTEND      |
            | SC = Scanner     |
            | EVN = Events     |
            | Charts, AI, etc  |
            +------------------+
```

---

## 4. Redis Streams

### 4.1 Streams de Datos

| Stream | Max | Publicador | Consumidores |
|--------|-----|-----------|-------------|
| `stream:realtime:aggregates` | 3000 | polygon_ws | analytics, event_detector, ws_server |
| `stream:realtime:quotes` | - | polygon_ws | ws_server |
| `stream:halt:events` | 500 | polygon_ws | event_detector |
| `stream:ranking:deltas` | 5000 | scanner | ws_server |
| `stream:events:market` | 5000 | event_detector | ws_server |
| `polygon_ws:subscriptions` | 2000 | scanner | polygon_ws |
| `snapshots:raw` | 1000 | data_ingest | scanner |

### 4.2 Consumer Groups

| Stream | Consumer Group | Consumer | Servicio |
|--------|---------------|----------|----------|
| `stream:realtime:aggregates` | `event_detector_aggregates` | `detector_1` | event_detector |
| `stream:realtime:aggregates` | `websocket_server_aggregates` | `ws_server_1` | ws_server |
| `stream:halt:events` | `event_detector_halts` | `detector_1` | event_detector |
| `stream:ranking:deltas` | `websocket_server_deltas` | `ws_server_1` | ws_server |
| `stream:events:market` | `websocket_server_events` | `ws_server_{pid}` | ws_server |
| `stream:realtime:quotes` | `websocket_server_quotes` | `ws_server_1` | ws_server |

**Garantias:**
- Fan-out: multiples consumer groups reciben todos los mensajes
- XACK despues de procesar (delivery garantizado)
- Auto-healing: recreacion automatica de grupos si se pierden (NOGROUP)
- Escalabilidad horizontal posible via multiples consumers por grupo

---

## 5. Scanner Service

### 5.1 Categorias (12)

| Categoria | Criterio | Tipo |
|-----------|---------|------|
| `gappers_up` | Gap >= 2% | Condicion |
| `gappers_down` | Gap <= -2% | Condicion |
| `momentum_up` | HOD <= 1%, change >= 1%, sobre VWAP, RVOL >= 1.5 | Multi |
| `momentum_down` | LOD <= 1%, change <= -1%, bajo VWAP, RVOL >= 1.5 | Multi |
| `winners` | Change >= 5%, RVOL >= 1.5 | Ranking |
| `losers` | Change <= -5%, RVOL >= 1.5 | Ranking |
| `new_highs` | Dentro de 0.1% del HOD | Condicion |
| `new_lows` | Dentro de 0.1% del LOD | Condicion |
| `high_volume` | RVOL >= 2.0 | Condicion |
| `anomalies` | Z-Score >= 3.0 | Condicion |
| `reversals` | Gap up cayendo, gap down subiendo | Condicion |
| `post_market` | Post-market con actividad | Condicion |

### 5.2 Sistema de Deltas

- **1a vez:** Snapshot completo (100 tickers)
- **2a+ vez:** Solo deltas (ADD, REMOVE, UPDATE, RERANK)
- **Umbrales:** Precio $0.01, Volumen 1000, Porcentaje 0.01%, RVOL 0.05

### 5.3 Motor RETE

- Compila reglas en grafo (Alpha/Beta/Terminal nodes)
- Evalua todos los tickers en una pasada
- Soporta system rules + user scan rules
- Fallback a ScannerCategorizer si deshabilitado

### 5.4 Loop Principal (cada 10s)

1. Leer `snapshot:enriched:latest` (Redis Hash, ~11,000 tickers)
2. Filtrar (precio, volumen, etc.) -> ~1,200 tickers
3. Evaluar con RETE -> categorizar
4. Calcular deltas vs ranking anterior
5. Publicar a `stream:ranking:deltas`
6. Auto-suscribir tickers en polygon_ws

---

## 6. Event Detector Service

### 6.1 Arquitectura de Plugins (6 detectores)

| Detector | Eventos | Cooldowns |
|----------|---------|-----------|
| PriceEventsDetector | new_high, new_low, crossed_above_open, crossed_below_open, crossed_above_prev_close, crossed_below_prev_close | 30-120s |
| VWAPEventsDetector | vwap_cross_up, vwap_cross_down | 60s |
| VolumeEventsDetector | rvol_spike, volume_surge, volume_spike_1min, unusual_prints, block_trade | 60-600s |
| MomentumEventsDetector | running_up, running_down, percent_up_5, percent_down_5, percent_up_10, percent_down_10 | 120-300s |
| PullbackEventsDetector | pullback_75_from_high, pullback_25_from_high, pullback_75_from_low, pullback_25_from_low | 300s |
| GapEventsDetector | gap_up_reversal, gap_down_reversal | 600s |

**+ Eventos externos:** `halt`, `resume` (desde stream:halt:events, sin cooldown)

**Total: 27 tipos de evento**

### 6.2 TickerState

Campos del estado por ticker:
- **Tiempo real:** price, volume, minute_volume (stream:realtime:aggregates ~1s)
- **Calculado en real-time:** change_percent ((price - prev_close) / prev_close * 100)
- **Enriquecido:** RVOL, gap%, ventanas de precio/volumen (snapshot cada 30s)
- **VWAP:** vwap diario
- **Extremos:** intraday_high, intraday_low, day_high, day_low
- **Referencias:** prev_close, open_price, change_from_open
- **Ventanas:** chg_1min..chg_30min, vol_1min, vol_5min
- **Tecnico:** atr, atr_percent, trades_z_score, market_cap

**EventRecord enriquecido:** Cada evento incluye snapshot completo del contexto al momento de dispararse (price, change%, rvol, volume, gap%, change_from_open, open, prev_close, vwap, atr%, intraday_high/low, market_cap). Esto permite filtrar y mostrar cualquier variable en el frontend.

### 6.3 Cooldown

- Cada detector tiene `CooldownTracker` propio
- Clave: `(event_type, symbol)` -> `last_fired_time`
- Reset diario via EventBus DAY_CHANGED
- Rangos: 30s (new_high) a 600s (gap_reversal, volume_surge)

### 6.4 Loops Concurrentes

1. `_consume_aggregates_loop()` - Aggregates -> detectar eventos
2. `_consume_halts_loop()` - Halts/resumes
3. `_enriched_refresh_loop()` - Cache enriched cada 30s
4. `_cleanup_loop()` - Limpiar datos antiguos cada 5min

---

## 7. WebSocket Server

### 7.1 Suscripcion de Eventos

```javascript
marketEventSubscriptions = Map<connectionId, {
    refCount: number,            // Componentes suscritos (ref counting)
    allTypes: boolean,           // true = todos los tipos
    eventTypes: Set<string>,     // Tipos solicitados
    symbolsInclude: Set | null,  // Whitelist (null = todos)
    symbolsExclude: Set,         // Blacklist
}>
```

### 7.2 Filtrado Server-Side

1. Filtro de tipo de evento
2. Filtro de simbolo (include/exclude)
3. **Filtros numericos:** price_min/max, rvol_min, change_min/max, volume_min
4. Backpressure: skip si `ws.bufferedAmount > 64KB`
5. Rate limiting: max 100 eventos/segundo por cliente

### 7.3 Snapshot Inicial

Al suscribirse: XREVRANGE ultimos 200 eventos -> filtrar server-side (tipo, simbolo, numericos) -> enviar como `events_snapshot`

### 7.4 Acciones Soportadas

| Accion | Funcion |
|--------|---------|
| `subscribe_events` | Suscribirse a eventos (incrementa refCount) |
| `unsubscribe_events` | Desuscribirse (decrementa refCount) |
| `update_event_filters` | Actualizar filtros sin re-suscribir |

---

## 8. Frontend

### 8.1 Comandos Principales

| Comando | Componente | Funcion |
|---------|------------|---------|
| `SC {cat}` | CategoryTableV2 | Tabla de scanner |
| `EVN {cat}` | EventTableContent | Tabla de eventos |
| `T {sym}` | ChartContent | Chart de ticker |
| `AI {prompt}` | AIAgentContent | Agente AI |
| `NEWS` | NewsContent | Noticias |
| `NOTES` | NotesContent | Notas |

### 8.2 Categorias de Eventos (EVN)

| ID | Tipos de Evento |
|----|----------------|
| `evt_new_highs` | new_high |
| `evt_new_lows` | new_low |
| `evt_vwap_crosses` | vwap_cross_up, vwap_cross_down |
| `evt_open_crosses` | crossed_above_open, crossed_below_open |
| `evt_close_crosses` | crossed_above_prev_close, crossed_below_prev_close |
| `evt_volume` | rvol_spike, volume_surge, volume_spike_1min, unusual_prints, block_trade |
| `evt_momentum` | running_up, running_down |
| `evt_big_movers` | percent_up_5/10, percent_down_5/10 |
| `evt_pullbacks` | pullback_75/25_from_high/low |
| `evt_gap_reversals` | gap_up_reversal, gap_down_reversal |
| `evt_halts` | halt, resume |
| `evt_all` | Todos |

### 8.3 Filtros

Store `useEventFiltersStore`: Filtros **per-category** (cada ventana EVN tiene sus propios filtros). Incluye tipos de evento, precio, cambio%, RVOL, volumen, simbolos (whitelist/blacklist/watchlist). Persistidos en localStorage + BD. Los filtros numericos se envian al WS server para **filtrado server-side** (reduce bandwidth).

### 8.4 Stack

Next.js 14 | TanStack Table + Virtual | Zustand | WebSocket nativo | Caddy (SSL)

---

## 9. Horarios (America/New_York)

| Sesion | Horario ET | Scanner |
|--------|-----------|---------|
| PRE_MARKET | 04:00 - 09:30 | 10s |
| REGULAR | 09:30 - 16:00 | 10s |
| POST_MARKET | 16:00 - 20:00 | 10s |
| CLOSED | 20:00 - 04:00 | 60s |

Eventos del sistema: `DAY_CHANGED` (reset caches), `SESSION_CHANGED` (transiciones)

---

## 10. Casos de Uso

### 10.1 Ver Gappers al Pre-Market

1. SC gappers_up -> WS suscribe -> snapshot (100 tickers) -> deltas cada 10s -> tabla en tiempo real
2. Filtros de precio/volumen/RVOL/market_cap aplicables

### 10.2 Alertas de New Highs

1. EVN new_highs -> WS suscribe con event_types: ["new_high"]
2. Snapshot filtrado (ultimos 100) -> nuevos eventos en tiempo real (~1s latencia)
3. Timeline: cada new_high = nueva fila con flash animation

### 10.3 Halt Detectado

1. Polygon WS recibe LULD halt -> stream:halt:events
2. Event Detector consume -> EventRecord(HALT, metadata)
3. stream:events:market -> WS server filtra -> cliente recibe

### 10.4 Scan Personalizado

1. Usuario crea regla RETE via API
2. Scanner la carga en el RETE network
3. Cada 10s: tickers que cumplen -> categoria custom -> deltas al frontend

---

## 11. Mejoras Pendientes

### 11.1 CRITICO

| # | Mejora | Desc | Complejidad |
|---|--------|------|-------------|
| 1 | **User Event Rules** | CRUD de reglas de eventos custom (tipo Trade Ideas) | Alta |
| 2 | **Notificaciones Push/Sound** | Alertas por evento configurable | Media |
| 3 | **Event Persistence** | Guardar en TimescaleDB (actualmente solo Redis ~8h) | Media |
| 4 | **Nuevos Tipos de Evento** | gap_fill, support_break, resistance_break, 52w_high/low | Alta |
| 5 | **Event Scoring** | Priorizar eventos por contexto (RVOL, mcap, etc.) | Media |

### 11.2 IMPORTANTE

| # | Mejora | Desc | Complejidad |
|---|--------|------|-------------|
| 6 | **Health Check** en event_detector | Puerto 8040 sin HTTP server | Baja |
| 7 | **Limpiar Codigo Legacy** | Detectores no usados en event_detector | Baja |
| 8 | **Categorias Custom Scanner** | Combinaciones de condiciones como Trade Ideas | Alta |
| 9 | **Filtros Avanzados Scanner** | Sector, industry, EPS, earnings date, short interest | Media |
| 10 | **Server-Side Filtering Completo** | Filtrar por precio, RVOL, change% en WS server | Media |
| 11 | **Metricas/Monitoring** | Prometheus metrics (eventos/seg, latencia, etc.) | Media |
| 12 | **Reconnection Handling** | Sequence numbers para no perder eventos | Media |

### 11.3 FRONTEND

| # | Mejora | Desc | Complejidad |
|---|--------|------|-------------|
| 13 | **Panel Filtros Eventos** | UI dedicada para filtros de EventTableContent | Media |
| 14 | **Event Detail Modal** | Click evento -> modal con detalles y chart mini | Media |
| 15 | **Sound Alerts** | Sonido configurable por tipo de evento | Baja |
| 16 | **Export CSV/Excel** | Exportar eventos | Baja |
| 17 | **Event Grouping** | Agrupar por simbolo o ventana temporal | Media |
| 18 | **Dashboard de Eventos** | Widget resumen del dia | Media |
| 19 | **Integrar EventFeed** | Componente existe pero no esta en workspace | Baja |

### 11.4 FUTURO

| # | Mejora | Desc | Complejidad |
|---|--------|------|-------------|
| 20 | **Multi-Timeframe Events** | Detectar en 1min, 5min, 15min | Alta |
| 21 | **Event Correlations** | Eventos compuestos (new_high + rvol_spike en 2min) | Alta |
| 22 | **ML-Based Events** | Anomaly detection avanzado | Muy Alta |
| 23 | **Event API Publica** | REST para consultar historico con filtros | Media |
| 24 | **Telegram/Discord Alerts** | Alertas a canales externos | Media |
| 25 | **Scanner -> Event Bridge** | Entrada a categoria = evento automatico | Media |
| 26 | **Backtesting** | "Si hubiera corrido esto ayer..." | Alta |

---

## 12. Roadmap Sugerido

### Fase 1: Estabilizacion (1-2 dias)
- [ ] #6 Health check en event_detector
- [ ] #7 Limpiar codigo legacy
- [ ] #13 Panel de filtros para eventos en frontend
- [ ] #19 Integrar EventFeed como widget

### Fase 2: User Events (3-5 dias)
- [ ] #1 User Event Rules (CRUD + UI + RETE)
- [ ] #8 Categorias custom de scanner
- [ ] #2 Notificaciones push/sound
- [ ] #15 Sound alerts frontend

### Fase 3: Persistencia (2-3 dias)
- [ ] #3 Event persistence en TimescaleDB
- [ ] #23 Event API publica
- [ ] #16 Export CSV/Excel

### Fase 4: Avanzado (5+ dias)
- [ ] #4 Nuevos tipos de evento
- [ ] #5 Event scoring
- [ ] #21 Event correlations
- [ ] #25 Scanner -> Event bridge
- [ ] #26 Backtesting

---

## 13. Deployment

```bash
# Backend (Docker)
docker compose up -d --force-recreate --build <servicio>
curl -s -X POST http://localhost:8005/api/scanner/start

# Frontend (Next.js + Caddy)
cd /opt/tradeul/frontend
npm run build
kill $(pgrep -f "next-server")
nohup npm start > /tmp/frontend.log 2>&1 &

# Verificar
curl -s -o /dev/null -w "%{http_code}" https://tradeul.com  # 200
docker logs tradeul_scanner --tail 10                         # Sin errores
```

Caddy: `tradeul.com` -> localhost:3000 (frontend), `/api/` -> :8000, `/ws/` -> :9000

---

---

## 12. Alert System (Trade Ideas-like)

### 12.1 Arquitectura del Sistema de Alertas

Inspirado en Trade Ideas. El sistema tiene:

| Concepto | Descripcion | Ejemplo |
|----------|-------------|---------|
| **Alert Type** | Un tipo de evento detectado | NHP (New High), CA200 (Cross SMA 200) |
| **Category** | Agrupacion de alertas | Price, VWAP, Volume, Momentum, MA Crosses |
| **Scan** | Combinacion de alertas + filtros | "High Vol Runners" = RUN + HRV + price>5 |
| **Filter** | Condiciones para filtrar alertas | price_min, rvol_min, market_cap_min |

### 12.2 Alert Registry

Catalogo completo en `services/event_detector/registry/alert_catalog.py`:

| Phase | Descripcion | # Alerts | Status |
|-------|------------|----------|--------|
| 1 | Tick-based (price, volume, VWAP, momentum, pullbacks, gaps, halts) | 27 | ✅ Live |
| 2 | Daily indicators (SMA crosses, Bollinger, daily levels, confirmed) | 34 | ✅ Detectores implementados |
| 3 | Intraday bars (ORB, timeframe highs, consolidation) | 43 | ⏳ Needs bar_builder |
| 4 | Intraday indicators (MACD, Stochastic, SMA crosses per timeframe) | 66 | ⏳ Needs bar_builder + indicator calc |
| 5 | Candlestick patterns (Doji, Hammer, Engulfing per timeframe) | 80 | ⏳ Needs bar_builder |
| 6 | Chart patterns (H&S, Triangles, Double Top/Bottom) | 10 | ⏳ Future |
| **Total** | | **260** | |

### 12.3 Data Pipeline para Alertas

```
                    ┌──────────────────┐
                    │   Polygon WS     │
                    │ (1s aggregates)  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ Analytics   │  │ Bar Builder │  │ Screener   │
     │ (enriched)  │  │ (1-60 min) │  │ (daily ind)│
     │ RVOL, ATR,  │  │ OHLC bars  │  │ SMA, BB,   │
     │ VWAP, chg%  │  │ stream:bars│  │ RSI, ADX   │
     └──────┬──────┘  └──────┬─────┘  └──────┬─────┘
            │                │               │
            └───────┬────────┴───────────────┘
                    ▼
           ┌────────────────┐
           │ Event Detector  │
           │ 9 plugins       │
           │ 53 EventTypes   │
           │ 38 TickerState  │
           └────────┬────────┘
                    │
            stream:events:market
                    │
           ┌────────┴────────┐
           │  WebSocket Srv  │ ← subscribe_events + filters
           │  (server-side   │
           │   filtering)    │
           └────────┬────────┘
                    │
              ┌─────┴─────┐
              │  Frontend  │
              │ EventTable │
              │ Scan Builder│
              └────────────┘
```

### 12.4 Screener → Event Detector Bridge

- Screener exporta SMA(20/50/200), Bollinger, RSI, 52w a Redis cada 5 min
- Redis key: `screener:daily_indicators:latest`
- Event detector lee cada 60s y popula TickerState con indicadores diarios
- Permite detectar cruces de SMA y rupturas de Bollinger en tiempo real

### 12.5 Bar Builder Service

`services/bar_builder/main.py` — Nuevo servicio para barras intradía:

- Consume `stream:realtime:aggregates` (1s data de Polygon WS)
- Construye OHLC bars en 7 timeframes: 1m, 2m, 5m, 10m, 15m, 30m, 60m
- Publica barra cerrada a `stream:bars:{timeframe}` para event_detector
- Almacena ultima barra en `bars:{timeframe}:latest` hash
- Foundation para Phase 3-5 alerts (ORB, candlestick patterns, MACD crosses)

### 12.6 API Endpoints

```
GET /api/alerts/catalog           — Catalogo completo con metadata
GET /api/alerts/categories        — Categorias con conteos
GET /api/alerts/catalog/active    — Solo alertas implementadas
GET /api/alerts/catalog/phase/:n  — Alertas por fase
GET /api/alerts/stats             — Estadisticas del sistema
```

---

*Mantener actualizado con cada cambio arquitectonico.*
