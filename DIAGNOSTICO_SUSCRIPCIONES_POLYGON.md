# Diagnóstico Completo: Problema de Suscripciones Polygon WebSocket

**Fecha**: 25 de Noviembre 2025  
**Hora**: 11:17 AM EST (Pre-Market)

---

## 📊 Síntomas Observados

- Scanner tiene **47 tickers** en categorías
- SET `polygon_ws:active_tickers` tiene **47 tickers**
- Polygon WS solo tiene **36 tickers** suscritos
- **GAP: 11 tickers faltantes**

### Tickers Afectados:
```
✗ NIO    - En categorías, en SET, pero NO suscrito
✗ SOXS   - En categorías, en SET, pero NO suscrito
✗ MSTZ   - En categorías, en SET, pero NO suscrito
✗ GOOG   - En categorías, en SET, pero NO suscrito
...y 7 más
```

---

## 🔍 Root Cause Identificado

### **Problema Principal: Reconexiones Constantes**

Polygon WebSocket está **reconectando cada 20-30 segundos**:
- **318 reconexiones en 1 hora**
- **Code 1008: Policy Violation**
- Polygon está **cerrando la conexión activamente**

### Evidencia:
```json
{"code": 1008, "reason": "", "event": "connection_closed"}
{"attempt": 1, "delay_seconds": 5, "event": "reconnecting"}
```

### Reconexiones detectadas:
```
10:40:42 - reconecting
10:41:02 - reconnecting (20s después)
10:41:36 - reconnecting (34s después)
10:41:56 - reconnecting (20s después)
...continúa cada 10-30 segundos
```

---

## 🔄 Flujo de Degradación

### Ciclo Vicioso:

1. **Polygon WS bootstrap**: Lee SET → 47 tickers → suscribe a 47
2. **Polygon cierra conexión** (Code 1008) después de 20s
3. **Re-conecta**: Re-suscribe `desired_subscriptions` (45 tickers ahora)
4. **Scanner envía unsubscribe** para 1 ticker que salió de categorías
5. **Polygon WS procesa**: Quita ticker de `desired_subscriptions`
6. **Polygon cierra conexión** de nuevo (Code 1008)
7. **Re-conecta**: Re-suscribe solo 44 tickers (perdió 1)
8. **Repite**: 44 → 43 → 42 → ... → 36

### Por Qué Se Pierden Tickers:

En el código `polygon_ws/main.py`:
```python
# Línea 376: Cuando llega unsubscribe
desired_subscriptions.discard(symbol)

# Línea 335: Al reconectar
await ws_client.subscribe_to_tickers(desired_subscriptions, event_types)
```

Si un ticker se desuscribe JUSTO ANTES de reconectar, se pierde para siempre.

---

## 🐛 ¿Por Qué Code 1008?

**Code 1008 = Policy Violation**

Posibles causas:
1. **Suscribiendo/Desuscribiendo demasiado rápido**
2. **Formato incorrecto de mensaje de suscripción**
3. **Límite de suscripciones excedido** (Polygon Advanced = 1000 max)
4. **Heartbeat/Ping-Pong no funcionando** correctamente
5. **Demasiados mensajes por segundo**

---

## 📋 Flujo Correcto (Cómo DEBERÍA funcionar)

### Scanner → Redis:
1. ✅ Evalúa tickers cada 10 segundos
2. ✅ Guarda categorías en `scanner:category:{name}` (17 en gappers_up)
3. ✅ Extrae TODOS los tickers únicos de categorías (47 total)
4. ✅ Guarda en SET `polygon_ws:active_tickers` (47)
5. ✅ Publica `subscribe`/`unsubscribe` al stream solo para CAMBIOS

### Websocket Server → Redis:
- Lee deltas/snapshots del scanner
- Mantiene índice `symbolToLists` en memoria
- NO participa en suscripciones a Polygon (eso es polygon_ws)

