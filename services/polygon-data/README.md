# Polygon Data Service

Centralized service for downloading and maintaining Polygon flat files.

## Features

- Downloads minute_aggs and day_aggs from Polygon S3
- Automatic daily updates via scheduler
- Provides shared volume for other services (screener, pattern-matching)

## Data Types

### Minute Aggregates (`minute_aggs/`)
- Minute-level OHLCV data
- ~300MB per day compressed
- Used by: pattern-matching

### Day Aggregates (`day_aggs/`)
- Daily OHLCV data
- ~5MB per day compressed
- Used by: screener

## API Endpoints

### `GET /health`
Health check.

### `GET /stats`
Download statistics for both data types.

### `POST /download`
Download data for a date range.

```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "data_types": ["day_aggs", "minute_aggs"],
  "force": false
}
```

### `POST /download/last-n-days`
Download last N days of data.

```bash
curl -X POST "http://localhost:8027/download/last-n-days?days=30&data_types=day_aggs"
```

### `POST /scheduler/run-now`
Trigger immediate scheduler update.

## Configuration

Environment variables:
- `POLYGON_DATA_POLYGON_S3_ACCESS_KEY`: S3 access key
- `POLYGON_DATA_POLYGON_S3_SECRET_KEY`: S3 secret key
- `POLYGON_DATA_DATA_DIR`: Base data directory (default: /data/polygon)
- `POLYGON_DATA_DAILY_UPDATE_HOUR`: Daily update hour UTC (default: 6)

## Volume Structure

```
/data/polygon/
├── minute_aggs/
│   ├── 2024-01-02.csv.gz
│   ├── 2024-01-03.csv.gz
│   └── ...
└── day_aggs/
    ├── 2024-01-02.csv.gz
    ├── 2024-01-03.csv.gz
    └── ...
```

## Usage

### Download initial data
```bash
# Download last 365 days of day_aggs
curl -X POST "http://localhost:8027/download/last-n-days?days=365&data_types=day_aggs"
```

### Check status
```bash
curl http://localhost:8027/stats
```

