# 📡 Integración con Polygon - Volumen Acumulado

Documentación sobre cómo el Analytics Service obtiene y procesa el volumen acumulado desde Polygon.

---

## 🎯 Fuente de Datos: Polygon

El Analytics Service **NO calcula** el volumen acumulado manualmente.

Polygon proporciona el volumen **YA ACUMULADO** desde el inicio del día de trading en dos endpoints:

### **1. Snapshots API** (Data Ingest Service)

```json
GET /v2/snapshot/locale/us/markets/stocks/tickers

{
  "tickers": [
    {
      "ticker": "AAPL",
      "min": {
        "av": 45678900,  // ← Volumen ACUMULADO del día hasta ahora
        "c": 175.50,
        "h": 176.20,
        "l": 174.80,
        "o": 175.00,
        "t": 1729785600000,
        "v": 150000,      // ← Volumen del minuto actual
        "vw": 175.45      // ← VWAP del minuto
      },
      "day": {
        "c": 175.50,
        "h": 176.50,
        "l": 174.50,
        "o": 175.00,
        "v": 45678900,
        "vw": 175.30
      },
      ...
    }
  ]
}
```

**Campo clave:** `snapshot.min.av`

- **Significado**: Accumulated Volume (volumen acumulado)
- **Valor**: Suma de todo el volumen desde el inicio del día hasta el minuto actual
- **Actualización**: Cada snapshot (cada 5 segundos)

---

### **2. WebSocket Aggregates** (Polygon WS Connector)

```json
wss://socket.polygon.io/stocks

// Mensaje de Aggregate (cada segundo)
{
  "ev": "A",              // Event type: Aggregate
  "sym": "AAPL",
  "v": 1500,              // Volumen del segundo actual
  "av": 45678900,         // ← Volumen ACUMULADO del día hasta ahora
  "op": 175.00,           // Opening price (del día)
  "vw": 175.45,           // Today's VWAP
  "o": 175.40,            // Open (del segundo)
  "c": 175.50,            // Close (del segundo)
  "h": 175.55,            // High (del segundo)
  "l": 175.35,            // Low (del segundo)
  "a": 175.45,            // VWAP (del segundo)
  "s": 1729785601000,     // Start timestamp
  "e": 1729785602000      // End timestamp
}
```

**Campo clave:** `agg.av`

- **Significado**: Today's Accumulated Volume
- **Valor**: Suma de todo el volumen desde el inicio del día hasta el segundo actual
- **Actualización**: Cada segundo (en tiempo real)

---

## 🔄 Flujo de Datos en Analytics Service

### **Pipeline Completo**

```
┌─────────────────────────────────────────────────────────────┐
│  POLYGON API                                                │
│  - Snapshots: snapshot.min.av                               │
│  - WebSocket: agg.av                                        │
│  (Volumen YA acumulado desde 4 AM)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  Data Ingest / Polygon WS                                   │
│  → Publica a Redis Stream con volume_accumulated           │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  Scanner Service                                            │
│  → Filtra 11k → 500-1000 tickers                           │
│  → Publica a stream:scanner:filtered                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  Analytics Service                                          │
│  1. Lee volume_accumulated del stream                      │
│  2. Detecta slot actual (0-191)                            │
│  3. VolumeSlotCache.update_volume(slot, volume_accumulated)│
│  4. NO suma ni calcula, solo GUARDA                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  Cálculo de RVOL                                            │
│  rvol = volume_accumulated_today / avg_historical(slot)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 💻 Código de Integración

### **En Analytics Service** (`rvol_calculator.py`)

```python
async def update_volume_for_symbol(
    self,
    symbol: str,
    volume_accumulated: int,  # ← De Polygon min.av o av
    timestamp: Optional[datetime] = None,
    vwap: float = 0.0
):
    """
    IMPORTANTE: volume_accumulated debe venir de Polygon:
    - De Snapshots: snapshot.min.av
    - De WebSocket: agg.av

    Polygon proporciona el volumen YA ACUMULADO.
    NO calcular o sumar manualmente.
    """
    current_slot = self.slot_manager.get_current_slot(timestamp)

    # Guardar volumen acumulado en el slot actual
    self.volume_cache.update_volume(
        symbol=symbol,
        slot_number=current_slot,
        volume_accumulated=volume_accumulated,  # ← Directo de Polygon
        vwap=vwap
    )
```

### **En Data Ingest Service** (`snapshot_consumer.py`)

```python
# Ejemplo de cómo publicar snapshots a Redis
async def process_snapshot(snapshot: PolygonSnapshot):
    """Procesa un snapshot de Polygon"""

    # Extraer volumen acumulado de Polygon
    volume_accumulated = snapshot.min.av if snapshot.min else 0
    vwap = snapshot.min.vw if snapshot.min else 0.0

    # Publicar a Redis Stream
    await redis.publish_to_stream(
        "stream:snapshots",
        {
            'symbol': snapshot.ticker,
            'volume_accumulated': str(volume_accumulated),  # ← min.av
            'vwap': str(vwap),
            'price': str(snapshot.min.c) if snapshot.min else '0',
            'timestamp': datetime.now().isoformat()
        }
    )
```

### **En Polygon WS Connector** (`ws_handler.py`)

```python
# Ejemplo de cómo manejar WebSocket aggregates
async def on_aggregate(agg: PolygonAgg):
    """Procesa un mensaje de aggregate del WebSocket"""

    # Extraer volumen acumulado de Polygon
    volume_accumulated = agg.av  # ← Today's accumulated volume
    vwap = agg.a  # ← Today's VWAP

    # Publicar a Redis Stream
    await redis.publish_to_stream(
        "stream:realtime:aggregates",
        {
            'symbol': agg.sym,
            'volume_accumulated': str(volume_accumulated),  # ← agg.av
            'vwap': str(vwap),
            'price': str(agg.c),
            'timestamp': datetime.now().isoformat()
        }
    )
