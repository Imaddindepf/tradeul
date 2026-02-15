# 🗺️ MAPA COMPLETO DE TABLAS - Tradeul Database

**Fecha**: 2025-11-23  
**Base de Datos**: `tradeul` (TimescaleDB/PostgreSQL)  
**Total Tablas**: 23 tablas activas  

---

## 📊 RESUMEN POR TAMAÑO

| Tabla | Tamaño | Registros Est. | Categoría |
|-------|--------|----------------|-----------|
| `volume_slots` | **1,044 MB** | ~50M+ | 🔥 Time-Series (Hypertable) |
| `ticker_metadata_old` | 13 MB | 12,147 | 📦 Backup |
| `tickers_unified` | 13 MB | 12,369 | ⭐ **TABLA MAESTRA** |
| `ticker_universe_old` | 3.6 MB | 12,369 | 📦 Backup |
| `institutional_holders` | 3.1 MB | ~15K | 📈 Análisis |
| `sec_filings` | 360 KB | ~2K | 📄 SEC Data |
| `financial_statements` | 176 KB | ~500 | 💰 Financials |
| `sec_dilution_profiles` | 120 KB | ~300 | 🎯 Dilution Tracker |
| `scanner_filters` | 96 KB | ~50 | ⚙️ Config |
| `sec_warrants` | 56 KB | ~200 | 📄 SEC Data |
| `sec_completed_offerings` | 48 KB | ~150 | 📄 SEC Data |
| `market_data_daily` | 32 KB | ~100 | 📈 Market |
| `market_sessions_log` | 24 KB | ~50 | 📊 Logs |
| Resto (10 tablas) | <16 KB | <100 | 📄 SEC + Config |

---

## 🏗️ ARQUITECTURA DE DATOS

### 📌 TABLAS MAESTRAS (Core)

#### ⭐ `tickers_unified` (13 MB, 12,369 registros)
**Tabla principal unificada de tickers**

```
PRIMARY KEY: symbol (VARCHAR(20))
INDICES: symbol (UNIQUE)

Campos (35):
├─ Identificación (5):
│  ├─ symbol VARCHAR(20) ⚡ PK
│  ├─ company_name VARCHAR(500)
│  ├─ cik VARCHAR(10)
│  ├─ ticker_root VARCHAR(10)
│  └─ ticker_suffix VARCHAR(10)
│
├─ Clasificación (4):
│  ├─ exchange VARCHAR(50) (XNAS, XNYS, etc.)
│  ├─ sector VARCHAR(100)
│  ├─ industry VARCHAR(200)
│  └─ type VARCHAR(20) (CS, ETF, ADR, etc.)
│
├─ Mercado (10):
│  ├─ current_price NUMERIC
│  ├─ market_cap BIGINT
│  ├─ float_shares BIGINT
│  ├─ shares_outstanding BIGINT
│  ├─ avg_volume_30d BIGINT
│  ├─ avg_volume_10d BIGINT
│  ├─ avg_price_30d NUMERIC
│  ├─ beta NUMERIC
│  ├─ locale VARCHAR(2) (us, gb, etc.)
│  └─ market VARCHAR(10) (stocks, crypto, fx)
│
├─ Información Compañía (6):
│  ├─ description TEXT
│  ├─ homepage_url TEXT
│  ├─ phone_number VARCHAR(20)
│  ├─ address JSONB
│  ├─ total_employees INTEGER
│  └─ list_date DATE
│
├─ Branding (2):
│  ├─ logo_url TEXT
│  └─ icon_url TEXT
│
├─ Identificadores Financieros (5):
│  ├─ composite_figi VARCHAR(12)
│  ├─ share_class_figi VARCHAR(12)
│  ├─ currency_name VARCHAR(10)
│  ├─ round_lot INTEGER
│  └─ delisted_utc TIMESTAMP
│
└─ Estados y Auditoría (3):
   ├─ is_active BOOLEAN
   ├─ is_etf BOOLEAN
   ├─ is_actively_trading BOOLEAN
   ├─ last_seen TIMESTAMP
   ├─ created_at TIMESTAMP
   └─ updated_at TIMESTAMP

RELACIONES:
└─→ Referenciada por: TODAS las tablas operacionales (sin FK formal aún)
```

---

### 🔥 TABLAS TIME-SERIES (Hypertables)

#### `volume_slots` (1,044 MB, ~50M registros)
**Volumen intraday por slots de tiempo**

