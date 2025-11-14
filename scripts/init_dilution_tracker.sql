-- =============================================
-- DILUTION TRACKER - DATABASE SCHEMA
-- =============================================
-- Script para crear las tablas necesarias para Dilution Tracker
-- Reutiliza ticker_metadata existente para market_cap, float, shares_outstanding
-- Solo agrega datos específicos de dilution tracking

-- =============================================
-- TABLA 1: FINANCIAL STATEMENTS (Balance + Income + Cash Flow)
-- =============================================

CREATE TABLE IF NOT EXISTS financial_statements (
    ticker VARCHAR(10) NOT NULL,
    period_date DATE NOT NULL,
    period_type VARCHAR(10) NOT NULL,  -- 'Q1', 'Q2', 'Q3', 'Q4', 'FY'
    fiscal_year INT,
    
    -- Balance Sheet (solo campos esenciales)
    total_assets NUMERIC(20, 2),
    total_liabilities NUMERIC(20, 2),
    stockholders_equity NUMERIC(20, 2),
    cash_and_equivalents NUMERIC(20, 2),
    short_term_investments NUMERIC(20, 2),
    total_debt NUMERIC(20, 2),
    total_current_assets NUMERIC(20, 2),
    total_current_liabilities NUMERIC(20, 2),
    
    -- Income Statement (solo campos esenciales)
    revenue NUMERIC(20, 2),
    gross_profit NUMERIC(20, 2),
    operating_income NUMERIC(20, 2),
    net_income NUMERIC(20, 2),
    eps_basic NUMERIC(10, 4),
    eps_diluted NUMERIC(10, 4),
    
    -- Cash Flow (solo campos esenciales)
    operating_cash_flow NUMERIC(20, 2),
    investing_cash_flow NUMERIC(20, 2),
    financing_cash_flow NUMERIC(20, 2),
    free_cash_flow NUMERIC(20, 2),
    
    -- Shares (crítico para dilución)
    shares_outstanding BIGINT,
    weighted_avg_shares_basic BIGINT,
    weighted_avg_shares_diluted BIGINT,
    
    -- Metadata
    source VARCHAR(10) DEFAULT 'fmp',  -- 'polygon' o 'fmp'
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (ticker, period_date, period_type)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_financials_ticker_period ON financial_statements(ticker, period_date DESC);
CREATE INDEX IF NOT EXISTS idx_financials_ticker_year ON financial_statements(ticker, fiscal_year DESC);
CREATE INDEX IF NOT EXISTS idx_financials_fetched ON financial_statements(fetched_at DESC);

-- Comentarios
COMMENT ON TABLE financial_statements IS 'Estados financieros históricos (Balance Sheet + Income Statement + Cash Flow)';
COMMENT ON COLUMN financial_statements.free_cash_flow IS 'Operating Cash Flow - CapEx';
COMMENT ON COLUMN financial_statements.weighted_avg_shares_diluted IS 'Usado para calcular dilución histórica';


-- =============================================
-- TABLA 2: INSTITUTIONAL HOLDERS (13F filings)
-- =============================================

CREATE TABLE IF NOT EXISTS institutional_holders (
    ticker VARCHAR(10) NOT NULL,
    holder_name VARCHAR(300) NOT NULL,
    report_date DATE NOT NULL,
    
    -- Position data
    shares_held BIGINT,
    position_value NUMERIC(20, 2),
    ownership_percent NUMERIC(5, 2),
    
    -- Change vs previous report
    position_change BIGINT,
    position_change_percent NUMERIC(10, 2),
    
    -- Filing info
    filing_date DATE,
    form_type VARCHAR(10) DEFAULT '13F',  -- '13F-HR', '13D', '13G', etc.
    
    -- Metadata
    cik VARCHAR(20),
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (ticker, holder_name, report_date)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_holders_ticker_date ON institutional_holders(ticker, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_holders_ticker_ownership ON institutional_holders(ticker, ownership_percent DESC);
CREATE INDEX IF NOT EXISTS idx_holders_date ON institutional_holders(report_date DESC);

-- Comentarios
COMMENT ON TABLE institutional_holders IS 'Holders institucionales de 13F filings';
COMMENT ON COLUMN institutional_holders.position_change IS 'Cambio en shares vs reporte anterior';


-- =============================================
-- TABLA 3: SEC FILINGS
-- =============================================

CREATE TABLE IF NOT EXISTS sec_filings (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    filing_type VARCHAR(20) NOT NULL,  -- '10-K', '10-Q', '8-K', 'S-3', '424B5', 'SC 13D/A', etc.
    filing_date DATE NOT NULL,
    report_date DATE,
    
    accession_number VARCHAR(50) UNIQUE NOT NULL,
    
    title TEXT,
    description TEXT,
    url TEXT,
    
    -- Clasificación para filtrado
    category VARCHAR(30),  -- 'financial', 'offering', 'ownership', 'proxy', 'other'
    is_offering_related BOOLEAN DEFAULT FALSE,
    is_dilutive BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(ticker, accession_number)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_filings_ticker_date ON sec_filings(ticker, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_filings_type ON sec_filings(filing_type, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_filings_category ON sec_filings(category, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_filings_offering ON sec_filings(ticker, filing_date DESC) WHERE is_offering_related = TRUE;
CREATE INDEX IF NOT EXISTS idx_filings_dilutive ON sec_filings(ticker, filing_date DESC) WHERE is_dilutive = TRUE;

-- Comentarios
COMMENT ON TABLE sec_filings IS 'SEC filings relevantes para análisis de dilución';
COMMENT ON COLUMN sec_filings.category IS 'financial|offering|ownership|proxy|other';
COMMENT ON COLUMN sec_filings.is_dilutive IS 'TRUE si el filing indica dilución potencial (S-3, 424B5, etc)';


-- =============================================
-- TABLA 4: DILUTION METRICS (Métricas calculadas)
-- =============================================

CREATE TABLE IF NOT EXISTS dilution_metrics (
    ticker VARCHAR(10) NOT NULL,
    calculated_at DATE NOT NULL,
    
    -- Cash Runway Analysis
    current_cash NUMERIC(20, 2),
    quarterly_burn_rate NUMERIC(20, 2),
    estimated_runway_months NUMERIC(10, 2),
    
    -- Dilution Analysis
    shares_outstanding_current BIGINT,
    shares_outstanding_1y_ago BIGINT,
    shares_outstanding_2y_ago BIGINT,
    dilution_pct_1y NUMERIC(10, 2),  -- % incremento en 1 año
    dilution_pct_2y NUMERIC(10, 2),  -- % incremento en 2 años
    
    -- Financial Health
    debt_to_equity NUMERIC(10, 4),
    current_ratio NUMERIC(10, 4),
    working_capital NUMERIC(20, 2),
    
    -- Risk Scores (0-100, donde 100 = alto riesgo)
    overall_risk_score INT,
    cash_need_score INT,
    dilution_risk_score INT,
    
    -- Metadata
    data_quality_score NUMERIC(3, 2),  -- 0.0 - 1.0 (calidad de datos usados para cálculo)
    last_financial_date DATE,  -- Fecha del último financial usado
    
    PRIMARY KEY (ticker, calculated_at)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_dilution_ticker ON dilution_metrics(ticker, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dilution_risk ON dilution_metrics(overall_risk_score DESC, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dilution_calculated ON dilution_metrics(calculated_at DESC);

-- Comentarios
COMMENT ON TABLE dilution_metrics IS 'Métricas de dilución calculadas periódicamente';
COMMENT ON COLUMN dilution_metrics.quarterly_burn_rate IS 'Promedio de operating cash flow de últimos 4 quarters (negativo = quemando cash)';
COMMENT ON COLUMN dilution_metrics.overall_risk_score IS '0-100 donde 100 = máximo riesgo de dilución';


-- =============================================
-- TABLA 5: TICKER SYNC CONFIG (Estrategia Tiered)
-- =============================================

CREATE TABLE IF NOT EXISTS ticker_sync_config (
    ticker VARCHAR(10) PRIMARY KEY,
    
    -- Tier configuration (1=high priority, 2=medium, 3=low/on-demand)
    tier INT DEFAULT 3 CHECK (tier IN (1, 2, 3)),
    sync_frequency VARCHAR(20) DEFAULT 'on-demand',  -- 'daily', 'weekly', 'on-demand'
    
    -- Sync tracking
    last_synced_at TIMESTAMPTZ,
    sync_count INT DEFAULT 0,
    failed_sync_count INT DEFAULT 0,
    last_error TEXT,
    
    -- Popularity tracking
    search_count_7d INT DEFAULT 0,
    search_count_30d INT DEFAULT 0,
    last_searched_at TIMESTAMPTZ,
    
    -- Priority calculation
    priority_score NUMERIC(10, 2) DEFAULT 0,
    
    -- Auto-promotion/demotion
    promoted_at TIMESTAMPTZ,
    demoted_at TIMESTAMPTZ,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_sync_config_tier ON ticker_sync_config(tier, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_sync_config_sync_freq ON ticker_sync_config(sync_frequency);
CREATE INDEX IF NOT EXISTS idx_sync_config_last_synced ON ticker_sync_config(last_synced_at);
CREATE INDEX IF NOT EXISTS idx_sync_config_search_count ON ticker_sync_config(search_count_30d DESC);

-- Comentarios
COMMENT ON TABLE ticker_sync_config IS 'Configuración de estrategia de sincronización por ticker';
COMMENT ON COLUMN ticker_sync_config.tier IS '1=Top 500 (daily), 2=Mid 2000 (weekly), 3=Long tail (on-demand)';
COMMENT ON COLUMN ticker_sync_config.priority_score IS 'Score calculado basado en market_cap, volume, searches';


-- =============================================
-- TABLA 6: DILUTION SEARCHES (Tracking de búsquedas)
-- =============================================

CREATE TABLE IF NOT EXISTS dilution_searches (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    user_id UUID,  -- Opcional, si tienes sistema de usuarios
    session_id VARCHAR(100),  -- Para tracking sin login
    searched_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_searches_ticker ON dilution_searches(ticker, searched_at DESC);
CREATE INDEX IF NOT EXISTS idx_searches_date ON dilution_searches(searched_at DESC);
CREATE INDEX IF NOT EXISTS idx_searches_ticker_recent ON dilution_searches(ticker) WHERE searched_at > NOW() - INTERVAL '30 days';

-- Comentarios
COMMENT ON TABLE dilution_searches IS 'Tracking de búsquedas para optimizar sincronización';


-- =============================================
-- VISTAS ÚTILES
-- =============================================

-- Vista: Últimos financials por ticker
CREATE OR REPLACE VIEW latest_financials AS
SELECT DISTINCT ON (ticker)
    ticker,
    period_date,
    period_type,
    fiscal_year,
    cash_and_equivalents,
    total_debt,
    revenue,
    net_income,
    operating_cash_flow,
    free_cash_flow,
    shares_outstanding,
    fetched_at
FROM financial_statements
ORDER BY ticker, period_date DESC, fetched_at DESC;

COMMENT ON VIEW latest_financials IS 'Último financial statement por ticker';


-- Vista: Top institutional holders por ticker
CREATE OR REPLACE VIEW top_institutional_holders AS
SELECT 
    ticker,
    holder_name,
    shares_held,
    ownership_percent,
    position_change,
    report_date
FROM (
    SELECT 
        ticker,
        holder_name,
        shares_held,
        ownership_percent,
        position_change,
        report_date,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ownership_percent DESC) as rn
    FROM institutional_holders
    WHERE report_date = (
        SELECT MAX(report_date) 
        FROM institutional_holders ih2 
        WHERE ih2.ticker = institutional_holders.ticker
    )
) ranked
WHERE rn <= 20;  -- Top 20 holders

COMMENT ON VIEW top_institutional_holders IS 'Top 20 institutional holders por ticker (último reporte)';


-- Vista: Tickers con high dilution risk
CREATE OR REPLACE VIEW high_dilution_risk_tickers AS
SELECT 
    dm.ticker,
    dm.overall_risk_score,
    dm.estimated_runway_months,
    dm.dilution_pct_1y,
    dm.calculated_at,
    tm.market_cap,
    tm.float_shares,
    tm.sector
FROM dilution_metrics dm
LEFT JOIN ticker_metadata tm ON dm.ticker = tm.symbol
WHERE dm.overall_risk_score >= 70
AND dm.calculated_at = (
    SELECT MAX(calculated_at) 
    FROM dilution_metrics dm2 
    WHERE dm2.ticker = dm.ticker
)
ORDER BY dm.overall_risk_score DESC;

COMMENT ON VIEW high_dilution_risk_tickers IS 'Tickers con alto riesgo de dilución (score >= 70)';


-- =============================================
-- FUNCIONES ÚTILES
-- =============================================

-- Función: Actualizar contadores de búsqueda
CREATE OR REPLACE FUNCTION update_search_counters()
RETURNS TRIGGER AS $$
BEGIN
    -- Actualizar contadores en ticker_sync_config
    INSERT INTO ticker_sync_config (
        ticker,
        search_count_7d,
        search_count_30d,
        last_searched_at,
        updated_at
    )
    VALUES (
        NEW.ticker,
        1,
        1,
        NEW.searched_at,
        NOW()
    )
    ON CONFLICT (ticker) DO UPDATE SET
        search_count_7d = (
            SELECT COUNT(*) 
            FROM dilution_searches 
            WHERE ticker = NEW.ticker 
            AND searched_at > NOW() - INTERVAL '7 days'
        ),
        search_count_30d = (
            SELECT COUNT(*) 
            FROM dilution_searches 
            WHERE ticker = NEW.ticker 
            AND searched_at > NOW() - INTERVAL '30 days'
        ),
        last_searched_at = NEW.searched_at,
        updated_at = NOW();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para actualizar contadores automáticamente
DROP TRIGGER IF EXISTS trigger_update_search_counters ON dilution_searches;
CREATE TRIGGER trigger_update_search_counters
    AFTER INSERT ON dilution_searches
    FOR EACH ROW
    EXECUTE FUNCTION update_search_counters();


-- Función: Auto-actualizar tiers basado en popularidad
CREATE OR REPLACE FUNCTION auto_update_tiers()
RETURNS void AS $$
BEGIN
    -- Promover tickers con muchas búsquedas a Tier 1
    UPDATE ticker_sync_config
    SET 
        tier = 1,
        sync_frequency = 'daily',
        promoted_at = NOW(),
        updated_at = NOW()
    WHERE search_count_30d >= 20
    AND tier > 1;
    
    -- Promover tickers con búsquedas moderadas a Tier 2
    UPDATE ticker_sync_config
    SET 
        tier = 2,
        sync_frequency = 'weekly',
        promoted_at = NOW(),
        updated_at = NOW()
    WHERE search_count_30d >= 5
    AND search_count_30d < 20
    AND tier > 2;
    
    -- Degradar tickers sin búsquedas recientes
    UPDATE ticker_sync_config
    SET 
        tier = 3,
        sync_frequency = 'on-demand',
        demoted_at = NOW(),
        updated_at = NOW()
    WHERE search_count_30d = 0
    AND tier < 3
    AND last_synced_at < NOW() - INTERVAL '60 days';
    
    RAISE NOTICE 'Tiers updated successfully';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION auto_update_tiers IS 'Ejecutar semanalmente para rebalancear tiers automáticamente';


-- =============================================
-- GRANTS (Ajustar según tu configuración)
-- =============================================

-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;


-- =============================================
-- FIN DEL SCRIPT
-- =============================================

-- Para ejecutar este script:
-- psql -h localhost -U postgres -d tradeul -f init_dilution_tracker.sql

\echo '✅ Dilution Tracker database schema created successfully!'
\echo '📊 Tables created: 6'
\echo '📈 Views created: 3'
\echo '⚙️  Functions created: 2'
\echo '🔔 Triggers created: 1'

