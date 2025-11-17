# SEC Dilution Profile System

Sistema completo para análisis de dilución de acciones basado en datos extraídos de SEC EDGAR filings usando scraping híbrido + Grok AI.

## 🎯 Características

- ✅ **Scraping automatizado** de SEC EDGAR (10-K, 10-Q, S-3, 8-K, 424B5)
- ✅ **Análisis con Grok AI** para extraer datos complejos de texto no estructurado
- ✅ **Caché multi-nivel** (Redis + PostgreSQL) para respuestas instantáneas
- ✅ **Datos reales** extraídos de filings oficiales de la SEC
- ✅ **API REST completa** con endpoints especializados

## 📊 Datos Extraídos

### 1. Warrants
- Fecha de emisión
- Warrants outstanding
- Precio de ejercicio
- Fecha de expiración
- Shares potenciales si todos se ejercen

### 2. ATM Offerings (At-The-Market)
- Capacidad total en dólares
- Capacidad restante
- Placement agent
- Fecha del filing
- Shares potenciales al precio actual

### 3. Shelf Registrations (S-3, S-1)
- Capacidad total del shelf
- Capacidad restante
- Es baby shelf (<$75M)
- Fecha de registro
- Fecha de expiración (típicamente 3 años)

### 4. Completed Offerings (Histórico)
- Tipo de offering (Direct, PIPE, Registered Direct)
- Shares emitidas
- Precio por share
- Monto total recaudado
- Fecha del offering

## 🏗️ Arquitectura

```
┌─────────────┐
│   Usuario   │
└──────┬──────┘
       │ GET /api/sec-dilution/{ticker}/profile
       ▼
┌─────────────────────────────────────────┐
│         API Gateway / Router            │
└──────┬──────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────┐
│      SECDilutionService                │
│                                         │
│  ┌─────────────────────────────────┐  │
│  │  1. Check Redis Cache (L1)      │  │
│  │     ↓ Miss                       │  │
│  │  2. Check PostgreSQL (L2)       │  │
│  │     ↓ Miss                       │  │
│  │  3. Scrape SEC EDGAR            │  │
│  │     ↓                            │  │
│  │  4. Extract with Grok API       │  │
│  │     ↓                            │  │
│  │  5. Save to PostgreSQL          │  │
│  │     ↓                            │  │
│  │  6. Cache in Redis (TTL: 24h)   │  │
│  │     ↓                            │  │
│  │  7. Return to user              │  │
│  └─────────────────────────────────┘  │
└────────────────────────────────────────┘
```

## 🚀 Endpoints API

### 1. Obtener Perfil Completo
```http
GET /api/sec-dilution/{ticker}/profile?force_refresh=false
```

**Response:**
```json
{
  "profile": {
    "ticker": "SOUN",
    "company_name": "SoundHound AI Inc",
    "cik": "0001840005",
    "current_price": 5.25,
    "shares_outstanding": 350000000,
    "warrants": [...],
    "atm_offerings": [...],
    "shelf_registrations": [...],
    "completed_offerings": [...]
  },
  "dilution_analysis": {
    "total_potential_dilution_pct": 85.5,
    "total_potential_new_shares": 299285714,
    "warrant_shares": 15000000,
    "atm_potential_shares": 14285714,
    "shelf_potential_shares": 270000000,
    "assumptions": [...]
  },
  "cached": true,
  "cache_age_seconds": 3600
}
```

### 2. Solo Warrants
```http
GET /api/sec-dilution/{ticker}/warrants
```

### 3. Solo ATM Offerings
```http
GET /api/sec-dilution/{ticker}/atm-offerings
```

### 4. Solo Shelf Registrations
```http
GET /api/sec-dilution/{ticker}/shelf-registrations
```

### 5. Solo Completed Offerings
```http
GET /api/sec-dilution/{ticker}/completed-offerings
```

### 6. Solo Análisis de Dilución
```http
GET /api/sec-dilution/{ticker}/dilution-analysis
```

### 7. Refresh (Force Re-scraping)
```http
POST /api/sec-dilution/{ticker}/refresh
```

## ⚡ Performance

| Escenario | Latencia | Origen |
|-----------|----------|--------|
| Cache hit (Redis) | <100ms | Redis L1 |
| Cache hit (PostgreSQL) | <200ms | PostgreSQL L2 |
| Cache miss (First request) | 10-60s | SEC Scraping + Grok API |

## 🗄️ Schema de Base de Datos

```sql
-- Tabla principal
sec_dilution_profiles
  - ticker (PK)
  - cik
  - company_name
  - shares_outstanding
  - current_price
  - last_scraped_at
  - source_filings (JSONB)

-- Warrants
sec_warrants
  - ticker (FK)
  - issue_date
  - outstanding
  - exercise_price
  - expiration_date
  - potential_new_shares

-- ATM Offerings
sec_atm_offerings
  - ticker (FK)
  - total_capacity
  - remaining_capacity
  - placement_agent
  - filing_date

-- Shelf Registrations
sec_shelf_registrations
  - ticker (FK)
  - total_capacity
  - remaining_capacity
  - is_baby_shelf
  - registration_statement (S-3, S-1)
  - expiration_date

-- Completed Offerings
sec_completed_offerings
  - ticker (FK)
  - offering_type
  - shares_issued
  - price_per_share
  - amount_raised
  - offering_date
```

## 🔧 Instalación y Setup

### 1. Migración de Base de Datos
```bash
# Ejecutar script de migración
psql -h timescaledb -U tradeul_user -d tradeul -f scripts/init_sec_dilution_profiles.sql
```

### 2. Configurar GROK_API_KEY
Agregar al `.env`:
```env
GROK_API_KEY=your_grok_api_key_here
```

