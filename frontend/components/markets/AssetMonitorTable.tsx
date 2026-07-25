'use client';

/**
 * AssetMonitorTable — motor compartido de los monitores de clase de activo
 * (FUT: futuros, FX: forex). Cada ventana es un componente propio que solo
 * define sus grupos y labels; este motor hace el polling del snapshot
 * (/api/v1/realtime/class/{assetClass}) y pinta la tabla agrupada.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

const FONT_FAMILIES: Record<string, string> = {
  'oxygen-mono': '"Oxygen Mono", monospace',
  'ibm-plex-mono': '"IBM Plex Mono", monospace',
  'jetbrains-mono': '"JetBrains Mono", monospace',
  'fira-code': '"Fira Code", monospace',
};

export interface MonitorGroup {
  title: string;
  symbols: string[];
}

export interface AssetEntry {
  symbol: string;
  name?: string | null;
  price: number;
  change?: number | null;
  change_percent?: number | null;
  day_low?: number | null;
  day_high?: number | null;
  updated_at?: number;
}

interface AssetMonitorTableProps {
  assetClass: 'future' | 'forex';
  groups: MonitorGroup[];
  labels?: Record<string, string>;
  pollMs?: number;
}

function formatPrice(value: number): string {
  if (value >= 1000) return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (value >= 100) return value.toFixed(2);
  if (value >= 1) return value.toFixed(4).replace(/0{1,2}$/, '');
  return value.toFixed(5);
}

function formatChange(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(3).replace(/0$/, '');
  return value.toFixed(5).replace(/0{1,2}$/, '');
}

export function AssetMonitorTable({ assetClass, groups, labels = {}, pollMs = 3000 }: AssetMonitorTableProps) {
  const { t } = useTranslation();
  const userFont = useUserPreferencesStore((s) => s.theme.font);
  const fontFamily = FONT_FAMILIES[userFont] || FONT_FAMILIES['jetbrains-mono'];

  const [entries, setEntries] = useState<Record<string, AssetEntry>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [flash, setFlash] = useState<Record<string, 'up' | 'down'>>({});
  const prevPricesRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    let cancelled = false;

    const fetchSnapshot = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/realtime/class/${assetClass}`);
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        if (cancelled) return;

        const next: Record<string, AssetEntry> = {};
        const nextFlash: Record<string, 'up' | 'down'> = {};
        for (const e of data.results || []) {
          next[e.symbol] = e;
          const prev = prevPricesRef.current[e.symbol];
          if (prev !== undefined && e.price !== prev) {
            nextFlash[e.symbol] = e.price > prev ? 'up' : 'down';
          }
          prevPricesRef.current[e.symbol] = e.price;
        }
        setEntries(next);
        setError(false);
        if (Object.keys(nextFlash).length > 0) {
          setFlash(nextFlash);
          setTimeout(() => { if (!cancelled) setFlash({}); }, 600);
        }
      } catch (err) {
        if (!cancelled) setError(true);
        console.error(`[AssetMonitor:${assetClass}] fetch error:`, err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchSnapshot();
    const interval = setInterval(fetchSnapshot, pollMs);
    return () => { cancelled = true; clearInterval(interval); };
  }, [assetClass, pollMs]);

  const lastUpdate = useMemo(() => {
    let max = 0;
    for (const e of Object.values(entries)) {
      if (e.updated_at && e.updated_at > max) max = e.updated_at;
    }
    return max;
  }, [entries]);

  const totalShown = useMemo(
    () => groups.reduce((acc, g) => acc + g.symbols.filter(s => entries[s]).length, 0),
    [groups, entries]
  );

  if (loading && Object.keys(entries).length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-surface">
        <Loader2 className="w-5 h-5 animate-spin text-muted-fg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-surface" style={{ fontFamily }}>
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-[11px]" style={{ borderCollapse: 'collapse' }}>
          <thead className="sticky top-0 z-10">
            <tr className="text-left uppercase tracking-wide text-foreground/80 bg-surface-inset text-[10px]">
              <th className="px-2 py-1 font-medium">{t('markets.instrument')}</th>
              <th className="px-2 py-1 font-medium text-right w-24">{t('markets.last')}</th>
              <th className="px-2 py-1 font-medium text-right w-20">{t('markets.chg')}</th>
              <th className="px-2 py-1 font-medium text-right w-20 pr-3">{t('markets.chgPct')}</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(group => {
              const rows = group.symbols.filter(s => entries[s]);
              if (rows.length === 0) return null;
              return (
                <React.Fragment key={group.title}>
                  <tr>
                    <td colSpan={4}
                      className="px-2 py-[3px] text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-fg bg-surface-inset/60 border-y border-border-subtle select-none">
                      {group.title}
                    </td>
                  </tr>
                  {rows.map(sym => {
                    const e = entries[sym];
                    const pct = e.change_percent;
                    const chg = e.change;
                    const up = (pct ?? chg ?? 0) >= 0;
                    const flashCls = flash[sym] === 'up'
                      ? 'bg-emerald-500/15'
                      : flash[sym] === 'down' ? 'bg-rose-500/15' : '';
                    return (
                      <tr key={sym} className={`border-b border-border-subtle hover:bg-surface-hover transition-colors ${flashCls}`}>
                        <td className="px-2 py-[3px]">
                          <span className="font-mono font-bold text-foreground">{sym}</span>
                          <span className="ml-2 text-[10px] text-muted-fg">
                            {labels[sym] || e.name || ''}
                          </span>
                        </td>
                        <td className="px-2 py-[3px] text-right font-mono tabular-nums font-semibold text-foreground">
                          {formatPrice(e.price)}
                        </td>
                        <td className={`px-2 py-[3px] text-right font-mono tabular-nums ${up ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {chg != null ? `${chg >= 0 ? '+' : ''}${formatChange(chg)}` : '—'}
                        </td>
                        <td className={`px-2 py-[3px] pr-3 text-right font-mono tabular-nums ${up ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {pct != null ? `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct).toFixed(2)}%` : '—'}
                        </td>
                      </tr>
                    );
                  })}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-2 py-1 border-t border-border bg-surface-hover text-[10px] shrink-0">
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${error ? 'bg-rose-500' : 'bg-emerald-500'}`} />
          <span className={error ? 'text-rose-500' : 'text-emerald-600'}>
            {error ? t('common.offline') : t('common.live')}
          </span>
          {lastUpdate > 0 && (
            <span className="text-muted-fg">
              · {new Date(lastUpdate).toLocaleTimeString('en-US', { hour12: false })}
            </span>
          )}
        </div>
        <span className="text-foreground/80">{totalShown} {t('markets.instruments')}</span>
      </div>
    </div>
  );
}
