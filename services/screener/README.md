# Screener Service

High-performance stock screener using DuckDB for analytical queries.
Calculates 60+ technical indicators from Polygon flat files.

## Features

- **60+ Technical Indicators**: RSI, MACD, Bollinger Bands, ATR, MAs, Beta, and more
- **DuckDB Engine**: Queries over parquet files in milliseconds
- **Flexible Filters**: Combine any indicators with AND logic
- **Built-in Presets**: Popular screener strategies ready to use

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run service
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### `POST /api/v1/screener/screen`
Run screener with custom filters.

```json
{
  "filters": [
    {"field": "price", "operator": "between", "value": [10, 100]},
    {"field": "rsi_14", "operator": "lt", "value": 35},
    {"field": "volume", "operator": "gt", "value": 1000000}
  ],
  "sort_by": "relative_volume",
  "sort_order": "desc",
  "limit": 50
}
```

### `GET /api/v1/screener/indicators`
List all available indicators.

### `GET /api/v1/screener/screen/presets`
Get built-in screener presets.

## Indicator Categories

### Price
- `price`, `change_1d`, `change_5d`, `change_20d`, `gap_percent`
- `high_52w`, `low_52w`, `from_52w_high`, `from_52w_low`
- `new_high_52w`, `new_low_52w`

### Volume
- `volume`, `avg_volume_10`, `avg_volume_20`, `avg_volume_50`
- `relative_volume`, `volume_change`, `dollar_volume`
- `volume_spike`

### Momentum
- `rsi_14`, `rsi_oversold`, `rsi_overbought`
- `macd`, `macd_signal`, `macd_histogram`, `macd_bullish`, `macd_bearish`
- `stoch_k`, `stoch_d`, `williams_r`, `cci_20`, `mfi_14`

### Trend
- `sma_10`, `sma_20`, `sma_50`, `sma_200`
- `ema_9`, `ema_21`
- `above_sma_20`, `above_sma_50`, `above_sma_200`
- `dist_sma_20`, `dist_sma_50`, `dist_sma_200`
- `golden_cross`, `death_cross`, `sma_50_above_200`
- `adx_14`, `plus_di`, `minus_di`, `trend_strong`

### Volatility
- `atr_14`, `atr_percent`
- `hv_20`, `hv_60`
- `bb_upper`, `bb_middle`, `bb_lower`
- `bb_width`, `bb_position`, `bb_squeeze`
- `above_bb_upper`, `below_bb_lower`
- `daily_range`, `avg_daily_range`

### Comparative (vs SPY)
- `beta_60`, `correlation_60`
- `relative_strength_20`, `relative_strength_60`
- `outperforming_spy_20`, `alpha_60`
- `high_beta`, `low_beta`

## Filter Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `gt` | Greater than | `{"field": "rsi_14", "operator": "gt", "value": 70}` |
| `gte` | Greater or equal | |
| `lt` | Less than | |
| `lte` | Less or equal | |
| `eq` | Equal | `{"field": "golden_cross", "operator": "eq", "value": true}` |
| `between` | Range | `{"field": "price", "operator": "between", "value": [10, 50]}` |

## Configuration

Environment variables:
- `SCREENER_DATA_PATH`: Path to Polygon parquet files
- `SCREENER_REDIS_URL`: Redis URL for caching
- `SCREENER_CACHE_TTL_SECONDS`: Cache TTL (default: 60)
- `SCREENER_MAX_RESULTS`: Maximum results per query (default: 500)

## Architecture

```
services/screener/
├── main.py                 # FastAPI application
├── config.py               # Configuration
├── core/
│   ├── indicators/         # Technical indicator definitions
│   ├── filters/            # Filter parsing and validation
│   └── engine/             # DuckDB query engine
└── api/
    ├── routes/             # API endpoints
    └── schemas/            # Pydantic models
```

## Performance

- Queries 8000+ tickers in <100ms
- All indicators calculated with SQL window functions
- Optional Redis caching for repeated queries

