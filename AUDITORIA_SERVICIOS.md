# 🔍 AUDITORÍA TÉCNICA: RESPONSABILIDADES Y DUPLICACIONES

**Fecha:** 13 Noviembre 2025
**Estado:** Análisis Completo
**Severidad:** ⚠️  MEDIA (ajustes recomendados)

---

## 📊 MATRIZ DE RESPONSABILIDADES

### ✅ **ESCRITURAS EN BASE DE DATOS**

| Tabla | Escritor(es) | Estado |
|-------|-------------|--------|
| `volume_slots` | data_maintenance | ✅ CORRECTO (único escritor) |
| `market_data_daily` | data_maintenance | ✅ CORRECTO (único escritor) |
| `ticker_universe` | historical | ✅ CORRECTO (único escritor) |
| `ticker_metadata` | historical + data_maintenance | ⚠️  2 ESCRITORES |

---

## 🚨 **PROBLEMAS IDENTIFICADOS**

### 1. **DUPLICACIÓN: ticker_metadata tiene 2 escritores**

**Servicios involucrados:**
- `historical/ticker_universe_loader.py`
- `data_maintenance/tasks/enrich_metadata.py`

**¿Qué escribe cada uno?**

```python
# Historical escribe:
- company_name
- exchange
- is_actively_trading
- updated_at

# Data Maintenance escribe:
- market_cap
- float_shares
- shares_outstanding
- sector
- industry
```

**Análisis:**
- ✅ Escriben campos DIFERENTES (complementarios)
- ⚠️  Posible race condition si ejecutan simultáneamente
- ⚠️  Falta coordinación clara

**Recomendación:**
```
OPCIÓN A (Ideal): Consolidar en UN solo servicio
  → data_maintenance carga TODO (universo + metadata)
  → historical solo SIRVE datos (GET)
  → Eliminar escritura de historical

OPCIÓN B (Actual): Documentar claramente
  → historical: campos básicos de Polygon
  → data_maintenance: enriquecimiento (market cap, sector)
  → Asegurar que NO se pisen
```

---

### 2. **DUPLICACIÓN: RVOL promedios históricos**

**Servicios involucrados:**
- `historical/main.py` → Endpoint: `GET /api/rvol/hist-avg/bulk`
- `data_maintenance/tasks/calculate_rvol_averages.py`

**¿Qué hace cada uno?**

```python
# Historical (bajo demanda):
@app.get("/api/rvol/hist-avg/bulk")
  → Calcula SQL: promedio por slot
  → Guarda en Redis
  → Responde al caller

# Data Maintenance (batch nocturno):
calculate_rvol_averages_task
  → Calcula SQL: promedio por slot
  → Guarda en Redis
  → Pre-calienta TODOS los símbolos
```

**Análisis:**
- ✅ CORRECTO: Historical es fallback bajo demanda
- ✅ CORRECTO: Data Maintenance es pre-calentamiento
- ⚠️  Usan MISMA query SQL (duplicación de código)

**Recomendación:**
```
✅ MANTENER ARQUITECTURA ACTUAL
  → data_maintenance: Pre-calcula TODO (noche)
  → historical: Fallback para cache misses (día)
  → SON COMPLEMENTARIOS, NO DUPLICADOS

⚠️  REFACTOR MENOR:
  → Mover query SQL a shared/utils/rvol_queries.py
  → Ambos servicios usan la misma función
  → DRY (Don't Repeat Yourself)
```

---

### 3. **ATR: Calculado por 2 servicios**

**Servicios involucrados:**
- `analytics/main.py` → Inicializa ATRCalculator
- `data_maintenance/tasks/calculate_atr.py`

**¿Qué hace cada uno?**

```python
# Analytics (tiempo real):
atr_calculator = ATRCalculator(...)
  → Lee ATR de Redis cache
  → Si cache miss: calcula desde market_data_daily
  → Guarda en Redis
  → Actualiza atr_percent con precio actual

# Data Maintenance (batch):
calculate_atr_task
  → Calcula ATR para TODOS los símbolos
  → Guarda en Redis con fecha de hoy
  → Se ejecuta UNA VEZ al día
```

