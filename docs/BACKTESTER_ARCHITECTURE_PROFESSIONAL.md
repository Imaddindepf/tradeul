# Arquitectura del backtester: ingeniería inversa vs profesionales (QuantRocket / Zipline / Trade Ideas)

## Objetivo

Construir un backtester profesional. Este documento compara nuestro flujo actual con el de QuantRocket/Zipline (ejemplo Sell-on-Gap) y Trade Ideas, y propone una arquitectura alineada.

---

## 1. Flujo profesional (QuantRocket Sell-on-Gap)

El ejemplo **Sell-on-Gap** sigue 6 partes claras:

| Parte | Nombre | Qué hace |
|-------|--------|----------|
| **1** | Historical Data Collection | Recopilar datos históricos (bundles: daily + minute). Sin esto no hay backtest. |
| **2** | Universe Selection | Definir **qué acciones** pueden ser candidatas cada día. Pipeline con reglas: top 10% dollar volume, above 20d MA, price 10–2000, common stocks only. Se ejecuta **por fecha** y devuelve un conjunto dinámico. |
| **3** | Interactive Strategy Development | Probar lógica de entrada/salida en notebooks (gap down 1σ, open below MA, short 10 min after open, close 5 min before close). |
| **4** | Zipline Strategy Code | Código del algo: `initialize()` → pipeline + schedule; `before_trading_start()` → pipeline output del día; `find_down_gaps()` 9:31; `short_down_gaps()` 9:40; `close_positions()` 5 min antes del cierre. |
| **5** | Backtest | Ejecutar `backtest("sell-gap", start_date=..., end_date=..., capital_base=...)` → CSV + pyfolio tear sheet. |
| **6** | Trade Inspection | Inspección de trades individuales, análisis de resultados. |

**Ideas clave:**

- **Universe es dinámico por día**: no es “estos 3 tickers”, sino “cada día, los que pasan el pipeline”. Pipeline = `initial_universe` + `columns` (factores) + `screen` (filtros).
- **Timing explícito**: entradas/salidas atadas a horarios (9:31, 9:40, 5 min antes del cierre).
- **Separación clara**: datos → universo → lógica → backtest → inspección.

---

## 2. Nuestro flujo actual (Tradeul backtester)

### 2.1 Componentes

| Componente | Rol |
|------------|-----|
| **DataLayer** | FLATS (day + minute adjusted) + REST; carga por `(start, end, tickers)`. |
| **StrategyConfig** | `UniverseFilter` (ALL_US, TICKER_LIST, SQL_FILTER), entry_signals, exit_rules, timeframe, capital, slippage, etc. |
| **BacktestEngine** | 1) Cargar barras para `strategy.universe.tickers` 2) Filtrar con `sql_where` si hay 3) Añadir indicadores 4) Evaluar señales 5) Simular portfolio (entradas/salidas por barra). |
| **Code path** | `strategy(bars)` Python generado por LLM; mismo engine con barras pre-cargadas. |

### 2.2 Flujo efectivo

```
Usuario/LLM → tickers (lista fija) + fechas + señales/salidas
       → DataLayer.load_*_adjusted(start, end, tickers)
       → add_indicators_sql(bars_df)
       → evaluate_entries(bars_df, entry_signals)
       → _simulate() (loop por ticker, por barra)
       → BacktestResult (trades, equity, metrics)
```

- **Universe**: viene dado como **lista fija de tickers** (o ALL_US resuelto fuera). No hay “pipeline que cada día devuelve candidatos”.
- **Timing**: `entry_timing` = open / close / next_open a nivel de barra; no hay horarios intraday tipo “10 min después del open” o “5 min antes del cierre” como primitivas.
- **Datos**: Part 1 está cubierta (FLATS + REST, histórico). No hay “Part 2” como servicio reutilizable (universe selection como pipeline ejecutable día a día).

---

## 3. Diferencias arquitectónicas (gap)

| Aspecto | QuantRocket / Zipline | Tradeul actual |
|---------|------------------------|----------------|
| **Universe** | Pipeline que corre **por fecha**; output = conjunto de activos por día. Puede depender de MA, dollar volume, sector, etc. | Lista fija de tickers (o SQL sobre barras ya cargadas). No hay “universe por día” como primera clase. |
| **Orden del flujo** | 1) Datos 2) Universe (pipeline) 3) Estrategia (usa output del pipeline cada día) 4) Backtest 5) Inspección | 1) Tickers + fechas 2) Cargar todo 3) Indicadores 4) Señales 5) Simular. Universe no es una fase separada. |
| **Intraday timing** | Funciones programadas a horas concretas (9:31, 9:40, 15:55). | Siguiente barra open/close o barra actual. No “N minutos después del open”. |
| **Reutilización** | Pipeline se define una vez y se usa en research y en el algo. | Filtro SQL opcional; no hay “Pipeline API” reutilizable. |
| **Trade inspection** | Part 6 explícita (análisis de trades). | Tenemos `TradeRecord` y lista de trades; no hay módulo/UI dedicado de “trade inspection”. |

---

## 4. Propuesta de arquitectura (hacia backtester profesional)

Objetivo: acercarnos al flujo **Datos → Universe → Estrategia → Backtest → Inspección** sin reescribir todo de golpe.