```
PRIMARY KEY: (date, symbol, slot_number)
HYPERTABLE: Particionado por date (1 día)

Campos:
├─ date DATE ⚡ Part Key
├─ symbol VARCHAR(20) → tickers_unified
├─ slot_number INTEGER (1-78, slots de 5 min)
├─ slot_time TIME
├─ volume_accumulated BIGINT
├─ trades_count INTEGER
└─ avg_price NUMERIC

USO:
• Cálculo de RVOL por slot
• Análisis de patrones intraday
• Detección de momentum
```

#### `market_data_daily` (32 KB, ~100 registros)
**OHLCV diario**

```
PRIMARY KEY: (trading_date, symbol)
HYPERTABLE: Particionado por trading_date (1 día)

Campos:
├─ trading_date DATE ⚡ Part Key
├─ symbol VARCHAR(20) → tickers_unified
├─ open NUMERIC
├─ high NUMERIC
├─ low NUMERIC
├─ close NUMERIC
├─ volume BIGINT
├─ vwap NUMERIC
└─ trades_count INTEGER

USO:
• Cálculo de ATR
• Gaps premarket
• Análisis técnico
```

#### `market_sessions_log` (24 KB, ~50 registros)
**Log de cambios de sesión de mercado**

```
PRIMARY KEY: time
HYPERTABLE: Particionado por time (1 día)

Campos:
├─ time TIMESTAMP ⚡ Part Key
├─ session VARCHAR(20) (PRE_MARKET, MARKET_OPEN, etc.)
├─ trading_date DATE
├─ event_type VARCHAR(50)
└─ metadata JSONB

USO:
• Auditoría de sesiones
• Debugging de horarios
• Análisis de eventos
```

---

### 📄 TABLAS SEC DILUTION TRACKER

#### ⭐ `sec_dilution_profiles` (120 KB, ~300 registros)
**Perfil maestro de dilución por ticker**

```
PRIMARY KEY: id (SERIAL)
UNIQUE: ticker

Campos:
├─ id SERIAL ⚡ PK
├─ ticker VARCHAR(20) UNIQUE → tickers_unified
├─ cik VARCHAR(10)
├─ company_name VARCHAR(500)
├─ current_price NUMERIC
├─ shares_outstanding BIGINT
├─ float_shares BIGINT
├─ last_scraped_at TIMESTAMP
├─ source_filings JSONB (URLs de filings procesados)
├─ scrape_success BOOLEAN
├─ scrape_error TEXT
├─ created_at TIMESTAMP
└─ updated_at TIMESTAMP

RELACIONES:
└─→ Referencia: sec_s1_offerings, sec_atm_offerings, sec_shelf_registrations
    sec_warrants, sec_convertible_notes, sec_convertible_preferred,
    sec_equity_lines, sec_completed_offerings
```

#### `sec_s1_offerings` (16 KB, ~50 registros)
**Ofertas S-1 (IPO/Secondary)**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ anticipated_deal_size NUMERIC
├─ final_deal_size NUMERIC
├─ final_shares_offered BIGINT
├─ warrant_coverage NUMERIC
├─ underwriter_agent VARCHAR
├─ status VARCHAR (pending, priced, completed, withdrawn)
└─ filing_url TEXT

USO: Análisis de dilución inmediata por ofertas directas
```

#### `sec_atm_offerings` (16 KB, ~30 registros)
**At-The-Market Offerings**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ total_capacity NUMERIC
├─ remaining_capacity NUMERIC (actualizable)
├─ placement_agent VARCHAR
├─ potential_shares_at_current_price BIGINT (calculado)
└─ status VARCHAR (active, exhausted, terminated)

USO: Dilución gradual, alto impacto en penny stocks
```

#### `sec_shelf_registrations` (16 KB, ~50 registros)
**Shelf Registrations (S-3, F-3)**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ total_capacity NUMERIC ($500M típico)
├─ remaining_capacity NUMERIC
├─ is_baby_shelf BOOLEAN (límite $75M para small caps)
├─ current_raisable_amount NUMERIC (baby shelf restriction)
├─ total_amount_raised NUMERIC
├─ total_amount_raised_last_12mo NUMERIC
├─ expiration_date DATE (3 años desde effect_date)
└─ security_type VARCHAR

USO: Potencial de dilución a largo plazo
```

#### `sec_warrants` (56 KB, ~200 registros)
**Warrants pendientes**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ outstanding BIGINT (número de warrants)
├─ exercise_price NUMERIC
├─ expiration_date DATE
├─ potential_new_shares BIGINT (= outstanding)
└─ issue_date DATE

USO: Dilución futura si precio > exercise_price
```

