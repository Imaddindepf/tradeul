FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY services/financials/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/financials/ /app/

# Set Python path to include app root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default port
ENV FINANCIALS_PORT=8020
EXPOSE 8020

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8020/health')" || exit 1

CMD ["python", "main.py"]
