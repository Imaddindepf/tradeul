# TradeUL AI Agent V3 - Arquitectura Técnica Completa
## Documento para Pitch

**Servicio:** ai-agent  
**Puerto:** 8030  
**Versión:** 3.0  
**Fecha:** 2026-01-21

---

## 1. Resumen Ejecutivo

El AI Agent V3 es un sistema de análisis financiero basado en **LLM Function Calling directo**. Responde preguntas sobre el mercado en lenguaje natural, ejecutando herramientas especializadas para obtener datos en tiempo real o históricos.

**Características clave:**
- **Dual-Model Architecture**: Gemini Flash (routing) + Gemini Pro (análisis)
- **Function Calling nativo**: Sin router local, sin regex, sin cold start
- **Sandbox aislado**: Ejecución de código Python/DuckDB en contenedor Docker
- **Datos Polygon**: 266 días de OHLCV diario, 32GB de minuto-a-minuto

---

## 2. Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTE                                             │
│                    (WebSocket o REST HTTP)                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        ┌──────────────────────┐       ┌──────────────────────┐
        │  WebSocket Endpoint  │       │   REST Endpoint      │
        │  /ws/chat/{client_id}│       │   POST /api/chat     │
        └──────────────────────┘       └──────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         MarketAgentV3 (core_v3.py)                               │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    PASO 1: ROUTING (Gemini Flash)                        │   │
│  │                                                                          │   │
│  │  Modelo: gemini-2.0-flash                                               │   │
│  │  Temperature: 0.1                                                        │   │
│  │  Mode: function_calling = "any"                                          │   │
│  │                                                                          │   │
│  │  Input: Query del usuario + Definiciones de 8 tools                     │   │
│  │  Output: function_call con nombre de tool + argumentos                  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
│          ┌────────────────────────┬┴───────────────────────┐                   │
│          ▼                        ▼                        ▼                   │
│  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐              │
│  │get_market_    │      │execute_       │      │research_      │              │
│  │snapshot       │      │analysis       │      │ticker         │              │
│  │               │      │               │      │               │              │
│  │ Fuente:       │      │ Fuente:       │      │ Fuente:       │              │
│  │ Scanner API   │      │ Sandbox+      │      │ Grok API      │              │
│  │ (Redis)       │      │ DuckDB        │      │ Web Search    │              │
│  └───────────────┘      └───────┬───────┘      └───────────────┘              │
│                                 │                                              │
│                                 ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                 PASO 2: CODE GENERATION (Gemini Pro)                     │   │
│  │                 (Solo para execute_analysis)                             │   │
│  │                                                                          │   │
│  │  Modelo: gemini-2.5-pro                                                 │   │
│  │  Temperature: 0.1 (0.05 en retry)                                       │   │
│  │  Max self-corrections: 3                                                │   │
│  │                                                                          │   │
│  │  System Prompt incluye:                                                 │   │
│  │  - Schema de datos (day_aggs, minute_aggs)                              │   │
│  │  - Tips de DuckDB                                                        │   │
│  │  - Ejemplo de cálculo de gaps                                           │   │
│  │  - Template de código obligatorio                                        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                 │                                              │
│                                 ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    PASO 3: SANDBOX EXECUTION                             │   │
│  │                                                                          │   │
│  │  Container: Docker aislado (sandbox-python)                              │   │
│  │  Network: none (sin acceso a red)                                        │   │
│  │  Memory: 512MB límite                                                    │   │
│  │  Timeout: 60 segundos                                                    │   │
│  │                                                                          │   │
│  │  Librerías disponibles:                                                  │   │
│  │  - pandas, numpy, duckdb                                                │   │
│  │  - matplotlib, seaborn                                                  │   │
│  │  - Funciones inyectadas: historical_query(), save_output()              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                 │                                              │
│                                 ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                PASO 4: RESPONSE GENERATION (Gemini Flash)               │   │
│  │                                                                          │   │
│  │  Input: Query original + Datos obtenidos (JSON)                         │   │
│  │  Output: Respuesta en lenguaje natural con tablas/insights              │   │
│  │  Temperature: 0.3                                                        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Modelos LLM Utilizados

| Modelo | Uso | Costo aproximado |
|--------|-----|------------------|
| **gemini-2.0-flash** | Routing (selección de tool) | ~$0.001/query |
| **gemini-2.0-flash** | Interpretación de resultados | ~$0.001/query |
| **gemini-2.5-pro** | Generación de código Python/SQL | ~$0.01/query |

