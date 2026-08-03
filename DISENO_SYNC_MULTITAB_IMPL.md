# Sync multi-pestaña — blueprint de implementación: QUITAR / PONER

Fecha: 2026-08-03. Segunda parte de `DISENO_SYNC_MULTITAB.md` (el análisis medido).
Objetivo: código limpio, bien repartido, escalable e identificable. Todo lo de
abajo está anclado a rutas y líneas reales medidas hoy.

---

## 0. Principios de diseño (los que hoy se violan)

1. **Una fuente de verdad por dato.** Hoy el tema vive en 2 sitios
   (`tradeul-user-preferences` + clave `theme` de next-themes), el layout en 2
   (`workspaces[]` + `windowLayouts` legacy).
2. **El store no hace red.** Hoy `useUserPreferencesStore.ts` tiene ~200 líneas
   de `fetch` dentro (`loadFromBackend`, `syncWorkspacesToBackend`).
3. **Un solo camino de escritura por recurso.** Hoy hay 2 debounces de 3 s
   independientes hacia el mismo PATCH (`useWorkspaceSync.ts:17` y
   `useWorkspaces.ts:31`), y el hook de sync se instancia en 4 componentes
   (workspace/page, AppShell, SettingsWindow, SettingsContent) — múltiples
   timers y efectos por pestaña para el mismo trabajo.
4. **Todo estado del cliente está clasificado y registrado.** Hoy hay ~25
   claves/familias de localStorage sin dueño ni política declarada.
5. **Los módulos se nombran por responsabilidad** y viven juntos
   (`lib/client-state/`), no repartidos entre stores/hooks/providers ad hoc.

---

## 1. QUITAR (inventario exacto)

| # | Qué muere | Dónde está hoy | Por qué | Fase |
|---|-----------|----------------|---------|------|
| Q1 | **next-themes** (dep completa) | `package.json:47`, importada SOLO en `components/settings/ThemeProvider.tsx`; clave localStorage `theme` | Es la segunda fuente de verdad del tema y la causa estructural del bug "botón Dark + UI light". Su única función real (clase en `<html>` + color-scheme + matchMedia para system) son ~50 líneas propias | PR3 |
| Q2 | **`ThemeSync` entero**, incluido el puente `lastStoreSchemeRef` añadido hoy | `components/settings/ThemeProvider.tsx` | Era un parche para reconciliar las dos fuentes. Con una sola fuente no hay nada que reconciliar | PR3 |
| Q3 | **`loadFromBackend` + `syncWorkspacesToBackend` dentro del store** | `stores/useUserPreferencesStore.ts` (~línea 380-540) | Red dentro del store = irrepartible e intesteable. Van a `lib/client-state/prefsSyncClient.ts` | PR1 |
| Q4 | **El debounce duplicado** | `hooks/useWorkspaces.ts` `scheduleSyncToBackend` (SYNC_DEBOUNCE_MS=3000) duplica `hooks/useWorkspaceSync.ts` (PREFS_SYNC_DEBOUNCE_MS=3000) | Dos timers que pueden disparar ambos con estados distintos de la misma pestaña | PR1 |
| Q5 | **Instancias múltiples del hook de sync** (4 call sites: `app/(dashboard)/workspace/page.tsx`, `components/layout/AppShell.tsx`, `components/settings/SettingsWindow.tsx`, `components/settings/SettingsContent.tsx`) | — | Una pestaña = UN sincronizador. Pasa a un provider único; los componentes consumen `{forceSync, lastSyncedAt}` de contexto | PR1 |
| Q6 | **`beforeunload` beacon incondicional** | `hooks/useWorkspaceSync.ts:130-155` | Dispara en cada F5 con el estado COMPLETO y corre carreras contra el GET de la carga siguiente. Sustituido por dirty-flag + `visibilitychange` (y solo el líder en PR5) | PR1 |
| Q7 | **Camino legacy de layouts**: `windowLayouts`, `saveWindowLayouts`, `clearWindowLayouts`, `layoutInitialized` (parcial), `migrateToWorkspaces`, y `hooks/useLayoutPersistence.ts` entero + su uso en SettingsContent ("Save layout") | store + hook | Segundo camino de guardado que además REGENERA los IDs (`${title}-${index}-${Date.now()}`) perdiendo `componentState`. El único camino queda `workspaces[].windowLayouts` vía `useWorkspaces` | PR6 (con sunset de migración: 1 release manteniendo `migrateToWorkspaces` en lectura) |
| Q8 | **Clave `theme` de next-themes en el head script** | `app/layout.tsx:87` (la línea `localStorage.setItem('theme', raw)` añadida hoy) | Con Q1 muere la clave entera; el script queda leyendo solo `tradeul-user-preferences` | PR3 |
| Q9 | **Claves per-tab en localStorage compartido** (ver tabla §3): `scatter-axes`, anchos de paneles (AIAgent `PIPELINE_W_KEY`, backtest `ui.tsx:448`), `chart-toolbar-last` | componentes varios | Estado efímero de UNA pestaña contaminando a las demás en el próximo arranque. → sessionStorage vía `registry.ts` | PR4 |
| Q10 | **`getSavedLanguage()` sin usos** y símbolos muertos que aparezcan al mover Q3 | `lib/i18n.ts:70` | Higiene | PR6 |

