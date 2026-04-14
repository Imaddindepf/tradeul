#  ANÁLISIS COMPLETO DE TABLAS DE LA BASE DE DATOS

**Fecha:** 2025-11-23  
**Total de tablas:** 22  
**Tamaño total:** ~1.06 GB

---

## 🟢 **TABLAS EN USO ACTIVO (18 tablas)**

### **Grupo 1: Scanner / Market Data (7 tablas) - 1.06 GB**

| Tabla | Tamaño | Registros | Uso | Servicios |
|-------|--------|-----------|-----|-----------|
| `volume_slots` | **1044 MB** | ~millones | ✅ ACTIVO | analytics, data_maintenance, scanner |
| `ticker_metadata` | **13 MB** | 12,147 | ✅ ACTIVO | ALL (usado por todos los servicios) |
| `ticker_universe` | **3.6 MB** | 12,031 | ✅ ACTIVO | historical, data_maintenance |
| `market_data_daily` | 32 KB | 343,796 | ✅ ACTIVO | data_maintenance, historical |
| `market_sessions_log` | 24 KB | ? | ✅ ACTIVO | market_session |
| `market_holidays` | 16 KB | ? | ✅ ACTIVO | market_session |
| `scanner_filters` | 96 KB | ? | ✅ ACTIVO | scanner |

**Notas:**
- `volume_slots` es la tabla más pesada (1GB) - almacena histórico de volumen por slots de 5 min
- `ticker_metadata` y `ticker_universe` tienen DUPLICACIÓN - candidatas para unificar

---

### **Grupo 2: Dilution Tracker - Financial (4 tablas) - 6.6 MB**

| Tabla | Tamaño | Registros | Uso | Servicios |
|-------|--------|-----------|-----|-----------|
| `financial_statements` | 176 KB | 354 | ✅ ACTIVO | dilution-tracker (fmp_financials) |
| `institutional_holders` | 3 MB | ? | ✅ ACTIVO | dilution-tracker (fmp_holders) |
| `sec_filings` | 360 KB | ? | ✅ ACTIVO | dilution-tracker (fmp_filings) |
| `ticker_sync_config` | 8 KB | ? | ✅ ACTIVO | dilution-tracker (tier_manager) |

---

### **Grupo 3: Dilution Tracker - SEC Profiles (7 tablas) - 304 KB**

| Tabla | Tamaño | Registros | Uso | Repository |
|-------|--------|-----------|-----|------------|
| `sec_dilution_profiles` | 120 KB | 5 | ✅ ACTIVO | sec_dilution_repository |
| `sec_warrants` | 56 KB | ? | ✅ ACTIVO | sec_dilution_repository |
| `sec_completed_offerings` | 48 KB | ? | ✅ ACTIVO | sec_dilution_repository |
| `sec_equity_lines` | 16 KB | ? | ✅ ACTIVO | sec_dilution_repository |
| `sec_atm_offerings` | 16 KB | ? | ✅ ACTIVO | sec_dilution_repository |
| `sec_convertible_notes` | 16 KB | ? | ✅ ACTIVO | sec_dilution_repository |
| `sec_shelf_registrations` | 16 KB | ? | ✅ ACTIVO | sec_dilution_repository |

**Nota:** Estas tablas están vacías o con muy pocos datos (solo 5 perfiles). El sistema está listo pero no se ha poblado.

---

## 🟡 **TABLAS CON POCO USO (2 tablas) - 8 KB**

| Tabla | Tamaño | Registros | Uso | Estado |
|-------|--------|-----------|-----|--------|
| `dilution_searches` | 8 KB | ? | 🟡 TRACKING | search_tracker |
| `sec_s1_offerings` | 16 KB | ? | 🟡 CREADA | sec_dilution_repository |
| `sec_convertible_preferred` | 16 KB | ? | 🟡 CREADA | sec_dilution_repository |

