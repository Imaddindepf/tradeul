-- Migration: crear tabla cash_history en la DB remota dilutiontracker
-- Ejecutar contra: DB_HOST / dilutiontracker
-- Autor: tradeul | Fecha: 2026-04-09

CREATE TABLE IF NOT EXISTS cash_history (
    ticker                          TEXT        NOT NULL,
    period_date                     DATE        NOT NULL,
    period_label                    TEXT,                           -- "Q1", "Q2", "Q3", "Q4"
    calendar_year                   TEXT,                           -- "2025"
    -- Campo principal (DilutionTracker.com methodology)
    cash_and_short_term_investments BIGINT,                         -- cashAndShortTermInvestments
    -- Fallback puro
    cash_and_cash_equivalents       BIGINT,                         -- cashAndCashEquivalents
    -- Cash flow operativo (para calcular burn rate y runway)
    operating_cf                    BIGINT,                         -- netCashProvidedByOperatingActivities
    -- Metadata
    scraped_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, period_date)
);

CREATE INDEX IF NOT EXISTS idx_cash_history_ticker
    ON cash_history (ticker);

CREATE INDEX IF NOT EXISTS idx_cash_history_scraped_at
    ON cash_history (scraped_at);

-- Vista conveniente: último trimestre por ticker
CREATE OR REPLACE VIEW cash_history_latest AS
SELECT DISTINCT ON (ticker)
    ticker,
    period_date,
    period_label,
    calendar_year,
    COALESCE(cash_and_short_term_investments, cash_and_cash_equivalents) AS cash,
    cash_and_short_term_investments,
    cash_and_cash_equivalents,
    operating_cf,
    scraped_at
FROM cash_history
ORDER BY ticker, period_date DESC;
