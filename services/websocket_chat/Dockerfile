FROM node:20-slim

WORKDIR /app

# Copy package files
COPY services/websocket_chat/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source
COPY services/websocket_chat/src ./src

# Expose chat WS port (different from scanner 9000)
EXPOSE 9001

# Run
CMD ["node", "src/index.js"]

