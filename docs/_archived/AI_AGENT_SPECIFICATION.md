# 🤖 Tradeul AI Agent - Especificación Técnica

## Visión General

Un agente conversacional que permite a los usuarios consultar datos del mercado en lenguaje natural.
El agente genera código en un DSL propio que se ejecuta contra la infraestructura existente de Tradeul.

---

## 📐 Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                       │
│                                                                             │
│  FloatingWindow (AIAgent)                                                   │
│  ┌─────────────────────┐              ┌────────────────────────────────┐   │
│  │   ChatPanel         │              │   ResultsPanel                 │   │
│  │   - Messages        │◄────────────►│   - ResultBlocks[]             │   │
│  │   - Input           │   Estado     │     - code (collapsible)       │   │
│  │   - Status badges   │   compartido │     - output (table/chart)     │   │
│  └─────────────────────┘              └────────────────────────────────┘   │
└────────────────────────────────────────┬────────────────────────────────────┘
                                         │ WebSocket
┌────────────────────────────────────────▼────────────────────────────────────┐
│                         AI AGENT SERVICE                                    │
│                         (services/ai-agent)                                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         GEMINI LLM                                   │   │
│  │  - System prompt con DSL completo                                    │   │
│  │  - Conocimiento de campos ScannerTicker                              │   │
│  │  - Conocimiento de categorías y criterios                            │   │
│  │  Output: Código Python/DSL                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                           Código generado                                   │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    DSL EXECUTOR                                      │   │
│  │  - Parsea código generado (AST, no exec directo)                     │   │
│  │  - Traduce Query() a llamadas reales                                 │   │
│  │  - Ejecuta display_table(), create_chart()                           │   │
│  │  - Retorna: { code, result_type, data }                              │   │
│  └───────────────────────────┬─────────────────────────────────────────┘   │
│                              │                                              │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   Redis         │   │  TimescaleDB    │   │  Scanner API    │
│                 │   │                 │   │                 │
│ - snapshots:raw │   │ - tickers_      │   │ - /categories   │
│ - scanner:*     │   │   unified       │   │ - /filtered     │
│ - metadata:*    │   │ - scan_results  │   │ - /gappers      │
│ - streams       │   │                 │   │                 │
└─────────────────┘   └─────────────────┘   └─────────────────┘
```

---

## 📊 Datos Disponibles

### Redis Keys
| Key Pattern | Descripción | Tipo |
|-------------|-------------|------|
| `scanner:filtered` | Tickers filtrados (~500-1000) | JSON List |
| `scanner:categories:{category}` | Tickers por categoría | JSON List |
| `snapshots:raw` | Snapshot completo del mercado | JSON (11k tickers) |
| `metadata:{symbol}` | Metadata de un ticker | JSON |
| `market:session:status` | Estado actual del mercado | JSON |
| `rvol:slots:{symbol}` | RVOL histórico por slots | Hash |

### Redis Streams
| Stream | Descripción | Campos |
|--------|-------------|--------|
| `stream:realtime:aggregates` | Aggregates segundo a segundo | symbol, open, high, low, close, volume, vwap |
| `stream:analytics:rvol` | RVOL calculado | symbol, rvol_slot, rvol_total |
| `stream:ranking:deltas` | Cambios en rankings | category, added, removed, moved |

### TimescaleDB Tables
| Tabla | Descripción |
|-------|-------------|
| `tickers_unified` | Metadata completa (35 campos) |
| `scan_results` | Histórico de scans |

### Modelo ScannerTicker (50+ campos)
```python
# Identidad
symbol: str
timestamp: datetime

# Precios
price: float
bid: Optional[float]
ask: Optional[float]
spread: Optional[float]          # En centavos
spread_percent: Optional[float]  # % del mid price
open: Optional[float]
high: Optional[float]
low: Optional[float]
prev_close: Optional[float]
vwap: Optional[float]
price_vs_vwap: Optional[float]   # % distancia de VWAP

# Intraday extremos
intraday_high: Optional[float]
intraday_low: Optional[float]
price_from_intraday_high: Optional[float]  # % desde HOD
price_from_intraday_low: Optional[float]   # % desde LOD

# Cambios
change: Optional[float]
change_percent: Optional[float]

# Volumen
volume: int
volume_today: int
minute_volume: Optional[int]
avg_volume_5d: Optional[int]
avg_volume_10d: Optional[int]
avg_volume_30d: Optional[int]
avg_volume_3m: Optional[int]
dollar_volume: Optional[float]      # price × avg_volume_10d
volume_today_pct: Optional[float]   # % del avg 10d

