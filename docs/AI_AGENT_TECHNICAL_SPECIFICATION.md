# TradeUL AI Agent - Especificación Técnica
## Documento para Revisión de Arquitectura

**Fecha:** 2026-01-20  
**Versión:** 1.0  
**Tipo:** Especificación técnica (sin recomendaciones)

---

## Índice

1. [Vista General del Sistema](#1-vista-general-del-sistema)
2. [Arquitectura de Componentes](#2-arquitectura-de-componentes)
3. [Inventario de Datos](#3-inventario-de-datos)
4. [Flujo de Procesamiento](#4-flujo-de-procesamiento)
5. [Código Fuente Relevante](#5-código-fuente-relevante)
6. [Frameworks Alternativos (Mercado 2025-2026)](#6-frameworks-alternativos-mercado-2025-2026)
7. [Métricas y Limitaciones Conocidas](#7-métricas-y-limitaciones-conocidas)

---

## 1. Vista General del Sistema

### 1.1 Propósito

El AI Agent de TradeUL responde preguntas sobre el mercado financiero usando:
- Datos en tiempo real (Redis snapshot)
- Datos históricos (DuckDB sobre Parquet)
- Investigación externa (Grok, Web)

### 1.2 Stack Tecnológico

| Componente | Tecnología | Versión |
|------------|------------|---------|
| LLM | Google Gemini | 2.5 Pro |
| Embeddings | sentence-transformers | all-MiniLM-L6-v2 |
| Query Engine | DuckDB | (in-process) |
| Almacenamiento histórico | Parquet files | - |
| Cache tiempo real | Redis | - |
| Runtime | Python | 3.11 |
| API Framework | FastAPI | - |
| Container | Docker | - |

### 1.3 Servicios Docker Relacionados

```
tradeul_ai_agent        :8030   Core del agente
tradeul_polygon_ws      :8006   WebSocket Polygon (quotes en vivo)
tradeul_polygon_data    :8027   API datos históricos
tradeul_ticker_metadata :8010   Metadata de tickers
tradeul_screener        :8026   Screener avanzado
tradeul_scanner         :8005   Scanner en tiempo real
```

---

## 2. Arquitectura de Componentes

### 2.1 Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Next.js)                                  │
│                         useAIAgent.ts (512 líneas)                           │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ WebSocket /ws/chat/{client_id}
                                      │ HTTP POST /api/chat
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        AI AGENT SERVICE (main.py)                            │
│                              228 líneas                                       │
│                                                                               │
│  Lifespan:                                                                    │
│  ├── RedisClient (conexión)                                                  │
│  ├── MarketAgent (instancia)                                                 │
│  ├── WebSocketHandler                                                         │
│  ├── REST Routes                                                              │
│  └── EventBus (session:changed)                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        MARKET AGENT (core.py)                                 │
│                              541 líneas                                       │
│                                                                               │
│  class MarketAgent:                                                           │
│    - model: "gemini-2.5-pro"                                                 │
│    - MAX_SELF_CORRECTIONS: 3                                                 │
│    - BASE_TEMPERATURE: 0.1                                                   │
│    - RETRY_TEMPERATURE: 0.05                                                 │
│                                                                               │
│  Clases auxiliares:                                                           │
│    - SQLQualityAnalyzer (detecta over-engineering)                           │
│    - AgentResult (dataclass de respuesta)                                    │
│                                                                               │
│  Arquitectura declarada:                                                      │
│    "semantic_routing + schema_injection + self_correction"                   │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│   INTENT ROUTER     │   │      SCHEMA         │   │       TOOLS         │
│   (584 líneas)      │   │   (schema.py)       │   │   (tool_definitions │
│                     │   │                     │   │    + tools.py)      │
│  Modelo:            │   │  Genera prompt con: │   │                     │
│  all-MiniLM-L6-v2   │   │  - Data schema      │   │  8 tools definidas  │
│                     │   │  - SQL tips         │   │                     │
│  Intents (5):       │   │  - Ejemplos de gaps │   │                     │
│  - HISTORICAL       │   │                     │   │                     │
│  - REALTIME_SCAN    │   │                     │   │                     │
│  - RESEARCH         │   │                     │   │                     │
│  - TICKER_INFO      │   │                     │   │                     │
│  - SYNTHETIC_ETF    │   │                     │   │                     │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

### 2.2 Intent Router (Detalle)

**Archivo:** `agent/intent_router.py` (584 líneas)

**Algoritmo de clasificación (3 pasos):**

```
Query entrada
     │
     ▼
┌────────────────────────────────────────────┐
│ PASO 1: NOW_PATTERNS (regex)               │
│                                            │
│ Patrones compilados:                       │
│ - \bahora\b                                │
│ - \ben\s+este\s+momento\b                  │
│ - \bahora\s+mismo\b                        │
│ - \bactual(?:es|mente)?\b                  │
│ - \ben\s+vivo\b                            │
│ - \ben\s+tiempo\s+real\b                   │
│ - \bright\s+now\b                          │
│ - \bcurrently\b                            │
│ - \bcurrent\b                              │
│ - \blive\b                                 │
│ - \breal[\s-]?time\b                       │
│                                            │
│ + "hoy/today" SIN palabras de cálculo      │
│   (gap, vwap, atr, rsi, sma, etc.)         │
│                                            │
│ Si match → REALTIME_SCAN (confidence=0.95) │
└────────────────────────────────────────────┘
     │ no match
     ▼
┌────────────────────────────────────────────┐
│ PASO 2: DATE_PATTERNS (regex)              │
│                                            │
│ Patrones para fechas específicas:          │
│ - desde enero hasta marzo                  │
│ - from january to march                    │
│ - el 24 de diciembre                       │
│ - semana pasada / last week                │
│ - en diciembre 2025                        │
│                                            │
│ Si match → HISTORICAL (confidence=0.95)    │
└────────────────────────────────────────────┘
     │ no match
     ▼
┌────────────────────────────────────────────┐
│ PASO 3: SEMANTIC SIMILARITY                │
│                                            │
│ Modelo: all-MiniLM-L6-v2 (local)           │
│ Dimensión: 384                             │
│                                            │
│ Proceso:                                   │
│ 1. Encode query → vector                   │
│ 2. Para cada intent:                       │
│    - Cargar embeddings de exemplars        │
│    - Calcular dot product                  │
│    - Tomar max similarity                  │
│ 3. Seleccionar intent con mayor score      │
│                                            │
│ CONFIDENCE_THRESHOLD: 0.35                 │
└────────────────────────────────────────────┘
```

**Exemplars por intent:**

| Intent | Cantidad de exemplars |
|--------|----------------------|
| HISTORICAL_ANALYSIS | 61 (EN + ES) |
| REALTIME_SCAN | 21 |
| RESEARCH | 17 |
| TICKER_INFO | 9 |
| SYNTHETIC_ETF | 10 |

### 2.3 Tools Disponibles

**Archivo:** `agent/tool_definitions.py`

| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `get_market_snapshot` | Snapshot tiempo real de Redis | filter_type, limit, min_volume, min_price, generate_chart |
| `get_top_movers` | Top movers pre-agregados por día | date_str, limit, direction |
| `execute_analysis` | Ejecución de código Python/DuckDB | code (string) |
| `research_ticker` | Investigación profunda (Grok, Web) | ticker, query |
| `quick_news` | Noticias rápidas | ticker, limit |
| `get_ticker_info` | Información básica de ticker | ticker |
| `classify_synthetic_sectors` | ETFs temáticos sintéticos | date, themes, min_tickers_per_sector |
| `get_earnings_calendar` | Calendario de earnings | date, days_ahead |

**Mapping Intent → Tools:**

```python
INTENT_TOOLS = {
    HISTORICAL_ANALYSIS: ["execute_analysis"],
    REALTIME_SCAN: ["get_market_snapshot", "get_ticker_info", "get_earnings_calendar"],
    RESEARCH: ["research_ticker", "quick_news"],
    TICKER_INFO: ["get_ticker_info", "get_market_snapshot"],
    SYNTHETIC_ETF: ["classify_synthetic_sectors", "get_market_snapshot"],
}
```

### 2.4 Schema Injection

**Archivo:** `agent/schema.py`

El schema se inyecta en el system prompt. Contiene:

1. **Estructura de datos** (tablas, columnas, tipos)
2. **Tips de DuckDB** (read_parquet, GLOB, timestamps)
3. **Ejemplo de cálculo de gaps** (JOIN entre días)
4. **Template de código** (historical_query + save_output)

---

## 3. Inventario de Datos

### 3.1 Polygon Flat Files (Histórico)

**Ubicación:** `/data/polygon/` (montado en Docker)

#### day_aggs/

| Propiedad | Valor |
|-----------|-------|
| Archivos | 265 (.parquet) |
| Tamaño | 146 MB |
| Rango | 2024-12-26 → 2026-01-16 |
| Filas por archivo | ~11,824 tickers |

**Schema exacto:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| ticker | object (VARCHAR) | Símbolo (AAPL, TSLA) |
| open | float64 | Precio apertura |
| high | float64 | Máximo del día |
| low | float64 | Mínimo del día |
| close | float64 | Precio cierre |
| volume | int64 | Volumen total |
| window_start | int64 | Timestamp en **nanosegundos** |
| transactions | int64 | Número de transacciones |

**Campos NO disponibles:**
- prev_close
- vwap
- change_percent
- gap_percent
- atr, rsi, sma, ema

#### minute_aggs/

| Propiedad | Valor |
|-----------|-------|
| Archivos | 1,765 (.csv.gz) + today.parquet |
| Tamaño | 32 GB |
| Rango | ~1 año |

**Schema:**
- Idéntico a day_aggs

### 3.2 Redis (Tiempo Real)

**Keys relevantes:**

| Key | Tipo | Contenido |
|-----|------|-----------|
| `snapshot:polygon:latest` | JSON | Snapshot de mercado |
| `snapshot:enriched:latest` | JSON | Snapshot enriquecido |
| `market:session:status` | String | Estado del mercado |
| `market:session:current` | JSON | Sesión actual |

**Estructura de `snapshot:polygon:latest`:**

```json
{
  "timestamp": "2026-01-20T20:31:33.911808",
  "count": 11096,
  "tickers": [
    {
      "ticker": "GLIBA",
      "updated": 1768941081094209096,
      "current_price": 37.88,
      "current_volume": 18312,
      "todaysChange": -0.18,
      "todaysChangePerc": -0.47,
      "day": {
        "o": 37.41, "h": 38.09, "l": 37.41, "c": 37.79,
        "v": 18422.0, "vw": 37.7128
      },
      "prevDay": {
        "o": 38.98, "h": 38.98, "l": 37.41, "c": 38.06,
        "v": 22105.0, "vw": 38.0204
      },
      "lastTrade": {
        "p": 37.88, "s": 108, "t": 1768941081094209096
      },
      "lastQuote": {
        "p": 37.6, "P": 37.88, "s": 200, "S": 200
      },
      "min": {
        "o": 37.64, "h": 37.79, "l": 37.64, "c": 37.79,
        "v": 1255, "vw": 37.6601
      }
    }
  ]
}
```

**Campos disponibles en snapshot (vs. day_aggs):**

| Campo | snapshot | day_aggs |
|-------|----------|----------|
| open/high/low/close | ✅ | ✅ |
| volume | ✅ | ✅ |
| vwap | ✅ (day.vw) | ❌ |
| prev_close | ✅ (prevDay.c) | ❌ |
| change_percent | ✅ (todaysChangePerc) | ❌ |
| bid/ask | ✅ (lastQuote) | ❌ |
| last_trade | ✅ | ❌ |
| transactions | ❌ | ✅ |

---

## 4. Flujo de Procesamiento

### 4.1 Flujo Completo de una Query

```
Usuario: "top gappers de la semana"
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. WebSocket/REST Handler                                      │
│    - Recibe query                                              │
│    - Pasa a MarketAgent.process()                              │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. Intent Router                                               │
│    - NOW_PATTERNS: no match                                    │
│    - DATE_PATTERNS: match "semana"                             │
│    - Result: HISTORICAL_ANALYSIS, confidence=0.95              │
│    - Tools: ["execute_analysis"]                               │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. Build System Prompt                                         │
│    - Inyecta schema de datos (schema.py)                       │
│    - Añade instrucciones de código                             │
│    - Incluye fecha actual: 2026-01-20                          │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. Gemini 2.5 Pro                                              │
│    - Recibe: system prompt + query + tools                     │
│    - Genera: function_call execute_analysis(code="...")        │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 5. Tool Execution (Sandbox)                                    │
│    - Ejecuta código Python                                     │
│    - historical_query(sql) → DuckDB                            │
│    - save_output(result, name) → captura DataFrame             │
└───────────────────────────────────────────────────────────────┘
                │
                ├─── Error? ─── Sí ───┐
                │                     │
                ▼                     ▼
┌─────────────────────────┐   ┌─────────────────────────────────┐
│ 6a. Success             │   │ 6b. Self-Correction Loop        │
│ - Retorna datos         │   │ - MAX_SELF_CORRECTIONS: 3       │
│                         │   │ - get_self_correction_prompt()  │
│                         │   │ - Regenera código               │
│                         │   │ - RETRY_TEMPERATURE: 0.05       │
└─────────────────────────┘   └─────────────────────────────────┘
                │                     │
                └──────────┬──────────┘
                           ▼
┌───────────────────────────────────────────────────────────────┐
│ 7. Gemini genera respuesta final                               │
│    - Interpreta datos                                          │
│    - Genera texto natural                                      │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 8. AgentResult                                                 │
│    - success: bool                                             │
│    - response: str                                             │
│    - data: Dict                                                │
│    - tools_used: List[str]                                     │
│    - self_corrections: int                                     │
└───────────────────────────────────────────────────────────────┘
```

### 4.2 SQL Quality Analyzer

El sistema incluye un analizador que detecta patrones de over-engineering:

```python
COMPLEXITY_PATTERNS = [
    (r'UNION\s+ALL.*UNION\s+ALL.*UNION\s+ALL', 
     "Multiple UNION ALL detected..."),
    (r'(FIRST_VALUE|LAST_VALUE).*OVER.*PARTITION',
     "Window functions detected..."),
    (r'DATE_TRUNC\s*\(\s*[\'"]week',
     "DATE_TRUNC('week',...) returns Monday..."),
    (r'GROUP\s+BY.*GROUP\s+BY',
     "Multiple GROUP BY clauses..."),
]

MAX_SIMPLE_QUERY_LINES = 25
```

---

## 5. Código Fuente Relevante

### 5.1 Estructura de Archivos

```
services/ai-agent/
├── main.py                    # 228 líneas - FastAPI app
├── agent/
│   ├── __init__.py           # Exports
│   ├── core.py               # 541 líneas - MarketAgent
│   ├── intent_router.py      # 584 líneas - Clasificación
│   ├── schema.py             # Schema injection
│   ├── tool_definitions.py   # 8 tools definidas
│   ├── tools.py              # Implementación de tools
│   └── legacy/               # Código deprecado
├── handlers/
│   ├── websocket.py          # WebSocket handler
│   └── rest.py               # REST routes
├── sandbox/
│   ├── manager.py            # Sandbox para código
│   └── data_injector.py      # Inyección de funciones
├── research/
│   ├── grok_research.py      # Integración Grok
│   └── polygon_news.py       # Noticias Polygon
├── llm/
│   └── gemini_client.py      # Cliente Gemini
└── data/
    ├── polygon_client.py     # API Polygon
    └── service_clients.py    # Clientes HTTP
```

### 5.2 Configuración del Modelo

```python
# core.py
class MarketAgent:
    MAX_SELF_CORRECTIONS = 3
    BASE_TEMPERATURE = 0.1
    RETRY_TEMPERATURE = 0.05
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro"):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.intent_router = get_intent_router()
```

### 5.3 Intent Router Configuration

```python
# intent_router.py
class IntentRouter:
    CONFIDENCE_THRESHOLD = 0.35
    
    # Modelo local
    _model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Pre-computed embeddings para 5 intents
    # ~118 exemplars totales
```

---

## 6. Frameworks Alternativos (Mercado 2025-2026)

### 6.1 Orquestación de Agentes

| Framework | Filosofía | Características principales |
|-----------|-----------|----------------------------|
| **LangGraph** | Graph-driven state machines | Checkpointing, time-travel debugging, ciclos |
| **CrewAI** | Role-based collaboration | Agentes con roles (Researcher, Analyst) |
| **AutoGen** | Conversational event loops | Code execution nativo, Azure integration |
| **OpenAI Agents SDK** | Agents, Tools, Handoffs | Sessions nativas, Guardrails |

**Fuente:** Comparativas publicadas 2025-2026

### 6.2 Protocolos de Contexto

| Protocolo | Desarrollador | Adopción |
|-----------|---------------|----------|
| **MCP (Model Context Protocol)** | Anthropic | OpenAI, Google, Microsoft (2025) |

MCP define tres primitivas:
- **Resources:** Datos read-only
- **Tools:** Funciones ejecutables
- **Prompts:** Templates predefinidos

### 6.3 Text-to-SQL

| Técnica | Accuracy (BIRD benchmark) |
|---------|---------------------------|
| CHASE-SQL + Gemini | 73.00% EX |
| OpenSearch-SQL v2 | 72.28% EX |
| AutoLink (schema linking) | 97.4% recall en Bird-Dev |

**Técnicas modernas:**
- HLR-SQL: Human-Like Reasoning con pasos incrementales
- Schema Linking extractivo (no generativo)
- ETM: Enhanced Tree Matching para evaluación

### 6.4 RAG Avanzado

| Técnica | Descripción |
|---------|-------------|
| Semantic Chunking | Grupos por similitud semántica, no tamaño fijo |
| Contextual Retrieval | Pre-resumen de chunks con contexto del documento |
| Cross-Encoder Reranking | Re-scoring de candidatos con transformers |
| Hybrid Search | BM25 (sparse) + Vector (dense) |
| GraphRAG | Knowledge graphs para relaciones complejas |
| Agentic RAG | Agente decide estrategia de retrieval |

### 6.5 Memory Systems

| Tipo | Uso | Implementación común |
|------|-----|---------------------|
| Short-term (Thread) | Conversación actual | Checkpointing (LangGraph) |
| Long-term (Cross-thread) | Preferencias usuario | Vector DB (pgvector, Pinecone) |

---

## 7. Métricas y Limitaciones Conocidas

### 7.1 Métricas Observadas

| Métrica | Valor |
|---------|-------|
| Cold start intent router | ~40-60s (carga modelo MiniLM) |
| Warm classification | ~500ms |
| Modelo LLM | gemini-2.5-pro |
| Self-correction máximo | 3 intentos |
| Tickers en day_aggs | ~11,824 por día |
| Días históricos | 265 (13 meses) |
| Tickers en snapshot | ~11,096 |

### 7.2 Limitaciones Documentadas

1. **Datos históricos limitados:**
   - Solo 8 columnas en day_aggs
   - No hay prev_close, vwap, indicadores técnicos
   - El LLM debe calcular gaps con JOINs

2. **Intent Router:**
   - Modelo local añade latencia en cold start
   - Híbrido: regex (NOW/DATE patterns) + semántico
   - 118 exemplars hardcodeados

3. **Snapshot Redis:**
   - Solo disponible durante horario de mercado
   - ~11,000 tickers (no todos)

4. **Sin memoria de conversación:**
   - Cada query es independiente
   - No hay checkpointing ni memory store

### 7.3 Comportamiento del Sistema

**Cuando funciona bien:**
- Queries con fechas explícitas → HISTORICAL_ANALYSIS
- Queries con "ahora/now" → REALTIME_SCAN
- Queries simples de ticker info

**Casos problemáticos documentados:**
- "top gainers de hoy" → Puede ir a HISTORICAL o REALTIME dependiendo de contexto
- Queries con "hoy" + palabras de cálculo → Fuerza HISTORICAL (para calcular gaps)

---

## Anexo A: Comandos de Verificación

```bash
# Ver schema de day_aggs
docker exec tradeul_ai_agent python3 -c "
import pandas as pd
df = pd.read_parquet('/data/polygon/day_aggs/2025-12-31.parquet')
print(df.columns.tolist())
print(df.dtypes)
"

# Ver estructura de Redis snapshot
docker exec tradeul_ai_agent python3 -c "
import redis, json
r = redis.Redis(host='redis', port=6379, password='tradeul_redis_secure_2024', decode_responses=True)
snap = r.get('snapshot:polygon:latest')
if snap:
    data = json.loads(snap)
    print('Keys:', list(data.keys()))
    if data.get('tickers'):
        print('Ticker fields:', list(data['tickers'][0].keys()))
"

# Ver logs del agente
docker logs tradeul_ai_agent --tail 50

# Contar archivos históricos
docker exec tradeul_ai_agent sh -c "ls /data/polygon/day_aggs/*.parquet | wc -l"
docker exec tradeul_ai_agent sh -c "ls /data/polygon/minute_aggs/*.csv.gz | wc -l"
```

---

## Anexo B: Referencias de Investigación

### Frameworks de Agentes
- LangGraph vs CrewAI vs AutoGen (comparativas 2025-2026)
- OpenAI Agents SDK documentation
- Model Context Protocol (Anthropic)

### Text-to-SQL
- DIN-SQL, DAIL-SQL (baseline 2023)
- HLR-SQL (2026): Human-Like Reasoning
- AutoLink (2025): Autonomous Schema Linking
- BIRD benchmark leaderboard

### RAG
- "Building RAG Systems in 2026" - Towards AI
- "Advanced RAG Techniques" - Neo4j
- RankRAG paper (2025)

### Financial AI
- FinRobot: AI Agent for Equity Research (arXiv 2411.08804)
- AlphaAgents: Multi-Agents for Portfolio Construction (arXiv 2508.11152)
- Orchestration Framework for Financial Agents (arXiv 2512.02227)

---

*Documento generado: 2026-01-20*  
*Este documento es una especificación técnica factual. No contiene recomendaciones.*
