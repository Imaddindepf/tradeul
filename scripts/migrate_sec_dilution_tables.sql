-- ===========================================================================
-- SEC DILUTION TABLES MIGRATION
-- ===========================================================================
-- Actualiza tablas existentes y crea nuevas tablas para tipos adicionales
-- Ejecutar después de init_sec_dilution_profiles.sql
-- ===========================================================================

-- 1. ACTUALIZAR TABLA: sec_atm_offerings
-- ===========================================================================
-- Agregar columnas nuevas: status, agreement_start_date, notes
DO $$ 
BEGIN
    -- Agregar status si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_atm_offerings' AND column_name = 'status'
    ) THEN
        ALTER TABLE sec_atm_offerings ADD COLUMN status VARCHAR(50);
    END IF;
    
    -- Agregar agreement_start_date si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_atm_offerings' AND column_name = 'agreement_start_date'
    ) THEN
        ALTER TABLE sec_atm_offerings ADD COLUMN agreement_start_date DATE;
    END IF;
    
    -- Agregar notes si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_atm_offerings' AND column_name = 'notes'
    ) THEN
        ALTER TABLE sec_atm_offerings ADD COLUMN notes TEXT;
    END IF;
END $$;

-- 2. ACTUALIZAR TABLA: sec_shelf_registrations
-- ===========================================================================
-- Agregar columnas nuevas: security_type, amounts raised, baby shelf restriction, etc.
DO $$ 
BEGIN
    -- Agregar security_type si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'security_type'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN security_type VARCHAR(50);
    END IF;
    
    -- Agregar current_raisable_amount si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'current_raisable_amount'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN current_raisable_amount DECIMAL(15,2);
    END IF;
    
    -- Agregar total_amount_raised si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'total_amount_raised'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN total_amount_raised DECIMAL(15,2);
    END IF;
    
    -- Agregar total_amount_raised_last_12mo si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'total_amount_raised_last_12mo'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN total_amount_raised_last_12mo DECIMAL(15,2);
    END IF;
    
    -- Agregar baby_shelf_restriction si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'baby_shelf_restriction'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN baby_shelf_restriction BOOLEAN;
    END IF;
    
    -- Agregar effect_date si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'effect_date'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN effect_date DATE;
    END IF;
    
    -- Agregar last_banker si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'last_banker'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN last_banker VARCHAR(255);
    END IF;
    
    -- Agregar notes si no existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sec_shelf_registrations' AND column_name = 'notes'
    ) THEN
        ALTER TABLE sec_shelf_registrations ADD COLUMN notes TEXT;
    END IF;
END $$;

-- 3. CREAR TABLA: sec_s1_offerings
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_s1_offerings (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- S-1 Offering details
    anticipated_deal_size DECIMAL(15,2),
    final_deal_size DECIMAL(15,2),
    final_pricing DECIMAL(12,4),
    final_shares_offered BIGINT,
    warrant_coverage DECIMAL(5,2),  -- Percentage
    final_warrant_coverage DECIMAL(5,2),  -- Final percentage
    exercise_price DECIMAL(12,4),
    underwriter_agent VARCHAR(255),
    s1_filing_date DATE,
    status VARCHAR(50),  -- "Priced", "Registered", "Pending"
    filing_url TEXT,
    last_update_date DATE,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sec_s1_offerings_ticker ON sec_s1_offerings(ticker);
CREATE INDEX IF NOT EXISTS idx_sec_s1_offerings_filing_date ON sec_s1_offerings(s1_filing_date);

-- 4. CREAR TABLA: sec_convertible_notes
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_convertible_notes (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Convertible Note details
    total_principal_amount DECIMAL(15,2),
    remaining_principal_amount DECIMAL(15,2),
    conversion_price DECIMAL(12,4),
    total_shares_when_converted BIGINT,
    remaining_shares_when_converted BIGINT,
    issue_date DATE,
    convertible_date DATE,
    maturity_date DATE,
    underwriter_agent VARCHAR(255),
    filing_url TEXT,
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sec_convertible_notes_ticker ON sec_convertible_notes(ticker);
CREATE INDEX IF NOT EXISTS idx_sec_convertible_notes_maturity ON sec_convertible_notes(maturity_date);

-- 5. CREAR TABLA: sec_convertible_preferred
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_convertible_preferred (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Convertible Preferred details
    series VARCHAR(50),  -- "Series A", "Series B", etc.
    total_dollar_amount_issued DECIMAL(15,2),
    remaining_dollar_amount DECIMAL(15,2),
    conversion_price DECIMAL(12,4),
    total_shares_when_converted BIGINT,
    remaining_shares_when_converted BIGINT,
    issue_date DATE,
    convertible_date DATE,
    maturity_date DATE,
    underwriter_agent VARCHAR(255),
    filing_url TEXT,
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sec_convertible_preferred_ticker ON sec_convertible_preferred(ticker);
CREATE INDEX IF NOT EXISTS idx_sec_convertible_preferred_series ON sec_convertible_preferred(series);

-- 6. CREAR TABLA: sec_equity_lines
-- ===========================================================================
CREATE TABLE IF NOT EXISTS sec_equity_lines (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Equity Line details
    total_capacity DECIMAL(15,2),
    remaining_capacity DECIMAL(15,2),
    agreement_start_date DATE,
    agreement_end_date DATE,
    filing_url TEXT,
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sec_equity_lines_ticker ON sec_equity_lines(ticker);
CREATE INDEX IF NOT EXISTS idx_sec_equity_lines_start_date ON sec_equity_lines(agreement_start_date);

-- 7. TRIGGERS PARA NUEVAS TABLAS
-- ===========================================================================
CREATE TRIGGER update_sec_s1_offerings_updated_at BEFORE UPDATE ON sec_s1_offerings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_convertible_notes_updated_at BEFORE UPDATE ON sec_convertible_notes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_convertible_preferred_updated_at BEFORE UPDATE ON sec_convertible_preferred FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sec_equity_lines_updated_at BEFORE UPDATE ON sec_equity_lines FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 8. COMENTARIOS DE DOCUMENTACIÓN
-- ===========================================================================
COMMENT ON TABLE sec_s1_offerings IS 'S-1 offerings con detalles de pricing y warrant coverage';
COMMENT ON TABLE sec_convertible_notes IS 'Convertible notes/debt que pueden convertirse en acciones comunes';
COMMENT ON TABLE sec_convertible_preferred IS 'Convertible preferred stock que puede convertirse en acciones comunes';
COMMENT ON TABLE sec_equity_lines IS 'Equity Lines of Credit (ELOC) activos';

