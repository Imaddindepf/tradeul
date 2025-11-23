# 📖 LÉEME PRIMERO - Tradeul Security Setup

## 🎯 Documento Principal

**Lee este documento para configurar toda la seguridad:**

📄 **[CONFIGURACION_SEGURIDAD.md](CONFIGURACION_SEGURIDAD.md)** (21 KB)

Este es el **ÚNICO documento que necesitas** para:
- ✅ Configurar Firewall de Hetzner
- ✅ Asegurar Redis con password
- ✅ Configurar servicios Docker (públicos vs privados)
- ✅ Configurar Frontend con IPs correctas
- ✅ Usar scripts de monitoreo
- ✅ Troubleshooting completo

---

## 📊 Scripts Principales

### 1. Monitoreo Continuo
```bash
cd /opt/tradeul
./scripts/monitor_system_health.sh 24  # Monitorear 24 horas
```

### 2. Diagnóstico Rápido
```bash
cd /opt/tradeul
./scripts/diagnose_system.sh  # Verifica todo el sistema
```

---

## 🚀 Quick Start

```bash
# 1. Verificar que todo está OK
cd /opt/tradeul
./scripts/diagnose_system.sh

# 2. Ver metadata en Redis
export $(grep REDIS_PASSWORD .env | xargs)
docker exec tradeul_redis redis-cli --no-auth-warning -a "$REDIS_PASSWORD" \
  --scan --pattern "metadata:ticker:*" | wc -l

# 3. Ver estado de servicios
docker ps --format "table {{.Names}}\t{{.Status}}"

# 4. Acceder al frontend
# http://TU_IP_SERVIDOR:3000/scanner
```

---

## 📚 Otros Documentos

- `README.md` - Información general del proyecto
- `PERFORMANCE_IMPROVEMENTS_SUMMARY.md` - Optimizaciones de performance
- `RECOVERY_GUIDE.md` - Guía de recuperación ante fallos

---

## ⚠️ IMPORTANTE

1. **NO expongas Redis** (puerto 6379) a internet
2. **USA contraseña fuerte** en `.env` para `REDIS_PASSWORD`
3. **Configura el firewall** de Hetzner con los puertos correctos
4. **Frontend debe usar IP del servidor**, NO `localhost`

---

**Todo lo que necesitas está en:** [CONFIGURACION_SEGURIDAD.md](CONFIGURACION_SEGURIDAD.md)
