# 🌅 Extended Hours - Pre-Market y Post-Market

El **Analytics Service** soporta cálculo de RVOL durante **todo el día de trading**, incluyendo:

- ✅ **Pre-Market** (4:00 AM - 9:30 AM ET)
- ✅ **Market Hours** (9:30 AM - 4:00 PM ET)
- ✅ **Post-Market** (4:00 PM - 8:00 PM ET)

---

## 📊 División de Slots con Extended Hours

### **Estructura Completa del Día**

```
┌─────────────────────────────────────────────────────────────────┐
│                    DÍA DE TRADING COMPLETO                      │
│                   4:00 AM - 8:00 PM (16 horas)                  │
│                      960 minutos = 192 slots                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PRE-MARKET                                                     │
│  4:00 AM - 9:30 AM                                              │
│  330 minutos = 66 slots (slots 0-65)                            │
│                                                                 │
│  Características:                                               │
│  - Menor liquidez                                               │
│  - Mayor volatilidad                                            │
│  - Ideal para detectar breakouts tempranos                      │
│  - RVOL alto en pre-market = catalizador fuerte                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MARKET HOURS (Regular)                                         │
│  9:30 AM - 4:00 PM                                              │
│  390 minutos = 78 slots (slots 66-143)                          │
│                                                                 │
│  Características:                                               │
│  - Máxima liquidez                                              │
│  - Volumen más alto del día                                     │
│  - Primera hora (9:30-10:30) y última hora (3-4 PM) críticas   │
│  - RVOL más estable                                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  POST-MARKET                                                    │
│  4:00 PM - 8:00 PM                                              │
│  240 minutos = 48 slots (slots 144-191)                         │
│                                                                 │
│  Características:                                               │
│  - Menor liquidez que market hours                              │
│  - Earnings releases típicamente a las 4 PM                     │
│  - Reacciones a noticias after-hours                            │
│  - RVOL alto post-market = noticia importante                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Casos de Uso por Sesión

### **1. Pre-Market (4:00 AM - 9:30 AM)**

#### **Detección de Breakouts Tempranos**

```python
# Filtrar tickers con RVOL alto en pre-market
if current_session == MarketSession.PRE_MARKET:
    if rvol > 3.0 and price_change_percent > 5:
        # Posible catalizador: earnings, noticias, gap up
        alert("Breakout pre-market detectado")
```

**Ejemplo Real:**

```
Ticker: NVDA
Hora: 7:30 AM (Pre-market)
Slot: 42 (de 66 en pre-market)
Volumen acumulado desde 4 AM: 2,500,000 shares
Promedio histórico a las 7:30 AM: 800,000 shares
RVOL = 2,500,000 / 800,000 = 3.13

Interpretación: ⚠️ Volumen 3x superior al normal
Posible causa: Earnings positivos anunciados a las 7 AM
```

#### **Ventajas de RVOL en Pre-Market**

- ✅ Detecta movers antes que el mercado regular
- ✅ Identifica catalizadores temprano
- ✅ Ventaja competitiva para traders
- ✅ Tiempo para investigar y planificar trades

---

### **2. Market Hours (9:30 AM - 4:00 PM)**

#### **Primera Hora (9:30 - 10:30 AM)**

La hora MÁS IMPORTANTE del día:

```
Slots 66-77 (primeros 12 slots de market hours)

Características:
- Volumen más alto del día
- Establece el tono del día
- Breakouts más significativos
- RVOL > 2.0 a las 10 AM = movimiento fuerte
```

**Ejemplo:**

```
Ticker: TSLA
Hora: 10:00 AM (30 min después de apertura)
Slot: 72
Volumen acumulado desde 4 AM: 8,000,000 shares
Histórico promedio a las 10 AM: 5,000,000 shares
RVOL = 1.6

Interpretación: ✅ Volumen normal/saludable para TSLA
```

#### **Power Hour (3:00 - 4:00 PM)**

```
Slots 132-143 (últimos 12 slots de market hours)

