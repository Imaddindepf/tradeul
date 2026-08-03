/**
 * Alert Catalog — frontend facade over the GENERATED catalog.
 *
 * The data (types, categories and one AlertDefinition per backend event
 * type) is AUTO-GENERATED from the backend registry
 * (services/alert_engine/registry/alert_catalog.py) into
 * ./alert-catalog.generated.ts by scripts/gen_event_assets.py.
 *
 * NEVER add or edit alert entries here — edit the backend registry and run:
 *   python3 scripts/gen_event_assets.py
 *
 * This module keeps only the hand-written parts (display helpers and
 * built-in presets) and re-exports the generated data so every existing
 * `@/lib/alert-catalog` import keeps working unchanged.
 */

export type {
  AlertDirection,
  CustomSettingType,
  CustomSettingMeta,
  AlertCategory,
  AlertDefinition,
} from './alert-catalog.generated';

export {
  ALERT_CATEGORIES,
  ALERT_CATEGORIES_MAP,
  ALERT_CATALOG,
  ALERT_BY_EVENT_TYPE,
  ALERT_BY_CODE,
  ALL_EVENT_TYPES,
  ACTIVE_EVENT_TYPES,
} from './alert-catalog.generated';

import {
  ALERT_CATEGORIES,
  ALERT_CATALOG,
  ALERT_BY_EVENT_TYPE,
  ACTIVE_EVENT_TYPES,
} from './alert-catalog.generated';
import type { AlertCategory, AlertDefinition } from './alert-catalog.generated';

// ============================================================================
// DISPLAY HELPERS — Derived from catalog, no more hardcoded maps
// ============================================================================

/** Get short label for an event type (for table cells, badges) */
export function getEventLabel(eventType: string): string {
  return ALERT_BY_EVENT_TYPE[eventType]?.shortLabel ?? eventType;
}

/** Get Tailwind color class for an event type */
export function getEventColor(eventType: string): string {
  const def = ALERT_BY_EVENT_TYPE[eventType];
  if (!def) return 'text-foreground/80';
  switch (def.direction) {
    case 'bullish': return 'text-emerald-600';
    case 'bearish': return 'text-rose-600 dark:text-rose-400';
    default: return 'text-foreground/80';
  }
}

/** Get alerts grouped by category (sorted by category order) */
export function getAlertsByCategory(): { category: AlertCategory; alerts: AlertDefinition[] }[] {
  const grouped = new Map<string, AlertDefinition[]>();
  for (const alert of ALERT_CATALOG) {
    if (!grouped.has(alert.category)) grouped.set(alert.category, []);
    grouped.get(alert.category)!.push(alert);
  }
  return ALERT_CATEGORIES
    .filter(cat => grouped.has(cat.id))
    .map(cat => ({ category: cat, alerts: grouped.get(cat.id)! }));
}

/** Get only active alerts */
export function getActiveAlerts(): AlertDefinition[] {
  return ALERT_CATALOG.filter(a => a.active);
}

/** Get all active event type strings */
export function getActiveEventTypes(): string[] {
  return ACTIVE_EVENT_TYPES;
}

/** Search alerts by name, code, or description */
export function searchAlerts(query: string, locale: 'en' | 'es' = 'en'): AlertDefinition[] {
  const q = query.toLowerCase().trim();
  if (!q) return ALERT_CATALOG;
  return ALERT_CATALOG.filter(a => {
    const name = locale === 'es' ? a.nameEs : a.name;
    const desc = locale === 'es' ? a.descriptionEs : a.description;
    return (
      a.code.toLowerCase().includes(q) ||
      name.toLowerCase().includes(q) ||
      desc.toLowerCase().includes(q) ||
      a.eventType.toLowerCase().includes(q) ||
      a.keywords.some(k => k.toLowerCase().includes(q))
    );
  });
}

// ============================================================================
// BUILT-IN PRESETS — Strategy templates
// ============================================================================

export interface BuiltInPreset {
  id: string;
  name: string;
  nameEs: string;
  description: string;
  descriptionEs: string;
  eventTypes: string[];
  filters: Record<string, any>;
  category: 'bullish' | 'bearish' | 'neutral' | 'custom';
  isBuiltIn: true;
}

