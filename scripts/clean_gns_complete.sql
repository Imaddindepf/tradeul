-- ===========================================================================
-- CLEAN GNS COMPLETE
-- ===========================================================================
-- Script para limpiar TODOS los datos de GNS de todas las tablas
-- ===========================================================================

BEGIN;

-- 1. Borrar todas las tablas relacionadas con dilution (en orden correcto)
DELETE FROM sec_warrants WHERE ticker = 'GNS';
DELETE FROM sec_atm_offerings WHERE ticker = 'GNS';
DELETE FROM sec_shelf_registrations WHERE ticker = 'GNS';
DELETE FROM sec_completed_offerings WHERE ticker = 'GNS';
DELETE FROM sec_s1_offerings WHERE ticker = 'GNS';
DELETE FROM sec_convertible_notes WHERE ticker = 'GNS';
DELETE FROM sec_convertible_preferred WHERE ticker = 'GNS';
DELETE FROM sec_equity_lines WHERE ticker = 'GNS';
DELETE FROM sec_dilution_profiles WHERE ticker = 'GNS';

-- 2. Borrar financial statements
DELETE FROM financial_statements WHERE ticker = 'GNS';

-- 3. Borrar institutional holders
DELETE FROM institutional_holders WHERE ticker = 'GNS';

-- 4. Verificar
SELECT 'Dilution Profiles' as tabla, COUNT(*) as registros FROM sec_dilution_profiles WHERE ticker = 'GNS'
UNION ALL 
SELECT 'Financial Statements', COUNT(*) FROM financial_statements WHERE ticker = 'GNS'
UNION ALL 
SELECT 'Institutional Holders', COUNT(*) FROM institutional_holders WHERE ticker = 'GNS'
UNION ALL 
SELECT 'Warrants', COUNT(*) FROM sec_warrants WHERE ticker = 'GNS'
UNION ALL 
SELECT 'ATM', COUNT(*) FROM sec_atm_offerings WHERE ticker = 'GNS'
UNION ALL 
SELECT 'Shelfs', COUNT(*) FROM sec_shelf_registrations WHERE ticker = 'GNS'
UNION ALL 
SELECT 'Completed', COUNT(*) FROM sec_completed_offerings WHERE ticker = 'GNS';

COMMIT;

