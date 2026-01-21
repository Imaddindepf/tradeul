# SQL Examples for RAG
# Verified working examples for Gemini File Search

## QUERY 1: Count gappers with specific gap percentage
**Natural Language**: "cuantos gappers hubo el 16 de enero con gap mayor a 5%"
**English**: "how many gappers were there on January 16 with gap greater than 5%"

```sql
WITH yesterday AS (
  SELECT ticker, close AS prev_close
  FROM read_parquet('/data/polygon/day_aggs/2026-01-15.parquet')
), 
today AS (
  SELECT ticker, open
  FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT COUNT(*) as gapper_count
FROM today t
JOIN yesterday y ON t.ticker = y.ticker
WHERE (t.open - y.prev_close) / y.prev_close > 0.05;
```

---

## QUERY 2: Top N gappers by gap percentage
**Natural Language**: "top 10 gappers del 16 de enero ordenados por porcentaje de gap"
**English**: "top 10 gappers on January 16 sorted by gap percentage"

```sql
WITH yesterday AS (
  SELECT ticker, close AS prev_close
  FROM read_parquet('/data/polygon/day_aggs/2026-01-15.parquet')
),
today AS (
  SELECT ticker, open, close, volume
  FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT
  t.ticker,
  y.prev_close,
  t.open,
  t.close,
  t.volume,
  ROUND((t.open - y.prev_close) / y.prev_close * 100, 2) AS gap_pct
FROM today AS t
JOIN yesterday AS y ON t.ticker = y.ticker
WHERE y.prev_close > 0
ORDER BY gap_pct DESC
LIMIT 10;
```

---

## QUERY 3: Gappers that closed below VWAP
**Natural Language**: "gappers del 16 enero con gap > 5% que cerraron por debajo del VWAP"
**English**: "gappers on January 16 with gap > 5% that closed below VWAP"

```sql
WITH prev_day AS (
  SELECT ticker, close AS prev_close
  FROM read_parquet('/data/polygon/day_aggs/2026-01-15.parquet')
),
current_day AS (
  SELECT ticker, open, high, low, close, volume
  FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT
  c.ticker,
  p.prev_close,
  c.open,
  c.close,
  ROUND((c.open - p.prev_close) / p.prev_close * 100, 2) AS gap_pct,
  ROUND((c.high + c.low + c.close) / 3, 2) AS vwap_approx,
  c.volume
FROM current_day c
JOIN prev_day p ON c.ticker = p.ticker
WHERE
  (c.open - p.prev_close) / p.prev_close > 0.05
  AND c.close < (c.high + c.low + c.close) / 3
ORDER BY gap_pct DESC;
```

---

## QUERY 4: Top weekly gainers
**Natural Language**: "top 10 gainers de la semana del 13 al 16 enero"
**English**: "top 10 gainers from January 13 to 16"

```sql
WITH semana_inicio AS (
  SELECT ticker, open AS open_del_13
  FROM read_parquet('/data/polygon/day_aggs/2026-01-13.parquet')
),
semana_fin AS (
  SELECT ticker, close AS close_del_16, high, low, volume
  FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT
  s.ticker,
  s.open_del_13,
  f.close_del_16,
  ROUND(((f.close_del_16 - s.open_del_13) / s.open_del_13) * 100, 2) AS ganancia_semanal_pct,
  ROUND((f.high + f.low + f.close_del_16) / 3, 2) AS vwap_aprox_del_16,
  f.volume AS volumen_del_16
FROM semana_inicio s
JOIN semana_fin f ON s.ticker = f.ticker
ORDER BY ganancia_semanal_pct DESC
LIMIT 10;
```

---

## QUERY 5: Small caps with high volume
**Natural Language**: "acciones con precio menor a 5 dolares y volumen mayor a 10 millones"
**English**: "stocks with price under 5 dollars and volume greater than 10 million"

```sql
SELECT
  ticker,
  close,
  volume
FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
WHERE close < 5 AND volume > 10000000
ORDER BY volume DESC;
```

---

## QUERY 6: Single day gapper count with threshold
**Natural Language**: "numero de gappers el 14 de enero con gap mayor a 10%"
**English**: "number of gappers on January 14 with gap greater than 10%"