**Qué NO se toca:** el SharedWorker del WS de mercado (8 ficheros — es el modelo
a seguir), los stores de dominio (news, tickers, eventos…) salvo registrarlos,
TVC/charting, `ChunkLoadErrorHandler` (sessionStorage correcto).

---

## 2. PONER (módulos nuevos y contratos)

Nueva carpeta **`lib/client-state/`** — todo el estado-de-cliente en un sitio:

### 2.1 `registry.ts` — el mapa que hace el sistema IDENTIFICABLE
```ts
export type StateScope = 'shared-config' | 'document' | 'per-tab';
export interface StateKey {
  key: string;                 // clave física
  scope: StateScope;
  crossTab: 'adopt' | 'none';  // ¿se adopta en caliente al cambiar en otra pestaña?
  syncsToBackend: boolean;
}
export const STATE_REGISTRY: StateKey[] = [ /* las ~25 claves, declaradas */ ];
```
Toda clave nueva se declara aquí o el helper de persistencia lanza en dev.

### 2.2 `crossTab.ts` — un solo canal entre pestañas
```ts
export const TAB_ID: string;                          // nanoid por pestaña
export type CrossTabDomain = 'theme' | 'language' | 'colors' | 'columns'
  | 'workspace-active' | 'prefs-updated';
export function publish<T>(domain: CrossTabDomain, payload: T): void;
export function subscribe<T>(domain: CrossTabDomain, cb: (p: T, from: string) => void): () => void;
```
`BroadcastChannel('tradeul-v1')` + fallback al evento `storage` (una clave
efímera `tradeul-bus`). Ignora mensajes con `from === TAB_ID`.

### 2.3 `theme.ts` — el tema sin dependencias (sustituye next-themes)
```ts
export type ColorScheme = 'light' | 'dark' | 'system';
export function applyTheme(scheme: ColorScheme, colors: ColorPreferences): void;
  // resuelve system con matchMedia, pone/quita clase 'dark' y color-scheme,
  // aplica el background custom (regla actual: en dark se ignora solo #ffffff)
export function watchSystemScheme(cb: () => void): () => void;  // matchMedia listener
```
Un suscriptor del store llama `applyTheme` en cada cambio; `crossTab` publica
`theme` y las hermanas adoptan vía `setColorScheme` (el botón de Settings
siempre acompaña — invariante del incidente de hoy).

