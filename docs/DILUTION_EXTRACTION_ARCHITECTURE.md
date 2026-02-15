# Arquitectura de Extracción de Dilución v4.1

## Cambios en v4.1

| Mejora | Descripción |
|--------|-------------|
| **Section-based extraction** | Extrae secciones específicas (DESCRIPTION OF SECURITIES, THE OFFERING, etc.) en vez de truncar a 30K chars |
| **Preservar tablas HTML** | Convierte tablas a formato texto con separadores `|` para no perder estructura |
| **Fingerprint granular** | Usa `{type}_{year}_{month}_{subtype}_{size_bucket}` como ID determinista |
| **Two-pass validation** | Verifica precios contra reglas (pre-funded ~$0.001) y corrige automáticamente |
| **PDF fallback** | Intenta extraer texto de PDFs con pypdf (best-effort) |
| **Evidence layer** | Cada campo crítico tiene `_source`, `_sources`, `_validation_confidence` |

## Visión General

Sistema de extracción de instrumentos dilutivos desde SEC filings usando:
- **Contextual Processing**: Gemini con contexto acumulado entre llamadas
- **Semantic Deduplication**: Embeddings para detectar duplicados

```
┌──────────┐     ┌───────────────┐     ┌──────────────┐     ┌───────────────┐     ┌────────────────┐
│ SEC-API  │ →   │  Categorizar  │ →   │  Descargar   │ →   │   Gemini      │ →   │  Deduplicar    │
│ (search) │     │  (chains vs   │     │  Contenido   │     │   (extraer)   │     │  (embeddings)  │
│          │     │  transactions)│     │  (.txt/HTML) │     │               │     │                │
└──────────┘     └───────────────┘     └──────────────┘     └───────────────┘     └────────────────┘
     │                  │                     │                    │                     │
     ▼                  ▼                     ▼                    ▼                     ▼
248 filings        12 chains            ~30KB texto           JSON estructurado    Warrants únicos
(metadatos)        145 transactions     por filing            por filing           (merged)
```

---

## Etapa 1: Búsqueda de Filings (SEC-API.io)

### Input
- Ticker (ej: `VMAR`)
- Se resuelve a CIK: `1813783`

### API Call
```json
POST https://api.sec-api.io?token=XXX
{
  "query": { "query_string": { "query": "cik:1813783" } },
  "from": 0, 
  "size": 50,
  "sort": [{ "filedAt": { "order": "desc" } }]
}
```

### Output
Lista de ~248 filings con metadatos:
```json
{
  "formType": "424B4",
  "filedAt": "2025-12-18",
  "accessionNo": "0001104659-25-122686",
  "linkToFilingDetails": "https://www.sec.gov/.../tm2533921d1_424b4.htm",
  "entities": [{ "fileNo": "333-291955" }]
}
```

> ⚠️ **NO descargamos contenido aquí** - Solo metadatos (muy rápido)

---

## Etapa 2: Categorización

Los filings se dividen en 3 categorías:

### Registration Chains (agrupados por `fileNo`)

| Formas | Descripción |
|--------|-------------|
| S-1, F-1 | IPO/Follow-on inicial |
| S-3, F-3 | Shelf registration |
| S-1/A, F-1/A, F-3/A | Amendments |
| EFFECT | Notificación de efectividad |
| RW, MEF, LETTER | Otros relacionados |

**Ejemplo para VMAR:**
```
333-291955: [F-1 (Dec 5), F-1/A (Dec 15), EFFECT (Dec 18)]  → IPO/Follow-on
333-291917: [F-3 (Dec 3), EFFECT (Dec 15)]                  → Shelf/ATM
```

📌 **Estos se procesan JUNTOS** para ver la evolución del registro

### Transaction Filings (por `accessionNo`)

| Formas | Descripción |
|--------|-------------|
| 424B4 | Pricing final de un offering |
| 424B5 | Prospectus supplement |
| 6-K | Anuncios (foreign companies) |
| 8-K | Material events (US companies) |

📌 **Estos son EVENTOS ATÓMICOS** - Se procesan uno a uno con contexto acumulado

### Financials (ignorados por ahora)

| Formas | Uso futuro |
|--------|------------|
| 10-Q, 10-K | Shares outstanding |
| 20-F, 40-F | Annual reports (foreign) |

---

## Etapa 3: Descarga de Contenido

### Formatos de Filings SEC

