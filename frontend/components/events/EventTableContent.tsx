/**
 * Event Table Content - Event-driven table for market events
 * 
 * Stack:
 * - RxJS for WebSocket streams
 * - TanStack Table + TanStack Virtual for virtualization
 * - Real-time event streaming from Event Detector service
 * 
 * Key differences from Scanner tables:
 * - Events are append-only (newest at top)
 * - Events are timestamped discrete occurrences
 * - Different column structure (time, symbol, event_type, price at event, etc.)
 * 
 * Features:
 * - Column ordering (drag & drop reorder)
 * - Column visibility (show/hide columns)
 * - Per-window filters (each category has its own filter set)
 * - Server-side numeric filtering (price, rvol, change%)
 * - Persistence via useUserPreferencesStore (synced to DB)
 */

'use client';

import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
} from '@tanstack/react-table';
import type { SortingState, Row, ColumnOrderState, VisibilityState } from '@tanstack/react-table';
import { formatNumber, formatPercent } from '@/lib/formatters';
import { getUserTimezone } from '@/lib/date-utils';
import { VirtualizedDataTable } from '@/components/table/VirtualizedDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';
import { TableSettings } from '@/components/table/TableSettings';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useLinkGroupPublisher } from '@/hooks/useLinkGroup';
import { useCloseCurrentWindow, useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useEventFiltersStore } from '@/stores/useEventFiltersStore';
import type { ActiveEventFilters } from '@/stores/useEventFiltersStore';
import { useEventsStore } from '@/stores/useEventsStore';
import { formatDistanceToNowStrict } from 'date-fns';
import { getColumnConfig, formatValue } from '@/lib/table/shared-column-configs';
import {
  TrendingUp,
  TrendingDown,
  Zap,
  BarChart3,
  CircleStop,
  Activity,
} from 'lucide-react';
import { ALERT_BY_EVENT_TYPE, getEventLabel, getEventColor } from '@/lib/alert-catalog';
import { ConfigWindow, type AlertWindowConfig } from '@/components/config/ConfigWindow';

// ============================================================================
// TYPES
// ============================================================================

export interface MarketEvent {
  id: string;
  symbol: string;
  event_type: string;
  timestamp: number; // Unix ms
  price: number;
  // Event-specific
  prev_value?: number;
  new_value?: number;
  delta?: number;
  delta_percent?: number;
  // Context at event time
  change_percent?: number;
  volume?: number;
  rvol?: number;
  market_cap?: number;
  gap_percent?: number;
  change_from_open?: number;
  open_price?: number;
  prev_close?: number;
  vwap?: number;
  atr_percent?: number;
  atr?: number;
  intraday_high?: number;
  intraday_low?: number;
  // Time-window changes
  chg_1min?: number;
  chg_5min?: number;
  chg_10min?: number;
  chg_15min?: number;
  chg_30min?: number;
  chg_60min?: number;
  // Time-window volumes
  vol_1min?: number;
  vol_5min?: number;
  vol_10min?: number;
  vol_15min?: number;
  vol_30min?: number;
  vol_1min_pct?: number;
  vol_5min_pct?: number;
  vol_10min_pct?: number;
  vol_15min_pct?: number;
  vol_30min_pct?: number;
  range_2min?: number;
  range_5min?: number;
  range_15min?: number;
  range_30min?: number;
  range_60min?: number;
  range_120min?: number;
  range_2min_pct?: number;
  range_5min_pct?: number;
  range_15min_pct?: number;
  range_30min_pct?: number;
  range_60min_pct?: number;
  range_120min_pct?: number;
  // Quote data
  bid?: number;
  ask?: number;
  bid_size?: number;
  ask_size?: number;
  spread?: number;
  // Fundamentals
  float_shares?: number;
  shares_outstanding?: number;
  // Intraday indicators
  rsi?: number;
  ema_20?: number;
  ema_50?: number;
  sma_5?: number;
  sma_8?: number;
  sma_20?: number;
  sma_50?: number;
  sma_200?: number;
  macd_line?: number;
  macd_hist?: number;
  stoch_k?: number;
  stoch_d?: number;
  adx_14?: number;
  bb_upper?: number;
  bb_lower?: number;
  // Daily indicators
  daily_sma_20?: number;
  daily_sma_50?: number;
  daily_sma_200?: number;
  daily_rsi?: number;
  daily_adx_14?: number;
  daily_atr_percent?: number;
  daily_bb_position?: number;
  // 52 week
  high_52w?: number;
  low_52w?: number;
  from_52w_high?: number;
  from_52w_low?: number;
  // Derived/computed
  dollar_volume?: number;
  todays_range?: number;
  todays_range_pct?: number;
  bid_ask_ratio?: number;
  float_turnover?: number;
  pos_in_range?: number;
  below_high?: number;
  above_low?: number;
  pos_of_open?: number;
  prev_day_volume?: number;
  // Distances
  dist_from_vwap?: number;
  dist_sma_5?: number;
  dist_sma_8?: number;
  dist_sma_20?: number;
  dist_sma_50?: number;
  dist_sma_200?: number;
  dist_daily_sma_20?: number;
  dist_daily_sma_50?: number;
  // Multi-day changes
  change_1d?: number;
  change_3d?: number;
  change_5d?: number;
  change_10d?: number;
  change_20d?: number;
  // Average volumes
  avg_volume_5d?: number;
  avg_volume_10d?: number;
  avg_volume_20d?: number;
  avg_volume_3m?: number;
  // Classification
  security_type?: string;
  sector?: string;
  industry?: string;
  // Other
  volume_today_pct?: number;
  price_from_high?: number;
  distance_from_nbbo?: number;
  premarket_change_percent?: number;
  postmarket_change_percent?: number;
  trades_today?: number;
  trades_z_score?: number;
  metadata?: Record<string, unknown>;
  quality?: number;
  description?: string;
  details?: Record<string, unknown>;
}

// ============================================================================
// EVENT TYPE CONFIG — derived from alert-catalog.ts (single source of truth)
// ============================================================================

function getEventTypeIcon(eventType: string): typeof Activity {
  const def = ALERT_BY_EVENT_TYPE[eventType];
  if (!def) return Activity;
  if (def.direction === 'bullish') return TrendingUp;
  if (def.direction === 'bearish') return TrendingDown;
  if (def.category === 'volume') return BarChart3;
  if (def.category === 'vwap') return Zap;
  if (def.category === 'halt') return CircleStop;
  return Activity;
}

function getEventTypeConfig(eventType: string): { label: string; color: string; icon: typeof Activity } {
  return {
    label: getEventLabel(eventType),
    color: getEventColor(eventType),
    icon: getEventTypeIcon(eventType),
  };
}

// Default column visibility for event tables
const DEFAULT_EVENT_COLUMN_VISIBILITY: VisibilityState = {
  // Siempre visibles
  row_number: true,
  timestamp: true,
  symbol: true,
  event_type: true,
  price: true,
  change_percent: true,
  volume: true,
  rvol: true,
  // Ocultas por defecto pero disponibles
  gap_percent: false,
  change_from_open: false,
  market_cap: false,
  atr_percent: false,
  atr: false,
  vwap: false,
  // Campos de evento
  prev_value: false,
  new_value: false,
  delta: false,
  delta_percent: false,
  // OHLC
  open_price: false,
  prev_close: false,
  intraday_high: false,
  intraday_low: false,
  // Cambios por ventana de tiempo
  chg_1min: false,
  chg_5min: false,
  chg_10min: false,
  chg_15min: false,
  chg_30min: false,
  chg_60min: false,
  // Volúmenes por ventana de tiempo
  vol_1min: false,
  vol_5min: false,
  vol_10min: false,
  vol_15min: false,
  vol_30min: false,
  vol_1min_pct: false,
  vol_5min_pct: false,
  vol_10min_pct: false,
  vol_15min_pct: false,
  vol_30min_pct: false,
  range_2min: false,
  range_5min: false,
  range_15min: false,
  range_30min: false,
  range_60min: false,
  range_120min: false,
  range_2min_pct: false,
  range_5min_pct: false,
  range_15min_pct: false,
  range_30min_pct: false,
  range_60min_pct: false,
  range_120min_pct: false,
  // Quote data
  bid: false,
  ask: false,
  bid_size: false,
  ask_size: false,
  spread: false,
  // Fundamentales
  float_shares: false,
  shares_outstanding: false,
  // Indicadores intraday
  rsi: false,
  ema_20: false,
  ema_50: false,
  sma_5: false,
  sma_8: false,
  sma_20: false,
  sma_50: false,
  sma_200: false,
  macd_line: false,
  macd_hist: false,
  stoch_k: false,
  stoch_d: false,
  adx_14: false,
  bb_upper: false,
  bb_lower: false,
  // Indicadores diarios
  daily_sma_20: false,
  daily_sma_50: false,
  daily_sma_200: false,
  daily_rsi: false,
  daily_adx_14: false,
  daily_atr_percent: false,
  daily_bb_position: false,
  // 52 semanas
  high_52w: false,
  low_52w: false,
  from_52w_high: false,
  from_52w_low: false,
  // Derivados
  dollar_volume: false,
  todays_range: false,
  todays_range_pct: false,
  bid_ask_ratio: false,
  float_turnover: false,
  pos_in_range: false,
  below_high: false,
  above_low: false,
  pos_of_open: false,
  prev_day_volume: false,
  // Distancias
  dist_from_vwap: false,
  dist_sma_5: false,
  dist_sma_8: false,
  dist_sma_20: false,
  dist_sma_50: false,
  dist_sma_200: false,
  dist_daily_sma_20: false,
  dist_daily_sma_50: false,
  // Cambios multi-día
  change_1d: false,
  change_3d: false,
  change_5d: false,
  change_10d: false,
  change_20d: false,
  // Volúmenes promedio
  avg_volume_5d: false,
  avg_volume_10d: false,
  avg_volume_20d: false,
  avg_volume_3m: false,
  // Clasificación
  security_type: false,
  sector: false,
  industry: false,
  // Otros
  volume_today_pct: false,
  price_from_high: false,
  distance_from_nbbo: false,
  premarket_change_percent: false,
  postmarket_change_percent: false,
  trades_today: false,
  trades_z_score: false,
};

const columnHelper = createColumnHelper<MarketEvent>();

// Stable empty object to prevent re-renders from `|| {}` creating new references
const EMPTY_FILTERS: ActiveEventFilters = {};

// ============================================================================
// PROPS
// ============================================================================

interface EventTableContentProps {
  categoryId: string;
  categoryName: string;
  eventTypes: string[]; // Filter to these event types (empty = all)
  /** Default server-side filters applied when user hasn't customized */
  defaultFilters?: {
    min_price?: number;
    max_price?: number;
    min_rvol?: number;
    max_rvol?: number;
    min_volume?: number;
    max_volume?: number;
    min_change_percent?: number;
    max_change_percent?: number;
    min_market_cap?: number;
    max_market_cap?: number;
    min_gap_percent?: number;
    max_gap_percent?: number;
    min_change_from_open?: number;
    max_change_from_open?: number;
    min_float_shares?: number;
    max_float_shares?: number;
    min_rsi?: number;
    max_rsi?: number;
    min_atr_percent?: number;
    max_atr_percent?: number;
  };
}

// ============================================================================
// HELPERS
// ============================================================================

