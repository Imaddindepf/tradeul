================================================================================
TICKER METADATA SERVICE
================================================================================

Servicio especializado en gestión de metadatos de compañías y tickers.

RESPONSABILIDADES:
- Enriquecer metadata desde fuentes externas (Polygon API)
- Mantener cache en Redis (fast access)
- Persistir en TimescaleDB (durabilidad)
- Exponer API REST para otros servicios

================================================================================
ARQUITECTURA
================================================================================

metadata_manager.py        → Core business logic
  ├── providers/
  │   ├── polygon_provider.py    → Integración con Polygon API
  │   └── cache_provider.py      → Cache Redis
  ├── api/
  │   ├── metadata_router.py     → Endpoints de metadata
  │   ├── company_router.py      → Endpoints de compañía
  │   └── statistics_router.py   → Endpoints de stats
  └── tasks/
      └── enrich_stale_metadata.py  → Background task opcional

================================================================================
FLUJO DE DATOS
================================================================================

1. Request → /api/v1/metadata/AAPL

2. metadata_manager.get_metadata():
   ├── Check Redis cache (TTL 1h)
   │   └── ✓ HIT → Return cached
   │   └── ✗ MISS → Continue
   │
   ├── Query TimescaleDB
   │   └── ✓ Found & Fresh (< 7 days) → Cache + Return
   │   └── ✓ Found & Stale (> 7 days) → Enrich from Polygon
   │   └── ✗ Not Found → Enrich from Polygon
   │
   └── Enrich from Polygon API
       ├── Call /v3/reference/tickers/{symbol}
       ├── Parse response
       ├── Save to TimescaleDB
       ├── Save to Redis cache
       └── Return

3. Response → {symbol, company_name, sector, industry, ...}

================================================================================
API ENDPOINTS
================================================================================

PORT: 8010
Base URL: http://localhost:8010

HEALTH:
-------
GET /health
    → Service health check

METADATA:
---------
GET /api/v1/metadata/{symbol}
    → Obtiene metadata completo de un ticker
    Query params:
      - force_refresh=true : Fuerza refresh desde Polygon
    
POST /api/v1/metadata/{symbol}/refresh
    → Fuerza refresh manual de metadata
    
POST /api/v1/metadata/bulk/refresh
    Body: {"symbols": ["AAPL", "TSLA", ...]}
    → Refresh múltiples symbols en paralelo
    
GET /api/v1/metadata/stats/service
    → Estadísticas del servicio (cache hit rate, API calls, etc)

COMPANY:
--------
GET /api/v1/company/{symbol}
    → Perfil completo de la compañía
    
GET /api/v1/company/{symbol}/info
    → Info básica (nombre, exchange, sector, industria)

STATISTICS:
-----------
GET /api/v1/statistics/{symbol}
    → Estadísticas de mercado (market cap, float, volumes, beta)

================================================================================
EJEMPLOS DE USO
================================================================================

1. Obtener metadata de Apple:
   curl http://localhost:8010/api/v1/metadata/AAPL

2. Forzar refresh:
   curl http://localhost:8010/api/v1/metadata/AAPL?force_refresh=true

3. Refresh manual:
   curl -X POST http://localhost:8010/api/v1/metadata/AAPL/refresh

4. Bulk refresh:
   curl -X POST http://localhost:8010/api/v1/metadata/bulk/refresh \
     -H "Content-Type: application/json" \
     -d '{"symbols": ["AAPL", "TSLA", "NVDA"]}'

5. Ver stats del servicio:
   curl http://localhost:8010/api/v1/metadata/stats/service

6. Obtener info de compañía:
   curl http://localhost:8010/api/v1/company/AAPL

================================================================================
CONFIGURACIÓN
================================================================================

Variables de entorno (heredadas de .env):

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

TIMESCALE_HOST=timescaledb
TIMESCALE_PORT=5432
TIMESCALE_DB=tradeul
TIMESCALE_USER=tradeul_user
TIMESCALE_PASSWORD=***

POLYGON_API_KEY=***

================================================================================
DEPENDENCIAS
================================================================================

SERVICIOS:
- Redis (cache)
- TimescaleDB (persistencia)

EXTERNOS:
- Polygon.io API (fuente de metadata)

CONSUMIDORES:
- api-gateway (principal)
- Cualquier servicio que necesite metadata

================================================================================
DEPLOYMENT
================================================================================

Docker Compose:
  docker-compose up -d ticker_metadata

Build manual:
  cd services/ticker-metadata-service
  docker build -t ticker-metadata-service .
  docker run -p 8010:8010 ticker-metadata-service

Logs:
  docker logs -f tradeul_ticker_metadata

Health Check:
  curl http://localhost:8010/health

================================================================================
PERFORMANCE
================================================================================

CACHE HIT RATE: ~80-90% esperado (1 hora TTL)
LATENCY:
  - Cache hit: < 5ms
  - DB hit: < 20ms
  - API call (cold): 200-500ms

RATE LIMITING:
  - Polygon API: 5 requests/segundo
  - Bulk refresh: Max 20 concurrent (configurable)

ESCALABILIDAD:
  - Stateless (puede escalar horizontalmente)
  - Redis shared entre instancias
  - DB connection pool

================================================================================
MONITORING
================================================================================

MÉTRICAS DISPONIBLES:
- GET /api/v1/metadata/stats/service
  {
    "cache_hit_rate": "85.2%",
    "cache_hits": 1523,
    "cache_misses": 265,
    "db_hits": 180,
    "api_calls": 85,
    "errors": 2
  }

LOGS:
- structlog format (JSON)
- Niveles: debug, info, warning, error
- Eventos clave:
  * metadata_cache_hit
  * metadata_db_hit
  * metadata_enriched
  * polygon_rate_limited
  * cache_get_failed

================================================================================
TROUBLESHOOTING
================================================================================

PROBLEMA: Servicio no arranca
  → Verificar Redis y TimescaleDB están running
  → docker-compose ps

PROBLEMA: 404 - Metadata not found
  → Symbol no existe en Polygon
  → Verificar símbolo es válido

PROBLEMA: Latencia alta
  → Check cache hit rate (debe ser > 70%)
  → Verificar Redis no está sobrecargado

PROBLEMA: Polygon rate limit
  → Reduce bulk_refresh concurrent requests
  → Espera automática implementada (0.2s entre requests)

================================================================================
DESARROLLO
================================================================================

Ejecutar localmente:
  cd services/ticker-metadata-service
  export PYTHONPATH=/app
  python main.py

Tests (futuro):
  pytest tests/

Linting:
  ruff check .
  mypy .

================================================================================
ROADMAP
================================================================================

v1.1 (Futuro):
  - Agregar más providers (FMP, Alpha Vantage)
  - Cache tiering (L1: memory, L2: Redis)
  - Métricas Prometheus
  - Background scheduler integrado
  - Webhooks para notificar cambios

v1.2:
  - GraphQL API
  - Búsqueda fuzzy de companies
  - Clasificación automática de sectores (ML)

================================================================================
FIN
================================================================================