# Ventanas de volumen (últimos N minutos)
vol_1min: Optional[int]
vol_5min: Optional[int]
vol_10min: Optional[int]
vol_15min: Optional[int]
vol_30min: Optional[int]

# Ventanas de cambio de precio (últimos N minutos)
chg_1min: Optional[float]
chg_5min: Optional[float]
chg_10min: Optional[float]
chg_15min: Optional[float]
chg_30min: Optional[float]

# Fundamentales
market_cap: Optional[int]
free_float: Optional[int]
free_float_percent: Optional[float]
shares_outstanding: Optional[int]
sector: Optional[str]
industry: Optional[str]
exchange: Optional[str]

# Indicadores calculados
rvol: Optional[float]           # RVOL simple
rvol_slot: Optional[float]      # RVOL del slot actual (5 min)
atr: Optional[float]            # Average True Range
atr_percent: Optional[float]    # ATR como % del precio

# Anomalías
trades_today: Optional[int]
avg_trades_5d: Optional[float]
trades_z_score: Optional[float]     # Z-Score (>=3 = anomalía)
is_trade_anomaly: Optional[bool]

# Post-market
postmarket_change_percent: Optional[float]
postmarket_volume: Optional[int]

# Sesión
session: MarketSession  # PRE_MARKET, MARKET_OPEN, POST_MARKET, CLOSED
```

### Categorías Disponibles
```python
class ScannerCategory(str, Enum):
    GAPPERS_UP = "gappers_up"        # change_percent >= 2%
    GAPPERS_DOWN = "gappers_down"    # change_percent <= -2%
    MOMENTUM_UP = "momentum_up"       # chg_5min >= 1.5% + near HOD + over VWAP + RVOL >= 5
    MOMENTUM_DOWN = "momentum_down"   # change_percent <= -3%
    ANOMALIES = "anomalies"          # trades_z_score >= 3.0
    NEW_HIGHS = "new_highs"          # precio >= 99.9% de intraday_high
    NEW_LOWS = "new_lows"            # precio <= 100.1% de intraday_low
    WINNERS = "winners"              # change_percent >= 5%
    LOSERS = "losers"                # change_percent <= -5%
    HIGH_VOLUME = "high_volume"      # rvol >= 2.0
    REVERSALS = "reversals"          # Gap up cayendo o gap down subiendo
    POST_MARKET = "post_market"      # Activo en post-market
```

---

## 🔧 DSL Query

### Sintaxis
```python
from tradeul import Query, col, display_table, create_chart

# Query básico
total, df = (Query()
    .select('symbol', 'price', 'change_percent', 'volume_today', 'rvol_slot')
    .from_source('scanner')
    .where(
        col('change_percent') >= 5,
        col('rvol_slot') >= 2.0
    )
    .order_by('change_percent', ascending=False)
    .limit(25)
    .execute())

# Mostrar resultados
display_table(df, "Top Gappers con RVOL > 2x")
```

### Fuentes de Datos (.from_source)
| Fuente | Descripción | Redis Key / API |
|--------|-------------|-----------------|
| `'scanner'` | Tickers filtrados | `scanner:filtered` |
| `'gappers_up'` | Gappers alcistas | `GET /api/categories/gappers_up` |
| `'gappers_down'` | Gappers bajistas | `GET /api/categories/gappers_down` |
| `'momentum_up'` | Momentum alcista | `GET /api/categories/momentum_up` |
| `'momentum_down'` | Momentum bajista | `GET /api/categories/momentum_down` |
| `'anomalies'` | Anomalías de trades | `GET /api/categories/anomalies` |
| `'high_volume'` | Alto volumen | `GET /api/categories/high_volume` |
| `'new_highs'` | Nuevos máximos | `GET /api/categories/new_highs` |
| `'new_lows'` | Nuevos mínimos | `GET /api/categories/new_lows` |
| `'winners'` | Top ganadores | `GET /api/categories/winners` |
| `'losers'` | Top perdedores | `GET /api/categories/losers` |
| `'reversals'` | Reversals | `GET /api/categories/reversals` |
| `'post_market'` | Post-market activos | `GET /api/categories/post_market` |
| `'realtime:{symbol}'` | Snapshot de un ticker | `metadata:{symbol}` + snapshot |

### Operadores de Columna
```python
col('field') >= value      # Mayor o igual
col('field') <= value      # Menor o igual
col('field') > value       # Mayor que
col('field') < value       # Menor que
col('field') == value      # Igual
col('field') != value      # Diferente
col('field').between(a, b) # Entre a y b
col('field').isin([...])   # En lista
col('field').contains('x') # Contiene string
col('field').is_null()     # Es nulo
col('field').not_null()    # No es nulo
```

### Funciones de Display
```python
# Tabla
display_table(df, "Título de la tabla")
display_table(df, "Título", columns=['symbol', 'price', 'change_percent'])

