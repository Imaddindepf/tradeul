# SEC Filings Service 📊

Servicio de streaming y backfill de SEC EDGAR filings en tiempo real.

## 🎯 Características

### Real-Time (Stream API)
- ✅ WebSocket connection a SEC Stream API
- ✅ Recibe filings en tiempo real (< 1 segundo de latencia)
- ✅ Auto-reconexión automática
- ✅ Guarda automáticamente en PostgreSQL/TimescaleDB

### Histórico (Query API)
- ✅ Backfill de filings históricos
- ✅ Búsquedas por fecha, ticker, form type, items
- ✅ Paginación automática
- ✅ Rate limiting integrado

### REST API
- ✅ Endpoints para buscar y filtrar filings
- ✅ Búsqueda por ticker, CIK, form type, items
- ✅ Estadísticas y métricas
- ✅ Paginación

## 🚀 Quick Start

### 1. Configurar API Key

Obtén tu API key de [sec-api.io](https://sec-api.io) y agrégala al `.env`:

```bash
SEC_API_IO=tu_api_key_aqui
```

### 2. Levantar servicio

```bash
docker-compose up -d sec-filings
```

### 3. Verificar estado

```bash
curl http://localhost:8012/health
curl http://localhost:8012/status
```

## 📡 REST API Endpoints

### Health & Status

#### GET `/health`
Health check del servicio

```bash
curl http://localhost:8012/health
```

#### GET `/status`
Estado completo del servicio (DB, Stream, Backfill)

```bash
curl http://localhost:8012/status
```

#### GET `/stream/status`
Estado del Stream API (real-time)

```bash
curl http://localhost:8012/stream/status
```

#### GET `/backfill/status`
Estado del backfill histórico

```bash
curl http://localhost:8012/backfill/status
```

---

### Filings

#### GET `/api/v1/filings`
Buscar filings con filtros

**Query Parameters:**
- `ticker` - Símbolo del ticker (e.g., TSLA)
- `form_type` - Tipo de formulario (e.g., 8-K, 10-K, 10-Q, 4)
- `cik` - Central Index Key
- `date_from` - Fecha inicio (YYYY-MM-DD)
- `date_to` - Fecha fin (YYYY-MM-DD)
- `items` - Items separados por coma (e.g., "1.03,9.01")
- `page` - Número de página (default: 1)
- `page_size` - Tamaño de página (default: 50, max: 200)

**Ejemplos:**

```bash
# Todos los 8-K de Tesla
curl "http://localhost:8012/api/v1/filings?ticker=TSLA&form_type=8-K"

# 8-Ks con Item 1.03 (Bankruptcy) en 2024
curl "http://localhost:8012/api/v1/filings?form_type=8-K&items=1.03&date_from=2024-01-01&date_to=2024-12-31"

# Form 4 (Insider Trading) de los últimos 30 días
curl "http://localhost:8012/api/v1/filings?form_type=4&date_from=2024-11-01"

# Todos los filings de un CIK específico
curl "http://localhost:8012/api/v1/filings?cik=789019"
```

#### GET `/api/v1/filings/{accession_no}`
Obtener filing por accession number

```bash
curl "http://localhost:8012/api/v1/filings/0001628280-24-041816"
```

#### GET `/api/v1/filings/latest/{count}`
Obtener los últimos N filings

```bash
# Últimos 50 filings
curl "http://localhost:8012/api/v1/filings/latest/50"

# Últimos 200 filings (máximo)
curl "http://localhost:8012/api/v1/filings/latest/200"
```

---

### Backfill (Admin)

#### POST `/api/v1/backfill/recent`
Iniciar backfill de últimos N días

```bash
# Backfill de últimos 30 días
curl -X POST "http://localhost:8012/api/v1/backfill/recent?days=30"

# Backfill de último año
curl -X POST "http://localhost:8012/api/v1/backfill/recent?days=365"
```

#### POST `/api/v1/backfill/date-range`
Backfill para un rango de fechas específico

```bash
# Backfill de todos los filings entre 2023-01-01 y 2023-12-31
curl -X POST "http://localhost:8012/api/v1/backfill/date-range?start_date=2023-01-01&end_date=2023-12-31"

# Backfill solo de 8-K y 10-K en 2024
curl -X POST "http://localhost:8012/api/v1/backfill/date-range?start_date=2024-01-01&end_date=2024-12-31&form_types=8-K,10-K"
```

---

### Estadísticas

#### GET `/api/v1/stats`
Estadísticas generales de la base de datos

```bash
curl "http://localhost:8012/api/v1/stats"
```

**Response:**
```json
{
  "total_filings": 125000,
  "total_tickers": 5000,
  "latest_filing": "2024-11-23T18:30:00Z",
  "oldest_filing": "2024-01-01T00:00:00Z",
  "total_8k": 45000,
  "total_10k": 5000,
  "total_10q": 15000,
  "total_form4": 30000
}
```

#### GET `/api/v1/stats/by-ticker/{ticker}`
Estadísticas para un ticker específico

```bash
curl "http://localhost:8012/api/v1/stats/by-ticker/TSLA"
```

#### GET `/api/v1/stats/by-form-type/{form_type}`
Estadísticas para un form type específico

```bash
curl "http://localhost:8012/api/v1/stats/by-form-type/8-K"
```

## 🔧 Configuración

### Variables de Entorno

```bash
# SEC API
SEC_API_IO=your_api_key_here

# Database
POSTGRES_HOST=timescaledb
POSTGRES_PORT=5432
POSTGRES_USER=tradeul_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=tradeul

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# Service
SERVICE_PORT=8012
LOG_LEVEL=INFO

# Stream Settings
STREAM_ENABLED=true
STREAM_RECONNECT_DELAY=5  # segundos
STREAM_PING_TIMEOUT=30     # segundos

# Backfill Settings
BACKFILL_ENABLED=true
BACKFILL_BATCH_SIZE=50
BACKFILL_DAYS_BACK=30  # días hacia atrás en inicio
```

## 📊 Schema de Base de Datos

### Tabla `sec_filings`

```sql
CREATE TABLE sec_filings (
    id TEXT PRIMARY KEY,
    accession_no TEXT UNIQUE NOT NULL,
    form_type TEXT NOT NULL,
    filed_at TIMESTAMPTZ NOT NULL,
    ticker TEXT,
    cik TEXT NOT NULL,
    company_name TEXT,
    company_name_long TEXT,
    period_of_report DATE,
    description TEXT,
    items TEXT[],  -- Array de items (e.g., ["1.03", "9.01"])
    group_members TEXT[],
    link_to_filing_details TEXT,
    link_to_txt TEXT,
    link_to_html TEXT,
    link_to_xbrl TEXT,
    entities JSONB,
    document_format_files JSONB,
    data_files JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_sec_filings_ticker ON sec_filings(ticker);
CREATE INDEX idx_sec_filings_form_type ON sec_filings(form_type);
CREATE INDEX idx_sec_filings_filed_at ON sec_filings(filed_at DESC);
CREATE INDEX idx_sec_filings_cik ON sec_filings(cik);
CREATE INDEX idx_sec_filings_items ON sec_filings USING GIN(items);
```

## 📚 Casos de Uso

### 1. Monitor de Bancarrotas (8-K Item 1.03)

```bash
curl "http://localhost:8012/api/v1/filings?form_type=8-K&items=1.03&date_from=2024-01-01"
```

### 2. Insider Trading (Form 4)

```bash
# Form 4 de los últimos 7 días
curl "http://localhost:8012/api/v1/filings?form_type=4&date_from=$(date -d '7 days ago' +%Y-%m-%d)"
```

### 3. IPOs y Ofertas (S-1, 424B4)

```bash
curl "http://localhost:8012/api/v1/filings?form_type=S-1&date_from=2024-01-01"
```

### 4. Institutional Holdings (13F)

```bash
curl "http://localhost:8012/api/v1/filings?form_type=13F-HR&date_from=2024-10-01"
```

### 5. Activist Investors (13D/13G)

```bash
curl "http://localhost:8012/api/v1/filings?form_type=SC 13D&date_from=2024-01-01"
```

## 🔗 Integración con Frontend

### Ejemplo: React Component

```typescript
import { useState, useEffect } from 'react';

interface Filing {
  accessionNo: string;
  formType: string;
  filedAt: string;
  ticker?: string;
  companyName?: string;
  linkToFilingDetails?: string;
}

export function LatestFilings() {
  const [filings, setFilings] = useState<Filing[]>([]);
  
  useEffect(() => {
    fetch('http://localhost:8012/api/v1/filings/latest/50')
      .then(res => res.json())
      .then(data => setFilings(data.filings));
  }, []);
  
  return (
    <div>
      <h2>Latest SEC Filings</h2>
      {filings.map(filing => (
        <div key={filing.accessionNo}>
          <strong>{filing.ticker || filing.companyName}</strong>
          {' - '}
          {filing.formType}
          {' - '}
          {new Date(filing.filedAt).toLocaleString()}
          {filing.linkToFilingDetails && (
            <a href={filing.linkToFilingDetails} target="_blank">View</a>
          )}
        </div>
      ))}
    </div>
  );
}
```

## 🐛 Troubleshooting

### Stream no conecta

1. Verificar API key: `echo $SEC_API_KEY`
2. Verificar logs: `docker logs tradeul_sec_filings`
3. Verificar estado: `curl http://localhost:8012/stream/status`

### Backfill muy lento

- Ajustar `BACKFILL_BATCH_SIZE` (default: 50)
- Dividir en rangos más pequeños
- Filtrar por form types específicos

### No se guardan filings

1. Verificar conexión a BD: `docker logs tradeul_timescale`
2. Verificar tabla existe: `docker exec tradeul_timescale psql -U tradeul_user -d tradeul -c "\d sec_filings"`
3. Verificar logs del servicio: `docker logs -f tradeul_sec_filings`

## 📖 Referencias

- [SEC API Documentation](https://sec-api.io/docs)
- [SEC EDGAR](https://www.sec.gov/edgar)
- [Form Types Reference](https://www.sec.gov/forms)

## 🚀 Performance

- **Real-time latency**: < 1 segundo
- **Query performance**: 10-50ms (con índices)
- **Backfill rate**: ~1,000 filings/minuto
- **Storage**: ~1KB por filing (metadata)

## 📝 License

Interno - Tradeul

