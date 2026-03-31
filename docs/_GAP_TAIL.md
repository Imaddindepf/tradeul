
---

# 17. CONSOLIDATION & CHANNELS (9 alertas TI)

## 17.1 Consolidation [C] — 🔧

**TI detecta:** ESTADO de consolidacion. Z-score vs rango ideal $0. Reevalua ~15 min.
**TI custom filter:** Quality 2=min, 5=tight, 10=best.
**TI Quality:** Z-score.
**TI Alert Info:** `keywords=Price vs Time, Volume Confirmed`

**Nuestro codigo** (`consolidation_events.py`):
```python
was_consolidating = (abs(prev_chg_5min) < 0.5 and abs(prev_chg_10min) < 1.0)
if chg_1min >= 0.8 and rvol >= 1.5:
    # CONSOLIDATION_BREAKOUT_UP, cooldown 600s
```

| Aspecto | Trade Ideas | TradeUL | Gap |
|---------|-------------|---------|-----|
| Que detecta | Estado de consolidacion | Breakout FROM consolidation | 🔧 Diferente |
| Z-score quality | 2-10 | No | ❌ |
| Multi-timeframe | Si | No | ❌ |

## 17.2 CHBOC — ❌. Channel Breakout Confirmed (~15 min). State machine consolidating->running + vol confirm.
## 17.3 CHBDC — ❌. Espejo.
## 17.4 CHBO — ❌. Channel Breakout Fast (~1 min).
## 17.5 CHBD — ❌. Espejo.
## 17.6-17.9 N-Min Consolidation Breakouts — ❌ (4 alertas en 5/10/15/30 min, 41 candles).

---

# 18. SUPPORT/RESISTANCE (4 alertas TI) — ❌

## 18.1 CARC — Crossed Above Resistance Confirmed

**TI detecta:** Cruza resistencia importante (volume-at-price level). Filtering propietario. Requiere volumen suficiente.
**TI custom filter:** Hours traded (resistencia mas vieja = mayor calidad).
**TI Quality:** Horas desde que se establecio el patron.
**TI Alert Info:** `direction=+`, `flip_code=CBSC`, `keywords=Support and Resistance, Volume Confirmed`

**Requisito:** Calculo dinamico S/R basado en volume-at-price + hours-traded metric + vol confirmation.

## 18.2 CBSC — ❌. Espejo. ## 18.3 CAR — ❌. Version rapida. ## 18.4 CBS — ❌. Espejo.

---

# 19. SECTOR ALERTS (4 alertas) — ❌

SBOO/SBDO/SBOC/SBDC. Stock diverge de sector ETF. Requiere mapping stock->sector ETF + divergencia real-time.

# 20. MARKET DIVERGENCE (2 alertas) — ❌

FDP/FDN. Stock diverge de QQQ. Requiere feed QQQ + correlacion.

# 21. CHART PATTERNS (10 alertas) — ❌

GBBOT/GBTOP (Broadening), GTBOT/GTTOP (Triangle), GRBOT/GRTOP (Rectangle), GDBOT/GDTOP (Double), GHAS (H&S). Requiere geometric pattern engine con 5+ turning points. Complejidad: MUY ALTA.

# 22. TIMEFRAME HIGHS/LOWS (10 alertas) — ❌

IDH5-IDL60. Nuevo high/low en 5/10/15/30/60-min chart. Requiere multi-TF bar builder.

# 23. TRAILING STOPS (4 alertas) — ❌

TSPU/TSPD (% based), TSSU/TSSD (sigma based). Reversion desde local high/low.

# 24. FIBONACCI (8 alertas) — ❌

FU38/FD38, FU50/FD50, FU62/FD62, FU79/FD79. 3-point volume-confirmed swing analysis.

# 25. LINEAR REGRESSION (8 alertas) — ❌

PEU5-PED90. Tendencia significativa en 5/15/30/90-min chart. R2 test. Requiere multi-TF bar builder.

# 26. THRUST (6 alertas) — ❌

SMAU2-SMAD15. Movimiento direccional fuerte en 2/5/15 min.

