# 🛡️ INSTRUCCIONES DE RESTAURACIÓN DE BACKUP

## 📦 Backups Creados

- **Fecha:** 2025-11-23 18:14:36
- **Formato Custom (70MB):** `tradeul_backup_20251123_181436.backup`
- **Formato SQL (311MB):** `tradeul_backup_20251123_181456.sql`

---

## 🔄 OPCIÓN 1: Restaurar desde Backup Custom (RECOMENDADO)

```bash
# 1. Parar todos los servicios
cd /opt/tradeul
docker-compose down

# 2. Levantar solo la base de datos
docker-compose up -d timescaledb
sleep 10

# 3. Restaurar desde backup custom
docker exec -i tradeul_timescale pg_restore \
  -U tradeul_user \
  -d tradeul \
  --clean \
  --if-exists \
  --disable-triggers \
  < backups/tradeul_backup_20251123_181436.backup

# 4. Verificar restauración
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "\dt"

# 5. Levantar todos los servicios
docker-compose up -d
```

---

## 🔄 OPCIÓN 2: Restaurar desde SQL

```bash
# 1. Parar todos los servicios
cd /opt/tradeul
docker-compose down

# 2. Levantar solo la base de datos
docker-compose up -d timescaledb
sleep 10

# 3. Borrar BD y recrear (CUIDADO!)
docker exec tradeul_timescale psql -U postgres -c "DROP DATABASE IF EXISTS tradeul;"
docker exec tradeul_timescale psql -U postgres -c "CREATE DATABASE tradeul OWNER tradeul_user;"

# 4. Restaurar desde SQL
docker exec -i tradeul_timescale psql -U tradeul_user -d tradeul < backups/tradeul_backup_20251123_181456.sql

# 5. Verificar restauración
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "\dt"

# 6. Levantar todos los servicios
docker-compose up -d
```

---

## 🔍 Verificar que TODO está bien

```bash
# Contar tablas
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "\dt" | wc -l

# Ver tamaño de la BD
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "
SELECT pg_size_pretty(pg_database_size('tradeul')) as size;
"

# Verificar tablas principales
docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "
SELECT 
  'ticker_metadata' as table, COUNT(*) as rows FROM ticker_metadata
UNION ALL
SELECT 
  'ticker_universe' as table, COUNT(*) as rows FROM ticker_universe
UNION ALL
SELECT 
  'sec_dilution_profiles' as table, COUNT(*) as rows FROM sec_dilution_profiles
UNION ALL
SELECT 
  'financial_statements' as table, COUNT(*) as rows FROM financial_statements;
"
```

---

## ⚠️ NOTAS IMPORTANTES

- Los warnings sobre "circular foreign-key constraints" son normales en TimescaleDB
- Si ves errores al restaurar, usa `--disable-triggers` como se muestra arriba
- El backup custom es más eficiente y rápido de restaurar
- El backup SQL es más fácil de editar si necesitas hacer cambios selectivos
- Siempre verifica que los servicios se levanten correctamente después de restaurar

---

##  Estado Pre-Migración

**Tablas actuales:**
- Scanner/Market: 9 tablas
- Dilution Tracker: 14 tablas
- Total: 23 tablas

**Problemas identificados:**
- 3 tablas maestras de tickers (ticker_metadata, ticker_universe, sec_dilution_profiles)
- Foreign keys faltantes entre áreas
- Duplicación de datos (shares_outstanding, market_cap, float_shares)

---

## 🎯 Siguientes Pasos

1. ✅ Backup creado
2. ⏭️ Crear `tickers_unified` con vistas compatibles (FASE 1)
3. ⏭️ Adaptar microservicios uno por uno (FASE 2)
4. ⏭️ Deprecar tablas viejas (FASE 3)

