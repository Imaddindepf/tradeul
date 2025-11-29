-- ============================================================================
-- Add Watchlist Sections Support
-- ============================================================================

-- Create sections table
CREATE TABLE IF NOT EXISTS watchlist_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT,
    icon TEXT,
    is_collapsed BOOLEAN DEFAULT FALSE,
    position INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_watchlist_sections_watchlist_id 
    ON watchlist_sections(watchlist_id);

-- Add section_id to tickers (NULL = unsorted/no section)
ALTER TABLE watchlist_tickers 
    ADD COLUMN IF NOT EXISTS section_id UUID REFERENCES watchlist_sections(id) ON DELETE SET NULL;

-- Add position column to tickers for ordering within sections
ALTER TABLE watchlist_tickers 
    ADD COLUMN IF NOT EXISTS position INTEGER DEFAULT 0;

-- Index for section lookups
CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_section_id 
    ON watchlist_tickers(section_id);

-- Apply trigger for updated_at on sections
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_watchlist_sections_updated_at') THEN
        CREATE TRIGGER update_watchlist_sections_updated_at
        BEFORE UPDATE ON watchlist_sections
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ============================================================================
-- Verify changes
-- ============================================================================
SELECT 
    table_name, 
    column_name, 
    data_type 
FROM information_schema.columns 
WHERE table_name IN ('watchlist_sections', 'watchlist_tickers')
ORDER BY table_name, ordinal_position;