# 27. L2/MICROSTRUCTURE (11 alertas) — ❌

LBS, LAS, MC, MCU, MCD, ML, LSP, TRA, TRB, TRAS, TRBS. Requiere Level 2 data feed.

# 28. NYSE IMBALANCE (2 alertas) — ❌

NYSEBI/NYSESI. Requiere NYSE MOC/MOO imbalance feed.

---

# 29. CANDLESTICK PATTERNS (87 alertas) — ❌

20 patrones x multiples timeframes (2,5,10,15,30,60 min):

| Patron | Timeframes | Alertas |
|--------|-----------|---------|
| Doji | 5,10,15,30,60 | 5 |
| Hammer | 2,5,10,15,30,60 | 6 |
| Hanging Man | 2,5,10,15,30,60 | 6 |
| Bullish/Bearish Engulfing | 5,10,15,30 | 8 |
| Piercing/Dark Cloud | 5,10,15,30 | 8 |
| Bottoming/Topping Tail | 2,5,10,15,30,60 | 12 |
| Narrow Range Buy/Sell | 5,10,15,30 | 8 |
| Green/Red Bar Reversal | 2,5,15,60 | 8 |
| 1-2-3 Cont. Buy/Sell Signal | 2,5,15,60 | 8 |
| 1-2-3 Cont. Buy/Sell Setup | 2,5,15,60 | 8 |
| Opening Power Bar | 5 | 2 |
| NR7 | 1,2,5,10,15,30 | 6 |
| Wide Range Bar | 2,5,15 | 3 |

Prerequisito: Multi-timeframe bar builder + candlestick pattern library.

---

# RESUMEN GLOBAL

## Conteo por estado

| Estado | Alertas | % |
|--------|---------|---|
| ✅ Activo (frontend + backend) | 57 | 20% |
| ⚠️ Backend only (frontend bloqueado) | 10 | 3% |
| 🔧 Parcial | 7 | 2% |
| ❌ No tenemos | 214 | 75% |
| **TOTAL TI** | **~288** | |

## Quick Wins (+10 alertas, 0 codigo backend)

| Alerta | Code | Accion |
|--------|------|--------|
| Pre-market High | HPRE | `active: false` -> `true` en `alert-catalog.ts:215` |
| Pre-market Low | LPRE | `active: false` -> `true` en `alert-catalog.ts:216` |
| Post-market High | HPOST | `active: false` -> `true` en `alert-catalog.ts:217` |
| Post-market Low | LPOST | `active: false` -> `true` en `alert-catalog.ts:218` |
| Cross Open Confirmed up | CAOC | `active: false` -> `true` en `alert-catalog.ts:209` |
| Cross Open Confirmed down | CBOC | `active: false` -> `true` en `alert-catalog.ts:210` |
| Cross Close Confirmed up | CACC | `active: false` -> `true` en `alert-catalog.ts:211` |
| Cross Close Confirmed down | CBCC | `active: false` -> `true` en `alert-catalog.ts:212` |
| Cross Above SMA 200 | CA200 | `active: false` -> `true` en `alert-catalog.ts:213` |
| Cross Below SMA 200 | CB200 | `active: false` -> `true` en `alert-catalog.ts:214` |

## Top Gaps por Impacto

