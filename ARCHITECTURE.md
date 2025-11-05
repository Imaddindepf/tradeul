# 🏗️ Arquitectura del Sistema Tradeul Scanner

Documentación detallada de la arquitectura de microservicios del sistema.

---

## 📊 Diagrama General

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND WEB                                  │
│                  (React/Vue/Angular + TypeScript)                    │
└────────────┬────────────────────────────────────┬────────────────────┘
             │                                    │
        REST API                             WebSocket
             │                                    │
┌────────────▼────────────────────────────────────▼────────────────────┐
│                      API GATEWAY (Puerto 8000)                       │
│  - REST Endpoints                                                     │
│  - WebSocket Manager                                                  │
│  - Agregación de datos                                               │
│  - CORS configurado                                                   │
└───────┬──────────────────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            ORQUESTACIÓN                         │
        ├──┤  ORCHESTRATOR (Puerto 8001)                    │
        │  │  - Health checks                                │
        │  │  - Coordinación de servicios                    │
        │  └─────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            GESTIÓN DE SESIONES                  │
        ├──┤  MARKET SESSION (Puerto 8002)                  │
        │  │  - Detecta PRE_MARKET, MARKET_OPEN, POST_MARKET │
        │  │  - Integra Polygon market status API           │
        │  │  - Maneja holidays y early closes               │
        │  │  - Resetea buffers en cambio de día            │
        │  └─────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            INGESTIÓN DE DATOS                   │
        ├──┤  DATA INGEST (Puerto 8003)                     │
        │  │  - Consume snapshots de Polygon cada 5 seg      │
        │  │  - Procesa 11,000 tickers                       │
        │  │  - Publica a Redis Streams                      │
        │  └─────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            DATOS HISTÓRICOS                     │
        ├──┤  HISTORICAL (Puerto 8004)                      │
        │  │  - Carga perfiles de FMP (batch/bulk)           │
        │  │  - Float, Market Cap, Volume avg                │
        │  │  - Caché en Redis                               │
        │  └─────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            MOTOR DE ESCANEO                     │
        ├──┤  SCANNER (Puerto 8005)                         │
        │  │  - Combina snapshots + datos históricos         │
        │  │  - Calcula RVOL simple (screening inicial)      │
        │  │  - Aplica filtros configurables                 │
        │  │  - Reduce: 11k → 500-1000 tickers              │
        │  └─────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            ANÁLISIS AVANZADO                    │
        ├──┤  ANALYTICS (Puerto 8007)                       │
        │  │  - RVOL por slots (preciso, siguiendo PineScript) │
        │  │  - Divide día en 192 slots de 5 min            │
        │  │  - Soporte extended hours (pre/post market)     │
        │  │  - Guarda histórico en TimescaleDB              │
        │  └─────────────────────────────────────────────────┘
        │
        │  ┌─────────────────────────────────────────────────┐
        │  │            DATOS EN TIEMPO REAL                 │
        └──┤  POLYGON WS (Puerto 8006)                      │
           │  - Conecta a wss://socket.polygon.io/stocks     │
           │  - Suscripción dinámica a tickers filtrados     │
           │  - Trades, Quotes, Aggregates por segundo       │
           │  - Reconexión automática                        │
           └─────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         INFRAESTRUCTURA                              │
├─────────────────────┬────────────────────────────────────────────────┤
│  REDIS (Puerto 6379)│  TIMESCALEDB (Puerto 5432)                    │
│  - Streams          │  - ticker_metadata                             │
│  - Cache            │  - scan_results                                │
│  - Pub/Sub          │  - volume_slots (para RVOL histórico)         │
│  - Session state    │  - ticks                                       │
└─────────────────────┴────────────────────────────────────────────────┘
```

---

## 🔄 Flujo de Datos Completo

### **Pipeline de Escaneo**

```
1️⃣ INGESTIÓN MASIVA
   └─ Data Ingest → Polygon Snapshots (11,000 tickers cada 5 seg)
                  → Publica a stream:snapshots

