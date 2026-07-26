# Auditoría de conformidad — TradingView Charting Library v31 vs integración TVC de tradeul

**Fecha:** 2026-07-26 · **Build auditado:** `P2dufljXvFP8fQtF_bCXs` · **Librería:** Advanced Charts v31.0.0 (build 2026-03-05)

**Método:** revisión línea a línea de `frontend/components/tvchart/` (datafeed.ts, TVChartCell.tsx, TVChartContent.tsx y auxiliares) contra la documentación oficial completa (Get started, Datafeed API, Datafeed subscriptions, UDF, Symbology, Sessions, Extended sessions, Datafeed common issues, Widget Constructor, Widget methods, Events, Localization, Accessibility, Shortcuts, Cross-origin, Saving/Loading en sus 3 variantes, Separate drawings, Settings adapter), verificando cada API citada contra el `.d.ts` **local** de la v31 (los docs públicos son de "latest" y difieren) y contra **datos reales** del backend.

**Leyenda:** ✅ conforme · 🔧 no-conformidad corregida en esta auditoría · ⚠️ gap abierto (decisión pendiente) · 💡 oportunidad · ➖ no aplica

---

## 1. Instalación y arranque

| Punto | Estado | Detalle |
|---|---|---|
| Archivos en `/public/charting_library` sin editar, bundles como caja negra | ✅ | Solo lectura; los iconos se EXTRAJERON de los bundles, no se modificaron. |
| Carga vía `charting_library.standalone.js` (IIFE) + script tag | ✅ | `TVChartCell.tsx` — loader único compartido entre celdas con promesa cacheada y reintento tras fallo. |
| Same-origin hosting | ✅ | Servido por el propio Next (`/charting_library/`); CORS no aplica. `library_path` con barra final ✅. |

## 2. Datafeed API — métodos requeridos

### onReady
- ✅ Callback asíncrono vía `setTimeout` (requisito explícito).
- ✅ `supported_resolutions` coherente con el resto del datafeed.
- ✅ `supports_marks/timescale_marks/time: false` — coherente: no implementamos `getMarks`/`getServerTime` (aún).
- 💡 `exchanges: []` y `symbols_types: []` → el buscador no ofrece filtros por exchange/tipo. El backend de metadata tiene ambos; rellenarlos es barato.

### searchSymbols
- ✅ Fetch asíncrono; error → `onResult([])` (lo que pide el contrato).
- 💡 `searchSymbolsPaginated` existe en v31: resultados por páginas al hacer scroll. Con miles de tickers US es la variante recomendada por los docs.
- 💡 `symbol_search_request_delay` (constructor) para reducir carga del backend al teclear.

### resolveSymbol
- ✅ `ticker === name` → una sola resolución por símbolo (comportamiento documentado de doble resolución evitado).
- ✅ `timezone: America/New_York` (zona del exchange, no del usuario) — crítico para no desplazar barras.
- ✅ `session: 0930-1600` + sesiones extendidas completas (ver §4).
- ✅ pricescale decimal según contrato (10^n; minmov 1) con ajuste small-caps vía snapshot.
- ✅ `data_status: 'streaming'`, `format: 'price'`, `volume_precision: 0`.
- ✅ Error → `onError('unknown_symbol')` → icono nativo de símbolo inválido (no activamos `hide_image_invalid_symbol`).
- ✅ `visible_plots_set` sin definir = ohlcv (tenemos OHLCV completo).
- 💡 `variable_tick_size` (existe en v31): small caps que cruzan $1 intradía hoy mantienen el pricescale resuelto al cargar; con esta prop el tick se adapta por precio sin re-resolver.
- 💡 `additional_symbol_info_fields`: el diálogo Security Info puede mostrar campos nuestros (sector, industria, float…) — la metadata ya los tiene.

