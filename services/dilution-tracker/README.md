# Dilution Tracker Service

Servicio para análisis de dilución de acciones, cash runway y riesgo de offerings.

## Características

### 🎯 **Core Features**
- ✅ Análisis de financial statements (Balance + Income + Cash Flow)
- ✅ Tracking de institutional holders (13F filings)
- ✅ Monitoreo de SEC filings
- ✅ Cálculo de cash runway
- ✅ Análisis de dilución histórica
- ✅ Risk scoring completo

###  **Estrategia Tiered**
- **Tier 1** (500 tickers): Sincronización diaria
- **Tier 2** (2000 tickers): Sincronización semanal
- **Tier 3** (resto): Lazy loading (solo cuando usuario lo solicita)

### 🔍 **Search Tracking**
- Tracking de búsquedas de usuarios
- Auto-promoción de tickers populares
- Pre-warming de cache inteligente

## Arquitectura

```
dilution-tracker/
├── models/              # Pydantic models
├── services/            # FMP API integration
├── calculators/         # Business logic
├── strategies/          # Tier & search strategies
├── routers/             # FastAPI endpoints
├── jobs/                # Background jobs
└── main.py             # FastAPI app
```

## APIs Utilizadas

### Financial Modeling Prep (FMP)
- `/v3/balance-sheet-statement/{ticker}`
- `/v3/income-statement/{ticker}`
- `/v3/cash-flow-statement/{ticker}`
- `/v3/institutional-holder/{ticker}`
- `/v3/sec_filings/{ticker}`

## Endpoints

### GET `/api/analysis/{ticker}`
Análisis completo del ticker

### GET `/api/analysis/{ticker}/summary`
Resumen rápido (metadata básica)

### GET `/api/analysis/{ticker}/risk-scores`
Risk scores calculados

### POST `/api/analysis/{ticker}/refresh`
Forzar actualización de datos

### GET `/api/analysis/trending`
Tickers más buscados

## Base de Datos

### Tablas Nuevas
1. **financial_statements** - Estados financieros históricos
2. **institutional_holders** - Holders institucionales (13F)
3. **sec_filings** - SEC filings relevantes
4. **dilution_metrics** - Métricas calculadas de dilución
5. **ticker_sync_config** - Configuración de sincronización
6. **dilution_searches** - Tracking de búsquedas

### Tablas Reutilizadas
- **ticker_metadata** - Metadata de tickers (market_cap, float, etc.)
- **market_data_daily** - OHLC histórico

## Setup

### 1. Crear tablas
```bash
psql -h localhost -U postgres -d tradeul -f scripts/init_dilution_tracker.sql
```

### 2. Build & Run
```bash
docker-compose up -d dilution-tracker
```

### 3. Verificar
```bash
curl http://localhost:8000/health
```

## Jobs

### Daily Job: Sync Tier 1
```bash
python jobs/sync_tier1_job.py
```

### Weekly Job: Tier Rebalance
```bash
python jobs/tier_rebalance_job.py
```

## Cálculos

### Cash Runway
```
Runway = Current Cash / Quarterly Burn Rate
```

### Dilution %
```
Dilution % = ((Shares Current - Shares Previous) / Shares Previous) * 100
```

### Risk Score
Combina:
- Cash need score (40%)
- Dilution risk score (40%)
- Market factors (20%)

## Cache Strategy

```
dilution:analysis:{TICKER}          TTL: 1h
dilution:financials:{TICKER}        TTL: 24h
dilution:holders:{TICKER}           TTL: 7d
dilution:filings:{TICKER}           TTL: 24h
```

## Rate Limiting

- FMP API: 250 requests/5 min (free tier)
- Internal: 0.5s sleep between requests
- Batch operations cuando sea posible

## TODO

- [ ] Implementar data persistence (save to DB)
- [ ] Implementar lazy loading completo
- [ ] Agregar más endpoints (financials, holders, filings)
- [ ] Implementar cache warmer job
- [ ] Agregar frontend components
- [ ] Tests unitarios

## Desarrollo

### Ejecutar localmente
```bash
cd services/dilution-tracker
python -m uvicorn main:app --reload --port 8000
```

### Tests
```bash
pytest tests/
```