# Gráficos
create_chart(df, type='bar', x='symbol', y='change_percent', title="...")
create_chart(df, type='scatter', x='change_percent', y='rvol_slot', size='volume_today')
create_chart(df, type='line', x='timestamp', y='price', title="...")
create_chart(df, type='heatmap', x='sector', y='change_percent', title="...")

# Métricas
print_stats(df, ['change_percent', 'volume_today', 'rvol_slot'])
```

---

## 🔐 Seguridad del DSL

### Validaciones
1. **Whitelist de fuentes**: Solo fuentes definidas en `ALLOWED_SOURCES`
2. **Whitelist de columnas**: Solo campos de `ScannerTicker`
3. **Límites**: `limit` máximo de 500
4. **Sin exec()**: El código se parsea con AST, no se ejecuta directamente
5. **Timeout**: Máximo 30 segundos por ejecución
6. **Rate limiting**: Máximo 10 queries/minuto por usuario

### Campos Permitidos
```python
ALLOWED_COLUMNS = [
    'symbol', 'price', 'bid', 'ask', 'spread', 'spread_percent',
    'open', 'high', 'low', 'prev_close', 'vwap', 'price_vs_vwap',
    'intraday_high', 'intraday_low', 'price_from_intraday_high', 'price_from_intraday_low',
    'change', 'change_percent',
    'volume', 'volume_today', 'minute_volume',
    'avg_volume_5d', 'avg_volume_10d', 'avg_volume_30d', 'avg_volume_3m',
    'dollar_volume', 'volume_today_pct',
    'vol_1min', 'vol_5min', 'vol_10min', 'vol_15min', 'vol_30min',
    'chg_1min', 'chg_5min', 'chg_10min', 'chg_15min', 'chg_30min',
    'market_cap', 'free_float', 'free_float_percent', 'shares_outstanding',
    'sector', 'industry', 'exchange',
    'rvol', 'rvol_slot', 'atr', 'atr_percent',
    'trades_today', 'avg_trades_5d', 'trades_z_score', 'is_trade_anomaly',
    'postmarket_change_percent', 'postmarket_volume',
    'session', 'timestamp'
]
```

---

## 🖥️ Frontend Components

### AIAgentWindow (FloatingWindow)
```tsx
// Usa el sistema existente de FloatingWindowContext
interface AIAgentWindowProps {
  // Hereda de FloatingWindow existente
}

// Layout interno: 30% chat, 70% resultados
<div className="flex h-full">
  <ChatPanel className="w-[30%]" />
  <ResultsPanel className="w-[70%]" />
</div>
```

### ChatPanel
```tsx
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  status?: 'thinking' | 'executing' | 'complete' | 'error';
  toolCalls?: ToolCall[];
}

interface ToolCall {
  name: string;
  status: 'pending' | 'running' | 'complete' | 'error';
  blockId?: number;  // Referencia al ResultBlock
}
```

### ResultsPanel
```tsx
interface ResultBlock {
  id: number;
  title: string;
  status: 'running' | 'success' | 'error';
  code: string;           // Código DSL generado
  codeVisible: boolean;   // Toggle para mostrar/ocultar
  resultType: 'table' | 'chart' | 'text' | 'error';
  data: TableData | ChartData | string;
  timestamp: Date;
}

interface TableData {
  columns: string[];
  rows: Record<string, any>[];
  total: number;
}

interface ChartData {
  type: 'bar' | 'scatter' | 'line' | 'heatmap';
  plotlyConfig: object;  // Configuración completa de Plotly
}
```

---

## 🔄 Integración con Servicios Existentes

### EventBus
```python
# El AI Agent se suscribe a eventos relevantes
event_bus.subscribe(EventType.SESSION_CHANGED, handle_session_changed)
event_bus.subscribe(EventType.DAY_CHANGED, handle_day_changed)

# Para notificar al usuario si el mercado cambia durante una conversación
async def handle_session_changed(event: Event):
    new_session = event.data['new_session']
    # Notificar a los clientes WebSocket conectados
    await notify_clients(f"Market session changed to {new_session}")
```

### Redis Streams
```python
# Consumir aggregates en tiempo real si el usuario lo solicita
async def stream_ticker_updates(symbol: str):
    async for message in redis_client.xread({'stream:realtime:aggregates': '$'}):
        if message['symbol'] == symbol:
            yield message
```

### Scanner API
```python
# Reutilizar endpoints existentes del scanner
async def get_category_data(category: str, limit: int):
    async with http_clients.internal.get(
        f"http://scanner:8005/api/categories/{category}",
        params={'limit': limit}
    ) as response:
        return await response.json()
