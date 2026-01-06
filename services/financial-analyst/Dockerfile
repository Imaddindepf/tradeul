FROM python:3.11-slim

WORKDIR /app

COPY services/financial-analyst/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/financial-analyst/main.py .

EXPOSE 8099

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099"]
