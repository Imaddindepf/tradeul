# 🚀 Pattern Matching - Deployment en Servidor Dedicado

## Servidor Actual
- **IP**: 37.27.183.194
- **Specs**: 16 vCPU, 32GB RAM, 600GB SSD
- **Provider**: Hetzner
- **OS**: Ubuntu 24.04

---

## 📋 Deployment desde Cero (Guía Rápida)

### 1. Preparar el servidor

```bash
ssh root@<IP_SERVIDOR>

# Actualizar sistema
apt update && apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com | sh

# Instalar AWS CLI (para descargar flat files)
apt install -y awscli

# Crear directorio
mkdir -p /opt/pattern-matching
cd /opt/pattern-matching
```

### 2. Copiar código desde GitHub

```bash
# Opción A: Clonar repo completo
git clone git@github.com:Imaddindepf/tradeul.git /tmp/tradeul
cp -r /tmp/tradeul/services/pattern-matching/* /opt/pattern-matching/

# Opción B: Solo copiar los archivos necesarios via SCP
scp -r services/pattern-matching/*.py root@<IP>:/opt/pattern-matching/
```

### 3. Crear archivos de configuración

#### `.env`
```bash
cat > .env << 'EOF'
POLYGON_API_KEY=tu_api_key_aqui
POLYGON_S3_ACCESS_KEY=tu_s3_access_key
POLYGON_S3_SECRET_KEY=tu_s3_secret_key
REDIS_PASSWORD=tu_redis_password
EOF
```

#### `docker-compose.yml`
```yaml
services:
  pattern-matching:
    build: .
    container_name: pattern_matching
    restart: unless-stopped
    ports:
      - "8025:8025"
    volumes:
      - ./data:/app/indexes
      - ./data:/app/data
      - ./flats/minute_aggs:/app/data/minute_aggs:ro
    env_file:
      - .env
    environment:
      - PYTHONUNBUFFERED=1
    deploy:
      resources:
        limits:
          memory: 24G
        reservations:
          memory: 8G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8025/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
```

#### `Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
RUN mkdir -p /app/data/minute_aggs /app/indexes
ENV PYTHONUNBUFFERED=1
EXPOSE 8025
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 CMD curl -f http://localhost:8025/health || exit 1
CMD ["python", "main.py"]
```

### 4. Descargar Flat Files históricos (~30GB)

```bash
mkdir -p flats/minute_aggs
cd /opt/pattern-matching

source .env
export AWS_ACCESS_KEY_ID=$POLYGON_S3_ACCESS_KEY
export AWS_SECRET_ACCESS_KEY=$POLYGON_S3_SECRET_KEY

# Descargar todos los archivos (2019-2025) - TARDA ~2-4 HORAS
aws s3 sync s3://flatfiles/us_stocks_sip/minute_aggs_v1/ ./flats/minute_aggs/ \
    --endpoint-url https://files.polygon.io

# O descargar solo último año (más rápido)
for year in 2024 2025; do
    aws s3 sync s3://flatfiles/us_stocks_sip/minute_aggs_v1/$year/ ./flats/minute_aggs/ \
        --endpoint-url https://files.polygon.io
done
```

### 5. Construir índice FAISS (~4-8 horas)

```bash
# Iniciar contenedor sin índice primero
docker-compose up -d --build

# Construir índice (dentro del contenedor)
docker exec -it pattern_matching python3 << 'EOF'
from pattern_indexer import PatternIndexer
from data_processor import DataProcessor
from glob import glob

# Procesar todos los flat files
processor = DataProcessor()
files = sorted(glob('/app/data/minute_aggs/*.csv.gz'))
print(f'Procesando {len(files)} archivos...')

vectors, metadata = processor.process_multiple_files(files, max_workers=8)
print(f'Vectores extraídos: {len(vectors):,}')

# Construir índice FAISS
indexer = PatternIndexer()
indexer.build_index(vectors, metadata)
indexer.save('/app/indexes')
print('✅ Índice guardado')
EOF

# Verificar
curl http://localhost:8025/api/index/stats
```

### 6. Configurar actualización diaria (Cron)

```bash
# Crear script de actualización
cat > /opt/pattern-matching/daily_update.sh << 'SCRIPT'
#!/bin/bash
LOG_FILE="/opt/pattern-matching/logs/daily_update.log"
mkdir -p /opt/pattern-matching/logs

