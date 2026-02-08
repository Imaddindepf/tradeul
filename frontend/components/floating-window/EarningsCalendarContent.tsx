'use client';

/**
 * EarningsCalendarContent
 * 
 * Professional earnings calendar with full Benzinga data.
 * Clean, compact, no icons/emojis. Multiple views including visual grid.
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useUserPreferencesStore, selectFont, selectColors } from '@/stores/useUserPreferencesStore';
import { cn } from '@/lib/utils';
import html2canvas from 'html2canvas';

// ============================================================================
// TYPES
// ============================================================================

interface EarningsReport {
  symbol: string;
  company_name: string;
  report_date: string;
  time_slot: 'BMO' | 'AMC' | 'DURING' | 'TBD';
  fiscal_quarter: string | null;
  fiscal_year: number | null;
  fiscal_period: string | null;
  eps_estimate: number | null;
  eps_actual: number | null;
  eps_surprise_pct: number | null;
  beat_eps: boolean | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  revenue_surprise_pct: number | null;
  beat_revenue: boolean | null;
  guidance_direction: string | null;
  guidance_commentary: string | null;
  key_highlights: string[] | null;
  status: 'scheduled' | 'reported';
  importance: number | null;
  date_status: 'confirmed' | 'projected' | null;
  eps_method: string | null;
  revenue_method: string | null;
  previous_eps: number | null;
  previous_revenue: number | null;
  sector: string | null;
  notes: string | null;
}

interface CalendarResponse {
  date: string;
  reports: EarningsReport[];
  total_count: number;
  total_bmo: number;
  total_amc: number;
  total_reported: number;
  total_scheduled: number;
  total_confirmed: number;
  total_projected: number;
}

interface UpcomingResponse {
  start_date: string;
  end_date: string;
  earnings: EarningsReport[];
  total_count: number;
  by_date: Record<string, number>;
}

interface TickerResponse {
  symbol: string;
  earnings: EarningsReport[];
  count: number;
  stats: {
    total_reported: number;
    beats: number;
    misses: number;
    beat_rate: number | null;
  };
}

type ViewMode = 'day' | 'week' | 'visual' | 'search';
type SortField = 'symbol' | 'time' | 'importance' | 'eps_surprise' | 'rev_surprise';
type SortDir = 'asc' | 'desc';

// ============================================================================
// CONFIG
// ============================================================================

const FONT_CLASS_MAP: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

// Logo service - Financial Modeling Prep (direct, good coverage)
const getLogoUrl = (symbol: string): string => {
  return `https://financialmodelingprep.com/image-stock/${symbol}.png`;
};

// ============================================================================
// UTILS
// ============================================================================

const fmt = {
  eps: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '-';
    return v.toFixed(2);
  },
  pct: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '-';
    return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
  },
  rev: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '-';
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
    return v.toLocaleString();
  },
  growth: (curr: number | null | undefined, prev: number | null | undefined): number | null => {
    if (curr === null || curr === undefined || prev === null || prev === undefined || prev === 0) return null;
    return ((curr - prev) / Math.abs(prev)) * 100;
  },
  date: (d: string): string => {
    const dt = new Date(d + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  },
  weekday: (d: string): string => {
    const dt = new Date(d + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { weekday: 'short' });
  },
  fullDate: (d: string): string => {
    const dt = new Date(d + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  },
};

// ============================================================================
// LOGO COMPONENT
// ============================================================================

function TickerLogo({ symbol, size = 24 }: { symbol: string; size?: number }) {
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // Styled initials fallback
  const initials = (
    <div
      className="flex items-center justify-center rounded font-bold"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.35,
        backgroundColor: '#3b82f6',
        color: '#fff'
      }}
    >
      {symbol.slice(0, 2)}
    </div>
  );

  if (error) return initials;

  return (
    <div style={{ width: size, height: size, position: 'relative' }}>
      {!loaded && initials}
      <img
        src={getLogoUrl(symbol)}
        alt={symbol}
        width={size}
        height={size}
        style={{
          position: loaded ? 'relative' : 'absolute',
          top: 0, left: 0,
          opacity: loaded ? 1 : 0,
          borderRadius: 4,
          objectFit: 'contain',
          backgroundColor: '#fff'
        }}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
      />
    </div>
  );
}

// ============================================================================
// SHARE BUTTON
// ============================================================================

function ShareButton({ targetRef }: { targetRef: React.RefObject<HTMLDivElement> }) {
  const [copying, setCopying] = useState(false);

  const handleShare = async () => {
    if (!targetRef.current || copying) return;

    setCopying(true);
    try {
      // Wait a bit for any pending image loads
      await new Promise(r => setTimeout(r, 200));

      const canvas = await html2canvas(targetRef.current, {
        backgroundColor: '#1a1a1a',
        scale: 2,
        logging: false,
        useCORS: true,
      });

      canvas.toBlob(async (blob) => {
        if (blob) {
          try {
            await navigator.clipboard.write([
              new ClipboardItem({ 'image/png': blob })
            ]);
          } catch {
            // Fallback: download
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `earnings-${new Date().toISOString().split('T')[0]}.png`;
            a.click();
            URL.revokeObjectURL(url);
          }
        }
        setCopying(false);
      }, 'image/png');
    } catch (e) {
      console.error('Share error:', e);
      setCopying(false);
    }
  };

  return (
    <button
      onClick={handleShare}
      disabled={copying}
      className="px-1.5 py-0.5 hover:bg-muted rounded text-[11px] text-muted-foreground hover:text-foreground transition-colors"
      title="Copy as image"
    >
      {copying ? '...' : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
          <polyline points="16 6 12 2 8 6" />
          <line x1="12" y1="2" x2="12" y2="15" />
        </svg>
      )}
    </button>
  );
}

// ============================================================================
// VISUAL GRID VIEW
// ============================================================================

function VisualGridView({
  reports,
  date,
  up,
  down,
  gridRef
}: {
  reports: EarningsReport[];
  date: string;
  up: string;
  down: string;
  gridRef: React.RefObject<HTMLDivElement>;
}) {
  const bmo = reports.filter(r => r.time_slot === 'BMO');
  const amc = reports.filter(r => r.time_slot === 'AMC' || r.time_slot === 'DURING');
  const tbd = reports.filter(r => r.time_slot === 'TBD');

  const renderCard = (r: EarningsReport) => {
    const hasResult = r.status === 'reported';
    const beat = r.beat_eps === true;
    const miss = r.beat_eps === false;

    return (
      <div
        key={`${r.symbol}-${r.report_date}`}
        className={cn(
          'flex flex-col items-center p-1 rounded border transition-colors',
          hasResult
            ? beat
              ? 'border-green-500/40 bg-green-500/5'
              : miss
                ? 'border-red-500/40 bg-red-500/5'
                : 'border-border/30 bg-muted/10'
            : 'border-border/30 bg-muted/10'
        )}
      >
        <TickerLogo symbol={r.symbol} size={24} />
        <span className="text-[10px] font-semibold mt-0.5 leading-tight">{r.symbol}</span>
        {hasResult && (
          <span
            className="text-[9px] font-medium leading-tight"
            style={{ color: beat ? up : miss ? down : undefined }}
          >
            {fmt.pct(r.eps_surprise_pct)}
          </span>
        )}
      </div>
    );
  };

  const renderSection = (title: string, items: EarningsReport[], count: number) => (
    <div className="flex-1 flex flex-col min-w-0">
      <div className="flex items-center justify-between px-1.5 py-0.5 border-b border-border/30">
        <span className="text-[10px] font-semibold">{title}</span>
        <span className="text-[9px] text-muted-foreground">{count}</span>
      </div>
      <div className="flex-1 overflow-auto p-1">
        {items.length === 0 ? (
          <div className="h-full flex items-center justify-center text-[9px] text-muted-foreground">
            No earnings
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-1 auto-rows-min">
            {items.map(renderCard)}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div ref={gridRef} className="h-full flex flex-col bg-background" style={{ position: 'relative' }}>
      {/* Date header */}
      <div className="px-2 py-1 border-b border-border/40 text-center">
        <span className="text-[11px] font-semibold">{fmt.fullDate(date)}</span>
        <span className="text-[9px] text-muted-foreground ml-2">
          {reports.length} earnings
        </span>
      </div>

      {/* Two columns: BMO | AMC */}
      <div className="flex-1 flex overflow-hidden">
        {renderSection('BEFORE MARKET', bmo, bmo.length)}
        <div className="w-px bg-border/40" />
        {renderSection('AFTER MARKET', amc, amc.length)}
      </div>

      {/* TBD row if any */}
      {tbd.length > 0 && (
        <div className="border-t border-border/40">
          <div className="px-1.5 py-0.5 flex items-center gap-1">
            <span className="text-[9px] text-muted-foreground">TBD:</span>
            <div className="flex gap-0.5 overflow-x-auto">
              {tbd.slice(0, 15).map(r => (
                <span key={r.symbol} className="text-[9px] bg-muted/50 px-1 rounded">
                  {r.symbol}
                </span>
              ))}
              {tbd.length > 15 && (
                <span className="text-[9px] text-muted-foreground">+{tbd.length - 15}</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Watermark overlay */}
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          right: 12,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.5,
          color: 'rgba(255,255,255,0.85)',
          textShadow: '0 1px 3px rgba(0,0,0,0.5), 0 0 8px rgba(0,0,0,0.3)',
          pointerEvents: 'none',
          userSelect: 'none'
        }}
      >
        Tradeul.com
      </div>
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export function EarningsCalendarContent() {
  const font = useUserPreferencesStore(selectFont);
  const colors = useUserPreferencesStore(selectColors);
  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';
  const up = colors?.tickUp || '#22c55e';
  const down = colors?.tickDown || '#ef4444';
  const gridRef = useRef<HTMLDivElement>(null);

  // State
  const [view, setView] = useState<ViewMode>('day');
  const [selectedDate, setSelectedDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [searchTicker, setSearchTicker] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [minImportance, setMinImportance] = useState<number>(0);
  const [timeFilter, setTimeFilter] = useState<'all' | 'BMO' | 'AMC'>('all');
  const [sortField, setSortField] = useState<SortField>('importance');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  // Data state
  const [dayData, setDayData] = useState<CalendarResponse | null>(null);
  const [weekData, setWeekData] = useState<UpcomingResponse | null>(null);
  const [tickerData, setTickerData] = useState<TickerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Fetch day data
  const fetchDay = useCallback(async (date: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ date });
      if (minImportance > 0) params.set('min_importance', String(minImportance));
      if (timeFilter !== 'all') params.set('time_slot', timeFilter);

      const res = await fetch(`${apiUrl}/api/v1/earnings/calendar?${params}`);
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();
      setDayData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  }, [apiUrl, minImportance, timeFilter]);

  // Fetch week data
  const fetchWeek = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ days: '7' });
      if (minImportance > 0) params.set('min_importance', String(minImportance));

      const res = await fetch(`${apiUrl}/api/v1/earnings/upcoming?${params}`);
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();
      setWeekData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  }, [apiUrl, minImportance]);

  // Fetch ticker data
  const fetchTicker = useCallback(async (ticker: string) => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/api/v1/earnings/ticker/${ticker.toUpperCase()}?limit=20`);
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();
      setTickerData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  // Effects
  useEffect(() => {
    if (view === 'day' || view === 'visual') fetchDay(selectedDate);
  }, [view, selectedDate, fetchDay]);

  useEffect(() => {
    if (view === 'week') fetchWeek();
  }, [view, fetchWeek]);

  useEffect(() => {
    if (view === 'search' && searchTicker) fetchTicker(searchTicker);
  }, [view, searchTicker, fetchTicker]);

  // Navigation
  const navDate = (days: number) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  // Sort function
  const sortReports = useCallback((reports: EarningsReport[]) => {
    return [...reports].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case 'time':
          const order: Record<string, number> = { BMO: 0, DURING: 1, AMC: 2, TBD: 3 };
          cmp = (order[a.time_slot] ?? 3) - (order[b.time_slot] ?? 3);
          break;
        case 'importance':
          cmp = (b.importance ?? -1) - (a.importance ?? -1);
          break;
        case 'eps_surprise':
          cmp = Math.abs(b.eps_surprise_pct ?? 0) - Math.abs(a.eps_surprise_pct ?? 0);
          break;
        case 'rev_surprise':
          cmp = Math.abs(b.revenue_surprise_pct ?? 0) - Math.abs(a.revenue_surprise_pct ?? 0);
          break;
      }
      return sortDir === 'desc' ? cmp : -cmp;
    });
  }, [sortField, sortDir]);

  // Get current reports
  const reports = useMemo(() => {
    let data: EarningsReport[] = [];
    if ((view === 'day' || view === 'visual') && dayData?.reports) {
      data = dayData.reports;
    } else if (view === 'week' && weekData?.earnings) {
      data = weekData.earnings;
    } else if (view === 'search' && tickerData?.earnings) {
      data = tickerData.earnings;
    }
    return sortReports(data);
  }, [view, dayData, weekData, tickerData, sortReports]);

  // Header click for sorting
  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  // Search handler
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      setSearchTicker(searchInput.trim().toUpperCase());
      setView('search');
    }
  };

  // Show date column in week/search views
  const showDateCol = view === 'week' || view === 'search';

  // Row component
  const renderRow = (r: EarningsReport, idx: number) => {
    const isExpanded = expandedRow === `${r.symbol}-${r.report_date}`;
    const epsGrowth = fmt.growth(r.eps_actual, r.previous_eps);
    const revGrowth = fmt.growth(r.revenue_actual, r.previous_revenue);

    return (
      <React.Fragment key={`${r.symbol}-${r.report_date}`}>
        <tr
          className={cn(
            'border-b border-border/10 transition-colors',
            idx % 2 === 1 ? 'bg-muted/5' : '',
            'hover:bg-muted/20 cursor-pointer'
          )}
          onClick={() => setExpandedRow(isExpanded ? null : `${r.symbol}-${r.report_date}`)}
        >
          {/* Logo */}
          <td className="px-1 py-1 w-7">
            <TickerLogo symbol={r.symbol} size={20} />
          </td>

          {/* Ticker */}
          <td className="px-1 py-0.5 text-[13px]">
            <div className="flex flex-col">
              <span className="font-semibold">{r.symbol}</span>
              <span className="text-[10px] text-muted-foreground truncate max-w-[70px]">
                {r.company_name || '-'}
              </span>
            </div>
          </td>

          {/* Date (if week/search view) */}
          {showDateCol && (
            <td className="px-1 py-0.5 text-center text-[12px] text-muted-foreground">
              <div>{fmt.weekday(r.report_date)}</div>
              <div>{fmt.date(r.report_date)}</div>
            </td>
          )}

          {/* Fiscal Period */}
          <td className="px-1 py-0.5 text-center text-[12px] text-muted-foreground">
            {r.fiscal_period || '-'}
          </td>

          {/* Time + Status */}
          <td className="px-1 py-0.5 text-center text-[12px]">
            <div className={r.date_status === 'confirmed' ? 'text-foreground' : 'text-muted-foreground'}>
              {r.time_slot || 'TBD'}
            </div>
            <div className="text-[9px] text-muted-foreground">
              {r.date_status === 'confirmed' ? 'conf' : 'proj'}
            </div>
          </td>

          {/* EPS Est */}
          <td className="px-1 py-0.5 text-right tabular-nums text-[12px] text-muted-foreground">
            {fmt.eps(r.eps_estimate)}
          </td>

          {/* EPS Act */}
          <td
            className="px-1 py-0.5 text-right tabular-nums font-medium text-[12px]"
            style={{ color: r.beat_eps === true ? up : r.beat_eps === false ? down : undefined }}
          >
            {fmt.eps(r.eps_actual)}
          </td>

          {/* EPS Surp % */}
          <td
            className="px-1 py-0.5 text-right tabular-nums text-[12px]"
            style={{ color: r.eps_surprise_pct != null ? (r.eps_surprise_pct >= 0 ? up : down) : undefined }}
          >
            {fmt.pct(r.eps_surprise_pct)}
          </td>

          {/* Revenue Est */}
          <td className="px-1 py-0.5 text-right tabular-nums text-[12px] text-muted-foreground">
            {fmt.rev(r.revenue_estimate)}
          </td>

          {/* Revenue Act */}
          <td
            className="px-1 py-0.5 text-right tabular-nums font-medium text-[12px]"
            style={{ color: r.beat_revenue === true ? up : r.beat_revenue === false ? down : undefined }}
          >
            {fmt.rev(r.revenue_actual)}
          </td>

          {/* Revenue Surp % */}
          <td
            className="px-1 py-0.5 text-right tabular-nums text-[12px]"
            style={{ color: r.revenue_surprise_pct != null ? (r.revenue_surprise_pct >= 0 ? up : down) : undefined }}
          >
            {fmt.pct(r.revenue_surprise_pct)}
          </td>

          {/* YoY EPS */}
          <td
            className="px-1 py-0.5 text-right tabular-nums text-[11px]"
            style={{ color: epsGrowth != null ? (epsGrowth >= 0 ? up : down) : undefined }}
          >
            {epsGrowth != null ? fmt.pct(epsGrowth) : '-'}
          </td>

          {/* YoY Rev */}
          <td
            className="px-1 py-0.5 text-right tabular-nums text-[11px]"
            style={{ color: revGrowth != null ? (revGrowth >= 0 ? up : down) : undefined }}
          >
            {revGrowth != null ? fmt.pct(revGrowth) : '-'}
          </td>

          {/* Method */}
          <td className="px-1 py-0.5 text-center text-[10px] text-muted-foreground">
            {r.eps_method?.toUpperCase().slice(0, 3) || '-'}
          </td>
        </tr>

        {/* Expanded details */}
        {isExpanded && (
          <tr className="bg-muted/10">
            <td colSpan={showDateCol ? 15 : 14} className="px-2 py-2 text-[11px]">
              <div className="grid grid-cols-3 gap-x-4 gap-y-1">
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">Fiscal Year: </span>
                  {r.fiscal_year || '-'}
                </div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">EPS Method: </span>
                  {r.eps_method?.toUpperCase() || '-'}
                </div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">Rev Method: </span>
                  {r.revenue_method?.toUpperCase() || '-'}
                </div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">Prev EPS: </span>
                  {fmt.eps(r.previous_eps)}
                </div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">Prev Rev: </span>
                  {fmt.rev(r.previous_revenue)}
                </div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground">Importance: </span>
                  {r.importance ?? '-'}/5
                </div>
                {r.sector && (
                  <div className="text-muted-foreground">
                    <span className="font-medium text-foreground">Sector: </span>
                    {r.sector}
                  </div>
                )}
                {r.notes && (
                  <div className="text-muted-foreground col-span-3">
                    <span className="font-medium text-foreground">Notes: </span>
                    {r.notes}
                  </div>
                )}
                {r.guidance_commentary && (
                  <div className="text-muted-foreground col-span-3">
                    <span className="font-medium text-foreground">Guidance: </span>
                    {r.guidance_commentary}
                  </div>
                )}
              </div>
            </td>
          </tr>
        )}
      </React.Fragment>
    );
  };

  // Column header
  const ColHeader = ({ field, label, align = 'center' }: { field: SortField; label: string; align?: string }) => (
    <th
      className={cn(
        'px-1 py-1 font-medium text-muted-foreground cursor-pointer hover:text-foreground text-[10px]',
        align === 'right' ? 'text-right' : align === 'left' ? 'text-left' : 'text-center'
      )}
      onClick={() => toggleSort(field)}
    >
      {label}
      {sortField === field && <span className="ml-0.5">{sortDir === 'desc' ? 'v' : '^'}</span>}
    </th>
  );

  // Stats
  const statsText = useMemo(() => {
    if ((view === 'day' || view === 'visual') && dayData) {
      return `${dayData.total_count ?? 0} | B:${dayData.total_bmo ?? 0} A:${dayData.total_amc ?? 0}`;
    }
    if (view === 'week' && weekData) {
      return `${weekData.total_count ?? 0} upcoming`;
    }
    if (view === 'search' && tickerData) {
      const beatRate = tickerData.stats?.beat_rate;
      const beatText = beatRate != null ? ` | ${beatRate.toFixed(0)}%` : '';
      return `${tickerData.count ?? 0}${beatText}`;
    }
    return '';
  }, [view, dayData, weekData, tickerData]);

  // Show visual view
  if (view === 'visual') {
    return (
      <div className={cn('h-full flex flex-col bg-background text-foreground overflow-hidden', fontClass)}>
        {/* Header */}
        <div className="flex items-center justify-between px-2 py-1 border-b border-border/40 gap-2">
          {/* View tabs */}
          <div className="flex items-center gap-0.5">
            {(['day', 'week', 'visual', 'search'] as ViewMode[]).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={cn(
                  'px-2 py-0.5 rounded transition-colors text-[11px]',
                  view === v ? 'bg-muted text-foreground font-medium' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {v === 'day' ? 'DAY' : v === 'week' ? 'WEEK' : v === 'visual' ? 'GRID' : 'FIND'}
              </button>
            ))}
          </div>

          {/* Date navigation + Share */}
          <div className="flex items-center gap-1">
            <button onClick={() => navDate(-1)} className="px-1.5 py-0.5 hover:bg-muted rounded text-[11px]">{'<'}</button>
            <button
              onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
              className="px-1.5 py-0.5 hover:bg-muted rounded min-w-[80px] text-center text-[11px]"
            >
              {fmt.date(selectedDate)}
            </button>
            <button onClick={() => navDate(1)} className="px-1.5 py-0.5 hover:bg-muted rounded text-[11px]">{'>'}</button>
            <ShareButton targetRef={gridRef} />
          </div>
        </div>

        {/* Visual Grid */}
        <div className="flex-1 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center h-full text-[11px] text-muted-foreground">
              Loading...
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full text-[11px] text-muted-foreground">
              {error}
            </div>
          ) : (
            <VisualGridView
              reports={dayData?.reports || []}
              date={selectedDate}
              up={up}
              down={down}
              gridRef={gridRef}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-2 py-0.5 border-t border-border/30 text-[9px] text-muted-foreground">
          <span>{statsText}</span>
          <span>tradeul.com</span>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('h-full flex flex-col bg-background text-foreground overflow-hidden', fontClass)}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/40 gap-2">
        {/* View tabs */}
        <div className="flex items-center gap-0.5">
          {(['day', 'week', 'visual', 'search'] as ViewMode[]).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                'px-2 py-0.5 rounded transition-colors text-[11px]',
                view === v ? 'bg-muted text-foreground font-medium' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {v === 'day' ? 'DAY' : v === 'week' ? 'WEEK' : v === 'visual' ? 'GRID' : 'FIND'}
            </button>
          ))}
        </div>

        {/* Search input */}
        <form onSubmit={handleSearch} className="flex-1 max-w-[120px]">
          <input
            type="text"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value.toUpperCase())}
            placeholder="Ticker..."
            className="w-full bg-transparent border border-border/50 rounded px-1.5 py-0.5 text-[11px] focus:border-foreground/50 outline-none"
          />
        </form>

        {/* Day navigation (only in day view) */}
        {view === 'day' && (
          <div className="flex items-center gap-1">
            <button onClick={() => navDate(-1)} className="px-1.5 py-0.5 hover:bg-muted rounded text-[11px]">{'<'}</button>
            <button
              onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
              className="px-1.5 py-0.5 hover:bg-muted rounded min-w-[80px] text-center text-[11px]"
            >
              {fmt.date(selectedDate)}
            </button>
            <button onClick={() => navDate(1)} className="px-1.5 py-0.5 hover:bg-muted rounded text-[11px]">{'>'}</button>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-border/30 gap-2">
        {/* Importance filter */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-muted-foreground">IMP:</span>
          {[0, 1, 2, 3, 4, 5].map(i => (
            <button
              key={i}
              onClick={() => setMinImportance(i)}
              className={cn(
                'w-5 h-5 rounded text-center text-[10px]',
                minImportance === i ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {i}
            </button>
          ))}
        </div>

        {/* Time filter (day view only) */}
        {view === 'day' && (
          <div className="flex items-center gap-1">
            {(['all', 'BMO', 'AMC'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTimeFilter(t)}
                className={cn(
                  'px-1.5 py-0.5 rounded text-[10px]',
                  timeFilter === t ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {t}
              </button>
            ))}
          </div>
        )}

        {/* Stats */}
        <div className="text-[10px] text-muted-foreground">
          {statsText}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full text-[11px] text-muted-foreground">
            Loading...
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-[11px] text-muted-foreground">
            {error}
          </div>
        ) : reports.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[11px] text-muted-foreground">
            {view === 'search' && !searchTicker ? 'Enter ticker to search' : 'No earnings found'}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-background/95 backdrop-blur-sm z-10">
              <tr className="border-b border-border/40">
                <th className="px-1 py-1 w-7"></th>
                <ColHeader field="symbol" label="TICKER" align="left" />
                {showDateCol && <th className="px-1 py-1 font-medium text-muted-foreground text-[10px]">DATE</th>}
                <th className="px-1 py-1 font-medium text-muted-foreground text-center text-[10px]">Q</th>
                <ColHeader field="time" label="TIME" />
                <th className="px-1 py-1 font-medium text-muted-foreground text-right text-[10px]">EPS Est</th>
                <th className="px-1 py-1 font-medium text-muted-foreground text-right text-[10px]">EPS Act</th>
                <ColHeader field="eps_surprise" label="EPS%" align="right" />
                <th className="px-1 py-1 font-medium text-muted-foreground text-right text-[10px]">Rev Est</th>
                <th className="px-1 py-1 font-medium text-muted-foreground text-right text-[10px]">Rev Act</th>
                <ColHeader field="rev_surprise" label="Rev%" align="right" />
                <th className="px-1 py-1 font-medium text-muted-foreground text-right text-[10px]">YoY E</th>
                <th className="px-1 py-1 font-medium text-muted-foreground text-right text-[10px]">YoY R</th>
                <th className="px-1 py-1 font-medium text-muted-foreground text-center text-[10px]">MTD</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r, idx) => renderRow(r, idx))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-2 py-0.5 border-t border-border/30 text-[9px] text-muted-foreground">
        <span>{reports.length} showing</span>
        <span>tradeul.com</span>
      </div>
    </div>
  );
}

export default EarningsCalendarContent;
