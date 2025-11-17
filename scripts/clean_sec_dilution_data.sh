#!/bin/bash

# ===========================================================================
# CLEAN SEC DILUTION DATA
# ===========================================================================
# Limpia todos los datos de dilución de Redis y PostgreSQL
# ===========================================================================

set -e

echo "🧹 Limpiando datos de dilución de Redis y PostgreSQL..."
echo ""

# 1. Limpiar Redis
echo "📦 Limpiando Redis..."
docker exec tradeul_redis redis-cli KEYS "sec_dilution:*" | xargs -r docker exec tradeul_redis redis-cli DEL || echo "  ✅ Redis limpio (no hay datos o Redis no está corriendo)"

# 2. Limpiar PostgreSQL
echo "🗄️  Limpiando PostgreSQL..."
docker exec tradeul_timescale psql -U tradeul_user -d tradeul <<EOF
-- Borrar datos secundarios (cascade delete desde profiles)
DELETE FROM sec_warrants;
DELETE FROM sec_atm_offerings;
DELETE FROM sec_shelf_registrations;
DELETE FROM sec_completed_offerings;

-- Borrar nuevos tipos (si existen tablas)
DO \$\$ 
BEGIN
    DELETE FROM sec_s1_offerings;
EXCEPTION WHEN undefined_table THEN NULL;
END \$\$;

DO \$\$ 
BEGIN
    DELETE FROM sec_convertible_notes;
EXCEPTION WHEN undefined_table THEN NULL;
END \$\$;

DO \$\$ 
BEGIN
    DELETE FROM sec_convertible_preferred;
EXCEPTION WHEN undefined_table THEN NULL;
END \$\$;

DO \$\$ 
BEGIN
    DELETE FROM sec_equity_lines;
EXCEPTION WHEN undefined_table THEN NULL;
END \$\$;

-- Borrar profiles principales
DELETE FROM sec_dilution_profiles;

-- Mostrar resumen
SELECT 
    'Warrants' as tabla, COUNT(*) as registros FROM sec_warrants
UNION ALL
SELECT 
    'ATM Offerings', COUNT(*) FROM sec_atm_offerings
UNION ALL
SELECT 
    'Shelf Registrations', COUNT(*) FROM sec_shelf_registrations
UNION ALL
SELECT 
    'Completed Offerings', COUNT(*) FROM sec_completed_offerings
UNION ALL
SELECT 
    'Profiles', COUNT(*) FROM sec_dilution_profiles;
EOF

echo ""
echo "✅ Limpieza completada!"
echo ""
echo "📊 Para verificar:"
echo "   docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c \"SELECT COUNT(*) FROM sec_dilution_profiles;\""
echo "   docker exec tradeul_redis redis-cli KEYS 'sec_dilution:*'"

