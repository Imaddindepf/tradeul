# Pattern Real-Time - Especificación Técnica

## Resumen Ejecutivo

Este documento describe la implementación de **Pattern Real-Time**, una nueva funcionalidad para Tradeul que permite escanear múltiples tickers en tiempo real, rankearlos por "edge" (ventaja estadística), y hacer tracking de predicciones con verificación de resultados.

---

## Lo que YA tenemos: Pattern Matching (Histórico)

### Descripción
Servicio existente que permite analizar patrones históricos de UN ticker en una fecha específica del pasado.

### Ubicación
- **Servidor**: `51.44.136.129`
- **Puerto**: `8787`
- **Repositorio**: `services/pattern-matching/`

### Arquitectura Actual

```
services/pattern-matching/
├── main.py                 # FastAPI application
├── pattern_matcher.py      # Lógica de búsqueda FAISS
├── config.py               # Configuración
├── daily_updater.py        # Actualización diaria del index
├── flat_files_downloader.py # Descarga minute bars de Polygon S3
├── indexes/
│   └── patterns_ivfpq.index  # FAISS index (~10 años de patrones)
├── data/
│   ├── minute_aggs/          # 599+ días de minute bars (CSV.gz)
│   └── patterns.db           # SQLite con metadata
└── docker-compose.yml
```

### Endpoints Existentes

```
POST /api/patterns/search
  Body: {
    "ticker": "AAPL",
    "mode": "historical" | "realtime",
    "timestamp": "2024-03-15T10:30:00",  # Para histórico
    "horizon": 30,                        # Minutos a predecir
    "k": 50                               # Número de vecinos
  }
  
  Response: {
    "ticker": "AAPL",
    "query_time": "2024-03-15T10:30:00",
    "horizon": 30,
    "prob_up": 0.72,
    "prob_down": 0.28,
    "mean_return": 1.2,
    "std_return": 0.8,
    "p10": -0.5,
    "p90": 2.1,
    "n_neighbors": 50,
    "neighbors": [...]  # Detalles de cada patrón similar
  }

GET /api/index/reload
  # Recarga el FAISS index en memoria

GET /health
  # Health check
```

### Frontend Existente
- **Componente**: `frontend/components/pattern-matching/PatternMatchingContent.tsx`
- **Funcionalidad**: 
  - Seleccionar UN ticker
  - Seleccionar fecha histórica
  - Ver patrones similares y forecast
  - Visualización con chart

---

## Lo que QUEREMOS crear: Pattern Real-Time

### Descripción
Nueva funcionalidad que permite:
1. **Batch scanning**: Escanear múltiples tickers simultáneamente
2. **Ranking**: Ordenar por "edge" (prob × mean_return)
3. **Tracking**: Guardar predicciones para seguimiento
4. **Verificación**: Comprobar si las predicciones fueron correctas después del horizon
5. **Performance**: Mostrar estadísticas de aciertos (win-rate, PnL)

### Diferencias Clave

| Aspecto | Pattern Matching (Histórico) | Pattern Real-Time (Nuevo) |
|---------|------------------------------|---------------------------|
| Tickers | 1 | N (batch) |
| Tiempo | Fecha pasada seleccionable | Ahora mismo |
| Propósito | Explorar/investigar | Detectar oportunidades |
| Tracking | No | Sí |
| Verificación | No necesita (ya ocurrió) | Sí ("actual") |
| Performance | No | Sí (win-rate, PnL) |

---

## Arquitectura Propuesta

### Backend (Extender servicio existente)

```
services/pattern-matching/
├── main.py                      # Modificar: añadir router realtime + WS
├── pattern_matcher.py           # NO TOCAR - se reutiliza
├── config.py                    # Modificar: añadir config realtime
│
├── realtime/                    # NUEVO directorio
│   ├── __init__.py
│   ├── router.py                # Endpoints /api/pattern-realtime/*
│   ├── websocket_manager.py     # Gestión de conexiones WebSocket
│   ├── engine.py                # Lógica de batch scanning
│   ├── verification_worker.py   # Background task para verificar predicciones
│   └── models.py                # Pydantic schemas
│
├── predictions.db               # NUEVO: SQLite para tracking
│
└── (resto sin cambios)
```

### Nuevos Endpoints

