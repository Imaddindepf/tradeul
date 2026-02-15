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

import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
} from '@tanstack/react-table';
import type { SortingState, Row, ColumnOrderState, VisibilityState } from '@tanstack/react-table';
import { formatNumber, formatPercent } from '@/lib/formatters';
import { VirtualizedDataTable } from '@/components/table/VirtualizedDataTable';
import { MarketTableLayout } from '@/components/table/MarketTableLayout';
import { TableSettings } from '@/components/table/TableSettings';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';
import { useCloseCurrentWindow, useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useEventFiltersStore } from '@/stores/useEventFiltersStore';
import type { ActiveEventFilters } from '@/stores/useEventFiltersStore';
import { formatDistanceToNowStrict } from 'date-fns';
import {
  TrendingUp,
  TrendingDown,
  Zap,
  BarChart3,
  CircleStop,
  Activity,
} from 'lucide-react';
import { ALERT_BY_EVENT_TYPE } from '@/lib/alert-catalog';
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
  intraday_high?: number;
  intraday_low?: number;
  // Time-window changes
  chg_1min?: number;
  chg_5min?: number;
  chg_10min?: number;
  chg_15min?: number;
  chg_30min?: number;
  vol_1min?: number;
  vol_5min?: number;
  // Daily indicators / fundamentals
  float_shares?: number;
  rsi?: number;
  ema_20?: number;
  ema_50?: number;
  metadata?: Record<string, unknown>;
}

// ============================================================================
// EVENT TYPE CONFIG
// ============================================================================

