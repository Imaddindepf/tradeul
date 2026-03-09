# Cómo haría el backtester profesional

Plan concreto, por fases, sin reescribir el engine. Se construye sobre lo que ya existe.

---

## Principio

- **Un solo engine** (`BacktestEngine`), un solo flujo (`run` → datos → señales → `_simulate` → métricas).
- Las mejoras son **parametrización y capas opcionales**: quien no las use sigue igual que ahora.
- Prioridad: **timing intraday** → **UniverseSelector** → **trade inspection** (API/export).

---

## Fase 1: Timing intraday (entry/exit en minutos)

**Objetivo:** Poder decir “entrar 10 minutos después del open” y “salir 30 minutos antes del cierre” (o “N minutos después de entrada”), como Trade Ideas.

### 1.1 Modelo

En `StrategyConfig` (o en un bloque opcional `IntradayTiming`):

```python
# models.py — añadir a StrategyConfig o nuevo modelo
class IntradayTiming(BaseModel):
    """Solo aplica cuando timeframe es intraday (minute)."""
    entry_start_minutes_after_open: int | None = None   # no entrar antes de N min
    entry_end_minutes_before_close: int | None = None   # no entrar después (ej. 60 = última hora sin entradas)
    exit_minutes_after_entry: int | None = None        # salir N minutos después de entrada (TIME ya existe en barras)
    exit_minutes_before_close: int | None = None       # forzar salida M min antes del cierre
```

- Si `timeframe == DAY_1`, se ignoran.
- Si son `None`, comportamiento actual (open/close/next_open).

### 1.2 Dónde actuar

1. **Entrada:** En `_simulate`, al evaluar “¿entramos en barra `i`?”:
   - Si hay `entry_start_minutes_after_open`: no entrar si `minutes_since_session_start(i) < entry_start_minutes_after_open`.
   - Si hay `entry_end_minutes_before_close`: no entrar si `minutes_until_session_end(i) < entry_end_minutes_before_close` (o equivalente: solo si estamos “suficiente antes del cierre”).
   - Para eso necesitas **por cada barra** el minuto del día (o el índice de barra dentro del día). Si los datos son 1min y tienen `timestamp`, `minutes_since_open = (timestamp - session_open_time).total_seconds() // 60`.

2. **Salida:**
   - `exit_minutes_after_entry`: ya lo cubre `ExitType.TIME` con `value = N` (barras). Solo hay que documentar que en intraday “TIME en barras” = “minutos si es 1min”.
   - `exit_minutes_before_close`: en `_check_exit`, añadir una regla implícita o un nuevo `ExitType.MINUTES_BEFORE_CLOSE` que compruebe `minutes_until_session_end(bar) <= exit_minutes_before_close` → salir.

### 1.3 Cálculo de “minutos desde open / hasta close”

- En **day bars** no tiene sentido; no se usa.
- En **minute bars**: si `timestamp` está en el DataFrame, por cada sesión (por día) puedes hacer:
  - `session_open` = 9:30, `session_close` = 16:00 (configurable después).
  - Por barra: `minute_of_day = (bar["timestamp"] - date_at_9_30).total_seconds() / 60`.
  - `minutes_until_close = (date_at_16_00 - bar["timestamp"]).total_seconds() / 60`.

Implementación práctica: en `_simulate`, al iterar por ticker, construir una vez por día un `first_bar_ts` y `last_bar_ts` (o min/max de timestamp por fecha), y por cada barra calcular minutos desde `first_bar_ts` y minutos hasta `last_bar_ts`. Así no dependes de un reloj fijo 9:30/16:00 si algún día los datos empiezan/terminan distinto.

### 1.4 Resumen Fase 1

| Cambio | Archivo | Qué hacer |
|--------|---------|-----------|
| Modelo `IntradayTiming` | `models.py` | Añadir clase; en `StrategyConfig` añadir `intraday_timing: IntradayTiming | None = None`. |
| Entrada: filtrar por minutos | `engine.py` `_simulate` | Antes de considerar entrada en barra `i`, si `intraday_timing` está definido, comprobar ventana en minutos; si no estamos dentro, no entrar. |
| Salida: minutos antes del cierre | `engine.py` `_check_exit` | Si `exit_minutes_before_close` está definido, comprobar `minutes_until_close <= value` → return True. |
| Helpers minutos | `engine.py` o `utils` | Función que, dado un DataFrame de barras de un ticker y un `date_col`/`timestamp`, devuelva para cada barra `minutes_since_open` y `minutes_until_close` (por día). |

Con esto el backtester ya ofrece “ventana horaria” y “salida antes del cierre” sin tocar el resto del flujo.

---

## Fase 2: Universe por día (Pipeline light)

**Objetivo:** Que cada día el universo no sea “siempre los mismos tickers”, sino el resultado de un screening (liquidez, precio, MA, etc.), como QuantRocket.

### 2.1 Idea

- Hoy: `strategy.universe.tickers` es una lista fija; se cargan todos los datos de una vez.
- Máximo nivel: opcionalmente, `universe` puede ser un **pipeline** que, por cada fecha de trading, devuelve un set de tickers candidatos. El engine:
  1. Itera por fecha (o por bloques de fechas).
  2. Para cada fecha, llama al pipeline → obtiene tickers del día.
  3. Carga datos solo para esos tickers (y quizá un buffer para indicadores que necesiten historia).
  4. Genera señales y simula solo ese día (o junta los datos y simula con la lógica actual, pero las entradas solo se permiten en tickers que estaban en el universo ese día).

La opción más simple que no obliga a reescribir todo: **precomputar el universo por día** antes de `run`.

### 2.2 Diseño minimal