#### `sec_convertible_notes` (16 KB, ~20 registros)
**Notas convertibles**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ total_principal_amount NUMERIC
├─ remaining_principal_amount NUMERIC
├─ conversion_price NUMERIC
├─ total_shares_when_converted BIGINT
├─ remaining_shares_when_converted BIGINT
├─ maturity_date DATE
└─ convertible_date DATE

USO: Dilución por conversión de deuda
```

#### `sec_convertible_preferred` (16 KB, ~15 registros)
**Acciones preferentes convertibles**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ series VARCHAR (A, B, C, etc.)
├─ total_dollar_amount_issued NUMERIC
├─ remaining_dollar_amount NUMERIC
├─ conversion_price NUMERIC
├─ total_shares_when_converted BIGINT
└─ remaining_shares_when_converted BIGINT

USO: Dilución por conversión de preferentes
```

#### `sec_equity_lines` (16 KB, ~10 registros)
**Equity Lines of Credit**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ total_capacity NUMERIC
├─ remaining_capacity NUMERIC
├─ agreement_start_date DATE
└─ agreement_end_date DATE

USO: Financiamiento flexible, alta dilución
```

#### `sec_completed_offerings` (48 KB, ~150 registros)
**Historial de ofertas completadas**

```
Campos Clave:
├─ ticker VARCHAR(20) → sec_dilution_profiles
├─ offering_type VARCHAR (S-1, RD, ATM, PIPE, etc.)
├─ shares_issued BIGINT
├─ price_per_share NUMERIC
├─ amount_raised NUMERIC
└─ offering_date DATE

USO: Análisis histórico de dilución
```

#### `sec_filings` (360 KB, ~2K registros)
**Todos los filings SEC relevantes**

```
Campos Clave:
├─ ticker VARCHAR(20) → tickers_unified
├─ filing_type VARCHAR (8-K, S-1, S-3, 424B5, etc.)
├─ filing_date DATE
├─ report_date DATE
├─ accession_number VARCHAR (UNIQUE)
├─ title TEXT
├─ description TEXT
├─ url TEXT
├─ category VARCHAR (offering, financial, corporate, etc.)
├─ is_offering_related BOOLEAN
└─ is_dilutive BOOLEAN

USO: Fuente de datos para scraping de dilución
```

---

### 💰 TABLAS FINANCIERAS

#### `financial_statements` (176 KB, ~500 registros)
**Estados financieros trimestrales/anuales**

```
PRIMARY KEY: (ticker, period_date, period_type)

Campos (69 campos total):
├─ Identificación:
│  ├─ ticker VARCHAR(20) → tickers_unified
│  ├─ period_date DATE
│  ├─ period_type VARCHAR (Q, Y)
│  └─ fiscal_year INTEGER
│
├─ Balance Sheet (23 campos):
│  ├─ total_assets NUMERIC
│  ├─ total_liabilities NUMERIC
│  ├─ stockholders_equity NUMERIC
│  ├─ cash_and_equivalents NUMERIC
│  ├─ short_term_investments NUMERIC
│  ├─ total_debt NUMERIC
│  ├─ receivables, inventories, etc.
│  └─ [20 más...]
│
├─ Income Statement (18 campos):
│  ├─ revenue NUMERIC
│  ├─ gross_profit NUMERIC
│  ├─ operating_income NUMERIC
│  ├─ net_income NUMERIC
│  ├─ eps_basic NUMERIC
│  ├─ eps_diluted NUMERIC
│  └─ [12 más...]
│
├─ Cash Flow (12 campos):
│  ├─ operating_cash_flow NUMERIC
│  ├─ investing_cash_flow NUMERIC
│  ├─ financing_cash_flow NUMERIC
│  ├─ free_cash_flow NUMERIC
│  └─ [8 más...]
│
└─ Shares:
   ├─ shares_outstanding BIGINT
   ├─ weighted_avg_shares_basic BIGINT
   └─ weighted_avg_shares_diluted BIGINT

