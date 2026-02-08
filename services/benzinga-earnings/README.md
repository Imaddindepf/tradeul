# Benzinga Earnings Service

Real-time earnings data streaming service using Polygon.io's Benzinga Earnings API.

## Features

- **Real-time Polling**: Polls Benzinga API every 30 seconds for updates
- **Redis Caching**: Fast in-memory cache for frontend queries
- **Redis Streams**: Real-time push notifications to frontend via WebSocket
- **TimescaleDB Persistence**: Historical data storage for analysis
- **Deduplication**: Intelligent change detection to avoid redundant updates

## Architecture

```
Polygon/Benzinga API
        ↓ (polling every 30s)
EarningsStreamManager
        ↓
   ┌────┴────┐
   ↓         ↓
Redis      Redis Stream ──→ WebSocket Server ──→ Frontend
Cache      "stream:benzinga:earnings"
   ↓
TimescaleDB
```

## API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /status` - Detailed status with statistics

### Earnings Data
- `GET /api/v1/earnings/today` - Today's earnings
- `GET /api/v1/earnings/upcoming?days=7` - Upcoming earnings
- `GET /api/v1/earnings/date/{YYYY-MM-DD}` - Earnings by date
- `GET /api/v1/earnings/ticker/{SYMBOL}` - Earnings history for ticker
- `POST /api/v1/earnings/sync` - Trigger manual sync

### Stream Info
- `GET /api/v1/stream/info` - Redis stream information

## Configuration

Environment variables:
- `POLYGON_API_KEY` - Polygon.io API key (required)
- `REDIS_HOST` - Redis host (default: redis)
- `REDIS_PORT` - Redis port (default: 6379)
- `TIMESCALE_HOST` - TimescaleDB host (default: timescaledb)
- `POLL_INTERVAL_SECONDS` - Polling interval (default: 30)
- `FULL_SYNC_INTERVAL_MINUTES` - Full sync interval (default: 60)

## Redis Keys

- `stream:benzinga:earnings` - Redis stream for real-time updates
- `cache:benzinga:earnings:today` - Today's earnings cache
- `cache:benzinga:earnings:upcoming` - Upcoming earnings cache
- `cache:benzinga:earnings:date:{date}` - Earnings by date
- `cache:benzinga:earnings:ticker:{ticker}` - Earnings by ticker
- `dedup:benzinga:earnings` - Deduplication set

## Running

```bash
# Development
python main.py

# Docker
docker build -t benzinga-earnings .
docker run -p 8020:8020 --env-file .env benzinga-earnings
```
