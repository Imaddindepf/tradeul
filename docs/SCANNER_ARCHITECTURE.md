# TradeUL Scanner Architecture v2.0

## 1. Overview

Real-time stock scanner processing 6000+ tickers every 10 seconds using RETE algorithm for efficient pattern matching.

### High-Level Flow

```
Polygon REST/WS -> Data Ingest -> Scanner Engine -> WebSocket Server -> Browser
                                       |
                                     Redis
```

## 2. Components

| Service | Location | Function |
|---------|----------|----------|
| Data Ingest | /services/data_ingest | Enriched snapshots |
| Scanner Engine | /services/scanner | RETE evaluation |
| WebSocket Server | /services/websocket_server | Real-time delivery |
| API Gateway | /services/api_gateway | User filter CRUD |

## 3. Data Pipeline

### Layer 1: Data Sources
- Polygon REST API (snapshot every 10s)
- Polygon WebSocket (aggregates every 1s)
- TimescaleDB (historical data)

### Layer 2: Data Enrichment
- Merges snapshot + aggregates
- Calculates RVOL, ATR
- Output: snapshot:enriched:latest (6000+ tickers)

### Layer 3: Processing (Scanner)
- Reads enriched snapshot
- RETE network evaluates all rules
- System rules: gappers_up, momentum_up, high_rvol
- User rules: uscan_23, uscan_45
- Output: scanner:category:{list} + stream:ranking:deltas

### Layer 4: Delivery (WebSocket)
- Reads stream:ranking:deltas
- Routes aggregates via symbolToLists
- Broadcasts to subscribed clients

### Layer 5: Presentation (Frontend)
- ScanBuilderContent: Filter UI
- ScannerTableContent: Real-time tables
- useScanner hook: WebSocket management
