FROM python:3.11-slim

WORKDIR /app

# Copy shared code first
COPY shared/ /app/shared/

# Copy service requirements and install
COPY services/api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/api_gateway/ /app/

# Expose port
EXPOSE 8000

# Run the service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

