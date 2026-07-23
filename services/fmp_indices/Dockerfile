FROM python:3.11-slim

WORKDIR /app

# Copy shared code first
COPY shared/ /app/shared/

# Copy service requirements and install
COPY services/fmp_indices/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/fmp_indices/ /app/

EXPOSE 8030

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]