### getBars
- ✅ **countBack correctamente priorizado**: `limit = clamp(countBack, 100, 5000)` + `before` → devolvemos siempre N barras hacia atrás, que es exactamente la recomendación para evitar el problema "getBars is called multiple times".
- ✅ `before` verificado **exclusivo** en el backend (`bar_time >= before` se excluye; filtro `b["time"] < before`) → sin barra duplicada en el límite → sin "data must have unique times".
- ✅ Orden ascendente garantizado (sort defensivo).
- ✅ `noData: true` cuando el histórico se agota (`has_more !== true`) → sin peticiones infinitas.
- ✅ La librería puede mutar los `Bar` → entregamos SIEMPRE objetos nuevos (`toTVBar`).
- ✅ Callbacks asíncronos (fetch).
- 🔧 **Velas diarias/semanales/mensuales**: el backend las sirve a medianoche ET (04:00/05:00 UTC) y el contrato exige **00:00:00 UTC del día de trading**. Sin corregir, la CL "desplaza" la hora en velas normales y **corrompe Heikin Ashi/Renko** (sección "Japanese charts show incorrect time"). Corregido: `toTVBar(bar, dailyOrAbove)` normaliza SOLO en la frontera hacia la librería (histórico + los 2 caminos realtime); el estado interno de agregación (`lastBar`, `lastHistoryBars`) permanece en base backend para no romper el merge de sealed bars.
- Menor (edge): el contrato pide "return at least two bars"; un símbolo con 1 sola vela histórica (IPO en 1D) la pasaría tal cual. Riesgo mínimo, documentado.

### subscribeBars / unsubscribeBars / suscripciones
- ✅ Una suscripción por `listenerGuid`, ruteo por símbolo, estado independiente por guid (requisito "handle each subscriberUID independently").
- ✅ Solo se actualiza la última vela o se añade una nueva; el merge de sealed exige `time` idéntico → sin `putToCacheNewBar: time violation`.
- ✅ Vela realtime con `time` = inicio del bucket (no la hora del update) — vía `lib/barAggregation`.
- ✅ Reemplazo completo OHLCV de la vela (la CL no acepta deltas) — `applyAggregate` emite velas completas.
- ✅ Unsubscribe diferido (~5 s) de la CL soportado: seguimos emitiendo hasta el `unsubscribeBars` explícito de ese guid.
- ✅ Cambio de resolución (subscribe nuevo + unsubscribe viejo solapados sobre el mismo símbolo): con el refcount global (`lib/chartStreams`) el servidor ni se entera — cero churn.
- ✅ Hueco detectado en el stream → `onResetCacheNeeded()` → la CL re-pide histórico (patrón documentado).
- ✅ Reconexión del WS → `resubscribeAllStreams` (coalescido) re-emite las suscripciones vivas.
- 💡 "Internet connection issues": los docs recomiendan `resetCache()` + `chart().resetData()` tras recuperar conexión. Hoy dependemos del gap-backfill (que llega con el primer aggregate); un `resetData()` explícito al reconectar cerraría el hueco también en símbolos poco líquidos y en diarios.

## 3. Resoluciones

- ✅ `supported_resolutions` = 13 resoluciones de 1m a 12M, seleccionables en UI.
- 🔧 **Anclaje de 1h/4h/12h**: el backend ancla a :00, pero con sesión regular `0930-1600` la CL espera velas 09:30/10:30… (caso literal de "Library shifts bar time"). Corregido con el mecanismo documentado de **resolution rebuilding**: `intraday_multipliers: ['1','2','5','15','30']` — la CL construye 60/240/720 desde 30m con el anclaje correcto para la sesión activa (regular o extendida). Consecuencia técnica: para charts de 1h+, `getBars`/`subscribeBars` llegan ahora con resolution '30'.
- ✅ `daily/weekly/monthly_multipliers` coinciden con lo que el backend sirve (1day/1week/1month/3month/1year).
- ➖ Segundos y ticks: `has_seconds`/`has_ticks` no declarados (no hay fuente de segundos en el backend hoy; "velas de segundos desde tape" está en el roadmap propio — cuando exista, activar `seconds_resolution` + `has_seconds` + `seconds_multipliers`).

## 4. Sesiones y horario extendido