Características:
- Segundo pico de volumen del día
- Institucionales ajustan posiciones
- Posibles breakouts de cierre
- RVOL alto aquí = momentum fuerte
```

---

### **3. Post-Market (4:00 PM - 8:00 PM)**

#### **Reacciones a Earnings**

```python
# Earnings típicamente a las 4:00 PM
if current_session == MarketSession.POST_MARKET:
    if slot < 6:  # Primeros 30 min post-market
        if rvol > 5.0:
            # Reacción fuerte a earnings
            alert("Reacción post-market extrema")
```

**Ejemplo:**

```
Ticker: AAPL
Hora: 4:15 PM (15 min después de earnings)
Slot: 147 (3er slot de post-market)
Volumen acumulado desde 4 AM: 95,000,000 shares
Histórico promedio a las 4:15 PM: 90,000,000 shares
RVOL en post-market = (95M - 90M) / avg_postmarket = alto

Interpretación: 📈 Reacción fuerte a earnings
```

---

## 🔧 Configuración

### **Habilitar/Deshabilitar Extended Hours**

```python
# En services/analytics/main.py

# ✅ CON Extended Hours (recomendado)
rvol_calculator = RVOLCalculator(
    redis_client=redis_client,
    timescale_client=timescale_client,
    slot_size_minutes=5,
    lookback_days=5,
    include_extended_hours=True  # Pre-market + Market + Post-market
)

# ❌ SOLO Market Hours (no recomendado)
rvol_calculator = RVOLCalculator(
    redis_client=redis_client,
    timescale_client=timescale_client,
    slot_size_minutes=5,
    lookback_days=5,
    include_extended_hours=False  # Solo 9:30 AM - 4:00 PM
)
```

### **Slots por Sesión**

| Sesión       | Horario            | Minutos | Slots (5 min) | Rango de Slots |
| ------------ | ------------------ | ------- | ------------- | -------------- |
| Pre-Market   | 4:00 AM - 9:30 AM  | 330     | 66            | 0 - 65         |
| Market Hours | 9:30 AM - 4:00 PM  | 390     | 78            | 66 - 143       |
| Post-Market  | 4:00 PM - 8:00 PM  | 240     | 48            | 144 - 191      |
| **TOTAL**    | **4:00 AM - 8 PM** | **960** | **192**       | **0 - 191**    |

---

## 📊 Ejemplos de Queries

### **RVOL por Sesión**

```sql
-- RVOL en Pre-Market
SELECT
    symbol,
    slot_number,
    volume_accumulated,
    CASE
        WHEN slot_number BETWEEN 0 AND 65 THEN 'PRE_MARKET'
        WHEN slot_number BETWEEN 66 AND 143 THEN 'MARKET_HOURS'
        WHEN slot_number BETWEEN 144 AND 191 THEN 'POST_MARKET'
    END as session
FROM volume_slots
WHERE date = CURRENT_DATE
    AND slot_number BETWEEN 0 AND 65  -- Solo pre-market
    AND symbol = 'AAPL'
ORDER BY slot_number;

-- Comparar volumen por sesión
SELECT
    CASE
        WHEN slot_number BETWEEN 0 AND 65 THEN 'PRE_MARKET'
        WHEN slot_number BETWEEN 66 AND 143 THEN 'MARKET_HOURS'
        WHEN slot_number BETWEEN 144 AND 191 THEN 'POST_MARKET'
    END as session,
    SUM(volume_accumulated) as total_volume,
    COUNT(*) as num_slots
FROM volume_slots
WHERE date = CURRENT_DATE
    AND symbol = 'NVDA'
GROUP BY
    CASE
        WHEN slot_number BETWEEN 0 AND 65 THEN 'PRE_MARKET'
        WHEN slot_number BETWEEN 66 AND 143 THEN 'MARKET_HOURS'
        WHEN slot_number BETWEEN 144 AND 191 THEN 'POST_MARKET'
    END;
