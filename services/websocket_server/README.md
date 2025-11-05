# Tradeul WebSocket Server

Servidor WebSocket de alto rendimiento usando **uWebSockets.js**, separado de Next.js para máximo rendimiento.

## Características

- 🚀 **uWebSockets.js**: El servidor WebSocket más rápido en Node.js (benchmark líder)
- 📡 **Redis Streams**: Consume streams en tiempo real directamente desde Redis
- 🎯 **Suscripciones selectivas**: Solo envía datos de tickers suscritos
- ⚡ **Alto rendimiento**: Optimizado para miles de conexiones simultáneas
- 🔄 **Transformación automática**: Convierte datos Redis → Formato Polygon
- 💪 **Resiliente**: Reconnection automática y manejo de errores

## Arquitectura

```
Redis Streams → uWebSockets.js Server → Frontend Clients
                    ↓
              Consumer Groups
              - stream:realtime:aggregates
              - stream:analytics:rvol
```

## Variables de Entorno

```bash
WS_PORT=9000              # Puerto del servidor WebSocket
REDIS_HOST=redis          # Host de Redis
REDIS_PORT=6379           # Puerto de Redis
LOG_LEVEL=info           # Nivel de logging (debug, info, warn, error)
```

## Uso

### Desarrollo

```bash
npm install
npm run dev
```

### Producción (Docker)

```bash
docker build -t tradeul-websocket-server .
docker run -p 9000:9000 -e REDIS_HOST=redis tradeul-websocket-server
```

## API WebSocket

### Conectar

```javascript
const ws = new WebSocket("ws://localhost:9000/ws/scanner");
```

### Suscribirse a tickers específicos

```json
{
  "action": "subscribe",
  "symbols": ["AAPL", "TSLA", "MSFT"]
}
```

### Suscribirse a todos

```json
{
  "action": "subscribe_all"
}
```

### Desuscribirse

```json
{
  "action": "unsubscribe",
  "symbols": ["AAPL"]
}
```

### Ping

```json
{
  "action": "ping"
}
```

## Mensajes Recibidos

### Connected

```json
{
  "type": "connected",
  "connection_id": "uuid",
  "message": "Connected to Tradeul Scanner",
  "timestamp": "2024-..."
}
```

### Aggregate Data

```json
{
  "type": "aggregate",
  "symbol": "AAPL",
  "data": {
    "o": 150.0,
    "h": 151.0,
    "l": 149.0,
    "c": 150.5,
    "v": 1000000,
    "av": 5000000,
    "vw": 150.2
  },
  "timestamp": "2024-..."
}
```

## Health Check

```bash
curl http://localhost:9000/health
```

Respuesta:

```json
{
  "status": "ok",
  "connections": 42,
  "timestamp": "2024-..."
}
```

