# Pattern Matching Service 🎯

**Ultra-fast pattern similarity search for financial time series using FAISS**

## Overview

This service finds historical patterns similar to current price movements and generates probabilistic forecasts based on what happened after those similar patterns.

```
Input:  45 minutes of NVDA prices
Output: 50 similar historical patterns + forecast (68% probability of +1.2% in 15 min)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PATTERN MATCHING SERVICE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │ Flat Files      │     │ Data Processor  │                   │
│  │ Downloader      │────▶│ (Sliding        │                   │
│  │ (Polygon S3)    │     │  Windows)       │                   │
│  └─────────────────┘     └────────┬────────┘                   │
│                                   │                             │
│                                   ▼                             │
│                          ┌─────────────────┐                   │
│                          │ Pattern Indexer │                   │
│                          │ (FAISS IVF+PQ)  │                   │
│                          └────────┬────────┘                   │
│                                   │                             │
│                                   ▼                             │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │ Pattern Matcher │────▶│ Forecast        │                   │
│  │ (k-NN Search)   │     │ Generator       │                   │
│  └─────────────────┘     └─────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Add Polygon S3 Credentials to `.env`

```bash
# Get these from your Polygon dashboard
POLYGON_S3_ACCESS_KEY=your-access-key
POLYGON_S3_SECRET_KEY=your-secret-key
```

### 2. Start the Service

```bash
docker-compose up -d pattern_matching
```

### 3. Download Historical Data

```bash
# Download last 6 months of minute data
curl -X POST http://localhost:8025/api/data/download \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-07-01",
    "end_date": "2024-12-25"
  }'
```

### 4. Build the Index

```bash
# Build FAISS index from downloaded data
curl -X POST http://localhost:8025/api/index/build \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-07-01",
    "end_date": "2024-12-25",
    "download_first": false
  }'
```

### 5. Search for Patterns

```bash
# Search using real-time prices
curl http://localhost:8025/api/search/NVDA?k=50&cross_asset=true
```

## API Endpoints

### Search

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search/{symbol}` | GET | Quick search with real-time prices |
| `/api/search` | POST | Search with custom parameters |
| `/api/search/prices` | POST | Search with raw price array |

### Index Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/index/build` | POST | Build/rebuild FAISS index |
| `/api/index/build/status` | GET | Check build progress |
| `/api/index/reload` | POST | Reload index from disk |
| `/api/index/stats` | GET | Get index statistics |

### Data Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data/download` | POST | Download Polygon flat files |
| `/api/data/stats` | GET | Get download statistics |

## Example Response

```json
{
  "status": "success",
  "query": {
    "symbol": "NVDA",
    "window_minutes": 45,
    "timestamp": "2024-12-25T10:30:00",
    "cross_asset": true
  },
  "forecast": {
    "horizon_minutes": 15,
    "mean_return": 0.82,
    "prob_up": 0.68,
    "prob_down": 0.32,
    "confidence": "medium",
    "best_case": 2.4,
    "worst_case": -0.8,
    "n_neighbors": 50
  },
  "neighbors": [
    {
      "symbol": "TSLA",
      "date": "2024-11-15",
      "start_time": "10:30",
      "end_time": "11:15",
      "distance": 0.023,
      "future_returns": [0.3, 0.8, 1.2, 1.5, 1.8]
    }
  ],
  "stats": {
    "query_time_ms": 8.5,
    "index_size": 45000000,
    "k_returned": 50
  }
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WINDOW_SIZE` | 45 | Pattern window size (minutes) |
| `FUTURE_SIZE` | 15 | Forecast horizon (minutes) |
| `STEP_SIZE` | 5 | Sliding window step |
| `DEFAULT_K` | 50 | Default neighbors |
| `INDEX_TYPE` | IVF4096,PQ32 | FAISS index configuration |
| `INDEX_NPROBE` | 64 | Clusters to search |
| `USE_GPU` | false | Enable GPU acceleration |

## Storage Requirements

| Dataset | Flat Files | FAISS Index | Total |
|---------|------------|-------------|-------|
| 6 months | ~15 GB | ~2 GB | ~17 GB |
| 1 year | ~30 GB | ~4 GB | ~34 GB |
| 5 years | ~150 GB | ~20 GB | ~170 GB |

## Performance

| Metric | Value |
|--------|-------|
| Query latency | 5-15ms |
| Index build | ~2-4 hours (1 year) |
| Concurrent queries | 100+ |
| Memory usage | 4-8 GB |

## Maintenance

### Daily Update (Cron Job)

```bash
# Add to crontab to update index daily at 11:00 PM
0 23 * * 1-5 curl -X POST http://localhost:8025/api/index/build \
  -d '{"start_date":"2024-01-01","end_date":"'$(date +%Y-%m-%d)'","download_first":true}'
```

### Manual Rebuild

```bash
# Full rebuild
docker-compose exec pattern_matching python -c "
from flat_files_downloader import FlatFilesDownloader
from data_processor import DataProcessor
from pattern_indexer import PatternIndexer
from datetime import datetime
from glob import glob

# Download
d = FlatFilesDownloader()
d.download_range(datetime(2024,1,1), datetime.now())

# Process
p = DataProcessor()
files = sorted(glob('/app/data/minute_aggs/*.csv.gz'))
vectors, metadata = p.process_multiple_files(files)

# Index
i = PatternIndexer()
i.build_index(vectors, metadata)
i.save()
print(f'Built index with {len(vectors):,} patterns')
"
```

## Troubleshooting

### No index loaded

```bash
# Check if index exists
docker-compose exec pattern_matching ls -la /app/indexes/

# Build index if missing
curl -X POST http://localhost:8025/api/index/build -d '...'
```

### Slow queries

```bash
# Check index stats
curl http://localhost:8025/api/index/stats

# Increase nprobe for better accuracy (slower)
# Or decrease for faster queries (less accurate)
```

### Out of memory

```bash
# Reduce index size by filtering symbols
curl -X POST http://localhost:8025/api/index/build \
  -d '{"symbols_filter": ["AAPL","TSLA","NVDA","AMD","GOOGL"]}'
```

