FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar shared primero (para cachear layers)
COPY shared/ /app/shared/

# Copiar requirements
COPY services/ticker-metadata-service/requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del servicio
COPY services/ticker-metadata-service/ /app/

# Puerto
EXPOSE 8010

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8010/health', timeout=5.0)"

# Comando
CMD ["python", "main.py"]