```

---

## ✅ Verificación

### **Comprobar que el volumen está acumulado**

```python
# Ejemplo con AAPL en un día típico:

# 9:30 AM (apertura) - Slot 66
volume_slot_66 = 5_000_000  # 5M shares en la primera hora

# 10:30 AM - Slot 78
volume_slot_78 = 12_000_000  # Acumulado desde 4 AM, NO solo última hora

# 4:00 PM (cierre) - Slot 143
volume_slot_143 = 85_000_000  # Volumen total del día

# ✅ CORRECTO: volume_slot_143 > volume_slot_78 > volume_slot_66
# ❌ INCORRECTO: Si los valores fueran iguales o menores
```

---

## ⚠️ Errores Comunes a Evitar

### ❌ **ERROR 1: Sumar volumen manualmente**

```python
# ❌ MAL - NO hacer esto
total_volume = 0
for trade in trades:
    total_volume += trade.volume  # NO!

await calculator.update_volume_for_symbol(
    symbol=symbol,
    volume_accumulated=total_volume  # ❌ Calculado manualmente
)
```

### ✅ **CORRECTO: Usar volumen de Polygon**

```python
# ✅ BIEN - Usar directamente de Polygon
volume_accumulated = snapshot.min.av  # o agg.av

await calculator.update_volume_for_symbol(
    symbol=symbol,
    volume_accumulated=volume_accumulated  # ✅ De Polygon
)
```

---

### ❌ **ERROR 2: Usar volumen del período en vez del acumulado**

```python
# ❌ MAL - Este es el volumen del minuto/segundo, no acumulado
volume = snapshot.min.v  # ← Volumen del minuto actual (NO acumulado)

# ✅ BIEN - Este es el volumen acumulado del día
volume_accumulated = snapshot.min.av  # ← Volumen acumulado
```

---

### ❌ **ERROR 3: Resetear volumen en cada slot**

```python
# ❌ MAL - El volumen acumulado NO se resetea por slot
if new_slot:
    volume_accumulated = 0  # ❌ NO resetear!

# ✅ BIEN - El volumen se acumula durante todo el día
# Solo se resetea al cambio de día (4 AM del día siguiente)
```

---

## 📊 Ejemplo Completo: Día de Trading de AAPL

```
Fecha: 2025-10-24
Ticker: AAPL

Slot |  Hora   | volume_accumulated (de Polygon min.av) | RVOL
-----|---------|----------------------------------------|------
  0  | 04:00   |        100,000                         | 0.8
  10 | 04:50   |        500,000                         | 0.9
  66 | 09:30   |      5,000,000  (apertura)             | 1.2
  78 | 10:30   |     12,000,000                         | 1.5
  90 | 12:30   |     25,000,000                         | 1.3
 132 | 15:00   |     65,000,000  (power hour)           | 1.8
 143 | 16:00   |     85,000,000  (cierre)               | 1.4
 150 | 16:35   |     87,000,000  (post-market)          | 1.1
 191 | 19:55   |     90,000,000  (fin post-market)      | 1.0

Observaciones:
1. ✅ El volumen SIEMPRE aumenta o se mantiene (nunca disminuye)
2. ✅ Picos de RVOL en apertura (slot 66) y power hour (slot 132)
3. ✅ El volumen post-market aumenta poco (baja liquidez)
4. ✅ Al día siguiente (4 AM), volume_accumulated vuelve a 0
```

---

## 🔍 Debugging

### **Verificar que el volumen viene de Polygon**

```bash
# En Redis, ver los mensajes publicados
redis-cli XREAD COUNT 10 STREAMS stream:snapshots 0

# Verificar que contiene volume_accumulated
1) "symbol"
2) "AAPL"
3) "volume_accumulated"
4) "45678900"  # ← Debe ser un número grande y creciente
5) "vwap"
6) "175.45"
```

### **Query SQL para verificar datos históricos**

```sql
-- Ver volumen por slot para AAPL hoy
SELECT
    slot_number,
    to_char(slot_time, 'HH24:MI') as hora,
    volume_accumulated,
    -- Verificar que el volumen siempre aumenta
    LAG(volume_accumulated) OVER (ORDER BY slot_number) as prev_volume,
    volume_accumulated - LAG(volume_accumulated) OVER (ORDER BY slot_number) as volume_diff
FROM volume_slots
WHERE date = CURRENT_DATE
    AND symbol = 'AAPL'
ORDER BY slot_number;

-- ✅ volume_diff debe ser siempre >= 0 (nunca negativo)
```

---

## 📚 Referencias de Polygon

- **Snapshots API**: https://polygon.io/docs/stocks/get_v2_snapshot_locale_us_markets_stocks_tickers
  - Campo: `min.av` (Accumulated Volume)
- **WebSocket Aggregates**: https://polygon.io/docs/stocks/ws_stocks_a
  - Campo: `av` (Today's Accumulated Volume)

---

## 🎯 Resumen

| ✅ **HACER**                      | ❌ **NO HACER**                             |
| --------------------------------- | ------------------------------------------- |
| Usar `snapshot.min.av` de Polygon | Calcular volumen sumando trades             |
| Usar `agg.av` del WebSocket       | Usar `snapshot.min.v` (volumen del período) |
| Guardar volumen acumulado directo | Resetear volumen en cada slot               |
| Confiar en los datos de Polygon   | Modificar o ajustar el volumen              |

---

**El Analytics Service es un CONSUMIDOR de datos de Polygon, NO un calculador de volumen.** 🎯
