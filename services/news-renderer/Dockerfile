# Imagen oficial de Playwright: trae Chromium y sus dependencias de sistema
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8074

HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8074/health')" || exit 1

CMD ["python", "main.py"]
