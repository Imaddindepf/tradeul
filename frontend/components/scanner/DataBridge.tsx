'use client';

/**
 * DataBridge — Single aggregates$ subscriber for the entire app.
 *
 * Problem solved:
 *   Each CategoryTableV2 instance subscribed to ws.aggregates$ independently.
 *   With 4-10 tables, that caused 4-10 identical updateAggregates() calls per
 *   100ms batch → 40+ Zustand set() per second → 600+ Map copies/sec → GC storm.
 *
 * Solution:
 *   Mount ONE DataBridge in AppShell. It subscribes to aggregates$ once and
 *   calls updateAggregates once per batch. All CategoryTableV2 instances just
 *   read from the store — zero duplicated subscriptions.
 *
 * This component renders nothing (returns null).
 */

import { useEffect } from 'react';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useTickersStore } from '@/stores/useTickersStore';

export function DataBridge() {
  const ws = useWebSocket();
  const updateAggregates = useTickersStore((state) => state.updateAggregates);

  useEffect(() => {
    if (!ws.isConnected) return;

    const sub = ws.aggregates$.subscribe((batch: any) => {
      if (batch.type === 'aggregates_batch' && batch.data instanceof Map) {
        updateAggregates(batch.data);
      }
    });

    return () => sub.unsubscribe();
  }, [ws.isConnected, ws.aggregates$, updateAggregates]);

  return null;
}
