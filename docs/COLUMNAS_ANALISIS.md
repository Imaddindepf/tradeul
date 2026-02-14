# Análisis Profundo: Columnas Backend vs Frontend

## TABLA SCANNER (CategoryTableV2.tsx)

### ✅ Columnas Implementadas en Frontend (40 columnas):

1. **row_number** (#)
2. **symbol**
3. **price**
4. **change_percent** (Chg %)
5. **gap_percent** (Gap %)
6. **volume_today** (Volume)
7. **rvol** (RVOL)
8. **market_cap** (MCap)
9. **free_float** (Free Float)
10. **shares_outstanding** (Outstanding)
11. **minute_volume** (Min Vol)
12. **avg_volume_5d** (Vol 5D)
13. **avg_volume_10d** (Vol 10D)
14. **avg_volume_3m** (Vol 3M)
15. **dollar_volume** ($ Vol)
16. **volume_today_pct** (Vol Today %)
17. **volume_yesterday_pct** (Vol Yest %)
18. **vol_1min** (1m vol)
19. **vol_5min** (5m vol)
20. **vol_10min** (10m vol)
21. **vol_15min** (15m vol)
22. **vol_30min** (30m vol)
23. **chg_1min** (1m Chg%)
24. **chg_5min** (5m Chg%)
25. **chg_10min** (10m Chg%)
26. **chg_15min** (15m Chg%)
27. **chg_30min** (30m Chg%)
28. **price_vs_vwap** (vs VWAP)
29. **premarket_change_percent** (Pre%)
30. **postmarket_change_percent** (PM Chg%)
31. **postmarket_volume** (PM Vol)
32. **trades_z_score** (Z-Score)
33. **trades_today** (Trades)
34. **avg_trades_5d** (Avg 5d)
35. **spread** (Spread)
36. **bid_size** (Bid Size)
37. **ask_size** (Ask Size)
38. **bid_ask_ratio** (B/A Ratio)
39. **distance_from_nbbo** (NBBO Dist)
40. **atr_percent** (ATR%)
41. **atr_used** (ATR Used) - columna derivada

### ❌ Columnas FALTANTES (Backend las envía pero NO están en UI):

#### Campos Básicos:
- **bid** - Precio Bid
- **ask** - Precio Ask
- **spread_percent** - Spread como % del precio
- **open** - Precio de apertura
- **high** - Máximo del día (regular hours)
- **low** - Mínimo del día (regular hours)
- **intraday_high** - Máximo intradía (incluye pre/post)
- **intraday_low** - Mínimo intradía (incluye pre/post)
- **prev_close** - Cierre anterior
- **prev_volume** - Volumen día anterior
- **change** - Cambio en dólares
- **vwap** - VWAP value (solo tenemos price_vs_vwap)
- **exchange** - Exchange donde cotiza

#### Indicadores Intradía (1-min bars):
- **rsi_14** - RSI(14) en barras de 1 minuto
- **ema_9** - EMA(9)
- **ema_20** - EMA(20)
- **ema_50** - EMA(50)
- **sma_5** - SMA(5)
- **sma_8** - SMA(8)
- **sma_20** - SMA(20)
- **sma_50** - SMA(50)
- **sma_200** - SMA(200)
- **macd_line** - MACD line
- **macd_signal** - MACD signal
- **macd_hist** - MACD histogram
- **bb_upper** - Bollinger Band superior
- **bb_mid** - Bollinger Band media
- **bb_lower** - Bollinger Band inferior
- **adx_14** - ADX(14)
- **stoch_k** - Stochastic %K
- **stoch_d** - Stochastic %D

#### Ventanas de Tiempo:
- **chg_60min** - Cambio % en últimos 60 minutos
- **vol_60min** - Volumen en últimos 60 minutos

#### Indicadores Diarios:
- **daily_sma_20** - SMA 20 días
- **daily_sma_50** - SMA 50 días
- **daily_sma_200** - SMA 200 días
- **daily_rsi** - RSI diario
- **daily_adx_14** - ADX diario
- **daily_atr_percent** - ATR diario %
- **daily_bb_position** - Posición en Bollinger Bands diarias (0-100)

#### 52 Semanas:
- **high_52w** - Máximo 52 semanas
- **low_52w** - Mínimo 52 semanas
- **from_52w_high** - % desde máximo 52w
- **from_52w_low** - % desde mínimo 52w

#### Cambios Multi-día:
- **change_1d** - Cambio 1 día %
- **change_3d** - Cambio 3 días %
- **change_5d** - Cambio 5 días %
- **change_10d** - Cambio 10 días %
- **change_20d** - Cambio 20 días %

#### Promedios Adicionales:
- **avg_volume_20d** - Volumen promedio 20 días
- **prev_day_volume** - Volumen del día anterior

#### Distancias/Derivados:
- **dist_from_vwap** - % distancia desde VWAP
- **dist_sma_5** - % distancia desde SMA(5)
- **dist_sma_8** - % distancia desde SMA(8)
- **dist_sma_20** - % distancia desde SMA(20)
- **dist_sma_50** - % distancia desde SMA(50)
- **dist_sma_200** - % distancia desde SMA(200)
- **dist_daily_sma_20** - % distancia desde SMA diaria 20
- **dist_daily_sma_50** - % distancia desde SMA diaria 50
- **todays_range** - Rango del día en $
- **todays_range_pct** - Rango del día %
- **float_turnover** - Ratio volumen/float
- **pos_in_range** - Posición en rango día (0-100%)
- **below_high** - $ debajo del máximo
- **above_low** - $ arriba del mínimo
- **pos_of_open** - Posición de apertura en rango (0-100%)

#### Fundamentales:
- **security_type** - Tipo (CS, ETF, PFD, WARRANT)
- **sector** - Sector
- **industry** - Industria
- **free_float_percent** - % de free float
- **float_rotation** - Rotación del float %

#### Otros:
- **atr** - ATR en dólares (solo tenemos atr_percent)
- **price_from_high** - % desde máximo día
- **price_from_low** - % desde mínimo día
- **price_from_intraday_high** - % desde máximo intradía
- **price_from_intraday_low** - % desde mínimo intradía
- **last_trade_timestamp** - Timestamp último trade

**TOTAL SCANNER: ~40 columnas implementadas, ~70 campos FALTAN**

---

## TABLA EVENTOS (EventTableContent.tsx)

### ✅ Columnas Implementadas en Frontend (12 columnas):

1. **row_number** (#)
2. **timestamp** (Time)
3. **symbol**
4. **event_type** (Event)
5. **price**
6. **change_percent** (Chg%)
7. **volume**
8. **rvol** (RVOL)
9. **gap_percent** (Gap%)
10. **change_from_open** (vs Open)
11. **market_cap** (MCap)
12. **atr_percent** (ATR%)
13. **vwap** (VWAP)

### ❌ Columnas FALTANTES (Backend las envía pero NO están en UI):

#### Campos de Evento:
- **prev_value** - Valor anterior (para cruces)
- **new_value** - Valor nuevo (para cruces)
- **delta** - Delta absoluto
- **delta_percent** - Delta en %

#### Contexto Básico:
- **open_price** - Precio apertura
- **prev_close** - Cierre anterior
- **intraday_high** - Máximo intradía
- **intraday_low** - Mínimo intradía

#### Ventanas de Tiempo:
- **chg_1min** - Cambio 1 min
- **chg_5min** - Cambio 5 min
- **chg_10min** - Cambio 10 min
- **chg_15min** - Cambio 15 min
- **chg_30min** - Cambio 30 min
- **vol_1min** - Volumen 1 min
- **vol_5min** - Volumen 5 min

#### Indicadores Técnicos:
- **float_shares** - Float en acción
- **rsi** - RSI al momento del evento
- **ema_20** - EMA 20 al momento
- **ema_50** - EMA 50 al momento

#### Fundamentales:
- **security_type** - Tipo de valor
- **sector** - Sector

**TOTAL EVENTOS: ~13 columnas implementadas, ~20 campos FALTAN**

---

## RESUMEN EJECUTIVO

### 🔴 CRÍTICO - Faltan ~90 columnas en total:

| Tabla | Backend envía | Frontend muestra | Faltan | % Cobertura |
|-------|---------------|------------------|--------|-------------|
| **Scanner** | ~110 campos | 40 columnas | ~70 | 36% |
| **Events** | ~33 campos | 13 columnas | ~20 | 39% |

### 💡 Columnas Críticas que FALTAN:

1. **Indicadores Técnicos Intradía**: RSI, SMA(5/8/20/50/200), EMA(20/50), MACD, Stochastic, ADX, Bollinger
2. **Indicadores Diarios**: daily_sma_20/50/200, daily_rsi, daily_adx, daily_bb_position
3. **52 Semanas**: high_52w, low_52w, from_52w_high, from_52w_low
4. **Cambios Multi-día**: change_1d/3d/5d/10d/20d
5. **Distancias**: dist_from_vwap, dist_sma_X, dist_daily_sma_X
6. **Derivados**: todays_range, float_turnover, pos_in_range, below_high, above_low
7. **Quote Data**: bid, ask, spread_percent
8. **Fundamentales**: sector, industry, security_type
9. **Ventanas 60min**: chg_60min, vol_60min

### 🎯 Recomendación:

El backend envía TODO el catálogo de datos técnicos pero el frontend solo expone ~35% de las columnas. Los usuarios NO pueden ver ni analizar la mayoría de indicadores técnicos que ya están calculados y disponibles.

Deberías:
1. Añadir todas las columnas faltantes al array de `columns` en ambas tablas
2. Mantenerlas ocultas por defecto (enableHiding: true)
3. Dejar que el usuario decida cuáles mostrar vía el selector de columnas