```

---

## 📡 WebSocket Protocol

### Cliente → Servidor
```json
{
  "type": "chat_message",
  "content": "Find me stocks down 3%+ with high RVOL",
  "conversation_id": "conv_123"
}
```

### Servidor → Cliente (Streaming)
```json
// Inicio de respuesta
{
  "type": "response_start",
  "message_id": "msg_456"
}

// Texto del asistente (streaming)
{
  "type": "assistant_text",
  "message_id": "msg_456",
  "delta": "I'll search for..."
}

// Ejecución de código
{
  "type": "code_execution",
  "message_id": "msg_456",
  "block_id": 1,
  "status": "running",
  "code": "total, df = (Query()..."
}

// Resultado
{
  "type": "result",
  "message_id": "msg_456",
  "block_id": 1,
  "status": "success",
  "result_type": "table",
  "data": { ... }
}

// Fin de respuesta
{
  "type": "response_end",
  "message_id": "msg_456"
}
```

---

## 📁 Estructura de Archivos

```
services/ai-agent/
├── Dockerfile
├── requirements.txt
├── main.py                    # FastAPI app
├── config.py                  # Configuración
├── llm/
│   ├── __init__.py
│   ├── gemini_client.py       # Cliente de Gemini
│   └── prompts.py             # System prompts
├── dsl/
│   ├── __init__.py
│   ├── query.py               # Clase Query()
│   ├── column.py              # Clase col()
│   ├── display.py             # display_table(), create_chart()
│   └── executor.py            # DSL Executor (parsea y ejecuta)
├── data/
│   ├── __init__.py
│   ├── redis_source.py        # Acceso a Redis
│   ├── scanner_source.py      # Acceso al Scanner API
│   └── timescale_source.py    # Acceso a TimescaleDB
└── ws/
    ├── __init__.py
    └── handler.py             # WebSocket handler

frontend/components/ai-agent/
├── AIAgentWindow.tsx          # Ventana principal
├── ChatPanel.tsx              # Panel de chat
├── ChatMessage.tsx            # Mensaje individual
├── ResultsPanel.tsx           # Panel de resultados
├── ResultBlock.tsx            # Bloque de resultado
├── CodeBlock.tsx              # Código colapsable con syntax highlight
├── DataTable.tsx              # Tabla de resultados
└── Chart.tsx                  # Gráfico (Plotly)
```

---

## 🚀 Próximos Pasos

1. **Revisar esta especificación** y ajustar según feedback
2. **Implementar DSL Query** con validaciones
3. **Crear servicio ai-agent** con FastAPI
4. **Implementar componentes frontend**
5. **Integrar con FloatingWindowContext**
6. **Testing end-to-end**

---

## 🛡️ Optimizaciones Implementadas

### 1. Caché Local en Memoria
Para evitar el cuello de botella de deserializar JSON grandes de Redis en cada request:

```python
class LocalCache:
    """
    Caché local que se actualiza cada 1.5 segundos en background.
    Los usuarios no notan latencia de 1-2 segundos en queries de lenguaje natural.
    """
    ttl = 2.0  # segundos
```

### 2. Auto-Heal para Alucinaciones del LLM
Cuando el LLM genera código inválido:

```python
async def execute_with_retry(code, max_retries=2):
    result = await executor.execute(code)
    if not result.success:
        # Pedir al LLM que corrija el código
        fixed_code = await gemini_client.fix_code(code, result.error)
        result = await executor.execute(fixed_code)
    return result
```

### 3. Contexto de Refinamiento
Para soportar conversaciones como:
```
Usuario: "Muestra RVOL > 3"
Usuario: "Filtrame solo tech"  <-- Sabe que se refiere al resultado anterior
```

Se inyecta en el prompt:
```
## RESULTADO ANTERIOR
El usuario está viendo una tabla "Top RVOL" con 50 filas.
Columnas: symbol, price, rvol_slot
Símbolos: AAPL, TSLA, NVDA...
```

### 4. Guardrail de Gráficos
Límite de 500 puntos para evitar colapsar el navegador:

```python
MAX_CHART_POINTS = 500

def create_chart(df, ...):
    if len(df) > MAX_CHART_POINTS:
        raise ChartLimitError("Demasiados datos. Filtra a menos de 500 puntos.")
```

---

## 📝 Notas

- El servicio se integra con el EventBus existente para recibir cambios de sesión
- Usa el RedisClient y TimescaleClient compartidos
- Reutiliza el sistema de FloatingWindow del frontend
- El DSL es seguro (no usa exec()) y tiene validaciones estrictas
- El LLM solo genera código, no tiene acceso directo a los datos

