# 🚀 Sistema Automático de Suscripciones a Polygon WS

## 📋 Problema Anterior

**❌ Arquitectura manual (Frontend-driven):**
```
Frontend → "Quiero suscribirme a AAPL, TSLA, NVDA..."
        ↓
WebSocket Server → polygon_ws:subscriptions
        ↓
Polygon WS Service → Polygon API
```

### Problemas:
- ❌ Frontend tiene que saber QUÉ tickers son relevantes
- ❌ Gestión manual de suscripciones/desuscripciones
- ❌ Múltiples clientes = múltiples suscripciones innecesarias
- ❌ No se adapta automáticamente al mercado
- ❌ Tickers que salen del ranking siguen suscritos (desperdicio)

---

## ✅ Nueva Arquitectura Profesional (Scanner-driven)

```
┌─────────────────────────────────────────────────┐
│ 1. Scanner Service                              │
│    - Filtra 11k → 1000 tickers (top ranked)    │
│    - Categoriza (gappers, momentum, etc.)      │
│    - Detecta cambios en rankings               │
│    ✅ PUBLICA automáticamente                   │
└──────────────┬──────────────────────────────────┘
               │
               │ Stream: polygon_ws:subscriptions
               │ {symbol: "AAPL", action: "subscribe"}
               │ {symbol: "GME", action: "unsubscribe"}
               │
               ▼
┌─────────────────────────────────────────────────┐
│ 2. Polygon WS Service                           │
│    - LEE stream de suscripciones                │
│    - SE SUSCRIBE automáticamente a nuevos       │
│    - SE DESUSCRIBE de tickers removidos         │
│    - Mantiene 500-1000 tickers activos          │
└──────────────┬──────────────────────────────────┘
               │
               │ Aggregates en tiempo real
               │ (OHLCV por segundo + volumen acumulado)
               │
               ▼
┌─────────────────────────────────────────────────┐
│ 3. WebSocket Server                             │
│    - Recibe aggregates de Polygon WS            │
│    - Broadcastea a frontend conectado           │
│    ✅ Frontend SOLO recibe datos                │
└─────────────────────────────────────────────────┘
```

---

## 🎯 Flujo de Auto-Suscripción

### **Ciclo 1: Scanner encuentra nuevos líderes**
```python
# Scanner filtra tickers (cada 10 segundos)
Filtered Tickers = [AAPL, TSLA, NVDA, MSFT, GOOGL]  # 1000 tickers

# Detecta NUEVOS tickers (no estaban en ciclo anterior)
New = [NVDA, MSFT]  # Entraron al ranking

# Publica suscripciones automáticamente
→ polygon_ws:subscriptions
  {symbol: "NVDA", action: "subscribe", source: "scanner_auto"}
  {symbol: "MSFT", action: "subscribe", source: "scanner_auto"}
```

### **Ciclo 2: Algunos tickers salen del ranking**
```python
# Nuevo scan (10 segundos después)
Filtered Tickers = [AAPL, TSLA, MSFT, AMD, INTC]  # NVDA y GOOGL salieron

# Detecta REMOVIDOS
Removed = [NVDA, GOOGL]  # Salieron del top 1000

# Publica desuscripciones automáticamente
→ polygon_ws:subscriptions
  {symbol: "NVDA", action: "unsubscribe", source: "scanner_auto"}
  {symbol: "GOOGL", action: "unsubscribe", source: "scanner_auto"}
```

---

## 💻 Implementación

### **1. Scanner Engine (scanner_engine.py)**