USO:
• Análisis fundamental
• Cálculo de cash runway
• Detección de necesidad de capital
```

#### `dilution_metrics` (0 bytes, vacía)
**Métricas calculadas de dilución**

```
Campos:
├─ ticker VARCHAR(20) → tickers_unified
├─ calculated_at DATE
├─ current_cash NUMERIC
├─ quarterly_burn_rate NUMERIC
├─ estimated_runway_months NUMERIC
├─ shares_outstanding_current BIGINT
├─ shares_outstanding_1y_ago BIGINT
├─ shares_outstanding_2y_ago BIGINT
├─ dilution_pct_1y NUMERIC
├─ dilution_pct_2y NUMERIC
├─ debt_to_equity NUMERIC
├─ current_ratio NUMERIC
├─ working_capital NUMERIC
├─ overall_risk_score INTEGER (0-100)
├─ cash_need_score INTEGER (0-100)
├─ dilution_risk_score INTEGER (0-100)
├─ data_quality_score NUMERIC
└─ last_financial_date DATE

USO:
• Dashboard de dilution tracker
• Rankings de riesgo
• Alertas automáticas
```

---

### 📈 TABLAS DE ANÁLISIS

#### `institutional_holders` (3.1 MB, ~15K registros)
**Holdings institucionales 13F**

```
PRIMARY KEY: (ticker, holder_name, report_date)

Campos:
├─ ticker VARCHAR(20) → tickers_unified
├─ holder_name VARCHAR(500)
├─ report_date DATE (quarterly)
├─ shares_held BIGINT
├─ position_value NUMERIC
├─ ownership_percent NUMERIC
├─ position_change BIGINT
├─ position_change_percent NUMERIC
├─ filing_date DATE
├─ form_type VARCHAR (13F-HR)
├─ cik VARCHAR(10)
└─ fetched_at TIMESTAMP

USO:
• Análisis de smart money
• Detección de acumulación institucional
• Sentiment institucional
```

#### `scanner_filters` (96 KB, ~50 registros)
**Configuración de filtros del scanner**

```
PRIMARY KEY: id (SERIAL)

Campos:
├─ id SERIAL ⚡ PK
├─ name VARCHAR(100)
├─ description TEXT
├─ enabled BOOLEAN
├─ filter_type VARCHAR(50)
├─ parameters JSONB:
│  {
│    "min_rvol": 2.0,
│    "min_price": 0.5,
│    "max_price": 50,
│    "min_volume": 100000,
│    "min_change_percent": 10,
│    "sectors": ["Technology", "Healthcare"],
│    "sessions": ["PRE_MARKET", "MARKET_OPEN"]
│  }
├─ priority INTEGER
├─ created_at TIMESTAMP
└─ updated_at TIMESTAMP

USO:
• Scanner engine filters
• Categorización dinámica
• Personalización de scans
```

---

### ⚙️ TABLAS DE CONFIGURACIÓN

#### `ticker_sync_config` (8 KB, ~200 registros)
**Configuración de sincronización por ticker**

```
PRIMARY KEY: ticker

Campos:
├─ ticker VARCHAR(20) ⚡ PK → tickers_unified
├─ tier INTEGER (1=high priority, 3=low)
├─ sync_frequency VARCHAR (realtime, hourly, daily)
├─ last_synced_at TIMESTAMP
├─ sync_count INTEGER
├─ failed_sync_count INTEGER
├─ last_error TEXT
├─ search_count_7d INTEGER
├─ search_count_30d INTEGER
├─ last_searched_at TIMESTAMP
├─ priority_score NUMERIC (calculado)
├─ promoted_at TIMESTAMP
├─ demoted_at TIMESTAMP
├─ created_at TIMESTAMP
└─ updated_at TIMESTAMP

USO:
• Rate limiting inteligente
• Priorización dinámica de scraping
• Análisis de demanda
```

#### `dilution_searches` (8 KB, ~500 registros)
**Log de búsquedas del dilution tracker**

```
Campos:
├─ id SERIAL ⚡ PK
├─ ticker VARCHAR(20) → tickers_unified
├─ user_id UUID
├─ session_id VARCHAR
└─ searched_at TIMESTAMP

USO:
• Analytics de uso
• Trending tickers
• Feed para ticker_sync_config.search_count_*
```

#### `market_holidays` (16 KB, ~20 registros/año)
**Calendario de días festivos del mercado**

```
Campos:
├─ date DATE ⚡ PK
├─ name VARCHAR(100)
├─ exchange VARCHAR(10) (NYSE, NASDAQ)
├─ is_early_close BOOLEAN
└─ early_close_time TIME

