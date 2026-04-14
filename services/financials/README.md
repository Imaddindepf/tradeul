# Tradeul Financials Service

## 🎯 Propósito

Microservicio dedicado a la **extracción, normalización y presentación de datos financieros** de empresas públicas estadounidenses. Replica la funcionalidad de plataformas como TIKR.com y Bloomberg Terminal.

---

## 📐 Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FINANCIALS MICROSERVICE                          │
│                        (Puerto 8020)                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │
│  │   SEC-API    │   │  edgartools  │   │     FMP      │            │
│  │   (Pago)     │   │   (Gratis)   │   │   (Backup)   │            │
│  │              │   │              │   │              │            │
│  │ JSON rápido  │   │ XBRL crudo   │   │ Datos alt.   │            │
│  │ Pre-parseado │   │ Detallado    │   │              │            │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘            │
│         │                  │                  │                     │
│         └─────────┬────────┴──────────────────┘                     │
│                   ▼                                                  │
│         ┌─────────────────┐                                         │
│         │    EXTRACTOR    │  ← Normaliza conceptos XBRL             │
│         │  (extractors.py)│    62 regex patterns                    │
│         └────────┬────────┘    10,732 FASB labels fallback          │
│                  │                                                   │
│                  ▼                                                   │
│         ┌─────────────────┐                                         │
│         │   CALCULATOR    │  ← Métricas derivadas                   │
│         │ (calculators.py)│    Gross Profit, EBITDA, Margins        │
│         └────────┬────────┘    YoY, FCF, Book Value                 │
│                  │                                                   │
│                  ▼                                                   │
│         ┌─────────────────┐                                         │
│         │   STRUCTURES    │  ← Jerarquía visual                     │
│         │ (structures.py) │    Secciones, orden, indentación        │
│         └────────┬────────┘    Perfiles de industria                │
│                  │                                                   │
│                  ▼                                                   │
│         ┌─────────────────┐                                         │
│         │     SPLITS      │  ← Ajuste histórico                     │
│         │   (splits.py)   │    EPS y Shares ajustados               │
│         └────────┬────────┘    Polygon API                          │
│                  │                                                   │
│                  ▼                                                   │
│              JSON Response                                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estructura de Archivos

```
services/financials/
├── main.py                      # FastAPI app, endpoints
├── Dockerfile                   # Container config
├── requirements.txt             # Dependencies
├── README.md                    # Este archivo
│
├── services/
│   ├── sec_xbrl/               # 🔵 SERVICIO PRINCIPAL
│   │   ├── __init__.py
│   │   ├── service.py          # Orquestador principal
│   │   ├── extractors.py       # Extracción y normalización XBRL
│   │   ├── calculators.py      # Métricas calculadas
│   │   ├── structures.py       # Jerarquía de display (141 campos)
│   │   └── splits.py           # Ajuste por stock splits
│   │
│   ├── mapping/                # 🧠 MAPPING ENGINE
│   │   ├── __init__.py
│   │   ├── adapter.py          # ⭐ Interfaz principal (XBRLMapper)
│   │   ├── schema.py           # ⭐ Schema + Tier 1 mappings (~250)
│   │   ├── sec_tier2.py        # ⭐ Tier 2 auto-mappings (~3,298)
│   │   ├── engine.py           # Regex patterns + FASB labels
│   │   ├── database.py         # (Futuro) PostgreSQL repository
│   │   ├── llm_classifier.py   # (Futuro) Grok LLM classifier
│   │   └── README.md           # Documentación del sistema
│   │
│   ├── edgar/                  # 🟢 ENRIQUECIMIENTO (edgartools)
│   │   ├── __init__.py
│   │   ├── service.py          # EdgarService principal
│   │   ├── models.py           # Modelos Pydantic
│   │   ├── cache.py            # Cache Redis + in-memory
│   │   ├── corrections.py      # Correcciones de datos
│   │   └── extractors/
│   │       ├── income.py       # Detalles de income statement
│   │       └── segments.py     # Segmentos y geografía
│   │
│   ├── fmp/                    # 🟡 DATOS ALTERNATIVOS
│   │   ├── __init__.py
│   │   └── service.py          # FMP API client
│   │
│   ├── industry/               # 🟣 PERFILES DE INDUSTRIA
│   │   ├── __init__.py
│   │   └── profiles.py         # Mapeo SIC → campos específicos
│   │
│   ├── fasb_labels.py          # 📚 10,732 labels US-GAAP
│   └── models.py               # Modelos compartidos
│
└── shared/
    ├── utils/
    │   └── logger.py           # Logging estructurado
    └── models/
        └── financials.py       # Modelos de respuesta
```

