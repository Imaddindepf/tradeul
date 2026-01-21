'use client';

/**
 * EarningsCalendarContent
 * 
 * Bloomberg-style earnings calendar floating window.
 * Dense information, professional design, user font preferences.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useUserPreferencesStore, selectFont, selectColors } from '@/stores/useUserPreferencesStore';
import { ChevronLeft, ChevronRight, RefreshCw, Sun, Moon, Clock, TrendingUp, TrendingDown, Minus, Filter } from 'lucide-react';
import { cn } from '@/lib/utils';

// ============================================================================
// TYPES
// ============================================================================

interface EarningsReport {
  symbol: string;
  company_name: string;
  report_date: string;
  time_slot: 'BMO' | 'AMC' | 'DURING' | 'TBD';
  fiscal_quarter: string | null;
  eps_estimate: number | null;
  eps_actual: number | null;
  eps_surprise_pct: number | null;
  beat_eps: boolean | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  revenue_surprise_pct: number | null;
  beat_revenue: boolean | null;
  guidance_direction: 'raised' | 'lowered' | 'maintained' | 'none' | null;
  guidance_commentary: string | null;
  key_highlights: string[] | null;
  status: 'scheduled' | 'reported' | 'confirmed';
}

interface EarningsResponse {
  date: string;
  reports: EarningsReport[];
  total_bmo: number;
  total_amc: number;
  total_reported: number;
  total_scheduled: number;
}

type FilterType = 'all' | 'bmo' | 'amc' | 'beats' | 'misses' | 'scheduled';

// ============================================================================
// FONT MAPPING
// ============================================================================

const FONT_CLASS_MAP: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

// ============================================================================
// COMPONENT
// ============================================================================

export function EarningsCalendarContent() {
  const font = useUserPreferencesStore(selectFont);
  const colors = useUserPreferencesStore(selectColors);

  const [data, setData] = useState<EarningsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    return new Date().toISOString().split('T')[0];
  });
  const [filter, setFilter] = useState<FilterType>('all');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';

  // Fetch earnings
  const fetchEarnings = useCallback(async (date: string) => {
    setLoading(true);
    setError(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/api/v1/earnings/calendar?date=${date}`);

      if (!response.ok) throw new Error(`Error ${response.status}`);

      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEarnings(selectedDate);
  }, [selectedDate, fetchEarnings]);

  // Filter logic
  const filteredReports = useMemo(() => {
    if (!data?.reports) return [];

    switch (filter) {
      case 'bmo':
        return data.reports.filter(r => r.time_slot === 'BMO');
      case 'amc':
        return data.reports.filter(r => r.time_slot === 'AMC');
      case 'beats':
        return data.reports.filter(r => r.status === 'reported' && r.beat_eps === true);
      case 'misses':
        return data.reports.filter(r => r.status === 'reported' && r.beat_eps === false);
      case 'scheduled':
        return data.reports.filter(r => r.status === 'scheduled');
      default:
        return data.reports;
    }
  }, [data, filter]);

  // Stats
  const stats = useMemo(() => {
    if (!data?.reports) return null;
    const reported = data.reports.filter(r => r.status === 'reported');
    const beats = reported.filter(r => r.beat_eps === true);
    const beatRate = reported.length > 0 ? (beats.length / reported.length * 100) : 0;
    return {
      total: data.reports.length,
      reported: reported.length,
      scheduled: data.reports.length - reported.length,
      beats: beats.length,
      misses: reported.length - beats.length,
      beatRate: beatRate.toFixed(0),
      bmo: data.total_bmo,
      amc: data.total_amc
    };
  }, [data]);

  // Formatters
  const fmt = {
    currency: (v: number | null, d = 2) => v !== null ? `$${v.toFixed(d)}` : '-',
    pct: (v: number | null) => v !== null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '-',
    rev: (v: number | null) => {
      if (v === null) return '-';
      if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
      if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
      return `$${v.toLocaleString()}`;
    }
  };

  // Navigate date
  const navDate = (days: number) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  // Colors from user preferences
  const up = colors.tickUp || '#22c55e';
  const down = colors.tickDown || '#ef4444';

  return (
    <div className={cn('h-full flex flex-col bg-background text-foreground overflow-hidden', fontClass)}>
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/40">
        {/* Date Nav */}
        <div className="flex items-center gap-1">
          <button onClick={() => navDate(-1)} className="p-1 hover:bg-muted rounded transition-colors">
            <ChevronLeft className="w-4 h-4" />
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-transparent text-xs px-2 py-1 border border-border rounded focus:border-primary outline-none w-28"
          />
          <button onClick={() => navDate(1)} className="p-1 hover:bg-muted rounded transition-colors">
            <ChevronRight className="w-4 h-4" />
          </button>
          <button
            onClick={() => fetchEarnings(selectedDate)}
            className="p-1 hover:bg-muted rounded transition-colors ml-1"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="flex items-center gap-3 text-[10px]">
            <span className="text-muted-foreground">{stats.total} TOTAL</span>
            <span className="flex items-center gap-1 text-amber-500">
              <Sun className="w-3 h-3" />{stats.bmo}
            </span>
            <span className="flex items-center gap-1 text-primary">
              <Moon className="w-3 h-3" />{stats.amc}
            </span>
            <span style={{ color: up }}>{stats.beats} BEAT</span>
            <span style={{ color: down }}>{stats.misses} MISS</span>
            <span className="px-1.5 py-0.5 rounded text-[9px] font-medium" style={{
              backgroundColor: Number(stats.beatRate) >= 50 ? `${up}15` : `${down}15`,
              color: Number(stats.beatRate) >= 50 ? up : down
            }}>
              {stats.beatRate}%
            </span>
          </div>
        )}
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border/30">
        {([
          { key: 'all', label: 'ALL' },
          { key: 'bmo', label: 'BMO' },
          { key: 'amc', label: 'AMC' },
          { key: 'beats', label: 'BEATS' },
          { key: 'misses', label: 'MISSES' },
          { key: 'scheduled', label: 'SCHED' },
        ] as const).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={cn(
              'px-2 py-0.5 text-[10px] font-medium rounded transition-colors',
              filter === key
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-destructive text-xs">{error}</div>
        ) : filteredReports.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-xs">No earnings</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-background/95 backdrop-blur-sm z-10">
              <tr className="border-b border-border/40">
                <th className="text-left px-2 py-1.5 font-medium text-muted-foreground w-20">TICKER</th>
                <th className="text-center px-1 py-1.5 font-medium text-muted-foreground w-12">TIME</th>
                <th className="text-right px-2 py-1.5 font-medium text-muted-foreground w-16">EPS EST</th>
                <th className="text-right px-2 py-1.5 font-medium text-muted-foreground w-16">EPS ACT</th>
                <th className="text-right px-2 py-1.5 font-medium text-muted-foreground w-16">SURP</th>
                <th className="text-right px-2 py-1.5 font-medium text-muted-foreground w-16">REV</th>
                <th className="text-center px-1 py-1.5 font-medium text-muted-foreground w-14">GUIDE</th>
                <th className="text-center px-2 py-1.5 font-medium text-muted-foreground w-16">STATUS</th>
              </tr>
            </thead>
            <tbody>
              {filteredReports.map((r) => {
                const isExpanded = expandedRow === r.symbol;
                const hasDetails = r.key_highlights?.length || r.guidance_commentary;

                return (
                  <React.Fragment key={`${r.symbol}-${r.report_date}`}>
                    <tr
                      className={cn(
                        'border-b border-border/20 hover:bg-muted/20 cursor-pointer transition-colors',
                        isExpanded && 'bg-muted/30'
                      )}
                      onClick={() => hasDetails && setExpandedRow(isExpanded ? null : r.symbol)}
                    >
                      {/* Ticker */}
                      <td className="px-2 py-1.5">
                        <div className="flex flex-col">
                          <span className="font-bold">{r.symbol}</span>
                          <span className="text-[9px] text-muted-foreground truncate max-w-[80px]">{r.company_name}</span>
                        </div>
                      </td>

                      {/* Time */}
                      <td className="text-center px-1 py-1.5">
                        <div className="flex items-center justify-center gap-0.5">
                          {r.time_slot === 'BMO' ? (
                            <Sun className="w-3 h-3 text-amber-500" />
                          ) : r.time_slot === 'AMC' ? (
                            <Moon className="w-3 h-3 text-primary" />
                          ) : (
                            <Clock className="w-3 h-3 text-muted-foreground" />
                          )}
                        </div>
                      </td>

                      {/* EPS Est */}
                      <td className="text-right px-2 py-1.5 font-mono text-muted-foreground">
                        {fmt.currency(r.eps_estimate)}
                      </td>

                      {/* EPS Act */}
                      <td className="text-right px-2 py-1.5 font-mono font-bold" style={{
                        color: r.beat_eps === true ? up : r.beat_eps === false ? down : undefined
                      }}>
                        {r.eps_actual !== null ? fmt.currency(r.eps_actual) : '-'}
                      </td>

                      {/* Surprise */}
                      <td className="text-right px-2 py-1.5 font-mono" style={{
                        color: r.eps_surprise_pct !== null
                          ? (r.eps_surprise_pct >= 0 ? up : down)
                          : undefined
                      }}>
                        {fmt.pct(r.eps_surprise_pct)}
                      </td>

                      {/* Revenue */}
                      <td className="text-right px-2 py-1.5 font-mono" style={{
                        color: r.beat_revenue === true ? up : r.beat_revenue === false ? down : undefined
                      }}>
                        {r.revenue_actual ? fmt.rev(r.revenue_actual) : fmt.rev(r.revenue_estimate)}
                      </td>

                      {/* Guidance */}
                      <td className="text-center px-1 py-1.5">
                        {r.guidance_direction === 'raised' ? (
                          <span className="text-[10px] font-bold px-1 rounded" style={{ color: up, backgroundColor: `${up}15` }}>UP</span>
                        ) : r.guidance_direction === 'lowered' ? (
                          <span className="text-[10px] font-bold px-1 rounded" style={{ color: down, backgroundColor: `${down}15` }}>DN</span>
                        ) : r.guidance_direction === 'maintained' ? (
                          <span className="text-[10px] font-medium text-muted-foreground">=</span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="text-center px-2 py-1.5">
                        <span className={cn(
                          'px-1.5 py-0.5 rounded text-[9px] font-bold uppercase',
                          r.status === 'reported'
                            ? r.beat_eps ? 'bg-emerald-500/20 text-emerald-500' : 'bg-red-500/20 text-red-500'
                            : 'bg-muted text-muted-foreground'
                        )}>
                          {r.status === 'reported' ? (r.beat_eps ? 'BEAT' : 'MISS') : 'PEND'}
                        </span>
                      </td>
                    </tr>

                    {/* Expanded Details */}
                    {isExpanded && hasDetails && (
                      <tr className="bg-muted/10">
                        <td colSpan={8} className="px-4 py-2.5">
                          <div className="space-y-1.5 text-[10px]">
                            {r.guidance_commentary && (
                              <div className="flex gap-2">
                                <span className="text-muted-foreground shrink-0 font-medium">GUIDANCE:</span>
                                <span>{r.guidance_commentary}</span>
                              </div>
                            )}
                            {r.key_highlights?.map((h, i) => (
                              <div key={i} className="flex gap-2">
                                <span className="text-primary shrink-0">-</span>
                                <span className="text-muted-foreground">{h}</span>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-1.5 border-t border-border/30 text-[9px] text-muted-foreground flex justify-between">
        <span>Click row for details</span>
        <span>Q4 2025</span>
      </div>
    </div>
  );
}

export default EarningsCalendarContent;