**Análisis:**
- ✅ CORRECTO: Data Maintenance pre-calcula
- ✅ CORRECTO: Analytics lee de cache
- ⚠️  Analytics TAMBIÉN puede calcular (fallback)
- ⚠️  Ambos usan shared/utils/atr_calculator.py (CORRECTO)

**Recomendación:**
```
✅ ARQUITECTURA CORRECTA
  → data_maintenance: Batch nocturno
  → analytics: Solo READ de cache (con fallback si falta)
  → Usar clase compartida: ATRCalculator

🔧 VERIFICAR:
  → Analytics debería SOLO leer, NO calcular
  → Si falta en cache: error/None, NO calcular
  → Simplificar analytics a read-only
```

---

### 4. **METADATA: 3 servicios involucrados**

**Servicios:**
- `historical` → Carga metadata básica de Polygon
- `data_maintenance` → Enriquece con market cap, sector
- `ticker-metadata-service` → Sirve metadata vía API

**Flujo actual:**

```
Polygon API
  ↓
historical → ticker_universe + metadata básica (company_name, exchange)
  ↓
data_maintenance → Enriquece (market_cap, float, sector)
  ↓
ticker-metadata-service → SIRVE datos (GET endpoints)
```

**Análisis:**
- ⚠️  CONFUSO: 3 servicios para lo mismo
- ⚠️  historical Y data_maintenance escriben
- ✅ ticker-metadata-service solo lee (correcto)

**Recomendación:**
```
CONSOLIDAR:
  1. historical: SOLO universo (ticker_universe)
  2. data_maintenance: TODO metadata (ticker_metadata)
  3. ticker-metadata-service: SOLO API (GET)

ELIMINAR:
  - historical/ticker_universe_loader.update_ticker_metadata()
  - historical escribe en ticker_metadata

RESULTADO:
  → Separación clara de responsabilidades
  → Sin conflictos de escritura
```

---

### 5. **POLYGON API: 9 servicios consultan directamente**

**Servicios que consultan Polygon:**

| Servicio | Endpoint | Propósito | Estado |
|----------|----------|-----------|--------|
| data_ingest | `/v2/snapshot` | Snapshots tiempo real | ✅ CORRECTO |
| market_session | `/v1/marketstatus` | Estado del mercado | ✅ CORRECTO |
| historical | `/v3/reference/tickers` | Universo completo | ✅ CORRECTO |
| data_maintenance | `/v2/aggs` (OHLC, slots) | Datos históricos | ✅ CORRECTO |
| analytics | `/v2/aggs` (recovery) | Recuperación intraday | ⚠️  OPCIONAL |
| ticker-metadata | `/v3/reference/tickers/{symbol}` | Metadata individual | ⚠️  DUPLICADO |

**Análisis:**
- ✅ MAYORMENTE CORRECTO: Cada uno usa endpoint diferente
- ⚠️  ticker-metadata duplica historical
- ⚠️  analytics recovery podría delegarse

**Recomendación:**
```
CONSOLIDAR:
  → ticker-metadata: Eliminar llamadas directas a Polygon
  → Usar historical service como proxy
  → Reducir de 9 servicios a 7 con acceso directo

BENEFICIO:
  → Menos API calls
  → Centralización de rate limiting
  → Más fácil cambiar a otro proveedor
```

---

## ✅ **LO QUE ESTÁ BIEN**

### 1. **Separación Clara de Escrituras**

```
✅ volume_slots: SOLO data_maintenance
✅ market_data_daily: SOLO data_maintenance
✅ ticker_universe: SOLO historical

→ Sin conflictos de escritura concurrente
```

### 2. **Analytics es Read-Only**

```
✅ Analytics NO escribe en BD
✅ Solo lee de Redis cache
✅ Calcula RVOL en memoria
✅ Enriquece snapshots
```

### 3. **Data Maintenance es el ETL Principal**

```
✅ Carga OHLC
✅ Carga volume_slots
✅ Calcula ATR
✅ Calcula promedios RVOL
✅ Enriquece metadata
✅ Sincroniza Redis
```

---

## 📋 **RECOMENDACIONES PRIORITARIAS**

### 🔴 **ALTA PRIORIDAD**

#### **1. Resolver conflicto en ticker_metadata**