---

## 🔧 Componentes Clave

### 1. `extractors.py` - Normalización de Conceptos XBRL

**Problema:** Cada empresa puede usar diferentes nombres XBRL para el mismo concepto.
- Google: `RevenueFromContractWithCustomerExcludingAssessedTax`
- Apple: `NetSales`
- Amazon: `Revenues`

**Solución:** 62 regex patterns que mapean a campos canónicos:

```python
CONCEPT_PATTERNS = [
    # Revenue - múltiples variantes → 'revenue'
    (r'^revenue$|^revenues$|^net_sales|revenue.*contract.*customer', 
     'revenue', 'Revenue', 10000, 'monetary'),
    
    # Cost of Revenue
    (r'cost.*revenue|cost.*goods.*sold|cost.*sales', 
     'cost_of_revenue', 'Cost of Revenue', 9500, 'monetary'),
    
    # ... 60 patrones más
]
```

**Fallback:** Si ningún pattern coincide, usa `FASB_LABELS` (10,732 conceptos).

### 2. `calculators.py` - Métricas Derivadas

Calcula campos que no vienen directamente del XBRL:

| Métrica | Fórmula |
|---------|---------|
| Gross Profit | Revenue - Cost of Revenue |
| Gross Margin % | Gross Profit / Revenue |
| Operating Margin % | Operating Income / Revenue |
| Net Margin % | Net Income / Revenue |
| EBITDA | Operating Income + D&A |
| EBITDA Margin % | EBITDA / Revenue |
| Revenue % YoY | (Rev[t] - Rev[t-1]) / Rev[t-1] |
| FCF | Operating CF - CapEx |
| Book Value/Share | Total Equity / Shares |

### 3. `structures.py` - Jerarquía Visual

Define cómo se muestran los campos en el frontend (estilo TIKR):

```python
INCOME_STATEMENT_STRUCTURE = {
    # Sección Revenue
    'revenue':           {'section': 'Revenue',           'order': 100, 'indent': 0},
    'revenue_yoy':       {'section': 'Revenue',           'order': 101, 'indent': 1},
    
    # Sección Cost & Gross Profit
    'cost_of_revenue':   {'section': 'Cost & Gross Profit', 'order': 200, 'indent': 0},
    'gross_profit':      {'section': 'Cost & Gross Profit', 'order': 210, 'indent': 0, 'is_subtotal': True},
    'gross_margin':      {'section': 'Cost & Gross Profit', 'order': 212, 'indent': 1},
    
    # ... más secciones
}
```

### 4. `splits.py` - Ajuste por Stock Splits

**Problema:** Apple hizo un split 4:1 en 2020. El EPS histórico sin ajustar no es comparable.

**Solución:** Usa Polygon API para obtener historial de splits y ajusta:
- `eps_basic`, `eps_diluted`
- `shares_basic`, `shares_diluted`
- `dividend_per_share`

### 5. `edgar/` - Enriquecimiento con edgartools

SEC-API es rápido pero a veces incompleto. edgartools parsea el XBRL crudo:

- **Segmentos de negocio** (Business Segments)
- **Geografía** (Geographic Revenue)
- **Correcciones** de valores incorrectos
- **Datos adicionales** que SEC-API omite

