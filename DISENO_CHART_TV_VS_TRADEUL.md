# Chart en tiempo real: TradingView vs Tradeul — análisis de ingeniería
**Fecha:** 2026-08-02 · **Método:** protocolo de tradingview.com capturado en vivo (frames verbatim de wss://data.tradingview.com, sesión fra2-charts-free-4) + lectura del código propio en /opt/tradeul (chart_aggregator, bar_builder, websocket_server, api_gateway, frontend/components/tvchart). Nada especulado: cada afirmación sobre ambos sistemas está medida.

---

## 1. Las dos observaciones del usuario, verificadas

**"Ellos forman las velas en el servidor aunque la pestaña esté inactiva"** → CIERTO y es la piedra angular. En TV cada resolución es una *serie server-side*: el servidor agrega los ticks y envía la vela EN CURSO ya formada (OHLCV completo). El cliente jamás agrega — solo sobrescribe y pinta. La pestaña puede morir, dormir o desconectarse: la serie existe en el servidor y al volver se recibe un snapshot fresco completo (timescale_update). No hay nada que "reparar" en el cliente.

**"Cada vela tiene un index"** → CIERTO. Formato real capturado: `{"i":4,"v":[1785662760.0,63298.01,63298.01,63272.0,63272.01,2.2154]}`. Identidad de doble capa: timestamp epoch (estable, v[0]) + índice entero `i` efímero por conexión. Los deltas (`du`) referencian el índice; los estudios llegan alineados por el MISMO índice; el histórico hacia atrás se acuña con índices NEGATIVOS (-1,-2,-3) sin renumerar nada. El índice no es persistente: tras reconectar se reinicia con el nuevo snapshot.

## 2. El modelo TradingView (capturado)

- **Transporte:** un solo WS multiplexa N sesiones (chart/quote/replay) con framing propio `~m~len~m~{json}`; cada mensaje del servidor lleva timestamp del servidor (t, t_ms).
- **Ciclo de una serie:** `resolve_symbol` → `create_series(cs, sds_1, "s1", símbolo, "1", 300)` → `series_loading` → `symbol_resolved` → `timescale_update` (snapshot con las N barras indexadas) → `series_completed {rt_update_period:5}`.
- **Vela viva:** `du` con la barra completa re-emitida (mismo `i`, valores evolucionando), conflacionada server-side según tier (5s en free). **La vela nueva NUNCA nace por `du`:** la acuña el servidor con un `timescale_update` incremental que extiende la escala (barra sembrada open=último precio, v=0.0).
- **Countdown/rollover:** cada delta lleva `lbs.bar_close_time` calculado por el SERVIDOR. El cliente hace una resta; no confía en su reloj. (Nuestro bug candidato "invalid date for DWM" es exactamente la clase de fallo que esto elimina.)
- **Anti-carreras:** turnaround id (`"s1"`→`"s2"`) versiona la serie en cada modify_series; cualquier delta rezagado de la versión vieja se descarta. Cambio de resolución = serie re-agregada en servidor + snapshot limpio.
- **Reconexión / pestaña dormida:** NO hay resume ni secuencias ni parcheo de huecos. Sesiones DESECHABLES: reconectar = re-suscribir = snapshot fresco. Huecos imposibles por construcción (el servidor es la única fuente); duplicados imposibles (sobrescritura por índice).
- **Calendarios:** `symbol_resolved` empuja el calendario COMPLETO (festivos 2000→2027, subsesiones pre/regular/post/night, correcciones de media jornada). El cliente no calcula NI UNA fecha de sesión. Diario anclado a 09:30 ET con cierre 15:59:59 servido, semanal al lunes.
- **Histórico:** `request_more_data` extiende LA MISMA serie hacia atrás (índices negativos). Una sola fuente de verdad para histórico y vivo; sin costura REST/WS.

## 3. El modelo Tradeul (medido en el código)

```
polygon_ws → stream:realtime:trades (Redis Stream)
                 → chart_aggregator: micro-DELTAS OHLCV cada 150ms (chart:trades:{SYM})
                 → bar_builder: velas server-side 9 TFs intradía [1..720min]
                       vela en curso en Redis (bars:{tf}min:current) + selladas (chart:sealed:{SYM})
websocket_server: reenvía ambos canales; subscribe_chart = ACK sin snapshot, sin secuencia
frontend (por CADA celda de chart): applyAggregate pliega los deltas de 150ms en velas
                 + heurística de huecos (gap-backfill→reset) + merge de selladas (solo si el TF coincide)
                 + normalización diaria en cliente (toTVBar) + resyncAll/resetData/watchdogs al despertar
REST /api/v1/chart: proxy a Polygon (intradía) y FMP (diario) + caché Redis + _stitch_live_bar
```

Hechos clave:
1. **El cable lleva deltas de trades (lo agregado en 150ms), no estados de vela.** Perder un delta = volumen mal para siempre hasta el próximo resync. La identidad es solo el timestamp del último trade → la CL grita "time order violation" cuando algo llega desordenado.
2. **La vela viva se construye N veces** — una por celda de chart abierta, cada una con su lastBar, su heurística de huecos y su estado. La complejidad vive multiplicada en el peor sitio: el cliente.
3. **bar_builder YA forma velas en servidor** (incluida la vela en curso, en Redis) — pero el chart NO la consume como fuente primaria; solo la usa para corrección a posteriori (sellada, y solo si el timeframe coincide exacto). El diario ni se forma (máx 720min): viene de FMP por REST.
4. **subscribe_chart no manda snapshot ni seq** (los canales del scanner SÍ tienen snapshot+sequence — el patrón bueno existe en casa, pero no en charts).
5. **Histórico y vivo son dos mundos** (Polygon/FMP+caché vs Redis pub/sub) cosidos DOS veces: en el endpoint (_stitch_live_bar) y en el cliente (re-siembra de lastBar en getBars). Cada costura es una fuente de bugs medida.
6. **El despertar es reparación client-side:** visibilitychange→resyncAll+resetData, liveness 75s del SharedWorker, watchdogs de celda, recreación con reintentos. El flood de warnings nocturno (2026-08-02, sin resolver) vive en esta maquinaria.
7. **Bugs ya medidos que son síntomas de esta clase:** el último segundo del minuto cae en la vela siguiente (agregación cliente del camino A.*); sellado sin diario; violaciones de orden temporal; flood al despertar; countdown dependiente de getServerTime una sola vez al init.

## 4. Por qué el planteamiento de TV es mejor ingeniería

| Dimensión | TradingView | Tradeul hoy | Consecuencia |
|---|---|---|---|
| Formación vela viva | Servidor, 1 vez por (símbolo,res) | Cliente, 1 vez POR CELDA | Divergencia, bugs multiplicados |
| Identidad de barra | timestamp + índice + turnaround | solo timestamp | Carreras y "time order violation" |
| Recuperación | Resnapshot (sesión desechable) | Resume + heurísticas + resyncs | Nuestra maquinaria más frágil |
| Nueva vela | La acuña el servidor (escala) | La deduce cada cliente | Vela del último segundo mal |
| Rollover/countdown | bar_close_time en cada delta | reloj cliente + serverTime 1 vez | Bugs DWM/medianoche |
| Calendarios sesión | Empujados completos al resolver | Calculados en cliente (toTVBar) | Alineación diaria frágil |
| Histórico | Misma serie (índices negativos) | REST externo + costuras | Dos fuentes de verdad |
| Conflación | Server-side por tier (5s free) | 150ms fijos a todos | Coste sin control |
| Huecos/duplicados | Imposibles por construcción | Detectados por heurística | Fiabilidad = suerte |

La idea-fuerza: **TV eligió lo simple-correcto (resnapshot barato de ~300 barras) donde nosotros construimos lo difícil-frágil (resume y auto-reparación).** Y movió TODA la complejidad a un solo sitio (la serie server-side), donde se paga una vez, en vez de N veces en N navegadores.

Matices a favor nuestro (para ser justos): su modelo cuesta CPU de servidor por (espectador×serie) — mitigable amortizando la serie por (símbolo,res) entre todos los suscriptores; nuestro workspace multi-ventana consume decenas de símbolos a la vez; y la Charting Library nos empuja al datafeed client-side. Pero ese último punto es un falso límite: **el contrato de la CL (getBars + onRealtimeCallback) ES exactamente snapshot + estados de vela completos.** La CL espera que le des velas formadas; somos nosotros los que le damos deltas plegados en el cliente.

## 5. Camino de adopción (sin cambiar de librería)

**F1 — Serie server-side intradía (el 80% del valor):** subscribe_chart pasa a (símbolo, resolución). Al suscribir: SNAPSHOT de la vela en curso (bar_builder ya la tiene en Redis) + seq. Después: estados COMPLETOS de la vela en curso conflacionados (250–500ms), con `seq` y `bar_close_time` en cada mensaje; el rollover lo acuña el servidor (vela nueva sembrada open=último, v=0). En el cliente: applyAggregate y la heurística de huecos MUEREN; el datafeed reenvía estados a onRealtimeCallback y punto.
**F2 — Series D/W/M server-side:** bar_builder + market_session (el calendario ya es un servicio nuestro) forman el diario/semanal; muere la normalización DWM del cliente (toTVBar) y su clase de bugs.
**F3 — Epoch/turnaround propio:** cada (re)suscripción lleva un id; todo mensaje lo ecoa; el datafeed descarta rezagados. Muere la carrera de cambio de símbolo/resolución.
**F4 — Despertar = resnapshot:** visibilitychange/reconexión → tirar estado + re-suscribir (snapshot). Muere resyncAll/gap-backfill; el watchdog queda solo para fallos reales de init. El flood nocturno pierde su hábitat.
**F5 (opcional) — Conflación por tier y unificar histórico** sobre el mismo almacén del builder.

Orden recomendado: F1→F4 primero (elimina las dos fuentes de incidentes medidas), F2 después, F3 barato en cualquier momento, F5 cuando toque monetizar.

---
*Capturas del protocolo TV, fuentes (GitHub de ingeniería inversa + soporte oficial) y archivos de trabajo: ver informe del agente 2026-08-02. Este doc sigue la regla no-parchear-sin-medir: todo lo afirmado sobre Tradeul tiene ruta de archivo y línea en el repo.*

---

## Adenda 2026-08-02: cadencia PREMIUM medida (corrección al §2)

El `rt_update_period: 5` capturado por la sonda aplica SOLO al tier anónimo/free. Medición sobre la cuenta Premium real del usuario (BTCUSDT · 1m en vivo, MutationObserver sobre la leyenda OHLCV del chart, ventana visible de ~10s):

- 22 actualizaciones de la vela viva en ~8,6s efectivos (2,56/s de media CON tramos sin trades).
- **Gap mediano entre actualizaciones: 31 ms; mínimo 11 ms; 16 de 21 gaps < 100 ms.** Patrón de ráfagas a frames consecutivos de rAF (16 ms) separadas por silencios sin trades (máx 6,3s en un minuto tranquilo de domingo).
- Conclusión: **Premium = streaming por tick pintado a cadencia de requestAnimationFrame**, no conflación de 5s. La conflación por tier es real y es producto: free 5s → Premium sub-100ms. (Nuestros 150 ms fijos para todos quedan entre ambos.)
- Límite del método: mide el repintado del cable (cota inferior, cuantizada a rAF), no el cable mismo: **el socket de datos de tradingview.com vive dentro de un worker** — invisible desde el contexto de la página (mismo patrón que nuestro SharedWorker). Hallazgo adicional: en pestañas ocultas TV hiberna sesiones (protocolo `quote_hibernate_all`) y congela el repintado; los datos de título siguen llegando throttled (~1-3s).

## Adenda 2 — Capa por capa del tick al píxel (respuesta a "¿tenemos el repaint igual y con índices?")

| Capa | tradingview.com | Tradeul (ventana TC) | ¿Iguales? |
|---|---|---|---|
| 1. Socket | En worker; du por tick con {i,v} + bar_close_time | SharedWorker; micro-delta OHLCV 150ms sin id | ✗ (patrón worker sí; contrato no) |
| 2. Worker→página | postMessage de estados de vela | postMessage de deltas de trades | ✗ |
| 3. Modelo de serie | El servidor ya dio la vela; cliente reemplaza por índice | applyAggregate pliega deltas + heurística huecos + DWM cliente | ✗ (nuestra capa extra, origen de bugs) |
| 4. Motor de serie/timescale | Series interno indexado con regla mismo-tiempo→replace / mayor→append | EL MISMO (Charting Library v31 = mismo core; misma regla, con "time order violation" si se viola) | ✓ IDÉNTICO |
| 5. Repaint | Máscara de invalidación + 1 rAF + canvas | EL MISMO, ya afinado (2026-08-01: máscara fusionada + 1 rAF) | ✓ IDÉNTICO |
| Oculta/despertar | Hibernate + congelar rAF; volver = snapshot | Congelar rAF; volver = resync/reparación | ✗ (F4) |

Conclusión: **el repaint y los índices YA los tenemos — son el motor de la CL, idéntico al de tradingview.com.** Los índices {i,v} de su wire son la serialización del mismo modelo indexado que nuestra CL usa por dentro. Nuestro gap real está en las capas 1-3: el contrato del cable (estados completos + snapshot + seq/epoch + rollover acuñado en servidor) y la eliminación de la capa applyAggregate. En nuestro wire el equivalente funcional de su índice+turnaround es seq+epoch por suscripción (la CL consume barras por tiempo vía onRealtimeCallback; el índice interno se lo gestiona ella).

Deuda señalada: existe un SEGUNDO sistema de chart (ventana "chart" legacy con lightweight-charts + useLiveChartData) que duplica toda la cadena con otro motor. Unificar en uno tras F1-F4.

Pendiente de medir (mercado cerrado hoy): cadencia de repintado de NUESTRA TC con el mismo método (MutationObserver en leyenda) en horario de mercado, para el número simétrico al gap mediano de 31 ms medido en TV Premium.

## Adenda 3 — Radio de impacto de F1 (verificado en código, 2026-08-02)

**Sorpresas a favor:** (1) `seq` por símbolo YA se estampa en chart_aggregate (websocket_server nextChartSeq:1752; el legacy lo usa, el TC lo ignora); (2) bar_builder ya tiene POST /hydrate y el server ya avisa a polygon_ws en el primer suscriptor (subscribeClientToChart:2857); (3) la lógica a portar (lib/barAggregation.ts) tiene suite de tests propia.

**Cambios por componente:**
1. `bar_builder/main.py` — publicar ESTADO de vela en curso por (sym,tf) a canal nuevo `chart:state:{SYM}` con bar_close_time+is_closed; conflación 150-250ms SOLO para símbolos con suscriptores. D1: alimentar el plegado fino desde stream:realtime:trades (hoy A.* 1s; PUBLISH_CURRENT_INTERVAL min 0.25s se queda corto para fluidez actual de 150ms).
2. `websocket_server/src/index.js` — subscribe_chart v2 (symbol, resolution, epoch): SNAPSHOT desde bars:{tf}min:current + reenvío de estados con seq por sym#tf y epoch. v1 (chart_aggregate trades+A.*) INTACTO mientras viva el chart legacy. OJO: chartSeqCounters se borra al perder el último suscriptor (:2921) — con epoch deja de importar.
3. `datafeed.ts` — consumir chart_bar_state→onTick directo; MUEREN applyAggregate, gap-backfill, re-siembra de lastBar en getBars y el merge de selladas (la sellada = último estado con is_closed). Hueco de seq → re-pedir snapshot, no resetData. D/W/M siguen por el camino actual hasta F2.
4. `TVChartCell.tsx` — despertar/reconexión = re-subscribe con epoch nuevo + snapshot (F4); fuera resyncAll/resetData; watchdog solo para init.
5. `lib/chartStreams.ts` — refcount de clave symbol → symbol#res.
6. SharedWorker — nada obligatorio; hibernate de suscripciones chart en pestañas ocultas como mejora posterior.

**No se toca:** CL/render, REST /chart (F5), chart_aggregator (tape+legacy), chart legacy (v1).

**Decisiones previas:** D1 fuente/cadencia del builder (recomendado: trades para suscritos, conflación 150-250ms). D2 horario extendido: hoy builder forma 4:00-20:00 y la CL filtra por SUBSESSIONS declaradas — verificar con un chart en RTH que la CL corta sola; si no, filtro barato en datafeed. D3: daily fuera de F1 (sigue REST/FMP hasta F2).

**Riesgo que F1 elimina de paso:** el doble feed actual (trades 150ms + A.* 1s como el MISMO tipo chart_aggregate, dedup solo en legacy) es el hábitat del bug "último segundo del minuto en la vela siguiente" — con el plegado en un solo sitio (builder) desaparece para la TC.

**Orden:** builder→ws v2 (v1 intacto)→datafeed/Cell tras flag→prueba lunes en mercado abierto con dos ventanas TC (v1 vs v2 en paralelo)→F4→F2.
