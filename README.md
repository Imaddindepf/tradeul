# 📈 Tradeul Scanner - Sistema de Escaneo en Tiempo Real

Sistema profesional de escaneo de mercados en tiempo real para 11,000+ acciones, con arquitectura de microservicios escalable.

## ✨ Características Principales

- 🚀 **Escalable**: Procesa 11,882 tickers con snapshots cada 5 segundos
- ⚡ **Tiempo Real**: WebSocket con datos segundo a segundo de Polygon
- 📊 **RVOL Preciso**: Cálculo por slots de 5 minutos (siguiendo lógica de PineScript)
- 🌅 **Extended Hours**: Soporte completo para pre-market y post-market (4 AM - 8 PM ET)
- 🔥 **Pre-Market Warmup**: Datos FMP precargados a las 3 AM (sin delays)
- 🔄 **Suscripción Dinámica**: WebSocket se ajusta automáticamente a tickers filtrados
- 💾 **Histórico**: Persistencia en TimescaleDB para backtesting
- 🎯 **Filtros Configurables**: 3 filtros listos, modificables vía SQL
- 🌐 **REST + WebSocket API**: Gateway completo para frontend web

## 🏗️ Arquitectura

### Microservicios

- **API Gateway** (Puerto 8000): REST API + WebSocket para frontend
- **Orchestrator** (Puerto 8001): Coordinador del pipeline completo
- **Market Session** (Puerto 8002): Detección de horarios de mercado
- **Data Ingest** (Puerto 8003): Consumo de snapshots de Polygon
- **Historical** (Puerto 8004): Datos históricos y de referencia (FMP)
- **Scanner** (Puerto 8005): Motor de escaneo y filtrado
- **Polygon WS** (Puerto 8006): WebSocket tiempo real para tickers filtrados
- **Analytics** (Puerto 8007): Cálculos avanzados (RVOL, indicadores)
- **Admin Panel** (Puerto 8008): Panel de configuración de filtros

### Infraestructura

- **Redis**: Message broker, cache, pub/sub
- **TimescaleDB**: Almacenamiento de series temporales
- **Nginx**: Reverse proxy (opcional)

## 🚀 Inicio Rápido

### **⚠️ IMPORTANTE: Verificar Docker Primero**

Antes de ejecutar el setup, asegúrate de que Docker puede descargar imágenes:

```bash
docker pull hello-world
```

**Si falla** → Lee `docs/DOCKER_ISSUES.md` para solucionar problemas de red.

**Si funciona** ✅ → Continúa con el setup:

---

### **Opción 1: Setup Automatizado** ⭐ (Recomendado)

El script automatizado configura todo el sistema en un solo comando:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

El script se encarga de:

- ✅ Verificar Docker y Docker Compose
- ✅ Solicitar tus API Keys (Polygon y FMP)
- ✅ Crear archivo `.env` con configuración
- ✅ Levantar Redis y TimescaleDB
- ✅ Inicializar base de datos con todas las tablas
- ✅ Construir imágenes Docker de todos los servicios
- ✅ Cargar universo inicial (~11,000 tickers)
- ✅ Iniciar todos los servicios
- ✅ Verificar que todo funcione correctamente

**Tiempo estimado**: 10-15 minutos la primera vez.

---

### **Opción 2: Guía Paso a Paso Detallada** 📚

Para una instalación paso a paso con explicaciones completas, sigue la guía detallada:

👉 **[Ver Guía Completa de Instalación](docs/QUICKSTART.md)**

La guía incluye:

- Pre-requisitos y verificación
- Obtención de API Keys
- Configuración manual detallada
- Troubleshooting común
- Comandos útiles de mantenimiento
- Dashboard de monitoreo

---

### **Opción 3: Setup Manual Rápido** 🛠️

Si prefieres configurar manualmente:

```bash
# 1. Configurar variables de entorno
nano .env  # Agregar API keys de Polygon y FMP

# 2. Levantar infraestructura
docker-compose up -d redis timescaledb
sleep 10  # Esperar que estén listos

# 3. Inicializar base de datos
docker cp scripts/init_db.sql tradeul-timescaledb:/tmp/init_db.sql
docker exec tradeul-timescaledb psql -U tradeul_user -d tradeul_scanner -f /tmp/init_db.sql

# 4. Construir imágenes
docker-compose build

# 5. Cargar universo de tickers (opcional pero recomendado)
python3 scripts/load_universe.py

# 6. Iniciar todos los servicios
docker-compose up -d
```

---

### **Verificación del Sistema**