```python
class ScannerEngine:
    def __init__(self):
        # Track símbolos previos para detectar cambios
        self._previous_filtered_symbols: Set[str] = set()
    
    async def run_scan(self):
        # ... filtrado y scoring ...
        
        # ✅ AUTO-SUSCRIPCIÓN (después de categorizar)
        await self._publish_filtered_tickers_for_subscription(scored_tickers)
    
    async def _publish_filtered_tickers_for_subscription(self, tickers):
        """
        🚀 Sistema Automático de Suscripciones
        """
        # 1. Símbolos actuales
        current_symbols = {t.symbol for t in tickers}
        
        # 2. Detectar NUEVOS
        new_symbols = current_symbols - self._previous_filtered_symbols
        
        # 3. Detectar REMOVIDOS
        removed_symbols = self._previous_filtered_symbols - current_symbols
        
        # 4. Publicar suscripciones para NUEVOS
        for symbol in new_symbols:
            await self.redis.xadd("polygon_ws:subscriptions", {
                "symbol": symbol,
                "action": "subscribe",
                "source": "scanner_auto"
            })
        
        # 5. Publicar desuscripciones para REMOVIDOS
        for symbol in removed_symbols:
            await self.redis.xadd("polygon_ws:subscriptions", {
                "symbol": symbol,
                "action": "unsubscribe",
                "source": "scanner_auto"
            })
        
        # 6. Actualizar tracking
        self._previous_filtered_symbols = current_symbols
```

### **2. Polygon WS Service (polygon_ws/main.py)**

Ya estaba implementado (líneas 242-391):

```python
async def manage_subscriptions():
    """
    Gestiona suscripciones dinámicas leyendo del stream
    """
    desired_subscriptions = set()
    
    while True:
        # Leer mensajes del stream
        messages = await redis_client.read_stream(
            stream_name="polygon_ws:subscriptions",
            consumer_group="polygon_ws_subscriptions_group"
        )
        
        for message in messages:
            symbol = message['symbol']
            action = message['action']
            
            if action == "subscribe":
                # Suscribir a Polygon
                await ws_client.subscribe_to_tickers({symbol}, {"A"})
            
            elif action == "unsubscribe":
                # Desuscribir de Polygon
                await ws_client.unsubscribe_from_tickers({symbol}, {"A"})
```

---

## 📊 Ventajas del Sistema Automático

### **1. Centralización** 🎯
- ✅ UN solo punto de decisión: Scanner
- ✅ UN solo servicio gestiona suscripciones: Polygon WS
- ✅ Frontend simplificado: solo consume datos

### **2. Eficiencia** ⚡
- ✅ 1 suscripción por ticker (no por cliente)
- ✅ Auto-desuscripción de tickers irrelevantes
- ✅ Máximo 1000 suscripciones (dentro del límite de Polygon)
- ✅ Sin duplicaciones

### **3. Adaptabilidad** 🔄
- ✅ Se adapta automáticamente al mercado
- ✅ Responde a cambios de volatilidad
- ✅ Sigue los líderes en tiempo real
- ✅ Cambio de sesión → nuevos tickers relevantes

### **4. Profesionalismo** 💼
- ✅ Arquitectura event-driven
- ✅ Desacoplamiento de servicios
- ✅ Escalable (múltiples frontends sin overhead)
- ✅ Logs detallados y observabilidad

---

## 🔍 Monitoreo y Logs

### **Scanner logs (cada 10 segundos):**
```json
{
  "event": "🔔 Auto-subscribe nuevos tickers",
  "count": 15,
  "examples": ["MSGM", "VKTX", "SRRK", "ALRN", "VRCA"]
}

{
  "event": "🔕 Auto-unsubscribe tickers removidos",
  "count": 8,
  "examples": ["GME", "AMC", "BBBY"]
}

{
  "event": "✅ Auto-subscription actualizada",
  "total_active": 847,
  "new": 15,
  "removed": 8,
  "session": "MARKET_OPEN"
}
```

### **Polygon WS logs:**
```json
{
  "event": "ticker_subscribed",
  "symbol": "MSGM",
  "total_subscribed": 847
}

{
  "event": "ticker_unsubscribed",
  "symbol": "GME",
  "total_subscribed": 839
}
```

---

## 🧪 Testing

### **1. Verificar Auto-Suscripción**
```bash
# Ver mensajes del stream
docker compose exec redis redis-cli
> XLEN polygon_ws:subscriptions
> XREAD COUNT 10 STREAMS polygon_ws:subscriptions 0-0

# Ver suscripciones activas
curl http://localhost:8006/subscriptions
```

### **2. Simular Cambio de Rankings**
```bash
# Scanner procesa nuevo scan
# → Automáticamente publica cambios al stream
# → Polygon WS se ajusta automáticamente
```

### **3. Verificar Logs**
```bash
# Scanner
docker compose logs scanner | grep "Auto-subscribe"

# Polygon WS
docker compose logs polygon_ws | grep "ticker_subscribed"
```