2️⃣ ENRIQUECIMIENTO
   ├─ Historical → Carga perfiles, float, market cap (FMP batch/bulk)
   │            → Caché en Redis
   │
   └─ Market Session → Detecta sesión actual (PRE_MARKET, MARKET_OPEN, etc)
                    → Publica a stream:session:changes

3️⃣ ESCANEO INICIAL
   └─ Scanner → Lee stream:snapshots
              → Combina con datos históricos (Redis)
              → Calcula RVOL SIMPLE (rápido)
              → Aplica filtros configurables
              → REDUCE: 11k → 500-1000 tickers
              → Publica a stream:scanner:filtered

4️⃣ ANÁLISIS PRECISO
   └─ Analytics → Lee stream:scanner:filtered
                → Calcula RVOL POR SLOTS (preciso)
                → Divide día en 192 slots de 5 min
                → Compara con histórico (TimescaleDB)
                → Publica a stream:analytics:rvol

5️⃣ DATOS EN TIEMPO REAL
   └─ Polygon WS → Lee stream:scanner:filtered
                 → Suscribe dinámicamente a tickers filtrados
                 → Recibe Trades, Quotes, Aggregates
                 → Publica a stream:realtime:*

6️⃣ EXPOSICIÓN AL FRONTEND
   └─ API Gateway → Consume todos los streams
                  → REST API para consultas
                  → WebSocket para streaming
                  → Frontend recibe updates en tiempo real
```

---

## 📦 Servicios Detallados

### **1. API Gateway**

**Responsabilidad**: Punto de entrada único para el frontend

**Tecnologías**: FastAPI, WebSockets, CORS

**Endpoints**:

- `GET /health` - Health check
- `GET /api/v1/scanner/status` - Estado del sistema
- `GET /api/v1/scanner/filtered` - Tickers filtrados
- `GET /api/v1/ticker/{symbol}` - Detalles de ticker
- `GET /api/v1/rvol/{symbol}` - RVOL actual
- `GET /api/v1/history/scans` - Histórico para backtesting
- `WS /ws/scanner` - WebSocket para streaming

**Redis Streams Consumidos**:

- `stream:analytics:rvol`
- `stream:realtime:aggregates`

**Documentación**: `services/api_gateway/README.md`

---

### **2. Market Session Service**

**Responsabilidad**: Detectar sesión de mercado actual

**Integración**: Polygon `/v1/marketstatus/now` y `/v1/marketstatus/upcoming`

**Funcionalidades**:

- Detecta: PRE_MARKET, MARKET_OPEN, POST_MARKET, CLOSED
- Maneja holidays y early closes dinámicamente
- Resetea buffers en cambio de día (4 AM ET)
- Publica cambios de sesión a Redis

**Documentación**: `services/market_session/README.md`

---

### **3. Data Ingest Service**

**Responsabilidad**: Consumir snapshots de Polygon

**Frecuencia**: Cada 5 segundos

**Volumen**: 11,000 tickers por snapshot

**Campos clave procesados**:

- `snapshot.min.av` - Volumen acumulado
- `snapshot.min.c` - Precio actual
- `snapshot.day.c` - Cierre anterior
- `snapshot.day.v` - Volumen del día

**Redis Streams Publicados**:

- `stream:snapshots`

**Documentación**: `services/data_ingest/README.md`

---

### **4. Historical Service**

**Responsabilidad**: Cargar datos de referencia de FMP

**Endpoints FMP Usados** (batch/bulk para eficiencia):

- `/stable/shares-float-all` - Float de todos los tickers
- `/stable/market-capitalization-batch` - Market cap en batch
- `/api/v3/available-traded/list` - Lista de tickers
- `/api/v3/quote?symbols=...` - Quotes en batch (100 símbolos)
- `/api/v3/profile?symbols=...` - Perfiles en batch

**Optimizaciones**:

- Paginación automática
- Chunking de 100 símbolos por request
- Rate limiting inteligente
- Caché en Redis (TTL configurable)

**Documentación**: `services/historical/README.md`

---

### **5. Scanner Service**

**Responsabilidad**: Filtrado inicial de tickers

**Pipeline**:

1. Lee `stream:snapshots`
2. Obtiene datos históricos de Redis
3. Calcula RVOL simple = `volume_today / avg_volume_30d`
4. Aplica filtros configurables
5. Reduce 11k → 500-1000 tickers
6. Publica a `stream:scanner:filtered`

**Filtros Soportados**:

- RVOL mínimo/máximo
- Precio mínimo/máximo
- Volumen mínimo
- Market cap mínimo/máximo
- % cambio mínimo/máximo

**Documentación**: `services/scanner/README.md`

---

### **6. Analytics Service** ⭐

**Responsabilidad**: Cálculo preciso de RVOL por slots

**Innovación**: Implementa lógica de PineScript para RVOL intraday

**Funcionamiento**:

1. Divide el día de trading en **192 slots de 5 minutos**:

   - Pre-market: 66 slots (4:00 AM - 9:30 AM)
   - Market hours: 78 slots (9:30 AM - 4:00 PM)
   - Post-market: 48 slots (4:00 PM - 8:00 PM)

2. Para cada ticker filtrado:

   - Obtiene `volume_accumulated` de Polygon (`min.av` o `av`)
   - Guarda en slot actual en memoria (VolumeSlotCache)
   - Consulta histórico de últimos N días para mismo slot
   - Calcula: `RVOL = volume_today(slot) / avg_historical(slot)`

3. Al final del día:
   - Persiste todos los slots en TimescaleDB (`volume_slots`)
   - Resetea caché
   - Limpia Redis

**Ventajas sobre RVOL simple**:

- ✅ Considera patrones intraday (más volumen en apertura/cierre)
- ✅ Compara manzanas con manzanas (mismo slot histórico)
- ✅ Detecta anomalías con mayor precisión
- ✅ Soporta pre-market y post-market

**Documentación**:

- `services/analytics/README.md`
- `services/analytics/EXTENDED_HOURS.md`
- `services/analytics/POLYGON_INTEGRATION.md`

---

### **7. Polygon WebSocket Connector**

**Responsabilidad**: Datos en tiempo real para tickers filtrados

**Conexión**: `wss://socket.polygon.io/stocks`

