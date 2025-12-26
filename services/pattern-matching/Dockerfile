# Pattern Matching Service - Dockerfile
# FAISS-based pattern similarity search for financial time series

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY services/pattern-matching/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/pattern-matching/*.py .

# Copy shared modules
COPY shared/ /app/shared/

# Create data directories
RUN mkdir -p /app/data/minute_aggs /app/indexes

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8025

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8025/health || exit 1

# Run the service
CMD ["python", "main.py"]

