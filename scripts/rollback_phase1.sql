-- ===========================================================================
-- ROLLBACK FASE 1: Deshacer Unificación de Tickers
-- ===========================================================================
-- Revierte los cambios de FASE 1 y restaura el estado original
-- ===========================================================================

\echo '⚠️  INICIANDO ROLLBACK FASE 1'
\echo ''

-- 1. Eliminar triggers
\echo '🗑️  Eliminando triggers...'
DROP TRIGGER IF EXISTS trigger_update_tickers_unified_timestamp ON tickers_unified;
DROP FUNCTION IF EXISTS update_tickers_unified_timestamp();

-- 2. Eliminar vistas
\echo '🗑️  Eliminando vistas compatibles...'
DROP VIEW IF EXISTS ticker_metadata CASCADE;
DROP VIEW IF EXISTS ticker_universe CASCADE;

-- 3. Renombrar tablas originales de vuelta (si fueron renombradas)
-- (En FASE 1 NO se renombraron, pero por si acaso)

-- 4. Eliminar tabla unificada
\echo '🗑️  Eliminando tickers_unified...'
DROP TABLE IF EXISTS tickers_unified CASCADE;

\echo ''
\echo '✅ ROLLBACK FASE 1 COMPLETADO'
\echo ''
\echo '⚠️  Las tablas originales ticker_metadata y ticker_universe ahora son TABLAS, no vistas'
\echo '⚠️  Los microservicios seguirán funcionando normalmente'
\echo ''

