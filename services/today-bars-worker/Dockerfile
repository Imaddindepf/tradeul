FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    httpx \
    pandas \
    pyarrow \
    pytz \
    structlog \
    fastapi \
    uvicorn \
    pydantic

COPY worker.py .

EXPOSE 8035

CMD ["python", "worker.py"]

