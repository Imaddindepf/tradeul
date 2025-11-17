-- ===========================================================================
-- SEC DILUTION PROFILES SCHEMA
-- ===========================================================================
-- Tablas para almacenar datos de dilución extraídos de SEC EDGAR filings
-- Incluye: Warrants, ATM Offerings, Shelf Registrations, Completed Offerings
-- ===========================================================================

-- 1. Tabla principal: Dilution Profiles
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_dilution_profiles (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    cik VARCHAR(10),
    company_name VARCHAR(255),
    
    -- Contexto de mercado
    current_price DECIMAL(12,4),
    shares_outstanding BIGINT,
    float_shares BIGINT,
    
    -- Metadata de scraping
    last_scraped_at TIMESTAMP NOT NULL DEFAULT NOW(),
    source_filings JSONB,  -- Array de filings utilizados
    scrape_success BOOLEAN DEFAULT TRUE,
    scrape_error TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(ticker)
);

CREATE INDEX idx_sec_dilution_profiles_ticker ON sec_dilution_profiles(ticker);
CREATE INDEX idx_sec_dilution_profiles_updated_at ON sec_dilution_profiles(updated_at);
CREATE INDEX idx_sec_dilution_profiles_cik ON sec_dilution_profiles(cik);


-- 2. Tabla: Warrants
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_warrants (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Warrant details
    issue_date DATE,
    outstanding BIGINT,  -- Number of warrants outstanding
    exercise_price DECIMAL(12,4),
    expiration_date DATE,
    potential_new_shares BIGINT,  -- Shares if all exercised
    
    -- Additional info
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX idx_sec_warrants_ticker ON sec_warrants(ticker);
CREATE INDEX idx_sec_warrants_expiration ON sec_warrants(expiration_date);


-- 3. Tabla: ATM Offerings
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_atm_offerings (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- ATM details
    total_capacity DECIMAL(15,2),  -- Total capacity in dollars
    remaining_capacity DECIMAL(15,2),  -- Remaining capacity
    placement_agent VARCHAR(255),
    filing_date DATE,
    filing_url TEXT,
    
    -- Calculated fields
    potential_shares_at_current_price BIGINT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX idx_sec_atm_offerings_ticker ON sec_atm_offerings(ticker);
CREATE INDEX idx_sec_atm_offerings_filing_date ON sec_atm_offerings(filing_date);


-- 4. Tabla: Shelf Registrations
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_shelf_registrations (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Shelf details
    total_capacity DECIMAL(15,2),  -- Total shelf capacity in dollars
    remaining_capacity DECIMAL(15,2),  -- Remaining capacity
    is_baby_shelf BOOLEAN DEFAULT FALSE,  -- Is baby shelf (<$75M)?
    filing_date DATE,
    registration_statement VARCHAR(50),  -- e.g., "S-3", "S-1"
    filing_url TEXT,
    expiration_date DATE,  -- Typically 3 years from filing
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX idx_sec_shelf_registrations_ticker ON sec_shelf_registrations(ticker);
CREATE INDEX idx_sec_shelf_registrations_filing_date ON sec_shelf_registrations(filing_date);
CREATE INDEX idx_sec_shelf_registrations_expiration ON sec_shelf_registrations(expiration_date);


-- 5. Tabla: Completed Offerings
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_completed_offerings (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Offering details
    offering_type VARCHAR(50),  -- "Direct Offering", "PIPE", "Registered Direct", etc.
    shares_issued BIGINT,
    price_per_share DECIMAL(12,4),
    amount_raised DECIMAL(15,2),
    offering_date DATE,
    filing_url TEXT,
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX idx_sec_completed_offerings_ticker ON sec_completed_offerings(ticker);
CREATE INDEX idx_sec_completed_offerings_date ON sec_completed_offerings(offering_date);


-- ===========================================================================
-- VIEWS Y FUNCIONES ÚTILES
-- ===========================================================================

-- View: Resumen de dilución potencial por ticker
CREATE OR REPLACE VIEW sec_dilution_summary AS
SELECT 
    p.ticker,
    p.company_name,
    p.shares_outstanding,
    p.current_price,
    p.last_scraped_at,
    
    -- Count de cada tipo
    COUNT(DISTINCT w.id) as warrant_count,
    COUNT(DISTINCT a.id) as atm_count,
    COUNT(DISTINCT s.id) as shelf_count,
    COUNT(DISTINCT co.id) as completed_offering_count,
    
    -- Potential shares from warrants
    COALESCE(SUM(w.potential_new_shares), 0) as total_warrant_shares,
    
    -- Potential capacity from ATM/Shelf
    COALESCE(SUM(a.remaining_capacity), 0) as total_atm_capacity,
    COALESCE(SUM(s.remaining_capacity), 0) as total_shelf_capacity,
    
    -- Total raised from completed offerings
    COALESCE(SUM(co.amount_raised), 0) as total_raised_historical
    
FROM sec_dilution_profiles p
LEFT JOIN sec_warrants w ON p.ticker = w.ticker
LEFT JOIN sec_atm_offerings a ON p.ticker = a.ticker
LEFT JOIN sec_shelf_registrations s ON p.ticker = s.ticker
LEFT JOIN sec_completed_offerings co ON p.ticker = co.ticker
GROUP BY p.ticker, p.company_name, p.shares_outstanding, p.current_price, p.last_scraped_at;


-- Function: Actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers para actualizar updated_at
CREATE TRIGGER update_sec_dilution_profiles_updated_at BEFORE UPDATE ON sec_dilution_profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_warrants_updated_at BEFORE UPDATE ON sec_warrants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_atm_offerings_updated_at BEFORE UPDATE ON sec_atm_offerings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_shelf_registrations_updated_at BEFORE UPDATE ON sec_shelf_registrations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_completed_offerings_updated_at BEFORE UPDATE ON sec_completed_offerings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ===========================================================================
-- COMENTARIOS DE DOCUMENTACIÓN
-- ===========================================================================
COMMENT ON TABLE sec_dilution_profiles IS 'Perfiles principales de dilución extraídos de SEC EDGAR';
COMMENT ON TABLE sec_warrants IS 'Warrants outstanding que pueden causar dilución';
COMMENT ON TABLE sec_atm_offerings IS 'At-The-Market offerings activos';
COMMENT ON TABLE sec_shelf_registrations IS 'Shelf registrations (S-3, S-1) activos';
COMMENT ON TABLE sec_completed_offerings IS 'Offerings completados (histórico)';
COMMENT ON VIEW sec_dilution_summary IS 'Vista resumen de dilución potencial por ticker';

