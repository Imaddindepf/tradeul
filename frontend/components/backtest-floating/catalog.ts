'use client';

/**
 * Catálogo unificado del Backtester: eventos, filtros e indicadores en una
 * sola lista tipada, cruzada con lo que el motor puede ejecutar de verdad.
 *
 * Antes había tres listas sueltas y tres cajas de scroll de 140px, y el
 * catálogo de alertas (158 eventos) se ofrecía entero aunque el traductor del
 * motor solo registra 73: los otros 85 evaluaban a todo-False sin avisar.
 * Aquí cada entrada lleva su estado de capacidad y la UI lo respeta.
 */

import { useEffect, useMemo, useState } from 'react';
import { ALERT_CATALOG, getAlertsByCategory } from '@/lib/alert-catalog';
import { FILTER_GROUPS } from '@/lib/filter-catalog.generated';

export type Capability = 'ok' | 'degraded' | 'unsupported' | 'unknown';
export type EntryKind = 'event' | 'filter' | 'indicator';

export interface CatalogEntry {
  /** Único en todo el catálogo: `event:gap_reversal`, `filter:rvol`… */
  uid: string;
  kind: EntryKind;
  /** Identificador que viaja al backend. */
  id: string;
  label: string;
  group: string;
  /** Texto extra para buscar (código de alerta, nombre en el otro idioma). */
  alias?: string;
  suffix?: string;
  /** Escalas del catálogo (['','K','M'] / ['K','M','B']): selector de unidad. */
  units?: readonly string[];
  defU?: string;
  capability: Capability;
  /** Por qué está degradado o no soportado. Se muestra tal cual. */
  reason?: string;
}

export interface TriggerSemantics { support: string; note: string }

export interface DataAxisEntry {
  range: { from: string; to: string; days: number } | null;
  semantics: string;
  note: string;
}

export interface Capabilities {
  /** Capacidades del análisis de disparos L0 (vocabulario BUILD completo). */
  trigger_analysis?: {
    engine: string;
    endpoint: string;
    events: { supported: string[]; count: number; note: string };
    filters: {
      all_build_filters_supported: boolean;
      by_semantics: Record<string, string[]>;
      semantics: Record<string, TriggerSemantics>;
    };
  };
  /** Eje temporal medido de cada fuente de datos. */
  data_axis?: Record<string, DataAxisEntry>;
  events: { supported: string[]; degraded: Record<string, string>; count: number };
  filters: { keys: string[]; meta: { min_key: string; max_key: string; column: string; description: string }[]; count: number };
  timeframes: { supported: string[]; resampled: string[] };
  universe_methods: string[];
  exit_types: string[];
  slippage_models: string[];
  limits: { min_days_daily: number; min_days_intraday: number };
}

/* ── Filtros: etiqueta y unidad legibles para las claves del motor ───────
   El motor manda `keys` + `description`; esto solo añade el sufijo y un
   nombre corto. Si aparece una clave nueva, se muestra con su description
   en vez de desaparecer — que es lo que hacía la lista fija de 21. */