USO:
• Market session service
• Cálculo de trading days
• Validación de horarios
```

---

### 📦 TABLAS DE BACKUP (Deprecated)

#### `ticker_metadata_old` (13 MB, 12,147 registros)
**Backup de ticker_metadata antes de migración**

```
⚠️ DEPRECATED - Preservado como backup de seguridad
Estado: Read-only
Plan: Eliminar después de 1 mes sin issues (FASE 4)
```

#### `ticker_universe_old` (3.6 MB, 12,369 registros)
**Backup de ticker_universe antes de migración**

```
⚠️ DEPRECATED - Preservado como backup de seguridad
Estado: Read-only
Plan: Eliminar después de 1 mes sin issues (FASE 4)
```

---

## 🔗 RELACIONES ENTRE TABLAS

### 🌟 FLUJO PRINCIPAL DE DATOS

```
┌─────────────────────────┐
│   tickers_unified       │ ← TABLA MAESTRA
│   (12,369 tickers)      │
└──────────┬──────────────┘
           │
           ├──→ scanner_filters (config)
           │
           ├──→ volume_slots (time-series, 1GB+)
           │   └─→ Cálculo RVOL → Scanner Engine
           │
           ├──→ market_data_daily (time-series)
           │   └─→ Cálculo ATR, Gaps → Scanner Engine
           │
           ├──→ ticker_sync_config (priorización)
           │   ├─→ Tier-based scraping
           │   └─→ Smart rate limiting
           │
           ├──→ dilution_searches (analytics)
           │   └─→ Trending detection
           │
           ├──→ sec_dilution_profiles (master profile)
           │   ├─→ sec_s1_offerings
           │   ├─→ sec_atm_offerings
           │   ├─→ sec_shelf_registrations
           │   ├─→ sec_warrants
           │   ├─→ sec_convertible_notes
           │   ├─→ sec_convertible_preferred
           │   ├─→ sec_equity_lines
           │   └─→ sec_completed_offerings
           │
           ├──→ sec_filings (fuente de scraping)
           │
           ├──→ financial_statements
           │   └─→ dilution_metrics (calculado)
           │
           ├──→ institutional_holders
           │
           └──→ market_sessions_log
```

### 🎯 FLUJO DILUTION TRACKER

```
1. USER busca ticker → dilution_searches (log)
                     ↓
2. Lookup → sec_dilution_profiles
           ├─ Cache hit? → Return data
           └─ Cache miss? → Scrape
                           ↓
3. Scrape SEC Edgar
   ├─→ Parse filings → sec_filings
   ├─→ Extract S-1 → sec_s1_offerings
   ├─→ Extract ATM → sec_atm_offerings
   ├─→ Extract Shelf → sec_shelf_registrations
   ├─→ Extract Warrants → sec_warrants
   ├─→ Extract Converts → sec_convertible_notes
   └─→ Extract Preferred → sec_convertible_preferred
                           ↓
4. Calculate metrics:
   ├─→ financial_statements (cash, burn rate)
   ├─→ tickers_unified (current price, shares)
   └─→ All dilution tables
                           ↓
5. Store → dilution_metrics (cache)
                           ↓
6. Return to frontend
```

### 📊 FLUJO SCANNER

```
1. Polygon WS → Real-time ticks
                ↓
2. Analytics Service:
   ├─→ Aggregate to slots → volume_slots
   ├─→ Calculate RVOL (compare with avg)
   └─→ Track intraday high/low
                ↓
3. Scanner Engine:
   ├─→ Read enriched snapshot (price, volume, RVOL)
   ├─→ Get metadata → tickers_unified (MGET batch)
   ├─→ Get filters → scanner_filters
   ├─→ Apply filters → Filter out non-matching
   ├─→ Calculate score → Rank tickers
   └─→ Categorize → gappers, volume_leaders, etc.
                ↓
4. Publish to Redis streams → WebSocket Server
                              ↓
5. Frontend receives → Display tables
```

---

## 🎯 PLAN DE MEJORA (FASE 4 - Futuro)

### 1. Agregar Foreign Keys
```sql
-- Scanner
ALTER TABLE volume_slots 
ADD CONSTRAINT fk_volume_slots_ticker 
FOREIGN KEY (symbol) REFERENCES tickers_unified(symbol);

ALTER TABLE market_data_daily 
ADD CONSTRAINT fk_market_data_ticker 
FOREIGN KEY (symbol) REFERENCES tickers_unified(symbol);

-- Dilution
ALTER TABLE sec_dilution_profiles 
ADD CONSTRAINT fk_sec_dilution_ticker 
FOREIGN KEY (ticker) REFERENCES tickers_unified(symbol);

