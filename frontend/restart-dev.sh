#!/bin/bash

echo "🛑 Deteniendo servidores..."
pkill -9 -f "next dev" 2>/dev/null
pkill -9 -f "next-server" 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
lsof -ti:3001 | xargs kill -9 2>/dev/null
sleep 2

echo "🧹 Limpiando cache..."
rm -rf .next
rm -rf node_modules/.cache
echo "✅ Cache limpiado"

echo "🚀 Iniciando servidor..."
NODE_OPTIONS="--max-old-space-size=4096" npm run dev

