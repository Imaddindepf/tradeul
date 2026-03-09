# Cómo se ejecuta un backtest — motor y flujos de uso

Explicación clara de **qué es el motor de ejecución**, **quién lo invoca** y **cómo lo prueba el usuario**.

---

## 1. ¿Tenemos “motor de ejecución”?

Sí. El **motor de ejecución del backtest** es el **servicio backtester** (microservicio en Python):

- **No** es un motor de ejecución de órdenes en vivo (no envía órdenes al broker).
- **Sí** es el motor que **simula** la estrategia sobre datos históricos: carga datos, genera señales, simula entradas/salidas, calcula métricas y devuelve el resultado.

Ese motor vive en:

- `services/backtester/`: FastAPI (`main.py`) + `BacktestEngine` y `CodeExecutor` en `core/`.

---

## 2. Qué hace el motor (por dentro)

Cuando “se ejecuta un backtest”, el motor hace algo equivalente a:

1. **Cargar datos** (DataLayer): FLATS day/minute + REST si hace falta, ajustado por splits.
2. **Añadir indicadores** (DuckDB): gap_pct, rvol, RSI, SMA, etc.
3. **Generar señales** según el modo:
   - **Template:** evalúa `entry_signals` y `exit_rules` sobre el DataFrame → máscaras de entrada/salida.
   - **Code:** ejecuta `strategy(bars)` en un sandbox → lista de trades.
4. **Simular portfolio** (solo en modo template): loop por ticker/barra, aplica entry_timing, fill (slippage/comisión), exit rules → lista de `TradeRecord`.
5. **Calcular métricas**: core (Sharpe, win rate, drawdown, etc.), opcionalmente advanced, walk-forward, Monte Carlo.
6. **Devolver** `BacktestResult` (trades, equity curve, métricas, etc.) en JSON.

Todo eso ocurre **dentro del servicio backtester**; no hay otro “motor” separado.

---

## 3. Cómo lo invoca el usuario (dos flujos)

El usuario puede ejecutar un backtest de **dos maneras** en la arquitectura actual:

---

### 3.1 Flujo A: API directa (template o código)

Alguien (frontend, script, Postman, otra API) llama **directamente al backtester** con un JSON ya definido.

| Endpoint | Qué envías | Qué hace el motor |
|----------|------------|--------------------|
| `POST /api/v1/backtest` | `BacktestRequest`: `strategy` (StrategyConfig JSON), opciones (walk_forward, monte_carlo, etc.) | Parsea la estrategia (señales, exit rules, fechas, tickers), carga datos, añade indicadores, **simula** con el engine (loop por barra), calcula métricas, devuelve `BacktestResponse`. |
| `POST /api/v1/backtest/code` | `CodeBacktestRequest`: `code` (Python con `strategy(bars)`), `tickers`, `timeframe`, `start_date`, `end_date`, capital, slippage, etc. | Carga datos para esos tickers y fechas, añade indicadores, **ejecuta** el código en sandbox (`CodeExecutor`), convierte los trades devueltos por `strategy(bars)` a `TradeRecord`, calcula métricas, devuelve `BacktestResponse`. |

- **Template:** el “motor de simulación” es `BacktestEngine._simulate()` (loop por ticker/barra).
- **Code:** el “motor” es `CodeExecutor.execute()` (ejecuta tu Python; la simulación la hace tu código, el servicio solo aplica slippage/comisión al convertir trades y calcula métricas).

En ambos casos **quien ejecuta el backtest es el servicio backtester**; el usuario (o la app) solo envía la petición HTTP con el payload correcto.

**Ejemplo mínimo (template):**

```bash
curl -X POST "https://backtester.tradeul.com/api/v1/backtest" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": {
      "name": "RSI mean reversion",
      "universe": { "method": "ticker_list", "tickers": ["SPY"] },
      "entry_signals": [{"indicator": "rsi_14", "operator": "<", "value": 30}],
      "exit_rules": [{"type": "target", "value": 0.02}, {"type": "stop_loss", "value": 0.01}],
      "entry_timing": "next_open",
      "timeframe": "1d",
      "start_date": "2023-01-01",
      "end_date": "2024-12-31",
      "initial_capital": 100000,
      "max_positions": 5,
      "position_size_pct": 0.10,
      "direction": "long"
    },
    "include_advanced_metrics": true,
    "include_walk_forward": true,
    "include_monte_carlo": true
  }'
```

**Ejemplo mínimo (código ORB/RVOL):**

```bash
curl -X POST "https://backtester.tradeul.com/api/v1/backtest/code" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def strategy(bars):\n  ... (tu código Python) ...",
    "tickers": ["SPY"],
    "timeframe": "5min",
    "start_date": "2025-01-01",
    "end_date": "2025-02-28",
    "initial_capital": 100000,
    "strategy_name": "ORB RVOL"
  }'
```