### 2.4 `prefsSyncClient.ts` — la red, fuera del store
```ts
export type PrefsDomain = 'workspaces' | 'theme' | 'colors' | 'columns' | 'activeWorkspace';
export function markDirty(domain: PrefsDomain): void;   // programa debounce 3s
export async function flush(reason: 'debounce'|'hide'|'manual'): Promise<void>;
  // PATCH SOLO con los dominios dirty + baseUpdatedAt; 409 → refetchAndReapply()
export async function initialLoad(): Promise<void>;      // GET + retries (migra la lógica actual)
```
Estado interno: `dirtySet`, `baseUpdatedAt` (del último GET/PATCH OK).
`visibilitychange → hidden` ⇒ `flush('hide')` con `sendBeacon` SOLO si hay dirty.

### 2.5 `leader.ts` (PR5)
```ts
export function runAsLeader(task: () => void | (() => void)): () => void;
  // navigator.locks.request('tradeul-leader', ...) — fallback heartbeat localStorage
export function isWorkspaceOpenElsewhere(wsId: string): Promise<boolean>;
```
Usos: flush periódico/beacon solo en el líder; banner "este workspace está
abierto en otra pestaña — el autosave de layout queda desactivado aquí"
(modelo TradingView: ownership, no merge).

### 2.6 `components/providers/ClientStateProvider.tsx`
Única instancia por pestaña (montada en AppShell): rehydrate del store →
suscripción theme → puentes crossTab → `initialLoad()` → dirty-watchers.
Sustituye a las 4 instancias de `useWorkspaceSync` (Q5); `SettingsContent`
consume `forceSync`/`lastSyncedAt` desde su contexto.

### 2.7 Backend (`services/api_gateway/routes/user_prefs.py`)
- PATCH acepta **payload parcial** (ya casi: el COALESCE existe — solo hay que
  dejar de mandar todo desde el cliente) + `workspaces` pasa a ser opcional
  (`COALESCE` también, hoy es reemplazo incondicional).
- **Versionado optimista**: body lleva `baseUpdatedAt`; el UPDATE añade
  `WHERE user_preferences.updated_at <= $base::timestamptz` (tolerancia 0);
  0 filas ⇒ `409 {current: <estado completo>, updatedAt}`. Cliente: refetch +
  re-aplicar SOLO sus dominios dirty y reintentar una vez.
- `activeWorkspaceId`: opcional en el body; solo se persiste si viene
  (el cliente lo envía únicamente en la acción "cambiar de workspace").

---

## 3. Registro de claves (clasificación completa de lo medido)

| Clave / familia | Hoy | Scope objetivo | crossTab | Backend |
|---|---|---|---|---|
| `tradeul-user-preferences` (tema, colores, fuente, tz, workspaces, columnas) | localStorage, sin sync | shared-config + document (workspaces) | adopt (config) / none (workspaces → ownership PR5) | sí (parcial+versión) |
| `tradeul-language` | localStorage | shared-config | adopt | no (candidato a sí, F4) |
| `theme` (next-themes) | localStorage | **MUERE (Q1)** | — | — |
| `tradeul-event-filters`, `news-global-filters`, `tradeul-alert-presets`, `catalyst-alerts-storage` | localStorage | shared-config | adopt (barato: son filtros) | no |
| `tradeul-notes-storage` | localStorage | document | none + aviso ownership (PR5) | no (ya tiene su backend aparte — verificar antes de tocar) |
| `tradeul-workflow-v2`, `tradeul-chat` | localStorage | document | none | parcial (chat ya vive en Postgres) |
| `tickers-store`, `news-tickers-store`, `news-store` | localStorage | shared-config (listas) | adopt | no |
| Columnas por tabla (prefijos scanner/CategoryTableV2/screener) | localStorage | shared-config | adopt (vía `columns`) | ya viaja en preferences |
| `scatter-axes`, `chart-toolbar-last`, `chart-indicator-settings` | localStorage | **per-tab → sessionStorage** (axes/toolbar) — `chart-indicator-settings` revisar: si es config de indicadores, shared-config | none | no |
| Anchos de panel (AIAgent `PIPELINE_W_KEY`, backtest `ui.tsx`) | localStorage | per-tab → sessionStorage | none | no |
| Pinned commands (`hooks/usePinnedCommands.ts`) | localStorage | shared-config | adopt | candidato F4 |
| Chart drawings (`useChartDrawings.ts`, 2 claves) | localStorage | document | none | candidato futuro |
| Market pulse presets (`MarketPulse.tsx LS_KEY`) | localStorage | shared-config | adopt | no |
| `lastChunkErrorReload` | sessionStorage | per-tab ✓ | none | no |

