FROM python:3.12-slim

WORKDIR /app

# Código compartido (contratos de streams, utils)
COPY shared/ /app/shared/

COPY services/bar_builder/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/bar_builder/ /app/

EXPOSE 8050

CMD ["python", "main.py"]