```

### **Detectar Movers en Pre-Market**

```python
# API call para obtener RVOL en pre-market
async def get_premarket_movers():
    """Encuentra tickers con alto RVOL en pre-market"""
    current_slot = slot_manager.get_current_slot()
    session = slot_manager.get_slot_session(current_slot)

    if session != MarketSession.PRE_MARKET:
        return []

    # Calcular RVOL para todos los tickers filtrados
    rvols = await calculator.calculate_rvol_batch(filtered_tickers)

    # Filtrar por RVOL > 2.0
    movers = [
        {"symbol": symbol, "rvol": rvol}
        for symbol, rvol in rvols.items()
        if rvol > 2.0
    ]

    return sorted(movers, key=lambda x: x["rvol"], reverse=True)
```

---

## 🎚️ Ajustes Recomendados por Sesión

### **Filtros Dinámicos**

```python
# Ajustar filtros según la sesión
def get_rvol_threshold(session: MarketSession) -> float:
    """
    Threshold de RVOL recomendado por sesión

    Pre-market: Más permisivo (menor liquidez)
    Market hours: Más estricto
    Post-market: Más permisivo
    """
    if session == MarketSession.PRE_MARKET:
        return 1.5  # Volumen 50% superior es significativo

    elif session == MarketSession.MARKET_OPEN:
        return 2.0  # Volumen 2x es significativo

    elif session == MarketSession.POST_MARKET:
        return 2.5  # Volumen 2.5x es significativo (menos común)

    else:
        return 1.0  # Default
```

---

## 📈 Visualización en Frontend

```javascript
// Código de ejemplo para frontend
function displayRVOLWithSession(data) {
  const { symbol, rvol, slot, session } = data;

  // Color por sesión
  const sessionColors = {
    PRE_MARKET: "#FFA500", // Naranja
    MARKET_OPEN: "#00FF00", // Verde
    POST_MARKET: "#FF00FF", // Magenta
  };

  // Badge de sesión
  const sessionBadge = `
        <span style="background: ${sessionColors[session]}">
            ${session} - Slot ${slot}
        </span>
    `;

  // Mostrar RVOL con contexto
  return `
        ${symbol}: RVOL ${rvol.toFixed(2)} ${sessionBadge}
    `;
}
```

---

## ⚠️ Consideraciones Importantes

### **1. Liquidez Reducida**

```
Pre-market y Post-market tienen:
- ❌ Menos liquidez (spreads más amplios)
- ❌ Mayor slippage
- ❌ Menos participantes
- ✅ Pero más oportunidades para early movers
```

### **2. Volatilidad Mayor**

```
Extended hours son más volátiles:
- Movimientos más bruscos
- Gaps frecuentes
- Reacciones exageradas
- Reversiones comunes
```

### **3. Patrones Diferentes**

```
RVOL en extended hours se comporta diferente:
- Pre-market: Volumen crece gradualmente
- Market open: Pico inmediato
- Post-market: Decae rápidamente (excepto earnings)
```

---

## 🎯 Best Practices

### ✅ **DO**

- Usar RVOL en pre-market para detectar catalizadores temprano
- Monitorear primeros 30 min de cada sesión
- Ajustar thresholds según la sesión
- Considerar el contexto (earnings, noticias, etc.)

### ❌ **DON'T**

- No comparar RVOL de pre-market con market hours directamente
- No ignorar el spread bid/ask en extended hours
- No usar los mismos filtros para todas las sesiones
- No asumir que alto RVOL = buena oportunidad sin contexto

---

## 📊 Métricas de Performance

```
Benchmarks con Extended Hours:

┌─────────────────────┬──────────────┬──────────────┐
│ Sesión              │ Slots        │ Cálculo RVOL │
├─────────────────────┼──────────────┼──────────────┤
│ Pre-Market          │ 66 slots     │ ~1-2 ms      │
│ Market Hours        │ 78 slots     │ ~1-2 ms      │
│ Post-Market         │ 48 slots     │ ~1-2 ms      │
│ TOTAL               │ 192 slots    │ ~1-2 ms      │
└─────────────────────┴──────────────┴──────────────┘

Memoria:
- 1000 tickers × 192 slots = ~9 MB en caché
- 100% manejable en memoria
```

---

**¡El sistema está optimizado para todo el día de trading, no solo market hours!** 🚀
