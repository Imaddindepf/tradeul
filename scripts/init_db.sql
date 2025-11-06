-- =============================================
-- TRADEUL SCANNER - INICIALIZACIÓN DE BASE DE DATOS
-- =============================================

-- Crear extensión TimescaleDB si no existe
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================
-- TABLA: TICKS EN TIEMPO REAL
-- =============================================

CREATE TABLE IF NOT EXISTS ticks (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    price DECIMAL(12, 4),
    size INTEGER,
    volume BIGINT,
    bid DECIMAL(12, 4),
    ask DECIMAL(12, 4),
    bid_size INTEGER,
    ask_size INTEGER,
    exchange VARCHAR(10),
    conditions TEXT[],
    tape VARCHAR(1)
);

-- Convertir a hypertable (particionado por tiempo)
SELECT create_hypertable('ticks', 'time', if_not_exists => TRUE);

-- Índices para optimizar queries
CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time ON ticks (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_ticks_time ON ticks (time DESC);

-- Política de compresión (datos >1 día)
ALTER TABLE ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol'
);

SELECT add_compression_policy('ticks', INTERVAL '1 day', if_not_exists => TRUE);

-- Política de retención (eliminar datos >90 días)
SELECT add_retention_policy('ticks', INTERVAL '90 days', if_not_exists => TRUE);

-- =============================================
-- TABLA: METADATOS DE TICKERS
-- =============================================

CREATE TABLE IF NOT EXISTS ticker_metadata (
    symbol VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255),
    exchange VARCHAR(20),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    float_shares BIGINT,
    shares_outstanding BIGINT,
    avg_volume_30d BIGINT,
    avg_volume_10d BIGINT,
    avg_price_30d DECIMAL(12, 4),
    beta DECIMAL(6, 4),
    is_etf BOOLEAN DEFAULT FALSE,
    is_actively_trading BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_sector ON ticker_metadata (sector);
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_market_cap ON ticker_metadata (market_cap DESC);
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_updated ON ticker_metadata (updated_at DESC);

-- =============================================
-- TABLA: RESULTADOS DE SCANS
-- =============================================

CREATE TABLE IF NOT EXISTS scan_results (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    session VARCHAR(20) NOT NULL,
    price DECIMAL(12, 4),
    volume BIGINT,
    volume_today BIGINT,
    change_percent DECIMAL(8, 4),
    rvol DECIMAL(10, 4),
    rvol_slot DECIMAL(10, 4),
    price_from_high DECIMAL(8, 4),
    price_from_low DECIMAL(8, 4),
    market_cap BIGINT,
    float_shares BIGINT,
    score DECIMAL(10, 4),
    filters_matched TEXT[],
    metadata JSONB
);

-- Convertir a hypertable
SELECT create_hypertable('scan_results', 'time', if_not_exists => TRUE);

-- Índices
CREATE INDEX IF NOT EXISTS idx_scan_results_symbol_time ON scan_results (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_scan_results_session ON scan_results (session, time DESC);
CREATE INDEX IF NOT EXISTS idx_scan_results_rvol ON scan_results (rvol DESC, time DESC);
CREATE INDEX IF NOT EXISTS idx_scan_results_score ON scan_results (score DESC, time DESC);

-- Política de compresión (datos >7 días)
ALTER TABLE scan_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,session'
);

SELECT add_compression_policy('scan_results', INTERVAL '7 days', if_not_exists => TRUE);

-- Política de retención (eliminar datos >180 días)
SELECT add_retention_policy('scan_results', INTERVAL '180 days', if_not_exists => TRUE);

-- =============================================
-- TABLA: HISTÓRICO DE VOLUMEN POR SLOTS
-- =============================================

