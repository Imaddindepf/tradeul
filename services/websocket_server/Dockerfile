FROM node:22-slim

# Instalar git y build tools para instalar uWebSockets.js desde GitHub
RUN apt-get update && apt-get install -y git python3 make g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar archivos de configuración
COPY services/websocket_server/package*.json ./

# Instalar dependencias
RUN npm install

# Copiar código fuente
COPY services/websocket_server/ ./

# Exponer puerto
EXPOSE 9000

# Ejecutar servidor
CMD ["node", "src/index.js"]

