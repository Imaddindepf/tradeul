/**
 * useMarketEvents - Hook for real-time market events / alerts subscription.
 *
 * Event types are defined in lib/alert-catalog.ts (the single source of truth).
 * This hook only deals with the WebSocket transport and in-memory store.
 */

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { BehaviorSubject, Subject, Observable } from 'rxjs';
import { filter, map, share, takeUntil } from 'rxjs/operators';

// Re-export catalog helpers so existing consumers keep working
export { getEventLabel, getEventColor, ALERT_BY_EVENT_TYPE } from '@/lib/alert-catalog';

// ============================================================================
// TYPES
// ============================================================================

export interface MarketEvent {
  id: string;
  event_type: string;
  rule_id: string;
  symbol: string;
  timestamp: string;
  price: number | null;
  prev_value: number | null;
  new_value: number | null;
  delta: number | null;
  delta_percent: number | null;
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
  quality: number | null;
  description: string | null;
  details: Record<string, any> | null;
}

export interface MarketEventsFilter {
  eventTypes?: string[];
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
  private destroy$ = new Subject<void>();

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
      map((msg: any) => msg.data as MarketEvent),
      takeUntil(this.destroy$)
    ).subscribe((event: MarketEvent) => {
      this.addEvent(event);
    });

    manager.messages$.pipe(
      filter((msg: any) => msg?.type === 'events_snapshot'),
      takeUntil(this.destroy$)
    ).subscribe((msg: any) => {
      const snapshot = (msg.events || []) as MarketEvent[];
      this.events.next(snapshot.slice(0, this.maxEvents));
    });
  }

  unsubscribe(): void {
    if (!this.isSubscribed) return;
    this.destroy$.next();
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

interface UseMarketEventsOptions {
  autoSubscribe?: boolean;
  filter?: MarketEventsFilter;
  maxEvents?: number;
}

interface UseMarketEventsReturn {
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

// EVENT_TYPE_LABELS and EVENT_TYPE_COLORS have been replaced by
// getEventLabel() and getEventColor() from @/lib/alert-catalog.
// They are re-exported at the top of this file for backward compatibility.
