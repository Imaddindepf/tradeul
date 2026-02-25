'use client';

import { useEffect, useState, useCallback } from 'react';
import { useFloatingWindow, useCurrentWindowId, type LinkGroup, type TickerBroadcast } from '@/contexts/FloatingWindowContext';

/**
 * Get the current window's linkGroup from context.
 */
export function useWindowLinkGroup(): LinkGroup {
  const { windows } = useFloatingWindow();
  const windowId = useCurrentWindowId();
  if (!windowId) return null;
  const win = windows.find(w => w.id === windowId);
  return win?.linkGroup ?? null;
}

/**
 * Hook for subscriber windows (chart, FAN, etc.)
 * Subscribes to ticker broadcasts for the window's link group.
 * Returns the latest broadcasted ticker, or null.
 */
export function useLinkGroupSubscription(): TickerBroadcast | null {
  const { subscribeTicker, windows } = useFloatingWindow();
  const windowId = useCurrentWindowId();
  const linkGroup = windowId ? (windows.find(w => w.id === windowId)?.linkGroup ?? null) : null;
  const [lastBroadcast, setLastBroadcast] = useState<TickerBroadcast | null>(null);

  useEffect(() => {
    if (!linkGroup) {
      return;
    }
    const unsubscribe = subscribeTicker(linkGroup, (broadcast) => {
      setLastBroadcast(broadcast);
    });
    return unsubscribe;
  }, [linkGroup, subscribeTicker]);

  return lastBroadcast;
}

/**
 * Hook for publisher windows (scanner, watchlist, etc.)
 * Returns a publish function and helper to check for subscribers.
 */
export function useLinkGroupPublisher() {
  const { broadcastTicker, getSubscriberCount, windows } = useFloatingWindow();
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