const FILTER_META: Record<string, { label: string; suffix?: string; group: string }> = {
  price:            { label: 'Precio', suffix: '$', group: 'Precio' },
  volume:           { label: 'Volumen', group: 'Volumen' },
  rvol:             { label: 'RVOL', suffix: '×', group: 'Volumen' },
  dollar_volume:    { label: 'Volumen en dólares', suffix: '$', group: 'Volumen' },
  avg_volume_5d:    { label: 'Volumen medio 5D', group: 'Volumen' },
  avg_volume_10d:   { label: 'Volumen medio 10D', group: 'Volumen' },
  avg_volume_20d:   { label: 'Volumen medio 20D', group: 'Volumen' },
  change_percent:   { label: 'Cambio', suffix: '%', group: 'Cambio' },
  gap_percent:      { label: 'Gap', suffix: '%', group: 'Cambio' },
  change_from_open: { label: 'Desde la apertura', suffix: '%', group: 'Cambio' },
  range_pct:        { label: 'Rango de la barra', suffix: '%', group: 'Cambio' },
  rsi:              { label: 'RSI', group: 'Técnico' },
  atr_percent:      { label: 'ATR', suffix: '%', group: 'Técnico' },
  adx_14:           { label: 'ADX', group: 'Técnico' },
  stoch_k:          { label: 'Estocástico %K', group: 'Técnico' },
  stoch_d:          { label: 'Estocástico %D', group: 'Técnico' },
  macd_line:        { label: 'MACD', group: 'Técnico' },
  macd_hist:        { label: 'MACD histograma', group: 'Técnico' },
  bb_upper:         { label: 'Bollinger superior', suffix: '$', group: 'Bollinger' },
  bb_lower:         { label: 'Bollinger inferior', suffix: '$', group: 'Bollinger' },
  vwap:             { label: 'VWAP', suffix: '$', group: 'Media móvil' },
  sma_5:            { label: 'SMA 5', suffix: '$', group: 'Media móvil' },
  sma_8:            { label: 'SMA 8', suffix: '$', group: 'Media móvil' },
  sma_20:           { label: 'SMA 20', suffix: '$', group: 'Media móvil' },
  sma_50:           { label: 'SMA 50', suffix: '$', group: 'Media móvil' },
  sma_200:          { label: 'SMA 200', suffix: '$', group: 'Media móvil' },
  ema_20:           { label: 'EMA 20', suffix: '$', group: 'Media móvil' },
  ema_50:           { label: 'EMA 50', suffix: '$', group: 'Media móvil' },
  dist_from_vwap:   { label: 'Distancia al VWAP', suffix: '%', group: 'Posición' },
  pos_in_range:     { label: 'Posición en el rango', suffix: '%', group: 'Posición' },
  below_high:       { label: 'Bajo el máximo', suffix: '%', group: 'Posición' },
  above_low:        { label: 'Sobre el mínimo', suffix: '%', group: 'Posición' },
  high_52w:         { label: 'Máximo 52 semanas', suffix: '$', group: 'Posición' },
  low_52w:          { label: 'Mínimo 52 semanas', suffix: '$', group: 'Posición' },
};

/** Indicadores que el motor calcula, para el lado derecho de una señal. */
export const INDICATORS: { id: string; label: string; group: string }[] = [
  { id: 'close', label: 'Cierre', group: 'Precio' },
  { id: 'open', label: 'Apertura', group: 'Precio' },
  { id: 'high', label: 'Máximo', group: 'Precio' },
  { id: 'low', label: 'Mínimo', group: 'Precio' },
  { id: 'volume', label: 'Volumen', group: 'Precio' },
  { id: 'prev_close', label: 'Cierre anterior', group: 'Precio' },
  { id: 'gap_pct', label: 'Gap %', group: 'Derivado' },
  { id: 'rvol', label: 'Volumen relativo', group: 'Derivado' },
  { id: 'range_pct', label: 'Rango %', group: 'Derivado' },
  { id: 'change_pct', label: 'Cambio %', group: 'Derivado' },
  { id: 'change_from_open', label: 'Desde apertura %', group: 'Derivado' },
  { id: 'dollar_volume', label: 'Volumen en dólares', group: 'Derivado' },
  { id: 'dist_from_vwap', label: 'Distancia VWAP %', group: 'Derivado' },
  { id: 'pos_in_range', label: 'Posición en rango', group: 'Derivado' },
  { id: 'rsi_14', label: 'RSI 14', group: 'Técnico' },
  { id: 'adx_14', label: 'ADX 14', group: 'Técnico' },
  { id: 'plus_di', label: '+DI', group: 'Técnico' },
  { id: 'minus_di', label: '−DI', group: 'Técnico' },
  { id: 'stoch_k', label: 'Estocástico %K', group: 'Técnico' },
  { id: 'stoch_d', label: 'Estocástico %D', group: 'Técnico' },
  { id: 'macd_line', label: 'MACD', group: 'MACD' },
  { id: 'macd_signal', label: 'MACD señal', group: 'MACD' },
  { id: 'macd_hist', label: 'MACD histograma', group: 'MACD' },
  { id: 'bb_upper', label: 'Bollinger superior', group: 'Bollinger' },
  { id: 'bb_middle', label: 'Bollinger media', group: 'Bollinger' },
  { id: 'bb_lower', label: 'Bollinger inferior', group: 'Bollinger' },
  { id: 'bb_width', label: 'Bollinger ancho', group: 'Bollinger' },
  { id: 'bb_pct_b', label: 'Bollinger %B', group: 'Bollinger' },
  { id: 'sma_5', label: 'SMA 5', group: 'Media móvil' },
  { id: 'sma_8', label: 'SMA 8', group: 'Media móvil' },
  { id: 'sma_20', label: 'SMA 20', group: 'Media móvil' },
  { id: 'sma_50', label: 'SMA 50', group: 'Media móvil' },
  { id: 'sma_200', label: 'SMA 200', group: 'Media móvil' },
  { id: 'ema_9', label: 'EMA 9', group: 'Media móvil' },
  { id: 'ema_20', label: 'EMA 20', group: 'Media móvil' },
  { id: 'ema_21', label: 'EMA 21', group: 'Media móvil' },
  { id: 'ema_50', label: 'EMA 50', group: 'Media móvil' },
  { id: 'vwap', label: 'VWAP', group: 'Media móvil' },
  // `atr_14` en este motor es AVG(high−low), que no es un ATR. El correcto
  // se llama `true_atr_14` y está al lado, así que se ofrece ese.
  { id: 'true_atr_14', label: 'ATR real 14', group: 'Volatilidad' },
  { id: 'atr_pct', label: 'ATR %', group: 'Volatilidad' },
  { id: 'high_20d', label: 'Máximo 20D', group: 'Rango' },
  { id: 'low_20d', label: 'Mínimo 20D', group: 'Rango' },
  { id: 'high_52w', label: 'Máximo 52S', group: 'Rango' },
  { id: 'low_52w', label: 'Mínimo 52S', group: 'Rango' },
  { id: 'avg_volume_5d', label: 'Volumen medio 5D', group: 'Volumen' },
  { id: 'avg_volume_10d', label: 'Volumen medio 10D', group: 'Volumen' },
  { id: 'avg_volume_20d', label: 'Volumen medio 20D', group: 'Volumen' },
];

