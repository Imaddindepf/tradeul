-- ============================================================================
-- minute_bars: compresión + retención (Fase 0e, 2026-08-02)
-- ============================================================================
-- Medido: 28 GB, 221M filas, 2026-02-09 → hoy, SIN política de retención.
-- Crece sin límite (~5 GB/mes). Escriben: analytics BarEngine (equities),
-- fmp_indices y fmp_forex (índices/futuros/forex — por eso hay filas 24/7).
--
-- Consumidores medidos y su lookback real:
--   - alert_engine baseline loader ....... 10 días  (σ intradía 1m/5m/15m)
--   - analytics BarEngine warmup ......... minutos
--   - api_gateway internal chart (FUT/FX)  from/to libre — con retención N
--     días, un chart interno diario muestra como mucho ~N*0.7 velas diarias
--   - mcp-gateway get_minute_bars(date) .. fecha libre (el agente); fechas
--     anteriores a la retención devolverán vacío (el minuto raw 2019+ sigue
--     en parquet: /data/polygon/minute_aggs/)
--
-- Aplicar como tradeul_user en la base tradeul:
--   docker exec -it tradeul_timescale psql -U tradeul_user -d tradeul \
--     -f /ruta/a/minute_bars_retention.sql
-- (o pegar los bloques a mano; cada bloque es independiente)

-- ----------------------------------------------------------------------------
-- 1) COMPRESIÓN de chunks > 7 días (28 GB → ~3-6 GB típico en OHLCV).
--    Sin pérdida, transparente para SELECT. Reduce la urgencia de retener.
-- ----------------------------------------------------------------------------
ALTER TABLE minute_bars SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'symbol',
  timescaledb.compress_orderby   = 'ts'
);
SELECT add_compression_policy('minute_bars', compress_after => INTERVAL '7 days');

-- ----------------------------------------------------------------------------
-- 2) RETENCIÓN — elegir UNA de las dos:
-- ----------------------------------------------------------------------------

-- Opción A (recomendada con compresión activada): 365 días.
-- Mantiene un año de charts internos FUT/FX y del tool del agente,
-- comprimido ocupa pocos GB.
SELECT add_retention_policy('minute_bars', drop_after => INTERVAL '365 days');

-- Opción B (sin compresión, más agresiva): 180 días — descomentar esta y
-- comentar la A si se prefiere no activar compresión.
-- SELECT add_retention_policy('minute_bars', drop_after => INTERVAL '180 days');

-- Verificación posterior:
--   SELECT * FROM timescaledb_information.jobs
--    WHERE hypertable_name = 'minute_bars';
--   SELECT pg_size_pretty(hypertable_size('minute_bars'));