### Polygon WS → Polygon API:
1. ✅ Bootstrap: Lee SET `polygon_ws:active_tickers` (47)
2. ✅ Suscribe a todos en Polygon WebSocket
3. ✅ Lee stream `polygon_ws:subscriptions` para cambios
4. ❌ **PROBLEMA**: Reconecta cada 20s y pierde tickers

---

## ✅ Soluciones Propuestas

### Solución 1: Arreglar el Code 1008 (Prioritaria)

Investigar por qué Polygon cierra la conexión:

```python
# Posible problema en ws_client.py
async def subscribe_to_tickers(self, tickers: Set[str], event_types: Set[str]):
    # ¿Estamos enviando todos los tickers de golpe?
    # ¿Deberíamos batchear?
    subscribe_message = {
        "action": "subscribe",
        "params": ",".join(subscriptions)  # ← Puede ser muy largo
    }
```

**Acciones**:
- [ ] Limitar tamaño del mensaje de suscripción
- [ ] Batchear suscripciones (max 50-100 por mensaje)
- [ ] Agregar delay entre batches
- [ ] Verificar heartbeat/ping-pong

### Solución 2: Preservar desired_subscriptions

No permitir que `desired_subscriptions` se reduzca con unsubscribes temporales:

```python
# Opción A: No procesar unsubscribes, solo subscribes
if action == "unsubscribe":
    # No quitar de desired_subscriptions
    # Solo desuscribir de Polygon si está activo
    pass

# Opción B: Periódicamente re-sincronizar desde el SET
async def periodic_sync():
    active_tickers = await redis_client.smembers('polygon_ws:active_tickers')
    desired_subscriptions = active_tickers
```

### Solución 3: Agregar Heartbeat Monitoring

Detectar cuando Polygon está rechazando la conexión:

```python
# Track closed connections con code
if close_code == 1008:
    logger.error("policy_violation_detected")
    # Reducir rate de subscriptions
    # O cambiar estrategia
```

---

## 🎯 Solución Inmediata (Sin Restart)

Forzar re-sincronización desde el SET cada vez que se reconecta:

```python
# En manage_subscriptions(), al reconectar:
if ws_client.is_authenticated and not was_authenticated:
    # SIEMPRE re-leer el SET completo
    active_tickers = await redis_client.smembers('polygon_ws:active_tickers')
    desired_subscriptions = active_tickers  # Reset completo
    
    await ws_client.subscribe_to_tickers(desired_subscriptions, event_types)
```

---

## 📈 Métricas Para Monitorear

1. **Reconexiones por hora**: Debe ser < 5
2. **Gap (SET vs Suscritos)**: Debe ser 0-2 (tolerancia)
3. **Close Code 1008**: Debe ser 0
4. **Lag en consumer group**: Debe ser 0

---

## 🔧 Comandos Para Verificar

```bash
# Ver reconexiones recientes
docker logs --since "1h" tradeul_polygon_ws | grep "reconnecting" | wc -l

# Ver close codes
docker logs --since "1h" tradeul_polygon_ws | grep "connection_closed" | head -20

# Comparar SET vs Suscritos
docker exec -i tradeul_redis redis-cli -a PASSWORD SCARD "polygon_ws:active_tickers"
curl -s http://localhost:8006/subscriptions | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])"

# Ver lag
docker exec -i tradeul_redis redis-cli -a PASSWORD XINFO GROUPS "polygon_ws:subscriptions" | grep lag
```

---

## ⚠️ NO Hacer

- ❌ NO reiniciar servicios (oculta el problema)
- ❌ NO agregar más logging sin arreglar el root cause
- ❌ NO incrementar el rate de subscriptions (empeora el 1008)

## ✅ Sí Hacer

- ✅ Investigar por qué Code 1008
- ✅ Agregar batching de suscripciones
- ✅ Preservar desired_subscriptions en reconexiones
- ✅ Agregar monitoring de connection stability

