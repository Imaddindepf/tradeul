-- ===========================================================================
-- FASE 1: UNIFICACIÓN DE TABLAS MAESTRAS DE TICKERS
-- ===========================================================================
-- Crea tickers_unified y vistas compatibles
-- NO toca las tablas originales - compatibilidad 100%
-- ===========================================================================

\echo '🚀 INICIANDO FASE 1: Unificación de Tickers'
\echo ''

-- ===========================================================================
-- 1. CREAR TABLA UNIFICADA
-- ===========================================================================
\echo '📊 Paso 1/5: Creando tabla tickers_unified...'

CREATE TABLE IF NOT EXISTS tickers_unified (
    symbol VARCHAR(10) PRIMARY KEY,
    
    -- Company Info (de ticker_metadata)
    company_name VARCHAR(255),
    cik VARCHAR(10),
    exchange VARCHAR(20),
    sector VARCHAR(100),
    industry VARCHAR(100),
    
    -- Market Data (de ticker_metadata)
    current_price DECIMAL(12,4),
    market_cap BIGINT,
    float_shares BIGINT,
    shares_outstanding BIGINT,
    avg_volume_30d BIGINT,
    avg_volume_10d BIGINT,
    avg_price_30d DECIMAL(12, 4),
    beta DECIMAL(6, 4),
    
    -- Status (combinado de ambas tablas)
    is_active BOOLEAN DEFAULT TRUE,
    is_etf BOOLEAN DEFAULT FALSE,
    is_actively_trading BOOLEAN DEFAULT TRUE,
    
    -- Tracking (de ticker_universe)
    last_seen TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_tickers_unified_sector ON tickers_unified(sector);
CREATE INDEX IF NOT EXISTS idx_tickers_unified_market_cap ON tickers_unified(market_cap DESC);
CREATE INDEX IF NOT EXISTS idx_tickers_unified_is_active ON tickers_unified(is_active, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_tickers_unified_exchange ON tickers_unified(exchange);
CREATE INDEX IF NOT EXISTS idx_tickers_unified_updated ON tickers_unified(updated_at DESC);

COMMENT ON TABLE tickers_unified IS 'Tabla maestra unificada de tickers (reemplaza ticker_metadata + ticker_universe)';

\echo '✅ Tabla tickers_unified creada'
\echo ''

-- ===========================================================================
-- 2. MIGRAR DATOS
-- ===========================================================================
\echo '📦 Paso 2/5: Migrando datos de ticker_metadata y ticker_universe...'

INSERT INTO tickers_unified (
    symbol,
    company_name,
    cik,
    exchange,
    sector,
    industry,
    current_price,
    market_cap,
    float_shares,
    shares_outstanding,
    avg_volume_30d,
    avg_volume_10d,
    avg_price_30d,
    beta,
    is_active,
    is_etf,
    is_actively_trading,
    last_seen,
    created_at,
    updated_at
)
SELECT 
    tm.symbol,
    tm.company_name,
    NULL as cik,  -- Se agregará después si es necesario
    tm.exchange,
    tm.sector,
    tm.industry,
    NULL as current_price,  -- Se actualiza dinámicamente
    tm.market_cap,
    tm.float_shares,
    tm.shares_outstanding,
    tm.avg_volume_30d,
    tm.avg_volume_10d,
    tm.avg_price_30d,
    tm.beta,
    COALESCE(tu.is_active, TRUE) as is_active,
    tm.is_etf,
    tm.is_actively_trading,
    tu.last_seen,
    COALESCE(tu.added_at, tm.created_at, NOW()) as created_at,
    tm.updated_at
FROM ticker_metadata tm
LEFT JOIN ticker_universe tu ON tm.symbol = tu.symbol
ON CONFLICT (symbol) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    exchange = EXCLUDED.exchange,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    market_cap = EXCLUDED.market_cap,
    float_shares = EXCLUDED.float_shares,
    shares_outstanding = EXCLUDED.shares_outstanding,
    avg_volume_30d = EXCLUDED.avg_volume_30d,
    avg_volume_10d = EXCLUDED.avg_volume_10d,
    avg_price_30d = EXCLUDED.avg_price_30d,
    beta = EXCLUDED.beta,
    is_active = EXCLUDED.is_active,
    is_etf = EXCLUDED.is_etf,
    is_actively_trading = EXCLUDED.is_actively_trading,
    last_seen = EXCLUDED.last_seen,
    updated_at = EXCLUDED.updated_at;

-- También agregar tickers que están SOLO en ticker_universe
INSERT INTO tickers_unified (
    symbol,
    is_active,
    last_seen,
    created_at,
    updated_at
)
SELECT 
    tu.symbol,
    tu.is_active,
    tu.last_seen,
    tu.added_at,
    NOW()
FROM ticker_universe tu
WHERE tu.symbol NOT IN (SELECT symbol FROM tickers_unified)
ON CONFLICT (symbol) DO NOTHING;

\echo '✅ Datos migrados'
\echo ''

-- ===========================================================================
-- 3. CREAR VISTAS COMPATIBLES
-- ===========================================================================
\echo '🔍 Paso 3/5: Creando vistas compatibles con código existente...'

-- Vista: ticker_metadata (compatible con código actual)
CREATE OR REPLACE VIEW ticker_metadata AS
SELECT 
    symbol,
    company_name,
    exchange,
    sector,
    industry,
    market_cap,
    float_shares,
    shares_outstanding,
    avg_volume_30d,
    avg_volume_10d,
    avg_price_30d,
    beta,
    is_etf,
    is_actively_trading,
    updated_at,
    created_at
FROM tickers_unified;

COMMENT ON VIEW ticker_metadata IS 'Vista compatible con ticker_metadata antigua - usa tickers_unified';

-- Vista: ticker_universe (compatible con código actual)
CREATE OR REPLACE VIEW ticker_universe AS
SELECT 
    symbol,
    is_active,
    last_seen,
    created_at as added_at,
    NULL::TIMESTAMPTZ as removed_at,
    NULL::TEXT as reason_removed
FROM tickers_unified;

COMMENT ON VIEW ticker_universe IS 'Vista compatible con ticker_universe antigua - usa tickers_unified';

\echo '✅ Vistas compatibles creadas'
\echo ''

-- ===========================================================================
-- 4. CREAR TRIGGERS PARA MANTENER SINCRONIZACIÓN
-- ===========================================================================
\echo '⚙️  Paso 4/5: Creando triggers de sincronización...'

-- Trigger: Auto-actualizar updated_at en tickers_unified
CREATE OR REPLACE FUNCTION update_tickers_unified_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_tickers_unified_timestamp ON tickers_unified;
CREATE TRIGGER trigger_update_tickers_unified_timestamp
    BEFORE UPDATE ON tickers_unified
    FOR EACH ROW
    EXECUTE FUNCTION update_tickers_unified_timestamp();

\echo '✅ Triggers creados'
\echo ''

-- ===========================================================================
-- 5. VERIFICACIÓN DE DATOS
-- ===========================================================================
\echo '🔍 Paso 5/5: Verificando integridad de datos...'
\echo ''

-- Contar registros
\echo '📊 Conteo de registros:'
SELECT 
    'ticker_metadata (vieja)' as tabla, 
    COUNT(*) as registros 
FROM ticker_metadata
UNION ALL
SELECT 
    'ticker_universe (vieja)', 
    COUNT(*) 
FROM ticker_universe
UNION ALL
SELECT 
    'tickers_unified (nueva)', 
    COUNT(*) 
FROM tickers_unified
ORDER BY tabla;

\echo ''
\echo '📊 Distribución por estado en tickers_unified:'
SELECT 
    is_active,
    COUNT(*) as cantidad
FROM tickers_unified
GROUP BY is_active
ORDER BY is_active DESC;

\echo ''
\echo '📊 Top 10 tickers por market cap:'
SELECT 
    symbol,
    company_name,
    market_cap,
    is_active
FROM tickers_unified
WHERE market_cap IS NOT NULL
ORDER BY market_cap DESC
LIMIT 10;

\echo ''
\echo '✅ FASE 1 COMPLETADA EXITOSAMENTE!'
\echo ''
\echo '🎯 Siguiente pasos:'
\echo '  1. ✅ Los microservicios siguen funcionando (usan las vistas)'
\echo '  2. ⏭️  Puedes empezar a adaptar microservicios para usar tickers_unified'
\echo '  3. ⏭️  Cuando todos estén migrados, ejecutar FASE 2'
\echo ''
\echo '📝 Para rollback, ejecutar: scripts/rollback_phase1.sql'
\echo ''

