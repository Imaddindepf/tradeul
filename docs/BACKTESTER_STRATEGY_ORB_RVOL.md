# Cómo probar una estrategia ORB + RVOL (y similares)

Guía práctica: qué es ORB + RVOL, cómo backtestearla **hoy** en Tradeul y qué falta para soportarla también por template.

---

## 1. Qué es ORB + RVOL (en una frase)

- **ORB (Opening Range Breakout):** Definir un “rango de apertura” (ej. primeras 15 o 30 minutos: 9:30–9:45). Después de ese periodo, **comprar** si el precio rompe por encima del máximo de ese rango, **vender** si rompe por debajo del mínimo.
- **RVOL (Relative Volume):** Volumen actual vs volumen medio (ej. 20 periodos). Se usa como filtro: solo operar si hay suficiente interés (ej. RVOL > 1.5).

Otras variantes que encajan en el mismo patrón: filtros por gap, por ATR, por RSI, salida a X minutos antes del cierre, etc.

---

## 2. Qué tiene hoy el backtester

| Necesidad ORB/RVOL | ¿Lo tenemos? | Dónde |
|--------------------|---------------|--------|
| Barras minuto (1min, 5min) | ✅ | `Timeframe.MIN_1`, `MIN_5`; DataLayer carga minute_aggs |
| RVOL | ✅ | `add_indicators_sql`: columna `rvol` = volume / avg_volume_20d |
| Gap %, RSI, ATR, VWAP, SMA, EMA | ✅ | `gap_pct`, `rsi_14`, `atr_14`, `vwap`, `sma_20`, `ema_9`, etc. |
| Opening Range high/low (primeros N min) | ❌ | No hay indicador `or_high_15` / `or_low_15` |
| “Solo entrar después de 9:45” (ventana en minutos) | ❌ | Template no tiene entry_start_minutes_after_open; en **code** sí se puede |

Conclusión: **hoy la forma viable de probar ORB + RVOL es con estrategia en código** (`strategy(bars)`), donde tú calculas el opening range por día y aplicas la ventana horaria en Python. Con template solo podrías aproximar (señal “close > X”) pero sin “solo después de los primeros N minutos” ni OR dinámico por día.

---

## 3. Cómo probarla HOY: estrategia en código (ORB long + RVOL)

Pasos:

1. **Datos:** Llamar al backtester con **timeframe 1min** (o 5min si prefieres), tickers y rango de fechas.
2. **Código:** La API de code backtest espera una función `strategy(bars)` que recibe un DataFrame con columnas: `ticker`, `timestamp` (o `date`), `open`, `high`, `low`, `close`, `volume`, y los indicadores ya calculados (`rvol`, `gap_pct`, `rsi_14`, etc.).
3. **Lógica en Python:**
   - Agrupar `bars` por `(ticker, date)`.
   - Para cada grupo, calcular el **opening range** de las primeras N barras (ej. 15): `or_high = high.max()`, `or_low = low.min()`.
   - A partir de la barra N+1 (o a partir de las 9:45), detectar:
     - **Long:** `close > or_high` y `rvol >= 1.5` (y opcionalmente más filtros).
     - **Short:** `close < or_low` y `rvol >= 1.5`.
   - Para cada señal, decidir salida (EOD, target %, stop %, o “M minutos después”) y añadir un trade al resultado.

Ejemplo de esqueleto (pseudocódigo conceptual):

```python
def strategy(bars):
    bars = bars.sort_values(["ticker", "timestamp"]).reset_index(drop=True)
    bars["date"] = bars["timestamp"].dt.date
    trades = []
    OR_MINUTES = 15   # opening range = first 15 bars (1min) or 3 bars (5min)
    MIN_RVOL = 1.5

    for (ticker, dt), grp in bars.groupby(["ticker", "date"]):
        grp = grp.reset_index(drop=True)
        if len(grp) < OR_MINUTES + 1:
            continue
        or_high = grp.iloc[:OR_MINUTES]["high"].max()
        or_low  = grp.iloc[:OR_MINUTES]["low"].min()

        for i in range(OR_MINUTES, len(grp)):
            row = grp.iloc[i]
            if row["close"] > or_high and row.get("rvol", 0) >= MIN_RVOL:
                # entrada long: salida al cierre del día o a X barras
                exit_row = grp.iloc[-1]  # EOD
                trades.append({
                    "ticker": ticker,
                    "direction": "long",
                    "entry_time": row["timestamp"],
                    "entry_price": row["close"],
                    "exit_time": exit_row["timestamp"],
                    "exit_price": exit_row["close"],
                })
                break  # un trade por símbolo por día (estilo Trade Ideas)
    return trades
```