(Decisiones marcadas "revisar" se validan leyendo el componente antes del PR4.)

---

## 4. Flujos resultantes (invariantes)

1. **Tema con N pestañas**: click Dark → store → `applyTheme` + `publish('theme')`
   + `markDirty('theme')`. Hermanas: `subscribe` → `setColorScheme` → su
   `applyTheme`. Invariante: botón y UI SIEMPRE juntos; un solo PATCH (el de la
   pestaña que cambió).
2. **Layout con el mismo workspace en 2 pestañas**: la segunda detecta
   (`isWorkspaceOpenElsewhere`) → banner + autosave off. Sin pérdida silenciosa.
3. **F5**: `visibilitychange:hidden` → flush SOLO si dirty (beacon parcial) →
   el GET de la carga nueva llega después de un estado consistente o, si el
   beacon aterriza tarde, el versionado lo convierte en 409 inofensivo (su
   baseUpdatedAt es viejo) en vez de pisada.
4. **Conflicto real** (dos dispositivos): 409 → refetch → re-aplicar dominios
   dirty → retry. Log `prefs_conflict` para medir frecuencia.

---

## 5. Orden de ejecución (PRs pequeños, cada uno deployable y probable)

| PR | Contenido | Quitar | Poner | Riesgo |
|----|-----------|--------|-------|--------|
| PR1 | Sync unificado: `prefsSyncClient.ts` + `ClientStateProvider` + payloads parciales + dirty + beacon condicional + activeWorkspaceId solo en switch | Q3,Q4,Q5,Q6 | §2.4, §2.6 | Medio (toca el guardado — probar layouts a fondo) |
| PR2 | Versionado optimista extremo a extremo. **+ hallazgo post-PR1 (visto en Network durante la verificación): `useCatalystAlertsStore` y `useNewsFiltersStore` hacen PUT propios a `/user/preferences` (2 PUT por carga); el de news-filters es un read-modify-write de `savedFilters` — carrera entre pestañas de libro. Migrarlos como dominios `newsAlerts`/`savedFilters` del prefsSyncClient** | PUTs ad hoc de 2 stores | §2.7 + 2 dominios nuevos | Bajo (10 líneas SQL + handler 409) |
| PR3 | Tema sin next-themes + crossTab | Q1,Q2,Q8 | §2.2, §2.3 | Medio (FOUC — el head script ya cubre) |
| PR4 | Registro de claves + reclasificar per-tab | Q9 | §2.1 | Bajo |
| PR5 | Líder + ownership de workspace | — | §2.5 | Bajo |
| PR6 | Purga legacy layouts + huérfanos | Q7,Q10 | — | Bajo (tras 1 release de sunset) |

Regla del proyecto: cada PR se despliega con fast-deploy, lo pruebas, y solo
entonces se commitea y se pasa al siguiente.

## 6. Métricas de éxito
- 0 escrituras del PATCH con dominios no-dirty (log backend).
- Contador `prefs_conflict` (409) visible — hoy los conflictos existen y son
  invisibles; después existen y se ven.
- `grep -c "localStorage.setItem"` fuera de `lib/client-state/` y stores → 0
  al final de PR4.
- El incidente de hoy (botón/UI divergentes) imposible por construcción: una
  sola clave de tema en todo el sistema.