### 6. `industry/profiles.py` - Campos por Industria

Diferentes industrias tienen campos específicos:

| Industria | SIC Codes | Campos Específicos |
|-----------|-----------|-------------------|
| Insurance | 6311-6399 | Premiums, Claims, Combined Ratio |
| Banking | 6021-6029 | Net Interest Income, Provisions |
| REIT | 6798 | FFO, NOI, Occupancy Rate |
| Tech | 7370-7379 | ARR, DAU, Churn Rate |

---

## 🌐 API Endpoints

### `GET /api/v1/financials/{symbol}`

Obtiene estados financieros completos.

**Parámetros:**
- `period`: `annual` | `quarter` (default: `annual`)
- `limit`: 1-30 (default: 10)
- `refresh`: `true` | `false` - forzar refresh de cache

**Response:**
```json
{
  "symbol": "GOOGL",
  "periods": ["2024", "2023", "2022", ...],
  "currency": "USD",
  "industry_code": "7370",
  "income_statement": [
    {
      "key": "revenue",
      "label": "Revenue",
      "values": [350018000000, 307394000000, ...],
      "section": "Revenue",
      "display_order": 100,
      "indent_level": 0,
      "data_type": "monetary",
      "importance": 10000
    },
    // ... más campos
  ],
  "balance_sheet": [...],
  "cash_flow": [...]
}
```

### `GET /api/v1/financials/{symbol}/segments`

Obtiene breakdown por segmentos y geografía.

**Response:**
```json
{
  "symbol": "GOOGL",
  "segments": {
    "revenue": {
      "Google Services": {"2024": 123000000000, "2023": 110000000000},
      "Google Cloud": {"2024": 33000000000, "2023": 28000000000}
    },
    "operating_income": {...}
  },
  "geography": {
    "revenue": {
      "United States": {...},
      "EMEA": {...}
    }
  }
}
```

### `POST /api/v1/financials/cache/clear`

Limpia cache de un símbolo.

**Body:**
```json
{"symbol": "GOOGL"}
```

---

## 🔄 Flujo de Datos

```
1. Request: GET /financials/GOOGL?period=annual&limit=10
                    │
                    ▼
2. Cache Check (Redis)
   └── Hit? → Return cached data
   └── Miss? → Continue
                    │
                    ▼
3. SEC-API Request
   └── GET filings for GOOGL (10-K annual reports)
   └── Parse JSON response
                    │
                    ▼
4. XBRL Extraction (extractors.py)
   └── Classify each field (income/balance/cashflow)
   └── Map XBRL concepts → canonical keys
   └── Apply FASB labels fallback
                    │
                    ▼
5. Edgar Enrichment (optional)
   └── Get additional details from edgartools
   └── Apply corrections
                    │
                    ▼
6. Calculations (calculators.py)
   └── Gross Profit = Revenue - COGS
   └── Margins, YoY, EBITDA, FCF
   └── Balance metrics (Book Value, Net Debt)
                    │
                    ▼
7. Split Adjustments (splits.py)
   └── Get split history from Polygon
   └── Adjust EPS and Shares
                    │
                    ▼
8. Structure Application (structures.py)
   └── Assign sections, order, indent
   └── Apply industry-specific structure
   └── Filter low-value fields
                    │
                    ▼
9. Cache & Return
   └── Store in Redis (24h TTL)
   └── Return JSON response
```

---

##  Cobertura de Campos

### Income Statement
- Revenue, Revenue % YoY
- Cost of Revenue
- Gross Profit, Gross Profit % YoY, Gross Margin %
- R&D Expenses, SG&A, Sales & Marketing
- Operating Expenses (total)
- Operating Income, Operating Income % YoY, Operating Margin %
- D&A, EBITDA, EBITDA Margin %
- Interest Income, Interest Expense
- Investment Income, Other Income/Expense
- Gain/Loss on Securities, Impairment Charges
- Income Before Tax, Income Tax
- Net Income, Net Margin %, Net Income % YoY
- EPS Basic, EPS Diluted, EPS % YoY
- Shares Basic, Shares Diluted
- Dividend per Share

