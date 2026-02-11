/**
 * useMarketEvents - Hook for real-time market events subscription
 * 
 * Events include 39 active event types detected by the Event Detector service:
 * Phase 1 (27 tick-based): price, VWAP, volume, momentum, pullbacks, gaps, halts
 * Phase 1B (12 snapshot-driven): EMA crosses, BB breakout, daily levels, running variants
 * 
 * Uses the shared WebSocket connection via WebSocketManager singleton.
 */

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { BehaviorSubject, Subject, Observable } from 'rxjs';
import { filter, map, share, takeUntil } from 'rxjs/operators';

// ============================================================================
// TYPES
// ============================================================================

export type MarketEventType =
  // Phase 1: Price
  | 'new_high'
  | 'new_low'
  | 'crossed_above_open'
  | 'crossed_below_open'
  | 'crossed_above_prev_close'
  | 'crossed_below_prev_close'
  // Phase 1: VWAP
  | 'vwap_cross_up'
  | 'vwap_cross_down'
  // Phase 1: Volume
  | 'rvol_spike'
  | 'volume_surge'
  | 'volume_spike_1min'
  | 'unusual_prints'
  | 'block_trade'
  // Phase 1: Momentum
  | 'running_up'
  | 'running_down'
  | 'percent_up_5'
  | 'percent_down_5'
  | 'percent_up_10'
  | 'percent_down_10'
  // Phase 1: Pullbacks
  | 'pullback_75_from_high'
  | 'pullback_25_from_high'
  | 'pullback_75_from_low'
  | 'pullback_25_from_low'
  // Phase 1: Gap
  | 'gap_up_reversal'
  | 'gap_down_reversal'
  // Phase 1: Halts
  | 'halt'
  | 'resume'
  // Phase 1B: Intraday EMA Crosses (snapshot-driven)
  | 'crossed_above_ema20'
  | 'crossed_below_ema20'
  | 'crossed_above_ema50'
  | 'crossed_below_ema50'
  // Phase 1B: Bollinger Bands
  | 'bb_upper_breakout'
  | 'bb_lower_breakdown'
  // Phase 1B: Daily Levels
  | 'crossed_daily_high_resistance'
  | 'crossed_daily_low_support'
  | 'false_gap_up_retracement'
  | 'false_gap_down_retracement'
  // Phase 1B: Running Variants
  | 'running_up_sustained'
  | 'running_down_sustained'
  | 'running_up_confirmed'
  | 'running_down_confirmed';

export interface MarketEvent {
  id: string;
  event_type: MarketEventType;
  rule_id: string;
  symbol: string;
  timestamp: string;
  price: number | null;
  prev_value: number | null;
  new_value: number | null;
  delta: number | null;
  delta_percent: number | null;
  // Context at event time
  change_percent: number | null;
  rvol: number | null;
  volume: number | null;
  market_cap: number | null;
  gap_percent: number | null;
  change_from_open: number | null;
  open_price: number | null;
  prev_close: number | null;
  vwap: number | null;
  atr_percent: number | null;
  intraday_high: number | null;
  intraday_low: number | null;
  details: Record<string, any> | null;
}

export interface MarketEventsFilter {
  eventTypes?: MarketEventType[];
  symbols?: string[];
  minPrice?: number;
  maxPrice?: number;
  minRvol?: number;
  minVolume?: number;
}

// ============================================================================
// WEBSOCKET MANAGER ACCESS
// ============================================================================

const getWSManager = () => {
  if (typeof window !== 'undefined' && (window as any).__WS_MANAGER__) {
    return (window as any).__WS_MANAGER__;
  }
  return null;
};

// ============================================================================
// EVENTS STORE - Centralized state for market events
// ============================================================================

class MarketEventsStore {
  private static instance: MarketEventsStore | null = null;

  private events = new BehaviorSubject<MarketEvent[]>([]);
  private newEvent = new Subject<MarketEvent>();
  private isSubscribed = false;
  private maxEvents = 200;

  private constructor() { }

  static getInstance(): MarketEventsStore {
    if (!MarketEventsStore.instance) {
      MarketEventsStore.instance = new MarketEventsStore();
    }
    return MarketEventsStore.instance;
  }

  subscribe(): void {
    if (this.isSubscribed) return;

    const manager = getWSManager();
    if (!manager) {
      console.warn('[MarketEvents] WebSocket manager not available');
      return;
    }

    manager.send({ action: 'subscribe_events' });
    this.isSubscribed = true;

    manager.messages$.pipe(
      filter((msg: any) => msg?.type === 'market_event'),
      map((msg: any) => msg.data as MarketEvent)
    ).subscribe((event: MarketEvent) => {
      this.addEvent(event);
    });

    // Handle snapshot on subscribe
    manager.messages$.pipe(
      filter((msg: any) => msg?.type === 'events_snapshot'),
    ).subscribe((msg: any) => {
      const snapshot = (msg.events || []) as MarketEvent[];
      this.events.next(snapshot.slice(0, this.maxEvents));
    });
  }

