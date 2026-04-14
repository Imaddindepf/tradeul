#  XBRL Mapping Engine

Sistema de normalización de datos financieros XBRL a campos canónicos.

## 🎯 Objetivo

Convertir los ~45,000 tags XBRL únicos que las empresas reportan a la SEC en ~150 campos canónicos estandarizados, logrando **>90% de cobertura** para cualquier ticker.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                   PIPELINE DE MAPPING                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TIER 1: Manual (~250 mappings)        confidence = 1.0   │   │
│  │ ─────────────────────────────────────────────────────────│   │
│  │ • schema.py → XBRL_TO_CANONICAL                          │   │
│  │ • Verificados contra TIKR/Bloomberg                      │   │
│  │ • Incluye: revenue, net_income, total_assets, etc.       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓ No match                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TIER 2: SEC Dataset (~3,298 mappings)  confidence = 0.85 │   │
│  │ ─────────────────────────────────────────────────────────│   │
│  │ • sec_tier2.py → SEC_TIER2_MAPPINGS                      │   │
│  │ • Generados de SEC Financial Statement Data Sets         │   │
│  │ • Inferidos por regex patterns sobre plabels             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓ No match                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TIER 3: Regex Patterns (~60 patterns)  confidence = 0.7  │   │
│  │ ─────────────────────────────────────────────────────────│   │
│  │ • engine.py → REGEX_PATTERNS                             │   │
│  │ • Patrones genéricos: .*Revenue.* → revenue              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓ No match                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TIER 4: FASB Labels (~10,732 labels)   confidence = 0.6  │   │
│  │ ─────────────────────────────────────────────────────────│   │
│  │ • engine.py → FASB_LABELS                                │   │
│  │ • Lookup por tag name en taxonomía US-GAAP               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓ No match                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TIER 5: Fallback                       confidence = 0.0  │   │
│  │ ─────────────────────────────────────────────────────────│   │
│  │ • adapter.py → _generate_fallback()                      │   │
│  │ • Normaliza CamelCase → snake_case                       │   │
│  │ • importance = 50 (bajo)                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Estructura de Archivos

```
services/mapping/
├── __init__.py          # Exports públicos
├── adapter.py           # ⭐ Interfaz principal (XBRLMapper)
├── schema.py            # ⭐ Campos canónicos + mappings Tier 1
├── sec_tier2.py         # ⭐ Mappings auto-generados Tier 2
├── engine.py            # Regex patterns + FASB labels
├── database.py          # (Futuro) Persistencia en PostgreSQL
├── llm_classifier.py    # (Futuro) Clasificador con LLM
└── README.md            # Esta documentación
```

## 🔧 Uso

### En extractors.py

```python
from services.mapping.adapter import XBRLMapper

mapper = XBRLMapper()

# Mapear un concepto XBRL
canonical_key, label, importance, data_type = mapper.detect_concept(
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    statement_type="income"
)
# → ("revenue", "Total Revenue", 10000, "monetary")
```

### Añadir nuevo mapping manual (Tier 1)

1. Edita `schema.py`
2. Añade al diccionario `XBRL_TO_CANONICAL`:

```python
XBRL_TO_CANONICAL = {
    # ...existing mappings...
    
    # Tu nuevo mapping
    "NewXBRLConceptName": "canonical_key",
}
```

3. Si es un campo nuevo, añádelo también al schema correspondiente:

```python
INCOME_STATEMENT_SCHEMA = [
    # ...existing fields...
    CanonicalField("canonical_key", "Display Label", "Section", order, importance=8000),
]
```

4. Rebuild el container:
```bash
docker compose build financials && docker compose up -d financials --force-recreate
```

5. Limpia cache:
```bash
docker exec tradeul_redis redis-cli -a "TU_PASSWORD" KEYS "financials:*" | \
  xargs docker exec -i tradeul_redis redis-cli -a "TU_PASSWORD" DEL
```