ALTER TABLE sec_s1_offerings 
ADD CONSTRAINT fk_s1_profile 
FOREIGN KEY (ticker) REFERENCES sec_dilution_profiles(ticker);

-- [Resto de tablas SEC...]

-- Analytics
ALTER TABLE financial_statements 
ADD CONSTRAINT fk_financial_ticker 
FOREIGN KEY (ticker) REFERENCES tickers_unified(symbol);

ALTER TABLE institutional_holders 
ADD CONSTRAINT fk_institutional_ticker 
FOREIGN KEY (ticker) REFERENCES tickers_unified(symbol);
```

### 2. Optimizar Índices
```sql
-- tickers_unified
CREATE INDEX idx_tickers_sector ON tickers_unified(sector);
CREATE INDEX idx_tickers_exchange ON tickers_unified(exchange);
CREATE INDEX idx_tickers_market_cap ON tickers_unified(market_cap);
CREATE INDEX idx_tickers_actively_trading ON tickers_unified(is_actively_trading) WHERE is_actively_trading = true;

-- volume_slots (ya tiene índices por hypertable)
CREATE INDEX idx_volume_slots_symbol_date ON volume_slots(symbol, date DESC);

-- sec_dilution_profiles
CREATE INDEX idx_dilution_last_scraped ON sec_dilution_profiles(last_scraped_at);
CREATE INDEX idx_dilution_success ON sec_dilution_profiles(scrape_success) WHERE scrape_success = false;
```

### 3. Vistas Útiles
```sql
-- Vista de tickers "hot" (alta búsqueda)
CREATE VIEW hot_tickers AS
SELECT t.*, tsc.search_count_7d, tsc.search_count_30d
FROM tickers_unified t
JOIN ticker_sync_config tsc ON t.symbol = tsc.ticker
WHERE tsc.search_count_7d > 10
ORDER BY tsc.search_count_7d DESC;

-- Vista de dilución combinada
CREATE VIEW dilution_summary AS
SELECT 
    sdp.ticker,
    sdp.company_name,
    sdp.current_price,
    sdp.shares_outstanding,
    COUNT(DISTINCT ss1.id) as s1_offerings_count,
    COUNT(DISTINCT satm.id) as atm_offerings_count,
    COUNT(DISTINCT sshelf.id) as shelf_count,
    COUNT(DISTINCT sw.id) as warrants_count,
    SUM(sw.potential_new_shares) as total_warrant_shares,
    SUM(satm.potential_shares_at_current_price) as total_atm_shares
FROM sec_dilution_profiles sdp
LEFT JOIN sec_s1_offerings ss1 ON sdp.ticker = ss1.ticker
LEFT JOIN sec_atm_offerings satm ON sdp.ticker = satm.ticker AND satm.status = 'active'
LEFT JOIN sec_shelf_registrations sshelf ON sdp.ticker = sshelf.ticker
LEFT JOIN sec_warrants sw ON sdp.ticker = sw.ticker AND sw.expiration_date > CURRENT_DATE
GROUP BY sdp.ticker, sdp.company_name, sdp.current_price, sdp.shares_outstanding;
```

---

## 📈 MÉTRICAS DE RENDIMIENTO

### Queries Más Frecuentes

1. **Scanner metadata lookup** (10K+ req/min en market hours)
   - `SELECT * FROM tickers_unified WHERE symbol = $1`
   - **Optimizado**: Redis cache + MGET batch

2. **Volume slots aggregation** (1 req/5 sec per ticker)
   - `SELECT * FROM volume_slots WHERE date = $1 AND symbol = $2`
   - **Optimizado**: Hypertable partitioning

3. **Dilution profile lookup** (100 req/min)
   - `SELECT * FROM sec_dilution_profiles WHERE ticker = $1`
   - **Optimizado**: Index on ticker (UNIQUE)

### Tamaños Proyectados (1 año)

| Tabla | Actual | 1 Año |
|-------|--------|-------|
| `volume_slots` | 1 GB | ~10 GB |
| `market_data_daily` | 32 KB | ~50 MB |
| `tickers_unified` | 13 MB | ~15 MB |
| `sec_filings` | 360 KB | ~5 MB |
| `financial_statements` | 176 KB | ~1 MB |

---

**Preparado por**: AI Assistant  
**Fecha**: 2025-11-23  
**Estado**: ✅ Base de datos optimizada y unificada

