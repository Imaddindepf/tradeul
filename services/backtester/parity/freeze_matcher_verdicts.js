#!/usr/bin/env node
/**
 * Congela veredictos del matcher VIVO para los fixtures de paridad.
 *
 * No reimplementa nada: extrae del fuente de producción
 * (services/websocket_server/src/index.js) las regiones que forman el pipeline
 * de matching y las ejecuta en un sandbox con enrichedCache controlado:
 *
 *   1. ENRICHED_* defs + enrichEventFromCache + pf/pi/ps + carga del catálogo
 *      + pickWireKey + buildEventSubscription + minutesSinceMarketOpen
 *      + INDEX defs + eventPassesSubscription   (bloque contiguo)
 *   2. el fragmento de broadcastMarketEvent que construye eventPayload
 *      (parseo string→número idéntico al vivo), envuelto en una función
 *
 * Uso:  node freeze_matcher_verdicts.js inputs.jsonl fixtures.jsonl meta.json
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const readline = require('readline');

const ROOT = '/opt/tradeul';
const INDEX_JS = path.join(ROOT, 'services/websocket_server/src/index.js');
const CATALOG = path.join(ROOT, 'shared/config/event_filter_catalog.json');

const [inputsPath, fixturesPath, metaPath] = process.argv.slice(2);
if (!metaPath) {
  console.error('uso: node freeze_matcher_verdicts.js inputs.jsonl fixtures.jsonl meta.json');
  process.exit(2);
}

const src = fs.readFileSync(INDEX_JS, 'utf8');

function cut(startMarker, endMarker, { inclusiveEnd = true, from = 0 } = {}) {
  const a = src.indexOf(startMarker, from);
  if (a < 0) throw new Error(`marker no encontrado: ${startMarker.slice(0, 60)}`);
  const b = src.indexOf(endMarker, a);
  if (b < 0) throw new Error(`end marker no encontrado: ${endMarker.slice(0, 60)}`);
  return src.slice(a, inclusiveEnd ? b + endMarker.length : b);
}

// Bloque contiguo: defs enriched → final de eventPassesSubscription.
const matcherStart = src.indexOf('function eventPassesSubscription');
if (matcherStart < 0) throw new Error('eventPassesSubscription no encontrado');
const matcherEndMarker = '\n  return true;\n}';
const matcherEnd = src.indexOf(matcherEndMarker, matcherStart);
if (matcherEnd < 0) throw new Error('cierre de eventPassesSubscription no encontrado');
const blockStart = src.indexOf('const ENRICHED_FLOAT_FIELDS = [');
if (blockStart < 0 || blockStart > matcherStart) throw new Error('ENRICHED_FLOAT_FIELDS no encontrado antes del matcher');
const mainBlock = src.slice(blockStart, matcherEnd + matcherEndMarker.length);

// Fragmento de broadcastMarketEvent que construye el payload del evento.
const payloadFragment = cut(
  '  // Parse details once (not per client)',
  '  enrichEventFromCache(eventPayload);'
);

const harness = `
${mainBlock}

function buildEventPayload(eventData) {
  const eventType = eventData.event_type;
  const symbol = eventData.symbol;
${payloadFragment}
  return eventPayload;
}

globalThis.__harness = { buildEventPayload, buildEventSubscription, eventPassesSubscription, enrichedCache };
`;

const sandbox = {
  fs, path, console,
  process: { env: { FILTER_CATALOG_PATH: CATALOG } },
  __dirname: path.join(ROOT, 'services/websocket_server/src'),
  logger: { info() {}, warn() {}, error() {}, debug() {} },
  enrichedCache: new Map(),
  Intl, Date, JSON, Math, Object, Array, Set, Map, String, Number, parseFloat, parseInt, isNaN, globalThis: {},
};
vm.createContext(sandbox);
vm.runInContext(harness, sandbox, { filename: 'matcher_harness.js' });
const { buildEventPayload, buildEventSubscription, eventPassesSubscription, enrichedCache } =
  sandbox.globalThis.__harness;

const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');

async function main() {
  const out = fs.createWriteStream(fixturesPath);
  const rl = readline.createInterface({ input: fs.createReadStream(inputsPath), crlfDelay: Infinity });
  let n = 0, passed = 0;
  const byOrigin = {};
  for await (const line of rl) {
    if (!line.trim()) continue;
    const c = JSON.parse(line);
    enrichedCache.clear();
    if (c.enriched) enrichedCache.set(c.event_fields.symbol, c.enriched);
    const payload = buildEventPayload(c.event_fields);
    const sub = buildEventSubscription(c.sub_data);
    const verdict = eventPassesSubscription(payload, sub);
    n++; if (verdict) passed++;
    byOrigin[c.origin] = byOrigin[c.origin] || { total: 0, passed: 0 };
    byOrigin[c.origin].total++; if (verdict) byOrigin[c.origin].passed++;
    out.write(JSON.stringify({
      case_id: c.case_id, origin: c.origin, mutation: c.mutation,
      strategy_id: c.strategy_id, event_type: c.event_fields.event_type,
      symbol: c.event_fields.symbol, quality: payload.quality, verdict,
    }) + '\n');
  }
  await new Promise((res) => out.end(res));

  const meta = {
    generated_by: 'freeze_matcher_verdicts.js',
    source_file: 'services/websocket_server/src/index.js',
    source_sha256: sha(src),
    extracted_regions_sha256: sha(mainBlock + payloadFragment),
    catalog_path: 'shared/config/event_filter_catalog.json',
    catalog_sha256: sha(fs.readFileSync(CATALOG, 'utf8')),
    node_version: process.version,
    cases: n, passed, pass_rate: +(passed / n).toFixed(4),
    by_origin: byOrigin,
  };
  fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2) + '\n');
  console.error(`fixtures: ${n} casos, ${passed} pasan (${(100 * passed / n).toFixed(1)}%)`);
  console.error(JSON.stringify(byOrigin));
}

main();