**Suscripción Dinámica**:

- Lee `stream:scanner:filtered`
- Ajusta suscripciones automáticamente
- Suscribe: `T.AAPL,Q.AAPL,A.AAPL,T.TSLA...`
- Desuscribe tickers que ya no están filtrados

**Eventos Procesados**:

- **T** (Trades): Ejecuciones en tiempo real
- **Q** (Quotes): NBBO (Best Bid/Offer)
- **A** (Aggregates): OHLCV por segundo

**Manejo de Errores**:

- Reconexión automática con backoff exponencial
- Heartbeat (ping/pong) cada 30 segundos
- Reintentos: hasta 10 intentos

**Redis Streams Publicados**:

- `stream:realtime:trades`
- `stream:realtime:quotes`
- `stream:realtime:aggregates`

**Documentación**: `services/polygon_ws/README.md`

---

## 🗄️ Base de Datos (TimescaleDB)

### **Tablas Principales**

#### **`ticks`**

Ticks en tiempo real (trades)

```sql
CREATE TABLE ticks (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    price DECIMAL(12, 4),
    size INTEGER,
    exchange INTEGER,
    conditions INTEGER[]
);

SELECT create_hypertable('ticks', 'time');
```

#### **`ticker_metadata`**

Datos de referencia de cada ticker

```sql
CREATE TABLE ticker_metadata (
    symbol VARCHAR(10) NOT NULL,
    name VARCHAR(255),
    market_cap BIGINT,
    float_shares BIGINT,
    avg_volume_30d BIGINT,
    sector VARCHAR(100),
    industry VARCHAR(100),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### **`volume_slots`** ⭐

Volumen acumulado por slot (para RVOL)

```sql
CREATE TABLE volume_slots (
    date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    slot_number INTEGER NOT NULL,  -- 0-191
    slot_time TIME NOT NULL,
    volume_accumulated BIGINT NOT NULL,
    trades_count INTEGER,
    avg_price DECIMAL(12, 4),
    PRIMARY KEY (date, symbol, slot_number)
);

