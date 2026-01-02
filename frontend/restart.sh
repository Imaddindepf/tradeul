#!/bin/bash
# Restart frontend - mata proceso en puerto 3000 y reinicia

cd /opt/tradeul/frontend

# Matar cualquier proceso en puerto 3000
PID=$(lsof -t -i:3000 2>/dev/null)
if [ -n "$PID" ]; then
    echo "Matando proceso $PID en puerto 3000..."
    kill -9 $PID 2>/dev/null
    sleep 2
fi

# Verificar que el puerto está libre
if lsof -i:3000 >/dev/null 2>&1; then
    echo "ERROR: Puerto 3000 sigue ocupado"
    exit 1
fi

# Build si se pasa --build
if [ "$1" = "--build" ]; then
    echo "Building..."
    rm -rf .next
    npm run build
fi

# Iniciar
echo "Iniciando frontend..."
PORT=3000 npm run start &

sleep 8
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q "200"; then
    echo "✓ Frontend corriendo en puerto 3000"
else
    echo "✗ Error: Frontend no responde"
fi