### 3. Rebuild del servicio
```bash
docker-compose up -d --build dilution-tracker
```

## 📝 Uso desde Frontend

### Ejemplo React Component

```typescript
import { useQuery } from '@tanstack/react-query';

interface DilutionProfile {
  profile: {
    ticker: string;
    company_name: string;
    warrants: Warrant[];
    atm_offerings: ATMOffering[];
    shelf_registrations: ShelfRegistration[];
    completed_offerings: CompletedOffering[];
  };
  dilution_analysis: {
    total_potential_dilution_pct: number;
    warrant_shares: number;
    atm_potential_shares: number;
    shelf_potential_shares: number;
  };
}

export function DilutionProfile({ ticker }: { ticker: string }) {
  const { data, isLoading } = useQuery<DilutionProfile>({
    queryKey: ['sec-dilution', ticker],
    queryFn: async () => {
      const res = await fetch(`/api/sec-dilution/${ticker}/profile`);
      return res.json();
    },
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      {/* Summary Card */}
      <DilutionSummaryCard analysis={data.dilution_analysis} />
      
      {/* Warrants Card */}
      <WarrantsCard warrants={data.profile.warrants} />
      
      {/* ATM Offerings Card */}
      <ATMCard offerings={data.profile.atm_offerings} />
      
      {/* Shelf Registrations Card */}
      <ShelfCard shelves={data.profile.shelf_registrations} />
      
      {/* Completed Offerings Table */}
      <CompletedOfferingsTable offerings={data.profile.completed_offerings} />
    </div>
  );
}
```

## 🔍 Ejemplos de Uso

### Caso 1: Usuario consulta SOUN por primera vez
```
1. Request: GET /api/sec-dilution/SOUN/profile
2. Cache miss (no existe en Redis ni PostgreSQL)
3. Sistema hace scraping de SEC EDGAR
4. Extrae datos con Grok API (15-30 segundos)
5. Guarda en PostgreSQL
6. Guarda en Redis (TTL: 24h)
7. Retorna profile completo
8. Latencia total: ~25 segundos
```

### Caso 2: Otro usuario consulta SOUN 10 minutos después
```
1. Request: GET /api/sec-dilution/SOUN/profile
2. Cache hit en Redis
3. Retorna profile inmediatamente
4. Latencia total: <100ms
```

### Caso 3: Usuario quiere datos frescos después de nuevo filing
```
1. Request: POST /api/sec-dilution/SOUN/refresh
2. Invalida caché Redis
3. Re-scraping forzado de SEC
4. Re-análisis con Grok
5. Actualiza PostgreSQL y Redis
6. Retorna nuevo profile
7. Latencia: ~25 segundos
```

## 🎨 UI/UX Recomendado

### Cards Layout
```
┌─────────────────────────────────────────┐
│  💰 Dilución Potencial Total: 85.5%    │
│  Based on all warrants + ATM + shelf   │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  📜 Warrants                            │
│  ┌───────────────────────────────────┐ │
│  │ • 15M warrants @ $11.50           │ │
│  │   Expires: 2028-05-15             │ │
│  │   Potential Dilution: 4.3%        │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  🏦 ATM Offerings                       │
│  ┌───────────────────────────────────┐ │
│  │ • $75M remaining capacity         │ │
│  │   Agent: B. Riley Securities      │ │
│  │   Potential shares: ~14.3M        │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  📋 Shelf Registrations                 │
│  ┌───────────────────────────────────┐ │
│  │ • S-3: $150M remaining            │ │
│  │   Filed: 2023-08-10               │ │
│  │   Expires: 2026-08-10             │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  ✅ Completed Offerings (Last 2 years)  │
│  ┌───────────────────────────────────┐ │
│  │ Date       | Type  | Shares | $   │ │
│  │ 2024-09-15 | RDO   | 5M     | 17.5M │
│  │ 2024-03-20 | PIPE  | 3M     | 12M  │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

## 🔐 Consideraciones de Seguridad

- ✅ Rate limiting en endpoints (evitar scraping masivo)
- ✅ User-Agent correcto para SEC EDGAR (compliance)
- ✅ Manejo de errores robusto
- ✅ Validación de datos extraídos por Grok

## 📈 Monitoreo

### Métricas Clave
- Cache hit rate (target: >90%)
- Scraping success rate (target: >95%)
- Grok API latency
- Average response time
- Error rate por ticker

### Logs Importantes
```python
logger.info("dilution_profile_from_redis")  # Cache hit
logger.info("dilution_profile_scraping_required")  # Cache miss
logger.error("grok_extraction_failed")  # Grok error
logger.info("sec_scrape_completed")  # Success
```

## 🐛 Troubleshooting

### Problema: Grok API falla
**Solución:** Verificar GROK_API_KEY en .env

### Problema: No encuentra CIK para ticker
**Solución:** Verificar que ticker existe en ticker_metadata o SEC EDGAR

### Problema: Cache nunca expira
**Solución:** Usar endpoint `/refresh` para forzar actualización

### Problema: Datos vacíos
**Solución:** No todos los tickers tienen warrants/ATM/shelf. Esto es normal.

## 💡 Próximas Mejoras

- [ ] Pre-warming automático de tickers populares
- [ ] Alertas cuando se detectan nuevos filings SEC
- [ ] Historical tracking de cambios en dilution profile
- [ ] Predicciones ML de dilución futura
- [ ] Integración con alertas de usuario

## 📚 Referencias

- [SEC EDGAR API](https://www.sec.gov/edgar/sec-api-documentation)
- [Grok API Docs](https://docs.x.ai/)
- [Form Types Guide](https://www.sec.gov/forms)

---

**Autor:** Tradeul Team  
**Última actualización:** 2024-11-16

