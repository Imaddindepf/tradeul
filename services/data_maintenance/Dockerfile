FROM python:3.11-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Crear directorio para logs
RUN mkdir -p /var/log/tradeul && chmod 777 /var/log/tradeul

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar shared (dependencias comunes)
COPY shared/ /app/shared/

# Copiar scripts (reutilizar scripts existentes)
COPY scripts/ /app/scripts/

# Copiar código del servicio
COPY services/data_maintenance/ /app/

# Exponer puerto para health check
EXPOSE 8008

# Comando por defecto
CMD ["python", "-u", "main.py"]