```bash
# Estado de todos los servicios
docker-compose ps

# Health check del API Gateway
curl http://localhost:8000/health

# Sesión de mercado actual
curl http://localhost:8002/session/current | jq

# Tickers filtrados
curl http://localhost:8000/api/v1/scanner/filtered | jq

# RVOL de un ticker específico
curl http://localhost:8000/api/v1/rvol/AAPL | jq

# Ver logs en tiempo real
docker-compose logs -f scanner
```

## 📊 Pipeline de Datos

```
┌─────────────────────────────────────────────────────────┐
│  Polygon Snapshots (11,000 tickers cada 5 seg)          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Data Ingest Service                                     │
│  - Consume snapshots                                     │
│  - Publica a Redis Streams                              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Historical Service (FMP)                                │
│  - Perfiles de empresas                                  │
│  - Float, Market Cap                                     │
│  - Promedios de volumen                                  │
│  - Datos históricos (batch/bulk)                        │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Scanner Service (FASE 1)                                │
│  - Combina snapshots + datos históricos                 │
│  - Calcula RVOL SIMPLE (rápido)                         │
│  - Aplica filtros configurables                          │
│  - Reduce: 11,000 → 500-1000 tickers                    │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐    ┌────────▼────────────────────────┐
│  Polygon WS     │    │  Analytics Service (FASE 2)     │
│  - Trades       │    │  - RVOL por slots (preciso)     │
│  - Quotes       │    │  - Divide día en 78 slots       │
│  - Aggregates   │    │  - Compara con histórico slot   │
│  - Real-time    │    │  - Guarda en TimescaleDB        │
│  500-1000 subs  │    │  - Caché en Redis               │
└────────┬────────┘    └────────┬────────────────────────┘
         │                       │
         └───────────┬───────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  API Gateway                                             │
│  - REST API endpoints                                    │
│  - WebSocket para frontend                               │
│  - Agregación de datos                                   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Frontend Web                                            │
│  - Datos en tiempo real (precio, volumen, RVOL)         │
│  - Actualizaciones vía WebSocket                         │
│  - Panel de administración                               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Market Session Service (Transversal)                    │
│  - Detecta: PRE_MARKET, MARKET_OPEN, POST_MARKET        │
│  - Usa Polygon market status API                         │
│  - Maneja holidays y early closes                        │
│  - Resetea buffers en cambio de día                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Orchestrator Service                                    │
│  - Coordina todos los servicios                          │
│  - Health checks                                         │
│  - Reintentos y fallbacks                               │
└─────────────────────────────────────────────────────────┘
```

## 🔧 Configuración de Filtros

Los filtros se configuran desde el Admin Panel o via API:

```bash
# Ejemplo: Configurar filtro de RVOL
curl -X POST http://localhost:8008/api/filters \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_admin_key" \
  -d '{
    "name": "rvol_filter",
    "enabled": true,
    "parameters": {
      "min_rvol": 2.0,
      "min_price": 1.0,
      "min_volume": 100000,
      "max_price": 500.0
    }
  }'
```

## 📡 API Endpoints

### API Gateway (Puerto 8000)

```
GET  /api/v1/scanner/status       - Estado del scanner
GET  /api/v1/scanner/filtered     - Tickers filtrados actuales
GET  /api/v1/ticker/{symbol}      - Info de un ticker específico
WS   /ws/realtime                 - WebSocket para datos en tiempo real
WS   /ws/scanner                  - WebSocket para resultados de scan
```

### Admin Panel (Puerto 8008)

```
GET    /api/filters               - Listar filtros configurados
POST   /api/filters               - Crear/actualizar filtro
DELETE /api/filters/{id}          - Eliminar filtro
GET    /api/universe              - Ver universo actual
POST   /api/universe/reload       - Recargar universo
GET    /api/stats                 - Estadísticas del sistema
```

## 🧮 Indicadores Calculados

### RVOL (Relative Volume) - Pipeline de 2 Fases

El sistema implementa un cálculo de RVOL en dos fases para máxima escalabilidad y precisión:

#### **Fase 1: RVOL Simple (Scanner Service)**

```
RVOL Simple = volumen_total_hoy / avg_volume_30d

Propósito: Screening inicial rápido
Aplicado a: 11,000 tickers
Resultado: Reduce universo a 500-1000 tickers
```

#### **Fase 2: RVOL por Slots (Analytics Service)**