```sql
WITH prev_day AS (
  SELECT ticker, close AS prev_close
  FROM read_parquet('/data/polygon/day_aggs/2026-01-13.parquet')
),
current_day AS (
  SELECT ticker, open
  FROM read_parquet('/data/polygon/day_aggs/2026-01-14.parquet')
)
SELECT COUNT(*) as num_gappers
FROM current_day c
JOIN prev_day p ON c.ticker = p.ticker
WHERE (c.open - p.prev_close) / p.prev_close > 0.10;
```

---

## QUERY 7: Top losers of the day
**Natural Language**: "top 10 perdedores del 16 de enero"
**English**: "top 10 losers on January 16"

```sql
SELECT
  ticker,
  open,
  close,
  ROUND((close - open) / open * 100, 2) AS change_pct,
  volume
FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
WHERE open > 0
ORDER BY change_pct ASC
LIMIT 10;
```

---

## QUERY 8: Stocks above VWAP with high volume
**Natural Language**: "acciones que cerraron por encima del VWAP con volumen mayor a 1 millon"
**English**: "stocks that closed above VWAP with volume greater than 1 million"

```sql
SELECT
  ticker,
  close,
  ROUND((high + low + close) / 3, 2) AS vwap_approx,
  ROUND((close - (high + low + close) / 3) / ((high + low + close) / 3) * 100, 2) AS pct_above_vwap,
  volume
FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
WHERE close > (high + low + close) / 3 AND volume > 1000000
ORDER BY pct_above_vwap DESC
LIMIT 20;
```

---

## QUERY 9: Weekly gainers that closed above VWAP
**Natural Language**: "top gainers de la semana que cerraron arriba del vwap"
**English**: "top weekly gainers that closed above VWAP"

```sql
WITH semana_inicio AS (
  SELECT ticker, open AS open_start
  FROM read_parquet('/data/polygon/day_aggs/2026-01-13.parquet')
),
semana_fin AS (
  SELECT ticker, close, high, low, volume
  FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT
  s.ticker,
  s.open_start,
  f.close,
  ROUND((f.close - s.open_start) / s.open_start * 100, 2) AS weekly_gain_pct,
  f.volume
FROM semana_inicio s
JOIN semana_fin f ON s.ticker = f.ticker
WHERE f.close > (f.high + f.low + f.close) / 3
ORDER BY weekly_gain_pct DESC
LIMIT 10;
```

---

## QUERY 10: Gap up that reversed (closed red)
**Natural Language**: "gappers que abrieron arriba pero cerraron en rojo"
**English**: "gap ups that reversed and closed red"

```sql
WITH prev_day AS (
  SELECT ticker, close AS prev_close
  FROM read_parquet('/data/polygon/day_aggs/2026-01-15.parquet')
),
current_day AS (
  SELECT ticker, open, close, volume
  FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT
  c.ticker,
  p.prev_close,
  c.open,
  c.close,
  ROUND((c.open - p.prev_close) / p.prev_close * 100, 2) AS gap_pct,
  ROUND((c.close - c.open) / c.open * 100, 2) AS intraday_change_pct,
  c.volume
FROM current_day c
JOIN prev_day p ON c.ticker = p.ticker
WHERE
  (c.open - p.prev_close) / p.prev_close > 0.05  -- Gap up > 5%
  AND c.close < c.open  -- Closed red
ORDER BY gap_pct DESC
LIMIT 20;
```

---

## IMPORTANT NOTES FOR SQL GENERATION

1. **VWAP Calculation**: day_aggs does NOT have VWAP column. Use approximate: `(high + low + close) / 3`

2. **Gap Calculation**: Always use JOIN between two days:
   - Previous day: `close AS prev_close`
   - Current day: `open`
   - Gap formula: `(open - prev_close) / prev_close * 100`

3. **File Paths**: 
   - Format: `/data/polygon/day_aggs/YYYY-MM-DD.parquet`
   - Use specific dates, not GLOB for simple queries

4. **Weekly Analysis**: JOIN first day with last day directly. Do NOT use complex UNION ALL or window functions.

5. **Column Names**: ticker, open, high, low, close, volume, window_start, transactions

6. **Output Format**: Always include ticker and relevant metrics. Round percentages to 2 decimals.
