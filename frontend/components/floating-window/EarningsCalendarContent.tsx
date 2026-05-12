'use client';

/**
 * EarningsCalendarContent
 *
 * Professional earnings calendar (Bloomberg / Finviz-pro style).
 *
 * Design notes:
 * - Pure CSS-variable palette (no hard-coded `dark:border-white/12` borders that
 *   used to render as bright white lines in dark mode).
 * - Single typographic scale (`xs` 11px / `sm` 12px / `base` 13px) – no more
 *   text-[9px]/[10px]/[11px]/[12px]/[13px] mix.
 * - Zebra rows via background only (no borders between rows). Header sits on a
 *   subtly elevated surface with a single divider underneath.
 * - Beat / miss colored badges instead of plain colored numbers, so the table
 *   keeps a calm look even with lots of green/red.
 * - Status pills (CONF / PROJ) and time-slot chips (BMO / AMC / DUR / TBD)
 *   have their own background tint instead of relying on tiny grey labels.
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

const getLogoUrl = (symbol: string): string =>
  `https://financialmodelingprep.com/image-stock/${symbol}.png`;

// Stable color picker for the initials fallback so the same ticker always
// gets the same accent (avoids the "all logos are blue" effect).
const LOGO_COLORS = [
  '#3b82f6', '#8b5cf6', '#ec4899', '#f97316',
  '#14b8a6', '#06b6d4', '#a855f7', '#f59e0b',
  '#10b981', '#6366f1', '#ef4444', '#22c55e',
];
const colorForSymbol = (s: string): string => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return LOGO_COLORS[h % LOGO_COLORS.length];
};

// ============================================================================
// UTILS
// ============================================================================

const fmt = {
  eps: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '–';
    return v.toFixed(2);
  },
  pct: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '–';
    return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
  },
  rev: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '–';
    if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
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
// SHARED PRIMITIVES
// ============================================================================

function TickerLogo({ symbol, size = 22 }: { symbol: string; size?: number }) {
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const bg = colorForSymbol(symbol);

  const initials = (
    <div
      className="flex items-center justify-center rounded-md font-bold text-white shadow-sm"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.38),
        backgroundColor: bg,
        letterSpacing: '-0.02em',
      }}
    >
      {symbol.slice(0, 2)}
    </div>
  );

  if (error) return initials;

  return (
    <div style={{ width: size, height: size, position: 'relative', flexShrink: 0 }}>
      {!loaded && initials}
      <img
        src={getLogoUrl(symbol)}
        alt={symbol}
        width={size}
        height={size}
        style={{
          position: loaded ? 'relative' : 'absolute',
          top: 0,
          left: 0,
          opacity: loaded ? 1 : 0,
          borderRadius: 6,
          objectFit: 'contain',
          backgroundColor: 'var(--color-surface)',
        }}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
      />
    </div>
  );
}

function TimeSlotChip({ slot }: { slot: EarningsReport['time_slot'] }) {
  const map = {
    BMO: { label: 'BMO', cls: 'text-amber-600 dark:text-amber-300 bg-amber-500/10 dark:bg-amber-400/10' },
    AMC: { label: 'AMC', cls: 'text-indigo-600 dark:text-indigo-300 bg-indigo-500/10 dark:bg-indigo-400/10' },
    DURING: { label: 'DUR', cls: 'text-sky-600 dark:text-sky-300 bg-sky-500/10 dark:bg-sky-400/10' },
    TBD: { label: 'TBD', cls: 'text-zinc-500 dark:text-zinc-400 bg-zinc-500/10' },
  } as const;
  const v = map[slot] ?? map.TBD;
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wider',
        v.cls
      )}
    >
      {v.label}
    </span>
  );
}

function StatusDot({ status }: { status: EarningsReport['date_status'] }) {
  const isConf = status === 'confirmed';
  return (
    <span
      title={isConf ? 'Confirmed' : 'Projected'}
      className={cn(
        'inline-block w-1.5 h-1.5 rounded-full ml-1 align-middle',
        isConf ? 'bg-emerald-500' : 'bg-zinc-400 dark:bg-zinc-600'
      )}
    />
  );
}

function ImportanceStars({ value }: { value: number | null | undefined }) {
  const v = value ?? 0;
  return (
    <span className="inline-flex items-center gap-px tabular-nums">
      <span className="text-amber-500 dark:text-amber-400 text-[11px] leading-none">★</span>
      <span className="text-foreground/70 text-[11px] tabular-nums">{v}</span>
    </span>
  );
}

function NumberCell({
  value,
  format,
  positiveColor,
  negativeColor,
  emphasized = false,
}: {
  value: number | null | undefined;
  format: (v: number | null | undefined) => string;
  positiveColor?: string;
  negativeColor?: string;
  emphasized?: boolean;
}) {
  const empty = value === null || value === undefined;
  const tone = empty
    ? 'text-foreground/35'
    : value! >= 0
      ? undefined
      : undefined;
  const color = empty
    ? undefined
    : value! >= 0
      ? positiveColor
      : negativeColor;
  return (
    <span
      className={cn('tabular-nums', tone, emphasized ? 'font-semibold' : undefined)}
      style={{ color }}
    >
      {format(value)}
    </span>
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
      await new Promise((r) => setTimeout(r, 200));
      const canvas = await html2canvas(targetRef.current, {
        backgroundColor: '#0a0a0a',
        scale: 2,
        logging: false,
        useCORS: true,
      });
      canvas.toBlob(async (blob) => {
        if (blob) {
          try {
            await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
          } catch {
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
      className="inline-flex items-center gap-1 px-2 h-7 rounded-md text-[11px] text-foreground/70 hover:text-foreground hover:bg-foreground/5 transition-colors"
      title="Copy as image"
    >
      {copying ? (
        <span>...</span>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
  gridRef,
}: {
  reports: EarningsReport[];
  date: string;
  up: string;
  down: string;
  gridRef: React.RefObject<HTMLDivElement>;
}) {
  const bmo = reports.filter((r) => r.time_slot === 'BMO');
  const amc = reports.filter((r) => r.time_slot === 'AMC' || r.time_slot === 'DURING');
  const tbd = reports.filter((r) => r.time_slot === 'TBD');

  const renderCard = (r: EarningsReport) => {
    const hasResult = r.status === 'reported';
    const beat = r.beat_eps === true;
    const miss = r.beat_eps === false;

    return (
      <div
        key={`${r.symbol}-${r.report_date}`}
        className={cn(
          'group relative flex flex-col items-center gap-1 p-2 rounded-lg transition-all',
          hasResult && beat && 'bg-emerald-500/10 ring-1 ring-emerald-500/25',
          hasResult && miss && 'bg-rose-500/10 ring-1 ring-rose-500/25',
          (!hasResult || (!beat && !miss)) && 'bg-foreground/[0.04] ring-1 ring-foreground/[0.06]',
          'hover:bg-foreground/[0.07]'
        )}
      >
        <TickerLogo symbol={r.symbol} size={28} />
        <span className="text-[11px] font-semibold leading-none">{r.symbol}</span>
        {hasResult ? (
          <span className="text-[10px] font-semibold leading-none tabular-nums" style={{ color: beat ? up : miss ? down : undefined }}>
            {fmt.pct(r.eps_surprise_pct)}
          </span>
        ) : (
          <span className="text-[9px] text-foreground/45 leading-none">{r.time_slot || 'TBD'}</span>
        )}
      </div>
    );
  };

  const renderSection = (title: string, items: EarningsReport[], accent: string) => (
    <div className="flex-1 flex flex-col min-w-0">
      <div className="px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: accent }} />
          <span className="text-[11px] font-semibold tracking-wide uppercase text-foreground/80">{title}</span>
        </div>
        <span className="text-[11px] tabular-nums text-foreground/55">{items.length}</span>
      </div>
      <div className="flex-1 overflow-auto px-2 pb-2">
        {items.length === 0 ? (
          <div className="h-full flex items-center justify-center text-[11px] text-foreground/40">No earnings</div>
        ) : (
          <div className="grid grid-cols-4 gap-1.5 auto-rows-min">{items.map(renderCard)}</div>
        )}
      </div>
    </div>
  );

  return (
    <div ref={gridRef} className="h-full flex flex-col" style={{ backgroundColor: 'var(--color-surface)', position: 'relative' }}>
      <div className="px-3 py-2 text-center">
        <span className="text-[12px] font-semibold tracking-wide">{fmt.fullDate(date)}</span>
        <span className="text-[11px] text-foreground/50 ml-2 tabular-nums">{reports.length} earnings</span>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {renderSection('Before Market', bmo, '#f59e0b')}
        <div className="w-px bg-foreground/[0.06]" />
        {renderSection('After Market', amc, '#6366f1')}
      </div>

      {tbd.length > 0 && (
        <div className="px-3 py-1.5 border-t border-foreground/[0.06]">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/50">TBD</span>
            <div className="flex gap-1 overflow-x-auto">
              {tbd.slice(0, 18).map((r) => (
                <span key={r.symbol} className="text-[10px] bg-foreground/[0.06] text-foreground/80 px-1.5 py-0.5 rounded">
                  {r.symbol}
                </span>
              ))}
              {tbd.length > 18 && <span className="text-[10px] text-foreground/45">+{tbd.length - 18}</span>}
            </div>
          </div>
        </div>
      )}

      <div
        style={{
          position: 'absolute',
          bottom: 8,
          right: 12,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.5,
          color: 'rgba(255,255,255,0.55)',
          textShadow: '0 1px 2px rgba(0,0,0,0.35)',
          pointerEvents: 'none',
          userSelect: 'none',
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
  const fetchDay = useCallback(
    async (date: string) => {
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
    },
    [apiUrl, minImportance, timeFilter]
  );

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

  const fetchTicker = useCallback(
    async (ticker: string) => {
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
    },
    [apiUrl]
  );

  useEffect(() => {
    if (view === 'day' || view === 'visual') fetchDay(selectedDate);
  }, [view, selectedDate, fetchDay]);

  useEffect(() => {
    if (view === 'week') fetchWeek();
  }, [view, fetchWeek]);

  useEffect(() => {
    if (view === 'search' && searchTicker) fetchTicker(searchTicker);
  }, [view, searchTicker, fetchTicker]);

  const navDate = (days: number) => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  const sortReports = useCallback(
    (reports: EarningsReport[]) => {
      return [...reports].sort((a, b) => {
        let cmp = 0;
        switch (sortField) {
          case 'symbol':
            cmp = a.symbol.localeCompare(b.symbol);
            break;
          case 'time': {
            const order: Record<string, number> = { BMO: 0, DURING: 1, AMC: 2, TBD: 3 };
            cmp = (order[a.time_slot] ?? 3) - (order[b.time_slot] ?? 3);
            break;
          }
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
    },
    [sortField, sortDir]
  );

  const reports = useMemo(() => {
    let data: EarningsReport[] = [];
    if ((view === 'day' || view === 'visual') && dayData?.reports) data = dayData.reports;
    else if (view === 'week' && weekData?.earnings) data = weekData.earnings;
    else if (view === 'search' && tickerData?.earnings) data = tickerData.earnings;
    return sortReports(data);
  }, [view, dayData, weekData, tickerData, sortReports]);

  const toggleSort = (field: SortField) => {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      setSearchTicker(searchInput.trim().toUpperCase());
      setView('search');
    }
  };

  const showDateCol = view === 'week' || view === 'search';

  // ----- Stats summary chips for the toolbar -----
  const summaryChips = useMemo(() => {
    if ((view === 'day' || view === 'visual') && dayData) {
      return [
        { label: 'Total', value: dayData.total_count ?? 0, tone: 'neutral' as const },
        { label: 'BMO', value: dayData.total_bmo ?? 0, tone: 'amber' as const },
        { label: 'AMC', value: dayData.total_amc ?? 0, tone: 'indigo' as const },
        { label: 'Conf.', value: dayData.total_confirmed ?? 0, tone: 'emerald' as const },
      ];
    }
    if (view === 'week' && weekData) {
      return [{ label: 'Upcoming', value: weekData.total_count ?? 0, tone: 'neutral' as const }];
    }
    if (view === 'search' && tickerData) {
      const beatRate = tickerData.stats?.beat_rate;
      const chips: Array<{ label: string; value: string | number; tone: 'neutral' | 'amber' | 'indigo' | 'emerald' | 'rose' }> = [
        { label: 'Reports', value: tickerData.count ?? 0, tone: 'neutral' },
      ];
      if (beatRate != null) chips.push({ label: 'Beat rate', value: `${beatRate.toFixed(0)}%`, tone: beatRate >= 50 ? 'emerald' : 'rose' });
      return chips;
    }
    return [];
  }, [view, dayData, weekData, tickerData]);

  const chipToneClass = (tone: 'neutral' | 'amber' | 'indigo' | 'emerald' | 'rose'): string => {
    switch (tone) {
      case 'amber':
        return 'text-amber-600 dark:text-amber-300 bg-amber-500/10';
      case 'indigo':
        return 'text-indigo-600 dark:text-indigo-300 bg-indigo-500/10';
      case 'emerald':
        return 'text-emerald-600 dark:text-emerald-300 bg-emerald-500/10';
      case 'rose':
        return 'text-rose-600 dark:text-rose-300 bg-rose-500/10';
      default:
        return 'text-foreground/70 bg-foreground/[0.06]';
    }
  };

  // ----- Row renderer -----
  const renderRow = (r: EarningsReport, idx: number) => {
    const rowKey = `${r.symbol}-${r.report_date}`;
    const isExpanded = expandedRow === rowKey;
    const epsGrowth = fmt.growth(r.eps_actual, r.previous_eps);
    const revGrowth = fmt.growth(r.revenue_actual, r.previous_revenue);
    const reported = r.status === 'reported';

    return (
      <React.Fragment key={rowKey}>
        <tr
          className={cn(
            'transition-colors cursor-pointer',
            idx % 2 === 1 ? 'bg-foreground/[0.025]' : 'bg-transparent',
            'hover:bg-foreground/[0.06]'
          )}
          onClick={() => setExpandedRow(isExpanded ? null : rowKey)}
        >
          {/* Logo */}
          <td className="pl-3 pr-1 py-1.5 w-8">
            <TickerLogo symbol={r.symbol} size={22} />
          </td>

          {/* Ticker + Company */}
          <td className="px-2 py-1.5 text-[13px] min-w-[120px] max-w-[180px]">
            <div className="flex flex-col leading-tight">
              <span className="font-semibold tracking-tight flex items-center gap-1">
                {r.symbol}
                <StatusDot status={r.date_status} />
              </span>
              <span className="text-[11px] text-foreground/55 truncate">{r.company_name || '—'}</span>
            </div>
          </td>

          {/* Date column (only week/search) */}
          {showDateCol && (
            <td className="px-2 py-1.5 text-[12px] text-foreground/65">
              <div className="leading-tight">
                <div className="font-medium">{fmt.weekday(r.report_date)}</div>
                <div className="text-[11px] text-foreground/45">{fmt.date(r.report_date)}</div>
              </div>
            </td>
          )}

          {/* Fiscal Period */}
          <td className="px-2 py-1.5 text-center text-[12px] text-foreground/65 tabular-nums">
            {r.fiscal_period || '—'}
          </td>

          {/* Time slot */}
          <td className="px-2 py-1.5 text-center">
            <TimeSlotChip slot={r.time_slot} />
          </td>

          {/* Importance */}
          <td className="px-2 py-1.5 text-center">
            <ImportanceStars value={r.importance} />
          </td>

          {/* EPS Est */}
          <td className="px-2 py-1.5 text-right text-[12px] tabular-nums text-foreground/65">
            {fmt.eps(r.eps_estimate)}
          </td>

          {/* EPS Act */}
          <td className="px-2 py-1.5 text-right text-[12px]">
            <NumberCell
              value={r.eps_actual}
              format={fmt.eps}
              positiveColor={r.beat_eps === true ? up : undefined}
              negativeColor={r.beat_eps === false ? down : undefined}
              emphasized
            />
          </td>

          {/* EPS Surp % */}
          <td className="px-2 py-1.5 text-right text-[12px]">
            <NumberCell value={r.eps_surprise_pct} format={fmt.pct} positiveColor={up} negativeColor={down} />
          </td>

          {/* Rev Est */}
          <td className="px-2 py-1.5 text-right text-[12px] tabular-nums text-foreground/65">
            {fmt.rev(r.revenue_estimate)}
          </td>

          {/* Rev Act */}
          <td className="px-2 py-1.5 text-right text-[12px]">
            <NumberCell
              value={r.revenue_actual}
              format={fmt.rev}
              positiveColor={r.beat_revenue === true ? up : undefined}
              negativeColor={r.beat_revenue === false ? down : undefined}
              emphasized
            />
          </td>

          {/* Rev Surp % */}
          <td className="px-2 py-1.5 text-right text-[12px]">
            <NumberCell value={r.revenue_surprise_pct} format={fmt.pct} positiveColor={up} negativeColor={down} />
          </td>

          {/* YoY EPS */}
          <td className="px-2 py-1.5 text-right text-[11px]">
            {epsGrowth != null ? (
              <NumberCell value={epsGrowth} format={fmt.pct} positiveColor={up} negativeColor={down} />
            ) : (
              <span className="text-foreground/35">—</span>
            )}
          </td>

          {/* YoY Rev */}
          <td className="px-2 py-1.5 text-right text-[11px]">
            {revGrowth != null ? (
              <NumberCell value={revGrowth} format={fmt.pct} positiveColor={up} negativeColor={down} />
            ) : (
              <span className="text-foreground/35">—</span>
            )}
          </td>

          {/* Method */}
          <td className="pr-3 pl-2 py-1.5 text-center text-[10px] text-foreground/45">
            {r.eps_method?.toUpperCase().slice(0, 3) || '—'}
          </td>
        </tr>

        {isExpanded && (
          <tr className="bg-foreground/[0.04]">
            <td colSpan={showDateCol ? 15 : 14} className="px-4 py-3 text-[12px]">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2">
                <DetailItem label="Fiscal Year">{r.fiscal_year ?? '—'}</DetailItem>
                <DetailItem label="EPS Method">{r.eps_method?.toUpperCase() || '—'}</DetailItem>
                <DetailItem label="Rev Method">{r.revenue_method?.toUpperCase() || '—'}</DetailItem>
                <DetailItem label="Prev EPS">{fmt.eps(r.previous_eps)}</DetailItem>
                <DetailItem label="Prev Rev">{fmt.rev(r.previous_revenue)}</DetailItem>
                <DetailItem label="Importance">{r.importance ?? '—'} / 5</DetailItem>
                {r.sector && <DetailItem label="Sector">{r.sector}</DetailItem>}
                <DetailItem label="Status">
                  <span
                    className={cn(
                      'inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider',
                      reported
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300'
                        : 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-300'
                    )}
                  >
                    {reported ? 'Reported' : 'Scheduled'}
                  </span>
                </DetailItem>
                {r.notes && (
                  <div className="col-span-full">
                    <DetailItem label="Notes">{r.notes}</DetailItem>
                  </div>
                )}
                {r.guidance_commentary && (
                  <div className="col-span-full">
                    <DetailItem label="Guidance">{r.guidance_commentary}</DetailItem>
                  </div>
                )}
              </div>
            </td>
          </tr>
        )}
      </React.Fragment>
    );
  };

  // Sortable column header
  const ColHeader = ({ field, label, align = 'center' }: { field: SortField; label: string; align?: 'left' | 'center' | 'right' }) => {
    const active = sortField === field;
    return (
      <th
        scope="col"
        className={cn(
          'px-2 py-2 font-medium text-[10px] uppercase tracking-wider select-none cursor-pointer transition-colors',
          active ? 'text-foreground' : 'text-foreground/55 hover:text-foreground/85',
          align === 'right' ? 'text-right' : align === 'left' ? 'text-left' : 'text-center'
        )}
        onClick={() => toggleSort(field)}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          <span className={cn('text-[9px] transition-opacity', active ? 'opacity-100' : 'opacity-0')}>
            {sortDir === 'desc' ? '▼' : '▲'}
          </span>
        </span>
      </th>
    );
  };

  // Static (non-sortable) column header
  const StaticHeader = ({ label, align = 'center' }: { label: string; align?: 'left' | 'center' | 'right' }) => (
    <th
      scope="col"
      className={cn(
        'px-2 py-2 font-medium text-[10px] uppercase tracking-wider text-foreground/55',
        align === 'right' ? 'text-right' : align === 'left' ? 'text-left' : 'text-center'
      )}
    >
      {label}
    </th>
  );

  // ===== Toolbar (used by every view) =====
  const Toolbar = () => (
    <div
      className="flex items-center gap-2 px-3 h-11 border-b"
      style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.18))' }}
    >
      {/* View tabs */}
      <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-foreground/[0.05]">
        {(['day', 'week', 'visual', 'search'] as ViewMode[]).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={cn(
              'px-2.5 h-7 rounded text-[11px] font-medium uppercase tracking-wider transition-all',
              view === v
                ? 'bg-foreground/[0.10] text-foreground shadow-sm'
                : 'text-foreground/55 hover:text-foreground/90 hover:bg-foreground/[0.04]'
            )}
          >
            {v === 'day' ? 'Day' : v === 'week' ? 'Week' : v === 'visual' ? 'Grid' : 'Find'}
          </button>
        ))}
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="relative">
        <svg
          className="absolute left-2 top-1/2 -translate-y-1/2 text-foreground/45 pointer-events-none"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
          placeholder="Ticker..."
          className="bg-foreground/[0.04] hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] text-foreground placeholder:text-foreground/40 rounded-md pl-7 pr-2 h-7 text-[11px] w-[140px] outline-none transition-colors border border-transparent focus:border-foreground/15"
        />
      </form>

      <div className="flex-1" />

      {/* Date pager (day / visual) */}
      {(view === 'day' || view === 'visual') && (
        <div className="flex items-center gap-1 p-0.5 rounded-md bg-foreground/[0.05]">
          <button
            onClick={() => navDate(-1)}
            className="w-6 h-6 rounded text-foreground/65 hover:text-foreground hover:bg-foreground/[0.08] transition-colors text-[12px] leading-none"
            title="Previous day"
          >
            ‹
          </button>
          <button
            onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
            className="px-2 h-6 rounded text-foreground hover:bg-foreground/[0.08] text-[11px] font-medium tracking-tight min-w-[88px]"
            title="Jump to today"
          >
            {fmt.fullDate(selectedDate)}
          </button>
          <button
            onClick={() => navDate(1)}
            className="w-6 h-6 rounded text-foreground/65 hover:text-foreground hover:bg-foreground/[0.08] transition-colors text-[12px] leading-none"
            title="Next day"
          >
            ›
          </button>
        </div>
      )}

      {view === 'visual' && <ShareButton targetRef={gridRef} />}
    </div>
  );

  // ===== Filters bar =====
  const FiltersBar = () => (
    <div
      className="flex items-center gap-3 px-3 h-9 border-b"
      style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.12))' }}
    >
      {/* Importance */}
      <div className="flex items-center gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/45">Imp.</span>
        <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-foreground/[0.04]">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <button
              key={i}
              onClick={() => setMinImportance(i)}
              className={cn(
                'w-6 h-6 rounded text-[10px] font-semibold tabular-nums transition-colors',
                minImportance === i
                  ? 'bg-amber-500/20 text-amber-600 dark:text-amber-300'
                  : 'text-foreground/55 hover:text-foreground/90 hover:bg-foreground/[0.05]'
              )}
              title={i === 0 ? 'No filter' : `Importance ≥ ${i}`}
            >
              {i === 0 ? '·' : i}
            </button>
          ))}
        </div>
      </div>

      {/* Time-slot filter (day view only) */}
      {view === 'day' && (
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/45">Time</span>
          <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-foreground/[0.04]">
            {(['all', 'BMO', 'AMC'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTimeFilter(t)}
                className={cn(
                  'px-2 h-6 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors',
                  timeFilter === t
                    ? t === 'BMO'
                      ? 'bg-amber-500/20 text-amber-600 dark:text-amber-300'
                      : t === 'AMC'
                        ? 'bg-indigo-500/20 text-indigo-600 dark:text-indigo-300'
                        : 'bg-foreground/[0.10] text-foreground'
                    : 'text-foreground/55 hover:text-foreground/90 hover:bg-foreground/[0.05]'
                )}
              >
                {t === 'all' ? 'All' : t}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1" />

      {/* Summary chips */}
      <div className="flex items-center gap-1.5">
        {summaryChips.map((c) => (
          <span
            key={c.label}
            className={cn('inline-flex items-center gap-1 px-2 h-6 rounded-md text-[10px] font-semibold uppercase tracking-wider', chipToneClass(c.tone))}
          >
            <span className="opacity-70">{c.label}</span>
            <span className="tabular-nums">{c.value}</span>
          </span>
        ))}
      </div>
    </div>
  );

  // ----- Visual view -----
  if (view === 'visual') {
    return (
      <div
        className={cn('h-full flex flex-col text-foreground overflow-hidden', fontClass)}
        style={{ backgroundColor: 'var(--color-surface)' }}
      >
        <Toolbar />
        <div className="flex-1 overflow-hidden">
          {loading ? (
            <CenterMessage>Loading…</CenterMessage>
          ) : error ? (
            <CenterMessage tone="error">{error}</CenterMessage>
          ) : (
            <VisualGridView reports={dayData?.reports || []} date={selectedDate} up={up} down={down} gridRef={gridRef} />
          )}
        </div>
        <Footer count={reports.length} />
      </div>
    );
  }

  // ----- Table view (day / week / search) -----
  return (
    <div
      className={cn('h-full flex flex-col text-foreground overflow-hidden', fontClass)}
      style={{ backgroundColor: 'var(--color-surface)' }}
    >
      <Toolbar />
      <FiltersBar />

      <div className="flex-1 overflow-auto">
        {loading ? (
          <CenterMessage>Loading…</CenterMessage>
        ) : error ? (
          <CenterMessage tone="error">{error}</CenterMessage>
        ) : reports.length === 0 ? (
          <CenterMessage>{view === 'search' && !searchTicker ? 'Enter a ticker to search' : 'No earnings found'}</CenterMessage>
        ) : (
          <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
            <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--color-surface)' }}>
              <tr
                style={{
                  borderBottom: '1px solid var(--color-border, rgba(127,127,127,0.18))',
                }}
              >
                <th className="pl-3 pr-1 py-2 w-8" />
                <ColHeader field="symbol" label="Ticker" align="left" />
                {showDateCol && <StaticHeader label="Date" align="left" />}
                <StaticHeader label="Q" />
                <ColHeader field="time" label="Time" />
                <ColHeader field="importance" label="Imp" />
                <StaticHeader label="EPS Est" align="right" />
                <StaticHeader label="EPS Act" align="right" />
                <ColHeader field="eps_surprise" label="EPS %" align="right" />
                <StaticHeader label="Rev Est" align="right" />
                <StaticHeader label="Rev Act" align="right" />
                <ColHeader field="rev_surprise" label="Rev %" align="right" />
                <StaticHeader label="YoY EPS" align="right" />
                <StaticHeader label="YoY Rev" align="right" />
                <StaticHeader label="Src" />
              </tr>
            </thead>
            <tbody>{reports.map((r, idx) => renderRow(r, idx))}</tbody>
          </table>
        )}
      </div>

      <Footer count={reports.length} />
    </div>
  );
}

// ============================================================================
// SMALL HELPERS
// ============================================================================

function CenterMessage({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'error' }) {
  return (
    <div
      className={cn(
        'flex items-center justify-center h-full text-[12px]',
        tone === 'error' ? 'text-rose-500 dark:text-rose-400' : 'text-foreground/45'
      )}
    >
      {children}
    </div>
  );
}

function Footer({ count }: { count: number }) {
  return (
    <div
      className="flex items-center justify-between px-3 h-7 border-t text-[10px] text-foreground/55"
      style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.12))' }}
    >
      <span className="tabular-nums">{count} showing</span>
      <span className="opacity-70">tradeul.com</span>
    </div>
  );
}

function DetailItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-foreground/45">{label}</span>
      <span className="text-foreground/85">{children}</span>
    </div>
  );
}

export default EarningsCalendarContent;
