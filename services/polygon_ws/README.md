# 📡 Polygon WebSocket Connector

Servicio para conectar al WebSocket de Polygon y consumir datos en tiempo real de los tickers filtrados por el Scanner.

---

## 🎯 Propósito

El Polygon WS Connector es el puente entre Polygon y el sistema, proporcionando:

- ✅ **Trades** en tiempo real (ejecuciones)
- ✅ **Quotes** (NBBO - National Best Bid and Offer)
- ✅ **Aggregates** por segundo (OHLCV en tiempo real)
- ✅ **Suscripción dinámica** a 500-1000 tickers filtrados
- ✅ **Reconexión automática** y manejo robusto de errores

---

## 🏗️ Arquitectura

### **Flujo de Datos**

```
┌─────────────────────────────────────────────────────────┐
│  Scanner Service                                         │
│  - Filtra 11k → 500-1000 tickers                        │
│  - Publica a stream:scanner:filtered                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Polygon WS Connector (este servicio)                   │
│  1. Lee tickers filtrados del stream                    │
│  2. Actualiza suscripciones dinámicamente               │
│  3. Conecta a wss://socket.polygon.io/stocks            │
│  4. Autentica con API key                               │
│  5. Suscribe: T.AAPL,Q.AAPL,A.AAPL,T.TSLA...           │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐    ┌────────▼────────┐    ┌────────▼────────┐
│  stream:        │    │  stream:        │    │  stream:        │
│  realtime:      │    │  realtime:      │    │  realtime:      │
│  trades         │    │  quotes         │    │  aggregates     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────┬───────────┴───────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Analytics Service / API Gateway                        │
│  - Consume streams en tiempo real                       │
│  - Calcula RVOL preciso                                 │
│  - Publica a frontend vía WebSocket                     │
└─────────────────────────────────────────────────────────┘
```

---

## 🔌 WebSocket de Polygon

### **Conexión**

```python
# URL del WebSocket
wss://socket.polygon.io/stocks

# Autenticación
{
  "action": "auth",
  "params": "YOUR_API_KEY"
}

# Respuesta
[{"status": "auth_success", "message": "authenticated"}]
```

### **Suscripción**

```python
# Suscribirse a múltiples tickers y eventos
{
  "action": "subscribe",
  "params": "T.AAPL,Q.AAPL,A.AAPL,T.TSLA,Q.TSLA,A.TSLA"
}

# T = Trades
# Q = Quotes (NBBO)
# A = Aggregates (per second)
```

### **Tipos de Mensajes**

#### **1. Trade (T)**

```json
{
  "ev": "T",
  "sym": "AAPL",
  "x": 4, // Exchange ID
  "p": 175.5, // Price
  "s": 100, // Size
  "c": [14, 41], // Conditions
  "t": 1729785601000, // Timestamp
  "i": "12345", // Trade ID
  "z": 3 // Tape (1=NYSE, 2=AMEX, 3=Nasdaq)
}
```

#### **2. Quote (Q)**

```json
{
  "ev": "Q",
  "sym": "AAPL",
  "bx": 4, // Bid exchange
  "bp": 175.48, // Bid price
  "bs": 5, // Bid size (lots of 100)
  "ax": 4, // Ask exchange
  "ap": 175.52, // Ask price
  "as": 3, // Ask size
  "t": 1729785601000, // Timestamp
  "z": 3 // Tape
}
```

#### **3. Aggregate (A)**

```json
{
  "ev": "A",
  "sym": "AAPL",
  "v": 1500, // Volume (of this second)
  "av": 45678900, // ← Accumulated volume (del día completo)
  "op": 175.0, // Open price (del día)
  "vw": 175.45, // VWAP (del segundo)
  "o": 175.4, // Open (del segundo)
  "c": 175.5, // Close (del segundo)
  "h": 175.55, // High (del segundo)
  "l": 175.35, // Low (del segundo)
  "a": 175.45, // Today's VWAP
  "s": 1729785601000, // Start timestamp
  "e": 1729785602000 // End timestamp
}
```

**IMPORTANTE:** `agg.av` es el volumen ACUMULADO del día, igual que `snapshot.min.av`.

---

## 🔄 Suscripción Dinámica

### **Actualización Automática**

El servicio ajusta las suscripciones dinámicamente basándose en el Scanner:

```python
# Scanner filtra y publica
Scanner → stream:scanner:filtered → ["AAPL", "TSLA", "NVDA", ...]

# Polygon WS lee y ajusta suscripciones
1. Lee nuevos tickers del stream
2. Compara con suscripciones actuales
3. Desuscribe tickers antiguos
4. Suscribe nuevos tickers
5. Log: "subscriptions_updated: 847 tickers"
```

### **Ventajas**

- ✅ No desperdicia suscripciones en tickers sin movimiento
- ✅ Se adapta automáticamente al universo filtrado
- ✅ Optimiza el uso del WebSocket (max 1000 suscripciones)
- ✅ Sin intervención manual

---

## 📊 Publicación a Redis Streams

### **Stream: realtime:trades**

```python
{
  'symbol': 'AAPL',
  'price': '175.50',
  'size': '100',
  'conditions': '14,41',
  'exchange': '4',
  'trade_id': '12345',
  'timestamp': '1729785601000',
  'tape': '3'
}
```