/** Backward-compatible alias used by ConfigWindow */
export type AlertPreset = BuiltInPreset;

export interface TopListPreset {
  id: string;
  name: string;
  nameEs: string;
  description: string;
  descriptionEs: string;
  filters: Record<string, any>;
  isTopList: true;
}

export const BUILT_IN_PRESETS: BuiltInPreset[] = [
  {
    id: 'high_vol_runners',
    name: 'High Vol Runners',
    nameEs: 'Runners Alto Volumen',
    description: 'Running up/down alerts with high relative volume',
    descriptionEs: 'Alertas running up/down con alto volumen relativo',
    eventTypes: ['running_up', 'running_down', 'running_up_sustained', 'running_down_sustained', 'running_up_confirmed', 'running_down_confirmed', 'running_up_intermediate', 'running_down_intermediate', 'rvol_spike', 'volume_surge'],
    filters: { min_rvol: 2 },
    category: 'neutral',
    isBuiltIn: true,
  },
  {
    id: 'gap_plays',
    name: 'Gap Plays',
    nameEs: 'Jugadas de Gap',
    description: 'Gap reversals and false gap retracements',
    descriptionEs: 'Reversiones de gap y retrocesos falsos',
    eventTypes: ['gap_up_reversal', 'gap_down_reversal', 'false_gap_up_retracement', 'false_gap_down_retracement'],
    filters: {},
    category: 'neutral',
    isBuiltIn: true,
  },
  {
    id: 'breakouts',
    name: 'Breakouts',
    nameEs: 'Rupturas',
    description: 'Channel breakouts, consolidation breaks, and ORB',
    descriptionEs: 'Rupturas de canal, consolidación y ORB',
    eventTypes: ['channel_breakout', 'channel_breakout_confirmed', 'orb_up_5min', 'orb_up_15min', 'consol_breakout_5m', 'consol_breakout_15m', 'new_high', 'crossed_daily_high_resistance'],
    filters: {},
    category: 'bullish',
    isBuiltIn: true,
  },
  {
    id: 'institutional',
    name: 'Institutional Flow',
    nameEs: 'Flujo Institucional',
    description: 'Block trades, large bid/ask, and volume confirmed crosses',
    descriptionEs: 'Block trades, grandes bid/ask, y cruces confirmados por volumen',
    eventTypes: ['block_trade', 'large_bid_size', 'large_ask_size', 'crossed_above_sma200', 'crossed_below_sma200', 'running_up_confirmed', 'running_down_confirmed'],
    filters: {},
    category: 'neutral',
    isBuiltIn: true,
  },
  {
    id: 'scalping',
    name: 'Scalping',
    nameEs: 'Scalping',
    description: 'Fast alerts: running now, VWAP crosses, open/close crosses',
    descriptionEs: 'Alertas rápidas: running now, cruces VWAP, cruces open/close',
    eventTypes: ['running_up', 'running_down', 'vwap_cross_up', 'vwap_cross_down', 'crossed_above_open', 'crossed_below_open'],
    filters: {},
    category: 'neutral',
    isBuiltIn: true,
  },
];

export const BUILT_IN_TOP_LISTS: TopListPreset[] = [
  {
    id: 'top_gainers',
    name: 'Top Gainers',
    nameEs: 'Mayores Subidas',
    description: 'Stocks with highest % change today',
    descriptionEs: 'Acciones con mayor % de cambio hoy',
    filters: { sort_by: 'change_percent', sort_dir: 'desc' },
    isTopList: true,
  },
  {
    id: 'top_losers',
    name: 'Top Losers',
    nameEs: 'Mayores Bajadas',
    description: 'Stocks with lowest % change today',
    descriptionEs: 'Acciones con menor % de cambio hoy',
    filters: { sort_by: 'change_percent', sort_dir: 'asc' },
    isTopList: true,
  },
  {
    id: 'most_active',
    name: 'Most Active',
    nameEs: 'Más Activos',
    description: 'Highest relative volume today',
    descriptionEs: 'Mayor volumen relativo hoy',
    filters: { sort_by: 'rvol', sort_dir: 'desc', min_rvol: 2 },
    isTopList: true,
  },
];