const EVENT_TYPE_CONFIG: Record<string, { label: string; color: string; icon: typeof Activity }> = {
  // Price
  'new_high': { label: 'New High', color: 'text-emerald-600', icon: TrendingUp },
  'new_low': { label: 'New Low', color: 'text-rose-600', icon: TrendingDown },
  'crossed_above_open': { label: '↑ Open', color: 'text-emerald-500', icon: TrendingUp },
  'crossed_below_open': { label: '↓ Open', color: 'text-rose-500', icon: TrendingDown },
  'crossed_above_prev_close': { label: '↑ Close', color: 'text-emerald-500', icon: TrendingUp },
  'crossed_below_prev_close': { label: '↓ Close', color: 'text-rose-500', icon: TrendingDown },
  // VWAP
  'vwap_cross_up': { label: 'VWAP ↑', color: 'text-blue-600', icon: Zap },
  'vwap_cross_down': { label: 'VWAP ↓', color: 'text-orange-600', icon: Zap },
  // Volume
  'rvol_spike': { label: 'RVOL 3x', color: 'text-purple-600', icon: BarChart3 },
  'volume_surge': { label: 'RVOL 5x', color: 'text-indigo-700 font-bold', icon: BarChart3 },
  'volume_spike_1min': { label: 'Vol Spike', color: 'text-purple-500', icon: BarChart3 },
  'unusual_prints': { label: 'Unusual', color: 'text-amber-600', icon: Activity },
  'block_trade': { label: 'Block', color: 'text-indigo-600', icon: BarChart3 },
  // Momentum
  'running_up': { label: 'Run ↑', color: 'text-emerald-700 font-bold', icon: TrendingUp },
  'running_down': { label: 'Run ↓', color: 'text-rose-700 font-bold', icon: TrendingDown },
  'percent_up_5': { label: '+5%', color: 'text-emerald-600', icon: TrendingUp },
  'percent_down_5': { label: '-5%', color: 'text-rose-600', icon: TrendingDown },
  'percent_up_10': { label: '+10%', color: 'text-emerald-700 font-bold', icon: TrendingUp },
  'percent_down_10': { label: '-10%', color: 'text-rose-700 font-bold', icon: TrendingDown },
  // Pullbacks
  'pullback_75_from_high': { label: 'PB 75% H', color: 'text-rose-500', icon: TrendingDown },
  'pullback_25_from_high': { label: 'PB 25% H', color: 'text-orange-500', icon: TrendingDown },
  'pullback_75_from_low': { label: 'Bounce 75%', color: 'text-emerald-500', icon: TrendingUp },
  'pullback_25_from_low': { label: 'Bounce 25%', color: 'text-cyan-500', icon: TrendingUp },
  // Gap
  'gap_up_reversal': { label: 'Gap↑ Rev', color: 'text-rose-600', icon: TrendingDown },
  'gap_down_reversal': { label: 'Gap↓ Rev', color: 'text-emerald-600', icon: TrendingUp },
  // Halts
  'halt': { label: 'HALT', color: 'text-red-700 font-bold', icon: CircleStop },
  'resume': { label: 'RESUME', color: 'text-green-600', icon: Activity },
  // Phase 1B: Intraday EMA Crosses
  'crossed_above_ema20': { label: 'EMA20 ↑', color: 'text-emerald-500', icon: TrendingUp },
  'crossed_below_ema20': { label: 'EMA20 ↓', color: 'text-rose-500', icon: TrendingDown },
  'crossed_above_ema50': { label: 'EMA50 ↑', color: 'text-emerald-600', icon: TrendingUp },
  'crossed_below_ema50': { label: 'EMA50 ↓', color: 'text-rose-600', icon: TrendingDown },
  // Phase 2: Bollinger
  'bb_upper_breakout': { label: 'BB Upper', color: 'text-emerald-600', icon: TrendingUp },
  'bb_lower_breakdown': { label: 'BB Lower', color: 'text-rose-600', icon: TrendingDown },
  // Phase 2: Daily Levels
  'crossed_daily_high_resistance': { label: 'Day High', color: 'text-emerald-600', icon: TrendingUp },
  'crossed_daily_low_support': { label: 'Day Low', color: 'text-rose-600', icon: TrendingDown },
  'false_gap_up_retracement': { label: 'False Gap Up', color: 'text-rose-500', icon: TrendingDown },
  'false_gap_down_retracement': { label: 'False Gap Dn', color: 'text-emerald-500', icon: TrendingUp },
  // Phase 2: Confirmed
  'running_up_sustained': { label: 'Run Up Sust', color: 'text-emerald-700 font-bold', icon: TrendingUp },
  'running_down_sustained': { label: 'Run Dn Sust', color: 'text-rose-700 font-bold', icon: TrendingDown },
  'running_up_confirmed': { label: 'Run Up Conf', color: 'text-emerald-700 font-bold', icon: TrendingUp },
  'running_down_confirmed': { label: 'Run Dn Conf', color: 'text-rose-700 font-bold', icon: TrendingDown },
  'vwap_divergence_up': { label: 'VWAP Div Up', color: 'text-emerald-600', icon: TrendingUp },
  'vwap_divergence_down': { label: 'VWAP Div Dn', color: 'text-rose-600', icon: TrendingDown },
  'crossed_above_open_confirmed': { label: 'Open Up Conf', color: 'text-emerald-600', icon: TrendingUp },
  'crossed_below_open_confirmed': { label: 'Open Dn Conf', color: 'text-rose-600', icon: TrendingDown },
  'crossed_above_close_confirmed': { label: 'Close Up Conf', color: 'text-emerald-600', icon: TrendingUp },
  'crossed_below_close_confirmed': { label: 'Close Dn Conf', color: 'text-rose-600', icon: TrendingDown },
  // Phase 2: Pre/Post Market
  'pre_market_high': { label: 'Pre High', color: 'text-emerald-500', icon: TrendingUp },
  'pre_market_low': { label: 'Pre Low', color: 'text-rose-500', icon: TrendingDown },
  'post_market_high': { label: 'Post High', color: 'text-emerald-500', icon: TrendingUp },
  'post_market_low': { label: 'Post Low', color: 'text-rose-500', icon: TrendingDown },
};