function parseEvent(d: any): MarketEvent {
  const p = (k: string) => d[k] ?? undefined;
  return {
    id: d.id || `${d.symbol}_${d.event_type}_${d.timestamp}`,
    symbol: d.symbol,
    event_type: d.event_type,
    timestamp: d.timestamp,
    price: d.price,
    prev_value: p('prev_value'),
    new_value: p('new_value'),
    delta: p('delta'),
    delta_percent: p('delta_percent'),
    change_percent: p('change_percent'),
    volume: p('volume'),
    rvol: p('rvol'),
    market_cap: p('market_cap'),
    gap_percent: p('gap_percent'),
    change_from_open: p('change_from_open'),
    open_price: p('open_price'),
    prev_close: p('prev_close'),
    vwap: p('vwap'),
    atr_percent: p('atr_percent'),
    atr: p('atr'),
    intraday_high: p('intraday_high'),
    intraday_low: p('intraday_low'),
    chg_1min: p('chg_1min'),
    chg_5min: p('chg_5min'),
    chg_10min: p('chg_10min'),
    chg_15min: p('chg_15min'),
    chg_30min: p('chg_30min'),
    chg_60min: p('chg_60min'),
    vol_1min: p('vol_1min'),
    vol_5min: p('vol_5min'),
    vol_10min: p('vol_10min'),
    vol_15min: p('vol_15min'),
    vol_30min: p('vol_30min'),
    vol_1min_pct: p('vol_1min_pct'),
    vol_5min_pct: p('vol_5min_pct'),
    vol_10min_pct: p('vol_10min_pct'),
    vol_15min_pct: p('vol_15min_pct'),
    vol_30min_pct: p('vol_30min_pct'),
    range_2min: p('range_2min'),
    range_5min: p('range_5min'),
    range_15min: p('range_15min'),
    range_30min: p('range_30min'),
    range_60min: p('range_60min'),
    range_120min: p('range_120min'),
    range_2min_pct: p('range_2min_pct'),
    range_5min_pct: p('range_5min_pct'),
    range_15min_pct: p('range_15min_pct'),
    range_30min_pct: p('range_30min_pct'),
    range_60min_pct: p('range_60min_pct'),
    range_120min_pct: p('range_120min_pct'),
    bid: p('bid'),
    ask: p('ask'),
    bid_size: p('bid_size'),
    ask_size: p('ask_size'),
    spread: p('spread'),
    float_shares: p('float_shares'),
    shares_outstanding: p('shares_outstanding'),
    rsi: p('rsi'),
    ema_20: p('ema_20'),
    ema_50: p('ema_50'),
    sma_5: p('sma_5'),
    sma_8: p('sma_8'),
    sma_20: p('sma_20'),
    sma_50: p('sma_50'),
    sma_200: p('sma_200'),
    macd_line: p('macd_line'),
    macd_hist: p('macd_hist'),
    stoch_k: p('stoch_k'),
    stoch_d: p('stoch_d'),
    adx_14: p('adx_14'),
    bb_upper: p('bb_upper'),
    bb_lower: p('bb_lower'),
    daily_sma_20: p('daily_sma_20'),
    daily_sma_50: p('daily_sma_50'),
    daily_sma_200: p('daily_sma_200'),
    daily_rsi: p('daily_rsi'),
    daily_adx_14: p('daily_adx_14'),
    daily_atr_percent: p('daily_atr_percent'),
    daily_bb_position: p('daily_bb_position'),
    high_52w: p('high_52w'),
    low_52w: p('low_52w'),
    from_52w_high: p('from_52w_high'),
    from_52w_low: p('from_52w_low'),
    dollar_volume: p('dollar_volume'),
    todays_range: p('todays_range'),
    todays_range_pct: p('todays_range_pct'),
    bid_ask_ratio: p('bid_ask_ratio'),
    float_turnover: p('float_turnover'),
    pos_in_range: p('pos_in_range'),
    below_high: p('below_high'),
    above_low: p('above_low'),
    pos_of_open: p('pos_of_open'),
    prev_day_volume: p('prev_day_volume'),
    dist_from_vwap: p('dist_from_vwap'),
    dist_sma_5: p('dist_sma_5'),
    dist_sma_8: p('dist_sma_8'),
    dist_sma_20: p('dist_sma_20'),
    dist_sma_50: p('dist_sma_50'),
    dist_sma_200: p('dist_sma_200'),
    dist_daily_sma_20: p('dist_daily_sma_20'),
    dist_daily_sma_50: p('dist_daily_sma_50'),
    change_1d: p('change_1d'),
    change_3d: p('change_3d'),
    change_5d: p('change_5d'),
    change_10d: p('change_10d'),
    change_20d: p('change_20d'),
    avg_volume_5d: p('avg_volume_5d'),
    avg_volume_10d: p('avg_volume_10d'),
    avg_volume_20d: p('avg_volume_20d'),
    avg_volume_3m: p('avg_volume_3m'),
    security_type: p('security_type'),
    sector: p('sector'),
    industry: p('industry'),
    volume_today_pct: p('volume_today_pct'),
    price_from_high: p('price_from_high'),
    distance_from_nbbo: p('distance_from_nbbo'),
    premarket_change_percent: p('premarket_change_percent'),
    postmarket_change_percent: p('postmarket_change_percent'),
    trades_today: p('trades_today'),
    trades_z_score: p('trades_z_score'),
    metadata: d.details || d.metadata,
  };
}

/**
 * Client-side filter: returns true if event passes ALL active filters.
 * Centralised to avoid duplication between market_event and events_snapshot.
 *
 * When a field is undefined on the event, we trust the server-side filter
 * (FILTER_MAP in queryHistoricalEvents) already applied that constraint.
 * This handles legacy events whose context JSONB lacks newer fields.
 * For real-time events the enrichment pipeline provides all fields, so
 * the check is strict in practice.
 */
function passesFilters(e: MarketEvent, f: import('@/stores/useEventFiltersStore').ActiveEventFilters): boolean {
  const chk = (val: number | undefined, min: number | undefined, max: number | undefined): boolean => {
    if (min === undefined && max === undefined) return true;
    if (val === undefined || val === null) return true;
    if (min !== undefined && max !== undefined && min > max) return val >= min || val <= max;
    if (min !== undefined && val < min) return false;
    if (max !== undefined && val > max) return false;
    return true;
  };

  // Price & basics
  if (!chk(e.price, f.min_price, f.max_price)) return false;
  if (!chk(e.change_percent, f.min_change_percent, f.max_change_percent)) return false;
  if (!chk(e.rvol, f.min_rvol, f.max_rvol)) return false;
  if (!chk(e.volume, f.min_volume, f.max_volume)) return false;
  if (!chk(e.market_cap, f.min_market_cap, f.max_market_cap)) return false;
  if (!chk(e.gap_percent, f.min_gap_percent, f.max_gap_percent)) return false;
  if (!chk(e.change_from_open, f.min_change_from_open, f.max_change_from_open)) return false;
  if (!chk(e.atr_percent, f.min_atr_percent, f.max_atr_percent)) return false;
  if (!chk(e.atr, f.min_atr, f.max_atr)) return false;
  if (!chk(e.vwap, f.min_vwap, f.max_vwap)) return false;

  // Time-window changes
  if (!chk(e.chg_1min, f.min_chg_1min, f.max_chg_1min)) return false;
  if (!chk(e.chg_5min, f.min_chg_5min, f.max_chg_5min)) return false;
  if (!chk(e.chg_10min, f.min_chg_10min, f.max_chg_10min)) return false;
  if (!chk(e.chg_15min, f.min_chg_15min, f.max_chg_15min)) return false;
  if (!chk(e.chg_30min, f.min_chg_30min, f.max_chg_30min)) return false;
  if (!chk(e.chg_60min, f.min_chg_60min, f.max_chg_60min)) return false;

  // Time-window volumes
  if (!chk(e.vol_1min, f.min_vol_1min, f.max_vol_1min)) return false;
  if (!chk(e.vol_5min, f.min_vol_5min, f.max_vol_5min)) return false;
  if (!chk(e.vol_10min, f.min_vol_10min, f.max_vol_10min)) return false;
  if (!chk(e.vol_15min, f.min_vol_15min, f.max_vol_15min)) return false;
  if (!chk(e.vol_30min, f.min_vol_30min, f.max_vol_30min)) return false;

  // Volume window %
  if (!chk(e.vol_1min_pct, f.min_vol_1min_pct, f.max_vol_1min_pct)) return false;
  if (!chk(e.vol_5min_pct, f.min_vol_5min_pct, f.max_vol_5min_pct)) return false;
  if (!chk(e.vol_10min_pct, f.min_vol_10min_pct, f.max_vol_10min_pct)) return false;
  if (!chk(e.vol_15min_pct, f.min_vol_15min_pct, f.max_vol_15min_pct)) return false;
  if (!chk(e.vol_30min_pct, f.min_vol_30min_pct, f.max_vol_30min_pct)) return false;

  // Range windows ($)
  if (!chk(e.range_2min, f.min_range_2min, f.max_range_2min)) return false;
  if (!chk(e.range_5min, f.min_range_5min, f.max_range_5min)) return false;
  if (!chk(e.range_15min, f.min_range_15min, f.max_range_15min)) return false;
  if (!chk(e.range_30min, f.min_range_30min, f.max_range_30min)) return false;
  if (!chk(e.range_60min, f.min_range_60min, f.max_range_60min)) return false;
  if (!chk(e.range_120min, f.min_range_120min, f.max_range_120min)) return false;

  // Range windows (%)
  if (!chk(e.range_2min_pct, f.min_range_2min_pct, f.max_range_2min_pct)) return false;
  if (!chk(e.range_5min_pct, f.min_range_5min_pct, f.max_range_5min_pct)) return false;
  if (!chk(e.range_15min_pct, f.min_range_15min_pct, f.max_range_15min_pct)) return false;
  if (!chk(e.range_30min_pct, f.min_range_30min_pct, f.max_range_30min_pct)) return false;
  if (!chk(e.range_60min_pct, f.min_range_60min_pct, f.max_range_60min_pct)) return false;
  if (!chk(e.range_120min_pct, f.min_range_120min_pct, f.max_range_120min_pct)) return false;

  // Fundamentals
  if (!chk(e.float_shares, f.min_float_shares, f.max_float_shares)) return false;
  if (!chk(e.shares_outstanding, f.min_shares_outstanding, f.max_shares_outstanding)) return false;
  if (!chk(e.rsi, f.min_rsi, f.max_rsi)) return false;

  // EMA (with legacy SMA fallback)
  if (!chk(e.ema_20, f.min_ema_20 ?? f.min_sma_20, f.max_ema_20 ?? f.max_sma_20)) return false;
  if (!chk(e.ema_50, f.min_ema_50 ?? f.min_sma_50, f.max_ema_50 ?? f.max_sma_50)) return false;

  // Intraday SMA
  if (!chk(e.sma_5, f.min_sma_5, f.max_sma_5)) return false;
  if (!chk(e.sma_8, f.min_sma_8, f.max_sma_8)) return false;
  if (!chk(e.sma_200, f.min_sma_200, f.max_sma_200)) return false;

  // Quote
  if (!chk(e.bid, f.min_bid, f.max_bid)) return false;
  if (!chk(e.ask, f.min_ask, f.max_ask)) return false;
  if (!chk(e.bid_size, f.min_bid_size, f.max_bid_size)) return false;
  if (!chk(e.ask_size, f.min_ask_size, f.max_ask_size)) return false;
  if (!chk(e.spread, f.min_spread, f.max_spread)) return false;

  // MACD / Stochastic / ADX / Bollinger
  if (!chk(e.macd_line, f.min_macd_line, f.max_macd_line)) return false;
  if (!chk(e.macd_hist, f.min_macd_hist, f.max_macd_hist)) return false;
  if (!chk(e.stoch_k, f.min_stoch_k, f.max_stoch_k)) return false;
  if (!chk(e.stoch_d, f.min_stoch_d, f.max_stoch_d)) return false;
  if (!chk(e.adx_14, f.min_adx_14, f.max_adx_14)) return false;
  if (!chk(e.bb_upper, f.min_bb_upper, f.max_bb_upper)) return false;
  if (!chk(e.bb_lower, f.min_bb_lower, f.max_bb_lower)) return false;

  // Daily indicators
  if (!chk(e.daily_sma_20, f.min_daily_sma_20, f.max_daily_sma_20)) return false;
  if (!chk(e.daily_sma_50, f.min_daily_sma_50, f.max_daily_sma_50)) return false;
  if (!chk(e.daily_sma_200, f.min_daily_sma_200, f.max_daily_sma_200)) return false;
  if (!chk(e.daily_rsi, f.min_daily_rsi, f.max_daily_rsi)) return false;
  if (!chk(e.daily_adx_14, f.min_daily_adx_14, f.max_daily_adx_14)) return false;
  if (!chk(e.daily_atr_percent, f.min_daily_atr_percent, f.max_daily_atr_percent)) return false;
  if (!chk(e.daily_bb_position, f.min_daily_bb_position, f.max_daily_bb_position)) return false;

  // 52-week
  if (!chk(e.high_52w, f.min_high_52w, f.max_high_52w)) return false;
  if (!chk(e.low_52w, f.min_low_52w, f.max_low_52w)) return false;
  if (!chk(e.from_52w_high, f.min_from_52w_high, f.max_from_52w_high)) return false;
  if (!chk(e.from_52w_low, f.min_from_52w_low, f.max_from_52w_low)) return false;

  // Trades anomaly
  if (!chk(e.trades_today, f.min_trades_today, f.max_trades_today)) return false;
  if (!chk(e.trades_z_score, f.min_trades_z_score, f.max_trades_z_score)) return false;

  // Derived / Computed
  if (!chk(e.dollar_volume, f.min_dollar_volume, f.max_dollar_volume)) return false;
  if (!chk(e.todays_range, f.min_todays_range, f.max_todays_range)) return false;
  if (!chk(e.todays_range_pct, f.min_todays_range_pct, f.max_todays_range_pct)) return false;
  if (!chk(e.bid_ask_ratio, f.min_bid_ask_ratio, f.max_bid_ask_ratio)) return false;
  if (!chk(e.float_turnover, f.min_float_turnover, f.max_float_turnover)) return false;
  if (!chk(e.dist_from_vwap, f.min_dist_from_vwap, f.max_dist_from_vwap)) return false;

  // Distance from intraday SMAs
  if (!chk(e.dist_sma_5, f.min_dist_sma_5, f.max_dist_sma_5)) return false;
  if (!chk(e.dist_sma_8, f.min_dist_sma_8, f.max_dist_sma_8)) return false;
  if (!chk(e.dist_sma_20, f.min_dist_sma_20, f.max_dist_sma_20)) return false;
  if (!chk(e.dist_sma_50, f.min_dist_sma_50, f.max_dist_sma_50)) return false;
  if (!chk(e.dist_sma_200, f.min_dist_sma_200, f.max_dist_sma_200)) return false;

  // Position / range
  if (!chk(e.pos_in_range, f.min_pos_in_range, f.max_pos_in_range)) return false;
  if (!chk(e.below_high, f.min_below_high, f.max_below_high)) return false;
  if (!chk(e.above_low, f.min_above_low, f.max_above_low)) return false;
  if (!chk(e.pos_of_open, f.min_pos_of_open, f.max_pos_of_open)) return false;
  if (!chk(e.prev_day_volume, f.min_prev_day_volume, f.max_prev_day_volume)) return false;

  // Multi-day changes
  if (!chk(e.change_1d, f.min_change_1d, f.max_change_1d)) return false;
  if (!chk(e.change_3d, f.min_change_3d, f.max_change_3d)) return false;
  if (!chk(e.change_5d, f.min_change_5d, f.max_change_5d)) return false;
  if (!chk(e.change_10d, f.min_change_10d, f.max_change_10d)) return false;
  if (!chk(e.change_20d, f.min_change_20d, f.max_change_20d)) return false;

  // Average daily volumes
  if (!chk(e.avg_volume_5d, f.min_avg_volume_5d, f.max_avg_volume_5d)) return false;
  if (!chk(e.avg_volume_10d, f.min_avg_volume_10d, f.max_avg_volume_10d)) return false;
  if (!chk(e.avg_volume_20d, f.min_avg_volume_20d, f.max_avg_volume_20d)) return false;
  if (!chk(e.avg_volume_3m, f.min_avg_volume_3m, f.max_avg_volume_3m)) return false;

  // Distance from daily SMAs
  if (!chk(e.dist_daily_sma_20, f.min_dist_daily_sma_20, f.max_dist_daily_sma_20)) return false;
  if (!chk(e.dist_daily_sma_50, f.min_dist_daily_sma_50, f.max_dist_daily_sma_50)) return false;

  // Scanner-aligned
  if (!chk(e.volume_today_pct, f.min_volume_today_pct, f.max_volume_today_pct)) return false;
  if (!chk(e.price_from_high, f.min_price_from_high, f.max_price_from_high)) return false;
  if (!chk(e.distance_from_nbbo, f.min_distance_from_nbbo, f.max_distance_from_nbbo)) return false;
  if (!chk(e.premarket_change_percent, f.min_premarket_change_percent, f.max_premarket_change_percent)) return false;
  if (!chk(e.postmarket_change_percent, f.min_postmarket_change_percent, f.max_postmarket_change_percent)) return false;

  // String filters
  if (f.security_type && e.security_type?.toUpperCase() !== f.security_type.toUpperCase()) return false;
  if (f.sector && (!e.sector || !e.sector.toUpperCase().includes(f.sector.toUpperCase()))) return false;
  if (f.industry && (!e.industry || !e.industry.toUpperCase().includes(f.industry.toUpperCase()))) return false;

  // Symbol filters
  if (f.symbols_include?.length && !f.symbols_include.includes(e.symbol)) return false;
  if (f.symbols_exclude?.length && f.symbols_exclude.includes(e.symbol)) return false;

  // Per-alert quality threshold (aq:event_type = minQuality)
  const aqKey = `aq:${e.event_type}` as const;
  const minQ = f[aqKey];
  if (minQ != null && (e.quality == null || e.quality < minQ)) return false;

  return true;
}

