# Análisis Completo: FILTROS Backend vs Frontend

## ✅ RESPUESTA CORRECTA A TU PREGUNTA:

**Tienes TODA LA RAZÓN**: Si el backend soporta filtrar por 150+ campos, el frontend DEBE:
1. ✅ **Recibir esos datos** del WebSocket (en los payloads de eventos)
2. ✅ **Poder filtrarlos** (tener la interfaz TypeScript definida)
3. ✅ **Exponerlos en la UI** para que el usuario pueda configurarlos
4. ✅ **Tener columnas para mostrarlos** (opcional pero recomendado)

## 📊 ESTADO ACTUAL:

### Backend (WebSocket Server)
**Archivo**: `services/websocket_server/src/index.js`

#### NUMERIC_FILTER_DEFS (~150 filtros, líneas 486-636):

**Grupo 1: Básicos (payload del evento)**
- price, rvol, change_percent, volume
- gap_percent, change_from_open
- atr_percent, rsi

**Grupo 2: Fundamentales (enriched cache)**
- market_cap, float_shares, shares_outstanding

**Grupo 3: Ventanas de Volumen (enriched)**
- vol_1min, vol_5min, vol_10min, vol_15min, vol_30min

**Grupo 4: Ventanas de Cambio % (enriched)**
- chg_1min, chg_5min, chg_10min, chg_15min, chg_30min, chg_60min

**Grupo 5: Quote Data (enriched)**
- bid, ask, bid_size, ask_size, spread

**Grupo 6: SMA Intradía (enriched, 1-min bars)**
- sma_5, sma_8, sma_20, sma_50, sma_200

**Grupo 7: EMA Intradía (enriched)**
- ema_20, ema_50

**Grupo 8: Indicadores Técnicos Avanzados (enriched)**
- macd_line, macd_hist
- stoch_k, stoch_d
- adx_14
- bb_upper, bb_lower

**Grupo 9: Indicadores Diarios (enriched)**
- daily_sma_20, daily_sma_50, daily_sma_200
- daily_rsi
- high_52w, low_52w

**Grupo 10: Trades Anomaly (enriched)**
- trades_today, trades_z_score

**Grupo 11: VWAP (enriched)**
- vwap

**Grupo 12: Derivados Computados (enriched)**
- dollar_volume
- todays_range, todays_range_pct
- bid_ask_ratio
- float_turnover
- dist_from_vwap
- dist_sma_5, dist_sma_8, dist_sma_20, dist_sma_50, dist_sma_200
- pos_in_range
- below_high, above_low
- pos_of_open
- prev_day_volume

**Grupo 13: Multi-día (enriched)**
- change_1d, change_3d, change_5d, change_10d, change_20d

**Grupo 14: Avg Volumes (enriched)**
- avg_volume_5d, avg_volume_10d, avg_volume_20d

**Grupo 15: Distancias Diarias (enriched)**
- dist_daily_sma_20, dist_daily_sma_50

**Grupo 16: 52w Distancias (enriched)**
- from_52w_high, from_52w_low

**Grupo 17: Indicadores Diarios Extra (enriched)**
- daily_adx_14, daily_atr_percent, daily_bb_position

**Grupo 18: Scanner-aligned (enriched)**
- volume_today_pct, minute_volume
- price_from_high, distance_from_nbbo
- premarket_change_percent, postmarket_change_percent
- avg_volume_3m, atr

#### STRING_FILTER_DEFS (3 filtros, líneas 705-709):
- security_type
- sector
- industry

**TOTAL BACKEND: ~150 filtros numéricos + 3 string = ~153 filtros**

---

## Frontend

### 1. ✅ TypeScript Interface (EventFilterParameters)
**Archivo**: `frontend/stores/useEventFiltersStore.ts` (líneas 19-269)

**COBERTURA**: ~145 filtros definidos en la interfaz
- ✅ Todos los filtros del backend están definidos
- ✅ La interfaz puede RECIBIR todos los filtros del backend
- ✅ El store Zustand puede ALMACENAR todos los filtros

### 2. ✅ UI de Configuración (ConfigWindow.tsx)
**Archivo**: `frontend/components/config/ConfigWindow.tsx` (líneas 996-1145)

**Array FG (Filter Groups)** - Filtros EXPUESTOS en la UI:

```typescript
const FG = [
  { id: 'price', group: 'Price', filters: [...] },          // 6 filtros
  { id: 'change', group: 'Change', filters: [...] },        // 6 filtros
  { id: 'volume', group: 'Volume', filters: [...] },        // 8 filtros
  { id: 'windows', group: 'Time Windows', filters: [...] }, // 6 filtros
  { id: 'quote', group: 'Quote', filters: [...] },          // 5 filtros
  { id: 'tech', group: 'Intraday Technical', filters: [...] }, // 17 filtros
  { id: 'daily', group: 'Daily Indicators', filters: [...] },  // 6 filtros
  { id: 'fund', group: 'Fundamentals', filters: [...] },    // 3 filtros
  { id: 'trades', group: 'Trades Anomaly', filters: [...] }, // 2 filtros
  { id: 'derived', group: 'Derived', filters: [...] },      // 10 filtros
  { id: 'dist', group: 'Distance %', filters: [...] },      // 8 filtros
  { id: 'multiday', group: 'Multi-Day Change %', filters: [...] }, // 5 filtros
  { id: 'avgvol', group: 'Avg Volume', filters: [...] },    // 4 filtros
  { id: '52wextra', group: '52W / Daily Extra', filters: [...] }, // 5 filtros
]
```