El usuario “prueba el backtest” usando una herramienta que haga esas llamadas (tu frontend, un script, Postman, etc.).

---

### 3.2 Flujo B: Lenguaje natural (vía AI Agent)

El usuario **no** manda JSON; escribe en lenguaje natural en el **chat del AI Agent** (por ejemplo con el comando `/backtest` o diciendo “backtest comprar cuando RSI &lt; 30 en SPY, stop 5%, target 10%”).

Flujo:

1. Usuario escribe en el chat del agente (frontend del agente).
2. El **supervisor** del agente detecta intención BACKTEST y envía el mensaje + tickers al **backtest agent**.
3. El **backtest agent** (`agents/backtest.py`):
   - Clasifica si la estrategia se puede expresar con **template** o hace falta **code**.
   - **Si template:** usa un LLM para convertir el texto en un `StrategyConfig` JSON y llama al backtester: `POST {BACKTESTER_URL}/api/v1/backtest` con ese JSON.
   - **Si code:** usa un LLM para generar el Python `strategy(bars)` y metadata (tickers, fechas, timeframe), y llama al backtester: `POST {BACKTESTER_URL}/api/v1/backtest/code` con código + metadata.
4. El **backtester** (el mismo motor de arriba) ejecuta el backtest y devuelve `BacktestResponse`.
5. El agente devuelve ese resultado al usuario (en el chat), y el frontend puede mostrarlo en un panel de resultados (gráficos, métricas, trades).

Aquí el “usuario” ejecuta el backtest **escribiendo en lenguaje natural**; el **motor de ejecución sigue siendo el servicio backtester**; el agente solo traduce y orquesta la llamada.

---

## 4. Frontend y endpoint “/natural”

En el frontend existe un hook `useBacktester` que hace:

- `POST {BACKTESTER_URL}/api/v1/backtest/natural`  
- Body: `{ "prompt": "..." }`

En el código actual del backtester **no existe** el endpoint `POST /api/v1/backtest/natural`. Por tanto:

- **Si** el frontend usa ese hook contra la URL del **backtester**, esa ruta fallaría (404) a menos que se añada.
- **Opciones de diseño:**
  - **A)** Añadir en el backtester un endpoint `/api/v1/backtest/natural` que reciba `{ "prompt" }`, llame internamente a un LLM (o a un servicio de parsing) para obtener StrategyConfig o código, y luego llame a `run_backtest` o a `run_code_backtest` (el backtester tendría que tener o llamar a un LLM).
  - **B)** Hacer que el frontend **no** llame al backtester para “natural”, sino al **AI Agent** (por ejemplo un endpoint del agente tipo “run backtest from prompt”), y que sea el agente quien hable con el backtester (`/api/v1/backtest` o `/api/v1/backtest/code`). En ese caso el usuario “prueba el backtest” desde el chat del agente, no desde una pantalla que llame solo al backtester.

Así que: **el motor de ejecución es siempre el backtester**; la duda es si “probar por lenguaje natural” se hace exponiendo un `/natural` en el backtester o unificando todo por el AI Agent.

---

## 5. Resumen para el usuario

| Pregunta | Respuesta |
|----------|-----------|
| ¿Tenemos motor de ejecución? | Sí: el **servicio backtester** (BacktestEngine + CodeExecutor). |
| ¿Qué “ejecuta”? | La **simulación** del backtest (datos → señales → simulación de trades → métricas). No ejecuta órdenes reales. |
| ¿Cómo prueba el usuario un backtest? | **(1)** Llamando a la API del backtester con JSON (template o code). **(2)** Escribiendo en lenguaje natural en el chat del AI Agent (el agente traduce y llama al backtester). |
| ¿Quién corre el backtest? | Siempre el **backtester**; desde fuera solo se le invoca por HTTP (por API directa o por el agente). |

Para “probar” un backtest ORB/RVOL u otro:

- **Por API:** el usuario (o tu app) envía `POST /api/v1/backtest/code` con el código Python de `strategy(bars)` y los parámetros (tickers, fechas, timeframe).
- **Por lenguaje natural:** el usuario escribe la estrategia en el chat del agente; el agente genera el código (o el config), llama al backtester y muestra el resultado.

Si quieres que haya una pantalla en el frontend que “solo escribo un prompt y corre el backtest”, hace falta o bien implementar `/natural` en el backtester (y que el backtester tenga o llame a un LLM) o bien que esa pantalla llame al AI Agent y muestre la respuesta del agente (que ya incluye el resultado del backtest).
