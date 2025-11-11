#!/bin/bash
# Start Data Maintenance Service

echo "🔧 Building Data Maintenance Service..."
docker compose build data_maintenance

echo "🚀 Starting Data Maintenance Service..."
docker compose up -d data_maintenance

echo ""
echo "✅ Data Maintenance Service started!"
echo ""
echo "📊 View logs:"
echo "   docker logs -f tradeul_data_maintenance"
echo ""
echo "🔍 Check status:"
echo "   curl http://localhost:8008/health"
echo "   curl http://localhost:8008/status"
echo ""
echo "⚡ Trigger manual maintenance:"
echo "   curl -X POST http://localhost:8008/trigger"
echo ""
