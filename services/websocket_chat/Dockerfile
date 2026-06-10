FROM node:20-slim

WORKDIR /app

# Copy package files
COPY services/websocket_chat/package*.json ./

# Install dependencies
RUN npm ci --omit=dev

# Copy source
COPY services/websocket_chat/src ./src

# Expose chat WS port (different from scanner 9000)
EXPOSE 9001

# Run. --max-old-space-size=768: sin el flag, V8 limita el heap a ~512MB en
# un contenedor de 1GB; 768MB deja ~250MB para buffers nativos y overhead.
CMD ["node", "--max-old-space-size=768", "src/index.js"]

