'use client';

/**
 * EarningsCalendarContent
 *
 * Earnings calendar served by our own API gateway (/api/v1/earnings/*):
 *
 *  - A week strip (Sun–Sat) with per-day call counts + top-company logos,
 *    driven by /api/v1/earnings/schedule.
 *  - A per-day list of companies with logo, name, ticker, fiscal period, the
 *    local report time and the AI summary bullets, driven by
 *    /api/v1/earnings/calendar.
 *  - A detail modal opened by clicking a company: quarter strip (per-symbol
 *    history), estimate vs actual + surprise, expected vs realized price move,
 *    and tabs for Highlights / Transcript / Documents.
 *
 * TIMEZONE: everything is rendered in the user's preferred timezone
 * (theme.timezone, default America/New_York). We pass `timezone` to every
 * endpoint so day bucketing matches, and the backend returns a pre-formatted
 * local `report_time` (HH:MM) plus the BMO/AMC/DURING slot (always ET-based).
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  useUserPreferencesStore,
  selectFont,
  selectColors,
  selectTimezone,
} from '@/stores/useUserPreferencesStore';
import { cn } from '@/lib/utils';
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { registerTickerSearch } from '@/lib/tickerSearchRegistry';

// ============================================================================
// TYPES
// ============================================================================

interface DayReport {
  symbol: string;
  company_name: string | null;
  event_id: number | null;
  report_date: string | null;
  report_time: string | null;
  utc_time: string | null;
  time_slot: 'BMO' | 'AMC' | 'DURING' | 'TBD';
  fiscal_year: number | null;
  fiscal_period: string | null;
  fiscal_quarter: string | null;
  eps_estimate: number | null;
  eps_actual: number | null;
  eps_surprise_pct: number | null;
  beat_eps: boolean | null;
  revenue_estimate: number | null;
  revenue_actual: number | null;
  revenue_surprise_pct: number | null;
  beat_revenue: boolean | null;
  summary: string | null;
  key_highlights: string[] | null;
  expected_move_pct: number | null;
  post_earnings_move_1d: number | null;
  market_cap: number | null;
  currency: string | null;
  status: 'scheduled' | 'reported';
  importance: number | null;
  source: string | null;
}

interface CalendarResponse {
  date: string;
  timezone: string;
  reports: DayReport[];
  total_count: number;
  total_bmo: number;
  total_amc: number;
  total_during: number;
  total_reported: number;
  total_scheduled: number;
}

interface ScheduleDay {
  date: string;
  count: number;
  top_companies: { symbol: string }[];
}

interface EventRow {
  symbol: string;
  event_id: number | null;
  report_date: string | null;
  report_time: string | null;
  time_slot: string;
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
  expected_move_pct: number | null;
  post_earnings_move_1d: number | null;
  avg_post_earnings_move_1d: number | null;
  status: string;
}

interface TranscriptResponse {
  symbol: string;
  event_id: number;
  status: string | null;
  report_date: string | null;
  report_time: string | null;
  audio_url: string | null;
  speakers: string[];
  chapters: { id: number; title: string; start: number; end: number; level: number }[];
  paragraphs: { time: number; text: string; speakers: string[] }[];
}

interface DocumentItem {
  id: number;
  file_url: string;
  type: string;
  name: string | null;
  description: string | null;
  form: string | null;
  category: string | null;
}

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

const WEEKDAYS_ES = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
const MONTHS_ES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

// ============================================================================
// UTILS
// ============================================================================

const fmt = {
  eps: (v: number | null | undefined): string => (v === null || v === undefined ? '–' : v.toFixed(2)),
  pct: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '–';
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  },
  // fraction (e.g. 0.0282) -> "+2.82%"
  moveFrac: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '–';
    const p = v * 100;
    return `${p >= 0 ? '+' : ''}${p.toFixed(2)}%`;
  },
  rev: (v: number | null | undefined): string => {
    if (v === null || v === undefined) return '–';
    const abs = Math.abs(v);
    if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    return v.toLocaleString();
  },
};

// Parse a YYYY-MM-DD string as a *calendar* date (noon avoids tz shifting).
const parseYmd = (d: string): Date => new Date(d + 'T12:00:00');
const toYmd = (d: Date): string => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};
const shortDate = (ymd: string): string => {
  const d = parseYmd(ymd);
  return `${d.getDate()} ${MONTHS_ES[d.getMonth()]}`;
};
const weekdayOf = (ymd: string): string => WEEKDAYS_ES[parseYmd(ymd).getDay()];

// Sunday that starts the week containing `ymd`.
const startOfWeek = (ymd: string): Date => {
  const d = parseYmd(ymd);
  d.setDate(d.getDate() - d.getDay());
  return d;
};

// ============================================================================
// SHARED PRIMITIVES
// ============================================================================

function TickerLogo({ symbol, size = 28 }: { symbol: string; size?: number }) {
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const bg = colorForSymbol(symbol);

  const initials = (
    <div
      className="flex items-center justify-center rounded-md font-bold text-white shadow-sm"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.36),
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
          borderRadius: 8,
          objectFit: 'contain',
          backgroundColor: 'var(--color-surface)',
        }}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
      />
    </div>
  );
}

function TimeSlotChip({ slot }: { slot: string }) {
  const map: Record<string, { label: string; cls: string; title: string }> = {
    BMO: { label: 'BMO', title: 'Before Market Open', cls: 'text-amber-600 dark:text-amber-300 bg-amber-500/10' },
    AMC: { label: 'AMC', title: 'After Market Close', cls: 'text-indigo-600 dark:text-indigo-300 bg-indigo-500/10' },
    DURING: { label: 'DUR', title: 'During Market', cls: 'text-sky-600 dark:text-sky-300 bg-sky-500/10' },
    TBD: { label: 'TBD', title: 'Time TBD', cls: 'text-zinc-500 dark:text-zinc-400 bg-zinc-500/10' },
  };
  const v = map[slot] ?? map.TBD;
  return (
    <span
      title={v.title}
      className={cn('inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wider', v.cls)}
    >
      {v.label}
    </span>
  );
}

function MoveBadge({ value, up, down }: { value: number | null; up: string; down: string }) {
  if (value === null || value === undefined) return <span className="text-foreground/35 text-[11px]">–</span>;
  const pos = value >= 0;
  return (
    <span className="text-[11px] font-semibold tabular-nums" style={{ color: pos ? up : down }}>
      {fmt.moveFrac(value)}
    </span>
  );
}

// ============================================================================
// WEEK STRIP
// ============================================================================

function WeekStrip({
  days,
  selectedDate,
  onSelect,
}: {
  days: ScheduleDay[];
  selectedDate: string;
  onSelect: (d: string) => void;
}) {
  return (
    <div className="grid grid-cols-7 gap-1.5 px-3 py-2">
      {days.map((d) => {
        const isSel = d.date === selectedDate;
        return (
          <button
            key={d.date}
            onClick={() => onSelect(d.date)}
            className={cn(
              'flex flex-col items-center gap-1 rounded-lg px-1 py-2 transition-all border',
              isSel
                ? 'bg-foreground/[0.08] border-foreground/20'
                : 'bg-foreground/[0.02] border-transparent hover:bg-foreground/[0.05]'
            )}
          >
            <span className="text-[10px] uppercase tracking-wider text-foreground/45">{weekdayOf(d.date)}</span>
            <span className="text-[13px] font-semibold leading-none">{shortDate(d.date)}</span>
            {d.count > 0 ? (
              <div className="flex items-center gap-1 mt-0.5">
                <div className="flex -space-x-1.5">
                  {d.top_companies.slice(0, 3).map((c) => (
                    <div key={c.symbol} className="ring-1 ring-[var(--color-surface)] rounded">
                      <TickerLogo symbol={c.symbol} size={16} />
                    </div>
                  ))}
                </div>
                <span className="text-[10px] text-foreground/60 tabular-nums">{d.count}</span>
              </div>
            ) : (
              <span className="text-[10px] text-foreground/35 mt-0.5">Sin llamadas</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ============================================================================
// COMPANY CARD (day list)
// ============================================================================

function CompanyCard({ r, onClick }: { r: DayReport; onClick: () => void }) {
  const highlights = r.key_highlights || [];
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3 border-b transition-colors hover:bg-foreground/[0.03]"
      style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}
    >
      <div className="flex items-start gap-3">
        <TickerLogo symbol={r.symbol} size={30} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[13px] font-semibold truncate">{r.company_name || r.symbol}</div>
              <div className="text-[11px] text-foreground/50">{r.symbol}</div>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <div className="flex items-center gap-1.5">
                {r.fiscal_period && r.fiscal_year && (
                  <span className="text-[11px] font-medium text-foreground/70">
                    {r.fiscal_period} {r.fiscal_year}
                  </span>
                )}
                {r.report_time ? (
                  <span className="text-[11px] tabular-nums text-foreground/55">{r.report_time}</span>
                ) : (
                  <TimeSlotChip slot={r.time_slot} />
                )}
              </div>
            </div>
          </div>

          {highlights.length > 0 && (
            <ul className="mt-1.5 space-y-1">
              {highlights.slice(0, 3).map((h, i) => (
                <li key={i} className="flex gap-1.5 text-[12px] leading-snug text-foreground/75">
                  <span className="text-foreground/30 select-none">•</span>
                  <span className="min-w-0">{h}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </button>
  );
}

// ============================================================================
// DETAIL MODAL
// ============================================================================

type DetailTab = 'highlights' | 'transcript' | 'documents';

function StatBox({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-foreground/45">{label}</span>
      <span className="text-[13px] font-semibold tabular-nums" style={{ color: tone }}>{value}</span>
    </div>
  );
}

function EventDetailModal({
  report,
  apiUrl,
  tz,
  up,
  down,
  onClose,
}: {
  report: DayReport;
  apiUrl: string;
  tz: string;
  up: string;
  down: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<DetailTab>('highlights');
  const [history, setHistory] = useState<EventRow[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(report.event_id);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [docsLoading, setDocsLoading] = useState(false);

  const tzq = encodeURIComponent(tz);

  // Load per-symbol quarter history for the strip.
  useEffect(() => {
    const c = new AbortController();
    fetch(`${apiUrl}/api/v1/earnings/ticker/${report.symbol}?timezone=${tzq}&limit=40`, { signal: c.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setHistory(d?.earnings || []))
      .catch(() => {});
    return () => c.abort();
  }, [apiUrl, report.symbol, tzq]);

  const selectedEvent: EventRow | undefined = useMemo(
    () => history.find((e) => e.event_id === selectedEventId),
    [history, selectedEventId]
  );

  // Merge: prefer live per-symbol row (has estimates) but fall back to the
  // clicked day report (has the AI summary bullets).
  const merged = useMemo(() => {
    const e = selectedEvent;
    const isSameEvent = selectedEventId === report.event_id;
    return {
      symbol: report.symbol,
      company_name: report.company_name,
      fiscal_period: e?.fiscal_period ?? report.fiscal_period,
      fiscal_year: e?.fiscal_year ?? report.fiscal_year,
      report_time: e?.report_time ?? report.report_time,
      report_date: e?.report_date ?? report.report_date,
      eps_estimate: e?.eps_estimate ?? report.eps_estimate,
      eps_actual: e?.eps_actual ?? report.eps_actual,
      eps_surprise_pct: e?.eps_surprise_pct ?? report.eps_surprise_pct,
      beat_eps: e?.beat_eps ?? report.beat_eps,
      revenue_estimate: e?.revenue_estimate ?? report.revenue_estimate,
      revenue_actual: e?.revenue_actual ?? report.revenue_actual,
      revenue_surprise_pct: e?.revenue_surprise_pct ?? report.revenue_surprise_pct,
      beat_revenue: e?.beat_revenue ?? report.beat_revenue,
      expected_move_pct: e?.expected_move_pct ?? report.expected_move_pct,
      post_earnings_move_1d: e?.post_earnings_move_1d ?? report.post_earnings_move_1d,
      highlights: isSameEvent ? report.key_highlights || [] : [],
    };
  }, [selectedEvent, selectedEventId, report]);

  // Lazy-load transcript when the tab is opened.
  useEffect(() => {
    if (tab !== 'transcript' || selectedEventId == null) return;
    setTranscript(null);
    setTranscriptLoading(true);
    const c = new AbortController();
    fetch(`${apiUrl}/api/v1/earnings/event/${report.symbol}/${selectedEventId}/transcript?timezone=${tzq}`, { signal: c.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setTranscript(d))
      .catch(() => {})
      .finally(() => setTranscriptLoading(false));
    return () => c.abort();
  }, [tab, selectedEventId, apiUrl, report.symbol, tzq]);

  // Lazy-load documents when the tab is opened.
  useEffect(() => {
    if (tab !== 'documents' || selectedEventId == null) return;
    setDocuments(null);
    setDocsLoading(true);
    const c = new AbortController();
    fetch(`${apiUrl}/api/v1/earnings/event/${report.symbol}/${selectedEventId}/documents`, { signal: c.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDocuments(d?.documents || []))
      .catch(() => {})
      .finally(() => setDocsLoading(false));
    return () => c.abort();
  }, [tab, selectedEventId, apiUrl, report.symbol]);

  const surpTone = (beat: boolean | null) => (beat === true ? up : beat === false ? down : undefined);

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-3xl max-h-full flex flex-col rounded-xl shadow-2xl overflow-hidden"
        style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border, rgba(127,127,127,0.2))' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.15))' }}>
          <TickerLogo symbol={report.symbol} size={36} />
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold truncate">{report.company_name || report.symbol}</div>
            <div className="text-[11px] text-foreground/50">{report.symbol}</div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-md text-foreground/60 hover:text-foreground hover:bg-foreground/10 transition-colors text-[16px] leading-none"
          >
            ×
          </button>
        </div>

        {/* Quarter strip */}
        {history.length > 0 && (
          <div className="flex gap-1.5 overflow-x-auto px-4 py-2 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
            {history.map((e) => {
              const isSel = e.event_id === selectedEventId;
              const reported = e.eps_actual !== null;
              return (
                <button
                  key={e.event_id}
                  onClick={() => setSelectedEventId(e.event_id)}
                  className={cn(
                    'shrink-0 flex flex-col items-center gap-0.5 rounded-md px-2.5 py-1.5 border transition-colors',
                    isSel ? 'bg-foreground/[0.10] border-foreground/25' : 'bg-foreground/[0.03] border-transparent hover:bg-foreground/[0.06]'
                  )}
                >
                  <span className="text-[11px] font-medium whitespace-nowrap">{e.fiscal_period} {e.fiscal_year}</span>
                  {reported ? (
                    <MoveBadge value={e.post_earnings_move_1d} up={up} down={down} />
                  ) : (
                    <span className="text-[10px] text-foreground/45">próximo</span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Selected event summary line */}
        <div className="px-4 py-2.5 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
          <div className="text-[13px] font-semibold">
            Llamada de resultados de {report.symbol} {merged.fiscal_year} {merged.fiscal_period}
          </div>
          <div className="text-[11px] text-foreground/50">
            {merged.report_date}{merged.report_time ? ` · ${merged.report_time}` : ''}
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2.5 mt-3">
            <StatBox label="Ingresos est." value={fmt.rev(merged.revenue_estimate)} />
            <StatBox label="Ingresos real" value={fmt.rev(merged.revenue_actual)} tone={surpTone(merged.beat_revenue)} />
            <StatBox label="Sorpresa ingr." value={fmt.pct(merged.revenue_surprise_pct)} tone={surpTone(merged.beat_revenue)} />
            <StatBox label="Mov. esperado" value={fmt.moveFrac(merged.expected_move_pct)} />
            <StatBox label="BPA est." value={fmt.eps(merged.eps_estimate)} />
            <StatBox label="BPA real" value={fmt.eps(merged.eps_actual)} tone={surpTone(merged.beat_eps)} />
            <StatBox label="Sorpresa BPA" value={fmt.pct(merged.eps_surprise_pct)} tone={surpTone(merged.beat_eps)} />
            <StatBox
              label="Mov. precio 1d"
              value={<MoveBadge value={merged.post_earnings_move_1d} up={up} down={down} />}
            />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 px-4 py-1.5 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
          {([
            ['highlights', 'Momentos destacados'],
            ['transcript', 'Transcripción'],
            ['documents', 'Documentos'],
          ] as [DetailTab, string][]).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                'px-2.5 h-7 rounded text-[11px] font-medium transition-colors',
                tab === id ? 'bg-foreground/[0.10] text-foreground' : 'text-foreground/55 hover:text-foreground/90 hover:bg-foreground/[0.05]'
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-auto px-4 py-3 min-h-[160px]">
          {tab === 'highlights' && (
            merged.highlights.length > 0 ? (
              <ul className="space-y-2">
                {merged.highlights.map((h, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-foreground/85">
                    <span className="text-foreground/30 select-none mt-0.5">•</span>
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">
                {selectedEventId === report.event_id
                  ? 'Sin resumen disponible para esta llamada.'
                  : 'Selecciona la llamada actual para ver el resumen.'}
              </div>
            )
          )}

          {tab === 'transcript' && (
            transcriptLoading ? (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">Cargando transcripción…</div>
            ) : transcript && transcript.paragraphs.length > 0 ? (
              <div className="space-y-3">
                {transcript.audio_url && (
                  <audio controls src={transcript.audio_url} className="w-full h-8" />
                )}
                {transcript.paragraphs.map((p, i) => (
                  <div key={i} className="text-[13px] leading-relaxed">
                    {p.speakers.length > 0 && (
                      <span className="font-semibold text-foreground/90 mr-1.5">{p.speakers.join(', ')}:</span>
                    )}
                    <span className="text-foreground/75">{p.text}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">Transcripción no disponible todavía.</div>
            )
          )}

          {tab === 'documents' && (
            docsLoading ? (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">Cargando documentos…</div>
            ) : documents && documents.length > 0 ? (
              <div className="space-y-1.5">
                {documents.map((d) => (
                  <a
                    key={d.id}
                    href={d.file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 px-3 py-2 rounded-lg bg-foreground/[0.03] hover:bg-foreground/[0.07] transition-colors"
                  >
                    <span className="inline-flex items-center justify-center min-w-[42px] h-6 px-1.5 rounded text-[10px] font-bold bg-foreground/10 text-foreground/70">
                      {d.form || d.type || 'DOC'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium truncate">{d.name || 'Documento'}</div>
                      {d.description && <div className="text-[11px] text-foreground/50 truncate">{d.description}</div>}
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-foreground/40">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">Sin documentos para esta llamada.</div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

type ViewMode = 'day' | 'search';

export function EarningsCalendarContent() {
  const font = useUserPreferencesStore(selectFont);
  const colors = useUserPreferencesStore(selectColors);
  const tz = useUserPreferencesStore(selectTimezone);
  const fontClass = FONT_CLASS_MAP[font] || 'font-jetbrains-mono';
  const up = colors?.tickUp || '#22c55e';
  const down = colors?.tickDown || '#ef4444';

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const tzq = encodeURIComponent(tz);

  const [view, setView] = useState<ViewMode>('day');
  const [selectedDate, setSelectedDate] = useState(() => toYmd(new Date()));
  const [searchInput, setSearchInput] = useState('');
  const [searchTicker, setSearchTicker] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [dayData, setDayData] = useState<CalendarResponse | null>(null);
  const [schedule, setSchedule] = useState<ScheduleDay[]>([]);
  const [tickerData, setTickerData] = useState<EventRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [modalReport, setModalReport] = useState<DayReport | null>(null);

  // Type-ahead search routing.
  const ecWindowId = useCurrentWindowId();
  useEffect(() => {
    if (!ecWindowId) return;
    return registerTickerSearch(ecWindowId, {
      getInput: () => searchInputRef.current,
      type: (char: string) => {
        searchInputRef.current?.focus();
        setSearchInput(char.toUpperCase());
      },
    });
  }, [ecWindowId]);

  // Fetch the day list.
  const fetchDay = useCallback(
    async (date: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiUrl}/api/v1/earnings/calendar?date=${date}&timezone=${tzq}`);
        if (!res.ok) throw new Error(`Error ${res.status}`);
        setDayData(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error');
      } finally {
        setLoading(false);
      }
    },
    [apiUrl, tzq]
  );

  // Fetch the week strip.
  const fetchSchedule = useCallback(
    async (date: string) => {
      try {
        const start = startOfWeek(date);
        const end = new Date(start);
        end.setDate(end.getDate() + 6);
        const res = await fetch(
          `${apiUrl}/api/v1/earnings/schedule?start_date=${toYmd(start)}&end_date=${toYmd(end)}&timezone=${tzq}`
        );
        if (!res.ok) return;
        const d = await res.json();
        setSchedule(d?.days || []);
      } catch {
        /* week strip is best-effort */
      }
    },
    [apiUrl, tzq]
  );

  const fetchTicker = useCallback(
    async (ticker: string) => {
      if (!ticker) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiUrl}/api/v1/earnings/ticker/${ticker.toUpperCase()}?timezone=${tzq}&limit=40`);
        if (!res.ok) throw new Error(`Error ${res.status}`);
        const d = await res.json();
        setTickerData(d?.earnings || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error');
      } finally {
        setLoading(false);
      }
    },
    [apiUrl, tzq]
  );

  useEffect(() => {
    if (view === 'day') {
      fetchDay(selectedDate);
      fetchSchedule(selectedDate);
    }
  }, [view, selectedDate, fetchDay, fetchSchedule]);

  useEffect(() => {
    if (view === 'search' && searchTicker) fetchTicker(searchTicker);
  }, [view, searchTicker, fetchTicker]);

  const navDate = (days: number) => {
    const d = parseYmd(selectedDate);
    d.setDate(d.getDate() + days);
    setSelectedDate(toYmd(d));
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      setSearchTicker(searchInput.trim().toUpperCase());
      setView('search');
    }
  };

  const openModalFromEventRow = (e: EventRow) => {
    // Adapt an EventRow (ticker history) into a DayReport for the modal.
    setModalReport({
      symbol: e.symbol,
      company_name: searchTicker || e.symbol,
      event_id: e.event_id,
      report_date: e.report_date,
      report_time: e.report_time,
      utc_time: null,
      time_slot: (e.time_slot as DayReport['time_slot']) || 'TBD',
      fiscal_year: e.fiscal_year,
      fiscal_period: e.fiscal_period,
      fiscal_quarter: e.fiscal_period,
      eps_estimate: e.eps_estimate,
      eps_actual: e.eps_actual,
      eps_surprise_pct: e.eps_surprise_pct,
      beat_eps: e.beat_eps,
      revenue_estimate: e.revenue_estimate,
      revenue_actual: e.revenue_actual,
      revenue_surprise_pct: e.revenue_surprise_pct,
      beat_revenue: e.beat_revenue,
      summary: null,
      key_highlights: null,
      expected_move_pct: e.expected_move_pct,
      post_earnings_move_1d: e.post_earnings_move_1d,
      market_cap: null,
      currency: null,
      status: (e.status as DayReport['status']) || 'scheduled',
      importance: null,
      source: 'tradeul',
    });
  };

  const isToday = selectedDate === toYmd(new Date());
  const summaryChips = dayData
    ? [
        { label: 'Total', value: dayData.total_count, cls: 'text-foreground/70 bg-foreground/[0.06]' },
        { label: 'BMO', value: dayData.total_bmo, cls: 'text-amber-600 dark:text-amber-300 bg-amber-500/10' },
        { label: 'AMC', value: dayData.total_amc, cls: 'text-indigo-600 dark:text-indigo-300 bg-indigo-500/10' },
        { label: 'Reportados', value: dayData.total_reported, cls: 'text-emerald-600 dark:text-emerald-300 bg-emerald-500/10' },
      ]
    : [];

  return (
    <div
      className={cn('h-full flex flex-col text-foreground overflow-hidden relative', fontClass)}
      style={{ backgroundColor: 'var(--color-surface)' }}
    >
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 h-11 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.18))' }}>
        <span className="text-[13px] font-semibold tracking-tight">Calendario de ganancias</span>

        <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-foreground/[0.05] ml-1">
          {(['day', 'search'] as ViewMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                'px-2.5 h-7 rounded text-[11px] font-medium transition-all',
                view === v ? 'bg-foreground/[0.10] text-foreground' : 'text-foreground/55 hover:text-foreground/90'
              )}
            >
              {v === 'day' ? 'Calendario' : 'Buscar'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSearch} className="relative">
          <input
            ref={searchInputRef}
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
            placeholder="Ticker..."
            className="bg-foreground/[0.04] hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] text-foreground placeholder:text-foreground/40 rounded-md px-2 h-7 text-[11px] w-[110px] outline-none transition-colors border border-transparent focus:border-foreground/15"
          />
        </form>

        <div className="flex-1" />

        {view === 'day' && (
          <div className="flex items-center gap-1 p-0.5 rounded-md bg-foreground/[0.05]">
            <button onClick={() => navDate(-1)} className="w-6 h-6 rounded text-foreground/65 hover:text-foreground hover:bg-foreground/[0.08] text-[12px]" title="Día anterior">‹</button>
            <button onClick={() => setSelectedDate(toYmd(new Date()))} className={cn('px-2 h-6 rounded text-[11px] font-medium', isToday ? 'text-foreground bg-foreground/[0.08]' : 'text-foreground hover:bg-foreground/[0.08]')} title="Hoy">
              {isToday ? 'Hoy' : `${weekdayOf(selectedDate)} ${shortDate(selectedDate)}`}
            </button>
            <button onClick={() => navDate(1)} className="w-6 h-6 rounded text-foreground/65 hover:text-foreground hover:bg-foreground/[0.08] text-[12px]" title="Día siguiente">›</button>
          </div>
        )}
      </div>

      {view === 'day' && (
        <>
          {schedule.length > 0 && (
            <div className="border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
              <WeekStrip days={schedule} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          )}

          {/* Summary chips */}
          {dayData && dayData.total_count > 0 && (
            <div className="flex items-center gap-1.5 px-3 h-8 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.08))' }}>
              {summaryChips.map((c) => (
                <span key={c.label} className={cn('inline-flex items-center gap-1 px-2 h-6 rounded-md text-[10px] font-semibold uppercase tracking-wider', c.cls)}>
                  <span className="opacity-70">{c.label}</span>
                  <span className="tabular-nums">{c.value}</span>
                </span>
              ))}
            </div>
          )}

          <div className="flex-1 overflow-auto">
            {loading ? (
              <CenterMessage>Cargando…</CenterMessage>
            ) : error ? (
              <CenterMessage tone="error">{error}</CenterMessage>
            ) : !dayData || dayData.reports.length === 0 ? (
              <CenterMessage>Sin llamadas de resultados este día</CenterMessage>
            ) : (
              dayData.reports.map((r) => (
                <CompanyCard key={`${r.symbol}-${r.event_id}`} r={r} onClick={() => setModalReport(r)} />
              ))
            )}
          </div>
        </>
      )}

      {view === 'search' && (
        <div className="flex-1 overflow-auto">
          {loading ? (
            <CenterMessage>Cargando…</CenterMessage>
          ) : error ? (
            <CenterMessage tone="error">{error}</CenterMessage>
          ) : !searchTicker ? (
            <CenterMessage>Escribe un ticker y pulsa Enter</CenterMessage>
          ) : !tickerData || tickerData.length === 0 ? (
            <CenterMessage>Sin historial para {searchTicker}</CenterMessage>
          ) : (
            <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
              <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--color-surface)' }}>
                <tr style={{ borderBottom: '1px solid var(--color-border, rgba(127,127,127,0.18))' }}>
                  {['Periodo', 'Fecha', 'BPA est.', 'BPA real', 'Sorp.', 'Ingr. real', 'Mov. 1d'].map((h, i) => (
                    <th key={h} className={cn('px-2 py-2 text-[10px] uppercase tracking-wider text-foreground/55 font-medium', i === 0 ? 'text-left pl-3' : 'text-right')}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tickerData.map((e, idx) => (
                  <tr
                    key={e.event_id}
                    className={cn('cursor-pointer transition-colors hover:bg-foreground/[0.06]', idx % 2 === 1 ? 'bg-foreground/[0.025]' : '')}
                    onClick={() => openModalFromEventRow(e)}
                  >
                    <td className="pl-3 pr-2 py-1.5 text-[12px] font-medium">{e.fiscal_period} {e.fiscal_year}</td>
                    <td className="px-2 py-1.5 text-[12px] text-right text-foreground/65">{e.report_date}</td>
                    <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">{fmt.eps(e.eps_estimate)}</td>
                    <td className="px-2 py-1.5 text-[12px] text-right tabular-nums font-semibold" style={{ color: e.beat_eps === true ? up : e.beat_eps === false ? down : undefined }}>{fmt.eps(e.eps_actual)}</td>
                    <td className="px-2 py-1.5 text-[12px] text-right tabular-nums" style={{ color: (e.eps_surprise_pct ?? 0) >= 0 ? up : down }}>{fmt.pct(e.eps_surprise_pct)}</td>
                    <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">{fmt.rev(e.revenue_actual)}</td>
                    <td className="px-2 py-1.5 text-right"><MoveBadge value={e.post_earnings_move_1d} up={up} down={down} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <Footer count={view === 'day' ? dayData?.reports.length || 0 : tickerData?.length || 0} tz={tz} />

      {modalReport && (
        <EventDetailModal
          report={modalReport}
          apiUrl={apiUrl}
          tz={tz}
          up={up}
          down={down}
          onClose={() => setModalReport(null)}
        />
      )}
    </div>
  );
}

// ============================================================================
// SMALL HELPERS
// ============================================================================

function CenterMessage({ children, tone = 'muted' }: { children: React.ReactNode; tone?: 'muted' | 'error' }) {
  return (
    <div className={cn('flex items-center justify-center h-full text-[12px]', tone === 'error' ? 'text-rose-500 dark:text-rose-400' : 'text-foreground/45')}>
      {children}
    </div>
  );
}

function Footer({ count, tz }: { count: number; tz: string }) {
  return (
    <div className="flex items-center justify-between px-3 h-7 border-t text-[10px] text-foreground/55" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.12))' }}>
      <span className="tabular-nums">{count} · {tz}</span>
      <span className="opacity-70">tradeul.com</span>
    </div>
  );
}

export default EarningsCalendarContent;
