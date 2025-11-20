#!/bin/bash
# =============================================================================
# TRADEUL - Cloud Server Setup Script
# =============================================================================
# Ejecutar en el servidor cloud después de SSH
# ssh root@157.180.45.153
# bash setup-cloud-server.sh
# =============================================================================

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     TRADEUL - Cloud Server Automated Setup                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 1. Actualizar sistema
echo "📦 [1/8] Actualizando sistema operativo..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y curl wget git vim htop net-tools

# 2. Instalar Docker
echo "🐳 [2/8] Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
    echo "✅ Docker instalado"
else
    echo "✅ Docker ya está instalado"
fi

# 3. Instalar Docker Compose
echo "🔧 [3/8] Instalando Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
    echo "✅ Docker Compose instalado"
else
    echo "✅ Docker Compose ya está instalado"
fi

# Verificar versiones
docker --version
docker compose version

# 4. Configurar firewall
echo "🔒 [4/8] Configurando firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp      # SSH
    ufw allow 80/tcp      # HTTP
    ufw allow 443/tcp     # HTTPS
    ufw allow 3000/tcp    # Next.js (temporal, luego usar Nginx)
    ufw --force enable
    echo "✅ Firewall configurado"
else
    echo "⚠️  UFW no disponible, configurar firewall manualmente"
fi

# 5. Crear directorio de trabajo
echo "📁 [5/8] Creando estructura de directorios..."
mkdir -p /opt/tradeul
cd /opt/tradeul

# 6. Clonar repositorio
echo "📥 [6/8] Clonando repositorio..."
if [ ! -d ".git" ]; then
    echo "Por favor, proporciona la URL del repositorio:"
    echo "Ejecuta manualmente:"
    echo "  cd /opt/tradeul"
    echo "  git clone https://github.com/tu-usuario/tradeul.git ."
    echo ""
    echo "O si ya tienes el código en tu Mac:"
    echo "  En tu Mac: scp -r /Users/imaddinamsif/Desktop/Tradeul-Amsif root@157.180.45.153:/opt/tradeul/"
else
    echo "✅ Repositorio ya clonado"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || echo "⚠️  Pull manual necesario"
fi

# 7. Crear archivo .env
echo "⚙️  [7/8] Configurando variables de entorno..."
cat > /opt/tradeul/.env << 'EOF'
# API KEYS (CAMBIAR ESTOS VALORES)
POLYGON_API_KEY=your_polygon_key_here
FMP_API_KEY=your_fmp_key_here
GROK_API_KEY=your_grok_key_here
SEC_API_IO=your_sec_api_key_here

# Database
POSTGRES_DB=tradeul
POSTGRES_USER=tradeul_user
POSTGRES_PASSWORD=tradeul_secure_prod_password_$(openssl rand -hex 16)

# Redis
REDIS_PASSWORD=$(openssl rand -hex 16)

# Network
SERVER_IP=157.180.45.153

# Environment
NODE_ENV=production
EOF

echo "✅ Archivo .env creado (ACTUALIZAR con tus API keys)"

# 8. Optimizaciones del sistema
echo "⚡ [8/8] Optimizaciones del sistema..."

# Aumentar límites de archivos abiertos
cat >> /etc/sysctl.conf << EOF

# Tradeul optimizations
fs.file-max = 2097152
vm.swappiness = 10
net.core.somaxconn = 1024
EOF
sysctl -p

# Aumentar límites para Docker
cat > /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF
systemctl restart docker

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                 ✅ SETUP COMPLETADO                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo ""
echo "1. ACTUALIZAR .env con tus API keys:"
echo "   vim /opt/tradeul/.env"
echo ""
echo "2. COPIAR tu código desde Mac (si no usaste git clone):"
echo "   En tu Mac: scp -r ~/Desktop/Tradeul-Amsif/* root@157.180.45.153:/opt/tradeul/"
echo ""
echo "3. INICIALIZAR base de datos:"
echo "   cd /opt/tradeul"
echo "   docker compose up -d timescaledb redis"
echo "   sleep 10"
echo "   docker exec tradeul_timescale psql -U tradeul_user -d tradeul -f /app/scripts/init_db.sql"
echo ""
echo "4. LEVANTAR todos los servicios:"
echo "   docker compose up -d"
echo ""
echo "5. VERIFICAR que todo funcione:"
echo "   docker ps"
echo "   curl http://localhost:3000"
echo ""
echo "6. ACCEDER desde tu Mac:"
echo "   http://157.180.45.153:3000"
echo ""
echo "═══════════════════════════════════════════════════════════════"