### **Stream: realtime:quotes**

```python
{
  'symbol': 'AAPL',
  'bid_price': '175.48',
  'bid_size': '5',
  'ask_price': '175.52',
  'ask_size': '3',
  'bid_exchange': '4',
  'ask_exchange': '4',
  'timestamp': '1729785601000',
  'tape': '3'
}
```

### **Stream: realtime:aggregates**

```python
{
  'symbol': 'AAPL',
  'open': '175.40',
  'high': '175.55',
  'low': '175.35',
  'close': '175.50',
  'volume': '1500',             # Volumen del segundo
  'volume_accumulated': '45678900',  # ← Volumen acumulado del día
  'vwap': '175.45',             # Today's VWAP
  'trades_count': '25',
  'timestamp_start': '1729785601000',
  'timestamp_end': '1729785602000',
  'otc': 'false'
}
```

---

## 🛡️ Manejo de Errores y Reconexión

### **Reconexión Automática**

```python
# Estrategia de backoff exponencial
Intento 1: 5 segundos
Intento 2: 10 segundos
Intento 3: 15 segundos
...
Intento 10: 50 segundos (máximo)

# Después de 10 intentos fallidos, el servicio se detiene
```

### **Tipos de Errores Manejados**

- ✅ Pérdida de conexión
- ✅ Fallo de autenticación
- ✅ Timeout de ping/pong
- ✅ Mensajes malformados
- ✅ Errores del servidor de Polygon

---

## 🚀 API Endpoints

### **GET /health**

Health check del servicio

```bash
curl http://localhost:8006/health
```

**Respuesta:**

```json
{
  "status": "healthy",
  "service": "polygon_ws",
  "timestamp": "2025-10-24T10:30:00-04:00",
  "ws_connected": true,
  "ws_authenticated": true
}
```

### **GET /stats**

Estadísticas del WebSocket

```bash
curl http://localhost:8006/stats
```

**Respuesta:**

```json
{
  "trades_received": 125847,
  "quotes_received": 458392,
  "aggregates_received": 89234,
  "errors": 3,
  "reconnections": 1,
  "last_message_time": "2025-10-24T10:30:15-04:00",
  "is_connected": true,
  "is_authenticated": true,
  "subscribed_tickers_count": 847,
  "reconnect_attempts": 0
}
```

### **GET /subscriptions**

Suscripciones activas

```bash
curl http://localhost:8006/subscriptions
```

**Respuesta:**

```json
{
  "subscribed_tickers": ["AAPL", "TSLA", "NVDA", ...],
  "count": 847,
  "is_authenticated": true
}
```

---

## 🎛️ Configuración

### **Variables de Entorno**

```bash
# Polygon API
POLYGON_API_KEY=your_api_key_here

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# WebSocket
WS_MAX_RECONNECT_ATTEMPTS=10
WS_RECONNECT_DELAY=5
```

### **Tipos de Eventos**

```python
# Configurar qué eventos suscribir
event_types = {"T", "Q", "A"}  # Default: Todos

# Solo Aggregates (más eficiente)
event_types = {"A"}

# Solo Trades y Quotes
event_types = {"T", "Q"}
```

---

## 📈 Performance

### **Capacidad**

- **Suscripciones simultáneas**: 1,000 tickers (Polygon Advanced Plan)
- **Mensajes por segundo**: 10,000+ (depende de volatilidad)
- **Latencia**: <100ms (desde Polygon hasta Redis)
- **Throughput**: 1MB/s - 10MB/s (depende de actividad)

### **Optimizaciones**

- ✅ Procesamiento asíncrono de mensajes
- ✅ Batch publishing a Redis Streams
- ✅ Heartbeat automático (ping/pong)
- ✅ Desuscripción de tickers inactivos

---

## 🐛 Debugging

### **Ver logs del servicio**

```bash
docker-compose logs -f polygon_ws
```

### **Ver mensajes en Redis**

```bash
# Trades
redis-cli XREAD COUNT 10 STREAMS stream:realtime:trades 0

# Quotes
redis-cli XREAD COUNT 10 STREAMS stream:realtime:quotes 0

# Aggregates
redis-cli XREAD COUNT 10 STREAMS stream:realtime:aggregates 0
```

### **Verificar suscripciones**

```bash
curl http://localhost:8006/subscriptions | jq
```

---

## ⚠️ Consideraciones

### **Límites de Polygon**

- Advanced Plan: 1,000 suscripciones simultáneas
- Starter Plan: 100 suscripciones
- Free Plan: 5 suscripciones

### **Uso de Datos**

Un día típico con 800 tickers puede generar:

- Trades: ~500K mensajes
- Quotes: ~2M mensajes
- Aggregates: ~3M mensajes (1 por segundo por ticker)

### **Redis Memory**

Los streams se deben limpiar periódicamente:

```bash
# Mantener solo últimos 1000 mensajes por stream
redis-cli XTRIM stream:realtime:aggregates MAXLEN ~ 1000
```

---

## 🔮 Roadmap

- [ ] Compresión de mensajes para reducir ancho de banda
- [ ] Métricas Prometheus
- [ ] Circuit breaker para errores repetidos
- [ ] Filtrado de mensajes por condiciones

---

**Conectado a Polygon para datos en tiempo real de máxima calidad** 📡