// Default column visibility for event tables
const DEFAULT_EVENT_COLUMN_VISIBILITY: VisibilityState = {
  row_number: true,
  timestamp: true,
  symbol: true,
  event_type: true,
  price: true,
  change_percent: true,
  volume: true,
  rvol: true,
  gap_percent: false,
  change_from_open: false,
  market_cap: false,
  atr_percent: false,
  vwap: false,
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
  return {
    id: d.id || `${d.symbol}_${d.event_type}_${d.timestamp}`,
    symbol: d.symbol,
    event_type: d.event_type,
    timestamp: d.timestamp,
    price: d.price,
    prev_value: d.prev_value ?? undefined,
    new_value: d.new_value ?? undefined,
    delta: d.delta ?? undefined,
    delta_percent: d.delta_percent ?? undefined,
    change_percent: d.change_percent ?? undefined,
    volume: d.volume ?? undefined,
    rvol: d.rvol ?? undefined,
    market_cap: d.market_cap ?? undefined,
    gap_percent: d.gap_percent ?? undefined,
    change_from_open: d.change_from_open ?? undefined,
    open_price: d.open_price ?? undefined,
    prev_close: d.prev_close ?? undefined,
    vwap: d.vwap ?? undefined,
    atr_percent: d.atr_percent ?? undefined,
    intraday_high: d.intraday_high ?? undefined,
    intraday_low: d.intraday_low ?? undefined,
    chg_1min: d.chg_1min ?? undefined,
    chg_5min: d.chg_5min ?? undefined,
    chg_10min: d.chg_10min ?? undefined,
    chg_15min: d.chg_15min ?? undefined,
    chg_30min: d.chg_30min ?? undefined,
    vol_1min: d.vol_1min ?? undefined,
    vol_5min: d.vol_5min ?? undefined,
    float_shares: d.float_shares ?? undefined,
    rsi: d.rsi ?? undefined,
    ema_20: d.ema_20 ?? undefined,
    ema_50: d.ema_50 ?? undefined,
    metadata: d.details || d.metadata,
  };
}

/**
 * Client-side filter: returns true if event passes ALL active filters.
 * Centralised to avoid duplication between market_event and events_snapshot.
 */
function passesFilters(e: MarketEvent, f: import('@/stores/useEventFiltersStore').ActiveEventFilters): boolean {
  // Helper: min/max numeric check (undefined field → exclude when filter active)
  const chk = (val: number | undefined, min: number | undefined, max: number | undefined): boolean => {
    if (min !== undefined && (val === undefined || val < min)) return false;
    if (max !== undefined && (val === undefined || val > max)) return false;
    return true;
  };
  if (!chk(e.price, f.min_price, f.max_price)) return false;
  if (!chk(e.change_percent, f.min_change_percent, f.max_change_percent)) return false;
  if (!chk(e.rvol, f.min_rvol, f.max_rvol)) return false;
  if (!chk(e.volume, f.min_volume, f.max_volume)) return false;
  if (!chk(e.market_cap, f.min_market_cap, f.max_market_cap)) return false;
  if (!chk(e.gap_percent, f.min_gap_percent, f.max_gap_percent)) return false;
  if (!chk(e.change_from_open, f.min_change_from_open, f.max_change_from_open)) return false;
  if (!chk(e.atr_percent, f.min_atr_percent, f.max_atr_percent)) return false;
  if (!chk(e.vwap, f.min_vwap, f.max_vwap)) return false;
  // Time-window changes
  if (!chk(e.chg_1min, f.min_chg_1min, f.max_chg_1min)) return false;
  if (!chk(e.chg_5min, f.min_chg_5min, f.max_chg_5min)) return false;
  if (!chk(e.chg_10min, f.min_chg_10min, f.max_chg_10min)) return false;
  if (!chk(e.chg_15min, f.min_chg_15min, f.max_chg_15min)) return false;
  if (!chk(e.chg_30min, f.min_chg_30min, f.max_chg_30min)) return false;
  // Time-window volumes
  if (!chk(e.vol_1min, f.min_vol_1min, f.max_vol_1min)) return false;
  if (!chk(e.vol_5min, f.min_vol_5min, f.max_vol_5min)) return false;
  // Fundamentals & indicators
  if (!chk(e.float_shares, f.min_float_shares, f.max_float_shares)) return false;
  if (!chk(e.rsi, f.min_rsi, f.max_rsi)) return false;
  if (!chk(e.ema_20, f.min_ema_20 ?? f.min_sma_20, f.max_ema_20 ?? f.max_sma_20)) return false;
  if (!chk(e.ema_50, f.min_ema_50 ?? f.min_sma_50, f.max_ema_50 ?? f.max_sma_50)) return false;
  // Symbol filters
  if (f.symbols_include?.length && !f.symbols_include.includes(e.symbol)) return false;
  if (f.symbols_exclude?.length && f.symbols_exclude.includes(e.symbol)) return false;
  return true;
}

// ============================================================================
// COMPONENT
// ============================================================================