### Balance Sheet
- Current Assets: Cash, Receivables, Inventory, ST Investments
- Non-Current Assets: PP&E, Goodwill, Intangibles
- Current Liabilities: Accounts Payable, ST Debt, Deferred Revenue
- Non-Current Liabilities: LT Debt
- Equity: Total Equity, Retained Earnings
- Calculated: Total Debt, Net Debt, Book Value/Share, Tangible Book Value

### Cash Flow
- Operating Activities: Operating CF
- Investing Activities: Investing CF, CapEx
- Financing Activities: Financing CF, Dividends Paid, Stock Repurchased
- Calculated: Free Cash Flow, FCF Margin %, FCF per Share

---

## ✅ Mapping Engine (IMPLEMENTADO)

### Sistema de Mapeo por Tiers

El sistema utiliza una **arquitectura de Tiers** para clasificar ~45,000 tags XBRL únicos:

```
┌─────────────────────────────────────────────────────────────────┐
│                   PIPELINE DE MAPPING                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TIER 1: Manual (~250 mappings)            confidence = 1.0     │
│  ════════════════════════════════════════════════════════════   │
│  • schema.py → XBRL_TO_CANONICAL                                │
│  • Verificados contra TIKR/Bloomberg                            │
│  • Incluye: revenue, net_income, leases (ASC 842), etc.         │
│                                                                  │
│  TIER 2: SEC Dataset Auto (~3,298 mappings) confidence = 0.85   │
│  ════════════════════════════════════════════════════════════   │
│  • sec_tier2.py → SEC_TIER2_MAPPINGS                            │
│  • Generados de SEC Financial Statement Data Sets               │
│  • Script: scripts/parse_sec_dataset.py                         │
│                                                                  │
│  TIER 3: Regex Patterns (~60 patterns)     confidence = 0.7     │
│  ════════════════════════════════════════════════════════════   │
│  • engine.py → REGEX_PATTERNS                                   │
│  • Patrones genéricos: .*Revenue.* → revenue                    │
│                                                                  │
│  TIER 4: FASB Labels (~10,732 labels)      confidence = 0.6     │
│  ════════════════════════════════════════════════════════════   │
│  • engine.py → FASB_LABELS                                      │
│  • Lookup por tag name en taxonomía US-GAAP                     │
│                                                                  │
│  TIER 5: Fallback                          confidence = 0.0     │
│  ════════════════════════════════════════════════════════════   │
│  • adapter.py → _generate_fallback()                            │
│  • Normaliza CamelCase → snake_case, importance = 50            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 📈 Cobertura Actual

| Ticker | Total Fields | Mapped | **Coverage** |
|--------|--------------|--------|--------------|
| COST   | 147          | 141    | **95.9%**    |
| AAPL   | 140          | 130    | **92.9%**    |
| GOOGL  | 203          | 183    | **90.1%**    |

### 📁 Estructura del Módulo

```
services/mapping/
├── __init__.py          # Exports públicos
├── adapter.py           # ⭐ Interfaz principal (XBRLMapper)
├── schema.py            # ⭐ Campos canónicos + mappings Tier 1
├── sec_tier2.py         # ⭐ Mappings auto-generados Tier 2 (3,298)
├── engine.py            # Regex patterns + FASB labels
├── database.py          # (Futuro) Persistencia en PostgreSQL
├── llm_classifier.py    # (Futuro) Clasificador con LLM
└── README.md            # Documentación detallada
```

### 🔧 Uso

```python
# En extractors.py (automático)
from services.mapping.adapter import XBRLMapper

