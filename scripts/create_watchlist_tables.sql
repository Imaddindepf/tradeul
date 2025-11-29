-- ============================================================================
-- Watchlist Tables for Quote Monitor
-- Run this script to create the necessary tables
-- ============================================================================

-- Watchlists table (tabs in Quote Monitor)
CREATE TABLE IF NOT EXISTS watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,  -- Clerk user ID
    name VARCHAR(100) NOT NULL,
    description TEXT,
    color VARCHAR(20),  -- Hex color for tab
    icon VARCHAR(50),   -- Icon name
    is_synthetic_etf BOOLEAN DEFAULT FALSE,
    columns JSONB DEFAULT '["ticker", "last", "bid", "ask", "change_percent", "volume", "latency"]'::jsonb,
    sort_by VARCHAR(50),
    sort_order VARCHAR(4) DEFAULT 'asc',
    position INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast user lookups
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_user_position ON watchlists(user_id, position);

-- Watchlist tickers table (tickers in each watchlist)
CREATE TABLE IF NOT EXISTS watchlist_tickers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10) DEFAULT 'US',
    notes TEXT,
    alert_price_above DECIMAL(20, 4),
    alert_price_below DECIMAL(20, 4),
    alert_change_percent DECIMAL(10, 4),
    position_size DECIMAL(20, 4),  -- For tracking positions
    weight DECIMAL(10, 4),  -- Weight in synthetic ETF (0-100)
    tags JSONB DEFAULT '[]'::jsonb,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint: no duplicate tickers in same watchlist
    UNIQUE(watchlist_id, symbol)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_watchlist_id ON watchlist_tickers(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_symbol ON watchlist_tickers(symbol);

-- User settings for Quote Monitor
CREATE TABLE IF NOT EXISTS quote_monitor_settings (
    user_id VARCHAR(255) PRIMARY KEY,
    active_watchlist_id UUID REFERENCES watchlists(id) ON DELETE SET NULL,
    settings JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for auto-updating updated_at
DROP TRIGGER IF EXISTS update_watchlists_updated_at ON watchlists;
CREATE TRIGGER update_watchlists_updated_at
    BEFORE UPDATE ON watchlists
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_quote_monitor_settings_updated_at ON quote_monitor_settings;
CREATE TRIGGER update_quote_monitor_settings_updated_at
    BEFORE UPDATE ON quote_monitor_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Sample data for testing (optional - comment out in production)
-- ============================================================================

-- INSERT INTO watchlists (user_id, name, color, position) VALUES
--     ('test_user_1', 'Tech Stocks', '#3B82F6', 0),
--     ('test_user_1', 'My ETF', '#10B981', 1),
--     ('test_user_1', 'Earnings Watch', '#F59E0B', 2);

COMMENT ON TABLE watchlists IS 'User-created watchlists for Quote Monitor';
COMMENT ON TABLE watchlist_tickers IS 'Tickers within each watchlist';
COMMENT ON TABLE quote_monitor_settings IS 'User preferences for Quote Monitor';