export function EventTableContent({ categoryId, categoryName, eventTypes: initialEventTypes, defaultFilters }: EventTableContentProps) {
  const { t } = useTranslation();
  const { executeTickerCommand } = useCommandExecutor();
  const closeCurrentWindow = useCloseCurrentWindow();
  const ws = useWebSocket();

  // ========================================================================
  // ALERT CONFIG PANEL STATE
  // ========================================================================

  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; symbol?: string } | null>(null);
  const { openWindow } = useFloatingWindow();
  const [customEventTypes, setCustomEventTypes] = useState<string[]>(initialEventTypes);

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
  // STATE
  // ========================================================================

  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [newEventIds, setNewEventIds] = useState<Set<string>>(new Set());

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
    return events.filter((event) => {
      // Event type filter (only for "All Events" category where user can narrow down)
      if (categoryId === 'evt_all' && eventFilters.event_types && eventFilters.event_types.length > 0) {
        if (!eventFilters.event_types.includes(event.event_type)) {
          return false;
        }
      }

      // Price filter (also applied server-side, this is a safety net)
      if (eventFilters.min_price !== undefined && event.price < eventFilters.min_price) return false;
      if (eventFilters.max_price !== undefined && event.price > eventFilters.max_price) return false;

      // Change percent filter
      if (eventFilters.min_change_percent !== undefined && (event.change_percent === undefined || event.change_percent < eventFilters.min_change_percent)) return false;
      if (eventFilters.max_change_percent !== undefined && (event.change_percent === undefined || event.change_percent > eventFilters.max_change_percent)) return false;

      // RVOL filter
      if (eventFilters.min_rvol !== undefined && (event.rvol === undefined || event.rvol < eventFilters.min_rvol)) return false;
      if (eventFilters.max_rvol !== undefined && (event.rvol === undefined || event.rvol > eventFilters.max_rvol)) return false;

      // Volume filter
      if (eventFilters.min_volume !== undefined && (event.volume === undefined || event.volume < eventFilters.min_volume)) return false;
      if (eventFilters.max_volume !== undefined && (event.volume === undefined || event.volume > eventFilters.max_volume)) return false;

      // Symbol include filter
      if (eventFilters.symbols_include && eventFilters.symbols_include.length > 0) {
        if (!eventFilters.symbols_include.includes(event.symbol)) return false;
      }

      // Symbol exclude filter
      if (eventFilters.symbols_exclude && eventFilters.symbols_exclude.length > 0) {
        if (eventFilters.symbols_exclude.includes(event.symbol)) return false;
      }

      return true;
    });
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
    // String filters
    setS('security_type', filters.security_type);
    setS('sector', filters.sector);
    setS('industry', filters.industry);
    // Symbols
    if (filters.symbols_include?.length) subscribeMsg.symbols_include = filters.symbols_include;
    if (filters.symbols_exclude?.length) subscribeMsg.symbols_exclude = filters.symbols_exclude;

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
          return [event, ...prev].slice(0, 500);
        });

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
        // Only process snapshot for OUR subscription
        if (msg.sub_id && msg.sub_id !== subId) return;

        const seen = new Set<string>();
        const snapshot: MarketEvent[] = (msg.events || [])
          .map((e: any) => parseEvent(e))
          .filter((e: MarketEvent) => {
            if (seen.has(e.id)) return false;
            seen.add(e.id);
            return true; // Server already filtered — no need to re-filter
          });
        setEvents(snapshot.slice(0, 500));
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
      ];
      for (const [k, v] of uPairs) uF(k, v);
      uS('security_type', f.security_type);
      uS('sector', f.sector);
      uS('industry', f.industry);
      updateMsg.symbols_include = f.symbols_include || null;
      updateMsg.symbols_exclude = f.symbols_exclude || null;
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
          <div className="text-center font-semibold text-slate-400 text-xs">
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
          });
          const relativeTime = formatDistanceToNowStrict(date, { addSuffix: false });
          return (
            <div className="font-mono text-xs text-slate-600" title={relativeTime + ' ago'}>
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
            className="font-bold text-blue-600 cursor-pointer hover:text-blue-800 hover:underline transition-colors text-xs"
            onClick={(e) => {
              e.stopPropagation();
              executeTickerCommand(info.getValue(), 'fan');
            }}
            title="Click to open Financial Analyst"
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
          const config = EVENT_TYPE_CONFIG[eventType] || {
            label: eventType,
            color: 'text-slate-600',
            icon: Activity,
          };
          const IconComponent = config.icon;
          return (
            <div className={`flex items-center gap-1 ${config.color} text-xs font-medium`}>
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
            <div className="font-mono text-xs text-slate-700 font-medium">
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
            return <div className="text-slate-400 text-xs">-</div>;
          }
          const isPositive = value > 0;
          return (
            <div className={`font-mono text-xs font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
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
          if (!value) return <div className="text-slate-400 text-xs">-</div>;
          return (
            <div className="font-mono text-xs text-slate-600">
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
          if (!value) return <div className="text-slate-400 text-xs">-</div>;
          return (
            <div className={`font-mono text-xs font-semibold ${value > 3 ? 'text-blue-700' : value > 1.5 ? 'text-blue-600' : 'text-slate-500'}`}>
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
          if (value === undefined || value === null) return <div className="text-slate-400 text-xs">-</div>;
          const isPositive = value > 0;
          return (
            <div className={`font-mono text-xs font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
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
          if (value === undefined || value === null) return <div className="text-slate-400 text-xs">-</div>;
          const isPositive = value > 0;
          return (
            <div className={`font-mono text-xs ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
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
          if (!value) return <div className="text-slate-400 text-xs">-</div>;
          const formatted = value >= 1e12
            ? `$${(value / 1e12).toFixed(1)}T`
            : value >= 1e9
              ? `$${(value / 1e9).toFixed(1)}B`
              : value >= 1e6
                ? `$${(value / 1e6).toFixed(0)}M`
                : `$${formatNumber(value)}`;
          return <div className="font-mono text-xs text-slate-600">{formatted}</div>;
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
          if (value === undefined || value === null) return <div className="text-slate-400 text-xs">-</div>;
          return (
            <div className={`font-mono text-xs ${value > 5 ? 'text-orange-600 font-semibold' : 'text-slate-500'}`}>
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
          if (!value) return <div className="text-slate-400 text-xs">-</div>;
          return <div className="font-mono text-xs text-slate-600">${value.toFixed(2)}</div>;
        },
      }),
    ],
    [executeTickerCommand]
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
      className="fixed z-[9999] bg-white border border-slate-200 rounded shadow-lg py-1 min-w-[180px]"
      style={{ left: ctxMenu.x, top: ctxMenu.y }}
      onContextMenu={e => e.preventDefault()}
    >
      {ctxMenu.symbol && (
        <>
          <button onClick={() => { executeTickerCommand(ctxMenu.symbol!, 'chart'); setCtxMenu(null); }}
            className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-blue-50 hover:text-blue-700">
            Trade {ctxMenu.symbol}
          </button>
          <div className="border-t border-slate-100 my-0.5" />
        </>
      )}
      <button onClick={() => { openConfigWindow(); setCtxMenu(null); }}
        className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-blue-50 hover:text-blue-700">
        Configure...
      </button>
      <button onClick={() => { setEvents([]); setCtxMenu(null); }}
        className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-blue-50 hover:text-blue-700">
        Clear
      </button>
      <div className="border-t border-slate-100 my-0.5" />
      <button onClick={() => { handleResetToDefaults(); setCtxMenu(null); }}
        className="w-full text-left px-3 py-1.5 text-xs text-slate-700 hover:bg-blue-50 hover:text-blue-700">
        Reset columns
      </button>
    </div>
  );

  const rightActions = (
    <div className="flex items-center gap-1">
      <button onClick={handleMenuButton}
        className="p-0.5 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
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

  // Empty state
  if (events.length === 0 && isSubscribed) {
    return (
      <div className="h-full flex flex-row">
        <div className="flex-1 flex flex-col min-w-0" onContextMenu={handleContextMenu}>
          <MarketTableLayout
            title={displayTitle}
            isLive={ws.isConnected}
            count={0}
            listName={categoryId}
            onClose={closeCurrentWindow}
            rightActions={rightActions}
          />
          <div className="flex-1 flex items-center justify-center bg-slate-50">
            <div className="text-center p-6">
              <Activity className="w-8 h-8 text-slate-400 mx-auto mb-2" />
              <h3 className="text-sm font-semibold text-slate-700 mb-1">
                Waiting for events...
              </h3>
              <p className="text-xs text-slate-500 max-w-xs">
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
          isLoading={!isSubscribed}
          estimateSize={16}
          overscan={10}
          enableVirtualization={true}
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
            count={filteredEvents.length}
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