### 4.1 Fase 1: Universe como primera clase (Pipeline / Universe Selection)

- **Concepto**: Introducir un **UniverseSelector** (o “Pipeline light”) que, dado un rango de fechas, devuelve **por cada fecha** el conjunto de tickers que pasan unas reglas.
- **Reglas típicas** (como en Sell-on-Gap):
  - Liquidez: top X% por dollar volume (necesitamos volume * close en daily).
  - Precio: min/max (ej. 10–2000).
  - Técnicos: close > SMA(20), etc.
  - Tipo: solo common stocks (si tenemos metadata).
- **Implementación posible**:
  - Opción A: Pipeline en DuckDB sobre `day_aggs`: por cada fecha, agregar indicadores (SMA, dollar volume rank) y aplicar filtros → tabla `(date, ticker)`.
  - Opción B: Mantener lista fija para el 80% de casos; para estrategias “estilo QuantRocket” el LLM o el usuario definen “universe: top 10% dollar volume, above 20d MA” y el backtester lo traduce a una ejecución pipeline por día.
- **Salida**: En lugar de `strategy.universe.tickers` fijo, el engine podría recibir “universe = pipeline_id” y, cada día del backtest, cargar solo los tickers que devolvió el pipeline para esa fecha. Así el backtest sería **universe dinámico**.

### 4.2 Fase 2: Timing intraday explícito

- **Concepto**: Poder expresar “entrar 10 minutos después del open” y “salir 5 minutos antes del close” sin depender solo de la barra siguiente.
- **Implementación**:
  - En timeframe minuto: definir “anchors” (market_open, market_close) y offsets en minutos (e.g. entry_delay_minutes=10, exit_minutes_before_close=5). En el loop de simulación, en cada barra comprobar si la barra actual es la “barra de entrada” (open + 10 min) o “barra de salida” (close − 5 min).
  - Mantener compatibilidad con `entry_timing` actual (open/close/next_open) para estrategias diarias o simples.

### 4.3 Fase 3: Partes 1–6 como flujo documentado y APIs

- **Part 1 – Historical Data**: Ya lo tenemos (DataLayer, FLATS, REST). Mejora: ampliar histórico day_aggs cuando se decida.
- **Part 2 – Universe Selection**: Fase 1 anterior.
- **Part 3 – Interactive Strategy Development**: Hoy es “probamos en el agente con un backtest”. Opcional: notebooks o endpoint “dry run” que devuelva señales/trades sin ejecutar backtest completo.
- **Part 4 – Strategy Code**: Ya tenemos template (StrategyConfig) y code (strategy(bars)). Mejora: que el código generado pueda usar “universe del día” si existe pipeline.
- **Part 5 – Backtest**: Ya existe. Mejora: mismo engine alimentado por universe dinámico y timing intraday.
- **Part 6 – Trade Inspection**: Endpoint o vista que, dado un `BacktestResult`, permita filtrar/ordenar trades, ver por ticker, por fecha, por PnL, y exportar. Los datos ya están en `BacktestResult.trades`.

### 4.4 Resumen de prioridades

1. **Universe dinámico (Pipeline)** → mayor impacto para estrategias “top N por liquidez + filtro técnico” como Sell-on-Gap.
2. **Timing intraday** (minutos después del open / antes del cierre) → necesario para replicar estrategias estilo QuantRocket.
3. **Trade inspection** → mejora de producto (análisis post-backtest) sin cambiar el core del engine.

---

## 5. Ejemplo Sell-on-Gap mapeado a nuestro modelo actual

| Regla Sell-on-Gap | En Zipline | En Tradeul hoy | Con mejoras propuestas |
|-------------------|------------|-----------------|-------------------------|
| Universe: top 10% dollar volume | `AverageDollarVolume(30).percentile_between(90,100)` | No existe; sería lista fija o SQL ad hoc. | Pipeline: rank dollar volume, filtrar percentil 90–100 por fecha. |
| Universe: above 20d MA | `EquityPricing.close.latest > SimpleMovingAverage(20)` | Posible vía `sql_where` sobre indicadores ya añadidos, pero sobre todos los tickers cargados. | Pipeline: por fecha, close > SMA(20). |
| Entry: gap down ≥1σ, open below MA, short 10 min after open | `short_down_gaps()` at 9:40 | Señal “gap_pct < -1*std” y “open < MA” se pueden expresar; “10 min after open” no es primera clase. | entry_delay_minutes=10; señal gap + open vs MA. |
| Exit: 5 min before close | `close_positions()` scheduled | ExitType.TIME en barras o EOD; no “minutos antes del cierre”. | exit_minutes_before_close=5. |

---

## 6. Referencias

- QuantRocket Sell-on-Gap: Part 2 (Universe Selection), Part 4 (Zipline Strategy Code), Part 5 (Backtest).
- Zipline Pipeline: `initial_universe`, `columns`, `screen`; ejecución con `run_pipeline`.
- Nuestro código: `services/backtester/core/engine.py`, `core/models.py` (UniverseFilter, StrategyConfig), `core/data_layer.py`.

---

*Documento generado a partir de ingeniería inversa sobre QuantRocket/Zipline y estado actual del backtester Tradeul. Próximo paso recomendado: diseñar la API concreta del UniverseSelector (Pipeline) y un POC que alimente el engine con universo por día.*
