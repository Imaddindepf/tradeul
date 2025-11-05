FROM python:3.11-slim

WORKDIR /app

# Copy shared code first
COPY shared/ /app/shared/

# Copy service requirements and install
COPY services/market_session/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/market_session/ /app/

# Expose port
EXPOSE 8002

# Run the service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