- ✅ Formato de sesión válido (`0930-1600`; extendida `0400-2000`), zona ET.
- ✅ Extendidas al completo según el artículo: featureset `pre_post_market_sessions` + `subsessions` (4 entradas exactas del ejemplo oficial) + `subsession_id`.
- ✅ **Handle session switch**: la CL re-resuelve con `extension.session` y devolvemos `session`+`subsession_id` actualizados. El invariante oficial `symbolInfo.session === subsessions.find(x => x.id === subsession_id).session` se cumple SIEMPRE por construcción.
- ⚠️ `session_holidays` y `corrections` no se proveen: los medios días (3 jul, día tras Acción de Gracias, 24 dic) pintan sombreado y status de mercado incorrectos, y el artículo avisa de que sesiones mal declaradas provocan cálculos de rango erróneos (nuestro getBars por countBack nos protege del efecto en datos, pero no del visual). El backend tiene calendario de mercado → rellenable.
- ➖ Pre/post price line (`rtc` en quotes): Trading Platform only.

## 5. Widget Constructor — barrido parámetro a parámetro

**Configurados y conformes:** `container`, `library_path`, `symbol`, `interval`, `datafeed`, `locale` (es/en, ambos soportados), `theme` + `overrides` de fondo, `loading_screen`, `autosize`, `timezone`, `auto_save_delay: 1`, `saved_data` (restore), `disabled_features` (header_widget, left_toolbar, timeframes_toolbar, header_saveload, use_localstorage_for_settings, save_chart_properties_to_local_storage, popup_hints, symbol_search_hot_key, widget_logo, library_branding), `enabled_features` (items_favoriting, library_custom_no_powered_branding, pre_post_market_sessions).

**Gaps y oportunidades (todo verificado presente en el .d.ts v31):**

| Parámetro | Estado | Nota |
|---|---|---|
| `settings_adapter` | ⚠️ **GAP #1** | Desactivamos localStorage (correcto para independencia por ventana) pero sin adapter a cambio: **favoritos (`items_favoriting`) y preferencias de diálogos se pierden en cada montaje**. Los docs son explícitos: settings de usuario separados del layout. Implementar adapter respaldado en preferencias por usuario, compartido entre celdas. |
| `timeframes_toolbar` | ⚠️ decisión | tradingview.com multichart SÍ muestra la barra inferior POR CHART (rangos 1D…5y, reloj/TZ, RTH/ETH, log/auto). La quitamos por diseño headless. Recomendación: reactivarla para paridad. |
| `favorites` | 💡 | Permite pre-sembrar favoritos por constructor; complementa (no sustituye) al settings_adapter. |
| `custom_css_url` / `custom_font_family` | 💡 | Branding dentro de los iframes (tipografía tradeul, scrollbars). |
| `custom_themes` / `changeTheme` | 💡 | Paleta exacta tradeul; cambio de tema en caliente sin remontar celdas. |
| `custom_formatters` / `numeric_formatting` | 💡 | Formato de fecha/números es-ES. |
| `context_menu` | 💡 | Menú contextual del chart con acciones tradeul (p. ej. "Abrir T&S", "Añadir a scanner"). |
| `compare_symbols` | 💡 | Lista curada para el diálogo Compare (SPY/QQQ/sector ETFs). |
| `studies_overrides` | 💡 | Colores de indicadores por defecto a paleta tradeul. |
| `custom_indicators_getter` | 💡 (fase) | Indicadores propios (RVOL, ASI del chart legacy) como estudios nativos de la CL. |
| `study_count_limit` | 💡 | Límite razonable (p. ej. 25) protege layouts de 16 celdas. |
| `snapshot_url` | ➖ | Usamos `takeClientScreenshot` (cliente) — patrón documentado y suficiente. |
| `debug` | 💡 dev | Activarlo condicionalmente en desarrollo: los logs `FEED [SYM|RES]` son la herramienta oficial de diagnóstico del datafeed. |
| `charts_storage_url` / `save_load_adapter` / `load_last_chart` | ➖ | Guardado por **low-level API** (ver §7). |
| Trading Platform (`broker_config`, `widgetbar`, `rss_news_feed`…) | ➖ | Advanced Charts; no existen aquí. |

## 6. Widget methods y eventos

