# Benzinga News Service 📰

Servicio de streaming de noticias de Benzinga en tiempo real.

## 🎯 Características

### Real-Time (Polling)
- ✅ Polling periódico a Benzinga API (via Polygon.io)
- ✅ Publicación a Redis streams para broadcast al frontend
- ✅ Caché de noticias recientes y por ticker
- ✅ Deduplicación automática

### REST API
- ✅ Endpoints para buscar y filtrar noticias
- ✅ Búsqueda por ticker, channels, tags, autor
- ✅ Paginación

## 🚀 Quick Start

### 1. Configurar API Key

Asegúrate de tener la API key de Polygon.io en el `.env`:

```bash
POLYGON_API_KEY=tu_api_key_aqui
```

### 2. Levantar servicio

```bash
docker-compose up -d benzinga-news
```

### 3. Verificar estado

```bash
curl http://localhost:8015/health
curl http://localhost:8015/status
```

## 📡 REST API Endpoints

### Health & Status

#### GET `/health`
Health check del servicio

#### GET `/status`
Estado completo del servicio

#### GET `/stream/status`
Estado del polling de noticias

---

### News API

#### GET `/api/v1/news`
Buscar noticias con filtros

**Query Parameters:**
- `ticker` - Símbolo del ticker (e.g., TSLA)
- `channels` - Canales/categorías (comma-separated)
- `tags` - Tags del artículo
- `author` - Nombre del autor
- `date_from` - Fecha inicio (YYYY-MM-DD)
- `date_to` - Fecha fin (YYYY-MM-DD)
- `limit` - Límite de resultados (default: 50, max: 200)

**Ejemplo:**
```bash
curl "http://localhost:8015/api/v1/news?ticker=TSLA&limit=10"
```

#### GET `/api/v1/news/latest`
Obtener últimas noticias

```bash
curl "http://localhost:8015/api/v1/news/latest?limit=20"
```

#### GET `/api/v1/news/ticker/{ticker}`
Obtener noticias para un ticker específico

```bash
curl "http://localhost:8015/api/v1/news/ticker/AAPL"
```

#### GET `/api/v1/news/live`
Obtener noticias directamente de la API (sin caché)

```bash
curl "http://localhost:8015/api/v1/news/live?limit=50"
```

## 🔧 Configuración

Variables de entorno:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `POLYGON_API_KEY` | - | API key de Polygon.io (requerido) |
| `REDIS_HOST` | redis | Host de Redis |
| `REDIS_PORT` | 6379 | Puerto de Redis |
| `REDIS_PASSWORD` | - | Password de Redis |
| `SERVICE_PORT` | 8015 | Puerto del servicio |
| `POLL_INTERVAL_SECONDS` | 5 | Intervalo de polling |
| `LOG_LEVEL` | INFO | Nivel de logging |

## 📊 Redis Keys

| Key | Tipo | Descripción |
|-----|------|-------------|
| `stream:benzinga:news` | Stream | Stream para broadcast de noticias |
| `cache:benzinga:news:latest` | ZSet | Últimas 500 noticias |
| `cache:benzinga:news:ticker:{TICKER}` | ZSet | Últimas 100 noticias por ticker |
| `dedup:benzinga:news` | Set | IDs procesados (deduplicación) |
| `benzinga:news:last_poll` | String | Timestamp del último poll |

## 🔌 WebSocket Integration

El WebSocket server consume `stream:benzinga:news` y hace broadcast a clientes suscritos.

Frontend se suscribe con:
```javascript
ws.send({ action: 'subscribe_benzinga_news' });
```

Y recibe mensajes:
```json
{
  "type": "benzinga_news",
  "article": { ... },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