**Configuración:**

```python
class MarketAgentV3:
    ROUTING_MODEL = "gemini-2.0-flash"   # Barato, rápido
    ANALYSIS_MODEL = "gemini-2.5-pro"     # Inteligente para código
    
    MAX_SELF_CORRECTIONS = 3
    BASE_TEMPERATURE = 0.1
    RETRY_TEMPERATURE = 0.05
```

---

## 4. Tools Disponibles (8)

### 4.1 get_market_snapshot
**Propósito:** Datos en tiempo real del mercado  
**Fuente:** Scanner API (http://scanner:8005)  
**Datos:** ~11,000 tickers activos

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| filter_type | enum | "all", "gainers", "losers", "volume", "premarket", "postmarket" |
| limit | int | Máximo de resultados (default 50) |
| min_volume | int | Filtro de volumen mínimo |
| min_price | float | Filtro de precio mínimo |
| min_market_cap | float | Filtro de market cap mínimo |
| generate_chart | bool | Generar gráfico de barras |

**Campos retornados por ticker:**
```
symbol, price, change_percent, volume_today, market_cap, 
sector, rvol, vwap, premarket_change_percent, postmarket_change_percent
```

### 4.2 execute_analysis
**Propósito:** Análisis histórico personalizado  
**Fuente:** DuckDB sobre archivos Parquet  
**Ejecución:** Sandbox Docker aislado

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| code | string | Código Python con SQL DuckDB |

**Funciones inyectadas en sandbox:**
- `historical_query(sql)` → Ejecuta SQL en DuckDB, retorna DataFrame
- `save_output(data, name)` → Guarda resultado para retornar al agente

### 4.3 get_top_movers
**Propósito:** Top movers pre-agregados por fecha  
**Fuente:** Archivos Parquet locales

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| date_str | string | "today", "yesterday", o "YYYY-MM-DD" |
| limit | int | Número de resultados |
| direction | enum | "up" (gainers) o "down" (losers) |

### 4.4 research_ticker
**Propósito:** Investigación profunda de un ticker  
**Fuente:** Grok API, búsqueda web

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| ticker | string | Símbolo (ej: "AAPL") |
| query | string | Qué investigar (opcional) |

### 4.5 quick_news
**Propósito:** Noticias recientes de un ticker  
**Fuente:** API de noticias

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| ticker | string | Símbolo |
| limit | int | Máximo de noticias |

### 4.6 get_ticker_info
**Propósito:** Información básica de un ticker  
**Fuente:** Metadata service

**Retorna:** name, price, market_cap, sector, industry

### 4.7 classify_synthetic_sectors
**Propósito:** Crear ETFs temáticos sintéticos  
**Temas:** Nuclear, AI, EV, Cannabis, Space, Biotech, Quantum, Robotics

### 4.8 get_earnings_calendar
**Propósito:** Calendario de earnings

---

## 5. Datos Disponibles

### 5.1 day_aggs (Datos diarios)

**Ubicación:** `/data/polygon/day_aggs/`  
**Formato:** Apache Parquet  
**Tamaño:** 146 MB  
**Archivos:** 266 (uno por día de trading)  
**Rango:** 2024-12-26 → 2026-01-20  
**Filas por archivo:** ~11,807 tickers

**Schema:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| ticker | VARCHAR | Símbolo del stock (ej: "AAPL") |
| open | DOUBLE | Precio de apertura |
| high | DOUBLE | Máximo del día |
| low | DOUBLE | Mínimo del día |
| close | DOUBLE | Precio de cierre |
| volume | INT64 | Volumen total del día |
| window_start | INT64 | Timestamp en **NANOSEGUNDOS** |
| transactions | INT64 | Número de transacciones |

**Ejemplo de fila:**
```json
{
  "ticker": "A",
  "volume": 2603512,
  "open": 144.2,
  "close": 139.64,
  "high": 144.88,
  "low": 139.485,
  "window_start": 1768539600000000000,
  "transactions": 40875
}
```

**Campos NO disponibles:**
- prev_close (debe calcularse con JOIN)
- vwap (debe aproximarse como (high+low+close)/3)
- indicadores técnicos (RSI, ATR, SMA)

### 5.2 minute_aggs (Datos por minuto)

**Ubicación:** `/data/polygon/minute_aggs/`  
**Formato:** CSV.gz (comprimido) + today.parquet  
**Tamaño:** 32 GB  
**Archivos:** ~1,765  
**Rango:** ~1 año

**Schema:** Idéntico a day_aggs

### 5.3 Acceso a datos en código

```python
# DuckDB read functions
read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
read_csv_auto('/data/polygon/minute_aggs/2026-01-16.csv.gz')

# GLOB para múltiples archivos
read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')

# Conversión de timestamp
to_timestamp(window_start / 1e9)  -- nanoseconds to seconds
```

---

## 6. Sandbox de Ejecución

### 6.1 Configuración del contenedor

```python
# sandbox/config.py
SandboxConfig:
    image: "sandbox-python:latest"
    memory_limit: "512m"
    cpu_period: 100000
    cpu_quota: 50000  # 50% de 1 CPU
    timeout_seconds: 60
    max_output_size: 50 * 1024 * 1024  # 50MB
    network_mode: "none"  # SIN acceso a red
```

### 6.2 Librerías disponibles en sandbox

```python
# Disponibles automáticamente
import pandas as pd
import numpy as np
import duckdb
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import pytz
```

### 6.3 Funciones inyectadas

```python
def historical_query(sql: str) -> pd.DataFrame:
    """Ejecuta SQL en DuckDB sobre archivos Parquet/CSV."""
    
def save_output(data, name='result'):
    """Guarda DataFrame/dict/chart para retornar al agente."""

def calculate_rsi(prices, period=14) -> pd.Series:
    """Calcula RSI."""

def calculate_atr(high, low, close, period=14) -> pd.Series:
    """Calcula Average True Range."""

def calculate_sma(prices, period=20) -> pd.Series:
    """Calcula Simple Moving Average."""

def calculate_ema(prices, period=20) -> pd.Series:
    """Calcula Exponential Moving Average."""

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Calcula Bollinger Bands."""
```

---

## 7. API Endpoints

### 7.1 REST API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /api/context | Contexto de mercado actual |
| POST | /api/chat | Procesar mensaje de chat |
| GET | /api/charts/{name} | Obtener gráfico generado |
| GET | /api/workflows | Listar workflows guardados |
| POST | /api/workflows | Crear workflow |
| POST | /api/workflow-execute | Ejecutar workflow ad-hoc |

### 7.2 Formato de Request (POST /api/chat)

```json
{
  "content": "top gainers today",
  "conversation_id": "optional-uuid"
}
```

### 7.3 Formato de Response

```json
{
  "success": true,
  "response": "Here are the top gainers...\n\n| Symbol | Price | Change% |...",
  "data": {
    "get_market_snapshot": {
      "success": true,
      "data": [...],
      "count": 50
    }
  },
  "tools_used": ["get_market_snapshot"],
  "tool_calls": [
    {"name": "get_market_snapshot", "args": {"filter_type": "gainers"}}
  ],
  "code": "get_market_snapshot(filter_type='gainers')",
  "charts": null,
  "execution_time_ms": 3200,
  "error": null
}
```

### 7.4 WebSocket

**Endpoint:** `ws://localhost:8030/ws/chat/{client_id}`

Permite streaming de pasos intermedios durante el procesamiento.

---

## 8. Flujo de Routing

El sistema usa un **prompt de routing** para ayudar a Gemini Flash a elegir la tool correcta:

```
CRITICAL ROUTING RULES:

1. REALTIME DATA (use get_market_snapshot):
   - "top gainers today", "top stocks now", "what's moving"
   - "top stocks tdy", "gainers ahora", "live prices"
   - Keywords: today, now, ahora, hoy, live, current, tdy

2. HISTORICAL ANALYSIS (use execute_analysis):
   - "gappers this week", "top gainers of the week/month"
   - ANY query about PAST dates, weeks, months
   - Calculations like gaps, VWAP comparisons
   - Keywords: week, month, yesterday, last, semana, mes

3. RESEARCH (use research_ticker):
   - "why is X up/down", "news about X"
   - Sentiment, news, SEC filings

4. TICKER INFO (use get_ticker_info):
   - "what is AAPL", "info about MSFT"
```

---

## 9. Self-Correction Loop

Cuando `execute_analysis` falla o retorna 0 resultados:

```
┌─────────────────────────────────────────────┐
│ Intento 1: Gemini Pro genera código         │
│            Temperature: 0.1                  │
└─────────────────────────────────────────────┘
                    │
                    ▼ Error o 0 resultados
┌─────────────────────────────────────────────┐
│ Intento 2: Self-correction prompt           │
│            Temperature: 0.05                 │
│            Incluye: código anterior + error │
└─────────────────────────────────────────────┘
                    │
                    ▼ Error o 0 resultados
┌─────────────────────────────────────────────┐
│ Intento 3: Último intento                   │
│            Temperature: 0.05                 │
└─────────────────────────────────────────────┘
                    │
                    ▼ Error
┌─────────────────────────────────────────────┐
│ Retornar error al usuario                   │
└─────────────────────────────────────────────┘
```

---

## 10. Dependencias Externas

| Servicio | Puerto | Propósito |
|----------|--------|-----------|
| Redis | 6379 | Cache, eventos, sesiones |
| Scanner | 8005 | Datos en tiempo real |
| Ticker Metadata | 8010 | Información de tickers |
| Grok API | externo | Investigación profunda |
| Google AI | externo | Gemini Flash + Pro |

---

## 11. Archivos del Servicio

```
/app/
├── main.py                    # FastAPI app, lifecycle, endpoints
├── agent/
│   ├── __init__.py           # Exports MarketAgentV3
│   ├── core_v3.py            # Lógica principal del agente (500 líneas)
│   ├── tool_definitions.py   # 8 tools definidas con parámetros
│   ├── tools.py              # Implementación de tools
│   └── schema.py             # Schema inyectado al LLM
├── handlers/
│   ├── rest.py               # Endpoints REST
│   └── websocket.py          # WebSocket handler
├── sandbox/
│   ├── manager.py            # Gestión de contenedores Docker
│   ├── config.py             # Configuración del sandbox
│   ├── duckdb_layer.py       # Funciones inyectadas (historical_query, etc.)
│   └── data_injector.py      # Inyección de datos al sandbox
├── research/
│   ├── grok_research.py      # Integración con Grok
│   └── synthetic_sectors.py  # Clasificador de sectores temáticos
└── data/
    └── polygon_client.py     # Cliente API Polygon (fallback)
```

---

## 12. Ejemplo de Ejecución

### Query: "top 5 stocks con mayor gap entre el 15 y 16 de enero"

**Paso 1: Routing (Gemini Flash)**
```
Input: "top 5 stocks con mayor gap entre el 15 y 16 de enero"
Output: function_call execute_analysis
```

**Paso 2: Code Generation (Gemini Pro)**
```python
sql = '''
WITH prev AS (
    SELECT ticker, close as prev_close 
    FROM read_parquet('/data/polygon/day_aggs/2026-01-15.parquet')
),
curr AS (
    SELECT ticker, open
    FROM read_parquet('/data/polygon/day_aggs/2026-01-16.parquet')
)
SELECT 
    c.ticker,
    p.prev_close,
    c.open,
    ROUND((c.open - p.prev_close) / p.prev_close * 100, 2) as gap_pct
FROM curr c
JOIN prev p ON c.ticker = p.ticker
WHERE p.prev_close > 0
ORDER BY gap_pct DESC
LIMIT 5
'''
result = historical_query(sql)
save_output(result, 'top_gaps')
```

**Paso 3: Sandbox Execution**
```
Resultado: DataFrame con 5 filas
- OCG: +24751.49%
- ASBP: +3676.49%
- HUBC: +1517.16%
- VERO: +301.40%
- JFBR: +120.43%
```

**Paso 4: Response Generation (Gemini Flash)**
```markdown
Aquí están las 5 acciones con el mayor gap entre el 15 y 16 de enero:

| Ticker | Cierre Anterior | Apertura | Gap (%) |
|--------|-----------------|----------|---------|
| OCG    | $0.0101         | $2.51    | 24751.49% |
| ASBP   | $0.0519         | $1.96    | 3676.49% |
...
```

---

## 13. Métricas de Rendimiento

| Operación | Tiempo típico |
|-----------|---------------|
| Routing (Flash) | 500-800ms |
| Code generation (Pro) | 2-5s |
| Sandbox execution | 1-10s (depende de query) |
| Response generation | 500-1000ms |
| **Total query simple** | **2-4 segundos** |
| **Total query compleja** | **15-30 segundos** |

---

*Documento generado automáticamente desde código fuente*  
*Versión: 3.0 | Fecha: 2026-01-21*