```python
# ═══════════════════════════════════════════════════════════════
# ENDPOINTS HTTP
# ═══════════════════════════════════════════════════════════════

POST /api/pattern-realtime/run
  """
  Inicia un batch scan de múltiples tickers.
  """
  Body: {
    "symbols": ["AAPL", "NVDA", "META", "GOOGL", ...],
    "k": 40,              # Vecinos a buscar
    "horizon": 10,        # Minutos para predicción
    "alpha": 6,           # Parámetro de weighting
    "trim_lo": 0,         # Percentil inferior a recortar
    "trim_hi": 0,         # Percentil superior a recortar
    "exclude_self": true, # Excluir el mismo ticker de vecinos
    "min_edge": 0.5       # Edge mínimo para incluir en resultados
  }
  
  Response: {
    "job_id": "uuid-xxx",
    "status": "running",
    "total_symbols": 20,
    "started_at": "2025-12-30T10:30:00Z"
  }


GET /api/pattern-realtime/job/{job_id}
  """
  Obtiene el estado y resultados de un job.
  """
  Response: {
    "job_id": "uuid-xxx",
    "status": "completed" | "running" | "failed",
    "progress": { "completed": 18, "total": 20 },
    "results": [
      {
        "symbol": "NVDA",
        "scan_time": "2025-12-30T10:30:00Z",
        "prob_up": 0.78,
        "prob_down": 0.22,
        "mean_return": 1.8,
        "edge": 1.404,  # prob_up × mean_return
        "direction": "UP",
        "n_neighbors": 40,
        "dist1": 0.023,  # Distancia al vecino más cercano
        "p10": -0.3,
        "p90": 3.2,
        # Campos de verificación (null hasta que pase horizon)
        "actual_return": null,
        "was_correct": null,
        "pnl": null,
        "verified_at": null
      },
      ...
    ],
    "failures": [
      {
        "symbol": "XYZ",
        "error_code": "E_NO_DATA",
        "reason": "No minute data available"
      }
    ]
  }


GET /api/pattern-realtime/job/{job_id}/results
  """
  Obtiene solo los resultados (más ligero).
  Incluye filtros opcionales.
  """
  Query params:
    - sort_by: "edge" | "prob_up" | "mean_return" (default: "edge")
    - direction: "ALL" | "UP" | "DOWN"
    - limit: int (default: 50)
    - include_verified: bool (default: true)


GET /api/pattern-realtime/performance
  """
  Estadísticas globales de performance.
  """
  Query params:
    - period: "1h" | "today" | "week" | "all"
  
  Response: {
    "period": "today",
    "total_predictions": 247,
    "verified": 183,
    "pending": 64,
    "stats": {
      "all": {
        "n": 183,
        "win_rate": 0.634,
        "mean_pnl": 0.42,
        "median_pnl": 0.31
      },
      "top_1pct": {
        "n": 2,
        "win_rate": 1.0,
        "mean_pnl": 2.1
      },
      "top_5pct": {
        "n": 9,
        "win_rate": 0.778,
        "mean_pnl": 1.4
      },
      "top_10pct": {
        "n": 18,
        "win_rate": 0.722,
        "mean_pnl": 1.1
      }
    },
    "by_direction": {
      "long": { "n": 120, "win_rate": 0.65, "mean_pnl": 0.48 },
      "short": { "n": 63, "win_rate": 0.60, "mean_pnl": 0.32 }
    }
  }


GET /api/pattern-realtime/history
  """
  Historial de predicciones pasadas.
  """
  Query params:
    - limit: int
    - offset: int
    - symbol: str (opcional, filtrar por ticker)
    - verified_only: bool


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════

WS /ws/pattern-realtime
  """
  Conexión WebSocket para updates en tiempo real.
  
  El cliente puede:
  - Suscribirse a un job específico
  - Recibir updates de progreso
  - Recibir resultados individuales cuando se completan
  - Recibir verificaciones cuando el horizon pasa
  """
  
  # Cliente → Servidor
  {
    "type": "subscribe",
    "job_id": "uuid-xxx"
  }
  
  {
    "type": "unsubscribe",
    "job_id": "uuid-xxx"
  }
  
  # Servidor → Cliente
  {
    "type": "progress",
    "job_id": "uuid-xxx",
    "completed": 5,
    "total": 20
  }
  
  {
    "type": "result",
    "job_id": "uuid-xxx",
    "data": {
      "symbol": "NVDA",
      "prob_up": 0.78,
      "edge": 1.404,
      ...
    }
  }
  
  {
    "type": "verification",
    "prediction_id": "uuid-yyy",
    "symbol": "NVDA",
    "actual_return": 1.2,
    "was_correct": true,
    "pnl": 1.2
  }
  
  {
    "type": "job_complete",
    "job_id": "uuid-xxx",
    "total_results": 18,
    "total_failures": 2
  }
```

