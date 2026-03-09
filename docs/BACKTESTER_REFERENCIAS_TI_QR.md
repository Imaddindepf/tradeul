# Referencias: Trade Ideas Oddsmaker + QuantRocket/Zipline

Documento para tener **dos referencias** claras y usar la combinación más potente en nuestro backtester.

---

## 1. Trade Ideas — Oddsmaker (resumen)

### Configuración de entrada
| Concepto | Cómo lo hace Trade Ideas |
|----------|---------------------------|
| **Ventana horaria** | Start Time / End Time diarios (ej. 9:30–16:00 o solo 11:00–14:00). El scan/entrada solo corre en esa ventana. |
| **Datos** | Solo market hours; no premarket/postmarket; no día actual. ~64 días de historia; basado en velas 1 min (no tick). |
| **Un trade por símbolo por día** | Una vez entrado en un símbolo, no vuelve a mirar ese símbolo hasta el día siguiente. Cada día empieza de cero. |

### Salidas
| Concepto | Cómo lo hace Trade Ideas |
|----------|---------------------------|
| **Timed exit** | Minutos después de entrada, o hora fija del día, o relativo a open/close (para swing). Si pones “30 min después de entrada” y entras a 30 min del cierre, salen al cierre. |
| **Target / Stop** | Por acción: dólares o porcentaje; opcional “Wiggle” en el stop (volatilidad 15 min × relative volume). Target/Stop también pueden basarse en un filtro. |
| **Trailing stop** | Porcentaje o en “barras de 15 min”. En live solo trailing “clásico” (limitación del broker). |
| **Exit por alerta** | Pueden definir una ventana de alertas como estrategia de salida. |

### Capital y costes
| Concepto | Cómo lo hace Trade Ideas |
|----------|---------------------------|
| **Capital inicial** | Configurable; afecta return y projected annual return. |
| **Tamaño de posición** | Dólares por trade o shares por trade (no solo %). |
| **Comisión** | Por trade y por share. |
| **Buying power** | Muestran la máxima buying power usada; aviso si > 4× equity. |

### Resultados y UX
| Concepto | Cómo lo hace Trade Ideas |
|----------|---------------------------|
| **Resumen** | Profit factor, win rate, avg winner vs avg loser, strategy return, projected annual return; campos en verde/rojo. |
| **Calendario** | Días coloreados (verde/rojo por P&L); hover = detalle del día; doble clic = lista de trades de ese día. |
| **Curva de equity** | Gross vs net (con comisiones); se actualiza al cambiar capital/tamaño/comisión. |
| **Gráficos** | Daily P&L, trades por día, drawdown, buying power en el tiempo. |
| **Optimization** | Desglose por filtro: intervalos de precio, franja horaria, símbolos. Por segmento: profit factor, win rate, avg gain, total gain, nº trades. “Having at least” para ocultar segmentos con pocos trades. Doble clic en segmento = trades. Sirve para afinar filtros de la estrategia. |
| **Export** | Guardar/cargar resultados (CSV); colaboración. |

### Limitaciones que ellos mismos dicen
- Basado en OHLC de 1 min, no tick → diferencias vs live.
- No incluyen spread; en live no hay garantía de fill al precio exacto.
- Recomiendan: backtest → paper → live.

---

## 2. QuantRocket / Zipline (resumen)

| Concepto | Cómo lo hace |
|----------|--------------|
| **Datos** | Bundles (daily + minute); ingest; ajustes por splits. |
| **Universe** | Pipeline que corre **por fecha**: initial_universe + screen (liquidez, MA, precio, tipo de activo). Output = candidatos por día. |
| **Estrategia** | Código: initialize, before_trading_start (recibe output del pipeline), funciones programadas a hora (ej. 9:31, 9:40, 15:55). |
| **Backtest** | backtest(nombre, fechas, capital_base) → CSV + pyfolio. |
| **Trade inspection** | Parte 6 explícita: inspección de trades individuales. |

---

## 3. Referencia única “más potente” (checklist)

Combinando lo mejor de ambos para nuestro backtester:

### Entrada
- [ ] **Ventana horaria diaria** (start_time / end_time) — estilo TI: solo buscar entradas en esa ventana.
- [ ] **Un trade por símbolo por día** (opcional) — como TI: no reentrar el mismo símbolo el mismo día.
- [ ] **Universe fijo o dinámico** — como QR: lista fija (actual) o pipeline por día (opcional).

