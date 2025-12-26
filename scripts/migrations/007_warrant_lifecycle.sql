-- ============================================================================
-- Migration 007: Warrant Lifecycle Tracking (v5)
-- ============================================================================
-- Adds comprehensive warrant lifecycle tracking:
-- - Extended warrant fields (type, blocker, proceeds, forced exercise)
-- - Lifecycle events table (exercises, expirations, adjustments)
-- - Price adjustment history table
-- 
-- Run with: psql -h localhost -U postgres -d tradeul -f scripts/migrations/007_warrant_lifecycle.sql
-- ============================================================================

-- ============================================================================
-- 1. ADD NEW COLUMNS TO sec_warrants TABLE
-- ============================================================================

-- Warrant Type Classification
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS warrant_type VARCHAR(50);
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS underlying_type VARCHAR(50) DEFAULT 'shares';

COMMENT ON COLUMN sec_warrants.warrant_type IS 'Type: Common, Pre-Funded, Penny, Placement Agent, Underwriter, SPAC Public, SPAC Private, Inducement';
COMMENT ON COLUMN sec_warrants.underlying_type IS 'Underlying security: shares (default), convertible_notes, preferred_stock';

-- Ownership Blocker
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS ownership_blocker_pct NUMERIC(5,2);
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS blocker_clause TEXT;

COMMENT ON COLUMN sec_warrants.ownership_blocker_pct IS 'Beneficial ownership blocker percentage (e.g., 4.99, 9.99, 19.99)';
COMMENT ON COLUMN sec_warrants.blocker_clause IS 'Full text of ownership blocker clause';

-- Proceeds Tracking
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS potential_proceeds NUMERIC(16,2);
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS actual_proceeds_to_date NUMERIC(16,2);

COMMENT ON COLUMN sec_warrants.potential_proceeds IS 'Total potential proceeds if all warrants exercised (outstanding × exercise_price)';
COMMENT ON COLUMN sec_warrants.actual_proceeds_to_date IS 'Actual proceeds received from warrant exercises to date';

-- Warrant Agreement Reference
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS warrant_agreement_exhibit VARCHAR(50);
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS warrant_agreement_url TEXT;

COMMENT ON COLUMN sec_warrants.warrant_agreement_exhibit IS 'Exhibit number where warrant agreement is filed (e.g., 4.1, 4.2, 10.1)';
COMMENT ON COLUMN sec_warrants.warrant_agreement_url IS 'Direct URL to warrant agreement exhibit';

-- Series Linking (for replacements/amendments)
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS replaced_by_id INTEGER;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS replaces_id INTEGER;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS amendment_of_id INTEGER;

COMMENT ON COLUMN sec_warrants.replaced_by_id IS 'ID of the warrant series that replaced this one';
COMMENT ON COLUMN sec_warrants.replaces_id IS 'ID of the warrant series that this one replaced';
COMMENT ON COLUMN sec_warrants.amendment_of_id IS 'ID of the original warrant if this is an amendment';

-- Alternate Exercise Options
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS has_alternate_cashless BOOLEAN;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS forced_exercise_provision BOOLEAN;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS forced_exercise_price NUMERIC(12,4);
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS forced_exercise_days INTEGER;

COMMENT ON COLUMN sec_warrants.has_alternate_cashless IS 'Has alternate cashless exercise formula (used when no registration)';
COMMENT ON COLUMN sec_warrants.forced_exercise_provision IS 'Has forced exercise if stock trades above threshold';
COMMENT ON COLUMN sec_warrants.forced_exercise_price IS 'Stock price threshold that triggers forced exercise';
COMMENT ON COLUMN sec_warrants.forced_exercise_days IS 'Number of trading days above threshold before forced exercise';

-- Price Adjustment History Reference
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS price_adjustment_count INTEGER DEFAULT 0;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS original_issue_price NUMERIC(12,4);
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS last_price_adjustment_date DATE;

COMMENT ON COLUMN sec_warrants.price_adjustment_count IS 'Number of price adjustments since issuance';
COMMENT ON COLUMN sec_warrants.original_issue_price IS 'Original exercise price at issuance (before any adjustments)';
COMMENT ON COLUMN sec_warrants.last_price_adjustment_date IS 'Date of most recent price adjustment';

-- Lifecycle Events Summary
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS exercise_events_count INTEGER DEFAULT 0;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS last_exercise_date DATE;
ALTER TABLE sec_warrants ADD COLUMN IF NOT EXISTS last_exercise_quantity INTEGER;

COMMENT ON COLUMN sec_warrants.exercise_events_count IS 'Total number of exercise events';
COMMENT ON COLUMN sec_warrants.last_exercise_date IS 'Date of most recent exercise';
COMMENT ON COLUMN sec_warrants.last_exercise_quantity IS 'Quantity exercised in most recent exercise';


