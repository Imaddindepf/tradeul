# 🔍 Búsqueda de Tickers en Tiempo Real - Arquitectura Profesional

## 📊 Cómo lo Hacen los Profesionales

Las aplicaciones financieras profesionales (Bloomberg Terminal, Robinhood, Webull, TradingView) usan estas técnicas para búsquedas ultrarrápidas:

### 1. **Base de Datos con Índices Optimizados**

```sql
-- Índice B-tree para búsquedas exactas y por prefijo
CREATE INDEX idx_symbol_btree ON tickers (symbol);

-- Índice GIN con pg_trgm para full-text search
CREATE EXTENSION pg_trgm;
CREATE INDEX idx_company_name_gin ON tickers USING GIN (company_name gin_trgm_ops);

-- Índice compuesto para filtros comunes
CREATE INDEX idx_active_symbol ON tickers (is_active, symbol) WHERE is_active = true;
```

**Performance:**
- **Sin índices**: 500-2000ms para 100K tickers
- **Con índices**: 10-50ms para 100K tickers (50x más rápido)

### 2. **Caché en Memoria (Redis)**

```typescript
// Frontend: Caché local (Map o LRU)
const searchCache = new Map<string, TickerResult[]>();

// Backend: Redis con TTL
await redis.set(`search:${query}`, results, 'EX', 300); // 5 minutos
```

**Beneficios:**
- Queries repetidas: **0-5ms** (hit desde caché)
- Reduce carga en PostgreSQL
- TTL corto (5min) porque los tickers no cambian frecuentemente

### 3. **Debouncing en Frontend**

```typescript
// Esperar 150-300ms después del último keystroke
useEffect(() => {
    const timer = setTimeout(() => {
        fetchResults(value);
    }, 150); // 150ms = sweet spot para UX
    return () => clearTimeout(timer);
}, [value]);
```

**Evita:**
- Escribir "AAPL" genera 1 query en vez de 4
- Saturar el servidor con queries inútiles

### 4. **Request Cancellation (AbortController)**

```typescript
const abortControllerRef = useRef<AbortController | null>(null);

// Cancelar request anterior si el usuario sigue escribiendo
if (abortControllerRef.current) {
    abortControllerRef.current.abort();
}

abortControllerRef.current = new AbortController();
fetch(url, { signal: abortControllerRef.current.signal });
```

**Evita:**
- Race conditions (request antiguo llega después que el nuevo)
- Desperdicio de bandwidth

### 5. **Query Optimization**

```sql
-- ❌ MAL: Sin índice, escanea toda la tabla
SELECT * FROM tickers WHERE company_name LIKE '%Apple%';

-- ✅ BIEN: Usa índice GIN con pg_trgm
SELECT symbol, company_name, exchange 
FROM tickers 
WHERE 
    is_actively_trading = true 
    AND (
        symbol ILIKE $1 || '%'  -- Prefijo (usa índice B-tree)
        OR company_name ILIKE '%' || $1 || '%'  -- Contains (usa índice GIN)
    )
ORDER BY 
    CASE 
        WHEN symbol = $1 THEN 0           -- Exacto (prioridad máxima)
        WHEN symbol ILIKE $1 || '%' THEN 1  -- Prefijo en symbol
        WHEN company_name ILIKE $1 || '%' THEN 2  -- Prefijo en nombre
        ELSE 3
    END,
    symbol ASC
LIMIT 10;
```

### 6. **Priorización de Resultados**

```
Orden de relevancia:
1. Match exacto (AAPL → AAPL)
2. Prefijo en symbol (AA → AAPL, AABA, AAL)
3. Prefijo en company_name (App → Apple Inc, AppLovin)
4. Contains en cualquier parte (ple → Apple, Maple)
```

### 7. **Límite de Resultados**

```typescript
// Mostrar solo 10-15 resultados
// Más de 20 empeora UX y performance
const MAX_RESULTS = 10;
```

### 8. **Fuzzy Matching (Avanzado)**

```sql
-- pg_trgm permite búsquedas fuzzy
SELECT symbol, company_name, similarity(symbol, 'APPL') AS score
FROM tickers
WHERE similarity(symbol, 'APPL') > 0.3
ORDER BY score DESC
LIMIT 10;

-- APPL → AAPL (typo común)
```

---

## 🚀 Implementación en Tradeul

### Frontend: `/frontend/components/common/TickerSearch.tsx`

```typescript
✅ Debouncing: 150ms
✅ Request cancellation: AbortController
✅ Error handling: Visual feedback
✅ Loading state: Spinner visible
✅ Empty state: "No se encontraron tickers"
✅ Keyboard navigation: Arrow keys + Enter
```

### Backend: `/services/ticker-metadata-service/api/metadata_router.py`

