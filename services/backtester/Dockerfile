FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -r backtester && chown -R backtester:backtester /app
USER backtester

EXPOSE 8060

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060", "--workers", "2"]
