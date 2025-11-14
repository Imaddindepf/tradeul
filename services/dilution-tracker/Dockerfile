FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules
COPY shared/ /app/shared/

# Copy service code
COPY services/dilution-tracker/ /app/services/dilution-tracker/

# Set working directory to service
WORKDIR /app/services/dilution-tracker

# Expose port
EXPOSE 8000

# Run service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