```
Implementación basada en PineScript:

1. División del día en slots de 5 minutos (78 slots = 390 minutos)
2. Volumen acumulado hasta el slot actual
3. Promedio histórico de los últimos N días para el mismo slot

RVOL(slot_N) = volume_accumulated_today(slot_N) / avg_historical(slot_N)

Ejemplo a las 10:30 AM (slot 12):
- Volumen acumulado hoy hasta 10:30: 500,000 shares
- Histórico últimos 5 días a las 10:30:
  * Día -1: 300,000
  * Día -2: 400,000
  * Día -3: 350,000
  * Día -4: 380,000
  * Día -5: 370,000
  Promedio: 360,000

RVOL = 500,000 / 360,000 = 1.39 ✅

Propósito: Cálculo preciso considerando patrones intraday
Aplicado a: 500-1000 tickers filtrados
Resultado: RVOL ultra preciso para trading decisions
```

**Ventajas del Enfoque:**

- ✅ **Escalable**: No calculamos slots para 11k tickers
- ✅ **Preciso**: RVOL detallado donde realmente importa
- ✅ **Rápido**: Screening inicial en milisegundos
- ✅ **Robusto**: Fallback si Analytics falla

### RVOL API Endpoints

```bash
# Obtener RVOL preciso de un ticker
curl http://localhost:8007/rvol/AAPL

# Obtener RVOL de múltiples tickers
curl -X POST http://localhost:8007/rvol/batch \
  -H "Content-Type: application/json" \
  -d '["AAPL", "TSLA", "NVDA"]'

# Ver estadísticas del calculador
curl http://localhost:8007/stats
```

## 🛠️ Desarrollo

### Estructura del Proyecto

```
tradeul-scanner/
├── docker-compose.yml
├── .env
├── services/              # Microservicios
│   ├── orchestrator/
│   ├── market_session/
│   ├── data_ingest/
│   ├── historical/
│   ├── scanner/
│   ├── polygon_ws/
│   ├── analytics/
│   ├── api_gateway/
│   └── admin_panel/
├── shared/                # Código compartido
│   ├── models/           # Pydantic models
│   ├── enums/
│   ├── utils/
│   └── config/
├── scripts/              # Scripts de utilidad
└── tests/
```

### Ejecutar tests

```bash
pytest tests/
pytest tests/unit/
pytest tests/integration/
```

### Logs

```bash
# Ver logs de un servicio específico
docker-compose logs -f scanner

# Ver logs de todos los servicios
docker-compose logs -f

# Logs en formato JSON en Redis
redis-cli XREAD STREAMS logs:scanner 0
```

## 📈 Monitoreo

### Métricas disponibles

- Prometheus metrics en cada servicio: `http://localhost:800X/metrics`
- Redis INFO: `docker-compose exec redis redis-cli INFO`
- TimescaleDB stats: Ver en pgAdmin o via SQL

### Health Checks

```bash
# Verificar estado de todos los servicios
curl http://localhost:8000/health

# Verificar servicio específico
curl http://localhost:8005/health
```

## 🔒 Seguridad

- API Keys para servicios externos (Polygon, FMP)
- JWT para autenticación de usuarios
- Rate limiting en API Gateway
- Admin Panel protegido con API Key

## 🎯 Casos de Uso

### 1. Encontrar acciones con alto RVOL

Configurar filtro: `rvol > 2.0` en horario de mercado

### 2. Detectar breakouts pre-market

Monitorear durante PRE_MARKET con filtros de volumen

### 3. Análisis de momentum

Combinar RVOL + % cambio + volumen

### 4. Backtest de estrategias

Usar histórico de scans en TimescaleDB

## 📝 Notas Importantes

### Límites de API

- **Polygon Advanced Plan**: ~100 req/seg para snapshots
- **WebSocket**: hasta 1000 suscripciones simultáneas
- Implementamos rate limiting automático

### Memoria

- Redis configurado con 2GB max y política LRU
- Scanner Service puede usar hasta 4GB
- Analytics Service hasta 3GB

### Limpieza automática

- Buffers de RVOL se limpian en cambio de día
- Redis keys temporales con TTL de 24h
- TimescaleDB comprime datos >7 días

## 🤝 Contribuir

1. Fork el repositorio
2. Crea una rama: `git checkout -b feature/nueva-funcionalidad`
3. Commit: `git commit -am 'Agregar nueva funcionalidad'`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Pull Request

## 📄 Licencia

Propietario - Tradeul © 2025

## 🆘 Soporte

- Email: support@tradeul.com
- Documentación: https://docs.tradeul.com
- Issues: GitHub Issues

---

**Desarrollado con ❤️ para traders profesionales**