| # | Feature | Alertas desbloqueadas | Esfuerzo |
|---|---------|----------------------|----------|
| 1 | **Quick wins frontend** | +10 | Trivial |
| 2 | **Multi-timeframe bar builder** | +163 (ORB, MACD, Stoch, SMA, TF H/L, candles, regression, thrust) | Alto |
| 3 | **Quality filter system** (366 dias) | Mejora NHP, NLP, HPRE, LPRE, CDHR, CDLS | Medio |
| 4 | **Candlestick pattern engine** | +87 (depende de #2) | Alto |
| 5 | **Chart pattern recognition** | +10 (H&S, Double Top, Triangles) | Muy alto |
| 6 | **Dynamic S/R calculation** | +4 | Alto |
| 7 | **Sector/Market divergence** | +6 | Medio |
| 8 | **Level 2 data integration** | +17 (NHA, NLB, filtered, L2 alerts) | Muy alto |
| 9 | **Fibonacci retracements** | +8 | Medio |
| 10 | **Linear regression + Thrust** | +14 | Medio |

## Lo que tenemos y TI NO tiene

- **25+ campos de contexto** en cada evento (rvol, gap%, mktcap, float, rsi, ema, sector...)
- **Estrategias de usuario** personalizadas con filtros JSONB
- **17 presets pre-construidos** optimizados (Momentum Runners, Squeeze Play, etc.)
- **Intraday EMA crosses** (TI solo tiene SMA)
- **Price vs SMA crosses** (TI tiene SMA vs SMA, no price vs SMA)
- **Stochastic zone entries** (oversold/overbought — TI solo tiene crosses)
- **MACD 1-min** (TI empieza en 5-min)
- **Consolidation breakout** con RVOL confirmation
- **False gap retracement** como evento separado
- **Running confirmed** con multi-window (5min + 15min)

## Mapa de dependencias

```
Multi-TF Bar Builder
  -> ORB 6 TFs (+12), MACD 4 TFs (+16), Stoch 2 TFs (+4)
  -> SMA crosses 5+ TFs (+20), TF Highs/Lows (+10)
  -> Candlestick Patterns (+87), Linear Regression (+8), Thrust (+6)
  TOTAL: ~163 alertas

Daily Historical Bars (366 dias)
  -> Quality filter NHP/NLP/HPRE/LPRE/CDHR/CDLS
  -> Description column (resistencia/soporte historico)
  -> 52-week high/low detection

Level 2 Data Feed
  -> NHA, NLB, NHAF, NLBF, NHBF, NLAF (+6)
  -> Block Trade "at bid/ask" info
  -> L2/Microstructure alerts (+11)
  TOTAL: ~17 alertas

Geometric Pattern Engine
  -> Chart Patterns (+10), Fibonacci (+8)
  TOTAL: ~18 alertas

Sector ETF Mapping + QQQ
  -> Sector Alerts (+4), Market Divergence (+2)
  TOTAL: ~6 alertas
```

## Codigo fuente analizado

| Archivo | Detector | Eventos |
|---------|----------|---------|
| `detectors/price_events.py` | PriceEventsDetector | NHP, NLP, CAO, CBO, CAC, CBC |
| `detectors/session_events.py` | SessionEventsDetector | HPRE, LPRE, HPOST, LPOST |
| `detectors/pullback_events.py` | PullbackEventsDetector | 12 pullbacks |
| `detectors/momentum_events.py` | MomentumEventsDetector | RUN, RDN, P5U, P5D, P10U, P10D |
| `detectors/bollinger_events.py` | BollingerEventsDetector | BBU, BBD |
| `detectors/daily_level_events.py` | DailyLevelEventsDetector | CDHR, CDLS, FGUR, FGDR, RU, RD, RUC, RDC |
| `detectors/volume_events.py` | VolumeEventsDetector | RVS, VSG, VS1, UNP, BLK |
| `detectors/vwap_events.py` | VWAPEventsDetector | VCU, VCD |
| `detectors/gap_events.py` | GapEventsDetector | GUR, GDR |
| `detectors/confirmed_cross_events.py` | ConfirmedCrossEventsDetector | CAOC, CBOC, CACC, CBCC |
| `detectors/ma_cross_events.py` | MACrossEventsDetector | 14 SMA/EMA crosses + SMA200 |
| `detectors/orb_events.py` | ORBEventsDetector | ORBU, ORBD |
| `detectors/consolidation_events.py` | ConsolidationEventsDetector | CBU, CBD |
| `detectors/macd_events.py` | MACDEventsDetector | MACDU, MACDD, MZU, MZD |
| `detectors/stochastic_events.py` | StochasticEventsDetector | STBU, STBD, STOS, STOB |
| `frontend/lib/alert-catalog.ts` | Frontend catalog | 85 definiciones (57 active + 28 phase 2) |