  unsubscribe(): void {
    if (!this.isSubscribed) return;
    const manager = getWSManager();
    if (manager) {
      manager.send({ action: 'unsubscribe_events' });
    }
    this.isSubscribed = false;
  }

  private addEvent(event: MarketEvent): void {
    const current = this.events.getValue();
    // Deduplicate by event ID (prevents duplicates from SharedWorker multi-port broadcast)
    if (current.some(e => e.id === event.id)) return;
    this.newEvent.next(event);
    const updated = [event, ...current].slice(0, this.maxEvents);
    this.events.next(updated);
  }

  clear(): void {
    this.events.next([]);
  }

  get events$(): Observable<MarketEvent[]> {
    return this.events.asObservable();
  }

  get newEvent$(): Observable<MarketEvent> {
    return this.newEvent.asObservable().pipe(share());
  }

  get currentEvents(): MarketEvent[] {
    return this.events.getValue();
  }

  get subscribed(): boolean {
    return this.isSubscribed;
  }
}

// ============================================================================
// REACT HOOK
// ============================================================================

export interface UseMarketEventsOptions {
  autoSubscribe?: boolean;
  filter?: MarketEventsFilter;
  maxEvents?: number;
}

export interface UseMarketEventsReturn {
  events: MarketEvent[];
  newEvent$: Observable<MarketEvent>;
  isSubscribed: boolean;
  subscribe: () => void;
  unsubscribe: () => void;
  clear: () => void;
}

function applyFilter(events: MarketEvent[], f?: MarketEventsFilter): MarketEvent[] {
  if (!f) return events;

  return events.filter(event => {
    if (f.eventTypes && f.eventTypes.length > 0) {
      if (!f.eventTypes.includes(event.event_type)) return false;
    }
    if (f.symbols && f.symbols.length > 0) {
      if (!f.symbols.includes(event.symbol)) return false;
    }
    if (f.minPrice !== undefined && event.price !== null) {
      if (event.price < f.minPrice) return false;
    }
    if (f.maxPrice !== undefined && event.price !== null) {
      if (event.price > f.maxPrice) return false;
    }
    if (f.minRvol !== undefined && event.rvol !== null) {
      if (event.rvol < f.minRvol) return false;
    }
    if (f.minVolume !== undefined && event.volume !== null) {
      if (event.volume < f.minVolume) return false;
    }
    return true;
  });
}

export function useMarketEvents(options: UseMarketEventsOptions = {}): UseMarketEventsReturn {
  const { autoSubscribe = true, filter: eventFilter, maxEvents = 100 } = options;

  const storeRef = useRef(MarketEventsStore.getInstance());
  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [isSubscribed, setIsSubscribed] = useState(storeRef.current.subscribed);
  const destroyRef = useRef(new Subject<void>());

  useEffect(() => {
    if (autoSubscribe) {
      storeRef.current.subscribe();
      setIsSubscribed(true);
    }

    const sub = storeRef.current.events$.pipe(
      takeUntil(destroyRef.current),
      map(allEvents => applyFilter(allEvents, eventFilter).slice(0, maxEvents))
    ).subscribe(setEvents);

    return () => {
      sub.unsubscribe();
      destroyRef.current.next();
    };
  }, [autoSubscribe, maxEvents]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const allEvents = storeRef.current.currentEvents;
    setEvents(applyFilter(allEvents, eventFilter).slice(0, maxEvents));
  }, [eventFilter, maxEvents]);

  const subscribe = useCallback(() => {
    storeRef.current.subscribe();
    setIsSubscribed(true);
  }, []);

  const unsubscribe = useCallback(() => {
    storeRef.current.unsubscribe();
    setIsSubscribed(false);
  }, []);

  const clear = useCallback(() => {
    storeRef.current.clear();
    setEvents([]);
  }, []);

  return useMemo(() => ({
    events,
    newEvent$: storeRef.current.newEvent$,
    isSubscribed,
    subscribe,
    unsubscribe,
    clear,
  }), [events, isSubscribed, subscribe, unsubscribe, clear]);
}

// ============================================================================
// HELPERS - Display labels, colors, icons for ALL active event types
// ============================================================================

