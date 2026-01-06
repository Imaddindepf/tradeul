FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY services/ai-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared /app/shared

# Copy service code
COPY services/ai-agent /app/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8030

# Run the service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]

