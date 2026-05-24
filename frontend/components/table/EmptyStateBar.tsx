'use client';

import { useEffect, useState } from 'react';
import { getUserTimezone } from '@/lib/date-utils';

interface EmptyStateBarProps {
  isConnected: boolean;
  count?: number;
  noun?: string;
  hint?: string;
  error?: string | null;
}

/**
 * Bloomberg-style status bar shown when a table/feed has no data yet.
 * Renders as a thin strip with a pulsing dot, status label, count and a
 * live clock. Designed to be embedded inside an empty table body so the
 * column headers stay visible and the UI never collapses to a "loading"
 * placeholder.
 */
export function EmptyStateBar({
  isConnected,
  count = 0,
  noun = 'events',
  hint,
  error,
}: EmptyStateBarProps) {
  const [now, setNow] = useState<string>('');

  useEffect(() => {
    const tick = () => {
      setNow(
        new Date().toLocaleTimeString('en-US', {
          timeZone: getUserTimezone(),
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        })
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const status = error ? 'ERROR' : isConnected ? 'LISTENING' : 'CONNECTING';
  const dotColor = error
    ? 'bg-red-500'
    : isConnected
      ? 'bg-emerald-500'
      : 'bg-amber-500';

  return (
    <div className="flex items-center justify-center gap-2 px-3 py-1 text-[10px] font-mono uppercase tracking-wider text-muted-fg/70 bg-surface-inset/40 border-t border-border-subtle select-none">
      <span className="relative flex h-1.5 w-1.5">
        {!error && isConnected && (
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${dotColor} opacity-60 animate-ping`}
          />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${dotColor}`} />
      </span>
      <span>{status}</span>
      <span className="text-muted-fg/40">·</span>
      <span>{count.toLocaleString()} {noun}</span>
      {hint && (
        <>
          <span className="text-muted-fg/40">·</span>
          <span className="normal-case tracking-normal text-muted-fg/60">{hint}</span>
        </>
      )}
      {error && (
        <>
          <span className="text-muted-fg/40">·</span>
          <span className="normal-case tracking-normal text-red-500/80">{error}</span>
        </>
      )}
      <span className="text-muted-fg/40">·</span>
      <span className="tabular-nums">{now}</span>
    </div>
  );
}

export default EmptyStateBar;