export const EVENT_TYPE_LABELS: Record<MarketEventType, string> = {
  // Phase 1: Price
  new_high: 'New High',
  new_low: 'New Low',
  crossed_above_open: '↑ Open',
  crossed_below_open: '↓ Open',
  crossed_above_prev_close: '↑ Close',
  crossed_below_prev_close: '↓ Close',
  // Phase 1: VWAP
  vwap_cross_up: 'VWAP ↑',
  vwap_cross_down: 'VWAP ↓',
  // Phase 1: Volume
  rvol_spike: 'RVOL 3x',
  volume_surge: 'RVOL 5x',
  volume_spike_1min: 'Vol Spike',
  unusual_prints: 'Unusual',
  block_trade: 'Block Trade',
  // Phase 1: Momentum
  running_up: 'Run ↑',
  running_down: 'Run ↓',
  percent_up_5: '+5%',
  percent_down_5: '-5%',
  percent_up_10: '+10%',
  percent_down_10: '-10%',
  // Phase 1: Pullbacks
  pullback_75_from_high: 'PB 75% H',
  pullback_25_from_high: 'PB 25% H',
  pullback_75_from_low: 'Bounce 75%',
  pullback_25_from_low: 'Bounce 25%',
  // Phase 1: Gap
  gap_up_reversal: 'Gap↑ Rev',
  gap_down_reversal: 'Gap↓ Rev',
  // Phase 1: Halts
  halt: 'HALT',
  resume: 'RESUME',
  // Phase 1B: EMA Crosses
  crossed_above_ema20: 'EMA20 ↑',
  crossed_below_ema20: 'EMA20 ↓',
  crossed_above_ema50: 'EMA50 ↑',
  crossed_below_ema50: 'EMA50 ↓',
  // Phase 1B: Bollinger
  bb_upper_breakout: 'BB Upper',
  bb_lower_breakdown: 'BB Lower',
  // Phase 1B: Daily Levels
  crossed_daily_high_resistance: 'Day High ↑',
  crossed_daily_low_support: 'Day Low ↓',
  false_gap_up_retracement: 'False Gap↑',
  false_gap_down_retracement: 'False Gap↓',
  // Phase 1B: Running Variants
  running_up_sustained: 'Run ↑ Sust',
  running_down_sustained: 'Run ↓ Sust',
  running_up_confirmed: 'Run ↑ Conf',
  running_down_confirmed: 'Run ↓ Conf',
};

export const EVENT_TYPE_COLORS: Record<MarketEventType, string> = {
  new_high: 'text-green-500',
  new_low: 'text-red-500',
  crossed_above_open: 'text-emerald-400',
  crossed_below_open: 'text-rose-400',
  crossed_above_prev_close: 'text-emerald-400',
  crossed_below_prev_close: 'text-rose-400',
  vwap_cross_up: 'text-emerald-400',
  vwap_cross_down: 'text-orange-400',
  rvol_spike: 'text-purple-500',
  volume_surge: 'text-violet-500',
  volume_spike_1min: 'text-purple-400',
  unusual_prints: 'text-amber-500',
  block_trade: 'text-indigo-500',
  running_up: 'text-green-600',
  running_down: 'text-red-600',
  percent_up_5: 'text-green-500',
  percent_down_5: 'text-red-500',
  percent_up_10: 'text-green-600',
  percent_down_10: 'text-red-600',
  pullback_75_from_high: 'text-rose-400',
  pullback_25_from_high: 'text-orange-400',
  pullback_75_from_low: 'text-emerald-400',
  pullback_25_from_low: 'text-cyan-400',
  gap_up_reversal: 'text-rose-500',
  gap_down_reversal: 'text-emerald-500',
  halt: 'text-red-600',
  resume: 'text-green-600',
  // Phase 1B
  crossed_above_ema20: 'text-emerald-500',
  crossed_below_ema20: 'text-rose-500',
  crossed_above_ema50: 'text-emerald-600',
  crossed_below_ema50: 'text-rose-600',
  bb_upper_breakout: 'text-emerald-600',
  bb_lower_breakdown: 'text-rose-600',
  crossed_daily_high_resistance: 'text-emerald-600',
  crossed_daily_low_support: 'text-rose-600',
  false_gap_up_retracement: 'text-rose-500',
  false_gap_down_retracement: 'text-emerald-500',
  running_up_sustained: 'text-emerald-700',
  running_down_sustained: 'text-rose-700',
  running_up_confirmed: 'text-emerald-700',
  running_down_confirmed: 'text-rose-700',
};

export const EVENT_TYPE_ICONS: Record<MarketEventType, string> = {
  new_high: '📈',
  new_low: '📉',
  crossed_above_open: '⬆️',
  crossed_below_open: '⬇️',
  crossed_above_prev_close: '⬆️',
  crossed_below_prev_close: '⬇️',
  vwap_cross_up: '⬆️',
  vwap_cross_down: '⬇️',
  rvol_spike: '🔥',
  volume_surge: '💥',
  volume_spike_1min: '📊',
  unusual_prints: '⚡',
  block_trade: '🏦',
  running_up: '🏃',
  running_down: '🏃',
  percent_up_5: '📈',
  percent_down_5: '📉',
  percent_up_10: '🚀',
  percent_down_10: '💣',
  pullback_75_from_high: '📉',
  pullback_25_from_high: '📉',
  pullback_75_from_low: '📈',
  pullback_25_from_low: '📈',
  gap_up_reversal: '🔄',
  gap_down_reversal: '🔄',
  halt: '🛑',
  resume: '▶️',
  // Phase 1B
  crossed_above_ema20: '📐',
  crossed_below_ema20: '📐',
  crossed_above_ema50: '📐',
  crossed_below_ema50: '📐',
  bb_upper_breakout: '📏',
  bb_lower_breakdown: '📏',
  crossed_daily_high_resistance: '📍',
  crossed_daily_low_support: '📍',
  false_gap_up_retracement: '🔃',
  false_gap_down_retracement: '🔃',
  running_up_sustained: '🏃',
  running_down_sustained: '🏃',
  running_up_confirmed: '✅',
  running_down_confirmed: '✅',
};