SELECT create_hypertable('volume_slots', 'date');
```

#### **`scan_results`**

Histórico de scans (para backtesting)

```sql
CREATE TABLE scan_results (
    scan_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    price DECIMAL(12, 4),
    volume BIGINT,
    rvol DECIMAL(10, 2),
    change_percent DECIMAL(8, 2),
    market_cap BIGINT,
    scan_timestamp TIMESTAMPTZ NOT NULL
);

SELECT create_hypertable('scan_results', 'scan_timestamp');
```

---

## 💾 Redis Streams

### **Streams de Datos**

| Stream                       | Productor      | Consumidor            | Propósito              |
| ---------------------------- | -------------- | --------------------- | ---------------------- |
| `stream:snapshots`           | Data Ingest    | Scanner               | Snapshots de Polygon   |
| `stream:scanner:filtered`    | Scanner        | Analytics, Polygon WS | Tickers filtrados      |
| `stream:analytics:rvol`      | Analytics      | API Gateway           | RVOL preciso           |
| `stream:realtime:trades`     | Polygon WS     | API Gateway           | Trades en tiempo real  |
| `stream:realtime:quotes`     | Polygon WS     | API Gateway           | Quotes (NBBO)          |
| `stream:realtime:aggregates` | Polygon WS     | API Gateway           | Aggregates por segundo |
| `stream:session:changes`     | Market Session | Todos                 | Cambios de sesión      |

### **Keys de Caché**

| Key Pattern                     | TTL | Propósito                  |
| ------------------------------- | --- | -------------------------- |
| `ticker:data:{symbol}`          | 5s  | Datos de ticker            |
| `ticker:profile:{symbol}`       | 1h  | Perfil de empresa          |
| `rvol:{symbol}`                 | 5s  | RVOL actual                |
| `rvol:hist:avg:{symbol}:{slot}` | 24h | Promedio histórico de RVOL |
| `market:session:current`        | -   | Sesión de mercado actual   |
| `scanner:filtered:count`        | 5s  | Count de tickers filtrados |

---

## 🚀 Escalabilidad

### **Capacidad del Sistema**

| Métrica               | Capacidad          |
| --------------------- | ------------------ |
| Tickers procesados    | 11,000+            |
| Snapshots por segundo | 2,200 (11k / 5seg) |
| Tickers filtrados     | 500-1000           |
| WebSocket connections | 1,000+             |
| Requests HTTP/seg     | 10,000+            |
| Latencia E2E          | <200ms             |

### **Optimizaciones Implementadas**

1. **Caché Inteligente** (Redis)

   - Datos frecuentes con TTL corto (5s)
   - Datos estables con TTL largo (1h)
   - Invalidación selectiva

2. **Batch Processing**

   - FMP: 100 símbolos por request
   - TimescaleDB: Inserts en batch
   - Redis Streams: Reads en batch (100 mensajes)

3. **Suscripción Dinámica**

   - WebSocket solo para tickers activos
   - Ajuste automático basado en filtros
   - Reducción de 11k a 500-1000 suscripciones

4. **Estructuras de Datos Eficientes**
   - NumPy para cálculos numéricos
   - Pandas para agregaciones
   - Redis Sorted Sets para rankings

---

## 🔐 Seguridad

### **API Keys**

```bash
# .env
POLYGON_API_KEY=your_key  # Nunca commitear
FMP_API_KEY=your_key      # Nunca commitear
```

### **CORS** (Producción)

```python
# Configurar dominios específicos
allow_origins=["https://tudominio.com"]
```

### **Rate Limiting** (TODO)

Implementar rate limiting por IP/usuario.

---

## 📊 Monitoreo

### **Health Checks**

Todos los servicios exponen `/health`:

```bash
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8002/health  # Market Session
# ... etc
```

### **Logs Estructurados**

Formato JSON con `structlog`:

```json
{
  "event": "scanner_filtered",
  "symbol": "AAPL",
  "rvol": 1.87,
  "timestamp": "2025-10-24T10:30:00Z",
  "level": "info"
}
```

### **Métricas** (TODO)

Implementar Prometheus + Grafana.

---

**Sistema diseñado para traders profesionales que requieren datos precisos y en tiempo real** 🎯
