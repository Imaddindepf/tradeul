'use client';

import { useEffect, useState, useCallback } from 'react';
import { useFloatingWindowActions, useFloatingWindowsList, useCurrentWindowId, type TickerBroadcast } from '@/contexts/FloatingWindowContext';

/**
 * Hook for subscriber windows (TC / TAS, etc.)
 * Subscribes to ticker broadcasts for the window's link group.
 * Seeds with the last ticker published to that group (if any).
 */
export function useLinkGroupSubscription(): TickerBroadcast | null {
  const { subscribeTicker, getLastTicker } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();
  const windowId = useCurrentWindowId();
  const linkGroup = windowId ? (windows.find(w => w.id === windowId)?.linkGroup ?? null) : null;
  const [lastBroadcast, setLastBroadcast] = useState<TickerBroadcast | null>(null);

  useEffect(() => {
    if (!linkGroup) {
      setLastBroadcast(null);
      return;
    }
    const seeded = getLastTicker(linkGroup);
    if (seeded) setLastBroadcast(seeded);
    const unsubscribe = subscribeTicker(linkGroup, (broadcast) => {
      setLastBroadcast(broadcast);
    });
    return unsubscribe;
  }, [linkGroup, subscribeTicker, getLastTicker]);

  return lastBroadcast;
}

/**
 * Hook for publisher windows (scanner, events, screener, etc.)
 * Returns a publish function and helper to check for subscribers.
 */
export function useLinkGroupPublisher() {
  const { broadcastTicker, getSubscriberCount } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();
  const windowId = useCurrentWindowId();
  const linkGroup = windowId ? (windows.find(w => w.id === windowId)?.linkGroup ?? null) : null;

  const publish = useCallback((ticker: string, exchange?: string) => {
    if (!linkGroup) return false;
    broadcastTicker(linkGroup, { ticker, exchange });
    return true;
  }, [linkGroup, broadcastTicker]);

  const hasSubscribers = useCallback(() => {
    if (!linkGroup) return false;
    return getSubscriberCount(linkGroup) > 0;
  }, [linkGroup, getSubscriberCount]);

  return { publish, hasSubscribers, linkGroup };
}