| Formato | Descripción | Manejo |
|---------|-------------|--------|
| `.txt` | Texto plano con HTML embebido | ✅ **PREFERIDO** - Más fácil de procesar |
| `.htm/.html` | Archivo HTML del prospectus | ✅ Segundo intento si .txt falla |
| `.pdf` | Algunos filings en PDF | ❌ **SALTAMOS** - No podemos parsear |

### Proceso de Descarga (por prioridad)

**1️⃣ Intentar .TXT directo (SEC.gov):**
```
https://www.sec.gov/Archives/edgar/data/1813783/000110465925122686/0001104659-25-122686.txt
```
- Headers: `User-Agent: "Tradeul Research contact@tradeul.com"`

**2️⃣ Si falla, usar SEC-API.io filing-reader (fallback):**
```
https://api.sec-api.io/filing-reader?token=XXX&url=<url_del_filing>
```

### Limpieza del Contenido

```python
# Quitar tags HTML
text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', text)

# Normalizar espacios
text = re.sub(r'\s+', ' ', text)

# Limitar tamaño (30K chars max por filing)
text = text[:30000]
```

**Resultado:** ~30KB de texto limpio por filing

---

## Etapa 4: Extracción con Gemini (LLM)

### Modelo
- **gemini-2.5-flash** (contexto de ~1M tokens)
- Capacidad: ~200K tokens por llamada (~800KB de texto)

### Procesamiento de Chains

Para cada chain (ej: `333-291955` con F-1, F-1/A, EFFECT):

1. **Seleccionar "key filings"** de la cadena:
   - Prioridad: `EFFECT > F-3/A > F-1/A > F-3 > F-1`
   - Max 4 filings por cadena

2. **Descargar contenido** de cada key filing

3. **Concatenar** todo en un solo texto:
```
=== F-1 (2025-12-05) ===
[contenido del F-1, ~30KB]

=== F-1/A (2025-12-15) ===
[contenido del amendment, ~30KB]

=== EFFECT (2025-12-18) ===
[notificación de efectividad]
```

4. **Enviar a Gemini** con `REGISTRATION_CHAIN_PROMPT`

5. **Gemini devuelve JSON estructurado:**
```json
{
  "offering": {
    "type": "F-1",
    "status": "Effective",
    "file_number": "333-291955"
  },
  "warrants": [
    {
      "series_name": "December 2025 Common Warrants",
      "exercise_price": 0.375,
      "total_issued": 16000000
    }
  ]
}
```

6. **Agregar al CONTEXTO ACUMULADO**

### Procesamiento de Transactions

Para cada transaction filing (424B4, 424B5, 6-K, 8-K):

```
┌─────────────────────────────────────────────────────────────┐
│                   CONTEXTO ACUMULADO                        │
│                                                             │
│ Ya hemos extraído:                                          │
│ - 3 warrants de chain 333-291955                            │
│ - 1 shelf registration de chain 333-291917                  │
│ - 1 ATM offering                                            │
│                                                             │
│ Este contexto se PASA a Gemini para:                        │
│ 1. Evitar duplicados                                        │
│ 2. Actualizar datos existentes                              │
│ 3. Correlacionar información                                │
└─────────────────────────────────────────────────────────────┘
```

**Prompt a Gemini:**
```
EXISTING DATA (ya extraído):
- Warrants: [Dec 2025 Common @ $0.375, Dec 2025 Pre-Funded @ $0.001, ...]
- Shelf: [F-3 $100M capacity, ...]

TRANSACTION FILING:
[contenido del 6-K, ~30KB]

Extrae SOLO información NUEVA o ACTUALIZADA...
```

**Gemini devuelve DELTAS:**
```json
{
  "warrants": [{ "series_name": "...", "event": "CLOSED" }],
  "updates": [{ "ref": "Dec 2025 Common", "outstanding": 15800000 }]
}
```

---

## Etapa 5: Deduplicación Semántica

### ¿Por qué es necesaria?

A pesar del contexto, pueden aparecer duplicados porque:
- Gemini puede "alucinar" precios históricos (ej: $125 de tablas de capitalización)
- Nombres varían ligeramente ("Dec 2025" vs "December 2025")
- Mismo warrant mencionado en múltiples filings

### Solución: Embeddings + Clustering

#### 1️⃣ Pre-agrupación (reduce espacio de búsqueda)

Agrupar por: `(mes, año, tipo_básico)`

```python
# Ejemplo:
"2025-12-common":     [warrant1, warrant2, warrant3]  # Solo estos se comparan
"2025-12-pre-funded": [warrant4, warrant5]
"2025-01-common":     [warrant6]                      # Separado (diferente mes)
```

#### 2️⃣ Generar Fingerprints

