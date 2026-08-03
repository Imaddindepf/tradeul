# Estado compartido entre pestañas — análisis medido y diseño objetivo

Fecha: 2026-08-03. Medido en `/opt/tradeul/frontend` y `services/api_gateway` (solo lectura).
Contexto: el incidente del tema (botón Dark + UI light) destapó que el estado
multi-pestaña está repartido en mecanismos que no se conocen entre sí.

---

## 1. Inventario medido (lo que existe HOY)

### 1.1 Seis mecanismos distintos conviven

| # | Mecanismo | Dónde | Sincroniza entre pestañas | Política |
|---|-----------|-------|---------------------------|----------|
| 1 | zustand `persist` → localStorage | 11 stores (`tradeul-user-preferences`, `tradeul-event-filters`, `catalyst-alerts-storage`, `tradeul-notes-storage`, `tradeul-workflow-v2`, `tradeul-chat`, `news-global-filters`, `tradeul-alert-presets`, `tickers-store`, `news-tickers-store`, `news-store`) | ❌ NO en caliente (cero listeners `storage` propios en todo el frontend — medido) | Cada `set()` escribe el objeto ENTERO; última pestaña que escribe gana el próximo arranque |
| 2 | localStorage suelto | ~14 claves/familias más: `theme` (next-themes), `tradeul-language`, `scatter-axes`, `chart-toolbar-last`, `chart-indicator-settings`, chart drawings (2), pinned commands, market pulse, notes-window, anchos de AIAgent/backtest, prefijos por tabla (scanner, CategoryTableV2, screener) | ❌ NO | Idem: divergencia silenciosa hasta el siguiente reload |
| 3 | next-themes clave `theme` | interna de la librería | ✅ SÍ (única clave con listener `storage`, el de la librería) | La otra pestaña APLICA el cambio al DOM. Hasta el fix de hoy, sin puente al store → botón Dark + UI light |
| 4 | Backend `user_preferences` (TimescaleDB) | `useWorkspaceSync`: GET al montar, PATCH debounce 3 s, `sendBeacon` en `beforeunload` | ❌ NO hay push del server; cada pestaña es una isla ("each tab is independent", comentario del hook) | Last-write-wins TOTAL (ver 1.2) |
| 5 | SharedWorker para WS de mercado | 8 ficheros (NewsProvider, MarketTableLayout, useLiveChartData, useRxWebSocket, useStableConnectionStatus, useTradingDayReset, useMarketEvents, news-window) | ✅ SÍ — una conexión para N pestañas | Bien resuelto. Es la prueba de que el proyecto ya sabe hacer cross-tab cuando se lo propone |
| 6 | sessionStorage | 1 clave (`lastChunkErrorReload`) | ❌ (por diseño, per-tab) | Correcto para su uso |

No hay: BroadcastChannel (la única mención es un comentario diciendo que no hay),
Web Locks, IndexedDB.

### 1.2 El backend no arbitra nada (medido en `routes/user_prefs.py:482-556`)

`PATCH /user/preferences/workspaces` hace `INSERT … ON CONFLICT DO UPDATE` con:
- `workspaces = $2` y `active_workspace_id = $3` SIEMPRE (reemplazo total);
- `colors/theme/columns` con `COALESCE` (solo si vienen en el body) — pero el
  cliente **siempre los envía todos** (`useWorkspaceSync` y el beacon mandan el
  estado completo), así que el COALESCE nunca protege nada en la práctica;
- **ningún** control de concurrencia: ni versión, ni `If-Match`, ni comparación
  de `updated_at`. `workspacesModifiedAt` existe en el store del cliente y ni
  siquiera se envía.

---

## 2. Carreras concretas que este diseño permite (todas reproducibles)

1. **Pestaña A cambia el layout, pestaña B cambia el tema** (±3 s): cada
   debounce PATCHea el estado COMPLETO de su pestaña → el segundo request pisa
   el campo que cambió el primero. Pérdida silenciosa, sin error en ningún lado.
2. **`activeWorkspaceId` compartido**: A trabaja en "Main", B en "Workspace 2".
   Cada PATCH de cualquiera de las dos pisa el workspace activo del otro → al
   recargar, la pestaña "salta" a otro workspace. (El PATCH lo envía siempre.)
3. **Beacon de recarga**: `beforeunload` también dispara en F5. La instancia
   moribunda beaconea su estado completo mientras la nueva hace el GET inicial:
   si el beacon aterriza después del GET, la nueva sesión trabaja sobre estado
   que ya no es el del server; si aterriza después del primer PATCH nuevo, lo
   pisa. Sin orden garantizado.
4. **El incidente del tema de hoy**: la clave `theme` era la única con sync
   cross-tab (next-themes), sin puente al store → una pestaña vieja podía dejar
   "botón Dark + UI light". Parcheado hoy con adopción bidireccional en
   `ThemeSync`, pero el patrón (dos fuentes de verdad para el mismo dato) sigue
   siendo la causa raíz.
5. **Los 11 stores persist**: dos pestañas modifican dominios distintos (notas
   en A, filtros de eventos en B) → sin conflicto real. Pero el MISMO dominio en
   dos pestañas (notas en ambas) → la última escritura de localStorage gana el
   próximo arranque y el trabajo de la otra desaparece sin aviso.
6. **`backendLoadComplete` / retries**: parches existentes (gate de escritura,
   retry con backoff) que tratan síntomas de este mismo diseño — señal de que el
   problema ya mordió antes (layouts perdidos).

---

## 3. Cómo lo resuelven las apps profesionales

No hay un mecanismo único: hay una **clasificación por tipo de estado** y una
política explícita por tipo. Ese es el orden que a Tradeul le falta.