**Problema:** Historical Y data_maintenance escriben

**Solución:**
```python
# ELIMINAR de historical/ticker_universe_loader.py:
async def update_ticker_metadata(...):
    # ← BORRAR ESTA FUNCIÓN COMPLETA

# MANTENER SOLO en data_maintenance/tasks/enrich_metadata.py
```

**Resultado:** Un único escritor, sin conflictos

---

#### **2. Centralizar cálculo de RVOL promedios**

**Problema:** Historical calcula bajo demanda, data_maintenance en batch

**Solución actual es CORRECTA, pero mejorar:**
```python
# Crear: shared/queries/rvol_queries.py
def get_rvol_avg_query():
    return """
        WITH last_days AS (...)
        SELECT ...
    """

# Historical usa:
query = get_rvol_avg_query()

# Data Maintenance usa:
query = get_rvol_avg_query()

→ DRY: Query definida UNA vez
```

---

### 🟠 **MEDIA PRIORIDAD**

#### **3. Simplificar Analytics (solo read-only)**

**Problema:** Analytics puede calcular ATR si falta en cache

**Solución:**
```python
# En analytics/main.py:
# CAMBIAR:
atr_data = await atr_calculator.calculate_atr_batch(symbols)

# POR:
atr_data = await atr_calculator._get_batch_from_cache(symbols)
# Si falta: atr_data[symbol] = None (NO calcular)

→ Analytics NUNCA calcula, solo lee
→ Si falta: data_maintenance lo calculará esta noche
```

---

#### **4. Eliminar ticker-metadata-service**

**Problema:** Servicio redundante con historical

**Análisis:**
```
ticker-metadata-service:
  → Solo hace GET a Polygon
  → Historical ya hace lo mismo
  → Capa extra innecesaria

Historical:
  → Ya tiene endpoints de metadata
  → Ya consulta Polygon
  → Ya cachea en Redis
```

**Recomendación:**
```
OPCIÓN A: Eliminar ticker-metadata-service
  → api_gateway llama directamente a historical
  → Menos complejidad

OPCIÓN B: Mantener como proxy especializado
  → Si planeas agregar lógica específica de metadata
  → Si quieres separar concerns

→ Depende de tu visión arquitectónica
```

---

## 📊 **ARQUITECTURA RECOMENDADA**

### **ESCRITURAS (Único Owner)**

```
ticker_universe:     historical      (carga universo de Polygon)
ticker_metadata:     data_maintenance (enriquecimiento)
volume_slots:        data_maintenance (slots históricos)
market_data_daily:   data_maintenance (OHLC histórico)
```

### **CÁLCULOS**

```
RVOL tiempo real:        analytics       (en memoria)
RVOL promedios:          data_maintenance (pre-cálculo) + historical (fallback)
ATR:                     data_maintenance (pre-cálculo)
Intraday high/low:       analytics       (en memoria)
Categorización:          scanner         (lógica de negocio)
```

### **POLYGON API (Acceso Directo)**

```
data_ingest:      /v2/snapshot              (snapshots tiempo real)
market_session:   /v1/marketstatus          (estado mercado)
historical:       /v3/reference/tickers     (universo + metadata)
data_maintenance: /v2/aggs                  (agregados históricos)
```

---

## 🎯 **PLAN DE ACCIÓN**

### **Cambios Inmediatos (1-2 horas)**

1. ✅ Eliminar `historical/ticker_universe_loader.update_ticker_metadata()`
2. ✅ Mover query RVOL a `shared/queries/rvol_queries.py`
3. ✅ Analytics: cambiar a read-only para ATR

### **Cambios Opcionales (evaluar)**

4. ⏸️  Eliminar o mantener `ticker-metadata-service` (decisión arquitectónica)
5. ⏸️  Centralizar todas las llamadas a Polygon en historical (más trabajo)

---

## 📈 **BENEFICIOS ESPERADOS**

```
✅ Sin conflictos de escritura concurrente
✅ Responsabilidades más claras
✅ Menos duplicación de código
✅ Más fácil de mantener
✅ Menos API calls a Polygon
```

---

**¿Quieres que implemente los cambios prioritarios ahora?**