- ✅ `onChartReady`: correcto **en v31** (`chartReady()` como promesa no existe en nuestro .d.ts; la deprecación es de "latest" — revisar al actualizar la librería).
- ✅ `activeChart()` (no el deprecado `widget.setSymbol`), `executeActionById`, `selectLineTool`, `magnetEnabled/magnetMode`, `lockAllDrawingTools`, `hideAllDrawingTools`, `undo/redo`, `takeClientScreenshot` (snippet oficial), `getLineToolsState`/`applyLineToolsState`.
- ✅ Eventos: `onAutoSaveNeeded`, `mouse_down`, `drawing_event`, `onSymbolChanged`, `onIntervalChanged` — con guards anti-eco para el sync (patrón correcto).
- ✅ Al ser una CL (un chart por widget), no nos afecta la advertencia de resuscripción en layouts múltiples nativos.
- ➖ Sync de retícula entre celdas: `crossHairMoved` SÍ existe en v31 (escuchar), pero `setCrosshairPosition`/`clearCrosshairPosition` **no existen** en v31 → seguir marcándolo "requiere actualización de librería", no es deuda nuestra.
- 💡 `closePopupsAndDialogs()`: integrable con el coordinador de popovers (cerrar diálogos nativos de la CL al abrir menús nuestros).

## 7. Guardado y carga

- ✅ **Low-level API** (`widget.save()` → `saved_data`): exactamente el enfoque que los docs recomiendan "cuando quieres UI de guardado propia" — nuestro gestor de diseños. Persistencia en Postgres vía `/api/v1/tv-designs`.
- ✅ `use_localstorage_for_settings` y `save_chart_properties_to_local_storage` desactivados (independencia por ventana) — coherente con el enfoque, PERO exige el settings_adapter del §5.
- ⚠️ Limitación documentada del low-level: **no soporta chart templates** (plantillas de estilo tipo "Guardar plantilla de gráfico" de TV). Si las queremos, la vía es `save_load_adapter` (IExternalSaveLoadAdapter) conviviendo con lo nuestro.
- 💡 **Plantillas de indicadores**: `createStudyTemplate`/`applyStudyTemplate` (low-level, disponible) → menú "Plantillas" como TV con nuestro propio storage.
- 💡 **`saveload_separate_drawings_storage`** (disponible en v31, incl. `saveLineToolsAndGroups`): dibujos **por símbolo y globales entre layouts** — el "New drawings sync globally" real de TV, con semántica documentada de `sharingMode` (NotShared/SharedInLayout/GloballyShared), tombstones `null` para borrados y filtrado por `ownerSource` (¡crítico para no reasignar dibujos de panes de indicadores al pane principal!). Nuestro toggle "globo" actual es en-memoria y por ventana; esta es su versión persistente y cross-layout. Requiere endpoints nuevos estilo tv_designs.

## 8. Checklist "Datafeed: common issues" (uno a uno)

| Issue documentado | Estado |
|---|---|
| getBars called multiple times | ✅ evitado (countBack vía limit+before) |
| Bar data is mutable | ✅ copias |
| Requested data outside visible range | ✅ entendido (indicadores) — sin workaround necesario |
| Infinite data requests | ✅ noData correcto |
| Time violation | ✅ guards en sealed/aggregate |
| Maximum call stack size exceeded | ✅ callbacks asíncronos |
| Data must have unique times | ✅ `before` exclusivo verificado en backend |
| Library shifts bar time | 🔧 corregido (diarias 00:00 UTC + rebuilding horario) |
| Internet connection issues (resetCache+resetData) | 💡 pendiente (hoy: gap-backfill al primer aggregate) |
| Quotes/TP delays | ➖ Trading Platform |
| New bar tras cierre | ✅ comportamiento esperado, sin bug |
| Japanese charts incorrect time | 🔧 resuelto por el fix de diarias |
| Indicator not plotted on resolution change | ✅ comportamiento esperado de la CL |

## 9. Localización, accesibilidad, shortcuts

- ✅ Locale es/en con guard y fallback (`en`); RTL no aplica.
- ✅ Atajos nativos ligados al header no disponibles en headless → los re-cableamos vía `executeActionById` (dígito→changeInterval, letra→symbolSearch, ESC, ⌘S) — decisión verificada contra el bundle en su día.
- Nota futura: `onShortcut` con strings ("alt+q") queda deprecado en latest a favor de key codes — nos afectará solo si usamos `onShortcut` al actualizar.
- ➖ `accessible_keyboard_shortcuts`, screen readers: sin trabajo específico (aceptado).

## 10. Lo que NO aplica (Trading Platform)

