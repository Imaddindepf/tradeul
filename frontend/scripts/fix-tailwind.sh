#!/bin/bash

# ========================================
# Script: Fix Tailwind & Deep Clean
# Uso: ./scripts/fix-tailwind.sh
# ========================================

set -e

echo "╔═══════════════════════════════════════╗"
echo "║  🔧 FIX TAILWIND & DEEP CLEAN        ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# 1. Cerrar todos los procesos Node
echo "1/7 🛑 Cerrando procesos Node.js..."
killall -9 node 2>/dev/null || true
sleep 2
echo "    ✅ Procesos cerrados"

# 2. Liberar puertos
echo "2/7 🔓 Liberando puertos 3000-3003..."
lsof -ti:3000,3001,3002,3003 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1
echo "    ✅ Puertos liberados"

# 3. Borrar .next
echo "3/7 🗑️  Eliminando .next..."
rm -rf .next
echo "    ✅ .next eliminado"

# 4. Borrar package-lock.json
echo "4/7 🗑️  Eliminando package-lock.json..."
rm -rf package-lock.json
echo "    ✅ package-lock.json eliminado"

# 5. Limpiar caches de node_modules
echo "5/7 🧹 Limpiando caches de node_modules..."
rm -rf node_modules/.cache 2>/dev/null || true
echo "    ✅ Cache de node_modules limpiado"

# 6. Limpiar cache de npm
echo "6/7 🧹 Limpiando cache de npm..."
npm cache clean --force > /dev/null 2>&1
echo "    ✅ Cache de npm limpiado"

# 7. Reinstalar dependencias
echo "7/7 📦 Reinstalando dependencias..."
npm install > /dev/null 2>&1
echo "    ✅ Dependencias reinstaladas"

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║  ✅ LIMPIEZA COMPLETA EXITOSA         ║"
echo "╚═══════════════════════════════════════╝"
echo ""
echo "🚀 Para iniciar el servidor:"
echo "   npm run dev"
echo ""
echo "🌐 Luego navega a:"
echo "   http://localhost:3000"
echo ""
echo "💡 Recuerda hacer Hard Refresh en el navegador:"
echo "   Mac:     Cmd + Shift + R"
echo "   Windows: Ctrl + Shift + R"
echo ""

