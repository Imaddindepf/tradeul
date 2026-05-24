'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Debounced connection-status hook.
 *
 * Returns the same boolean as the underlying source, but absorbs short
 * `false` blips so the UI doesn't flash "offline" on transient
 * reconnections (e.g. SharedWorker rebroadcasts, token refreshes,
 * tab visibility changes).
 *
 * - true  -> propagates immediately (we always want to show "live" ASAP)
 * - false -> only propagated after `gracePeriodMs` of sustained false
 *
 * If the source flips back to `true` during the grace window, the
 * pending "offline" update is cancelled and the UI never shows offline.
 */
export function useStableConnectionStatus(
  isConnected: boolean,
  gracePeriodMs: number = 800,
): boolean {
  const [stable, setStable] = useState(isConnected);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (isConnected) {
      // Propagate "live" immediately and cancel any pending "offline" flip.
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setStable(true);
      return;
    }

    // Disconnect: only commit to "offline" after a sustained period.
    if (timerRef.current) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setStable(false);
    }, gracePeriodMs);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isConnected, gracePeriodMs]);

  return stable;
}
