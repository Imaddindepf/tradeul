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
 *    and tabs for Momentos destacados / Transcript / Documents. The short
 *    preview summary renders on the calendar row, not inside the card.
 *
 * TIMEZONE: everything is rendered in the user's preferred timezone
 * (theme.timezone, default America/New_York). We pass `timezone` to every
 * endpoint so day bucketing matches, and the backend returns a pre-formatted
 * local `report_time` (HH:MM) plus the BMO/AMC/DURING slot (always ET-based).
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/lib/i18n';
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
  summary_bullets: string[] | null;
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
  // True while the call is still being transcribed. The payload then changes
  // every few seconds and `poll_after_seconds` says how long to wait before
  // asking again.
  is_live: boolean;
  poll_after_seconds: number | null;
  went_live_at: string | null;
  paragraph_count: number;
  last_paragraph_time: number | null;
  report_date: string | null;
  report_time: string | null;
  // Path on our own API, not an upstream URL — the audio is relayed. Needs the
  // API base prefixed, and an HLS player outside Safari.
  audio_url: string | null;
  audio_is_hls: boolean;
  speakers: string[];
  chapters: { id: number; title: string; start: number; end: number; level: number }[];
  paragraphs: { time: number; text: string; speakers: string[] }[];
}

/** An earnings call being transcribed right now (from /earnings/live). */
interface LiveCall {
  symbol: string;
  company_name: string | null;
  event_id: number;
  report_date: string | null;
  report_time: string | null;
  time_slot: string;
  fiscal_period: string | null;
  fiscal_year: number | null;
  market_cap: number | null;
  went_live_at: string | null;
  paragraph_count: number;
  last_paragraph_time: number | null;
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

function monthsShort(): string[] {
  const m = i18n.t('earnings.monthsShort', { returnObjects: true });
  return Array.isArray(m) && m.length === 12
    ? (m as string[])
    : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
}

function weekdaysShort(): string[] {
  const days = i18n.t('earnings.weekdaysShort', { returnObjects: true });
  return Array.isArray(days) ? (days as string[]) : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
}

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
  return `${d.getDate()} ${monthsShort()[d.getMonth()]}`;
};
const weekdayOf = (ymd: string): string => weekdaysShort()[parseYmd(ymd).getDay()];

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

/**
 * Franja de la fila. Solo se pinta cuando la empresa NO tiene hora
 * confirmada, ocupando el hueco de `report_time` — asi que se pinta con el
 * mismo peso que el, texto plano y apagado, y no como una pastilla de color
 * que aparece a saltos en una lista por lo demas neutra.
 */