```python
# Fingerprint = "{month_year} {basic_type}"
# Ejemplos:
"2025-12 common warrant"
"2025-12 pre-funded warrant"
"2025-01 common warrant"

# ⚠️ NO incluimos precio - puede estar incorrecto
```

#### 3️⃣ Generar Embeddings

- Modelo: `text-embedding-004`
- Cada fingerprint → vector de 768 dimensiones
- API: `google.genai.embed_content()`

#### 4️⃣ Calcular Similitud (Cosine Similarity)

```
           similarity_matrix
           w1      w2      w3      w4
      ┌────────────────────────────────┐
  w1  │  1.0    0.98    0.95    0.45  │
  w2  │  0.98   1.0     0.97    0.42  │   w1,w2,w3 similares (>0.85)
  w3  │  0.95   0.97    1.0     0.40  │   w4 diferente (<0.85)
  w4  │  0.45   0.42    0.40    1.0   │
      └────────────────────────────────┘
```

#### 5️⃣ Clustering Greedy

- Umbral: 0.85 (85% similitud)
- `w1, w2, w3` → cluster1
- `w4` → cluster2

#### 6️⃣ Merge Inteligente (por cluster)

**Prioridad de fuentes:**

| Fuente | Prioridad | Descripción |
|--------|-----------|-------------|
| 424B4 | 100 | Pricing definitivo |
| 6-K | 90 | Confirmación de cierre |
| 424B5 | 80 | Prospectus supplement |
| 8-K | 70 | Material event |
| chain | 30 | Registration (puede tener datos preliminares) |

**Resultado del merge:**
```python
cluster1 = [w1(424B4), w2(6-K), w3(chain)]
→ merged_warrant = w1  # Toma datos de 424B4
→ merged_warrant._sources = ["424B4", "6-K", "chain"]
→ merged_warrant._merged_from = 3
```

---

## Etapa 6: Filtrado Final

### Excluir (warrants de intermediarios)

```python
# Remover si:
- warrant_type contiene "underwriter" o "placement agent"
- series_name contiene "underwriter" o "placement agent"
- known_owners = ["H.C. Wainwright", "Roth Capital", ...]
```

### Incluir (resultado final)

- ✅ Common Warrants (para inversores)
- ✅ Pre-Funded Warrants (para inversores)
- ✅ Convertible Notes
- ✅ ATM Offerings
- ✅ Shelf Registrations

---

## Estructura de Archivos

```
services/dilution-tracker/
├── services/extraction/
│   ├── contextual_extractor.py    ← 🔹 CORE: Procesa chains + transactions
│   │                                   - _process_registration_chain()
│   │                                   - _process_transactions_with_context()
│   │                                   - extract_all() → orquesta todo
│   │
│   └── semantic_deduplicator.py   ← 🔹 DEDUP: Embeddings + clustering
│                                       - _create_fingerprint()
│                                       - deduplicate() → agrupa + mergea
│
├── http_clients/
│   ├── sec_api_client.py          ← API para buscar filings (sec-api.io)
│   └── sec_gov_client.py          ← Descarga directa de SEC.gov
│
└── routers/
    ├── extraction_router.py       ← Endpoints /api/extraction/*
    └── debug_router.py            ← Endpoints /api/debug/* (step-by-step)
```

---

## API Endpoints

### Extracción

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/extraction/{ticker}/extract` | GET | Ejecuta extracción completa |
| `/api/extraction/{ticker}/chains` | GET | Lista registration chains |

### Debug

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/debug/{ticker}/pipeline` | GET | Muestra estado de cada etapa (sin Gemini) |
| `/api/debug/{ticker}/extract-with-debug` | GET | Extracción real con debug detallado |
| `/api/debug/{ticker}/test-dedup` | GET | Prueba deduplicación con datos mock |
| `/api/debug/{ticker}/filing-content/{accession}` | GET | Obtiene contenido de un filing |

---

## Configuración

```python
# contextual_extractor.py
MAX_TOKENS_PER_BATCH = 200_000   # ~200K tokens por llamada
CHARS_PER_TOKEN = 4              # 4 caracteres ≈ 1 token
MAX_CONTENT_PER_FILING = 30_000  # 30K chars max por filing
MAX_FILINGS_PER_BATCH = 15       # Max filings por batch
```

---

## FAQ

### ¿Es RAG?

**No exactamente.** RAG tradicional:
1. Indexa documentos en Vector DB
2. Query → Retrieve relevant chunks
3. Generate con contexto recuperado

