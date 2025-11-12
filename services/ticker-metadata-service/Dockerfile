FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/

COPY services/ticker-metadata-service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/ticker-metadata-service/ /app/

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8010/health', timeout=5.0)"

CMD ["python", "main.py"]

