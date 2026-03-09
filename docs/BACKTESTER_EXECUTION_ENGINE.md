# Motor de ejecución (paper / live)

Estado actual y cómo encajaría un motor de ejecución en Tradeul.

---

## 1. ¿Tenemos hoy un motor de ejecución?

**No.** Tradeul **no tiene** hoy un motor que envíe órdenes a un broker (paper o real).

| Componente | Qué hace | ¿Envía órdenes? |
|------------|----------|------------------|
| **Backtester** | Simula estrategias sobre datos históricos; produce trades y métricas. | No. Todo es simulación en memoria. |
| **Scanner / eventos** | Detecta gappers, volumen, noticias; sirve listas y alertas. | No. Solo datos y filtros. |
| **API / frontend** | Exponen backtest y scanner. | No. No hay integración con broker. |

Es decir: **backtest y señales existen; la ejecución (enviar órdenes a un broker) no está implementada.**

Referencia: Trade Ideas tiene un “Brokerage Plus Module” para live; ellos recomiendan backtest → paper → live. Nosotros hoy solo cubrimos el primer paso (backtest).

---

## 2. Qué sería un “motor de ejecución”

Un **motor de ejecución** es el componente que:

1. **Recibe señales** de entrada/salida (de una estrategia backtesteada, del scanner, de reglas en tiempo real, o de un agente).
2. **Traduce** esas señales en **órdenes** concretas: mercado, límite, stop, stop-limit, tamaño (shares o dólares).
3. **Envía** esas órdenes a un **broker** (Alpaca, Interactive Brokers, etc.) en modo **paper** (cuenta simulada) o **live** (cuenta real).
4. **Sigue** el estado de las órdenes y posiciones (filled, partial, cancelled) y opcionalmente actualiza trailing stops, targets, etc.

Responsabilidades típicas:

- **Gestión de sesión:** Horario de mercado, premarket/postmarket si el broker lo permite.
- **Riesgo:** Límites por posición, por día, por símbolo; no superar buying power.
- **Reintentos y errores:** Timeout, rechazo del broker, conexión caída.
- **Auditoría:** Log de todas las órdenes enviadas y su resultado.

---

## 3. Cómo encajaría en la arquitectura

Flujo lógico:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Backtester /   │     │  Motor de       │     │  Broker API     │
│  Estrategia /   │────▶│  ejecución      │────▶│  (Alpaca, IB,   │
│  Scanner        │     │  (paper o live) │     │  etc.)          │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     Señales                  Órdenes                 Fills reales
     (ticker, side,            (market, limit,          o simulados
      size, target, stop)      stop, size)
```

- **Entrada al motor:** Una “señal” bien definida: símbolo, dirección (long/short), tamaño (shares o $), tipo de orden, opcional target/stop.
- **Salida del motor:** Órdenes enviadas al broker (o al simulador de paper) y estado de posiciones/órdenes.
- **No sustituye al backtester:** El backtester sigue siendo off-line, histórico. El motor de ejecución es para **tiempo real** (o paper con datos en vivo).

Opciones de diseño:

- **A) Servicio dedicado “execution”**  
  Microservicio que expone API (ej. “ejecutar esta señal en paper”) y dentro habla con el broker. El frontend o un job llama a este servicio cuando el usuario “activa” una estrategia o una alerta.

- **B) Integrado en api_gateway**  
  Endpoints tipo `POST /api/v1/execution/signal` que validan la señal y delegan en un cliente del broker (library o API REST). Menos aislamiento que un servicio aparte.

- **C) Worker + cola**  
  Las señales se publican en una cola (Redis, etc.); un worker las consume y envía órdenes al broker. Útil si hay muchas señales o se quiere retry/backoff.

Para “el mejor backtester del mundo” no es obligatorio tener ejecución; sí es natural ofrecer después **paper trading** (misma lógica que el backtest pero con precios en vivo y órdenes simuladas) y luego **live** con un broker, y ahí es donde entra el motor de ejecución.

---

## 4. Resumen

| Pregunta | Respuesta |
|----------|-----------|
| ¿Tenemos motor de ejecución hoy? | **No.** Solo backtest (simulación) y scanner; no enviamos órdenes a ningún broker. |
| ¿Qué sería? | Componente que recibe señales, las convierte en órdenes y las envía a un broker (paper o live). |
| ¿Dónde encaja? | Entre “señales” (backtest/estrategia/scanner) y la API del broker; opcionalmente como microservicio o dentro del API gateway. |
| ¿Prioridad? | Primero cerrar backtester “máximo nivel” (timing, universo, inspección); después se puede añadir paper/live con un motor de ejecución. |

Cuando decidas añadir paper o live, el siguiente paso sería definir el contrato de “señal” (payload) y elegir el primer broker a integrar (por ejemplo Alpaca o IBKR).