CREATE TABLE IF NOT EXISTS volume_slots (
    date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    slot_number INTEGER NOT NULL,  -- 0-77 (slots de 5 min en 390 min)
    slot_time TIME NOT NULL,
    volume_accumulated BIGINT,
    trades_count INTEGER,
    avg_price DECIMAL(12, 4),
    PRIMARY KEY (date, symbol, slot_number)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_volume_slots_symbol ON volume_slots (symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_volume_slots_date ON volume_slots (date DESC);

-- =============================================
-- TABLA: DATOS OHLC DIARIOS (para ATR y otros indicadores)
-- =============================================

CREATE TABLE IF NOT EXISTS market_data_daily (
    trading_date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    open DECIMAL(12, 4) NOT NULL,
    high DECIMAL(12, 4) NOT NULL,
    low DECIMAL(12, 4) NOT NULL,
    close DECIMAL(12, 4) NOT NULL,
    volume BIGINT NOT NULL,
    vwap DECIMAL(12, 4),
    trades_count INTEGER,
    PRIMARY KEY (trading_date, symbol)
);

-- Convertir a hypertable para TimescaleDB
SELECT create_hypertable('market_data_daily', 'trading_date', 
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 month'
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_market_data_daily_symbol ON market_data_daily (symbol, trading_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_daily_date ON market_data_daily (trading_date DESC);

-- =============================================
-- TABLA: CONFIGURACIÓN DE FILTROS
-- =============================================

CREATE TABLE IF NOT EXISTS scanner_filters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    filter_type VARCHAR(50) NOT NULL,  -- 'rvol', 'price', 'volume', 'custom'
    parameters JSONB NOT NULL,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_scanner_filters_enabled ON scanner_filters (enabled, priority DESC);

-- Filtros por defecto
INSERT INTO scanner_filters (name, description, enabled, filter_type, parameters, priority)
VALUES 
    ('rvol_high', 'Alto volumen relativo', TRUE, 'rvol', '{"min_rvol": 2.0}', 10),
    ('price_range', 'Precio mínimo tradeable', TRUE, 'price', '{"min_price": 1.0}', 5),
    ('volume_min', 'Volumen mínimo', TRUE, 'volume', '{"min_volume": 100000}', 5)
ON CONFLICT (name) DO NOTHING;

-- =============================================
-- TABLA: MARKET HOLIDAYS
-- =============================================

CREATE TABLE IF NOT EXISTS market_holidays (
    date DATE PRIMARY KEY,
    name VARCHAR(100),
    exchange VARCHAR(20) DEFAULT 'NASDAQ',
    is_early_close BOOLEAN DEFAULT FALSE,
    early_close_time TIME
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_market_holidays_date ON market_holidays (date DESC);

-- =============================================
-- TABLA: SESIONES DE MERCADO (LOG)
-- =============================================

CREATE TABLE IF NOT EXISTS market_sessions_log (
    time TIMESTAMPTZ NOT NULL,
    session VARCHAR(20) NOT NULL,
    trading_date DATE NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- 'session_start', 'session_end', 'session_change'
    metadata JSONB
);

-- Convertir a hypertable
SELECT create_hypertable('market_sessions_log', 'time', if_not_exists => TRUE);

-- Índices
CREATE INDEX IF NOT EXISTS idx_market_sessions_log_date ON market_sessions_log (trading_date DESC, time DESC);

-- Política de retención (eliminar datos >365 días)
SELECT add_retention_policy('market_sessions_log', INTERVAL '365 days', if_not_exists => TRUE);

-- =============================================
-- TABLA: UNIVERSO DE TICKERS
-- =============================================

CREATE TABLE IF NOT EXISTS ticker_universe (
    symbol VARCHAR(10) PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    added_at TIMESTAMPTZ DEFAULT NOW(),
    removed_at TIMESTAMPTZ,
    reason_removed TEXT
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_ticker_universe_active ON ticker_universe (is_active, last_seen DESC);

-- =============================================
-- VISTAS ÚTILES
-- =============================================

-- Vista: Top scanners de hoy
CREATE OR REPLACE VIEW v_today_top_scanners AS
SELECT 
    symbol,
    MAX(rvol) as max_rvol,
    MAX(score) as max_score,
    MAX(volume_today) as max_volume,
    COUNT(*) as scan_count,
    MAX(time) as last_seen
FROM scan_results
WHERE time >= CURRENT_DATE
GROUP BY symbol
ORDER BY max_score DESC, max_rvol DESC
LIMIT 100;

-- Vista: Resumen de actividad por sesión
CREATE OR REPLACE VIEW v_session_activity AS
SELECT 
    session,
    DATE(time) as trading_date,
    COUNT(DISTINCT symbol) as unique_symbols,
    AVG(rvol) as avg_rvol,
    MAX(rvol) as max_rvol,
    SUM(volume_today) as total_volume
FROM scan_results
WHERE time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY session, DATE(time)
ORDER BY trading_date DESC, session;

-- =============================================
-- FUNCIONES ÚTILES
-- =============================================

-- Función: Limpiar datos antiguos manualmente
CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- Limpiar ticks >90 días
    DELETE FROM ticks WHERE time < NOW() - INTERVAL '90 days';
    
    -- Limpiar scan_results >180 días
    DELETE FROM scan_results WHERE time < NOW() - INTERVAL '180 days';
    
    -- Limpiar market_sessions_log >365 días
    DELETE FROM market_sessions_log WHERE time < NOW() - INTERVAL '365 days';
    
    RAISE NOTICE 'Limpieza completada';
END;
$$ LANGUAGE plpgsql;

-- Función: Actualizar timestamp de ticker_metadata
CREATE OR REPLACE FUNCTION update_ticker_metadata_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Auto-actualizar updated_at
DROP TRIGGER IF EXISTS trigger_update_ticker_metadata_timestamp ON ticker_metadata;
CREATE TRIGGER trigger_update_ticker_metadata_timestamp
    BEFORE UPDATE ON ticker_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_ticker_metadata_timestamp();

-- =============================================
-- PERMISOS
-- =============================================

-- Otorgar permisos al usuario de la aplicación
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tradeul_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tradeul_user;

-- =============================================
-- FINALIZACIÓN
-- =============================================

-- Vacuum y analyze para optimizar
VACUUM ANALYZE;

-- Mensaje de confirmación
DO $$
BEGIN
    RAISE NOTICE '✅ Base de datos inicializada correctamente';
    RAISE NOTICE '📊 Tablas creadas: ticks, ticker_metadata, scan_results, volume_slots, scanner_filters, market_holidays, market_sessions_log, ticker_universe';
    RAISE NOTICE '🔍 Vistas creadas: v_today_top_scanners, v_session_activity';
END $$;

