FROM python:3.11-slim

WORKDIR /app

# Copy shared code first
COPY shared/ /app/shared/

# Copy service requirements and install
COPY services/event_detector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/event_detector/ /app/

# Expose port (for health check endpoint if needed)
EXPOSE 8040

# Run the service
CMD ["python", "-m", "main"]