`getQuotes`/`subscribeQuotes`/`subscribeDepth`, Watchlist, Details, News widget, DOM, Account Manager, Broker API, `widgetbar`, multichart NATIVO (por eso existe nuestra rejilla propia), `build_seconds_from_ticks`. Nuestra suite propia (scanner, T&S, halts, news) cubre ese terreno fuera de la librería.

## 11. Registro de no-conformidades corregidas en esta auditoría

1. **Diarias+ a 00:00 UTC** (datafeed.ts, `toTVBar` con flag `dailyOrAbove` en frontera; internals en base backend).
2. **Anclaje horario por sesión** (datafeed.ts, `intraday_multipliers` sin 60/240/720 → rebuilding oficial de la CL).

Verificación pendiente de mercado abierto (lunes): chart 1h en RTH debe mostrar velas 09:30/10:30…; realtime de 1h ahora se alimenta de la suscripción de 30m.

## 12. Semántica multichart (nuestra rejilla propia vs tradingview.com)

La CL es un chart por widget: NUESTRO multichart son N widgets orquestados. Cada control de la ventana debe declarar su ámbito. Auditado control a control (2026-07-26, build `VyR9hllWZoNShfpSUYS5f`):

| Control | Ámbito correcto (TV.com) | Estado |
|---|---|---|
| Búsqueda de símbolo / Compare / Indicadores / Ajustes | Celda enfocada | ✅ ya correcto |
| Intervalo | Celda enfocada; todas si sync-intervalo ON | ✅ ya correcto |
| Tipo de gráfico | Celda enfocada | ✅ ya correcto |
| **Cámara** | **TODO el layout** (un solo PNG) | 🔧 corregido: `screenshotLayout()` compone los `takeClientScreenshot()` de cada celda según su geometría real (`data-cell-id` + rects, devicePixelRatio), fondo del tema, nombre `tradeul_<símbolos>_<ts>.png` |
| Herramienta de dibujo (armar) | GLOBAL: armada en todas las celdas, se dibuja donde cliques | 🔧 corregido (`forEachCell` en pick/flyouts/regla/zoom-tool/emoji y en ESC→cursor) |
| Imán + modo (débil/fuerte) | GLOBAL del layout | 🔧 corregido |
| Bloquear todos los dibujos | GLOBAL | 🔧 corregido |
| Permanecer en modo dibujo (drawLock) | GLOBAL | 🔧 corregido (toggle sobre todas; celdas nuevas se alinean al ready) |
| Ojo (ocultar dibujos/indicadores) | GLOBAL | 🔧 corregido |
| **Herencia de estado en celdas nuevas** | La celda que nace (cambio de layout, watchdog) hereda imán/candados/ojo/herramienta | 🔧 corregido: `onReady(cellId)` → la barra re-aplica su estado SOLO a esa celda (ops idempotentes; drawLock un exec porque parte de OFF) |
| Zoom out (lupa −) | Celda enfocada | ✅ (TV: actúa sobre el chart activo) |
| Papelera (borrar dibujos/estudios) | Celda enfocada | ✅ (TV: por chart) |
| Globo (sync dibujos mismo símbolo) | Celdas del mismo símbolo | ✅ ya correcto |
| Undo/Redo | TV: pila global del layout | ⚠️ limitación estructural: cada widget CL tiene SU pila; imposible fusionarlas → actúa sobre la celda enfocada. Documentado, no corregible sin multichart nativo (Trading Platform). |
| ⌘S / Guardar diseño | Layout completo | ✅ (flush de todas las celdas) |
| Watchdog / popovers / persistencia | Por celda / ventana | ✅ tandas anteriores |

## 13. Plan priorizado

1. **settings_adapter** (favoritos y prefs de usuario persistentes — el único gap que rompe una feature ya activada).
2. **timeframes_toolbar por celda** (paridad tradingview.com — decisión de producto).
3. **Marks earnings/news** (`supports_marks` + `getMarks`/`getTimescaleMarks` — ya en roadmap).
4. **Dibujos globales por símbolo** (`saveload_separate_drawings_storage` + backend).
5. `resetData()` al reconectar; `session_holidays`/`corrections`; `variable_tick_size`; filtros del buscador (`exchanges`/`symbols_types`); `searchSymbolsPaginated`; plantillas de indicadores; branding del iframe (css/fuente/temas/formatters); `context_menu`; `compare_symbols`; `debug` en dev.
