FROM node:22-slim

WORKDIR /app

COPY services/chart_aggregator/package*.json ./
RUN npm install --production

COPY services/chart_aggregator/ ./

CMD ["node", "src/index.js"]
