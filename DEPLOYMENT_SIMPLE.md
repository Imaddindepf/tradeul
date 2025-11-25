# 🚀 DEPLOYMENT: Limpieza Automática de Caches (3:00 AM)

## QUÉ HACE

A las **3:00 AM cada día**, automáticamente limpia los caches para que el pre-market (4:00 AM) inicie con datos frescos.

---

## DEPLOYMENT (cuando no haya usuarios - madrugada)

### 1. Editar WebSocket Server

```bash
nano /opt/tradeul/services/websocket_server/src/index.js
```

**Agregar al inicio (línea ~25):**
```javascript
const { subscribeToNewDayEvents } = require('./cache_cleaner');
```

**Después de conectar Redis (línea ~85):**
```javascript
// Después de: logger.info("📡 Connected to Redis");
const redisSubscriber = redis.createClient(redisConfig);
await redisSubscriber.connect();
subscribeToNewDayEvents(redisSubscriber, lastSnapshots);
```

Guardar: `Ctrl+X`, `Y`, `Enter`

---

### 2. Rebuild y Restart

```bash
cd /opt/tradeul

# Rebuild
docker-compose build data_maintenance websocket_server

# Restart
docker-compose restart data_maintenance websocket_server
```

---

### 3. Verificar

```bash
# Verificar data_maintenance
docker logs tradeul_data_maintenance --tail 20 | grep cache_clear

# Debería mostrar:
# ✅ "cache_clear_scheduler_started"

# Verificar websocket
docker logs tradeul_websocket_server --tail 20 | grep -i subscribed

# Debería mostrar:
# ✅ "Subscribed to new trading day events"
```

---

## RESULTADO

- ✅ Cada día a las 3:00 AM se limpian caches automáticamente
- ✅ Pre-market (4:00 AM) inicia con datos limpios
- ✅ Usuarios pueden revisar datos por la noche (8 PM - 3 AM)

---

## SI ALGO FALLA

```bash
# Ver logs
docker logs tradeul_data_maintenance --tail 50
docker logs tradeul_websocket_server --tail 50

# Restart
docker-compose restart data_maintenance websocket_server
```

---

**Eso es todo.** Simple y automático.

