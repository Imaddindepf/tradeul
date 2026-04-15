'use client';

import { useState, useEffect, useCallback } from 'react';

interface KeyInfo {
  key_id: string;
  name: string;
  active: boolean;
  last_used_at: string | null;
  rate_limit: number;
}

function formatRelative(iso: string | null): string {
  if (!iso) return 'never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function UsageSection() {
  const [keys, setKeys] = useState<KeyInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/v1/developer/keys');
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setKeys(data.keys);
    } catch (e: any) {
      setError(e.message || 'Failed to load usage data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);

  const active = keys.filter(k => k.active);

  return (
    <div className="flex flex-col h-full overflow-y-auto">

      {error && (
        <div className="px-2 py-1 text-[10px] text-red-500 border-b border-border flex-shrink-0">
          {error}
        </div>
      )}

      {/* Keys activity */}
      <div className="border-b border-border flex-shrink-0">
        <div className="px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 border-b border-border">
          Key Activity
        </div>
        <div className="grid grid-cols-[2fr_1fr] px-2 py-1">
          {['KEY', 'LAST SEEN'].map(h => (
            <span key={h} className="text-[8px] font-medium uppercase tracking-wider text-muted-foreground/30">
              {h}
            </span>
          ))}
        </div>

        {loading && (
          <div className="px-2 py-2 text-[10px] text-muted-foreground/40">Loading…</div>
        )}

        {!loading && active.length === 0 && (
          <div className="px-2 py-2 text-[10px] text-muted-foreground/40">
            No active keys. Generate one in the Keys tab.
          </div>
        )}

        {active.map(k => (
          <div
            key={k.key_id}
            className="grid grid-cols-[2fr_1fr] items-center px-2 py-[5px] border-b border-border hover:bg-muted/5 transition-colors"
          >
            <span className="text-[10px] font-medium truncate">{k.name}</span>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {formatRelative(k.last_used_at)}
            </span>
          </div>
        ))}
      </div>

      {/* Service limits */}
      <div className="border-b border-border flex-shrink-0">
        <div className="px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 border-b border-border">
          Service Limits
        </div>
        {[
          { label: 'Rate limit',      value: `${keys[0]?.rate_limit ?? 120} req / min per key` },
          { label: 'Max keys',        value: '10 keys per account' },
          { label: 'News retention',  value: '500 items in cache' },
          { label: 'WS connections',  value: 'Up to 5 simultaneous per key' },
        ].map(row => (
          <div
            key={row.label}
            className="flex justify-between items-center px-2 py-[5px] border-b border-border hover:bg-muted/5 transition-colors"
          >
            <span className="text-[10px] text-muted-foreground/60">{row.label}</span>
            <span className="text-[10px] font-medium tabular-nums">{row.value}</span>
          </div>
        ))}
      </div>

      {/* Stream info */}
      <div className="flex-shrink-0">
        <div className="px-2 py-1 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 border-b border-border">
          Stream Info
        </div>
        {[
          { label: 'Protocol',  value: 'WebSocket (WSS)' },
          { label: 'Encoding',  value: 'JSON frames' },
          { label: 'Keepalive', value: 'Server ping every 30s' },
          { label: 'Filtering', value: 'Per-session ticker subscription' },
        ].map(row => (
          <div
            key={row.label}
            className="flex justify-between items-center px-2 py-[5px] border-b border-border hover:bg-muted/5 transition-colors"
          >
            <span className="text-[10px] text-muted-foreground/60">{row.label}</span>
            <span className="text-[10px] font-medium">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
