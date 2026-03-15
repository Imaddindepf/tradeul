FROM python:3.11-slim
WORKDIR /app
COPY shared/ /app/shared/
COPY services/alert_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/alert_engine/ /app/
EXPOSE 8041
CMD ["python", "-m", "main"]
