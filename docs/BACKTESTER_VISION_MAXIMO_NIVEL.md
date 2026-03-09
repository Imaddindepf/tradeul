# Backtester Engine de máximo nivel — Visión

Documento único que define cómo es y cómo funciona nuestro backtester cuando está en su **máximo nivel**: motor profesional para traders de todo el mundo.

---

## 1. Qué significa “máximo nivel”

Un backtester de máximo nivel reúne:

| Principio | Qué implica |
|-----------|-------------|
| **Rigor** | Cero look-ahead: señales solo con datos hasta la barra actual; fills realistas (slippage, comisión, participación en volumen). |
| **Datos de calidad** | OHLCV ajustado por splits; una sola fuente de verdad (day + minute); soporte histórico amplio y fallback a API cuando haga falta. |
| **Métricas profesionales** | Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor; métricas avanzadas (Deflated Sharpe, PSR, min track record); walk-forward y Monte Carlo para robustez. |
| **Flexibilidad de uso** | Dos modos: **(A)** lista fija de tickers + reglas (el 80% de casos) y **(B)** universo dinámico por día (screening tipo QuantRocket) cuando la estrategia lo pida. |
| **Timing explícito** | Daily: open/close/next_open. Intraday: además, “N minutos después del open” y “M minutos antes del cierre” para estrategias tipo opening range / closing flush. |
| **Inspección y análisis** | Resultado no es solo un número: lista de trades explotable, curva de equity, drawdown, returns mensuales; posibilidad de inspección por trade (Part 6). |

El engine actual ya cumple la mayor parte; “máximo nivel” se alcanza añadiendo **capas opcionales** sin romper el core.

---

## 2. Arquitectura en capas

El flujo es lineal; algunas capas son opcionales según el caso de uso.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CAPA 1: DATOS                                                           │
│  DataLayer — FLATS (day_aggs + minute_aggs_adjusted) + REST              │
│  Entrada: (start_date, end_date, tickers?)                               │
│  Salida:  DataFrame OHLCV con indicadores (gap_pct, rsi, sma, atr…)   │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │  ¿Universe dinámico? (caso B)     │
                    │  SÍ → CAPA 2 (opcional)           │
                    │  NO → tickers ya definidos       │
                    └─────────────────┴─────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CAPA 2 (opcional): UNIVERSO POR DÍA                                     │
│  UniverseSelector / Pipeline — reglas: liquidez, precio, MA, sector…    │
│  Entrada: rango de fechas + reglas de screening                         │
│  Salida:  por cada fecha, set de tickers candidatos                     │
│  → El engine pide datos solo para esos tickers cada día                 │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CAPA 3: SEÑALES Y REGLAS                                                │
│  • Template: StrategyConfig (entry_signals, exit_rules, entry_timing)   │
│  • Code: strategy(bars) Python (LLM o usuario)                         │
│  Salida:  máscaras de entrada + señales de salida (por barra)           │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CAPA 4: SIMULACIÓN DE PORTFOLIO                                         │
│  BacktestEngine._simulate() — loop por ticker, por barra                 │
│  • Entradas: respetar entry_timing (open/close/next_open o intraday)    │
│  • Salidas: EOD, TIME, TARGET, STOP_LOSS, TRAILING_STOP, SIGNAL           │
│  • Fills: FillModel (fixed_bps, volume_based, spread_based)              │
│  • Capital, max_positions, position_size_pct, long/short/both            │
│  Salida:  lista de TradeRecord, curva de equity por barra               │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CAPA 5: MÉTRICAS                                                        │
│  compute_core_metrics() + opcional advanced_metrics, walk_forward,       │
│  monte_carlo                                                            │
│  Salida:  BacktestResult (core_metrics, trades, equity_curve,           │
│           monthly_returns, drawdown_curve, warnings)                     │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│  CAPA 6: INSPECCIÓN Y EXPORT                                             │
│  Trade inspection: filtrar/ordenar/exportar trades por ticker, fecha,   │
│  PnL, duración; vista por periodo; export CSV/Parquet                   │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Caso A (lista fija)**: se usa Capa 1 → 3 → 4 → 5 → 6 (sin Capa 2).
- **Caso B (universe dinámico)**: Capa 2 define candidatos por día; el engine usa esos candidatos para pedir datos y simular (Capas 1–6).

---

## 3. Estado actual vs máximo nivel

| Bloque | Hoy (estado actual) | Máximo nivel |
|--------|----------------------|--------------|
| **Datos** | FLATS day + minute adjusted, REST fallback, indicadores DuckDB | ✅ Igual + ampliar histórico day cuando se decida |
| **Universe** | Lista fija (o SQL sobre barras cargadas) | ✅ Lista fija + **opcional** UniverseSelector por día (Pipeline light) |
| **Señales** | Template (Signal + ExitRule) y Code (strategy(bars)) | ✅ Igual |
| **Timing** | open / close / next_open por barra | ✅ Igual + **opcional** entry_delay_minutes, exit_minutes_before_close para intraday |
| **Simulación** | Loop por ticker/barra, fills (fixed_bps, volume_based), long/short, max_positions | ✅ Igual |
| **Métricas** | Core + Advanced (DSR, PSR) + Walk-Forward + Monte Carlo | ✅ Ya lo tenemos |
| **Inspección** | BacktestResult.trades en memoria | ✅ + API/UI de trade inspection (filtrar, exportar) |

Es decir: el **core ya es de nivel profesional** (datos, señales, simulación, métricas). El “máximo nivel” se alcanza con:

1. **UniverseSelector opcional** (Capa 2) para estrategias de screening diario.
2. **Timing intraday explícito** (minutos después del open / antes del cierre) como opción en la simulación.
3. **Trade inspection** como capa de producto (API + eventual UI) sobre `BacktestResult.trades`.

---

## 4. Cómo sería el engine “de máximo nivel” en una frase

**Un único BacktestEngine** que:

- Siempre usa **DataLayer** (Capa 1) y **métricas profesionales** (Capa 5).
- Acepta **universe = lista fija** (comportamiento actual) o **universe = pipeline** (por día); si es pipeline, antes de cargar datos cada día consulta la Capa 2 y pide solo los tickers candidatos.
- Acepta **entry_timing** en barra (open/close/next_open) y, en intraday, **opcionalmente** delays en minutos (entry_delay_minutes, exit_minutes_before_close).
- Devuelve **BacktestResult** (trades, equity, métricas, warnings) y expone **trade inspection** (filtrar, ordenar, exportar) sobre ese resultado.

Nada de esto obliga a reescribir el loop de simulación; solo a parametrizar de dónde salen los tickers (lista fija vs pipeline) y cómo se interpreta el “momento de entrada/salida” en barras minuto.

---

## 5. Priorización sugerida

1. **Timing intraday** (entry_delay_minutes, exit_minutes_before_close) — poco cambio en el engine, mucho valor para estrategias tipo opening range / sell-on-gap.
2. **UniverseSelector (Pipeline light)** — para soportar el caso de uso “cada día, top N por liquidez + filtro técnico”.
3. **Trade inspection** — API o módulo que, dado un `BacktestResult`, permita consultas y export sobre `trades`.

Con eso, el backtester queda en **máximo nivel** manteniendo un solo flujo y un solo engine, con capas opcionales según el caso de uso.
