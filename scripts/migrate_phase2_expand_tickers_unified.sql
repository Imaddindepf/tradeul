-- ===========================================================================
-- FASE 2: EXPANDIR tickers_unified con campos adicionales
-- ===========================================================================
-- Agrega todos los campos que usa ticker-metadata-service
-- ===========================================================================

\echo '🚀 INICIANDO FASE 2: Expansión de tickers_unified'
\echo ''

-- ===========================================================================
-- 1. AGREGAR COLUMNAS FALTANTES
-- ===========================================================================
\echo '📊 Paso 1/4: Agregando columnas faltantes a tickers_unified...'

-- Información de la compañía
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS homepage_url TEXT;
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS address JSONB;
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS total_employees INTEGER;
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS list_date DATE;

-- Branding
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS icon_url TEXT;

-- Identificadores
-- cik ya existe, pero agregamos el resto
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS composite_figi VARCHAR(20);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS share_class_figi VARCHAR(20);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS ticker_root VARCHAR(10);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS ticker_suffix VARCHAR(10);

-- Detalles del activo
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS type VARCHAR(20);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS currency_name VARCHAR(20);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS locale VARCHAR(10);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS market VARCHAR(20);
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS round_lot INTEGER;
ALTER TABLE tickers_unified ADD COLUMN IF NOT EXISTS delisted_utc TIMESTAMPTZ;

\echo '✅ Columnas agregadas'
\echo ''

-- ===========================================================================
-- 2. MIGRAR DATOS DESDE ticker_metadata_old
-- ===========================================================================
\echo '📦 Paso 2/4: Migrando datos extendidos desde ticker_metadata_old...'

UPDATE tickers_unified tu
SET 
    description = COALESCE(tu.description, tm.description),
    homepage_url = COALESCE(tu.homepage_url, tm.homepage_url),
    phone_number = COALESCE(tu.phone_number, tm.phone_number),
    address = COALESCE(tu.address, tm.address),
    total_employees = COALESCE(tu.total_employees, tm.total_employees),
    list_date = COALESCE(tu.list_date, tm.list_date),
    logo_url = COALESCE(tu.logo_url, tm.logo_url),
    icon_url = COALESCE(tu.icon_url, tm.icon_url),
    composite_figi = COALESCE(tu.composite_figi, tm.composite_figi),
    share_class_figi = COALESCE(tu.share_class_figi, tm.share_class_figi),
    ticker_root = COALESCE(tu.ticker_root, tm.ticker_root),
    ticker_suffix = COALESCE(tu.ticker_suffix, tm.ticker_suffix),
    type = COALESCE(tu.type, tm.type),
    currency_name = COALESCE(tu.currency_name, tm.currency_name),
    locale = COALESCE(tu.locale, tm.locale),
    market = COALESCE(tu.market, tm.market),
    round_lot = COALESCE(tu.round_lot, tm.round_lot),
    delisted_utc = COALESCE(tu.delisted_utc, tm.delisted_utc)
FROM ticker_metadata_old tm
WHERE tu.symbol = tm.symbol
AND (
    tu.description IS NULL OR
    tu.homepage_url IS NULL OR
    tu.logo_url IS NULL OR
    tu.composite_figi IS NULL OR
    tu.type IS NULL
);

\echo '✅ Datos migrados'
\echo ''

-- ===========================================================================
-- 3. ACTUALIZAR VISTA ticker_metadata
-- ===========================================================================
\echo '🔍 Paso 3/4: Actualizando vista ticker_metadata con campos nuevos...'

CREATE OR REPLACE VIEW ticker_metadata AS
SELECT 
    -- Campos básicos
    symbol,
    company_name,
    exchange,
    sector,
    industry,
    
    -- Market data
    market_cap,
    float_shares,
    shares_outstanding,
    avg_volume_30d,
    avg_volume_10d,
    avg_price_30d,
    beta,
    
    -- Información de la compañía
    description,
    homepage_url,
    phone_number,
    address,
    total_employees,
    list_date,
    
    -- Branding
    logo_url,
    icon_url,
    
    -- Identificadores
    cik,
    composite_figi,
    share_class_figi,
    ticker_root,
    ticker_suffix,
    
    -- Detalles del activo
    type,
    currency_name,
    locale,
    market,
    round_lot,
    delisted_utc,
    
    -- Estados
    is_etf,
    is_actively_trading,
    
    -- Timestamps
    updated_at,
    created_at
FROM tickers_unified;

COMMENT ON VIEW ticker_metadata IS 'Vista completa compatible con ticker_metadata antigua - incluye TODOS los campos';

\echo '✅ Vista actualizada'
\echo ''

-- ===========================================================================
-- 4. CREAR ÍNDICES PARA NUEVOS CAMPOS
-- ===========================================================================
\echo '⚡ Paso 4/4: Creando índices para performance...'

CREATE INDEX IF NOT EXISTS idx_tickers_unified_type ON tickers_unified(type);
CREATE INDEX IF NOT EXISTS idx_tickers_unified_cik ON tickers_unified(cik);
CREATE INDEX IF NOT EXISTS idx_tickers_unified_list_date ON tickers_unified(list_date);

\echo '✅ Índices creados'
\echo ''

-- ===========================================================================
-- VERIFICACIÓN
-- ===========================================================================
\echo '🔍 Verificación de datos:'
\echo ''

-- Contar tickers con datos extendidos
SELECT 
    COUNT(*) as total_tickers,
    SUM(CASE WHEN description IS NOT NULL THEN 1 ELSE 0 END) as con_description,
    SUM(CASE WHEN logo_url IS NOT NULL THEN 1 ELSE 0 END) as con_logo,
    SUM(CASE WHEN homepage_url IS NOT NULL THEN 1 ELSE 0 END) as con_homepage,
    SUM(CASE WHEN cik IS NOT NULL THEN 1 ELSE 0 END) as con_cik
FROM tickers_unified;

\echo ''
\echo '📊 Columnas en tickers_unified:'
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tickers_unified' 
AND table_schema = 'public'
ORDER BY ordinal_position;

\echo ''
\echo '✅ FASE 2 PASO 1 COMPLETADO!'
\echo ''
\echo '🎯 Ahora la vista ticker_metadata tiene TODOS los campos necesarios'
\echo '📝 Los microservicios seguirán funcionando sin cambios'
\echo ''