- **UniverseSelector**: función o clase que recibe `(date, data_layer?)` y devuelve `list[str]` (tickers).
  - Implementación 1: “top N por volumen del día anterior” (necesita day bars del día anterior).
  - Implementación 2: “precio entre A y B, volumen > X” (mismo dato).
- **Cambio en el engine:** En lugar de “cargar todos los datos de [start, end] para tickers fijos”, si `strategy.universe.method == UniverseMethod.PIPELINE` (o similar):
  1. Obtener lista de fechas en [start, end].
  2. Para cada fecha, llamar al selector → union de todos los tickers que alguna vez fueron candidatos (o por bloques semanales para no hacer 252 llamadas).
  3. Cargar datos para ese conjunto más grande.
  4. En `_simulate`, al evaluar entrada en barra `i` (fecha `d`, ticker `T`): además de las condiciones actuales, exigir que `T in universe_for_date(d)`.

Para no cargar datos por día (lento), la opción pragmática: **cargar una vez** para un “superconjunto” de tickers (p.ej. S&P 500 o “todos los que alguna vez salieron del pipeline”), y en simulación **filtrar entradas** por “¿este ticker estaba en el universo este día?”. El pipeline entonces se ejecuta día a día sobre los datos que ya tienes (por ejemplo sobre day_aggs del día anterior) y produce un mapa `date -> set(tickers)` que el engine usa solo para el chequeo de entrada.

### 2.3 Dónde actuar

| Cambio | Archivo | Qué hacer |
|--------|---------|-----------|
| `UniverseMethod.PIPELINE` | `models.py` | Añadir enum; en `UniverseFilter` algo como `pipeline_id: str \| None` o `pipeline_config: dict`. |
| Selector por día | Nuevo `universe_selector.py` | `def get_universe_for_dates(data_layer, start, end, config) -> dict[date, set[str]]` que itera fechas y para cada una aplica reglas (liquidez, precio, etc.) usando day bars; devuelve el mapa. |
| Carga de datos | `engine.py` `run` | Si universe es pipeline: (1) llamar a `get_universe_for_dates` para [start, end]; (2) unir todos los tickers → lista; (3) cargar bars para esa lista (igual que ahora); (4) pasar `universe_by_date` a `_simulate`. |
| Condición de entrada | `engine.py` `_simulate` | Si `universe_by_date` no es None, al evaluar entrada en (ticker, fecha) comprobar `ticker in universe_by_date.get(bar_date, set())`. |

Así el “universe dinámico” es una capa opcional: quien no la use sigue con lista fija.

---

## Fase 3: Trade inspection y resultados “estilo Oddsmaker”

**Objetivo:** No solo devolver métricas, sino que las trades sean consultables, filtrables y exportables (calendario por día, lista de trades, CSV).

### 3.1 Ya tenemos

- `BacktestResult.trades`: lista de `TradeRecord` con ticker, entry/exit date, prices, PnL, etc.
- Con eso se puede ya: agrupar por día, por ticker, ordenar por PnL, calcular “best/worst day”.

### 3.2 Lo que añadiría

1. **Módulo de inspección** (p.ej. `inspection.py` o dentro de `metrics.py`):
   - `trades_by_date(result: BacktestResult) -> dict[str, list[TradeRecord]]`
   - `trades_by_ticker(result: BacktestResult) -> dict[str, list[TradeRecord]]`
   - `daily_summary(result: BacktestResult) -> DataFrame` (fecha, PnL día, nº trades, win rate día)
   - `to_dataframe(result: BacktestResult) -> DataFrame` (cada fila = trade, columnas = campos de TradeRecord)

2. **API (si hay backend de backtester):**
   - `GET /backtest/{run_id}/trades?date=2024-01-15&ticker=AAPL` → lista de trades filtrada.
   - `GET /backtest/{run_id}/trades/export?format=csv` → CSV de todas las trades (o filtrado por query params).

3. **Frontend (más adelante):**
   - Calendario: cada día con color por PnL; hover = resumen del día; doble clic = abrir lista de trades de ese día (llamando a la API de inspección).
   - Tabla de trades con ordenación y filtros.

La Fase 3 no cambia el engine; solo usa `BacktestResult.trades` y expone helpers + API + UI.

---

## Fase 4 (opcional): Position size en $ y comisión por share

- **Position size:** Hoy solo `position_size_pct`. Añadir `position_size_mode: "pct" | "dollars" | "shares"` y `position_size_value: float`. En `_simulate`, al calcular `pv` (position value): si dollars → `pv = min(position_size_value, equity * max_pct)`, si shares → `pv = position_size_value * fill_price`.
- **Comisión por share:** En `FillResult` y `estimate_fill`, añadir `commission_per_share` y aplicarlo: `commission = commission_per_trade + shares * commission_per_share`. En `StrategyConfig`: `commission_per_share: float = 0.0`.

---

## Orden de implementación recomendado

1. **Fase 1 (timing intraday)** — poco código, alto impacto para estrategias tipo opening range / sell-on-gap.
2. **Fase 3 (trade inspection)** — solo helpers + API sobre datos existentes; no toca el loop de simulación.
3. **Fase 2 (universe por día)** — más diseño (cómo se define el pipeline en config); se puede hacer “pipeline simple” (top N por volumen día anterior) primero.
4. **Fase 4** — cuando quieras paridad con Trade Ideas en capital/costes.

---

## Resumen en una frase

**Haría el backtester profesional ampliando el engine actual con (1) ventana de entrada/salida en minutos, (2) universo por día opcional como filtro de entrada, y (3) una capa de inspección y export sobre las trades que ya devolvemos; sin reescribir el core.**