-- ============================================================================
-- 2. CREATE WARRANT LIFECYCLE EVENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS sec_warrant_lifecycle_events (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    warrant_id INTEGER REFERENCES sec_warrants(id) ON DELETE CASCADE,
    series_name VARCHAR(255),
    
    -- Event Type
    event_type VARCHAR(50) NOT NULL,
    event_date DATE NOT NULL,
    
    -- For Exercise Events
    warrants_affected INTEGER,
    shares_issued INTEGER,
    proceeds_received NUMERIC(16,2),
    exercise_method VARCHAR(50),
    
    -- For Price Adjustment Events
    old_price NUMERIC(12,4),
    new_price NUMERIC(12,4),
    adjustment_reason VARCHAR(100),
    adjustment_factor NUMERIC(12,6),
    
    -- For Amendment Events
    amendment_description TEXT,
    
    -- Running Totals (after this event)
    outstanding_after INTEGER,
    exercised_cumulative INTEGER,
    expired_cumulative INTEGER,
    
    -- Source
    source_filing VARCHAR(100),
    filing_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT fk_ticker FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_events_ticker ON sec_warrant_lifecycle_events(ticker);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_warrant_id ON sec_warrant_lifecycle_events(warrant_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_date ON sec_warrant_lifecycle_events(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_type ON sec_warrant_lifecycle_events(event_type);

COMMENT ON TABLE sec_warrant_lifecycle_events IS 'Warrant lifecycle events: exercises, price adjustments, expirations, amendments';
COMMENT ON COLUMN sec_warrant_lifecycle_events.event_type IS 'Type: Exercise, Cashless_Exercise, Price_Adjustment, Expiration, Amendment, Redemption, Cancellation, Split_Adjustment';
COMMENT ON COLUMN sec_warrant_lifecycle_events.exercise_method IS 'Cash, Cashless, or Combination';
COMMENT ON COLUMN sec_warrant_lifecycle_events.adjustment_reason IS 'Reason: Stock_Split, Reverse_Split, Reset_Provision, Anti_Dilution, Amendment';


-- ============================================================================
-- 3. CREATE WARRANT PRICE ADJUSTMENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS sec_warrant_price_adjustments (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    warrant_id INTEGER REFERENCES sec_warrants(id) ON DELETE CASCADE,
    series_name VARCHAR(255),
    
    -- Adjustment Details
    adjustment_date DATE NOT NULL,
    adjustment_type VARCHAR(50) NOT NULL,
    
    -- Price Change
    price_before NUMERIC(12,4) NOT NULL,
    price_after NUMERIC(12,4) NOT NULL,
    price_change_pct NUMERIC(8,2),
    
    -- Quantity Change (if applicable)
    quantity_before INTEGER,
    quantity_after INTEGER,
    quantity_multiplier NUMERIC(12,6),
    
    -- Trigger Information
    trigger_event TEXT,
    trigger_price NUMERIC(12,4),
    trigger_filing VARCHAR(100),
    
    -- Source
    source_filing VARCHAR(100),
    filing_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- FK
    CONSTRAINT fk_price_adj_ticker FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_adj_ticker ON sec_warrant_price_adjustments(ticker);
CREATE INDEX IF NOT EXISTS idx_price_adj_warrant_id ON sec_warrant_price_adjustments(warrant_id);
CREATE INDEX IF NOT EXISTS idx_price_adj_date ON sec_warrant_price_adjustments(adjustment_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_adj_type ON sec_warrant_price_adjustments(adjustment_type);

COMMENT ON TABLE sec_warrant_price_adjustments IS 'Warrant price adjustment history: splits, resets, anti-dilution, amendments';
COMMENT ON COLUMN sec_warrant_price_adjustments.adjustment_type IS 'Type: Stock_Split, Reverse_Split, Reset_Provision, Full_Ratchet, Weighted_Average, Amendment, Anti_Dilution';


-- ============================================================================
-- 4. CREATE WARRANT AGREEMENTS CACHE TABLE (optional, for exhibit parsing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sec_warrant_agreements (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    exhibit_number VARCHAR(50),
    filing_date DATE,
    form_type VARCHAR(20),
    exhibit_url TEXT,
    filing_url TEXT,
    description TEXT,
    
    -- Extracted Terms (JSON for flexibility)
    warrant_terms JSONB,
    exercise_provisions JSONB,
    ownership_blocker JSONB,
    anti_dilution JSONB,
    reset_provisions JSONB,
    redemption JSONB,
    adjustment_formula JSONB,
    holder_rights JSONB,
    
    -- Metadata
    extracted_at TIMESTAMP WITH TIME ZONE,
    extraction_model VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- FK
    CONSTRAINT fk_wa_ticker FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_warrant_agreements_ticker ON sec_warrant_agreements(ticker);
CREATE INDEX IF NOT EXISTS idx_warrant_agreements_exhibit ON sec_warrant_agreements(exhibit_number);
CREATE INDEX IF NOT EXISTS idx_warrant_agreements_date ON sec_warrant_agreements(filing_date DESC);

COMMENT ON TABLE sec_warrant_agreements IS 'Cached warrant agreement terms extracted from Exhibit 4.x filings';


-- ============================================================================
-- 5. ADD INDEXES FOR COMMON QUERIES
-- ============================================================================

-- Warrant type queries
CREATE INDEX IF NOT EXISTS idx_warrants_type ON sec_warrants(warrant_type);
CREATE INDEX IF NOT EXISTS idx_warrants_prefunded ON sec_warrants(is_prefunded) WHERE is_prefunded = true;

-- Lifecycle tracking
CREATE INDEX IF NOT EXISTS idx_warrants_exercise_date ON sec_warrants(last_exercise_date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_warrants_price_adj_date ON sec_warrants(last_price_adjustment_date DESC NULLS LAST);


-- ============================================================================
-- 6. GRANT PERMISSIONS
-- ============================================================================

-- Grant permissions if needed (adjust role name)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON sec_warrant_lifecycle_events TO tradeul_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON sec_warrant_price_adjustments TO tradeul_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON sec_warrant_agreements TO tradeul_app;
-- GRANT USAGE, SELECT ON SEQUENCE sec_warrant_lifecycle_events_id_seq TO tradeul_app;
-- GRANT USAGE, SELECT ON SEQUENCE sec_warrant_price_adjustments_id_seq TO tradeul_app;
-- GRANT USAGE, SELECT ON SEQUENCE sec_warrant_agreements_id_seq TO tradeul_app;


-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
SELECT 'Migration 007_warrant_lifecycle completed successfully' AS status;

