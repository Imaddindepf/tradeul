-- ============================================================================
-- MIGRATION 004: OPTIMIZACIÓN DE USO DE MEMORIA
-- ============================================================================
-- Esta migración configura:
-- 1. Políticas de retención automáticas
-- 2. Compresión automática por edad
-- 3. Continuous aggregates para reducir CPU
-- 4. Índices optimizados
--
-- EJECUTAR: Una sola vez, se mantiene automáticamente después
-- ============================================================================

-- ============================================================================
-- 1. POLÍTICAS DE RETENCIÓN AUTOMÁTICAS
-- ============================================================================

-- scan_results: Mantener solo 3 días de datos raw
SELECT add_retention_policy(
    'scan_results',
    INTERVAL '3 days',
    if_not_exists => true
);

-- volume_slots: Mantener solo 14 días
SELECT add_retention_policy(
    'volume_slots',
    INTERVAL '14 days',
    if_not_exists => true
);

-- volume_slot_averages: Mantener solo 14 días
SELECT add_retention_policy(
    'volume_slot_averages',
    INTERVAL '14 days',
    if_not_exists => true
);

-- market_data_daily: Mantener solo 90 días
SELECT add_retention_policy(
    'market_data_daily',
    INTERVAL '90 days',
    if_not_exists => true
);

-- ============================================================================
-- 2. COMPRESIÓN AUTOMÁTICA
-- ============================================================================

-- Habilitar compresión en scan_results
ALTER TABLE scan_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,session',
    timescaledb.compress_orderby = 'time DESC'
);

-- Política: comprimir chunks > 2 horas
SELECT add_compression_policy(
    'scan_results',
    INTERVAL '2 hours',
    if_not_exists => true
);

-- Habilitar compresión en volume_slots
ALTER TABLE volume_slots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy(
    'volume_slots',
    INTERVAL '6 hours',
    if_not_exists => true
);

-- ============================================================================
-- 3. CONTINUOUS AGGREGATES (Pre-cálculos automáticos)
-- ============================================================================

-- Aggregate por 1 MINUTO (reduce 60x el tamaño)
CREATE MATERIALIZED VIEW IF NOT EXISTS scan_results_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', time) AS bucket,
    symbol,
    session,
    
    -- Precio (OHLC)
    FIRST(price, time) as open_price,
    MAX(price) as high_price,
    MIN(price) as low_price,
    LAST(price, time) as close_price,
    
    -- Volumen
    SUM(volume) as total_volume,
    LAST(volume_today, time) as volume_today,
    
    -- RVOL
    AVG(rvol) as avg_rvol,
    MAX(rvol) as max_rvol,
    LAST(rvol, time) as last_rvol,
    
    AVG(rvol_slot) as avg_rvol_slot,
    MAX(rvol_slot) as max_rvol_slot,
    
    -- Precio desde high/low
    AVG(price_from_high) as avg_price_from_high,
    AVG(price_from_low) as avg_price_from_low,
    
    -- Score
    AVG(score) as avg_score,
    MAX(score) as max_score,
    LAST(score, time) as last_score,
    
    -- Change %
    AVG(change_percent) as avg_change_percent,
    MAX(change_percent) as max_change_percent,
    
    -- Metadata
    LAST(market_cap, time) as market_cap,
    LAST(float_shares, time) as float_shares,
    
    -- Contadores
    COUNT(*) as sample_count
    
FROM scan_results
GROUP BY bucket, symbol, session;

-- Refresh cada 30 segundos
SELECT add_continuous_aggregate_policy(
    'scan_results_1min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds',
    if_not_exists => true
);

-- Retención de 30 días (vs 3 días de raw)
SELECT add_retention_policy(
    'scan_results_1min',
    INTERVAL '30 days',
    if_not_exists => true
);

-- ============================================================================