### 3.1 Clasificación estándar

| Tipo de estado | Ejemplos en Tradeul | Política profesional |
|---|---|---|
| **Config de usuario** (baja frecuencia, global) | tema, idioma, colores, fuente, timezone, columnas | Server = fuente de verdad. Cambio → server → push a todas las sesiones (WS/SSE) y BroadcastChannel a las pestañas hermanas. localStorage SOLO como caché de arranque anti-FOUC. Last-write-wins está bien aquí |
| **Documento/espacio de trabajo** (alta frecuencia, valioso) | workspaces + windowLayouts, notas, workflows | Un dueño a la vez o versionado. TradingView: si abres el mismo layout en otra pestaña, la segunda AVISA y desactiva su autosave — no intenta merge. Google Docs/Figma: OT/CRDT (sobredimensionado para esto). Mínimo viable: versión optimista + 409 |
| **Estado efímero de UI** (per-tab) | anchos de paneles, scroll, popup abierto, ejes del scatter | Per-tab por diseño: sessionStorage o memoria. NO sincronizar. (Hoy varios van a localStorage compartido sin necesidad) |
| **Datos de mercado** (streams) | quotes, tape, news | SharedWorker/una conexión compartida — Tradeul YA lo hace bien |

### 3.2 Mecanismos concretos del patrón moderno

- **BroadcastChannel** — canal pub/sub mismo-origen, soportado por todos los
  navegadores actuales. Es EL mecanismo para "avísale a las otras pestañas";
  el evento `storage` queda como fallback legado.
- **Web Locks API (`navigator.locks`)** — elección de líder: UNA pestaña
  se encarga del sync saliente/beacon/limpiezas; las demás delegan. Elimina
  el problema "N pestañas escriben el mismo endpoint".
- **Versionado optimista** — el cliente manda la versión que leyó
  (`baseUpdatedAt` o un entero); el server escribe solo si coincide
  (`WHERE updated_at = $base`), si no responde 409 con el estado actual y el
  cliente rebasa/mergea. Una condición WHERE: barato y mata TODAS las pisadas
  silenciosas.
- **Payloads parciales** — cada PATCH lleva solo los campos que ESA acción
  cambió. Combinado con el COALESCE que el backend ya tiene, reduce el radio de
  pisada aun sin versionado.
- **`visibilitychange`/dirty-flag en vez de `beforeunload` incondicional** —
  beacon solo si hay cambios sin sincronizar; `beforeunload` es poco fiable y
  dispara en cada F5.
- **Push del server** (echo de "preferences updated" por el WS existente) —
  lo que convierte multi-tab en multi-dispositivo. Slack/Linear/Notion lo hacen
  así: la otra sesión se entera por el canal realtime, no por localStorage.

---

## 4. Diseño objetivo para Tradeul (fases, sin implementar)

**F0 — Cortar las pisadas gordas (día):**
1. PATCH con payload parcial: `theme`/`colors`/`columns` solo si cambiaron en
   esta pestaña (dirty-tracking por dominio en `useWorkspaceSync`).
2. `activeWorkspaceId`: enviarlo solo en la acción "cambiar de workspace".
3. Beacon solo con dirty-flag (y en `visibilitychange`, no solo unload).

**F1 — Versionado optimista (día):** guardar `updatedAt` del último GET/PATCH
en el store; enviarlo como `baseUpdatedAt`; backend: `WHERE updated_at <= $base`
→ si no matchea, 409 + estado fresco; cliente: refetch + re-aplicar su delta
(para workspaces: por workspace-id). Log de conflictos para medir frecuencia real.

**F2 — Canal cross-tab unificado (1-2 días):** `lib/crossTab.ts` con
`BroadcastChannel('tradeul')` + fallback `storage`. Mensajes tipados
`{domain, payload, sourceTabId}`. Migrar ahí: tema (generaliza el puente de hoy
en `ThemeSync`), idioma, colores, columnas. Regla por dominio: config → adoptar
en caliente; documento → NO adoptar (ver F3); efímero → ni viaja.
Reclasificar de paso las claves per-tab que hoy van a localStorage (anchos,
ejes) → sessionStorage.

**F3 — Un solo escritor (día):** líder con Web Locks (fallback: heartbeat en
localStorage). Solo el líder hace beacon y sync periódico. Aviso estilo
TradingView cuando el MISMO workspace está activo en dos pestañas: banner
"este workspace está abierto en otra pestaña — los cambios de layout aquí no se
guardarán" (autosave off en la segunda). Sin merges mágicos de layout.

**F4 — Push del server (opcional, medio día):** evento `prefs_updated` por el
WS/SharedWorker existente → adopción también entre dispositivos. Cierra el
círculo: BroadcastChannel para hermanas, WS para el resto del mundo.

**Recomendación de orden:** F0+F1 primero (matan la pérdida de datos, que es lo
grave); F2 después (mata la incoherencia visual); F3/F4 cuando duelan.

---

## 5. Qué NO hacer

- No añadir sync caliente a los 11 stores indiscriminadamente: notas/workflows
  en dos pestañas son un problema de OWNERSHIP (F3), no de broadcast — adoptar
  en caliente ahí provoca pérdidas peores que las actuales.
- No meter CRDT/Yjs para layouts: el modelo "un workspace = un dueño a la vez +
  aviso" (TradingView) cubre el caso real con 1% del coste.
- No confiar en `storage` events como canal primario (no disparan en la pestaña
  escritora, serializan JSON completo por escritura de zustand, y ya vimos hoy
  lo frágil que es tener UNA clave sincronizada y las demás no).