---

## 📈 Métricas Esperadas

| Métrica | Valor Típico | Límite |
|---------|--------------|--------|
| **Tickers activos** | 500-1000 | 1000 (Polygon) |
| **Cambios por ciclo** | 10-50 | - |
| **Nuevos/ciclo** | 5-30 | - |
| **Removidos/ciclo** | 5-30 | - |
| **Latencia suscripción** | <100ms | - |
| **Latencia desuscripción** | <100ms | - |

---

## 🚨 Casos Edge

### **1. Primer Scan del Día**
```python
# _previous_filtered_symbols = set()  # Vacío
# current_symbols = {1000 tickers}

# new_symbols = 1000  # Todos son nuevos
# → Suscribirse a los 1000 tickers iniciales
```

### **2. Cambio de Sesión (PRE_MARKET → MARKET_OPEN)**
```python
# Pre-market leaders vs Market-open leaders son DIFERENTES
# → Automáticamente se ajusta a nuevos líderes
```

### **3. Market CLOSED**
```python
# Scanner no filtra nada (no hay snapshots)
# → No se publican cambios
# → Polygon WS mantiene últimas suscripciones (opcional: desuscribir todo)
```

### **4. Reconexión de Polygon WS**
```python
# Polygon WS se desconecta y reconecta
# → manage_subscriptions() re-suscribe TODOS los tickers en desired_subscriptions
# → No se pierden suscripciones
```

---

## 🎓 Comparación: Manual vs Automático

| Aspecto | Manual (Frontend) | Automático (Scanner) |
|---------|-------------------|----------------------|
| **Decisión** | Frontend decide | ✅ Scanner decide (profesional) |
| **Gestión** | Frontend gestiona | ✅ Polygon WS gestiona |
| **Eficiencia** | N clientes = N suscripciones | ✅ N clientes = 1 suscripción |
| **Adaptabilidad** | Estático | ✅ Dinámico (se adapta al mercado) |
| **Complejidad Frontend** | Alta | ✅ Mínima (solo consume) |
| **Escalabilidad** | Limitada | ✅ Excelente |
| **Desperdicio** | Suscripciones obsoletas | ✅ Auto-cleanup |

---

## 🔐 Seguridad y Rate Limits

### **Polygon Limits:**
- ✅ Max 1000 suscripciones simultáneas
- ✅ Max 500 requests/min (para comandos)
- ✅ Scanner limita a 1000 tickers (settings.max_filtered_tickers)

### **Protecciones:**
```python
# 1. Límite en Scanner
if len(scored_tickers) > settings.max_filtered_tickers:
    scored_tickers = scored_tickers[:settings.max_filtered_tickers]

# 2. Batch de suscripciones (en lugar de 1 por 1)
# TODO: Implementar batching si hay >100 cambios simultáneos

# 3. Throttling en Polygon WS
# TODO: Rate limiting si excede 500 requests/min
```

---

## 📚 Referencias

- **Stream usado:** `polygon_ws:subscriptions` (settings.key_polygon_subscriptions)
- **Consumer group:** `polygon_ws_subscriptions_group`
- **Formato mensajes:**
  ```json
  {
    "symbol": "AAPL",
    "action": "subscribe|unsubscribe",
    "source": "scanner_auto",
    "session": "MARKET_OPEN",
    "timestamp": "2025-11-07T17:45:00Z"
  }
  ```

---

## ✅ Checklist de Implementación

- [x] Agregar `_previous_filtered_symbols` tracking en Scanner
- [x] Crear método `_publish_filtered_tickers_for_subscription()`
- [x] Detectar nuevos símbolos (set difference)
- [x] Detectar símbolos removidos (set difference)
- [x] Publicar suscripciones al stream
- [x] Publicar desuscripciones al stream
- [x] Logs informativos con contadores
- [x] Polygon WS ya consume el stream (implementado previamente)
- [ ] **TODO:** Testing en producción
- [ ] **TODO:** Monitoreo con Grafana/Prometheus
- [ ] **TODO:** Alertas si excede 1000 suscripciones

---

**Fecha de implementación:** 2025-11-07  
**Versión:** 1.0  
**Status:** ✅ Implementado y listo para testing