// ============================================================================
// COMPONENT
// ============================================================================

export function EventTableContent({ categoryId, categoryName, eventTypes: initialEventTypes, defaultFilters }: EventTableContentProps) {
  const { t } = useTranslation();
  const { executeTickerCommand } = useCommandExecutor();
  const { publish: publishTicker, hasSubscribers, linkGroup } = useLinkGroupPublisher();
  const closeCurrentWindow = useCloseCurrentWindow();
  const ws = useWebSocket();

  // ========================================================================
  // ALERT CONFIG PANEL STATE
  // ========================================================================

  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; symbol?: string } | null>(null);
  const { openWindow } = useFloatingWindow();
  const [customEventTypes, setCustomEventTypes] = useState<string[]>(initialEventTypes);

  // Refs to avoid stale closures in memoized column definitions
  const linkGroupRef = useRef(linkGroup);
  const hasSubscribersRef = useRef(hasSubscribers);
  const publishTickerRef = useRef(publishTicker);
  const openWindowRef = useRef(openWindow);
  const executeTickerCommandRef = useRef(executeTickerCommand);
  useEffect(() => {
    linkGroupRef.current = linkGroup;
    hasSubscribersRef.current = hasSubscribers;
    publishTickerRef.current = publishTicker;
    openWindowRef.current = openWindow;
    executeTickerCommandRef.current = executeTickerCommand;
  });

  // Active event types: custom selection or initial from category
  // IMPORTANT: useMemo with serialized key to prevent infinite re-render loop
  // (array reference must be stable or useEffect with this dependency fires every render)
  const activeEventTypes = useMemo(() => {
    return customEventTypes.length > 0 ? customEventTypes : initialEventTypes;
  }, [customEventTypes.join(','), initialEventTypes.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  // ========================================================================
  // USER PREFERENCES STORE (synced to DB)
  // ========================================================================

  const saveColumnVisibilityToStore = useUserPreferencesStore((s) => s.saveColumnVisibility);
  const saveColumnOrderToStore = useUserPreferencesStore((s) => s.saveColumnOrder);

  const listKey = `evt_${categoryId}`;
  const storedColumnVisibility = useUserPreferencesStore((s) => s.columnVisibility[listKey]);
  const storedColumnOrder = useUserPreferencesStore((s) => s.columnOrder[listKey]);

  // ========================================================================
  // STATE (SWR: seed from global cache for instant render on re-mount)
  // ========================================================================

  const eventsCache = useEventsStore((s) => s.getEvents);
  const setEventsCache = useEventsStore((s) => s.setEvents);
  const appendEventCache = useEventsStore((s) => s.appendEvent);
  const clearCategoryCache = useEventsStore((s) => s.clearCategory);

  const cachedEvents = useMemo(() => eventsCache(categoryId) as MarketEvent[], [eventsCache, categoryId]);
  const hasCachedEvents = cachedEvents.length > 0;

  const [events, setEvents] = useState<MarketEvent[]>(cachedEvents);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [newEventIds, setNewEventIds] = useState<Set<string>>(new Set());

  // Infinite scroll pagination state
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const oldestEventTsRef = useRef<string | null>(null);

  const animationTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'timestamp', desc: true },
  ]);

  const [columnOrder, setColumnOrder] = useState<ColumnOrderState>(() =>
    storedColumnOrder || []
  );

  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(() => {
    if (storedColumnVisibility && Object.keys(storedColumnVisibility).length > 0) {
      return storedColumnVisibility;
    }
    return DEFAULT_EVENT_COLUMN_VISIBILITY;
  });

  useEffect(() => {
    if (columnOrder.length > 0) {
      saveColumnOrderToStore(listKey, columnOrder);
    }
  }, [columnOrder, listKey, saveColumnOrderToStore]);

  useEffect(() => {
    if (Object.keys(columnVisibility).length > 0) {
      saveColumnVisibilityToStore(listKey, columnVisibility);
    }
  }, [columnVisibility, listKey, saveColumnVisibilityToStore]);

  // ========================================================================
  // EVENT FILTERS (per-category from store)
  // ========================================================================

  const eventFilters = useEventFiltersStore(
    useCallback((s: { filtersMap: Record<string, ActiveEventFilters> }) => s.filtersMap[categoryId], [categoryId])
  ) || EMPTY_FILTERS;

  // Sync event_types from store → customEventTypes (for external updates, e.g., ConfigWindow BUILD flow)
  // When the store's event_types changes (from outside this component), update the local state.
  const storeEventTypes = eventFilters.event_types;
  useEffect(() => {
    if (storeEventTypes && storeEventTypes.length > 0) {
      setCustomEventTypes(prev => {
        const prevKey = prev.sort().join(',');
        const newKey = [...storeEventTypes].sort().join(',');
        return prevKey === newKey ? prev : storeEventTypes;
      });
    }
  }, [storeEventTypes]); // eslint-disable-line react-hooks/exhaustive-deps

  // Apply client-side filters (complement server-side filtering)
  const filteredEvents = useMemo(() => {
    const result = events.filter((event) => {
      if (categoryId === 'evt_all' && eventFilters.event_types && eventFilters.event_types.length > 0) {
        if (!eventFilters.event_types.includes(event.event_type)) {
          return false;
        }
      }
      return passesFilters(event, eventFilters);
    });
    return result;
  }, [events, eventFilters, categoryId]);

  // Cleanup animation timeouts on unmount
  useEffect(() => {
    const timers = animationTimersRef.current;
    return () => {
      timers.forEach((timerId) => clearTimeout(timerId));
      timers.clear();
    };
  }, []);

  // ========================================================================
  // WEBSOCKET SUBSCRIPTION (with flood protection)
  // ========================================================================

  // Refs for idempotent filter updates (prevents re-sending identical filters)
  const lastSentFiltersRef = useRef<string>('');
  const lastSentTypesRef = useRef<string>('');
  const filterDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeEventTypesRef = useRef(activeEventTypes);
  activeEventTypesRef.current = activeEventTypes;
  const eventFiltersRef = useRef(eventFilters);
  eventFiltersRef.current = eventFilters;

  // Stable subscription ID for this table instance — survives re-renders, not remounts
  const subIdRef = useRef(`${categoryId}_${Date.now()}`);

  // 1) SUBSCRIPTION EFFECT: only depends on connection + event types
  //    Subscribes/unsubscribes and listens for incoming events.
  //    Does NOT depend on filters (filters are updated separately).
  useEffect(() => {
    if (!ws.isConnected) {
      setConnectionError('Connecting to server...');
      return;
    }

    setConnectionError(null);
    const subId = subIdRef.current;
    const types = activeEventTypes;

    // Build subscribe message with sub_id + current event types + snapshot of filters
    const filters = eventFiltersRef.current;
    const df = defaultFilters;
    const subscribeMsg: Record<string, any> = {
      action: 'subscribe_events',
      sub_id: subId,
      event_types: types.length > 0 ? types : undefined,
    };
    // Server-side filters: user override → category default → omit
    // Maps frontend min_xxx → server xxx_min format
    const setF = (key: string, val: number | undefined) => { if (val !== undefined) subscribeMsg[key] = val; };
    const setS = (key: string, val: string | undefined) => { if (val !== undefined && val !== '') subscribeMsg[key] = val; };
    // Core filters (with category defaults fallback)
    setF('price_min', filters.min_price ?? df?.min_price); setF('price_max', filters.max_price ?? df?.max_price);
    setF('rvol_min', filters.min_rvol ?? df?.min_rvol); setF('rvol_max', filters.max_rvol ?? df?.max_rvol);
    setF('change_min', filters.min_change_percent ?? df?.min_change_percent); setF('change_max', filters.max_change_percent ?? df?.max_change_percent);
    setF('volume_min', filters.min_volume ?? df?.min_volume); setF('volume_max', filters.max_volume ?? df?.max_volume);
    setF('market_cap_min', filters.min_market_cap ?? df?.min_market_cap); setF('market_cap_max', filters.max_market_cap ?? df?.max_market_cap);
    setF('gap_percent_min', filters.min_gap_percent ?? df?.min_gap_percent); setF('gap_percent_max', filters.max_gap_percent ?? df?.max_gap_percent);
    setF('change_from_open_min', filters.min_change_from_open ?? df?.min_change_from_open); setF('change_from_open_max', filters.max_change_from_open ?? df?.max_change_from_open);
    setF('float_shares_min', filters.min_float_shares ?? df?.min_float_shares); setF('float_shares_max', filters.max_float_shares ?? df?.max_float_shares);
    setF('rsi_min', filters.min_rsi ?? df?.min_rsi); setF('rsi_max', filters.max_rsi ?? df?.max_rsi);
    setF('atr_percent_min', filters.min_atr_percent ?? df?.min_atr_percent); setF('atr_percent_max', filters.max_atr_percent ?? df?.max_atr_percent);
    setF('vwap_min', filters.min_vwap); setF('vwap_max', filters.max_vwap);
    // Volume windows
    setF('vol_1min_min', filters.min_vol_1min); setF('vol_1min_max', filters.max_vol_1min);
    setF('vol_5min_min', filters.min_vol_5min); setF('vol_5min_max', filters.max_vol_5min);
    setF('vol_10min_min', filters.min_vol_10min); setF('vol_10min_max', filters.max_vol_10min);
    setF('vol_15min_min', filters.min_vol_15min); setF('vol_15min_max', filters.max_vol_15min);
    setF('vol_30min_min', filters.min_vol_30min); setF('vol_30min_max', filters.max_vol_30min);
    // Volume window %
    setF('vol_1min_pct_min', filters.min_vol_1min_pct); setF('vol_1min_pct_max', filters.max_vol_1min_pct);
    setF('vol_5min_pct_min', filters.min_vol_5min_pct); setF('vol_5min_pct_max', filters.max_vol_5min_pct);
    setF('vol_10min_pct_min', filters.min_vol_10min_pct); setF('vol_10min_pct_max', filters.max_vol_10min_pct);
    setF('vol_15min_pct_min', filters.min_vol_15min_pct); setF('vol_15min_pct_max', filters.max_vol_15min_pct);
    setF('vol_30min_pct_min', filters.min_vol_30min_pct); setF('vol_30min_pct_max', filters.max_vol_30min_pct);
    // Range windows
    setF('range_2min_min', filters.min_range_2min); setF('range_2min_max', filters.max_range_2min);
    setF('range_5min_min', filters.min_range_5min); setF('range_5min_max', filters.max_range_5min);
    setF('range_15min_min', filters.min_range_15min); setF('range_15min_max', filters.max_range_15min);
    setF('range_30min_min', filters.min_range_30min); setF('range_30min_max', filters.max_range_30min);
    setF('range_60min_min', filters.min_range_60min); setF('range_60min_max', filters.max_range_60min);
    setF('range_120min_min', filters.min_range_120min); setF('range_120min_max', filters.max_range_120min);
    setF('range_2min_pct_min', filters.min_range_2min_pct); setF('range_2min_pct_max', filters.max_range_2min_pct);
    setF('range_5min_pct_min', filters.min_range_5min_pct); setF('range_5min_pct_max', filters.max_range_5min_pct);
    setF('range_15min_pct_min', filters.min_range_15min_pct); setF('range_15min_pct_max', filters.max_range_15min_pct);
    setF('range_30min_pct_min', filters.min_range_30min_pct); setF('range_30min_pct_max', filters.max_range_30min_pct);
    setF('range_60min_pct_min', filters.min_range_60min_pct); setF('range_60min_pct_max', filters.max_range_60min_pct);
    setF('range_120min_pct_min', filters.min_range_120min_pct); setF('range_120min_pct_max', filters.max_range_120min_pct);
    // Change windows
    setF('chg_1min_min', filters.min_chg_1min); setF('chg_1min_max', filters.max_chg_1min);
    setF('chg_5min_min', filters.min_chg_5min); setF('chg_5min_max', filters.max_chg_5min);
    setF('chg_10min_min', filters.min_chg_10min); setF('chg_10min_max', filters.max_chg_10min);
    setF('chg_15min_min', filters.min_chg_15min); setF('chg_15min_max', filters.max_chg_15min);
    setF('chg_30min_min', filters.min_chg_30min); setF('chg_30min_max', filters.max_chg_30min);
    setF('chg_60min_min', filters.min_chg_60min); setF('chg_60min_max', filters.max_chg_60min);
    // Shares & quote
    setF('shares_outstanding_min', filters.min_shares_outstanding); setF('shares_outstanding_max', filters.max_shares_outstanding);
    setF('bid_min', filters.min_bid); setF('bid_max', filters.max_bid);
    setF('ask_min', filters.min_ask); setF('ask_max', filters.max_ask);
    setF('bid_size_min', filters.min_bid_size); setF('bid_size_max', filters.max_bid_size);
    setF('ask_size_min', filters.min_ask_size); setF('ask_size_max', filters.max_ask_size);
    setF('spread_min', filters.min_spread); setF('spread_max', filters.max_spread);
    // Intraday SMA / MACD / Stoch / ADX / BB
    setF('sma_5_min', filters.min_sma_5); setF('sma_5_max', filters.max_sma_5);
    setF('sma_8_min', filters.min_sma_8); setF('sma_8_max', filters.max_sma_8);
    setF('sma_20_min', filters.min_sma_20); setF('sma_20_max', filters.max_sma_20);
    setF('sma_50_min', filters.min_sma_50); setF('sma_50_max', filters.max_sma_50);
    setF('sma_200_min', filters.min_sma_200); setF('sma_200_max', filters.max_sma_200);
    setF('macd_line_min', filters.min_macd_line); setF('macd_line_max', filters.max_macd_line);
    setF('macd_hist_min', filters.min_macd_hist); setF('macd_hist_max', filters.max_macd_hist);
    setF('stoch_k_min', filters.min_stoch_k); setF('stoch_k_max', filters.max_stoch_k);
    setF('stoch_d_min', filters.min_stoch_d); setF('stoch_d_max', filters.max_stoch_d);
    setF('adx_14_min', filters.min_adx_14); setF('adx_14_max', filters.max_adx_14);
    setF('bb_upper_min', filters.min_bb_upper); setF('bb_upper_max', filters.max_bb_upper);
    setF('bb_lower_min', filters.min_bb_lower); setF('bb_lower_max', filters.max_bb_lower);
    // Daily indicators
    setF('daily_sma_20_min', filters.min_daily_sma_20); setF('daily_sma_20_max', filters.max_daily_sma_20);
    setF('daily_sma_50_min', filters.min_daily_sma_50); setF('daily_sma_50_max', filters.max_daily_sma_50);
    setF('daily_sma_200_min', filters.min_daily_sma_200); setF('daily_sma_200_max', filters.max_daily_sma_200);
    setF('daily_rsi_min', filters.min_daily_rsi); setF('daily_rsi_max', filters.max_daily_rsi);
    setF('high_52w_min', filters.min_high_52w); setF('high_52w_max', filters.max_high_52w);
    setF('low_52w_min', filters.min_low_52w); setF('low_52w_max', filters.max_low_52w);
    // Trades
    setF('trades_today_min', filters.min_trades_today); setF('trades_today_max', filters.max_trades_today);
    setF('trades_z_score_min', filters.min_trades_z_score); setF('trades_z_score_max', filters.max_trades_z_score);
    // === NEW: Computed derived fields ===
    setF('dollar_volume_min', filters.min_dollar_volume); setF('dollar_volume_max', filters.max_dollar_volume);
    setF('todays_range_min', filters.min_todays_range); setF('todays_range_max', filters.max_todays_range);
    setF('todays_range_pct_min', filters.min_todays_range_pct); setF('todays_range_pct_max', filters.max_todays_range_pct);
    setF('bid_ask_ratio_min', filters.min_bid_ask_ratio); setF('bid_ask_ratio_max', filters.max_bid_ask_ratio);
    setF('float_turnover_min', filters.min_float_turnover); setF('float_turnover_max', filters.max_float_turnover);
    setF('dist_from_vwap_min', filters.min_dist_from_vwap); setF('dist_from_vwap_max', filters.max_dist_from_vwap);
    setF('dist_sma_5_min', filters.min_dist_sma_5); setF('dist_sma_5_max', filters.max_dist_sma_5);
    setF('dist_sma_8_min', filters.min_dist_sma_8); setF('dist_sma_8_max', filters.max_dist_sma_8);
    setF('dist_sma_20_min', filters.min_dist_sma_20); setF('dist_sma_20_max', filters.max_dist_sma_20);
    setF('dist_sma_50_min', filters.min_dist_sma_50); setF('dist_sma_50_max', filters.max_dist_sma_50);
    setF('dist_sma_200_min', filters.min_dist_sma_200); setF('dist_sma_200_max', filters.max_dist_sma_200);
    setF('pos_in_range_min', filters.min_pos_in_range); setF('pos_in_range_max', filters.max_pos_in_range);
    setF('below_high_min', filters.min_below_high); setF('below_high_max', filters.max_below_high);
    setF('above_low_min', filters.min_above_low); setF('above_low_max', filters.max_above_low);
    setF('pos_of_open_min', filters.min_pos_of_open); setF('pos_of_open_max', filters.max_pos_of_open);
    setF('prev_day_volume_min', filters.min_prev_day_volume); setF('prev_day_volume_max', filters.max_prev_day_volume);
    // Multi-day changes
    setF('change_1d_min', filters.min_change_1d); setF('change_1d_max', filters.max_change_1d);
    setF('change_3d_min', filters.min_change_3d); setF('change_3d_max', filters.max_change_3d);
    setF('change_5d_min', filters.min_change_5d); setF('change_5d_max', filters.max_change_5d);
    setF('change_10d_min', filters.min_change_10d); setF('change_10d_max', filters.max_change_10d);
    setF('change_20d_min', filters.min_change_20d); setF('change_20d_max', filters.max_change_20d);
    // Average daily volumes
    setF('avg_volume_5d_min', filters.min_avg_volume_5d); setF('avg_volume_5d_max', filters.max_avg_volume_5d);
    setF('avg_volume_10d_min', filters.min_avg_volume_10d); setF('avg_volume_10d_max', filters.max_avg_volume_10d);
    setF('avg_volume_20d_min', filters.min_avg_volume_20d); setF('avg_volume_20d_max', filters.max_avg_volume_20d);
    // Distance from daily SMAs
    setF('dist_daily_sma_20_min', filters.min_dist_daily_sma_20); setF('dist_daily_sma_20_max', filters.max_dist_daily_sma_20);
    setF('dist_daily_sma_50_min', filters.min_dist_daily_sma_50); setF('dist_daily_sma_50_max', filters.max_dist_daily_sma_50);
    // 52w distances
    setF('from_52w_high_min', filters.min_from_52w_high); setF('from_52w_high_max', filters.max_from_52w_high);
    setF('from_52w_low_min', filters.min_from_52w_low); setF('from_52w_low_max', filters.max_from_52w_low);
    // Daily ADX / ATR / BB position
    setF('daily_adx_14_min', filters.min_daily_adx_14); setF('daily_adx_14_max', filters.max_daily_adx_14);
    setF('daily_atr_percent_min', filters.min_daily_atr_percent); setF('daily_atr_percent_max', filters.max_daily_atr_percent);
    setF('daily_bb_position_min', filters.min_daily_bb_position); setF('daily_bb_position_max', filters.max_daily_bb_position);
    // Scanner-aligned filters
    setF('volume_today_pct_min', filters.min_volume_today_pct); setF('volume_today_pct_max', filters.max_volume_today_pct);
    setF('minute_volume_min', filters.min_minute_volume);
    setF('price_from_high_min', filters.min_price_from_high); setF('price_from_high_max', filters.max_price_from_high);
    setF('price_from_low_min', filters.min_price_from_low); setF('price_from_low_max', filters.max_price_from_low);
    setF('price_from_intraday_high_min', filters.min_price_from_intraday_high); setF('price_from_intraday_high_max', filters.max_price_from_intraday_high);
    setF('price_from_intraday_low_min', filters.min_price_from_intraday_low); setF('price_from_intraday_low_max', filters.max_price_from_intraday_low);
    setF('distance_from_nbbo_min', filters.min_distance_from_nbbo); setF('distance_from_nbbo_max', filters.max_distance_from_nbbo);
    setF('premarket_change_percent_min', filters.min_premarket_change_percent); setF('premarket_change_percent_max', filters.max_premarket_change_percent);
    setF('postmarket_change_percent_min', filters.min_postmarket_change_percent); setF('postmarket_change_percent_max', filters.max_postmarket_change_percent);
    setF('avg_volume_3m_min', filters.min_avg_volume_3m); setF('avg_volume_3m_max', filters.max_avg_volume_3m);
    setF('atr_min', filters.min_atr); setF('atr_max', filters.max_atr);
    setF('change_from_open_dollars_min', filters.min_change_from_open_dollars); setF('change_from_open_dollars_max', filters.max_change_from_open_dollars);
    // EMA filters (map to ema_ prefix for server)
    setF('ema_20_min', filters.min_ema_20); setF('ema_20_max', filters.max_ema_20);
    setF('ema_50_min', filters.min_ema_50); setF('ema_50_max', filters.max_ema_50);
    // String filters
    setS('security_type', filters.security_type);
    setS('sector', filters.sector);
    setS('industry', filters.industry);
    // Symbols
    if (filters.symbols_include?.length) subscribeMsg.symbols_include = filters.symbols_include;
    if (filters.symbols_exclude?.length) subscribeMsg.symbols_exclude = filters.symbols_exclude;
    // Per-alert quality thresholds (aq:event_type → min quality)
    for (const [k, v] of Object.entries(filters)) {
      if (k.startsWith('aq:') && v != null) subscribeMsg[k] = v;
    }

    ws.send(subscribeMsg);
    setIsSubscribed(true);

    // Track what we sent for idempotency
    lastSentTypesRef.current = types.join(',');
    lastSentFiltersRef.current = JSON.stringify(filters);

    const eventSub = ws.messages$.subscribe((msg: any) => {
      if (msg.type === 'market_event') {
        // Only process if this event matched OUR subscription
        const matchedSubs: string[] = msg.matched_subs || [];
        if (!matchedSubs.includes(subId)) return;

        const d = msg.data || msg;
        const event = parseEvent(d);

        // Client-side event type filter (safety net)
        const currentTypes = activeEventTypesRef.current;
        if (currentTypes.length > 0 && !currentTypes.includes(event.event_type)) return;

        // Client-side filters (safety net)
        if (!passesFilters(event, eventFiltersRef.current)) return;

        setEvents((prev) => {
          if (prev.some(e => e.id === event.id)) return prev;
          return [event, ...prev];
        });
        appendEventCache(categoryId, event);

        // Flash animation
        setNewEventIds((prev) => new Set(prev).add(event.id));
        const timerId = setTimeout(() => {
          setNewEventIds((prev) => {
            const updated = new Set(prev);
            updated.delete(event.id);
            return updated;
          });
          animationTimersRef.current.delete(timerId);
        }, 850);
        animationTimersRef.current.add(timerId);
      }

      if (msg.type === 'events_snapshot') {
        if (msg.sub_id && msg.sub_id !== subId) return;

        const seen = new Set<string>();
        const snapshot: MarketEvent[] = (msg.events || [])
          .map((e: any) => parseEvent(e))
          .filter((e: MarketEvent) => {
            if (seen.has(e.id)) return false;
            seen.add(e.id);
            return true;
          });
        setEvents(snapshot);
        setEventsCache(categoryId, snapshot);
        setHasMore(!!msg.has_more);

        if (snapshot.length > 0) {
          const oldest = snapshot[0];
          oldestEventTsRef.current = typeof oldest.timestamp === 'number'
            ? new Date(oldest.timestamp).toISOString()
            : String(oldest.timestamp);
        }
      }

      if (msg.type === 'older_events') {
        if (msg.sub_id && msg.sub_id !== subId) return;

        const seen = new Set<string>();
        const olderBatch: MarketEvent[] = (msg.events || [])
          .map((e: any) => parseEvent(e))
          .filter((e: MarketEvent) => {
            if (seen.has(e.id)) return false;
            seen.add(e.id);
            return true;
          });

        setHasMore(!!msg.has_more);
        setLoadingMore(false);

        if (olderBatch.length > 0) {
          // Update cursor to the oldest event in this batch
          const oldest = olderBatch[0];
          oldestEventTsRef.current = typeof oldest.timestamp === 'number'
            ? new Date(oldest.timestamp).toISOString()
            : String(oldest.timestamp);

          setEvents((prev) => {
            const existingIds = new Set(prev.map(e => e.id));
            const unique = olderBatch.filter(e => !existingIds.has(e.id));
            const merged = [...prev, ...unique];
            setEventsCache(categoryId, merged);
            return merged;
          });
        }
      }

      if (msg.type === 'trading_day_changed') {
        setEvents([]);
        clearCategoryCache(categoryId);
        setHasMore(false);
        oldestEventTsRef.current = null;
      }
    });

    return () => {
      eventSub.unsubscribe();
      ws.send({ action: 'unsubscribe_events', sub_id: subId });
      setIsSubscribed(false);
      if (filterDebounceRef.current) {
        clearTimeout(filterDebounceRef.current);
        filterDebounceRef.current = null;
      }
    };
  }, [ws.isConnected, ws.messages$, ws.send, activeEventTypes]); // eslint-disable-line react-hooks/exhaustive-deps

  // 2) FILTER UPDATE EFFECT: debounced + idempotent
  //    Only sends update_event_filters when filters ACTUALLY change.
  //    Debounced to prevent rapid-fire updates.
  const eventFiltersKey = useMemo(() => JSON.stringify(eventFilters), [eventFilters]);
  useEffect(() => {
    if (!ws.isConnected || !isSubscribed) return;

    // IDEMPOTENCY: skip if filters haven't actually changed
    if (eventFiltersKey === lastSentFiltersRef.current) return;

    // DEBOUNCE: wait 300ms before sending (user might be typing/adjusting)
    if (filterDebounceRef.current) {
      clearTimeout(filterDebounceRef.current);
    }

    filterDebounceRef.current = setTimeout(() => {
      // Re-check idempotency after debounce
      const currentKey = JSON.stringify(eventFiltersRef.current);
      if (currentKey === lastSentFiltersRef.current) return;

      const f = eventFiltersRef.current;
      const df = defaultFilters;
      // Build update message with ALL filter fields (null = clear filter)
      const updateMsg: Record<string, any> = {
        action: 'update_event_filters',
        sub_id: subIdRef.current,
      };
      const uF = (k: string, v: number | undefined) => { updateMsg[k] = v ?? null; };
      const uS = (k: string, v: string | undefined) => { updateMsg[k] = v || null; };
      // Reuse same numericFilters array pattern as subscribe
      const uPairs: [string, number | undefined][] = [
        ['price_min', f.min_price ?? df?.min_price], ['price_max', f.max_price ?? df?.max_price],
        ['rvol_min', f.min_rvol ?? df?.min_rvol], ['rvol_max', f.max_rvol ?? df?.max_rvol],
        ['change_min', f.min_change_percent ?? df?.min_change_percent], ['change_max', f.max_change_percent ?? df?.max_change_percent],
        ['volume_min', f.min_volume ?? df?.min_volume], ['volume_max', f.max_volume ?? df?.max_volume],
        ['market_cap_min', f.min_market_cap ?? df?.min_market_cap], ['market_cap_max', f.max_market_cap ?? df?.max_market_cap],
        ['gap_percent_min', f.min_gap_percent ?? df?.min_gap_percent], ['gap_percent_max', f.max_gap_percent ?? df?.max_gap_percent],
        ['change_from_open_min', f.min_change_from_open ?? df?.min_change_from_open], ['change_from_open_max', f.max_change_from_open ?? df?.max_change_from_open],
        ['float_shares_min', f.min_float_shares ?? df?.min_float_shares], ['float_shares_max', f.max_float_shares ?? df?.max_float_shares],
        ['rsi_min', f.min_rsi ?? df?.min_rsi], ['rsi_max', f.max_rsi ?? df?.max_rsi],
        ['atr_percent_min', f.min_atr_percent ?? df?.min_atr_percent], ['atr_percent_max', f.max_atr_percent ?? df?.max_atr_percent],
        ['vwap_min', f.min_vwap], ['vwap_max', f.max_vwap],
        ['vol_1min_min', f.min_vol_1min], ['vol_1min_max', f.max_vol_1min],
        ['vol_5min_min', f.min_vol_5min], ['vol_5min_max', f.max_vol_5min],
        ['vol_10min_min', f.min_vol_10min], ['vol_10min_max', f.max_vol_10min],
        ['vol_15min_min', f.min_vol_15min], ['vol_15min_max', f.max_vol_15min],
        ['vol_30min_min', f.min_vol_30min], ['vol_30min_max', f.max_vol_30min],
        ['vol_1min_pct_min', f.min_vol_1min_pct], ['vol_1min_pct_max', f.max_vol_1min_pct],
        ['vol_5min_pct_min', f.min_vol_5min_pct], ['vol_5min_pct_max', f.max_vol_5min_pct],
        ['vol_10min_pct_min', f.min_vol_10min_pct], ['vol_10min_pct_max', f.max_vol_10min_pct],
        ['vol_15min_pct_min', f.min_vol_15min_pct], ['vol_15min_pct_max', f.max_vol_15min_pct],
        ['vol_30min_pct_min', f.min_vol_30min_pct], ['vol_30min_pct_max', f.max_vol_30min_pct],
        ['range_2min_min', f.min_range_2min], ['range_2min_max', f.max_range_2min],
        ['range_5min_min', f.min_range_5min], ['range_5min_max', f.max_range_5min],
        ['range_15min_min', f.min_range_15min], ['range_15min_max', f.max_range_15min],
        ['range_30min_min', f.min_range_30min], ['range_30min_max', f.max_range_30min],
        ['range_60min_min', f.min_range_60min], ['range_60min_max', f.max_range_60min],
        ['range_120min_min', f.min_range_120min], ['range_120min_max', f.max_range_120min],
        ['range_2min_pct_min', f.min_range_2min_pct], ['range_2min_pct_max', f.max_range_2min_pct],
        ['range_5min_pct_min', f.min_range_5min_pct], ['range_5min_pct_max', f.max_range_5min_pct],
        ['range_15min_pct_min', f.min_range_15min_pct], ['range_15min_pct_max', f.max_range_15min_pct],
        ['range_30min_pct_min', f.min_range_30min_pct], ['range_30min_pct_max', f.max_range_30min_pct],
        ['range_60min_pct_min', f.min_range_60min_pct], ['range_60min_pct_max', f.max_range_60min_pct],
        ['range_120min_pct_min', f.min_range_120min_pct], ['range_120min_pct_max', f.max_range_120min_pct],
        ['chg_1min_min', f.min_chg_1min], ['chg_1min_max', f.max_chg_1min],
        ['chg_5min_min', f.min_chg_5min], ['chg_5min_max', f.max_chg_5min],
        ['chg_10min_min', f.min_chg_10min], ['chg_10min_max', f.max_chg_10min],
        ['chg_15min_min', f.min_chg_15min], ['chg_15min_max', f.max_chg_15min],
        ['chg_30min_min', f.min_chg_30min], ['chg_30min_max', f.max_chg_30min],
        ['chg_60min_min', f.min_chg_60min], ['chg_60min_max', f.max_chg_60min],
        ['shares_outstanding_min', f.min_shares_outstanding], ['shares_outstanding_max', f.max_shares_outstanding],
        ['bid_min', f.min_bid], ['bid_max', f.max_bid],
        ['ask_min', f.min_ask], ['ask_max', f.max_ask],
        ['bid_size_min', f.min_bid_size], ['bid_size_max', f.max_bid_size],
        ['ask_size_min', f.min_ask_size], ['ask_size_max', f.max_ask_size],
        ['spread_min', f.min_spread], ['spread_max', f.max_spread],
        ['sma_5_min', f.min_sma_5], ['sma_5_max', f.max_sma_5],
        ['sma_8_min', f.min_sma_8], ['sma_8_max', f.max_sma_8],
        ['sma_20_min', f.min_sma_20], ['sma_20_max', f.max_sma_20],
        ['sma_50_min', f.min_sma_50], ['sma_50_max', f.max_sma_50],
        ['sma_200_min', f.min_sma_200], ['sma_200_max', f.max_sma_200],
        ['macd_line_min', f.min_macd_line], ['macd_line_max', f.max_macd_line],
        ['macd_hist_min', f.min_macd_hist], ['macd_hist_max', f.max_macd_hist],
        ['stoch_k_min', f.min_stoch_k], ['stoch_k_max', f.max_stoch_k],
        ['stoch_d_min', f.min_stoch_d], ['stoch_d_max', f.max_stoch_d],
        ['adx_14_min', f.min_adx_14], ['adx_14_max', f.max_adx_14],
        ['bb_upper_min', f.min_bb_upper], ['bb_upper_max', f.max_bb_upper],
        ['bb_lower_min', f.min_bb_lower], ['bb_lower_max', f.max_bb_lower],
        ['daily_sma_20_min', f.min_daily_sma_20], ['daily_sma_20_max', f.max_daily_sma_20],
        ['daily_sma_50_min', f.min_daily_sma_50], ['daily_sma_50_max', f.max_daily_sma_50],
        ['daily_sma_200_min', f.min_daily_sma_200], ['daily_sma_200_max', f.max_daily_sma_200],
        ['daily_rsi_min', f.min_daily_rsi], ['daily_rsi_max', f.max_daily_rsi],
        ['high_52w_min', f.min_high_52w], ['high_52w_max', f.max_high_52w],
        ['low_52w_min', f.min_low_52w], ['low_52w_max', f.max_low_52w],
        ['trades_today_min', f.min_trades_today], ['trades_today_max', f.max_trades_today],
        ['trades_z_score_min', f.min_trades_z_score], ['trades_z_score_max', f.max_trades_z_score],
        // === NEW: Computed derived fields ===
        ['dollar_volume_min', f.min_dollar_volume], ['dollar_volume_max', f.max_dollar_volume],
        ['todays_range_min', f.min_todays_range], ['todays_range_max', f.max_todays_range],
        ['todays_range_pct_min', f.min_todays_range_pct], ['todays_range_pct_max', f.max_todays_range_pct],
        ['bid_ask_ratio_min', f.min_bid_ask_ratio], ['bid_ask_ratio_max', f.max_bid_ask_ratio],
        ['float_turnover_min', f.min_float_turnover], ['float_turnover_max', f.max_float_turnover],
        ['dist_from_vwap_min', f.min_dist_from_vwap], ['dist_from_vwap_max', f.max_dist_from_vwap],
        ['dist_sma_5_min', f.min_dist_sma_5], ['dist_sma_5_max', f.max_dist_sma_5],
        ['dist_sma_8_min', f.min_dist_sma_8], ['dist_sma_8_max', f.max_dist_sma_8],
        ['dist_sma_20_min', f.min_dist_sma_20], ['dist_sma_20_max', f.max_dist_sma_20],
        ['dist_sma_50_min', f.min_dist_sma_50], ['dist_sma_50_max', f.max_dist_sma_50],
        ['dist_sma_200_min', f.min_dist_sma_200], ['dist_sma_200_max', f.max_dist_sma_200],
        ['pos_in_range_min', f.min_pos_in_range], ['pos_in_range_max', f.max_pos_in_range],
        ['below_high_min', f.min_below_high], ['below_high_max', f.max_below_high],
        ['above_low_min', f.min_above_low], ['above_low_max', f.max_above_low],
        ['pos_of_open_min', f.min_pos_of_open], ['pos_of_open_max', f.max_pos_of_open],
        ['prev_day_volume_min', f.min_prev_day_volume], ['prev_day_volume_max', f.max_prev_day_volume],
        // Multi-day changes
        ['change_1d_min', f.min_change_1d], ['change_1d_max', f.max_change_1d],
        ['change_3d_min', f.min_change_3d], ['change_3d_max', f.max_change_3d],
        ['change_5d_min', f.min_change_5d], ['change_5d_max', f.max_change_5d],
        ['change_10d_min', f.min_change_10d], ['change_10d_max', f.max_change_10d],
        ['change_20d_min', f.min_change_20d], ['change_20d_max', f.max_change_20d],
        // Average daily volumes
        ['avg_volume_5d_min', f.min_avg_volume_5d], ['avg_volume_5d_max', f.max_avg_volume_5d],
        ['avg_volume_10d_min', f.min_avg_volume_10d], ['avg_volume_10d_max', f.max_avg_volume_10d],
        ['avg_volume_20d_min', f.min_avg_volume_20d], ['avg_volume_20d_max', f.max_avg_volume_20d],
        // Distance from daily SMAs
        ['dist_daily_sma_20_min', f.min_dist_daily_sma_20], ['dist_daily_sma_20_max', f.max_dist_daily_sma_20],
        ['dist_daily_sma_50_min', f.min_dist_daily_sma_50], ['dist_daily_sma_50_max', f.max_dist_daily_sma_50],
        // 52w distances
        ['from_52w_high_min', f.min_from_52w_high], ['from_52w_high_max', f.max_from_52w_high],
        ['from_52w_low_min', f.min_from_52w_low], ['from_52w_low_max', f.max_from_52w_low],
        // Daily ADX / ATR / BB position
        ['daily_adx_14_min', f.min_daily_adx_14], ['daily_adx_14_max', f.max_daily_adx_14],
        ['daily_atr_percent_min', f.min_daily_atr_percent], ['daily_atr_percent_max', f.max_daily_atr_percent],
        ['daily_bb_position_min', f.min_daily_bb_position], ['daily_bb_position_max', f.max_daily_bb_position],
        // Scanner-aligned filters
        ['volume_today_pct_min', f.min_volume_today_pct], ['volume_today_pct_max', f.max_volume_today_pct],
        ['minute_volume_min', f.min_minute_volume],
        ['price_from_high_min', f.min_price_from_high], ['price_from_high_max', f.max_price_from_high],
        ['price_from_low_min', f.min_price_from_low], ['price_from_low_max', f.max_price_from_low],
        ['price_from_intraday_high_min', f.min_price_from_intraday_high], ['price_from_intraday_high_max', f.max_price_from_intraday_high],
        ['price_from_intraday_low_min', f.min_price_from_intraday_low], ['price_from_intraday_low_max', f.max_price_from_intraday_low],
        ['distance_from_nbbo_min', f.min_distance_from_nbbo], ['distance_from_nbbo_max', f.max_distance_from_nbbo],
        ['premarket_change_percent_min', f.min_premarket_change_percent], ['premarket_change_percent_max', f.max_premarket_change_percent],
        ['postmarket_change_percent_min', f.min_postmarket_change_percent], ['postmarket_change_percent_max', f.max_postmarket_change_percent],
        ['avg_volume_3m_min', f.min_avg_volume_3m], ['avg_volume_3m_max', f.max_avg_volume_3m],
        ['atr_min', f.min_atr], ['atr_max', f.max_atr],
        ['ema_20_min', f.min_ema_20], ['ema_20_max', f.max_ema_20],
        ['ema_50_min', f.min_ema_50], ['ema_50_max', f.max_ema_50],
      ];
      for (const [k, v] of uPairs) uF(k, v);
      uS('security_type', f.security_type);
      uS('sector', f.sector);
      uS('industry', f.industry);
      updateMsg.symbols_include = f.symbols_include || null;
      updateMsg.symbols_exclude = f.symbols_exclude || null;
      // Per-alert quality thresholds (aq:event_type = minQuality)
      for (const [k, v] of Object.entries(f)) {
        if (k.startsWith('aq:')) updateMsg[k] = v ?? null;
      }
      ws.send(updateMsg);

      lastSentFiltersRef.current = currentKey;
      filterDebounceRef.current = null;
    }, 300);

    return () => {
      if (filterDebounceRef.current) {
        clearTimeout(filterDebounceRef.current);
        filterDebounceRef.current = null;
      }
    };
  }, [eventFiltersKey, ws.isConnected, isSubscribed, ws.send]); // eslint-disable-line react-hooks/exhaustive-deps

  // ========================================================================
  // INFINITE SCROLL — request older events from server
  // ========================================================================

  const loadOlderEvents = useCallback(() => {
    if (!ws.isConnected || !isSubscribed || loadingMore || !hasMore) return;
    if (!oldestEventTsRef.current) return;

    setLoadingMore(true);
    ws.send({
      action: 'load_older_events',
      sub_id: subIdRef.current,
      before_ts: oldestEventTsRef.current,
      limit: 200,
    });
  }, [ws.isConnected, ws.send, isSubscribed, loadingMore, hasMore]);

  // ========================================================================
  // TABLE CONFIGURATION
  // ========================================================================

  const data = useMemo(() => filteredEvents, [filteredEvents]);

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'row_number',
        header: '#',
        size: 40,
        minSize: 35,
        maxSize: 50,
        enableSorting: false,
        cell: (info) => (
          <div className="text-center font-semibold text-muted-fg">
            {info.row.index + 1}
          </div>
        ),
      }),
      columnHelper.accessor('timestamp', {
        header: 'Time',
        size: 70,
        minSize: 60,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const ts = info.getValue();
          const date = new Date(ts);
          const timeStr = date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZone: getUserTimezone(),
          });
          const relativeTime = formatDistanceToNowStrict(date, { addSuffix: false });
          return (
            <div className="font-mono text-foreground/80" title={relativeTime + ' ago'}>
              {timeStr}
            </div>
          );
        },
      }),
      columnHelper.accessor('symbol', {
        header: 'Symbol',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => (
          <div
            className="font-bold text-primary cursor-pointer hover:text-primary hover:underline transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              const symbol = info.getValue();
              const currentLinkGroup = linkGroupRef.current;
              if (currentLinkGroup) {
                if (hasSubscribersRef.current()) {
                  publishTickerRef.current(symbol);
                } else {
                  const sw = typeof window !== 'undefined' ? window.innerWidth : 1920;
                  const sh = typeof window !== 'undefined' ? window.innerHeight : 1080;
                  openWindowRef.current({
                    title: `Chart: ${symbol}`,
                    content: React.createElement(
                      require('@/components/chart/ChartContent').ChartContent,
                      { ticker: symbol }
                    ),
                    width: 900, height: 600,
                    x: Math.max(50, sw / 2 - 450), y: Math.max(80, sh / 2 - 300),
                    minWidth: 600, minHeight: 400,
                    linkGroup: currentLinkGroup,
                  } as any);
                }
              } else {
                executeTickerCommandRef.current(symbol, 'chart');
              }
            }}
            title="Click to open Chart"
          >
            {info.getValue()}
          </div>
        ),
      }),
      columnHelper.accessor('event_type', {
        header: 'Event',
        size: 90,
        minSize: 75,
        maxSize: 120,
        enableSorting: true,
        cell: (info) => {
          const eventType = info.getValue();
          const config = getEventTypeConfig(eventType);
          const IconComponent = config.icon;
          return (
            <div className={`flex items-center gap-1 ${config.color} font-medium`}>
              <IconComponent className="w-3 h-3" />
              <span>{config.label}</span>
            </div>
          );
        },
      }),
      columnHelper.accessor('price', {
        header: 'Price',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const price = info.getValue();
          return (
            <div className="font-mono text-foreground font-medium">
              ${price?.toFixed(2) || '-'}
            </div>
          );
        },
      }),
      columnHelper.accessor('change_percent', {
        header: 'Chg%',
        size: 65,
        minSize: 55,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) {
            return <div className="text-muted-fg">-</div>;
          }
          const isPositive = value > 0;
          return (
            <div className={`font-mono font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
              {formatPercent(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('volume', {
        header: 'Volume',
        size: 75,
        minSize: 60,
        maxSize: 100,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return (
            <div className="font-mono text-foreground/80">
              {formatNumber(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('rvol', {
        header: 'RVOL',
        size: 60,
        minSize: 50,
        maxSize: 80,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return (
            <div className={`font-mono font-semibold ${value > 3 ? 'text-primary' : value > 1.5 ? 'text-primary' : 'text-muted-fg'}`}>
              {value.toFixed(1)}x
            </div>
          );
        },
      }),
      columnHelper.accessor('gap_percent', {
        header: 'Gap%',
        size: 60,
        minSize: 50,
        maxSize: 80,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return (
            <div className={`font-mono font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
              {formatPercent(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('change_from_open', {
        header: 'vs Open',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return (
            <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
              {formatPercent(value)}
            </div>
          );
        },
      }),
      columnHelper.accessor('market_cap', {
        header: 'MCap',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          const formatted = value >= 1e12
            ? `$${(value / 1e12).toFixed(1)}T`
            : value >= 1e9
              ? `$${(value / 1e9).toFixed(1)}B`
              : value >= 1e6
                ? `$${(value / 1e6).toFixed(0)}M`
                : `$${formatNumber(value)}`;
          return <div className="font-mono text-foreground/80">{formatted}</div>;
        },
      }),
      columnHelper.accessor('atr_percent', {
        header: 'ATR%',
        size: 60,
        minSize: 50,
        maxSize: 75,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          return (
            <div className={`font-mono ${value > 5 ? 'text-orange-600 font-semibold' : 'text-muted-fg'}`}>
              {value.toFixed(1)}%
            </div>
          );
        },
      }),
      columnHelper.accessor('vwap', {
        header: 'VWAP',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      // ═══════════════════════════════════════════════════════════════
      // NUEVAS COLUMNAS - Ocultas por defecto
      // ═══════════════════════════════════════════════════════════════

      // ── Campos de Evento ──
      columnHelper.accessor('prev_value', {
        header: 'Prev Val',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      columnHelper.accessor('new_value', {
        header: 'New Val',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      columnHelper.accessor('delta', {
        header: 'Delta',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {isPositive ? '+' : ''}{value.toFixed(2)}
          </div>;
        },
      }),

      columnHelper.accessor('delta_percent', {
        header: 'Delta %',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatPercent(value)}
          </div>;
        },
      }),

      // ── Contexto Básico ──
      columnHelper.accessor('open_price', {
        header: 'Open',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      columnHelper.accessor('prev_close', {
        header: 'Prev Close',
        size: 75,
        minSize: 60,
        maxSize: 95,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      columnHelper.accessor('intraday_high', {
        header: 'High',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-green-600">${value.toFixed(2)}</div>;
        },
      }),

      columnHelper.accessor('intraday_low', {
        header: 'Low',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-red-600">${value.toFixed(2)}</div>;
        },
      }),

      // ── Ventanas de Tiempo ──
      columnHelper.accessor('chg_1min', {
        header: 'Chg 1m',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatPercent(value)}
          </div>;
        },
      }),

      columnHelper.accessor('chg_5min', {
        header: 'Chg 5m',
        size: 65,
        minSize: 50,
        maxSize: 85,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatPercent(value)}
          </div>;
        },
      }),

      columnHelper.accessor('chg_10min', {
        header: 'Chg 10m',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatPercent(value)}
          </div>;
        },
      }),

      columnHelper.accessor('chg_15min', {
        header: 'Chg 15m',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatPercent(value)}
          </div>;
        },
      }),

      columnHelper.accessor('chg_30min', {
        header: 'Chg 30m',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const isPositive = value > 0;
          return <div className={`font-mono ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
            {formatPercent(value)}
          </div>;
        },
      }),

      columnHelper.accessor('vol_1min', {
        header: 'Vol 1m',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">{formatNumber(value)}</div>;
        },
      }),

      columnHelper.accessor('vol_5min', {
        header: 'Vol 5m',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">{formatNumber(value)}</div>;
        },
      }),

      // ── Indicadores Técnicos ──
      columnHelper.accessor('float_shares', {
        header: 'Float',
        size: 75,
        minSize: 60,
        maxSize: 100,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">{formatNumber(value)}</div>;
        },
      }),

      columnHelper.accessor('rsi', {
        header: 'RSI',
        size: 60,
        minSize: 50,
        maxSize: 80,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const colorClass = value > 70 ? 'text-red-600 font-semibold' : value < 30 ? 'text-green-600 font-semibold' : 'text-foreground/80';
          return <div className={`font-mono ${colorClass}`}>{value.toFixed(1)}</div>;
        },
      }),

      columnHelper.accessor('ema_20', {
        header: 'EMA(20)',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      columnHelper.accessor('ema_50', {
        header: 'EMA(50)',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="font-mono text-foreground/80">${value.toFixed(2)}</div>;
        },
      }),

      // ── Fundamentales ──
      columnHelper.accessor('security_type', {
        header: 'Type',
        size: 70,
        minSize: 55,
        maxSize: 90,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="text-foreground font-medium">{value}</div>;
        },
      }),

      columnHelper.accessor('sector', {
        header: 'Sector',
        size: 90,
        minSize: 75,
        maxSize: 120,
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (!value) return <div className="text-muted-fg">-</div>;
          return <div className="text-foreground">{value}</div>;
        },
      }),

      // ═══════════════════════════════════════════════════════════════
      // COLUMNAS ADICIONALES - Auto-generadas desde shared-column-configs
      // ═══════════════════════════════════════════════════════════════

      columnHelper.accessor('chg_60min', {
        ...getColumnConfig('chg_60min'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('chg_60min');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_10min', {
        ...getColumnConfig('vol_10min'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_10min');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_15min', {
        ...getColumnConfig('vol_15min'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_15min');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_30min', {
        ...getColumnConfig('vol_30min'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_30min');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_1min_pct', {
        ...getColumnConfig('vol_1min_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_1min_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = value >= 200 ? 'text-green-600 font-semibold' : value >= 100 ? 'text-foreground/80' : 'text-red-500';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_5min_pct', {
        ...getColumnConfig('vol_5min_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_5min_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = value >= 200 ? 'text-green-600 font-semibold' : value >= 100 ? 'text-foreground/80' : 'text-red-500';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_10min_pct', {
        ...getColumnConfig('vol_10min_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_10min_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = value >= 200 ? 'text-green-600 font-semibold' : value >= 100 ? 'text-foreground/80' : 'text-red-500';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_15min_pct', {
        ...getColumnConfig('vol_15min_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_15min_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = value >= 200 ? 'text-green-600 font-semibold' : value >= 100 ? 'text-foreground/80' : 'text-red-500';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('vol_30min_pct', {
        ...getColumnConfig('vol_30min_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('vol_30min_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = value >= 200 ? 'text-green-600 font-semibold' : value >= 100 ? 'text-foreground/80' : 'text-red-500';
          return <div className={'font-mono ' + cellClass}>{formatted}</div>;
        },
      }),

      ...(['range_2min', 'range_5min', 'range_15min', 'range_30min', 'range_60min', 'range_120min'] as const).map(key => (
        columnHelper.accessor(key, {
          ...getColumnConfig(key),
          enableSorting: true,
          cell: (info) => {
            const value = info.getValue();
            if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
            const config = getColumnConfig(key);
            const formatted = formatValue(value, config.format, config.suffix);
            return <div className="font-mono text-foreground/80">{formatted}</div>;
          },
        })
      )),
      ...(['range_2min_pct', 'range_5min_pct', 'range_15min_pct', 'range_30min_pct', 'range_60min_pct', 'range_120min_pct'] as const).map(key => (
        columnHelper.accessor(key, {
          ...getColumnConfig(key),
          enableSorting: true,
          cell: (info) => {
            const value = info.getValue();
            if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
            const config = getColumnConfig(key);
            const formatted = formatValue(value, config.format, config.suffix);
            const cellClass = value >= 200 ? 'text-green-600 font-semibold' : value >= 100 ? 'text-foreground/80' : 'text-red-500';
            return <div className={'font-mono ' + cellClass}>{formatted}</div>;
          },
        })
      )),

      columnHelper.accessor('bid', {
        ...getColumnConfig('bid'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('bid');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('ask', {
        ...getColumnConfig('ask'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('ask');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('bid_size', {
        ...getColumnConfig('bid_size'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('bid_size');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('ask_size', {
        ...getColumnConfig('ask_size'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('ask_size');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('spread', {
        ...getColumnConfig('spread'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('spread');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('shares_outstanding', {
        ...getColumnConfig('shares_outstanding'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('shares_outstanding');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('sma_5', {
        ...getColumnConfig('sma_5'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('sma_5');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('sma_8', {
        ...getColumnConfig('sma_8'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('sma_8');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('sma_20', {
        ...getColumnConfig('sma_20'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('sma_20');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('sma_50', {
        ...getColumnConfig('sma_50'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('sma_50');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('sma_200', {
        ...getColumnConfig('sma_200'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('sma_200');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('macd_line', {
        ...getColumnConfig('macd_line'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('macd_line');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('macd_hist', {
        ...getColumnConfig('macd_hist'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('macd_hist');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('stoch_k', {
        ...getColumnConfig('stoch_k'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('stoch_k');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('stoch_d', {
        ...getColumnConfig('stoch_d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('stoch_d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('adx_14', {
        ...getColumnConfig('adx_14'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('adx_14');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('bb_upper', {
        ...getColumnConfig('bb_upper'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('bb_upper');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('bb_lower', {
        ...getColumnConfig('bb_lower'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('bb_lower');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('atr', {
        ...getColumnConfig('atr'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('atr');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_sma_20', {
        ...getColumnConfig('daily_sma_20'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_sma_20');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_sma_50', {
        ...getColumnConfig('daily_sma_50'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_sma_50');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_sma_200', {
        ...getColumnConfig('daily_sma_200'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_sma_200');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_rsi', {
        ...getColumnConfig('daily_rsi'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_rsi');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_adx_14', {
        ...getColumnConfig('daily_adx_14'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_adx_14');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_atr_percent', {
        ...getColumnConfig('daily_atr_percent'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_atr_percent');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('daily_bb_position', {
        ...getColumnConfig('daily_bb_position'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('daily_bb_position');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('high_52w', {
        ...getColumnConfig('high_52w'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('high_52w');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('low_52w', {
        ...getColumnConfig('low_52w'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('low_52w');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('from_52w_high', {
        ...getColumnConfig('from_52w_high'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('from_52w_high');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('from_52w_low', {
        ...getColumnConfig('from_52w_low'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('from_52w_low');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dollar_volume', {
        ...getColumnConfig('dollar_volume'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dollar_volume');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('todays_range', {
        ...getColumnConfig('todays_range'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('todays_range');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('todays_range_pct', {
        ...getColumnConfig('todays_range_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('todays_range_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('bid_ask_ratio', {
        ...getColumnConfig('bid_ask_ratio'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('bid_ask_ratio');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('float_turnover', {
        ...getColumnConfig('float_turnover'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('float_turnover');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('pos_in_range', {
        ...getColumnConfig('pos_in_range'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('pos_in_range');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('below_high', {
        ...getColumnConfig('below_high'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('below_high');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('above_low', {
        ...getColumnConfig('above_low'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('above_low');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('pos_of_open', {
        ...getColumnConfig('pos_of_open'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('pos_of_open');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('prev_day_volume', {
        ...getColumnConfig('prev_day_volume'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('prev_day_volume');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_from_vwap', {
        ...getColumnConfig('dist_from_vwap'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_from_vwap');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_sma_5', {
        ...getColumnConfig('dist_sma_5'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_sma_5');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_sma_8', {
        ...getColumnConfig('dist_sma_8'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_sma_8');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_sma_20', {
        ...getColumnConfig('dist_sma_20'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_sma_20');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_sma_50', {
        ...getColumnConfig('dist_sma_50'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_sma_50');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_sma_200', {
        ...getColumnConfig('dist_sma_200'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_sma_200');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_daily_sma_20', {
        ...getColumnConfig('dist_daily_sma_20'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_daily_sma_20');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('dist_daily_sma_50', {
        ...getColumnConfig('dist_daily_sma_50'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('dist_daily_sma_50');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('change_1d', {
        ...getColumnConfig('change_1d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('change_1d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('change_3d', {
        ...getColumnConfig('change_3d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('change_3d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('change_5d', {
        ...getColumnConfig('change_5d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('change_5d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('change_10d', {
        ...getColumnConfig('change_10d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('change_10d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('change_20d', {
        ...getColumnConfig('change_20d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('change_20d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('avg_volume_5d', {
        ...getColumnConfig('avg_volume_5d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('avg_volume_5d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('avg_volume_10d', {
        ...getColumnConfig('avg_volume_10d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('avg_volume_10d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('avg_volume_20d', {
        ...getColumnConfig('avg_volume_20d'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('avg_volume_20d');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('avg_volume_3m', {
        ...getColumnConfig('avg_volume_3m'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('avg_volume_3m');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('industry', {
        ...getColumnConfig('industry'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('industry');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('volume_today_pct', {
        ...getColumnConfig('volume_today_pct'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('volume_today_pct');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('price_from_high', {
        ...getColumnConfig('price_from_high'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('price_from_high');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('distance_from_nbbo', {
        ...getColumnConfig('distance_from_nbbo'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('distance_from_nbbo');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('premarket_change_percent', {
        ...getColumnConfig('premarket_change_percent'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('premarket_change_percent');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('postmarket_change_percent', {
        ...getColumnConfig('postmarket_change_percent'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('postmarket_change_percent');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('trades_today', {
        ...getColumnConfig('trades_today'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('trades_today');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),

      columnHelper.accessor('trades_z_score', {
        ...getColumnConfig('trades_z_score'),
        enableSorting: true,
        cell: (info) => {
          const value = info.getValue();
          if (value === undefined || value === null) return <div className="text-muted-fg">-</div>;
          const config = getColumnConfig('trades_z_score');
          const formatted = formatValue(value, config.format, config.suffix);
          const cellClass = config.cellClass ? config.cellClass(value) : 'text-foreground/80';
          return <div className={`font-mono ${cellClass}`}>{formatted}</div>;
        },
      }),
    ],
    [] // Columns static - link group accessed via refs
  );

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnOrder,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableColumnResizing: true,
    columnResizeMode: 'onChange',
  });

  // ========================================================================
  // RENDER
  // ========================================================================

  const handleResetToDefaults = useCallback(() => {
    setColumnVisibility(DEFAULT_EVENT_COLUMN_VISIBILITY);
    setColumnOrder([]);
  }, []);

  // ---- Context menu system ----
  const ctxMenuRef = useRef<HTMLDivElement>(null);

  const openCtxAt = useCallback((x: number, y: number, symbol?: string) => {
    // Clamp to viewport so menu doesn't overflow
    const mx = Math.min(x, window.innerWidth - 200);
    const my = Math.min(y, window.innerHeight - 180);
    setCtxMenu({ x: mx, y: my, symbol });
  }, []);

  // Right-click on table rows
  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const tr = (e.target as HTMLElement).closest('tr');
    const symbol = tr?.querySelector('td:nth-child(2)')?.textContent?.trim();
    openCtxAt(e.clientX, e.clientY, symbol || undefined);
  }, [openCtxAt]);

  // Three-dot button in header (for trackpad / Mac users)
  const handleMenuButton = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    openCtxAt(rect.left, rect.bottom + 2);
  }, [openCtxAt]);

  // Close on mousedown outside menu
  useEffect(() => {
    if (!ctxMenu) return;
    const handle = (e: MouseEvent) => {
      if (ctxMenuRef.current && !ctxMenuRef.current.contains(e.target as Node)) {
        setCtxMenu(null);
      }
    };
    // Use timeout so the opening click doesn't immediately close
    const t = setTimeout(() => document.addEventListener('mousedown', handle), 0);
    return () => { clearTimeout(t); document.removeEventListener('mousedown', handle); };
  }, [ctxMenu]);

  const contextMenu = ctxMenu && (
    <div ref={ctxMenuRef}
      className="fixed z-[9999] bg-surface border border-border rounded shadow-lg py-1 min-w-[180px]"
      style={{ left: ctxMenu.x, top: ctxMenu.y }}
      onContextMenu={e => e.preventDefault()}
    >
      {ctxMenu.symbol && (
        <>
          <button onClick={() => { executeTickerCommandRef.current(ctxMenu.symbol!, 'chart'); setCtxMenu(null); }}
            className="w-full text-left px-3 py-1.5 text-foreground hover:bg-[var(--color-table-row-hover)] hover:text-primary">
            Trade {ctxMenu.symbol}
          </button>
          <div className="border-t border-border-subtle my-0.5" />
        </>
      )}
      <button onClick={() => { openConfigWindow(); setCtxMenu(null); }}
        className="w-full text-left px-3 py-1.5 text-foreground hover:bg-[var(--color-table-row-hover)] hover:text-primary">
        Configure...
      </button>
      <button onClick={() => { setEvents([]); setCtxMenu(null); }}
        className="w-full text-left px-3 py-1.5 text-foreground hover:bg-[var(--color-table-row-hover)] hover:text-primary">
        Clear
      </button>
      <div className="border-t border-border-subtle my-0.5" />
      <button onClick={() => { handleResetToDefaults(); setCtxMenu(null); }}
        className="w-full text-left px-3 py-1.5 text-foreground hover:bg-[var(--color-table-row-hover)] hover:text-primary">
        Reset columns
      </button>
    </div>
  );

  const rightActions = (
    <div className="flex items-center gap-1">
      <button onClick={handleMenuButton}
        className="p-0.5 rounded text-muted-fg hover:text-foreground/80 hover:bg-surface-hover transition-colors"
        title="Menu">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <circle cx="8" cy="3" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="8" cy="13" r="1.5" />
        </svg>
      </button>
      <TableSettings
        table={table}
        onResetToDefaults={handleResetToDefaults}
      />
    </div>
  );

  // Custom event types indicator
  const isCustom = customEventTypes.length > 0 && customEventTypes !== initialEventTypes;
  const displayTitle = isCustom
    ? categoryName + ' (' + customEventTypes.length + ' alerts)'
    : categoryName;

  // Open Strategy Builder (ConfigWindow) pre-loaded with current config
  const openConfigWindow = useCallback(() => {
    openWindow({
      title: 'Strategy Builder',
      content: (
        <ConfigWindow
          initialAlerts={customEventTypes}
          initialFilters={eventFilters}
          initialName={categoryName}
          initialTab="alerts"
          onCreateAlertWindow={(config: AlertWindowConfig) => {
            // Update THIS window's config instead of creating a new one
            setCustomEventTypes(config.eventTypes);
            const setAllFilters = useEventFiltersStore.getState().setAllFilters;
            setAllFilters(categoryId, config.filters);
          }}
        />
      ),
      width: 700,
      height: 550,
      x: 200,
      y: 130,
      minWidth: 500,
      minHeight: 400,
    });
  }, [openWindow, customEventTypes, eventFilters, categoryName, categoryId, setCustomEventTypes]);

  // Empty state — only show if subscribed AND no cached data to display
  if (events.length === 0 && isSubscribed && !hasCachedEvents) {
    return (
      <div className="h-full flex flex-row">
        <div className="flex-1 flex flex-col min-w-0" onContextMenu={handleContextMenu}>
          <MarketTableLayout
            title={displayTitle}
            isLive={ws.isConnected}
            listName={categoryId}
            onClose={closeCurrentWindow}
            rightActions={rightActions}
          />
          <div className="flex-1 flex items-center justify-center bg-surface-hover">
            <div className="text-center p-6">
              <Activity className="w-8 h-8 text-muted-fg mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-foreground mb-1">
                Waiting for events...
              </h3>
              <p className="text-muted-fg max-w-xs">
                {connectionError || 'Events will appear here in real-time as they occur.'}
              </p>
            </div>
          </div>
          {contextMenu}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-row">
      <div className="flex-1 min-w-0" onContextMenu={handleContextMenu}>
        <VirtualizedDataTable
          table={table}
          showResizeHandles={false}
          stickyHeader={true}
          isLoading={!isSubscribed && events.length === 0}
          estimateSize={18}
          overscan={10}
          enableVirtualization={true}
          onEndReached={loadOlderEvents}
          hasMore={hasMore}
          loadingMore={loadingMore}
          getRowClassName={(row: Row<MarketEvent>) => {
            const event = row.original;
            if (newEventIds.has(event.id)) {
              return 'new-ticker-flash';
            }
            return '';
          }}
        >
          <MarketTableLayout
            title={displayTitle}
            isLive={ws.isConnected}
            listName={categoryId}
            onClose={closeCurrentWindow}
            rightActions={rightActions}
          />
        </VirtualizedDataTable>
        {contextMenu}
      </div>
    </div>
  );
}