**TOTAL UI: ~91 filtros expuestos**

---

## 🔴 PROBLEMA REAL:

```
┌─────────────────────┬─────────────┬──────────────────────┬─────────────┬────────────┐
│                     │   Backend   │  Frontend Interface  │  Frontend   │ Cobertura  │
│                     │   Soporta   │    (TypeScript)      │     UI      │    UI      │
├─────────────────────┼─────────────┼──────────────────────┼─────────────┼────────────┤
│  Filtros Numéricos  │     150     │         ~145         │     ~91     │    ~61%    │
│  Filtros String     │      3      │           3          │      0      │     0%     │
├─────────────────────┼─────────────┼──────────────────────┼─────────────┼────────────┤
│       TOTAL         │     153     │         ~148         │     ~91     │    ~60%    │
└─────────────────────┴─────────────┴──────────────────────┴─────────────┴────────────┘
```

### ❌ Filtros NO expuestos en la UI (~60 filtros):

#### Quote Data (faltan 0):
✅ Ya están todos expuestos

#### Ventanas de Tiempo (faltan 0):
✅ Ya están todos expuestos

#### Indicadores Técnicos Intradía (faltan 0):
✅ Ya están todos expuestos

#### Indicadores Diarios (faltan 0):
✅ Ya están todos expuestos

#### Derivados (faltan 0):
✅ Ya están todos expuestos

#### **String Filters (faltan 3):**
- ❌ `security_type` - Filtrar por tipo (CS, ETF, PFD, WARRANT)
- ❌ `sector` - Filtrar por sector
- ❌ `industry` - Filtrar por industria

### 💡 FILTROS ESPECIALES NO EXPUESTOS:

Algunos filtros del backend NO están en la UI porque son:
- **Aliases o legacy**: min_sma_20/max_sma_20 (legacy para backward compat)
- **Internos**: watchlist_only, symbols_include, symbols_exclude (manejados por tab separado)

---

## 🎯 CONCLUSIÓN:

### ¿Tenemos cobertura completa?

#### Para EVENTOS (Event Detector):
- ✅ **Interface TypeScript**: 98% cobertura (~145/150 filtros)
- ✅ **UI Configuration**: ~60% cobertura (~91/150 filtros)
- ❌ **String Filters UI**: 0% cobertura (0/3 filtros)
- ✅ **Columnas en tabla**: ~40% cobertura (13/33 campos)

**PROBLEMA**: El usuario NO puede configurar:
1. ❌ Filtros por **sector**, **industry**, **security_type** (strings)
2. ❌ ~60 filtros numéricos avanzados (aunque la mayoría son edge cases)

#### Para SCANNER:
- ✅ **Backend**: Envía ~110 campos por ticker
- ✅ **Frontend Ticker interface**: ~60 campos mapeados
- ✅ **Columnas visibles**: 40 columnas implementadas
- ⚠️ **Filtros UI**: ~91 expuestos (compartido con eventos)

**PROBLEMA**: El usuario NO puede:
1. ❌ Filtrar por **sector**, **industry**, **security_type**
2. ❌ Ver ~70 columnas adicionales en las tablas (aunque los datos SÍ llegan)

---

## 🛠️ RECOMENDACIÓN:

### Prioridad ALTA:
1. **Añadir filtros string a la UI** (sector, industry, security_type)
   - Requiere dropdowns o autocomplete en lugar de inputs numéricos
   - Backend ya los soporta 100%

### Prioridad MEDIA:
2. **Añadir columnas faltantes a las tablas** (scanner + events)
   - Los datos YA llegan del backend
   - Solo hay que mapearlos en `columnHelper.accessor()`
   - Mantenerlas ocultas por defecto

### Prioridad BAJA:
3. **Exponer filtros numéricos edge-case** (ej: minute_volume, minute_volume_min)
   - Son casos muy específicos que pocos usuarios necesitan
   - Pero si queremos cobertura 100%, hay que añadirlos

---

## 📋 FILTROS NUMÉRICOS FALTANTES EN UI (detalle):

Revisando el código más detenidamente, la mayoría de filtros YA están expuestos. Los ~60 "faltantes" que mencioné antes son en realidad:
- **Aliases** (min_sma_20 es alias de min_ema_20, legacy)
- **Manejados en otra parte de la UI** (symbols_include en tab Symbols)
- **Edge cases** que raramente se usan

El problema REAL son los **3 filtros STRING** que NO están en la UI.