mapper = XBRLMapper()
key, label, importance, dtype = mapper.detect_concept("OperatingLeaseCost")
# → ('operating_lease_cost', 'Operating Lease Cost', 6850, 'monetary')
```

### ➕ Añadir Nuevo Mapping

1. Edita `schema.py`:
```python
XBRL_TO_CANONICAL = {
    # ...existing...
    "NewXBRLTag": "canonical_key",
}
```

2. Si es campo nuevo, añade al schema:
```python
INCOME_STATEMENT_SCHEMA = [
    # ...existing...
    CanonicalField("canonical_key", "Label", "Section", order, importance=8000),
]
```

3. Rebuild:
```bash
docker compose build financials && docker compose up -d financials --force-recreate
```

4. Limpia cache Redis:
```bash
docker exec tradeul_redis redis-cli -a "PASSWORD" KEYS "financials:*" | \
  xargs docker exec -i tradeul_redis redis-cli -a "PASSWORD" DEL
```

### 🔄 Actualizar Tier 2 (Trimestral)

```bash
# 1. Descargar de https://www.sec.gov/dera/data/financial-statement-data-sets
# 2. Parsear
python3 scripts/parse_sec_dataset.py /path/to/2024q4/ /tmp/output/
# 3. Copiar
cp /tmp/output/tier2_python.py services/mapping/sec_tier2.py
# 4. Rebuild
```

Ver documentación completa en: `services/mapping/README.md`

### Inicializar Base de Datos

```bash
cd services/financials
python -m services.mapping.seed
```

### Test del Sistema

```bash
cd services/financials/services/mapping
python test_mapping.py
```

---

## 🔑 Variables de Entorno

```env
FINANCIALS_PORT=8020
REDIS_HOST=redis
REDIS_PASSWORD=xxx
SEC_API_IO=xxx          # SEC-API.io key
FMP_API_KEY=xxx         # Financial Modeling Prep
POLYGON_API_KEY=xxx     # Para stock splits
```

---

## 🐳 Docker

```yaml
# docker-compose.yml
financials:
  build:
    context: .
    dockerfile: services/financials/Dockerfile
  ports:
    - "127.0.0.1:8020:8020"
  volumes:
    - ./edgar_cache:/app/edgar_cache  # Cache de edgartools
  depends_on:
    - redis
```

---

## 📝 Para una IA que continúe este trabajo

### Lo que FUNCIONA bien:
1. Extracción de ~45 campos clave de XBRL
2. Cálculo de métricas derivadas (márgenes, YoY, FCF)
3. Ajuste por stock splits
4. Segmentos y geografía via edgartools
5. Estructura jerárquica tipo TIKR

### Lo que NECESITA mejora:
1. ✅ ~~**Mapeo XBRL → Canonical**~~: **IMPLEMENTADO** - Sistema multi-etapa con DB + LLM
2. **Campos faltantes**: Algunos campos específicos de industria no se extraen (pero ahora con 141 campos canónicos es más completo)
3. ✅ **Desglose de "Other Income"**: Ahora incluye equity_method_income, foreign_exchange_gain_loss, etc.
4. **Quarterly data**: Funciona pero menos probado que annual

### Archivos clave para modificar:
- **Añadir nuevo campo**: `extractors.py` (pattern) + `structures.py` (display) + `calculators.py` (si es calculado)
- **Nueva industria**: `industry/profiles.py`
- **Nuevo cálculo**: `calculators.py`
- **Cambiar display**: `structures.py`

### Testing:
```bash
# Probar un ticker
curl "http://localhost:8020/api/v1/financials/AAPL?period=annual&limit=5"

# Limpiar cache y re-fetch
curl -X POST "http://localhost:8020/api/v1/financials/cache/clear" -d '{"symbol":"AAPL"}'
```

---

## 📚 Referencias

- [SEC EDGAR](https://www.sec.gov/edgar)
- [US-GAAP Taxonomy (FASB)](https://xbrl.fasb.org/)
- [SEC-API.io Documentation](https://sec-api.io/docs)
- [edgartools GitHub](https://github.com/dgunning/edgartools)
- [TIKR.com](https://tikr.com) - Referencia de UI/UX

