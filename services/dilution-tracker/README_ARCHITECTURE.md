#  Dilution Tracker Service - Documentación Técnica Completa

> Servicio de análisis de dilución de acciones basado en SEC EDGAR con extracción por IA

## 📑 Tabla de Contenidos

- [Arquitectura General](#-arquitectura-general)
- [Modelos de Datos](#-modelos-de-datos)
- [Servicio Principal](#-servicio-principal-sec_dilution_servicepy)
- [Endpoints API](#-endpoints-api)
- [Sistema de Risk Ratings](#-sistema-de-risk-ratings)
- [Extractores de IA](#-extractores-de-ia)
- [Full-Text Search](#-full-text-search)
- [Cálculo de Dilución](#-cálculo-de-dilución-potencial)
- [Deduplicación Inteligente](#-deduplicación-inteligente)
- [Baby Shelf e IB6](#-baby-shelf-e-ib6)
- [Fuentes de Datos](#-fuentes-de-datos)
- [Flujo Completo](#-flujo-completo-de-una-request)
- [Configuración](#-configuración)

---

## 🏗️ Arquitectura General

El servicio de **dilution-tracker** es un microservicio FastAPI diseñado para analizar la dilución potencial de acciones de empresas cotizadas en bolsa. Es una implementación avanzada inspirada en **DilutionTracker.com** con capacidades de IA.

### Estructura del Proyecto

```
services/dilution-tracker/
├── main.py                           # Punto de entrada FastAPI
├── http_clients.py                   # Clientes HTTP compartidos
├── requirements.txt                  # Dependencias Python
├── Dockerfile                        # Contenedor Docker
│
├── routers/                          # Endpoints API
│   ├── sec_dilution_router.py        # Endpoints principales de dilución
│   ├── websocket_router.py           # WebSockets para real-time
│   ├── analysis_router.py            # Endpoints de análisis
│   └── async_analysis_router.py      # Análisis asíncrono
│
├── services/
│   ├── core/
│   │   └── sec_dilution_service.py   # Servicio central (~2,700 líneas)
│   ├── gemini/
│   │   └── gemini_extractor.py       # Extractor con Gemini AI
│   ├── grok/
│   │   ├── grok_extractor.py         # Extractor con Grok AI (fallback)
│   │   ├── grok_pool.py              # Pool de conexiones Grok
│   │   ├── grok_normalizers.py       # Normalización de datos
│   │   └── chunk_processor.py        # Procesamiento de chunks
│   ├── analysis/
│   │   ├── deduplication_service.py  # Deduplicación de instrumentos
│   │   ├── preliminary_analyzer.py   # Análisis preliminar con IA
│   │   ├── spac_detector.py          # Detector de SPACs
│   │   └── instrument_linker.py      # Vinculación de instrumentos
│   ├── sec/
│   │   ├── sec_filing_fetcher.py     # Descarga de filings SEC
│   │   ├── sec_fulltext_search.py    # Búsqueda full-text SEC-API
│   │   ├── sec_cash_history.py       # Historial de cash (XBRL)
│   │   ├── sec_edgar_shares.py       # Shares outstanding
│   │   └── sec_13f_holders.py        # Holders institucionales
│   ├── data/
│   │   ├── shares_data_service.py    # Servicio de datos de acciones
│   │   ├── enhanced_data_fetcher.py  # Fetcher mejorado
│   │   └── data_aggregator.py        # Agregador de datos
│   ├── market/
│   │   ├── market_data_calculator.py # Cálculos de mercado
│   │   ├── cash_runway_service.py    # Cash runway
│   │   └── capital_raise_extractor.py# Extractor de capital raises
│   ├── cache/
│   │   └── cache_service.py          # Servicio de caché
│   └── extraction/
│       └── html_section_extractor.py # Extractor de secciones HTML
│
├── models/
│   ├── sec_dilution_models.py        # Modelos Pydantic principales
│   ├── dilution_models.py            # Modelos adicionales
│   ├── filing_models.py              # Modelos de filings
│   └── financial_models.py           # Modelos financieros
│
├── calculators/
│   ├── dilution_tracker_risk_scorer.py # Calculador de ratings (5 ratings)
│   ├── dilution_calculator.py        # Cálculos de dilución
│   ├── cash_runway.py                # Cálculo de cash runway
│   └── risk_scorer.py                # Scoring de riesgo
│
├── repositories/
│   └── sec_dilution_repository.py    # Repositorio PostgreSQL
│
├── prompts/
│   └── preliminary_analysis_prompt.py # Prompts para análisis IA
│
├── jobs/
│   ├── scraping_jobs.py              # Jobs de scraping
│   ├── sync_tier1_job.py             # Sincronización Tier 1
│   └── tier_rebalance_job.py         # Rebalanceo de tiers
│
├── workers/
│   └── arq_worker.py                 # Worker ARQ para jobs
│
└── strategies/
    ├── search_tracker.py             # Tracking de búsquedas
    └── tier_manager.py               # Gestión de tiers
```

---

## 📋 Modelos de Datos

### 8 Tipos de Instrumentos Dilutivos

El sistema modela 8 tipos de instrumentos que pueden causar dilución:

#### 1. WarrantModel - Warrants

```python
class WarrantModel(BaseModel):
    ticker: str
    issue_date: Optional[date]
    expiration_date: Optional[date]
    outstanding: Optional[int]                    # Warrants vigentes
    exercise_price: Optional[Decimal]             # Precio de ejercicio
    potential_new_shares: Optional[int]           # Acciones potenciales
    
    # Estado y clasificación
    status: Optional[str]                         # Active | Exercised | Replaced | Historical_Summary
    is_summary_row: Optional[bool]                # Si es fila resumen de 10-Q
    exclude_from_dilution: Optional[bool]         # Excluir del cálculo
    
    # Ajuste por splits
    split_adjusted: Optional[bool]
    split_factor: Optional[float]
    original_exercise_price: Optional[Decimal]
    original_outstanding: Optional[int]
    
    # Tracking de ejercicios (de 10-Q/10-K)
    total_issued: Optional[int]
    exercised: Optional[int]
    expired: Optional[int]
    remaining: Optional[int]
    
    # Campos adicionales estilo DilutionTracker
    series_name: Optional[str]                    # "August 2025 Warrants"
    known_owners: Optional[str]                   # "3i, Akita, CVI"
    underwriter_agent: Optional[str]
    price_protection: Optional[str]               # "Customary Anti-Dilution" | "Reset" | "Full Ratchet"
    pp_clause: Optional[str]                      # Texto literal de la cláusula
    exercisable_date: Optional[date]
    is_prefunded: Optional[bool]
    has_cashless_exercise: Optional[bool]
```

#### 2. ATMOfferingModel - At-The-Market Offerings

```python
class ATMOfferingModel(BaseModel):
    ticker: str
    series_name: Optional[str]                    # "January 2023 Cantor ATM"
    total_capacity: Optional[Decimal]             # Capacidad total en USD
    remaining_capacity: Optional[Decimal]         # Capacidad restante
    placement_agent: Optional[str]                # "B. Riley Securities"
    status: Optional[str]                         # Active | Terminated | Replaced
    agreement_start_date: Optional[date]
    filing_date: Optional[date]
    filing_url: Optional[str]
    potential_shares_at_current_price: Optional[int]
    
    # Baby Shelf
    atm_limited_by_baby_shelf: Optional[bool]
    remaining_capacity_without_restriction: Optional[Decimal]
```

#### 3. ShelfRegistrationModel - S-3/S-1/F-3 Registrations

```python
class ShelfRegistrationModel(BaseModel):
    ticker: str
    series_name: Optional[str]                    # "April 2022 Shelf"
    total_capacity: Optional[Decimal]
    remaining_capacity: Optional[Decimal]
    current_raisable_amount: Optional[Decimal]    # Limitado por Baby Shelf
    total_amount_raised: Optional[Decimal]
    total_amount_raised_last_12mo: Optional[Decimal]
    
    # Tipo de shelf
    is_baby_shelf: bool = False                   # Float < $75M
    baby_shelf_restriction: Optional[bool]
    security_type: Optional[str]                  # "common_stock" | "preferred_stock" | "mixed"
    registration_statement: Optional[str]         # "S-3" | "S-1" | "F-3" | "S-11"
    
    # Fechas
    filing_date: Optional[date]
    effect_date: Optional[date]
    expiration_date: Optional[date]               # Típicamente 3 años
    
    # Cálculos Baby Shelf
    price_to_exceed_baby_shelf: Optional[Decimal]
    ib6_float_value: Optional[Decimal]
    highest_60_day_close: Optional[Decimal]
    outstanding_shares_calc: Optional[int]
    float_shares_calc: Optional[int]
    
    last_banker: Optional[str]
    status: Optional[str]                         # Active | Expired | Replaced
```

#### 4. CompletedOfferingModel - Ofertas Completadas

```python
class CompletedOfferingModel(BaseModel):
    ticker: str
    offering_type: Optional[str]                  # "Direct Offering" | "PIPE" | "Registered Direct"
    shares_issued: Optional[int]
    price_per_share: Optional[Decimal]
    amount_raised: Optional[Decimal]
    offering_date: Optional[date]
    filing_url: Optional[str]
    notes: Optional[str]
```

#### 5. S1OfferingModel - Ofertas S-1 Pendientes

```python
class S1OfferingModel(BaseModel):
    ticker: str
    anticipated_deal_size: Optional[Decimal]
    final_deal_size: Optional[Decimal]
    final_pricing: Optional[Decimal]
    final_shares_offered: Optional[int]
    warrant_coverage: Optional[Decimal]
    final_warrant_coverage: Optional[Decimal]
    exercise_price: Optional[Decimal]
    underwriter_agent: Optional[str]
    s1_filing_date: Optional[date]
    status: Optional[str]                         # "Priced" | "Registered" | "Pending"
    filing_url: Optional[str]
```

#### 6. ConvertibleNoteModel - Notas Convertibles

```python
class ConvertibleNoteModel(BaseModel):
    ticker: str
    series_name: Optional[str]                    # "November 2020 1.25% Convertible Notes Due 2025"
    total_principal_amount: Optional[Decimal]
    remaining_principal_amount: Optional[Decimal]
    conversion_price: Optional[Decimal]           # CRÍTICO
    original_conversion_price: Optional[Decimal]
    conversion_ratio: Optional[Decimal]           # Shares per $1000
    total_shares_when_converted: Optional[int]
    remaining_shares_when_converted: Optional[int]
    interest_rate: Optional[Decimal]              # ej: 1.25 para 1.25%
    
    # Fechas
    issue_date: Optional[date]
    convertible_date: Optional[date]
    maturity_date: Optional[date]
    
    # Registro y protección
    is_registered: Optional[bool]
    registration_type: Optional[str]              # "EDGAR" | "Not Registered"
    known_owners: Optional[str]
    underwriter_agent: Optional[str]
    
    # Protección de precio (CRÍTICO)
    price_protection: Optional[str]               # "Variable Rate" | "Full Ratchet" | "Reset"
    pp_clause: Optional[str]                      # Texto VERBATIM del contrato
    
    # Indicadores de toxicidad
    variable_rate_adjustment: Optional[bool]      # Death spiral
    floor_price: Optional[Decimal]
    is_toxic: Optional[bool]                      # Financiamiento tóxico
```

#### 7. ConvertiblePreferredModel - Preferentes Convertibles

```python
class ConvertiblePreferredModel(BaseModel):
    ticker: str
    series_name: Optional[str]                    # "October 2025 Series B Convertible Preferred"
    series: Optional[str]                         # "A" | "B" | "C"
    total_dollar_amount_issued: Optional[Decimal]
    remaining_dollar_amount: Optional[Decimal]
    conversion_price: Optional[Decimal]
    total_shares_when_converted: Optional[int]
    remaining_shares_when_converted: Optional[int]
    
    # Fechas
    issue_date: Optional[date]
    convertible_date: Optional[date]
    maturity_date: Optional[date]
    
    # Registro y protección
    is_registered: Optional[bool]
    known_owners: Optional[str]
    price_protection: Optional[str]
    pp_clause: Optional[str]
    floor_price: Optional[Decimal]
    variable_rate_adjustment: Optional[bool]
    is_toxic: Optional[bool]
```

#### 8. EquityLineModel - Equity Lines (ELOC)

```python
class EquityLineModel(BaseModel):
    ticker: str
    series_name: Optional[str]                    # "September 2025 White Lion SPA"
    total_capacity: Optional[Decimal]
    remaining_capacity: Optional[Decimal]
    counterparty: Optional[str]                   # "Lincoln Park" | "YA II" | "White Lion"
    agreement_start_date: Optional[date]
    agreement_end_date: Optional[date]
    filing_url: Optional[str]
    is_registered: Optional[bool]
```

### SECDilutionProfile - Perfil Completo

```python
class SECDilutionProfile(BaseModel):
    ticker: str
    company_name: Optional[str]
    cik: Optional[str]
    
    # Datos de mercado
    current_price: Optional[Decimal]
    shares_outstanding: Optional[int]
    float_shares: Optional[int]
    
    # Instrumentos dilutivos
    warrants: List[WarrantModel] = []
    atm_offerings: List[ATMOfferingModel] = []
    shelf_registrations: List[ShelfRegistrationModel] = []
    completed_offerings: List[CompletedOfferingModel] = []
    s1_offerings: List[S1OfferingModel] = []
    convertible_notes: List[ConvertibleNoteModel] = []
    convertible_preferred: List[ConvertiblePreferredModel] = []
    equity_lines: List[EquityLineModel] = []
    
    # Historial
    historical_shares: List[dict] = []
    
    # Metadata
    metadata: DilutionProfileMetadata
    
    # Métodos de análisis
    def calculate_potential_dilution(self) -> dict
    def calculate_warrant_analysis(self) -> dict
    def calculate_equity_line_shares(self) -> dict
```

---

## ⚙️ Servicio Principal (`sec_dilution_service.py`)

### Pipeline de Scraping "Exhibits First v2"

El servicio utiliza una arquitectura de pipeline en múltiples etapas:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE EXTRACCIÓN                        │
├─────────────────────────────────────────────────────────────────┤
│ 0. FILE NUMBER GROUPING (Anti-Context Pollution)                 │
│    ├─ Agrupar filings por SEC File Number (333-XXXXXX)          │
│    ├─ S-1 + S-1/A + 424B4 = misma cadena → solo 424B4           │
│    └─ Elimina duplicados ANTES de enviar al LLM                 │
├─────────────────────────────────────────────────────────────────┤
│ 1. DISCOVERY                                                     │
│    ├─ Full-Text Search (keywords dilutivos)                     │
│    ├─ SEC-API.io Query API (todos los filings desde 2010)       │
│    └─ Fetch 424B filings (prospectus supplements)               │
├─────────────────────────────────────────────────────────────────┤
│ 2. DOWNLOAD                                                      │
│    ├─ Descargar filings principales (HTML)                      │
│    └─ Descargar exhibits (ex4-*, ex10-*, ex99-*)                │
├─────────────────────────────────────────────────────────────────┤
│ 3. EXTRACTION (Gemini Flash)                                     │
│    └─ Extraer de exhibits (contratos legales = datos exactos)   │
├─────────────────────────────────────────────────────────────────┤
│ 4. PRE-MERGE                                                     │
│    └─ Combinar notas parciales del mismo mes/año                │
├─────────────────────────────────────────────────────────────────┤
│ 5. CONSOLIDATION (Gemini Pro)                                    │
│    └─ Limpiar, deduplicar, validar con LLM inteligente          │
├─────────────────────────────────────────────────────────────────┤
│ 6. VALIDATION                                                    │
│    ├─ Filtrar notas sin conversion_price                        │
│    ├─ Filtrar warrants sin exercise_price                       │
│    └─ Filtrar shelfs de resale (no dilutivos)                   │
├─────────────────────────────────────────────────────────────────┤
│ 7. SPLIT ADJUSTMENT (Polygon.io)                                 │
│    ├─ Usar historical_adjustment_factor de Polygon (cumulative) │
│    ├─ Solo primer split después de issue_date (factor ya cumul.)│
│    └─ Skip warrants para comprar NOTAS (no shares)              │
├─────────────────────────────────────────────────────────────────┤
│ 8. BABY SHELF CALCULATION                                        │
│    ├─ Calcular IB6 Float Value = Float × Highest60DayClose × ⅓  │
│    └─ Determinar current_raisable_amount                        │
├─────────────────────────────────────────────────────────────────┤
│ 9. BUILD PROFILE                                                 │
│    └─ Construir SECDilutionProfile final                        │
└─────────────────────────────────────────────────────────────────┘
```

### Sistema de Caché Multinivel

```
┌──────────────────┐
│ Request          │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐    HIT (~10ms)
│ Redis (L1)       │─────────────────► Return cached
│ TTL: 24 horas    │
└────────┬─────────┘
         │ MISS
         ▼
┌──────────────────┐    HIT (~50ms)
│ PostgreSQL (L2)  │─────────────────► Save to Redis → Return
└────────┬─────────┘
         │ MISS
         ▼
┌──────────────────┐
│ SEC Scraping     │    (10-60 segundos)
│ + AI Extraction  │─────────────────► Save to DB + Redis → Return
└──────────────────┘
```

### Checkpoints para Debugging

El servicio guarda estados intermedios en Redis para debugging:

```python
# Tiers de checkpoints
checkpoint:{ticker}:discovery        # Filings y exhibits encontrados
checkpoint:{ticker}:extraction_raw   # Datos raw de Gemini Flash
checkpoint:{ticker}:pre_merge        # Después de pre-merge
checkpoint:{ticker}:consolidated     # Después de Gemini Pro
checkpoint:{ticker}:validated        # Después de validación
checkpoint:{ticker}:split_adjusted   # Después de ajuste por splits

# Recuperar checkpoint
data = await service.get_checkpoint("MULN", "extraction_raw")

# Listar checkpoints disponibles
tiers = await service.list_checkpoints("MULN")
```

### Métodos Principales

```python
class SECDilutionService:
    async def get_dilution_profile(ticker: str, force_refresh: bool = False) -> SECDilutionProfile:
        """Obtener perfil completo (con caché multinivel)"""
        
    async def get_from_cache_only(ticker: str) -> Optional[SECDilutionProfile]:
        """Solo consultar caché (non-blocking)"""
        
    async def invalidate_cache(ticker: str) -> bool:
        """Invalidar caché Redis + PostgreSQL"""
        
    async def get_shares_history(ticker: str) -> Dict:
        """Historial de shares outstanding desde SEC EDGAR XBRL"""
        
    async def get_cash_data(ticker: str) -> Dict:
        """Cash position y runway"""
        
    async def get_enhanced_dilution_profile(ticker: str) -> Dict:
        """Perfil + shares + cash + risk flags"""
```

---

## 🔌 Endpoints API

### Endpoints Principales

| Endpoint | Método | Descripción | Latencia |
|----------|--------|-------------|----------|
| `/{ticker}/check` | GET | Verifica caché (non-blocking) | ~10-50ms |
| `/{ticker}/profile` | GET | Perfil completo con risk ratings | ~150ms cached / 10-60s fresh |
| `/{ticker}/refresh` | POST | Forzar re-scraping | 10-60s |
| `/{ticker}/warrants` | GET | Solo warrants | ~150ms |
| `/{ticker}/atm-offerings` | GET | Solo ATMs | ~150ms |
| `/{ticker}/shelf-registrations` | GET | Solo shelfs | ~150ms |
| `/{ticker}/completed-offerings` | GET | Ofertas históricas | ~150ms |
| `/{ticker}/filings` | GET | Filings procesados (paginado) | ~200ms |
| `/{ticker}/dilution-analysis` | GET | Solo análisis de dilución | ~150ms |

### Endpoints Enhanced

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/{ticker}/shares-history` | GET | Historial de acciones (SEC XBRL) |
| `/{ticker}/cash-position` | GET | Cash + runway (SEC-API XBRL) |
| `/{ticker}/risk-ratings` | GET | 5 ratings de DilutionTracker |
| `/{ticker}/enhanced-profile` | GET | Perfil + shares + cash + flags |
| `/{ticker}/cash-runway-enhanced` | GET | Metodología DilutionTracker |

### Endpoints de Análisis Preliminar (IA)

| Endpoint | Método | Descripción | Tiempo |
|----------|--------|-------------|--------|
| `/{ticker}/preliminary/stream` | GET | Streaming SSE (terminal real-time) | 15-45s |
| `/{ticker}/preliminary` | GET | JSON estructurado | ~45s |
| `/{ticker}/preliminary/quick` | GET | Snapshot rápido | <5s |

### Endpoints de Jobs (Background)

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/{ticker}/jobs/scrape` | POST | Encolar job de scraping |
| `/{ticker}/jobs/status` | GET | Estado del job |
| `/jobs/stats` | GET | Estadísticas de la cola |

### Ejemplos de Uso

```bash
# Verificar caché (rápido)
curl "http://localhost:8000/api/sec-dilution/MULN/check"

# Obtener perfil completo
curl "http://localhost:8000/api/sec-dilution/MULN/profile"

# Forzar actualización
curl -X POST "http://localhost:8000/api/sec-dilution/MULN/refresh"

# Análisis preliminar con streaming
curl "http://localhost:8000/api/sec-dilution/MULN/preliminary/stream"

# Risk ratings
curl "http://localhost:8000/api/sec-dilution/MULN/risk-ratings"
```

---

##  Sistema de Risk Ratings

### 5 Ratings Estilo DilutionTracker.com

El sistema calcula 5 ratings basados en la metodología de DilutionTracker.com:

```
┌───────────────────────────────────────────────────────────────────┐
│                    DILUTION RISK RATINGS                           │
├───────────────────────────────────────────────────────────────────┤
│ 1. OVERALL RISK         (Weighted average de los 4 sub-ratings)   │
│    Weights: Offering(30%) + Overhead(25%) + Historical(15%) + Cash(30%)
│    High = Short bias, Low = Long bias                              │
├───────────────────────────────────────────────────────────────────┤
│ 2. OFFERING ABILITY     (Capacidad de emitir acciones)            │
│    High:   >$20M shelf capacity activo                             │
│    Medium: $1M-$20M shelf capacity                                 │
│    Low:    <$1M o sin shelf activo                                 │
├───────────────────────────────────────────────────────────────────┤
│ 3. OVERHEAD SUPPLY      (Dilución potencial existente)            │
│    High:   >50% dilución vs O/S actual                             │
│    Medium: 20%-50% dilución                                        │
│    Low:    <20% dilución                                           │
│    Incluye: Warrants + ATM + Convertibles + Equity Lines           │
├───────────────────────────────────────────────────────────────────┤
│ 4. HISTORICAL           (Patrón histórico de dilución)            │
│    High:   >100% aumento O/S en 3 años                             │
│    Medium: 30%-100% aumento                                        │
│    Low:    <30% aumento                                            │
├───────────────────────────────────────────────────────────────────┤
│ 5. CASH NEED            (Necesidad de efectivo)                   │
│    High:   <6 meses de runway                                      │
│    Medium: 6-24 meses de runway                                    │
│    Low:    >24 meses o CF operativo positivo                       │
└───────────────────────────────────────────────────────────────────┘
```

### Implementación

```python
class DilutionTrackerRiskScorer:
    def calculate_all_ratings(
        self,
        # Offering Ability
        shelf_capacity_remaining: float,
        has_active_shelf: bool,
        has_pending_s1: bool,
        
        # Overhead Supply
        warrants_shares: int,
        atm_shares: int,
        convertible_shares: int,
        equity_line_shares: int,
        shares_outstanding: int,
        
        # Historical
        shares_outstanding_3yr_ago: int,
        shares_outstanding_current_sec: int,
        
        # Cash Need
        runway_months: float,
        has_positive_operating_cf: bool,
        
        current_price: float
    ) -> DilutionRiskRatings:
        """Calcula los 5 ratings"""
```

### Ejemplo de Respuesta

```json
{
    "overall_risk": "High",
    "offering_ability": "High",
    "overhead_supply": "Medium",
    "historical": "Low",
    "cash_need": "High",
    "scores": {
        "overall": 72,
        "offering_ability": 90,
        "overhead_supply": 45,
        "historical": 25,
        "cash_need": 85
    },
    "details": {
        "offering_ability": {
            "shelf_capacity_remaining": 50000000,
            "has_active_shelf": true,
            "has_pending_s1": false
        },
        "overhead_supply": {
            "warrants_shares": 10000000,
            "atm_shares": 5000000,
            "convertible_shares": 3000000,
            "dilution_pct": 45.2
        },
        "historical": {
            "shares_outstanding_current": 40000000,
            "shares_outstanding_3yr_ago": 35000000,
            "increase_pct": 14.3
        },
        "cash_need": {
            "runway_months": 4.5,
            "has_positive_operating_cf": false
        }
    }
}
```

---

## 🤖 Extractores de IA

### 1. Gemini Extractor (Fuente Primaria)

Usa **Gemini 2.5 Flash** para extraer datos de exhibits Y filings principales.

```python
class GeminiExtractor:
    model = "gemini-2.5-flash"  # Modelo estable con 1M tokens contexto
    
    async def extract_all(ticker: str, filings: List[Dict]) -> Dict:
        """
        1. Identificar exhibits relevantes (ex4-*, ex10-*, ex99-*)
        2. Procesar filings principales (6-K, 8-K, 424B, F-1, S-1, F-3, S-3)
        3. Subir a Gemini Files API
        4. Extraer con prompt unificado (8 tipos de instrumentos)
        5. Devolver instrumentos estructurados
        """
    
    async def consolidate_instruments(raw_instruments: Dict) -> Dict:
        """
        Consolidation Pass con Gemini 2.5 Flash:
        - Merge duplicates
        - Resolve conflicts
        - Filter garbage (conservatively)
        - Complete missing data
        """
```

**Filings Procesados por Gemini:**
```python
# Filings principales (además de exhibits)
GEMINI_FILING_TYPES = [
    '6-K', '8-K', '10-Q', '10-K',      # Reports
    '424B5', '424B4',                   # Prospectus
    'F-1', 'F-1/A', 'S-1', 'S-1/A',    # S-1 Offerings (IPO/follow-on)
    'F-3', 'F-3/A', 'S-3', 'S-3/A'     # Shelf/ATM registrations
]
```

**Campos Críticos Extraídos:**
- `conversion_price`, `exercise_price` - Precios de conversión/ejercicio
- `total_principal_amount` - Monto principal
- `pp_clause` - Cláusula de protección de precio (VERBATIM)
- `is_toxic` - Detecta death spiral financing
- `warrant_type` - "Common" | "Pre-Funded" | "Placement Agent" | "SPAC"
- `s1_offerings` - IPO/follow-on offerings pendientes o completados

**Patrones de Exhibits:**
```python
EXHIBIT_PATTERNS = {
    "convertible_note": [r"ex4[-_]?\d*\.htm", r"ex10[-_]?\d*\.htm"],
    "warrant": [r"ex4[-_]?\d*\.htm", r"ex10[-_]?\d*\.htm"],
    "general": [r"ex\d+[-_]?\d*\.htm"]
}
```

### 2. Grok Extractor (Fallback para Filings Grandes)

Se activa como **fallback** cuando:
- Gemini no tiene éxito con exhibits
- No hay exhibits disponibles
- Filings muy grandes (F-1 de 5MB+)

Arquitectura **Multi-Pass** para análisis completo:

```
Pass 2: S-3/S-1/F-3/F-1     → Shelf Registrations, ATM agreements, S-1 Offerings
Pass 3: 424B (PARALELO)      → ATM usage, Warrants, Completed offerings
Pass 4a: 10-Q                → Warrant exercises
Pass 4b: 10-Q                → ATM usage
Pass 5: S-8                  → Employee stock plans
Pass 6: 8-K/6-K              → Current reports
Pass 7: DEF 14A              → Proxy statements
```

```python
class GrokExtractor:
    async def extract_with_multipass_grok(
        ticker: str,
        company_name: str,
        filing_contents: List[Dict],
        parsed_tables: Optional[Dict]
    ) -> Dict:
        """
        Extracción en múltiples pasadas enfocadas.
        
        Usa Files API de Grok para documentos grandes.
        Pool de conexiones para parallelización.
        """
```

### 3. Preliminary Analyzer (Análisis Rápido)

Usa **Gemini 3 Flash + Google Search** para análisis instantáneo:

```python
class PreliminaryAnalyzer:
    model = "gemini-3-flash-preview"
    
    async def analyze_streaming(ticker: str) -> AsyncGenerator[str]:
        """Streaming SSE para terminal real-time (15-45s)"""
        
    async def analyze_json(ticker: str) -> Dict:
        """JSON estructurado completo (~45s)"""
        
    async def quick_lookup(ticker: str) -> Dict:
        """Snapshot en <5 segundos"""
```

**Formato de Output Streaming:**
```
[CONNECTING] Initializing Tradeul AI analysis for MULN...
[SCAN] Searching SEC EDGAR for dilution instruments...
[RISK] Dilution Risk Score: 8/10 (HIGH)
[WARRANTS] Found 3 active warrant series...
[ATM] Active ATM with $50M remaining capacity...
[CASH] Cash runway: 4.5 months (CRITICAL)
[FLAGS] 🚩 Variable rate convertible (toxic)
[VERDICT] HIGH DILUTION RISK - Short bias recommended
[STREAM_END]
```

---

## 📁 File Number Grouping v2 (Anti-Context Pollution)

### El Problema: Entity Resolution en SEC Filings

Si le das a un LLM 50 documentos a la vez, mezclará el "Precio de Ejercicio" del Warrant A (2021) con la "Fecha de Vencimiento" del Warrant B (2023). Este es el clásico problema de **Context Pollution**.

### La Solución: Agrupación Inteligente por Tipo de Cadena

No todos los filings se deduplican igual:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIPO DE CADENA                      │ QUÉ PROCESAR                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ IPO: S-1 → S-1/A → EFFECT → 424B4   │ Solo 424B4 (precio final definitivo)  │
│ Follow-on: S-1 → EFFECT → 424B4     │ Solo 424B4 (precio final definitivo)  │
│ Resale: S-1 → EFFECT → 424B3        │ S-1 (detalles) + 424B3 (confirmación) │
├─────────────────────────────────────────────────────────────────────────────┤
│ Shelf: S-3/F-3                      │ S-3 (capacidad total del shelf)       │
│   + 424B5 ATM                       │ + 424B5 (cada ATM es diferente)       │
│   + 424B5 Oferta 1                  │ + 424B5 (cada oferta es diferente)    │
│   + 424B5 Oferta 2                  │ + 424B5 (NO deduplicar)               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 8-K/6-K (material events)           │ TODOS (cada uno es evento único)      │
│ 10-Q/10-K (financials)              │ TODOS (cada uno es trimestre/año)     │
│ DEF 14A (proxies)                   │ TODOS (cada uno es meeting)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Guía Completa de SEC Filings para Dilución

| Filing | Propósito | Cuándo se presenta | Impacto en Precio | Cómo Procesamos |
|--------|-----------|-------------------|-------------------|-----------------|
| **S-1/F-1** | IPO, Follow-on, o Resale | Meses antes (IPO) o <1 mes (follow-on) | None-Medium | Clasificar por contenido |
| **S-1/A** | Enmienda | Después del inicial | None | Skip si hay 424B4 |
| **EFFECT** | SEC aprobó | Después de review | Low-Medium | Señal de pricing inminente |
| **424B4** | Prospecto FINAL | Después de pricing | None | **FUENTE DEFINITIVA** |
| **S-3/F-3** | Shelf registration | Anytime | None-Low | Extraer capacidad total |
| **424B5** | ATM o oferta bajo shelf | Después de EFFECT | None-Medium | **CADA UNO ES DIFERENTE** |
| **424B3** | Resale confirmation | Después de EFFECT | None-Low | Confirmación de registro |
| **8-K/6-K** | Material event | Dentro de 4 días | None-High | **NUNCA DEDUPLICAR** |
| **10-Q/10-K** | Financials | 45/90 días post-Q/Y | None-Low | **NUNCA DEDUPLICAR** |

### Lógica de Deduplicación

```python
class FilingGrouper:
    def deduplicate_filings(filings: List[Dict]) -> Tuple[List[Dict], Dict]:
        """
        REGLAS:
        1. 8-K/6-K/10-Q/10-K: NUNCA deduplicar (cada uno es evento único)
        2. IPO/Follow-on chain (S-1 → 424B4): Solo procesar 424B4
        3. Shelf + ofertas (S-3 + 424B5s): S-3 + TODOS los 424B5
        4. Sin file_number: No deduplicar (no hay cadena)
        """
```

### Por Qué 424B4 es la Fuente Definitiva para IPO/Follow-on

El 424B4 es el **Final Prospectus** que contiene:
- Precio **definitivo** por acción
- Número **exacto** de acciones emitidas
- Términos **finales** de warrants
- Descuentos y comisiones del underwriter

Los S-1/S-1/A anteriores tienen **placeholders** (`$___ per share`) que se llenan en el 424B4.

### Por Qué NO Deduplicar 424B5 bajo un Shelf

Un S-3 shelf de $300M puede generar:
- 424B5 ATM (Enero) - $75M at-the-market program
- 424B5 Oferta (Marzo) - $50M direct offering @ $2.50
- 424B5 Oferta (Julio) - $25M direct offering @ $1.80

**Cada 424B5 es una oferta DIFERENTE** con términos distintos. Deduplicarlos perdería información crítica.

### Ejemplo de Uso

```python
from services.sec.filing_grouper import FilingGrouper

grouper = FilingGrouper()
deduplicated, stats = grouper.deduplicate_filings(filings)

# stats:
# {
#     "original_count": 15,
#     "never_deduplicated": 8,      # 8-K, 10-Q, etc.
#     "grouped_for_dedup": 7,       # S-1, S-3, 424B filings
#     "deduplicated_count": 12,
#     "removed": 3,
#     "groups_detail": {
#         "333-291955": {"type": "ipo_followon", "original": 3, "selected": 1},
#         "333-289000": {"type": "shelf_offerings", "original": 4, "selected": 4}
#     }
# }
```

---

## 🔎 Full-Text Search

### Keywords Exhaustivos

El servicio busca más de 200 keywords organizados por categoría:

```python
DILUTION_KEYWORDS = {
    # Warrants
    "WARRANTS": [
        'warrant', '"warrant agreement"', '"warrants to purchase"',
        '"exercise price"', '"warrant holder"', '"outstanding warrants"'
    ],
    "PRE_FUNDED_WARRANTS": [
        '"pre-funded warrant"', '"prefunded warrant"',
        '"$0.0001 exercise"', '"nominal exercise price"'
    ],
    "PENNY_WARRANTS": ['"penny warrant"', '"$0.01 exercise"'],
    "PLACEMENT_AGENT_WARRANTS": ['"placement agent warrant"', '"broker warrant"'],
    
    # ATM
    "ATM": [
        '"at-the-market"', '"ATM offering"', '"ATM program"',
        '"equity distribution"', '"sales agreement"'
    ],
    
    # Shelf
    "SHELF": [
        '"shelf registration"', '"universal shelf"',
        '"prospectus supplement"', '"Form S-3"', '"Form F-3"'
    ],
    "BABY_SHELF": [
        '"baby shelf"', '"General Instruction I.B.6"',
        '"one-third of public float"'
    ],
    
    # Convertibles
    "CONVERTIBLE_NOTES": [
        '"convertible note"', '"conversion price"',
        '"convertible debt"', '"convertible into common"'
    ],
    "CONVERTIBLE_PREFERRED": [
        '"convertible preferred"', '"series A preferred"',
        '"liquidation preference"'
    ],
    
    # Private Placements
    "PRIVATE_PLACEMENT": [
        '"private placement"', '"PIPE"',
        '"securities purchase agreement"', '"SPA"'
    ],
    
    # Equity Lines
    "EQUITY_LINE": [
        '"equity line"', '"ELOC"',
        '"committed equity facility"', '"Lincoln Park"'
    ],
    
    # Y muchas más categorías...
}
```

### Comprehensive Discovery

```python
class SECFullTextSearch:
    async def comprehensive_dilution_discovery(
        cik: str,
        ticker: str,
        start_date: str = "2015-01-01"
    ) -> Dict:
        """
        Búsqueda exhaustiva de TODOS los instrumentos dilutivos.
        
        Returns:
            {
                "summary": {
                    "total_filings_with_dilution": 45,
                    "categories_detected": ["WARRANTS", "ATM", "CONVERTIBLE_NOTES"],
                    "has_warrants": True,
                    "has_atm": True,
                    "has_shelf": True,
                    "has_convertibles": True
                },
                "priority_filings": [...],
                "prospectus_data": [...]
            }
        """
```

---

## 📈 Cálculo de Dilución Potencial

### Metodología

```python
def calculate_potential_dilution(self) -> dict:
    # 1. WARRANTS (solo Active, excluyendo Replaced/Exercised)
    warrant_shares = sum(
        w.potential_new_shares or w.outstanding or 0 
        for w in warrants
        if not w.exclude_from_dilution 
        and w.status in ['Active', None]
    )
    
    # 2. ATM (remaining_capacity / current_price)
    # Solo ATMs activos
    atm_shares = sum(
        int(atm.remaining_capacity / current_price)
        for atm in atm_offerings
        if atm.status in ['Active', None]
    )
    
    # 3. SHELF (SOLO common stock, precio conservador)
    # NO incluir preferred stock shelves (S-11)
    # Usar 80% del precio actual (descuento típico)
    shelf_shares = 0
    for shelf in shelf_registrations:
        if shelf.status not in ['Active', None]:
            continue
        if shelf.registration_statement == 'S-11':
            continue  # Preferred stock, no diluye common
        if shelf.security_type == 'preferred_stock':
            continue
        
        conservative_price = current_price * 0.8
        shelf_shares += int(shelf.remaining_capacity / conservative_price)
    
    # 4. CONVERTIBLE NOTES
    convertible_note_shares = sum(
        note.remaining_shares_when_converted or note.total_shares_when_converted or 0
        for note in convertible_notes
    )
    
    # 5. CONVERTIBLE PREFERRED
    convertible_preferred_shares = sum(
        cp.remaining_shares_when_converted or cp.total_shares_when_converted or 0
        for cp in convertible_preferred
    )
    
    # 6. EQUITY LINES (remaining / current_price)
    equity_line_shares = sum(
        int(el.remaining_capacity / current_price)
        for el in equity_lines
    )
    
    # TOTAL
    total_potential_shares = (
        warrant_shares + atm_shares + shelf_shares + 
        convertible_note_shares + convertible_preferred_shares + 
        equity_line_shares
    )
    
    dilution_pct = (total_potential_shares / shares_outstanding) * 100
    
    return {
        "total_potential_new_shares": total_potential_shares,
        "warrant_shares": warrant_shares,
        "atm_potential_shares": atm_shares,
        "shelf_potential_shares": shelf_shares,
        "convertible_note_shares": convertible_note_shares,
        "convertible_preferred_shares": convertible_preferred_shares,
        "equity_line_shares": equity_line_shares,
        "current_shares_outstanding": shares_outstanding,
        "total_potential_dilution_pct": round(dilution_pct, 2),
        "assumptions": [
            "All warrants exercised",
            "All ATM capacity used at current price",
            "Common stock shelves used at 80% of current price (conservative)",
            "Preferred stock shelves (S-11) NOT converted to common stock dilution",
            "All convertible notes converted to common stock",
            "All convertible preferred converted to common stock",
            "All equity lines used at current price"
        ]
    }
```

---

## 🔄 Deduplicación Inteligente

### Servicio de Deduplicación

```python
class DeduplicationService:
    def deduplicate_warrants(warrants: List[Dict]) -> List[Dict]:
        """
        Deduplicar por (tipo + exercise_price).
        Tomar el registro más COMPLETO de cada grupo.
        """
        
    def filter_summary_warrants(warrants: List[Dict]) -> List[Dict]:
        """
        Filtrar "warrants outstanding as of X date" de 10-Q.
        Evita doble conteo con warrants específicos.
        """
        
    def classify_warrant_status(warrants: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar: Active | Exercised | Replaced | Historical_Summary
        Detecta inducement/replacement deals.
        """
        
    def impute_missing_exercise_prices(warrants: List[Dict]) -> List[Dict]:
        """
        Inferir exercise_price de warrants de la misma serie.
        """
        
    def calculate_remaining_warrants(warrants: List[Dict]) -> List[Dict]:
        """
        Calcular remaining = total_issued - exercised - expired
        """
```

### Lógica de Clasificación

```python
# Detectar warrants summary (NO sumar a dilución)
is_summary = (
    'as of' in notes and 
    ('outstanding warrants' in notes or 
     'weighted average' in notes or
     'total outstanding' in notes)
)

# Detectar warrants ejercidos
exercised_keywords = ['exercised', 'fully exercised', 'upon exercise']

# Detectar warrants reemplazados
replacement_keywords = ['inducement', 'replacement', 'in exchange for']
```

---

## 💰 Baby Shelf e IB6

### Restricción Baby Shelf

Empresas con **public float < $75M** tienen restricciones bajo **General Instruction I.B.6**:

```python
# Determinar si es Baby Shelf
float_value = float_shares × current_price
is_baby_shelf = float_value < 75_000_000

if is_baby_shelf:
    # Solo puede usar 1/3 del float value cada 12 meses
    ib6_float_value = float_shares × highest_60_day_close × (1/3)
    
    # Current raisable amount (limitado por IB6)
    current_raisable = min(shelf_remaining, ib6_float_value - raised_last_12mo)
    
    # Precio necesario para superar restricción
    # Float Value = Float Shares × Price
    # $75M = Float Shares × Price
    # Price = $75M × 3 / Float Shares
    price_to_exceed = (75_000_000 × 3) / float_shares
```

### Cálculos Implementados

```python
async def _enrich_profile_with_baby_shelf_calculations(
    self,
    profile: SECDilutionProfile,
    float_shares: int
) -> SECDilutionProfile:
    """
    1. Obtener Highest 60-Day Close desde Polygon
    2. Calcular IB6 Float Value = Float × Highest60DayClose × (1/3)
    3. Calcular Current Raisable Amount
    4. Calcular Price To Exceed Baby Shelf
    5. Determinar si ATM está limitado por Baby Shelf
    """
```

---

## 📉 Split Adjustment (Polygon.io)

### Lógica de Ajuste por Splits

```python
async def adjust_warrants_for_splits(ticker: str, warrants: List[Dict]) -> List[Dict]:
    """
    Ajusta warrants y notas convertibles por stock splits.
    
    IMPORTANTE: Polygon's historical_adjustment_factor es CUMULATIVE.
    - Split 2025-03-31: factor=10 (solo este)
    - Split 2024-10-08: factor=90 (9×10, incluye 2025)
    - Split 2024-08-22: factor=1350 (15×9×10, incluye todos)
    
    Por eso usamos SOLO el primer split después de issue_date,
    NO multiplicamos todos los factores.
    """
    
    for warrant in warrants:
        # Skip warrants para comprar NOTAS (no shares)
        if is_note_purchase_warrant(warrant):
            continue
            
        issue_date = warrant.get('issue_date')
        
        # Usar SOLO el primer split después de issue_date
        for split in splits:
            if split['date'] > issue_date:
                factor = split['historical_adjustment_factor']
                
                # Ajustar precio (multiplicar para reverse split)
                warrant['exercise_price'] *= factor
                
                # Ajustar outstanding (dividir para reverse split)
                warrant['outstanding'] /= factor
                
                break  # Solo usar el primer split (factor ya es cumulative)
```

### Detección de Note Purchase Warrants

```python
def is_note_purchase_warrant(warrant: Dict) -> bool:
    """
    Warrants para comprar NOTAS convertibles (no shares) NO se ajustan.
    El exercise_price es el principal de la nota, no precio por acción.
    """
    notes_text = str(warrant.get('notes', '')).lower()
    exercise_price = float(warrant.get('exercise_price', 0) or 0)
    
    return (
        ('purchase' in notes_text and 'note' in notes_text) or
        ('convertible note' in notes_text) or
        (exercise_price > 100000)  # No warrant cuesta $100K+ por acción
    )
```

---

## 🌐 Fuentes de Datos

| Fuente | Uso | Variable de Entorno | Rate Limit |
|--------|-----|---------------------|------------|
| **SEC EDGAR** | Filings gratuitos, XBRL | User-Agent | 10 req/seg |
| **SEC-API.io** | Full-text search, Query API, Historical Shares | `SEC_API_IO_KEY` | Según plan |
| **FMP** | Cash data (fallback) | `FMP_API_KEY` | 300 req/min |
| **Polygon** | Precio actual, Highest 60-day, **Split History**, Shares Outstanding | `POLYGON_API_KEY` | 5 req/min (free) |
| **Gemini** | Extracción primaria (exhibits + filings) | `GOOGL_API_KEY_V2` | Según plan |
| **Grok** | Fallback para filings grandes | `GROK_API_KEY` | Según plan |

### HTTP Clients Compartidos

```python
# http_clients.py
class HTTPClients:
    sec_gov: SECGovClient       # SEC EDGAR directo
    sec_api: SECAPIClient       # SEC-API.io
    fmp: FMPClient              # Financial Modeling Prep
    polygon: PolygonClient      # Polygon.io
    
    async def initialize(polygon_api_key, fmp_api_key, sec_api_key):
        """Inicializar con connection pooling"""
```

---

## 🔄 Flujo Completo de una Request

```
Usuario → GET /api/sec-dilution/MULN/profile
                    │
                    ▼
            ┌───────────────┐
            │ Cache Check   │
            │ (Redis L1)    │
            └───────┬───────┘
                    │ MISS
                    ▼
            ┌───────────────┐
            │ DB Check      │
            │ (PostgreSQL)  │
            └───────┬───────┘
                    │ MISS
                    ▼
            ┌───────────────┐
            │ Get CIK       │
            │ (SEC EDGAR)   │
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Full-Text     │
            │ Search        │ → Encuentra filings con warrants, ATM, etc.
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Download      │
            │ Filings +     │ → ~20 filings más recientes
            │ Exhibits      │
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Gemini        │
            │ Extraction    │ → Extrae de exhibits (contracts)
            │ (Flash)       │
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Pre-Merge     │ → Combina notas parciales
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Consolidation │
            │ (Gemini Pro)  │ → Limpia y deduplica con IA
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Validation    │ → Filtra datos incompletos
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Split         │
            │ Adjustment    │ → Ajusta por reverse splits
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Baby Shelf    │
            │ Calculation   │ → IB6 Float Value
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Risk Ratings  │
            │ (5 ratings)   │ → Overall, Offering, Overhead, Historical, Cash
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Build Profile │
            │ + Save Cache  │ → Redis + PostgreSQL
            └───────┬───────┘
                    │
                    ▼
            Return DilutionProfileResponse
```

---

## ⚙️ Configuración

### Variables de Entorno Requeridas

```bash
# Base de datos
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=tradeul
TIMESCALE_USER=postgres
TIMESCALE_PASSWORD=password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# APIs de datos
SEC_API_IO_KEY=your_sec_api_key
FMP_API_KEY=your_fmp_key
POLYGON_API_KEY=your_polygon_key

# APIs de IA
GOOGL_API_KEY_V2=your_gemini_key
GROK_API_KEY=your_grok_key
```

### Iniciar el Servicio

```bash
# Desarrollo
cd services/dilution-tracker
uvicorn main:app --reload --port 8000

# Docker
docker build -t dilution-tracker .
docker run -p 8000:8000 dilution-tracker

# Con Docker Compose (desde raíz)
docker-compose up dilution-tracker
```

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "healthy", "service": "dilution-tracker", "version": "1.0.0"}
```

---

## 📚 Referencias

- [DilutionTracker.com](https://dilutiontracker.com/) - Inspiración del sistema de ratings
- [SEC EDGAR](https://www.sec.gov/edgar) - Fuente oficial de filings
- [SEC-API.io](https://sec-api.io/) - API de búsqueda full-text
- [General Instruction I.B.6](https://www.sec.gov/rules/final/33-8878.htm) - Restricción Baby Shelf