/* ── Construcción del catálogo ───────────────────────────────────────── */

function buildCatalog(caps: Capabilities | null): CatalogEntry[] {
  const out: CatalogEntry[] = [];

  // Eventos: siempre desde el catálogo de alertas (es el que tiene nombres
  // legibles y categorías), cruzado con lo que el motor registra.
  const supported = caps ? new Set(caps.events.supported) : null;
  const degraded = caps?.events.degraded ?? {};

  for (const { category, alerts } of getAlertsByCategory()) {
    for (const a of alerts) {
      const cap: Capability = !supported
        ? 'unknown'
        : degraded[a.eventType] ? 'degraded'
          : supported.has(a.eventType) ? 'ok'
            : 'unsupported';
      out.push({
        uid: `event:${a.eventType}`,
        kind: 'event',
        id: a.eventType,
        label: a.name,
        group: category.name,
        alias: `${a.code} ${a.nameEs} ${a.eventType}`,
        capability: cap,
        reason: cap === 'degraded' ? degraded[a.eventType]
          : cap === 'unsupported'
            ? 'el simulador de cartera no lo implementa — disponible en el modo Disparos (eventos reales)'
            : undefined,
      });
    }
  }

  // Filtros: la lista la manda el motor, no una copia local que se
  // desincroniza. FILTER_META solo pone nombre bonito y unidad.
  const keys = caps?.filters.keys ?? Object.keys(FILTER_META);
  for (const key of keys) {
    const meta = FILTER_META[key];
    const fallback = caps?.filters.meta.find(m => m.min_key === `min_${key}`)?.description;
    out.push({
      uid: `filter:${key}`,
      kind: 'filter',
      id: key,
      label: meta?.label ?? fallback ?? key,
      group: meta?.group ?? 'Otros',
      alias: key,
      suffix: meta?.suffix,
      capability: caps ? 'ok' : 'unknown',
    });
  }

  for (const ind of INDICATORS) {
    out.push({
      uid: `indicator:${ind.id}`,
      kind: 'indicator',
      id: ind.id,
      label: ind.label,
      group: ind.group,
      alias: ind.id,
      capability: 'ok',
    });
  }

  return out;
}

/* ── Catálogo del modo DISPAROS (L0) ─────────────────────────────────────
   El análisis de disparos no traduce eventos (son alertas reales grabadas):
   los 279 tipos valen. Los filtros son los mismos de BUILD (catálogo
   generado), etiquetados con su semántica real: exacto si viaja en el
   evento, degradado si viene del snapshot del cierre o de índices 1-min. */