**Nuestra arquitectura:**
1. Categoriza filings por tipo
2. Procesa chains con texto completo
3. Pasa CONTEXTO ACUMULADO al LLM

### ¿Qué formato de archivo procesamos?

- ✅ `.txt` - Formato principal de SEC
- ✅ `.htm/.html` - Fallback
- ✅ `.pdf` - Best-effort con pypdf (v4.1)

### ¿Cuánto texto se pasa a Gemini?

- **Por chain:** ~120KB (4 filings × 30KB)
- **Por transaction:** ~30KB del filing + ~5KB de contexto JSON
- **Modelo:** gemini-2.5-flash (1M tokens de contexto)

### ¿Por qué aún hay duplicados?

Gemini puede "alucinar" datos de tablas históricas (ej: capitalización).
La deduplicación semántica agrupa estos duplicados y selecciona el dato más definitivo.

---

## Ejemplo de Output

Para VMAR (después de deduplicación):

```
INPUT:  6 warrants duplicados
OUTPUT: 3 warrants únicos

Dec 2025 Common:     $0.375  ✅ (de 424B4)
Dec 2025 Pre-Funded: $0.001  ✅
Jan 2025 Common:     $1.5    ✅
```

---

## Nuevos Módulos v4.1

### `section_extractor.py`

Extrae secciones específicas de SEC filings en vez de truncar arbitrariamente.

**Secciones objetivo:**
```python
SECTION_PATTERNS = {
    'description_of_securities': [...],  # Términos de warrants
    'the_offering': [...],               # Pricing, cantidades
    'plan_of_distribution': [...],       # Underwriters
    'dilution': [...],                   # Impacto
    'capitalization': [...],             # Estructura
    'selling_stockholders': [...],       # Holders vendiendo
    'recent_developments': [...],        # Eventos recientes
}
```

**Funciones clave:**
- `extract_sections_for_dilution(text)` - Extrae y concatena secciones relevantes
- `clean_html_preserve_structure(html)` - Limpia HTML preservando tablas
- `html_table_to_text(html)` - Convierte tablas HTML a formato `| col1 | col2 |`

### `validator.py`

Two-pass validation para detectar y corregir datos alucinados.

**Reglas de validación:**
```python
PRICE_RULES = {
    'pre-funded': {
        'expected_range': (0.0001, 0.01),  # Casi siempre ~$0.001
        'flag_if_above': 1.0,              # ERROR si > $1
    },
    'common': {
        'expected_range': (0.10, 100.0),
        'flag_if_above': 500.0,            # WARNING si > $500
    },
}
```

**Funciones clave:**
- `validate_warrant(warrant, source_text)` - Valida un warrant
- `apply_corrections(instrument, result)` - Aplica correcciones automáticas

### `semantic_deduplicator.py` (v4.1)

Deduplicación con IDs deterministas (no depende de embeddings).

**Formato de instrument_id:**
```
{type}_{year}_{month}_{subtype}_{size_bucket}[_{price_bucket}]

Ejemplo: warrant_2025_12_common_5-20M_sub-dollar
```

**Buckets de tamaño:**
- `0-1M`: < 1,000,000
- `1-5M`: 1M - 5M
- `5-20M`: 5M - 20M
- `>20M`: > 20,000,000

**Prioridad de merge:**
```python
SOURCE_PRIORITY = {
    '424B4': 100,  # Pricing final
    '6-K': 90,     # Announcement
    '424B5': 80,   # Prospectus
    'chain': 30,   # Registration
}
```

---

## Campos de Provenance (v4.1)

Cada instrumento extraído incluye:

```python
{
    "series_name": "December 2025 Common Warrants",
    "exercise_price": 0.375,
    # ... datos normales ...
    
    # Provenance v4.1
    "_source": "424B4:2025-12-18:0001104659-25-122686",
    "_sources": ["424B4:2025-12-18", "6-K:2025-12-19", "chain:333-291955"],
    "_merged_from": 3,
    "_dedup_id": "warrant_2025_12_common_5-20M_sub-dollar",
    "_validation_confidence": 0.95,
    "_validation_issues": [],  # O lista de issues si hay
    "filing_url": "https://www.sec.gov/..."
}
```

---

## Testing v4.1

```bash
# Test section extraction
curl "http://localhost:8009/api/debug/VMAR/pipeline"

# Test deduplication
curl "http://localhost:8009/api/debug/VMAR/test-dedup?threshold=0.85"

# Full extraction with debug
curl "http://localhost:8009/api/debug/VMAR/extract-with-debug?max_transactions=5"
```