### Salida
- [ ] **Timed exit**: “N minutos después de entrada” y “salir a hora X” o “M minutos antes del cierre” — TI + QR.
- [ ] **Target / Stop** en $ o % — ya tenemos en %; añadir $ por acción si se quiere paridad con TI.
- [ ] **Trailing stop** en % (ya lo tenemos) o en ATR/barras — TI tiene “15-min bars”.
- [ ] **Wiggle / offset en stop** (opcional) — volatilidad o ATR para ensanchar stop; TI lo tiene.

### Capital y costes
- [ ] **Position size**: % de equity (ya), dólares por trade, o shares por trade — TI.
- [ ] **Comisión**: por trade (ya) y por share — TI.
- [ ] **Buying power** en resultados (máx. utilizada, aviso si > N× equity) — TI.

### Datos
- [ ] Basado en velas 1 min (no tick); sin premarket/postmarket si se desea; aviso explícito de limitaciones vs live — como TI/QR.
- [ ] Ajuste por splits y fuente única (day + minute) — ya lo tenemos.

### Resultados y análisis
- [ ] **Resumen**: Profit factor, win rate, avg winner vs avg loser, return, projected annual, buying power — TI + lo que ya tenemos (Sharpe, Sortino, etc.).
- [ ] **Calendario**: Días coloreados por P&L; hover = resumen del día; doble clic = trades del día — TI.
- [ ] **Curva de equity** gross vs net (comisiones) — TI; nosotros tenemos curva, falta gross vs net si se quiere.
- [ ] **Gráficos**: Daily P&L, trades/día, drawdown, buying power — TI.
- [ ] **Optimization por segmentos**: desglose por banda de precio, franja horaria, símbolo (u otros filtros); métricas por segmento; “having at least” y doble clic a trades — TI. Nosotros tenemos walk-forward y Monte Carlo pero no este desglose por filtro.
- [ ] **Trade inspection**: lista de trades, filtrar, exportar (CSV) — TI + QR Part 6.
- [ ] **Guardar/cargar** resultados (y opcionalmente config) — TI.

### Rigor (ya nuestro)
- Cero look-ahead; fills con slippage; métricas avanzadas (DSR, PSR, walk-forward, Monte Carlo).

---

## 4. Mapa rápido: nosotros vs referencia “más potente”

| Funcionalidad | Trade Ideas | QuantRocket | Nosotros hoy |
|---------------|-------------|-------------|--------------|
| Ventana horaria (start/end time) | ✅ | ✅ (schedule) | ❌ |
| Un trade por símbolo por día | ✅ | depende | ❌ (1 pos/símbolo, no “por día”) |
| Exit “N min después entrada” | ✅ | ✅ | ❌ (solo en código) |
| Exit “M min antes cierre” | ✅ | ✅ | ❌ (solo en código) |
| Target/Stop $ o % | ✅ | ✅ | ✅ % |
| Trailing stop % | ✅ | ✅ | ✅ |
| Position size $ o shares | ✅ | ✅ | % solo |
| Comisión por trade y por share | ✅ | ✅ | por trade |
| Buying power en resultados | ✅ | — | ❌ |
| Calendario + doble clic a trades | ✅ | — | ❌ |
| Optimization por filtros (segmentos) | ✅ | — | ❌ |
| Universe dinámico por día | — | ✅ | ❌ |
| Walk-forward / Monte Carlo | — | — | ✅ |
| DSR / PSR / métricas avanzadas | — | pyfolio | ✅ |
| Datos minuto ajustados + REST | — | bundles | ✅ |

---

## 5. Uso de este doc

- **Producto / roadmap**: priorizar ítems del checklist según impacto (ej. ventana horaria + timed exit + calendario + optimization por segmentos).
- **Diseño**: al añadir “timing intraday” o “risk management”, mirar cómo lo exponen TI (Entry/Timed Exit/Risk Tabs) y QR (schedule) para no reinventar.
- **Copy / avisos**: reutilizar sus disclaimer (OHLC 1 min, no tick, no spread, backtest → paper → live).

Con Trade Ideas y QuantRocket como referencias, este documento deja fijada la **referencia más potente** para ir cerrando gaps sin perder el rigor que ya tenemos.
