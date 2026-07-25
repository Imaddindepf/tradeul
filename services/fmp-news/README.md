# FMP News Service

Ingesta los feeds de noticias de Financial Modeling Prep hacia el pipeline
unificado de noticias de Tradeul (cache Redis + stream + websocket + frontend).

## Feeds

| Feed | Endpoint FMP | Channel | Intervalo |
|------|--------------|---------|-----------|
| Stock News | `/stable/news/stock-latest` | `Stock` | 20s |
| Press Releases | `/stable/news/press-releases-latest` | `Press Releases` | 20s |
| General News | `/stable/news/general-latest` | `General` | 60s |
| Forex News | `/stable/news/forex-latest` | `Forex` | 120s |
| FMP Articles | `/stable/fmp-articles` | `FMP` | 300s |

Crypto queda fuera a propósito.

## Integración

- Cada artículo se normaliza al shape del pipeline (`id` = hash de la URL,
  `author` = publisher, `published` en ISO 8601 con offset) y se publica en
  `stream:benzinga:news` (stream unificado, nombre histórico) y en la cache
  compartida `cache:benzinga:news:latest` / `cache:benzinga:news:ticker:*`.
  Con eso el websocket_server y la ventana de News del frontend lo reciben
  sin cambios.
- Los artículos cuyo publisher es Reuters se cachean además en
  `cache:fmp:news:reuters` y se sirven en `GET /api/v1/news/top`
  (proxy del gateway: `/news/api/v1/news/top`) — feed "Top News".

## Timezones

FMP devuelve `publishedDate` de los feeds `/news/*` en hora del Este y
`date` de `/fmp-articles` en UTC (verificado empíricamente). La conversión
se hace en `models/news.py`.

## Endpoints

- `GET /health`
- `GET /status` — stats de polling por feed
- `GET /api/v1/news/top?limit=100&offset=0`
