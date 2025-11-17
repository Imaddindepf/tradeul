#!/bin/bash

echo "🛑 Deteniendo todos los procesos de Next.js..."
pkill -9 -f "next dev" 2>/dev/null
pkill -9 -f "next-server" 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
lsof -ti:3001 | xargs kill -9 2>/dev/null
sleep 2

echo "🧹 Limpiando cache..."
rm -rf .next
rm -rf node_modules/.cache
rm -rf .swc
find . -name "*.log" -type f -delete 2>/dev/null
echo "✅ Cache completamente limpiado"

echo "🚀 Iniciando servidor con configuración optimizada..."
NODE_OPTIONS="--max-old-space-size=4096 --no-warnings" npm run dev