-- Aggregate por 1 HORA (para análisis histórico)
CREATE MATERIALIZED VIEW IF NOT EXISTS scan_results_1hour
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    symbol,
    session,
    
    FIRST(price, time) as open_price,
    MAX(price) as high_price,
    MIN(price) as low_price,
    LAST(price, time) as close_price,
    
    SUM(volume) as total_volume,
    LAST(volume_today, time) as volume_today,
    
    AVG(rvol) as avg_rvol,
    MAX(rvol) as max_rvol,
    
    AVG(score) as avg_score,
    MAX(score) as max_score,
    
    AVG(change_percent) as avg_change_percent,
    MAX(change_percent) as max_change_percent,
    
    LAST(market_cap, time) as market_cap,
    LAST(float_shares, time) as float_shares,
    
    COUNT(*) as sample_count
    
FROM scan_results
GROUP BY bucket, symbol, session;

SELECT add_continuous_aggregate_policy(
    'scan_results_1hour',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => true
);

-- Retención de 180 días (6 meses)
SELECT add_retention_policy(
    'scan_results_1hour',
    INTERVAL '180 days',
    if_not_exists => true
);

-- ============================================================================
-- 4. ÍNDICES OPTIMIZADOS (Partial indexes para datos recientes)
-- ============================================================================

-- Índice para queries por sesión (solo datos recientes)
DROP INDEX IF EXISTS idx_scan_session_time_score;
CREATE INDEX idx_scan_session_time_score 
ON scan_results (session, time DESC, score DESC)
WHERE time > NOW() - INTERVAL '3 days';

-- Índice para top movers por RVOL (solo hot data)
DROP INDEX IF EXISTS idx_scan_rvol_hot;
CREATE INDEX idx_scan_rvol_hot 
ON scan_results (rvol DESC, time DESC)
WHERE time > NOW() - INTERVAL '2 hours' AND rvol > 2.0;

-- Índice para búsqueda por símbolo (solo última sesión)
DROP INDEX IF EXISTS idx_scan_symbol_recent;
CREATE INDEX idx_scan_symbol_recent 
ON scan_results (symbol, time DESC)
WHERE time > NOW() - INTERVAL '24 hours';

-- ============================================================================
-- 5. CONFIGURACIÓN DE AUTOVACUUM AGRESIVO
-- ============================================================================

ALTER TABLE scan_results SET (
    autovacuum_vacuum_scale_factor = 0.05,  -- Vacuum cuando 5% cambió (vs 20% default)
    autovacuum_analyze_scale_factor = 0.02, -- Analyze cuando 2% cambió
    autovacuum_vacuum_cost_delay = 10,      -- Más agresivo
    autovacuum_vacuum_cost_limit = 1000     -- Mayor límite
);

ALTER TABLE volume_slots SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05
);

-- ============================================================================
-- 6. VERIFICAR CONFIGURACIÓN
-- ============================================================================

-- Ver políticas de retención activas
SELECT 
    hypertable_name,
    older_than,
    schedule_interval,
    config
FROM timescaledb_information.jobs j
JOIN timescaledb_information.job_stats js ON j.job_id = js.job_id
WHERE proc_name = 'policy_retention'
ORDER BY hypertable_name;

-- Ver políticas de compresión activas
SELECT 
    hypertable_name,
    older_than,
    schedule_interval
FROM timescaledb_information.jobs j
JOIN timescaledb_information.job_stats js ON j.job_id = js.job_id
WHERE proc_name = 'policy_compression'
ORDER BY hypertable_name;

-- Ver continuous aggregates
SELECT 
    view_name,
    refresh_lag,
    refresh_interval
FROM timescaledb_information.continuous_aggregates
ORDER BY view_name;

-- ============================================================================
-- MIGRACIÓN COMPLETADA
-- ============================================================================
-- 
-- ✅ Políticas de retención: automáticas
-- ✅ Compresión: automática cada 2 horas
-- ✅ Continuous aggregates: se refrescan automáticamente
-- ✅ Índices: optimizados para datos recientes
-- ✅ VACUUM: configurado agresivamente
--
-- El sistema ahora se auto-gestiona sin intervención manual
-- ============================================================================