## 📈 Métricas de Cobertura

| Ticker | Total Fields | Mapped | Coverage |
|--------|--------------|--------|----------|
| COST   | 147          | 141    | **95.9%** |
| AAPL   | 140          | 130    | **92.9%** |
| GOOGL  | 203          | 183    | **90.1%** |

## 🔄 Actualizar Tier 2 (SEC Dataset)

Cada trimestre la SEC publica nuevos datos. Para actualizar:

### 1. Descargar dataset

```bash
# Ir a: https://www.sec.gov/dera/data/financial-statement-data-sets
# Descargar el ZIP más reciente (ej: 2024q4.zip)

mkdir -p /tmp/sec_data
cd /tmp/sec_data
# Descarga manual o:
wget https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q4.zip
unzip 2024q4.zip -d 2024q4/
```

### 2. Parsear y generar mappings

```bash
cd /opt/tradeul/services/financials
python3 scripts/parse_sec_dataset.py /tmp/sec_data/2024q4/ /tmp/sec_output/
```

### 3. Actualizar sec_tier2.py

```bash
cp /tmp/sec_output/tier2_python.py services/mapping/sec_tier2.py
```

### 4. Rebuild y limpiar cache

```bash
docker compose build financials && docker compose up -d financials --force-recreate
# Limpiar cache Redis
```

## 🎯 Añadir Mappings para Campos Faltantes

### Encontrar campos sin mapear

```bash
curl -s "http://localhost:8020/api/v1/financials/COST?period=annual&limit=1" | \
python3 -c "
import sys, json
data = json.load(sys.stdin)
for stmt in ['income_statement', 'balance_sheet', 'cash_flow']:
    for f in data.get(stmt, []):
        if f.get('importance', 50) <= 50:
            print(f\"{f['key']}: {f.get('source_fields', ['?'])[0]}\")
"
```

### Proceso de mapping

1. **Identificar** el tag XBRL original (ej: `UnrecognizedTaxBenefits`)
2. **Decidir** si es importante o debe ignorarse
3. **Añadir** a `XBRL_TO_CANONICAL` en `schema.py`:
   - Si es importante: `"UnrecognizedTaxBenefits": "unrecognized_tax_benefits"`
   - Si debe ignorarse: `"UnrecognizedTaxBenefits": "_skip_tax_detail"`
4. **Crear campo** canónico si no existe (en el schema correspondiente)
5. **Rebuild** y limpiar cache

## 🏭 Industrias Especiales

El sistema incluye mappings para industrias específicas:

| Industria | Campos especiales |
|-----------|-------------------|
| Banking   | `net_interest_income`, `provision_loan_losses`, `noninterest_income` |
| Insurance | `premiums_earned`, `policy_benefits`, `underwriting_income` |
| REITs     | `rental_revenue`, `ffo`, `noi` |
| Tech      | `cloud_revenue`, `subscription_revenue`, `arr` |
| Retail    | `same_store_sales`, `membership_fees`, `e_commerce_revenue` |

## 🔮 Futuras Mejoras

### LLM Classification (Tier 6)
- Archivo: `llm_classifier.py`
- Usa Grok para clasificar tags desconocidos
- Requiere: `GROK_API_KEY` en `.env`

### Database Persistence
- Archivo: `database.py`
- Persistir mappings verificados en PostgreSQL
- Requiere: Tablas `canonical_fields`, `xbrl_mappings`

### Fuzzy Matching
- Instalar: `pip install rapidfuzz`
- Agrupa plabels similares automáticamente
- Mejora cobertura de Tier 2

## 📚 Referencias

- [SEC Financial Statement Data Sets](https://www.sec.gov/dera/data/financial-statement-data-sets)
- [FASB XBRL Taxonomy](https://xbrl.fasb.org/)
- [US-GAAP Taxonomy](https://xbrl.us/home/filers/sec-reporting/taxonomies/)

