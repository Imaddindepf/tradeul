# Tradeul Replay — demo local

Un **solo reloj** moviendo gráfico + Level 2 + Time & Sales, con la **Charting
Library de TradingView** (CL v31, la misma del TC de producción) en modo replay.

La CL **no trae replay** — eso es una función de tradingview.com, montada sobre
sesiones de servidor que la librería licenciada no expone. Aquí está hecho por
ingeniería inversa: la librería cree que está viendo el mercado en directo.

## Arrancar

```bash
python3 /Users/imaddinamsif/real_time_twitter/replay_demo/server.py 8791
```

Y abrir **http://localhost:8791** (o `preview_start` con el perfil `replay-demo`).

Selector **Motor**: `Lienzo` (canvas propio, ligero) o `TradingView CL` (la real).

## Guardia de gasto

Por defecto la demo **no puede facturar**. Databento cobra cada petición nueva,
así que `spend=0` sirve solo lo que ya está en `l2demo/.cache/`; lo que falte
vuelve vacío y se lista en el aviso (`misses`). Para descargar ventanas nuevas
hay que marcar **"permitir compras"** a mano.

El desplegable **"En caché"** lista las ventanas ya pagadas. La buena:
**NVDA · 2026-07-01 · 09:35 · 5 min**, que encadena con la de 09:40 → 10 minutos
seguidos gratis.

## Cómo funciona el replay en la CL

Cuatro piezas, y las cuatro importan:

1. **`getBars` sirve historia solo hasta `Clock.t`.** Para la librería, el pasado
   del replay es "toda la historia que existe". No hay futuro que pueda filtrarse.
2. **`subscribeBars` recibe cada trade reproducido.** La vela viva se forma dentro
   de la CL exactamente igual que con el mercado real. Al cruzar frontera de vela
   se **sella la anterior** antes de abrir la nueva: a alta velocidad puede haber
   varias fronteras en un frame y si solo se emitiera la última quedarían huecos.
3. **Seek = `onResetCacheNeeded()` + `resetData()`.** La CL vuelve a pedir `getBars`,
   que sirve otra vez recortado al nuevo instante. **Nunca** se le mandan ticks
   hacia atrás: eso provoca "time violation" y deja el gráfico corrupto.
4. **`setVisibleRange` al reloj del replay.** La CL asume que "ahora" es el reloj
   de pared real y deja el viewport en el presente mientras las velas viven en el
   pasado — se ve un gráfico en blanco con la leyenda llena. Se recoloca tras el
   primer `getBars`, no antes (sin velas no hay nada que encuadrar).

Conflación: un solo `onTick` por frame, no uno por print.

## Verificado (medido, no supuesto)

| Prueba | Resultado |
|---|---|
| Reloj a 1x (motor CL) | ratio sim/real **0,9997** |
| Reloj a 1x / 5x (lienzo) | **0,9994** / **4,994** |
| Emisión de cinta | error medio **12,3 ms** por print |
| Seek atrás a 09:35:30 | **30 velas**, última 09:35:29, corte exacto; vela viva reseteada |
| Consola de la CL | **0 errores**, 0 violaciones de tiempo |
| Encadenado 09:35 → 09:45 | sin costura, desde caché, **0 $** |

## Trampas (valen para el port a producción)

- **La CL no pinta con la pestaña en segundo plano.** Llegan los datos, se
  actualiza la leyenda, pero 0 frames. Un gráfico "en blanco" en una captura
  automatizada casi siempre es esto, no un bug.
- **rAF y los timers de página se estrangulan en segundo plano** (hasta 1/min).
  Por eso el reloj va **anclado a la pared** (`t = anclaSim + (pared − ancla) × vel`)
  y lo despierta un **metrónomo en Web Worker**, cuyos timers no se recortan.
- Solo la cadena rAF vigente se re-encola (token): si el metrónomo también
  encolara, cada rescate apilaría un bucle más.
- El servidor re-parsea los CSV en cada carga (~20-40 s de Python que ahogan el
  GIL). Para producción: cachear el payload ya montado.

## Ficheros

- `server.py` — importa el backend del `l2demo` sin tocarlo y añade la guardia de
  gasto, `/api/cached`, `/api/cache_windows` y los estáticos de `/vendor`.
- `index.html` — todo el frontend: reloj, libro, cinta, chart de lienzo y datafeed
  de replay para la CL.
- `vendor/charting_library/` — copia local de la CL v31 (26 MB, desde
  `/opt/tradeul/frontend/public/`). **No commitear**: es software licenciado.

---

## Nota de repositorio

Esto es un **prototipo verificado**, no codigo de produccion. Se sube como
referencia de la integracion en `feature/replay-pro`.

- `vendor/charting_library/` **no esta**: es software licenciado de TradingView.
  El repo ya tiene su copia en `frontend/public/charting_library/`.
- `server.py` importa el backend de `l2demo/` por `importlib`, que vive fuera
  del repo. En produccion ese papel lo hace `services/api_gateway/l2replay_core.py`.
- La cache de Databento se queda en local y esta en `.gitignore`.

Lo que hay aqui y **todavia no en produccion**: el reloj anclado a pared con
metronomo en Worker, la precarga por colchon real, el datafeed de replay para
la Charting Library, y el pasado con `ohlcv-1s` de XNAS.BASIC.
