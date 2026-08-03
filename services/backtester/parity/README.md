# Fixtures de paridad del matcher

Especificación ejecutable del matcher vivo (`eventPassesSubscription` del
websocket_server), congelada desde producción. Es el paso 1 de la Fase 1 del
diseño (`DISENO_BACKTESTER_PROFESIONAL.md` §8.1): los fixtures se construyen
**antes** que el matcher portado, y el port deberá reproducir estos veredictos
al 100% en CI.

## Pipeline (3 pasos, re-ejecutable cualquier día de mercado)

```bash
cd /opt/tradeul/services/backtester/parity
DT=$(date +%F)
mkdir -p fixtures/$DT

# 1. Dump crudo del stream de alertas (strings wire exactos, incluye quality)
docker exec -i tradeul_alert_worker_0 python3 - < extract_stream_events.py \
  > fixtures/$DT/stream_events.jsonl

# 2. Casos estratificados: 109 estrategias reales × eventos reales + sintéticos
python3 build_fixture_inputs.py fixtures/$DT/stream_events.jsonl fixtures/$DT/inputs.jsonl

# 3. Veredictos del código VIVO (extraído de index.js en runtime, no copiado)
node freeze_matcher_verdicts.js fixtures/$DT/inputs.jsonl \
  fixtures/$DT/fixtures.jsonl fixtures/$DT/meta.json
```

## Qué congela cada caso

- `event_fields`: el dict crudo del stream (lo que el ws parsea de verdad).
- `enriched`: el `context` de `market_events` — el enriched del símbolo en el
  instante del disparo (sustituto fiel del enrichedCache, borrosidad ≤30 s).
- `sub_data`: `{event_types, ...filters}` tal cual la estrategia BUILD
  (formato legacy `min_/max_` + `aq:` — `buildEventSubscription` lo acepta).
- `verdict`: lo que el matcher vivo decidió con ese trío exacto.

Orígenes: `real` (estrategia × tipo suscrito), `real_negative_type` (debe
rechazar por tipo — 0% pass esperado), `real_aq_spectrum` (quality bajo/medio/
alto para estrategias con `aq:`), `synthetic` (mutaciones etiquetadas que
fuerzan las semánticas raras: rango invertido, modo estricto con valor
ausente, `aq:` ± en torno a la quality real).

## Garantías

- **Cero reimplementación**: `freeze_matcher_verdicts.js` extrae las regiones
  de `index.js` por marcadores y las ejecuta en un sandbox `vm` con
  `enrichedCache` controlado. Si el fuente cambia de forma que los marcadores
  no casan, el harness revienta en vez de congelar mentiras.
- **Drift detectable**: `meta.json` lleva sha256 del `index.js` completo, de
  las regiones extraídas y del catálogo. Si producción cambia el matcher, los
  fixtures viejos se distinguen por hash.
- **Determinista**: misma entrada ⇒ mismo `fixtures.jsonl` bit a bit
  (verificado por md5 en la primera tanda). El muestreo usa seed fija.

## Tanda 2026-08-02 (primera)

5.003 eventos del stream del 31-07 · 1.113 casos (todos con enriched) ·
149 tipos cubiertos · 380 pasan (34,1%) · negativos 0/327 ✓ ·
`aq_above_fail` 0/12 ✓ · `inverted_range_fail` 0/12 ✓ ·
`strict_missing_value` 0/12 ✓.

## Limitaciones conocidas

- `quality` NO se persiste (la BD y el lake lo descartan en
  `_SKIP_CONTEXT_KEYS` de `services/alert_engine/persistence/__init__.py`):
  los fixtures lo sacan del stream de Redis, que solo retiene ~100k entradas.
  Por eso el paso 1 debe correr el mismo día o el siguiente al de mercado.
- La cobertura de tipos depende de lo que disparó ese día (149/279 en la
  primera tanda). Tandas de días distintos se acumulan en `fixtures/<fecha>/`.

## El port y su paridad (hechos 2026-08-02)

- `services/backtester/matching/matcher.py` — port 1:1 con semántica JS exacta
  (parseFloat/parseInt de prefijo, coerción Number() en comparaciones, NaN,
  falsy de ''). Lee el MISMO `event_filter_catalog.json` que el websocket.
- `services/backtester/matching/matcher_defs_generated.py` — las 244
  comprobaciones + listas ENRICHED_* + defs de índice, GENERADAS desde
  `index.js` por `scripts/gen_matcher_port_assets.py` (con `--check`).
- `check_matcher_parity.py` — corre el port sobre cada tanda y exige veredicto
  idéntico. Primera pasada: **1.113/1.113 idénticos**. Prueba negativa: un bug
  inyectado en la rama de rango invertido produce exactamente los 6 desajustes
  esperados.
- Integrado como **zona 9** de `scripts/check_event_filter_parity.py`, que ya
  corre como gate del deploy del frontend.

## Siguiente paso (pendiente)

Validación 422 del backtester contra `shared/config/event_catalog.json` +
`/capabilities` con eje temporal + endpoint de análisis de disparos L0
(DuckDB sobre el lake) — resto de la Fase 1 del diseño.