```python
✅ Query optimizado con CASE para priorización
✅ Índices: B-tree (symbol) + GIN (company_name)
✅ Caché Redis: TTL 5 minutos
✅ Logging de queries lentas (> 100ms)
✅ Límite configurable (default: 10, max: 50)
```

### Base de Datos: PostgreSQL + TimescaleDB

```sql
✅ Extensión pg_trgm habilitada
✅ Índice B-tree en symbol
✅ Índice GIN en company_name
✅ Índice compuesto en (is_actively_trading, symbol)
✅ ANALYZE ejecutado para estadísticas
```

---

## 📈 Benchmarks Esperados

| Query Type | Sin Índices | Con Índices | Con Caché Redis |
|-----------|-------------|-------------|-----------------|
| Exacto (AAPL) | 200ms | 5ms | 1ms |
| Prefijo (AA) | 800ms | 15ms | 2ms |
| Contains (Apple) | 1500ms | 40ms | 3ms |
| Fuzzy (APPL) | 2000ms | 80ms | 5ms |

**Target:** < 50ms para el 95% de queries

---

## 🛠️ Setup

### 1. Crear Índices en Base de Datos

```bash
# Método 1: Docker Compose
docker-compose exec timescaledb psql -U tradeul_user -d tradeul < scripts/add_ticker_search_indexes.sql

# Método 2: Conectar manualmente
psql -h 157.180.45.153 -p 5432 -U tradeul_user -d tradeul < scripts/add_ticker_search_indexes.sql
```

### 2. Verificar Índices

```sql
-- Ver índices creados
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'tickers_unified';

-- Test de performance
EXPLAIN ANALYZE 
SELECT symbol, company_name, exchange 
FROM tickers_unified 
WHERE symbol ILIKE 'AA%' AND is_actively_trading = true 
LIMIT 10;
```

**Resultado esperado:**
```
Index Scan using idx_tickers_symbol_btree on tickers_unified
Planning Time: 0.123 ms
Execution Time: 8.456 ms  ← < 50ms ✅
```

### 3. Restart Servicios

```bash
docker-compose restart ticker_metadata
```

### 4. Test en Frontend

```bash
# Abrir http://localhost:3000/sec-filings
# Escribir "AA" en el buscador
# Debería mostrar sugerencias en < 200ms (150ms debounce + 50ms query)
```

---

## 🔍 Debugging

### Problema: "Se queda cargando"

**Causas posibles:**

1. **Servicio caído**
   ```bash
   docker-compose logs ticker_metadata | tail -50
   ```

2. **BD sin índices**
   ```sql
   \d+ tickers_unified  -- Ver índices
   ```

3. **Query lenta**
   ```sql
   SELECT * FROM pg_stat_statements 
   WHERE query LIKE '%tickers_unified%' 
   ORDER BY mean_exec_time DESC;
   ```

4. **Redis caído** (opcional, no crítico)
   ```bash
   docker-compose logs redis | tail -20
   ```

### Problema: "No muestra resultados"

**Verificar:**

1. **Hay datos en la tabla**
   ```sql
   SELECT COUNT(*) FROM tickers_unified WHERE is_actively_trading = true;
   ```

2. **Query funciona manualmente**
   ```sql
   SELECT symbol, company_name 
   FROM tickers_unified 
   WHERE symbol ILIKE 'AA%' 
   LIMIT 5;
   ```

3. **Respuesta del endpoint**
   ```bash
   curl "http://157.180.45.153:8010/api/v1/metadata/search?q=AA&limit=10"
   ```

### Logs útiles

```bash
# Ver logs de búsquedas lentas
docker-compose logs ticker_metadata | grep "slow_ticker_search"

# Ver errores de búsqueda
docker-compose logs ticker_metadata | grep "search_error"
```

---

## 📚 Referencias

- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [pg_trgm Extension](https://www.postgresql.org/docs/current/pgtrgm.html)
- [React Query Debouncing](https://tkdodo.eu/blog/react-query-and-type-script#type-safe-debouncing)
- [Bloomberg Terminal Search](https://www.bloomberg.com/professional/solution/bloomberg-terminal/)

---

## ✅ Checklist

- [x] Índices creados en PostgreSQL
- [x] Extensión pg_trgm habilitada
- [x] Query optimizado con CASE para priorización
- [x] Debouncing en frontend (150ms)
- [x] Request cancellation (AbortController)
- [x] Error handling visual
- [x] Loading state visible
- [x] Empty state para "sin resultados"
- [x] Caché Redis (opcional pero recomendado)
- [x] Logging de queries lentas
- [ ] Monitoreo de performance (Grafana/Prometheus)
- [ ] Fuzzy matching con similarity() (opcional)

---

**¡Ahora tu búsqueda de tickers es tan rápida como Bloomberg Terminal!** 🚀

