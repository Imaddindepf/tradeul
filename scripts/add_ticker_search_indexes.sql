-- =====================================================
-- ÍNDICES OPTIMIZADOS PARA BÚSQUEDA DE TICKERS
-- =====================================================
-- Este script agrega índices para búsqueda ultrarrápida (< 50ms)
-- Uso: psql -U tradeul_user -d tradeul -f add_ticker_search_indexes.sql

-- Habilitar extensión pg_trgm para búsquedas fuzzy
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =====================================================
-- 1. ÍNDICE B-TREE PARA SYMBOL (búsquedas por prefijo)
-- =====================================================
-- Uso: WHERE symbol ILIKE 'AA%' o WHERE symbol = 'AAPL'
-- Performance: O(log n) - búsquedas exactas y por prefijo
CREATE INDEX IF NOT EXISTS idx_tickers_symbol_btree 
ON tickers_unified (symbol);

-- Índice para case-insensitive (ILIKE)
CREATE INDEX IF NOT EXISTS idx_tickers_symbol_lower 
ON tickers_unified (LOWER(symbol) text_pattern_ops);

-- =====================================================
-- 2. ÍNDICE GIN PARA COMPANY_NAME (full-text search)
-- =====================================================
-- Uso: WHERE company_name ILIKE '%Apple%'
-- Performance: Mucho más rápido que LIKE sin índice
CREATE INDEX IF NOT EXISTS idx_tickers_company_name_gin 
ON tickers_unified USING GIN (company_name gin_trgm_ops);

-- Índice adicional para búsquedas por prefijo en company_name
CREATE INDEX IF NOT EXISTS idx_tickers_company_name_lower 
ON tickers_unified (LOWER(company_name) text_pattern_ops);

-- =====================================================
-- 3. ÍNDICE COMPUESTO (is_actively_trading + symbol)
-- =====================================================
-- Uso: WHERE is_actively_trading = true ORDER BY symbol
-- Performance: Evita table scans completos
CREATE INDEX IF NOT EXISTS idx_tickers_active_symbol 
ON tickers_unified (is_actively_trading, symbol) 
WHERE is_actively_trading = true;

-- =====================================================
-- 4. ÍNDICE PARA EXCHANGE (filtros comunes)
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_tickers_exchange 
ON tickers_unified (exchange) 
WHERE exchange IS NOT NULL;

-- =====================================================
-- 5. ACTUALIZAR ESTADÍSTICAS (para query planner)
-- =====================================================
-- Esto ayuda a PostgreSQL a elegir el mejor plan de ejecución
ANALYZE tickers_unified;

-- =====================================================
-- VERIFICAR ÍNDICES CREADOS
-- =====================================================
\echo 'Índices creados para tickers_unified:'
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE tablename = 'tickers_unified' 
ORDER BY indexname;

-- =====================================================
-- ESTADÍSTICAS DE LA TABLA
-- =====================================================
\echo 'Estadísticas de tickers_unified:'
SELECT 
    COUNT(*) as total_rows,
    COUNT(CASE WHEN is_actively_trading = true THEN 1 END) as active_tickers,
    COUNT(DISTINCT exchange) as exchanges,
    pg_size_pretty(pg_total_relation_size('tickers_unified')) as table_size
FROM tickers_unified;

-- =====================================================
-- TEST DE PERFORMANCE (queries comunes)
-- =====================================================
\echo 'Test 1: Búsqueda exacta por symbol'
EXPLAIN ANALYZE 
SELECT symbol, company_name, exchange 
FROM tickers_unified 
WHERE symbol = 'AAPL' AND is_actively_trading = true;

\echo 'Test 2: Búsqueda por prefijo en symbol'
EXPLAIN ANALYZE 
SELECT symbol, company_name, exchange 
FROM tickers_unified 
WHERE symbol ILIKE 'AA%' AND is_actively_trading = true 
ORDER BY symbol 
LIMIT 10;

\echo 'Test 3: Búsqueda en company_name'
EXPLAIN ANALYZE 
SELECT symbol, company_name, exchange 
FROM tickers_unified 
WHERE company_name ILIKE '%Apple%' AND is_actively_trading = true 
ORDER BY symbol 
LIMIT 10;

\echo '✅ Índices creados correctamente!'
\echo 'Las búsquedas de tickers ahora deberían ser < 50ms'