- **Un trade por símbolo por día:** Como en el Oddsmaker, tras la primera señal del día en ese ticker haces `break` y no vuelves a entrar en ese ticker hasta el día siguiente.
- **Salida:** Puedes usar la última barra del día (EOD), o buscar la primera barra donde `low <= stop` o `high >= target` para simular stop/target.
- **RVOL:** Ya viene en `bars` como `rvol`; solo filtrar `row["rvol"] >= MIN_RVOL`.

Para ejecutarlo: usar el endpoint de **code backtest** (por ejemplo `POST /api/v1/backtest/code` con `code`, `tickers`, `timeframe`, `start_date`, `end_date`). El servicio cargará los datos, aplicará `add_indicators_sql` (incluyendo `rvol`) y ejecutará tu `strategy(bars)`.

---

## 4. Ejemplo más completo: ORB long con RVOL, stop y target en %

Si quieres salida por stop/target en lugar de solo EOD, en el loop de salida puedes recorrer las barras desde `i+1` hasta el final del día y tomar la primera barra donde se cumpla stop o target (o EOD si no se cumple antes). Ejemplo de idea:

```python
# Tras entrada long en barra i a precio entry_price:
entry_price = row["close"]
stop_pct = 0.01   # 1% stop
target_pct = 0.02 # 2% target
for j in range(i + 1, len(grp)):
    r = grp.iloc[j]
    if r["low"] <= entry_price * (1 - stop_pct):
        exit_price = entry_price * (1 - stop_pct)
        exit_time = r["timestamp"]
        break
    if r["high"] >= entry_price * (1 + target_pct):
        exit_price = entry_price * (1 + target_pct)
        exit_time = r["timestamp"]
        break
else:
    exit_price = grp.iloc[-1]["close"]
    exit_time = grp.iloc[-1]["timestamp"]
trades.append({...})
```

Eso simula salida intrabar (simplificado: usas close de la barra o el nivel; un backtester estricto usaría high/low para saber si se tocó el stop/target antes). El backtester actual con code no hace ese “touch” automáticamente; lo haces tú en la lógica de `strategy(bars)`.

---

## 5. Qué faltaría para ORB + RVOL “por template” (sin código)

Para poder definir ORB + RVOL solo con configuración (template + filtros), haría falta:

| Funcionalidad | Descripción |
|---------------|-------------|
| **Indicadores Opening Range** | En `add_indicators_sql` (o equivalente), por cada barra y día: “high del primer bloque de N minutos” y “low del primer bloque de N minutos”. Requiere ventana por (ticker, date) para las primeras N barras. |
| **Ventana de entrada en minutos** | En el engine: “solo considerar señales de entrada en barras donde minutes_since_open >= X” (véase `IntradayTiming` en `BACKTESTER_PLAN_PROFESIONAL.md`). Así el template podría decir “entrar solo después de 9:45”. |
| **Un trade por símbolo por día (opcional)** | Regla en simulación: una vez abierta posición en un ticker ese día, no volver a entrar en ese ticker hasta el día siguiente. |

Con eso, podrías tener por ejemplo:

- Señal de entrada: `close > or_high_15` AND `rvol >= 1.5`
- Entry timing: “solo después de 15 minutos del open”
- Exit: EOD o TIME (minutos) o TARGET/STOP_LOSS

Hoy eso no está; la vía práctica es **estrategia en código**.

---

## 6. Resumen

- **Probar ORB + RVOL (y variantes) hoy:** usar **backtest por código** (`strategy(bars)`), con timeframe 1min o 5min. En el código:
  - Calcular opening range (high/low de las primeras N barras) por (ticker, fecha).
  - A partir de la barra N+1, detectar ruptura por encima/debajo con filtro `rvol >= X`.
  - Opcional: un trade por símbolo por día, salida por EOD o por stop/target en % dentro del mismo día.
- **Indicadores que ya usas:** `rvol`, `gap_pct`, `rsi_14`, `atr_14`, `vwap`, etc., ya vienen en `bars` tras `add_indicators_sql`.
- **Para hacer lo mismo solo con template:** haría falta añadir indicadores de Opening Range y ventana horaria de entrada (timing intraday), como se describe en el plan profesional.

Si quieres, el siguiente paso puede ser un ejemplo ejecutable completo (incluyendo llamada al API de code backtest) para un par de tickers y un rango de fechas concretos.