**Nota:** Estas tablas están creadas pero con muy poco o nada de datos. Son parte del sistema de Dilution Tracker que aún no se usa completamente.

---

## 🔴 **TABLAS VACÍAS O SIN USO (2 tablas) - 0 bytes**

| Tabla | Tamaño | Registros | Uso | Recomendación |
|-------|--------|-----------|-----|---------------|
| `dilution_metrics` | **0 bytes** | 0 | ❌ VACÍA | ⚠️ MANTENER (se usará para métricas calculadas) |

**Nota:** Esta tabla está diseñada para almacenar métricas calculadas periódicamente, pero el job aún no se ejecuta.

---

## ⚠️ **PROBLEMAS DETECTADOS**

### **1. Duplicación de Datos**

**Campos duplicados entre tablas:**
- `shares_outstanding`: en `ticker_metadata`, `financial_statements`, `sec_dilution_profiles`
- `market_cap`: en `ticker_metadata`, `scan_results`
- `float_shares`: en `ticker_metadata`, `sec_dilution_profiles`

**Impacto:** 
- Inconsistencias potenciales
- Espacio desperdiciado
- Complejidad en actualizaciones

### **2. Inconsistencia en Tablas Maestras**

**Tenemos 3 "tablas maestras" de tickers:**
1. `ticker_metadata` (12,147 registros) - Usada por scanner y servicios generales
2. `ticker_universe` (12,031 registros) - Usada por historical
3. `sec_dilution_profiles` (5 registros) - Usada solo por dilution tracker

**Problema:** No hay relación formal (FK) entre ellas.

### **3. Tablas Preparadas pero Vacías**

Estas tablas están listas pero no se usan aún:
- `dilution_metrics` (0 registros)
- Muchas tablas SEC tienen muy pocos datos

---

## 💡 **RECOMENDACIONES**

### ✅ **MANTENER TODAS las 22 tablas**

**Razón:** Aunque algunas están vacías o con poco uso, forman parte de la arquitectura del Dilution Tracker que está en desarrollo activo. Son tablas bien diseñadas y necesarias.

### ⚠️ **NO BORRAR NINGUNA TABLA**

Todas tienen un propósito válido:
- Las del scanner están en uso activo (volume_slots con 1GB de datos)
- Las de dilution tracker están diseñadas para funcionalidad futura que ya está implementada en el código
- Borrar tablas requeriría modificar múltiples microservicios

### 🔧 **SÍ HACER: Consolidación de Tablas Maestras**

En lugar de borrar, UNIFICAR:
```
ticker_metadata + ticker_universe → tickers_unified
```

Esto:
- ✅ Elimina duplicación
- ✅ Simplifica relaciones
- ✅ Mantiene compatibilidad con vistas
- ✅ No requiere borrar tablas

---

## 📈 **MÉTRICAS POR ÁREA**

### Scanner / Market (7 tablas)
- Tamaño: 1.06 GB (99% del total)
- Estado: ✅ Producción activa
- Uso: Muy alto

### Dilution Tracker (15 tablas)
- Tamaño: 10.9 MB (1% del total)
- Estado: 🟡 En desarrollo/poblándose
- Uso: Bajo-Medio (sistema nuevo)

---

## 🎯 **CONCLUSIÓN**

**NO BORRAR NINGUNA TABLA.**

Todas son parte de la arquitectura. En su lugar:
1. ✅ Mantener todas las tablas
2. ✅ Unificar `ticker_metadata` + `ticker_universe` → `tickers_unified`
3. ✅ Añadir Foreign Keys faltantes
4. ✅ Continuar poblando tablas de Dilution Tracker

El problema NO es tener "demasiadas tablas", sino:
- ❌ Falta de relaciones formales (FK)
- ❌ Duplicación de datos
- ⚠️ Tablas maestras múltiples

Estos se arreglan con la migración FASE 1-3 propuesta, NO borrando tablas.

