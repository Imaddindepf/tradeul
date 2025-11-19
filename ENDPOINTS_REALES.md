# 🌐 Servicios y Endpoints REALES

## 📦 Servicios Docker Activos

| Servicio | Puerto Externo | Descripción |
|----------|----------------|-------------|
| `tradeul_api_gateway` | **8000** | Gateway principal (proxy a otros servicios) |
| `tradeul_market_session` | **8002** | Estado del mercado (abierto/cerrado) |
| `tradeul_data_ingest` | 8003 | Ingesta de datos |
| `tradeul_historical` | 8004 | Datos históricos |
| `tradeul_scanner` | **8005** | Scanner en tiempo real |
| `tradeul_polygon_ws` | 8006 | WebSocket de Polygon |
| `tradeul_analytics` | 8007 | Analytics y estadísticas |
| `tradeul_data_maintenance` | 8008 | Mantenimiento de datos |
| `tradeul_dilution_tracker` | **8009** | Dilution tracker (SEC filings) |
| `tradeul_ticker_metadata` | **8010** | Metadatos de tickers |
| `tradeul_websocket_server` | **9000** | WebSocket para frontend |
| `tradeul_timescale` | 5432 | Base de datos TimescaleDB |
| `tradeul_redis` | 6379 | Redis cache |

---

## 🎯 Endpoints para el Frontend

### 1. **Market Session** (Puerto 8002)

```javascript
GET http://localhost:8002/api/session/current
```

**Respuesta:**
```json
{
  "current_session": "MARKET_OPEN",
  "trading_date": "2025-11-19",
  "timestamp": "2025-11-19T10:30:00-05:00",
  "is_trading_day": true
}
```

---

### 2. **Ticker Metadata** (Puerto 8000 - API Gateway)

```javascript
GET http://localhost:8000/api/v1/ticker/{symbol}/metadata
```

**Ejemplo:**
```bash
curl http://localhost:8000/api/v1/ticker/AAPL/metadata
```

**Respuesta:**
```json
{
  "symbol": "AAPL",
  "company_name": "Apple Inc.",
  "exchange": "NASDAQ",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "market_cap": 2750000000000,
  "float_shares": 15500000000,
  "logo_url": "https://...",
  "description": "Apple Inc. designs, manufactures...",
  "website": "https://www.apple.com",
  "is_actively_trading": true,
  "cik": "0000320193"
}
```

---

### 3. **Dilution Tracker** (Puerto 8009)

#### Get SEC Dilution Profile
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/profile
```

**Ejemplo:**
```bash
curl http://localhost:8009/api/sec-dilution/CMBM/profile
```

**Respuesta:**
```json
{
  "profile": {
    "symbol": "CMBM",
    "current_price": 1.25,
    "shares_outstanding": 50000000,
    "warrants": [...],
    "atm_offerings": [...],
    "shelf_registrations": [...],
    "completed_offerings": [...],
    "metadata": {
      "last_scraped_at": "2025-11-19T10:00:00Z",
      "source": "SEC EDGAR",
      "source_filings": ["10-K", "S-1", "8-K"]
    }
  },
  "dilution_analysis": {
    "total_potential_dilution_pct": 45.5,
    "total_potential_new_shares": 22750000,
    "risk_level": "HIGH",
    "risk_factors": [...]
  },
  "cached": true,
  "cache_age_seconds": 120
}
```

#### Refresh Profile (Force Update)
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/profile?refresh=true
```

#### Get Dilution Analysis
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/dilution-analysis
```

#### Get Warrants
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/warrants
```

#### Get ATM Offerings
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/atm-offerings
```

#### Get Shelf Registrations
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/shelf-registrations
```

#### Get Completed Offerings
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/completed-offerings
```

#### Get SEC Filings
```javascript
GET http://localhost:8009/api/sec-dilution/{ticker}/filings
```

---

### 4. **WebSocket Scanner** (Puerto 9000)

```javascript
ws://localhost:9000/ws/scanner
```

**Protocolo:**
```javascript
// Conectar
const ws = new WebSocket('ws://localhost:9000/ws/scanner');

// Suscribirse a una lista
ws.send(JSON.stringify({
  action: 'subscribe_list',
  list: 'gappers_up'
}));

// Desuscribirse
ws.send(JSON.stringify({
  action: 'unsubscribe_list',
  list: 'gappers_up'
}));

// Recibir snapshots
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'snapshot') {
    console.log('Snapshot:', msg.rows);
  }
  if (msg.type === 'delta') {
    console.log('Delta:', msg.deltas);
  }
};
```

---

## ⚙️ Variables de Entorno (.env.local)

```bash
# API Gateway (proxy centralizado)
NEXT_PUBLIC_API_URL=http://localhost:8000

# Market Session (directo)
NEXT_PUBLIC_MARKET_SESSION_URL=http://localhost:8002

# WebSocket Scanner
NEXT_PUBLIC_WS_URL=ws://localhost:9000/ws/scanner
```

---

## ✅ Archivos Frontend Actualizados

- **`lib/api.ts`** - Endpoints de Market Session y Ticker Metadata
- **`lib/dilution-api.ts`** - Endpoints de Dilution Tracker

Todos usan los **endpoints REALES** ahora.

---

## 🧪 Prueba los Endpoints

```bash
# Market Session
curl http://localhost:8002/api/session/current

# Ticker Metadata
curl http://localhost:8000/api/v1/ticker/AAPL/metadata

# Dilution Profile
curl http://localhost:8009/api/sec-dilution/CMBM/profile

# Scanner Status  
curl http://localhost:8000/api/v1/scanner/status
```

---

**✅ TODO CORREGIDO CON ENDPOINTS REALES**