function buildTriggerCatalog(caps: Capabilities | null): CatalogEntry[] {
  const out: CatalogEntry[] = [];

  for (const { category, alerts } of getAlertsByCategory()) {
    for (const a of alerts) {
      out.push({
        uid: `event:${a.eventType}`,
        kind: 'event',
        id: a.eventType,
        label: a.name,
        group: category.name,
        alias: `${a.code} ${a.nameEs} ${a.eventType}`,
        capability: 'ok',
      });
    }
  }

  const ta = caps?.trigger_analysis;
  const semByKey = new Map<string, { capability: Capability; reason?: string }>();
  if (ta) {
    for (const [bucket, keys] of Object.entries(ta.filters.by_semantics)) {
      const [support, source] = bucket.split(':');
      const note = ta.filters.semantics[source]?.note;
      for (const k of keys) {
        semByKey.set(k, {
          capability: support === 'exact' ? 'ok' : 'degraded',
          reason: support === 'exact' ? undefined : note,
        });
      }
    }
  }

  for (const g of FILTER_GROUPS) {
    for (const f of g.filters) {
      const base = f.minK.replace(/^min_/, '');
      const sem = semByKey.get(f.minK);
      out.push({
        uid: `filter:${base}`,
        kind: 'filter',
        id: base,
        label: f.label,
        group: g.group,
        alias: `${f.minK} ${f.maxK}`,
        suffix: f.suf || undefined,
        units: f.units && f.units.length > 0 ? f.units : undefined,
        defU: f.defU,
        capability: sem?.capability ?? (ta ? 'degraded' : 'unknown'),
        reason: sem?.reason,
      });
    }
  }

  return out;
}

/* ── Hook: se pide una vez por sesión y se comparte ──────────────────── */

let cache: Capabilities | null = null;
let inflight: Promise<Capabilities | null> | null = null;

async function fetchCapabilities(): Promise<Capabilities | null> {
  if (cache) return cache;
  if (!inflight) {
    inflight = fetch('/api/backtest/capabilities')
      .then(r => (r.ok ? r.json() : null))
      .then((d: Capabilities | null) => {
        // Un 503 devuelve `{error}`: solo cacheamos una respuesta con forma.
        cache = d && Array.isArray(d?.events?.supported) ? d : null;
        return cache;
      })
      .catch(() => null)
      .finally(() => { inflight = null; });
  }
  return inflight;
}

export function useCatalog() {
  const [caps, setCaps] = useState<Capabilities | null>(cache);
  const [loading, setLoading] = useState(!cache);

  useEffect(() => {
    if (cache) return;
    let alive = true;
    fetchCapabilities().then((c) => {
      if (!alive) return;
      setCaps(c);
      setLoading(false);
    });
    return () => { alive = false; };
  }, []);

  // El catálogo son ~250 entradas y solo cambia cuando llegan capacidades.
  const entries = useMemo(() => buildCatalog(caps), [caps]);

  const byUid = useMemo(() => {
    const m = new Map<string, CatalogEntry>();
    for (const e of entries) m.set(e.uid, e);
    return m;
  }, [entries]);

  const eventCapability = useMemo(() => {
    const m = new Map<string, CatalogEntry>();
    for (const e of entries) if (e.kind === 'event') m.set(e.id, e);
    return m;
  }, [entries]);

  const stats = useMemo(() => {
    const ev = entries.filter(e => e.kind === 'event');
    return {
      eventsTotal: ev.length,
      eventsOk: ev.filter(e => e.capability === 'ok').length,
      eventsDegraded: ev.filter(e => e.capability === 'degraded').length,
      filters: entries.filter(e => e.kind === 'filter').length,
      known: caps !== null,
    };
  }, [entries, caps]);

  const triggerEntries = useMemo(() => buildTriggerCatalog(caps), [caps]);

  return {
    caps, entries, byUid, eventCapability, stats, loading,
    triggerEntries,
    dataAxis: caps?.data_axis ?? null,
    triggerCaps: caps?.trigger_analysis ?? null,
  };
}

/** Nombre legible de un evento aunque no esté en el catálogo de alertas. */
export function eventLabel(id: string): string {
  const a = ALERT_CATALOG.find(x => x.eventType === id);
  return a?.name ?? id.replace(/_/g, ' ');
}