function TimeSlotChip({ slot }: { slot: string }) {
  const map: Record<string, { label: string; title: string }> = {
    BMO: { label: 'BMO', title: i18n.t('earnings.bmoTitle') },
    AMC: { label: 'AMC', title: i18n.t('earnings.amcTitle') },
    DURING: { label: 'DUR', title: i18n.t('earnings.duringTitle') },
    TBD: { label: 'TBD', title: i18n.t('earnings.tbdTitle') },
  };
  const v = map[slot] ?? map.TBD;
  return (
    <span title={v.title} className="text-[11px] font-medium tracking-wider text-foreground/55">
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
              <span className="text-[10px] text-foreground/35 mt-0.5">{i18n.t('earnings.noCalls')}</span>
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

/**
 * Strip of calls on the air right now, above the day list. Without it a live
 * call is invisible unless the user happens to open that company's card — the
 * day feed itself carries no live flag.
 */
function LiveCallsStrip({ calls, onOpen }: { calls: LiveCall[]; onOpen: (c: LiveCall) => void }) {
  if (calls.length === 0) return null;
  return (
    <div
      className="flex items-center gap-2 px-4 py-2 border-b shrink-0 overflow-x-auto"
      style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}
    >
      <LiveBadge compact />
      <span className="text-[10px] uppercase tracking-wider text-foreground/45 shrink-0">
        {i18n.t('earnings.callsNow')}
      </span>
      <div className="flex items-center gap-1.5">
        {calls.map((c) => (
          <button
            key={c.event_id}
            onClick={() => onOpen(c)}
            title={`${c.company_name || c.symbol} — ${i18n.t('earnings.liveTranscriptOf')}`}
            className="shrink-0 inline-flex items-center gap-1.5 px-2 h-6 rounded border border-foreground/20 bg-foreground/[0.04] hover:bg-foreground/[0.09] transition-colors"
          >
            <TickerLogo symbol={c.symbol} size={14} />
            <span className="text-[11px] font-semibold">{c.symbol}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function CompanyCard({ r, onClick, isLive = false }: { r: DayReport; onClick: () => void; isLive?: boolean }) {
  const summaryBullets = r.summary_bullets || [];
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
                {isLive && <LiveBadge compact />}
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

          {summaryBullets.length > 0 && (
            <ul className="mt-1.5 space-y-1">
              {summaryBullets.slice(0, 3).map((h, i) => (
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

/**
 * Audio player for the relayed HLS stream.
 *
 * Safari plays HLS natively; every other browser needs a player, so hls.js is
 * loaded on demand — a plain <audio src="...m3u8"> is simply silent in Chrome,
 * which is how this went unnoticed.
 */
function CallAudio({ src, isHls }: { src: string; isHls: boolean }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    setFailed(false);

    const nativeHls = el.canPlayType('application/vnd.apple.mpegurl') !== '';
    if (!isHls || nativeHls) {
      el.src = src;
      return;
    }

    let destroy: (() => void) | undefined;
    let cancelled = false;
    import('hls.js')
      .then(({ default: Hls }) => {
        if (cancelled) return;
        if (!Hls.isSupported()) {
          setFailed(true);
          return;
        }
        const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
        hls.loadSource(src);
        hls.attachMedia(el);
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data.fatal) setFailed(true);
        });
        destroy = () => hls.destroy();
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      destroy?.();
    };
  }, [src, isHls]);

  return (
    <div>
      <audio ref={audioRef} controls className="w-full h-8" />
      {failed && (
        <div className="mt-1 text-[11px] text-foreground/40">
          {i18n.t('earnings.audioFailed')}
        </div>
      )}
    </div>
  );
}

/** "EN DIRECTO" pill for a call that is being transcribed right now. */
function LiveBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className={cn(
        'shrink-0 inline-flex items-center gap-1.5 rounded-full border border-foreground/20 bg-foreground/[0.06]',
        compact ? 'px-1.5 h-[18px]' : 'px-2 h-[22px]'
      )}
    >
      <span className="relative flex w-1.5 h-1.5">
        <span className="absolute inline-flex w-full h-full rounded-full bg-foreground/60 animate-ping" />
        <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-foreground/80" />
      </span>
      <span className={cn('font-semibold uppercase tracking-wider', compact ? 'text-[9px]' : 'text-[10px]')}>
        En directo
      </span>
    </span>
  );
}

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
  const { t } = useTranslation();
  const [tab, setTab] = useState<DetailTab>('highlights');
  const [history, setHistory] = useState<EventRow[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(report.event_id);
  // Key highlights of the call. The short preview summary is NOT shown here:
  // it already renders on the calendar row, outside the card.
  const [eventKeyHighlights, setEventKeyHighlights] = useState<string[]>([]);
  const [highlightsLoading, setHighlightsLoading] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  // Known from the event-detail fetch, so the live badge shows on any tab
  // without having to load the transcript first.
  const [transcriptIsLive, setTranscriptIsLive] = useState(false);
  // The source keeps `status: "live"` for a while after the call has actually
  // ended, until post-processing flips it to "final" — observed sitting there
  // for over 15 minutes with the text frozen on the closing remarks. Without
  // this we would poll a dead call forever.
  const [transcriptStalled, setTranscriptStalled] = useState(false);
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
  // clicked day report for fields missing from history.
  const merged = useMemo(() => {
    const e = selectedEvent;
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
      keyHighlights: eventKeyHighlights,
    };
  }, [selectedEvent, report, eventKeyHighlights]);

  // Fetch the call's key highlights whenever the selected quarter changes.
  useEffect(() => {
    if (selectedEventId == null) return;
    setHighlightsLoading(true);
    const c = new AbortController();
    fetch(`${apiUrl}/api/v1/earnings/event/${report.symbol}/${selectedEventId}?timezone=${tzq}`, { signal: c.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        setEventKeyHighlights(Array.isArray(d?.key_highlights) ? d.key_highlights : []);
        setTranscriptIsLive(d?.transcript_is_live === true);
      })
      .catch(() => {
        setEventKeyHighlights([]);
        setTranscriptIsLive(false);
      })
      .finally(() => setHighlightsLoading(false));
    return () => c.abort();
  }, [selectedEventId, apiUrl, report.symbol, tzq]);

  // A call happening right now is what the user opened the card for, so land on
  // the transcript instead of the highlights (which are empty until the call is
  // processed anyway). Once only — never fight a user who navigated away.
  const autoOpenedLiveRef = useRef(false);
  useEffect(() => {
    if (transcriptIsLive && !autoOpenedLiveRef.current) {
      autoOpenedLiveRef.current = true;
      setTab('transcript');
    }
  }, [transcriptIsLive]);

  // Still being transcribed *and* still moving. A stalled call is over, so it
  // must stop presenting itself as live.
  const isLive = (transcript?.is_live ?? transcriptIsLive) && !transcriptStalled;

  // Follow the live text, but only while the reader is already at the bottom:
  // scrolling up to re-read something must not be yanked back down. Keyed on
  // paragraph count *and* the length of the last one, since a live update often
  // just extends the trailing paragraph.
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const liveTick = transcript
    ? `${transcript.paragraphs.length}:${transcript.paragraphs[transcript.paragraphs.length - 1]?.text.length ?? 0}`
    : '';
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || tab !== 'transcript' || !isLive) return;
    if (stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [liveTick, tab, isLive]);

  // Transcript: load when the tab is opened, then keep following it for as long
  // as the call is live. Each poll replaces the whole payload instead of
  // appending a delta, because the source rewrites its last paragraph in place
  // as the speaker finishes the sentence — appending by index would duplicate
  // half-sentences. The cadence comes from the server (`poll_after_seconds`),
  // and polling stops by itself the moment `is_live` turns false.
  useEffect(() => {
    if (tab !== 'transcript' || selectedEventId == null) return;
    setTranscript(null);
    setTranscriptStalled(false);
    setTranscriptLoading(true);
    const c = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    // Give up following when the text has not moved for this long: the call is
    // over and we are only waiting for the source to relabel it. Comfortably
    // longer than any pause between a question and its answer.
    const STALL_MS = 4 * 60 * 1000;
    let signature = '';
    let lastAdvance = Date.now();

    const poll = async () => {
      try {
        const r = await fetch(
          `${apiUrl}/api/v1/earnings/event/${report.symbol}/${selectedEventId}/transcript?timezone=${tzq}`,
          { signal: c.signal, cache: 'no-store' }
        );
        const d: TranscriptResponse | null = r.ok ? await r.json() : null;
        if (stopped) return;
        if (d) {
          setTranscript(d);
          // Count both a new paragraph and the trailing one growing as progress.
          const sig = `${d.paragraph_count}:${d.paragraphs[d.paragraphs.length - 1]?.text.length ?? 0}`;
          if (sig !== signature) {
            signature = sig;
            lastAdvance = Date.now();
          }
          if (d.is_live) {
            if (Date.now() - lastAdvance > STALL_MS) {
              setTranscriptStalled(true);
            } else {
              timer = setTimeout(poll, (d.poll_after_seconds ?? 8) * 1000);
            }
          }
        }
      } catch {
        // Aborted (tab/quarter changed) or offline: stop following.
      } finally {
        if (!stopped) setTranscriptLoading(false);
      }
    };
    poll();

    return () => {
      stopped = true;
      c.abort();
      if (timer) clearTimeout(timer);
    };
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
    // pointer-events-none on the shell lets clicks reach the floating-window
    // resize handle (z-[100] on FloatingWindowBase). Only the card captures input.
    <div className="absolute inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
      <button
        type="button"
        aria-label={i18n.t('earnings.closeDetail')}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm pointer-events-auto cursor-default"
        onClick={onClose}
      />
      <div
        className="relative w-full max-w-3xl max-h-full flex flex-col rounded-xl shadow-2xl overflow-hidden pointer-events-auto"
        style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border, rgba(127,127,127,0.2))' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.15))' }}>
          <TickerLogo symbol={report.symbol} size={36} />
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold truncate">{report.company_name || report.symbol}</div>
            <div className="text-[11px] text-foreground/50">{report.symbol}</div>
          </div>
          {isLive && <LiveBadge />}
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 rounded-md text-foreground/60 hover:text-foreground hover:bg-foreground/10 transition-colors text-[16px] leading-none"
            aria-label={i18n.t('earnings.close')}
          >
            ×
          </button>
        </div>

        {/* Quarter strip */}
        {history.length > 0 && (
          <div className="flex gap-1.5 overflow-x-auto px-4 py-2 border-b shrink-0" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
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
                    <span className="text-[10px] text-foreground/45">{i18n.t('earnings.upcoming')}</span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Selected event summary */}
        <div className="px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
          <div className="text-[13px] font-semibold">
            {i18n.language === 'es'
              ? `${i18n.t('earnings.callOf')} ${report.symbol} ${merged.fiscal_year ?? ''} ${merged.fiscal_period ?? ''}`.trim()
              : `${report.symbol} ${merged.fiscal_year ?? ''} ${merged.fiscal_period ?? ''} ${i18n.t('earnings.callOf')}`.replace(/\s+/g, ' ').trim()}
          </div>
          <div className="text-[11px] text-foreground/50">
            {merged.report_date}{merged.report_time ? ` · ${merged.report_time}` : ''}
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2.5 mt-3">
            <StatBox label={i18n.t('earnings.revEstimate')} value={fmt.rev(merged.revenue_estimate)} />
            <StatBox label={i18n.t('earnings.revActual')} value={fmt.rev(merged.revenue_actual)} tone={surpTone(merged.beat_revenue)} />
            <StatBox label={i18n.t('earnings.revSurprise')} value={fmt.pct(merged.revenue_surprise_pct)} tone={surpTone(merged.beat_revenue)} />
            <StatBox label={i18n.t('earnings.expectedMove')} value={fmt.moveFrac(merged.expected_move_pct)} />
            <StatBox label={i18n.t('earnings.epsEstimate')} value={fmt.eps(merged.eps_estimate)} />
            <StatBox label={i18n.t('earnings.epsActual')} value={fmt.eps(merged.eps_actual)} tone={surpTone(merged.beat_eps)} />
            <StatBox label={i18n.t('earnings.epsSurprise')} value={fmt.pct(merged.eps_surprise_pct)} tone={surpTone(merged.beat_eps)} />
            <StatBox
              label={i18n.t('earnings.move1d')}
              value={<MoveBadge value={merged.post_earnings_move_1d} up={up} down={down} />}
            />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 px-4 py-1.5 border-b shrink-0" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.10))' }}>
          {([
            ['highlights', 'Momentos destacados'],
            ['transcript', t('earnings.transcript')],
            ['documents', 'Documentos'],
          ] as [DetailTab, string][]).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                'inline-flex items-center gap-1.5 px-2.5 h-7 rounded text-[11px] font-medium transition-colors',
                tab === id ? 'bg-foreground/[0.10] text-foreground' : 'text-foreground/55 hover:text-foreground/90 hover:bg-foreground/[0.05]'
              )}
            >
              {label}
              {id === 'transcript' && isLive && <LiveBadge compact />}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
          }}
          className="flex-1 min-h-0 overflow-auto px-4 py-3 min-h-[160px]"
        >
          {tab === 'highlights' && (
            highlightsLoading ? (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">{i18n.t('earnings.loadingHighlights')}</div>
            ) : merged.keyHighlights.length > 0 ? (
              <ul className="space-y-2.5">
                {merged.keyHighlights.map((h, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-foreground/85">
                    <span className="text-foreground/30 select-none mt-0.5">•</span>
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">
                Sin momentos destacados para esta llamada.
              </div>
            )
          )}

          {tab === 'transcript' && (
            transcriptLoading && !transcript ? (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">{i18n.t('earnings.loadingTranscript')}</div>
            ) : transcript && transcript.paragraphs.length > 0 ? (
              <div className="space-y-3">
                {transcript.audio_url && (
                  <CallAudio src={`${apiUrl}${transcript.audio_url}`} isHls={transcript.audio_is_hls} />
                )}
                {transcript.paragraphs.map((p, i) => {
                  // While live, the final paragraph is a partial that will be
                  // rewritten on the next poll: dim it so the reader can tell
                  // the sentence is still being spoken.
                  const provisional = isLive && i === transcript.paragraphs.length - 1;
                  return (
                    <div key={i} className="text-[13px] leading-relaxed">
                      {p.speakers.length > 0 && (
                        <span className="font-semibold text-foreground/90 mr-1.5">{p.speakers.join(', ')}:</span>
                      )}
                      <span className={provisional ? 'text-foreground/55' : 'text-foreground/75'}>{p.text}</span>
                      {provisional && <span className="ml-0.5 animate-pulse text-foreground/40">▍</span>}
                    </div>
                  );
                })}
                {isLive && (
                  <div className="pt-1 pb-2 text-[11px] text-foreground/40 text-center">
                    Transcribiendo la llamada en directo…
                  </div>
                )}
                {transcriptStalled && (
                  <div className="pt-1 pb-2 text-[11px] text-foreground/40 text-center">
                    {i18n.t('earnings.transcriptStalled')}
                  </div>
                )}
              </div>
            ) : isLive ? (
              // Live but nothing transcribed yet: the call has been announced or
              // has just started. Not the same as "no transcript exists".
              <div className="text-[12px] text-foreground/45 pt-6 text-center">
                {i18n.t('earnings.transcriptStarting')}
              </div>
            ) : (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">{t('earnings.transcriptUnavailable')}</div>
            )
          )}

          {tab === 'documents' && (
            docsLoading ? (
              <div className="text-[12px] text-foreground/45 pt-6 text-center">{i18n.t('earnings.loadingFilings')}</div>
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
              <div className="text-[12px] text-foreground/45 pt-6 text-center">{i18n.t('earnings.noFilings')}</div>
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
  const { t } = useTranslation();
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

  type SlotFilter = 'ALL' | 'BMO' | 'DURING' | 'AMC' | 'REPORTED';
  const [slotFilter, setSlotFilter] = useState<SlotFilter>('ALL');
  const [modalReport, setModalReport] = useState<DayReport | null>(null);
  const [liveCalls, setLiveCalls] = useState<LiveCall[]>([]);
  const liveEventIds = useMemo(() => new Set(liveCalls.map((l) => l.event_id)), [liveCalls]);

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

  // Which calls are on the air right now. Independent of the selected day: a
  // live call is news wherever the user happens to be browsing. The server
  // caches the scan, so this poll is cheap regardless of how many windows ask.
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const c = new AbortController();

    const tick = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/earnings/live?timezone=${tzq}`, {
          signal: c.signal,
          cache: 'no-store',
        });
        const d = res.ok ? await res.json() : null;
        if (stopped) return;
        setLiveCalls(Array.isArray(d?.live) ? d.live : []);
      } catch {
        /* best-effort: the calendar works without the live strip */
      } finally {
        if (!stopped) timer = setTimeout(tick, 30_000);
      }
    };
    tick();

    return () => {
      stopped = true;
      c.abort();
      if (timer) clearTimeout(timer);
    };
  }, [apiUrl, tzq]);

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
      summary_bullets: null,
      expected_move_pct: e.expected_move_pct,
      post_earnings_move_1d: e.post_earnings_move_1d,
      market_cap: null,
      currency: null,
      status: (e.status as DayReport['status']) || 'scheduled',
      importance: null,
      source: 'tradeul',
    });
  };

  // Open the detail card straight from the live strip. The card fills in
  // estimates and actuals itself from the per-symbol history, so the adapter
  // only has to carry identity and timing.
  const openModalFromLiveCall = (c: LiveCall) => {
    setModalReport({
      symbol: c.symbol,
      company_name: c.company_name,
      event_id: c.event_id,
      report_date: c.report_date,
      report_time: c.report_time,
      utc_time: null,
      time_slot: (c.time_slot as DayReport['time_slot']) || 'TBD',
      fiscal_year: c.fiscal_year,
      fiscal_period: c.fiscal_period,
      fiscal_quarter: c.fiscal_period,
      eps_estimate: null,
      eps_actual: null,
      eps_surprise_pct: null,
      beat_eps: null,
      revenue_estimate: null,
      revenue_actual: null,
      revenue_surprise_pct: null,
      beat_revenue: null,
      summary: null,
      summary_bullets: null,
      expected_move_pct: null,
      post_earnings_move_1d: null,
      market_cap: c.market_cap,
      currency: null,
      status: 'reported',
      importance: null,
      source: 'tradeul',
    });
  };

  const isToday = selectedDate === toYmd(new Date());

  // Filtro por franja. Pulsar la pastilla activa la quita, asi que la propia
  // fila de contadores es el control: no hace falta un "ver todo" aparte.
  const visibleReports = useMemo(() => {
    const all = dayData?.reports ?? [];
    if (slotFilter === 'ALL') return all;
    if (slotFilter === 'REPORTED') return all.filter((r) => r.status === 'reported');
    return all.filter((r) => r.time_slot === slotFilter);
  }, [dayData, slotFilter]);
  // Contadores del dia. Sin color: en esta ventana el unico color lo ponen
  // los logos, asi que estas pastillas heredan el lenguaje de las de
  // "Llamadas ahora" (LiveCallsStrip) — borde tenue, fondo casi plano,
  // etiqueta en versalitas y valor tabular.
  const summaryChips = dayData
    ? ([
        { key: 'ALL', label: t('earnings.total'), value: dayData.total_count, title: t('earnings.totalTitle') },
        { key: 'BMO', label: 'BMO', value: dayData.total_bmo, title: t('earnings.bmoTitle') },
        { key: 'DURING', label: 'DUR', value: dayData.total_during, title: t('earnings.duringTitle') },
        { key: 'AMC', label: 'AMC', value: dayData.total_amc, title: t('earnings.amcTitle') },
        { key: 'REPORTED', label: t('earnings.reported'), value: dayData.total_reported, title: t('earnings.reportedTitle') },
      ] as const)
    : [];

  return (
    <div
      className={cn('h-full flex flex-col text-foreground overflow-hidden relative', fontClass)}
      style={{ backgroundColor: 'var(--color-surface)' }}
    >
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 h-11 border-b" style={{ borderColor: 'var(--color-border, rgba(127,127,127,0.18))' }}>
        <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-foreground/[0.05]">
          {(['day', 'search'] as ViewMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                'px-2.5 h-7 rounded text-[11px] font-medium transition-all',
                view === v ? 'bg-foreground/[0.10] text-foreground' : 'text-foreground/55 hover:text-foreground/90'
              )}
            >
              {v === 'day' ? t('earnings.tabCalendar') : t('earnings.tabSearch')}
            </button>
          ))}
        </div>

        <form onSubmit={handleSearch} className="relative">
          <input
            ref={searchInputRef}
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
            placeholder={t('earnings.tickerPlaceholder')}
            className="bg-foreground/[0.04] hover:bg-foreground/[0.06] focus:bg-foreground/[0.08] text-foreground placeholder:text-foreground/40 rounded-md px-2 h-7 text-[11px] w-[110px] outline-none transition-colors border border-transparent focus:border-foreground/15"
          />
        </form>

        <div className="flex-1" />

        {view === 'day' && (
          <div className="flex items-center gap-1 p-0.5 rounded-md bg-foreground/[0.05]">
            <button onClick={() => navDate(-1)} className="w-6 h-6 rounded text-foreground/65 hover:text-foreground hover:bg-foreground/[0.08] text-[12px]" title={t('earnings.prevDay')}>‹</button>
            <button onClick={() => setSelectedDate(toYmd(new Date()))} className={cn('px-2 h-6 rounded text-[11px] font-medium', isToday ? 'text-foreground bg-foreground/[0.08]' : 'text-foreground hover:bg-foreground/[0.08]')} title={t('earnings.today')}>
              {isToday ? t('earnings.today') : `${weekdayOf(selectedDate)} ${shortDate(selectedDate)}`}
            </button>
            <button onClick={() => navDate(1)} className="w-6 h-6 rounded text-foreground/65 hover:text-foreground hover:bg-foreground/[0.08] text-[12px]" title={t('earnings.nextDay')}>›</button>
          </div>
        )}
      </div>

      <LiveCallsStrip calls={liveCalls} onOpen={openModalFromLiveCall} />

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
              {summaryChips.map((c) => {
                // Un cero no merece el mismo peso que un dato: se apaga en vez
                // de gritar igual que los que si tienen contenido. Y un chip
                // vacio no filtra: dejaria la lista en blanco a proposito.
                const empty = !c.value;
                const active = slotFilter === c.key;
                const canFilter = !empty || c.key === 'ALL';
                return (
                  <button
                    key={c.key}
                    type="button"
                    disabled={!canFilter}
                    onClick={() => setSlotFilter((prev) => (prev === c.key ? 'ALL' : c.key))}
                    title={active && c.key !== 'ALL' ? t('earnings.filterOff') : c.title}
                    aria-pressed={active}
                    className={cn(
                      'inline-flex items-center gap-1.5 px-2 h-6 rounded border transition-colors',
                      active
                        ? 'border-foreground/45 bg-foreground/[0.10]'
                        : empty
                          ? 'border-foreground/10'
                          : 'border-foreground/20 bg-foreground/[0.04]',
                      canFilter && !active && 'hover:bg-foreground/[0.08] hover:border-foreground/30',
                      !canFilter && 'cursor-default'
                    )}
                  >
                    <span
                      className={cn(
                        'text-[10px] uppercase tracking-wider',
                        active ? 'text-foreground/70' : empty ? 'text-foreground/25' : 'text-foreground/45'
                      )}
                    >
                      {c.label}
                    </span>
                    <span
                      className={cn(
                        'text-[11px] font-semibold tabular-nums',
                        active ? 'text-foreground' : empty ? 'text-foreground/25' : 'text-foreground'
                      )}
                    >
                      {c.value}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex-1 overflow-auto">
            {loading ? (
              <CenterMessage>{t('earnings.loading')}</CenterMessage>
            ) : error ? (
              <CenterMessage tone="error">{error}</CenterMessage>
            ) : !dayData || dayData.reports.length === 0 ? (
              <CenterMessage>{t('earnings.noCallsDay')}</CenterMessage>
            ) : visibleReports.length === 0 ? (
              <CenterMessage>{t('earnings.noCallsFiltered')}</CenterMessage>
            ) : (
              visibleReports.map((r) => (
                <CompanyCard
                  key={`${r.symbol}-${r.event_id}`}
                  r={r}
                  isLive={r.event_id != null && liveEventIds.has(r.event_id)}
                  onClick={() => setModalReport(r)}
                />
              ))
            )}
          </div>
        </>
      )}

      {view === 'search' && (
        <div className="flex-1 overflow-auto">
          {loading ? (
            <CenterMessage>{t('earnings.loading')}</CenterMessage>
          ) : error ? (
            <CenterMessage tone="error">{error}</CenterMessage>
          ) : !searchTicker ? (
            <CenterMessage>{t('earnings.typeTicker')}</CenterMessage>
          ) : !tickerData || tickerData.length === 0 ? (
            <CenterMessage>{t('earnings.noHistoryFor')} {searchTicker}</CenterMessage>
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