### Base de Datos de Predicciones

```sql
-- predictions.db (SQLite)

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL,  -- 'running', 'completed', 'failed'
    params JSON NOT NULL,  -- k, horizon, alpha, etc.
    total_symbols INTEGER,
    completed_symbols INTEGER DEFAULT 0,
    failed_symbols INTEGER DEFAULT 0
);

CREATE TABLE predictions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    scan_time TIMESTAMP NOT NULL,
    horizon INTEGER NOT NULL,  -- minutos
    
    -- Predicción
    prob_up REAL NOT NULL,
    prob_down REAL NOT NULL,
    mean_return REAL NOT NULL,
    edge REAL NOT NULL,
    direction TEXT NOT NULL,  -- 'UP' o 'DOWN'
    n_neighbors INTEGER NOT NULL,
    dist1 REAL,
    p10 REAL,
    p90 REAL,
    
    -- Precio al momento del scan
    price_at_scan REAL NOT NULL,
    
    -- Verificación (null hasta que pase horizon)
    price_at_horizon REAL,
    actual_return REAL,
    was_correct BOOLEAN,
    pnl REAL,
    verified_at TIMESTAMP,
    
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX idx_predictions_job ON predictions(job_id);
CREATE INDEX idx_predictions_symbol ON predictions(symbol);
CREATE INDEX idx_predictions_pending ON predictions(verified_at) WHERE verified_at IS NULL;
CREATE INDEX idx_predictions_scan_time ON predictions(scan_time);
```

### Verification Worker

```python
"""
Background task que corre cada minuto.
Verifica predicciones cuyo horizon ya pasó.
"""

async def verification_loop():
    while True:
        # Buscar predicciones pendientes donde scan_time + horizon < now
        pending = db.query("""
            SELECT * FROM predictions 
            WHERE verified_at IS NULL 
            AND datetime(scan_time, '+' || horizon || ' minutes') < datetime('now')
        """)
        
        for prediction in pending:
            # Obtener precio actual
            current_price = await get_current_price(prediction.symbol)
            
            # Calcular retorno real
            actual_return = (current_price - prediction.price_at_scan) / prediction.price_at_scan * 100
            
            # Determinar si acertamos dirección
            if prediction.direction == "UP":
                was_correct = actual_return > 0
                pnl = actual_return
            else:  # DOWN
                was_correct = actual_return < 0
                pnl = -actual_return  # Invertir para short
            
            # Actualizar DB
            db.update(prediction.id, {
                "price_at_horizon": current_price,
                "actual_return": actual_return,
                "was_correct": was_correct,
                "pnl": pnl,
                "verified_at": datetime.utcnow()
            })
            
            # Broadcast via WebSocket
            await ws_manager.broadcast({
                "type": "verification",
                "prediction_id": prediction.id,
                "symbol": prediction.symbol,
                "actual_return": actual_return,
                "was_correct": was_correct,
                "pnl": pnl
            })
        
        await asyncio.sleep(60)  # Cada minuto
```

---

## Frontend

### Nueva Estructura

```
frontend/components/pattern-realtime/
├── PatternRealtimeContent.tsx    # Componente principal
├── SymbolInput.tsx               # Input para lista de tickers
├── ParametersPanel.tsx           # k, horizon, alpha, etc.
├── RealtimeTable.tsx             # Tabla de resultados con ranking
├── PerformanceStats.tsx          # Win-rate, PnL por buckets
├── FailuresPanel.tsx             # Errores del batch
└── hooks/
    └── usePatternRealtimeWS.ts   # Hook para WebSocket
```

### Integración en Window Injector