exec >> "$LOG_FILE" 2>&1
echo ""
echo "=========================================="
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting daily update"
echo "=========================================="

cd /opt/pattern-matching
source .env

export AWS_ACCESS_KEY_ID=$POLYGON_S3_ACCESS_KEY
export AWS_SECRET_ACCESS_KEY=$POLYGON_S3_SECRET_KEY

# Descargar últimos 7 días
echo "📥 Downloading recent flat files..."
for i in {1..7}; do
    DATE=$(date -d "$i days ago" '+%Y-%m-%d')
    FILE="flats/minute_aggs/${DATE}.csv.gz"
    
    if [ ! -f "$FILE" ]; then
        echo "   Downloading $DATE..."
        aws s3 cp "s3://flatfiles/us_stocks_sip/minute_aggs_v1/${DATE:0:4}/${DATE:5:2}/${DATE}.csv.gz" \
            "$FILE" --endpoint-url https://files.polygon.io 2>/dev/null
        [ -f "$FILE" ] && echo "   ✅ Downloaded: $DATE"
    fi
done

# Actualizar índice FAISS
echo ""
echo "🔄 Updating FAISS index..."
docker exec pattern_matching python3 -c "
from daily_updater import DailyUpdater
updater = DailyUpdater()
missing = updater.find_missing_dates()
if missing:
    print(f'Processing {len(missing)} missing dates')
    for date in missing:
        added = updater.update_date(date)
        print(f'  {date}: {added:,} patterns')
else:
    print('Index up to date')
"

# Recargar en memoria
echo ""
echo "🔃 Reloading index into memory..."
curl -s -X POST http://localhost:8025/api/index/reload

echo ""
echo "$(date '+%Y-%m-%d %H:%M:%S') - Complete"
SCRIPT

chmod +x /opt/pattern-matching/daily_update.sh

# Añadir al crontab (8 AM UTC = 3 AM EST, después de que Polygon suba datos)
(crontab -l 2>/dev/null | grep -v daily_update; echo "0 8 * * 1-5 /opt/pattern-matching/daily_update.sh") | crontab -
```

---

## 🔧 Comandos Útiles

### Ver estado del servicio
```bash
curl http://localhost:8025/health
curl http://localhost:8025/api/index/stats
```

### Ver fechas indexadas
```bash
curl http://localhost:8025/api/index/indexed-dates | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total: {len(d[\"dates\"])}, Última: {d[\"dates\"][-1]}')"
```

### Forzar actualización manual
```bash
/opt/pattern-matching/daily_update.sh
```

### Ver logs
```bash
# Logs del contenedor
docker logs pattern_matching --tail 100

# Logs del cron
tail -f /opt/pattern-matching/logs/daily_update.log
```

### Recargar índice en memoria
```bash
curl -X POST http://localhost:8025/api/index/reload
```

### Reiniciar servicio
```bash
cd /opt/pattern-matching
docker-compose restart
```

---

## 📊 Tamaños Esperados

| Componente | Tamaño |
|------------|--------|
| Flat files (6 años) | ~30 GB |
| Índice FAISS | ~6 GB |
| Metadata SQLite | ~20 GB |
| Trajectories | ~20 GB |
| **Total** | **~75 GB** |

---

## 🔗 Integración con Tradeul

El API Gateway (`services/api_gateway/main.py`) hace proxy a este servidor:

```python
PATTERN_MATCHING_URL = os.getenv("PATTERN_MATCHING_URL", "http://37.27.183.194:8025")
```

Endpoints disponibles via API Gateway:
- `GET /patterns/health`
- `GET /patterns/api/index/stats`
- `POST /patterns/api/search/{symbol}`

---

## ⚠️ Troubleshooting

### "Index not found"
El índice FAISS no existe. Construirlo con el paso 5.

### "Read-only file system" al descargar
El volumen `minute_aggs` está montado como `:ro`. Descargar desde el host, no desde el contenedor.

### Índice no se actualiza después del cron
El cron actualiza el disco pero no la memoria. Asegurar que el script llame a `/api/index/reload`.

### Out of memory al construir índice
Reducir `max_workers` en el procesamiento o aumentar RAM del servidor.

---

*Última actualización: 30 Dic 2025*