Añadir en `frontend/lib/window-injector/index.ts` o crear nuevo archivo `pattern-realtime-window.ts`.

### UI Propuesta

```
┌─────────────────────────────────────────────────────────────────────┐
│ Pattern Real-Time                                              [×] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Symbols (space/comma/newline)           │ Parameters               │
│ ┌─────────────────────────────────┐     │ k: [40]  horizon: [10]   │
│ │ AAPL NVDA META GOOGL MSFT AMZN  │     │ alpha: [6]               │
│ │ JPM BAC XOM HD PG KO PEP JNJ    │     │ trim: [0] - [0]          │
│ │ UNH TPL SMCI COIN SBAC HSY      │     │ [✓] exclude self         │
│ └─────────────────────────────────┘     │                          │
│                                         │ Sort by: [edge ▼]        │
│                                         │ Direction: [ALL ▼]       │
│ [▶ Run]  [■ Stop]          Progress: 18/20                         │
├─────────────────────────────────────────────────────────────────────┤
│ Performance Summary @ 10m                                           │
│ ┌─────────┬─────┬──────┬───────┬──────────┬──────────┬───────────┐ │
│ │ Bucket  │  N  │ Long │ Short │ Win-rate │ Mean P&L │ Median    │ │
│ ├─────────┼─────┼──────┼───────┼──────────┼──────────┼───────────┤ │
│ │ Top 1%  │  2  │  2   │   0   │  100%    │  +2.1%   │  +2.1%    │ │
│ │ Top 5%  │  9  │  7   │   2   │  77.8%   │  +1.4%   │  +1.2%    │ │
│ │ Top 10% │ 18  │ 12   │   6   │  72.2%   │  +1.1%   │  +0.9%    │ │
│ │ All     │ 183 │ 120  │  63   │  63.4%   │  +0.42%  │  +0.31%   │ │
│ └─────────┴─────┴──────┴───────┴──────────┴──────────┴───────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│ Top suggestions @ 10m (ranked by edge)                              │
│ ┌────────┬───────┬─────┬───────┬─────────┬───────┬─────┬─────────┐ │
│ │ Symbol │ Time  │ Dir │ Edge  │ Prob_up │ Mean  │  N  │ Actual  │ │
│ ├────────┼───────┼─────┼───────┼─────────┼───────┼─────┼─────────┤ │
│ │ NVDA   │ 10:30 │  ↑  │ 1.40  │  78%    │ +1.8% │ 40  │ +1.2% ✓ │ │
│ │ META   │ 10:30 │  ↑  │ 1.22  │  72%    │ +1.7% │ 40  │ pending │ │
│ │ AAPL   │ 10:30 │  ↓  │ 0.98  │  35%    │ -2.8% │ 40  │ -0.3% ✓ │ │
│ │ ...    │       │     │       │         │       │     │         │ │
│ └────────┴───────┴─────┴───────┴─────────┴───────┴─────┴─────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│ Failures (2)                                                        │
│ ┌────────┬───────┬────────────┬─────────────────────────────────┐  │
│ │ Symbol │ Time  │ Code       │ Reason                          │  │
│ ├────────┼───────┼────────────┼─────────────────────────────────┤  │
│ │ XYZ    │ 10:30 │ E_NO_DATA  │ No minute data available        │  │
│ │ ABC    │ 10:30 │ E_WINDOW   │ Insufficient contiguous bars    │  │
│ └────────┴───────┴────────────┴─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                  │
│                                                                     │
│  1. Usuario introduce tickers y parámetros                          │
│  2. Click "Run"                                                     │
│  3. WebSocket conecta a /ws/pattern-realtime                       │
│  4. Envía mensaje { type: "subscribe", job_id }                     │
│  5. Recibe updates de progreso y resultados                         │
│  6. Tabla se actualiza en tiempo real                               │
│  7. Cuando pasa horizon, recibe verificaciones                      │
│  8. Performance stats se actualizan                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │ WebSocket + HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PATTERN MATCHING SERVICE                           │
│                  51.44.136.129:8787                                 │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    WebSocket Manager                         │   │
│  │  - Gestiona conexiones de clientes                          │   │
│  │  - Broadcast updates a suscriptores                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Realtime Engine                           │   │
│  │  1. Recibe job (symbols, params)                            │   │
│  │  2. Para cada symbol:                                        │   │
│  │     a. Llama a pattern_matcher.search() ← REUTILIZA         │   │
│  │     b. Calcula edge = prob × mean_return                    │   │
│  │     c. Guarda predicción en predictions.db                  │   │
│  │     d. Broadcast resultado via WS                           │   │
│  │  3. Marca job como completado                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Verification Worker (Background)                │   │
│  │  - Corre cada minuto                                        │   │
│  │  - Busca predicciones donde scan_time + horizon < now       │   │
│  │  - Obtiene precio actual                                    │   │
│  │  - Calcula actual_return, was_correct, pnl                  │   │
│  │  - Actualiza DB                                             │   │
│  │  - Broadcast verificación via WS                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                 CORE (EXISTENTE - REUTILIZAR)               │   │
│  │  - FAISS index (patterns_ivfpq.index)                       │   │
│  │  - pattern_matcher.search()                                 │   │
│  │  - minute bar data                                          │   │
│  │  - forecast logic                                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    predictions.db (NUEVO)                    │   │
│  │  - Tabla jobs                                               │   │
│  │  - Tabla predictions                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Códigos de Error

```
E_WEEKEND        - Sábado/Domingo, mercado cerrado
E_MARKET_CLOSED  - Fuera de horario 09:30-16:00 ET
E_NO_DATA        - No hay minute data para el ticker
E_WINDOW         - No se pudo formar ventana contigua de 30 bars
E_FAISS          - Error al buscar en FAISS index
E_PRICE          - Error obteniendo precio actual
```

---

## Consideraciones Técnicas

### Performance
- El batch scanning puede paralelizarse (asyncio.gather)
- FAISS search es muy rápido (~1-5ms por query)
- El cuello de botella puede ser obtener precios real-time
- Considerar cache de precios con TTL corto

### Horario de Mercado
- Pre-market: 04:00-09:30 ET
- Regular: 09:30-16:00 ET
- After-hours: 16:00-20:00 ET
- El scanner debe funcionar en todas las sesiones
- Indicar claramente la sesión actual

### WebSocket
- Usar `fastapi-websocket` o similar
- Implementar heartbeat/ping-pong
- Manejar reconexiones gracefully
- Autenticación via token en query param

### Precios Real-Time
- Usar Polygon WebSocket para precios en tiempo real
- O llamar a API de precios existente en Tradeul
- Cache con TTL de 1-5 segundos

---

## Pasos de Implementación

### Fase 1: Backend Core
1. Crear estructura `realtime/` en `services/pattern-matching/`
2. Implementar SQLite schema para predictions
3. Crear `engine.py` con lógica de batch scanning
4. Crear `router.py` con endpoints HTTP básicos
5. Probar con curl/Postman

### Fase 2: WebSocket
1. Implementar `websocket_manager.py`
2. Añadir endpoint WS a `main.py`
3. Integrar broadcasts en engine
4. Probar con wscat

### Fase 3: Verification
1. Implementar `verification_worker.py`
2. Añadir como background task en FastAPI
3. Integrar broadcasts de verificaciones
4. Probar end-to-end

### Fase 4: Frontend
1. Crear componente `PatternRealtimeContent.tsx`
2. Implementar hook `usePatternRealtimeWS.ts`
3. Crear tablas y UI
4. Integrar en window-injector
5. Testing completo

### Fase 5: Deploy
1. Actualizar Docker image
2. Deploy en servidor 51.44.136.129
3. Configurar proxy/nginx para WS si necesario
4. Monitoring y logs

---

## Conexión al Servidor

```bash
# SSH al servidor de Pattern Matching
ssh root@51.44.136.129

# Directorio del servicio
cd /opt/pattern-matching

# Ver logs
docker-compose logs -f pattern_matching

# Reiniciar servicio
docker-compose restart pattern_matching
```

---

## Notas Adicionales

- El servicio existente de Pattern Matching NO debe modificarse en su core
- Todo lo nuevo va en el directorio `realtime/`
- Los endpoints existentes (`/api/patterns/search`) siguen funcionando igual
- El FAISS index y minute data se REUTILIZAN, no se duplican
- El frontend existente (`PatternMatchingContent.tsx`) no se toca

