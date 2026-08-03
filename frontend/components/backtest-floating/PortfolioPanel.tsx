'use client';

/**
 * Backtester (Fase 2): entradas = disparos reales del motor vivo; este panel
 * configura salidas, capital y costes, y pinta UN informe con las dos
 * mitades — operaciones y calidad de la señal — de la misma pasada.
 *
 * i18n vía react-i18next (namespace `backtester` en locales/{en,es}.json);
 * los avisos del motor se traducen por código con fallback a su detalle.
 * Tema por tokens (--color-surface, foreground, currentColor): dark y light.
 */

import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  ActionButton, CenterMessage, Field, RULE, SectionHead, Seg, TextButton,
} from './ui';
import { useCatalog, eventLabel, type CatalogEntry, type EntryKind } from './catalog';
import { CatalogPicker } from './CatalogPicker';
import { TriggerFilterRows } from './TriggersPanel';
import { NumericField } from '@/components/ui/FilterNumInput';

/* ── Contrato de /api/backtest/simulate ─────────────────────────────────── */

interface SimMetrics {
  trades: number;
  win_rate: number | null;
  profit_factor: number | null;
  total_pnl: number;
  total_return_pct: number;
  avg_win: number | null;
  avg_loss: number | null;
  expectancy: number | null;
  max_drawdown_pct: number;
  max_consecutive_losses: number;
  by_exit_reason: Record<string, number>;
}

interface FwdStat {
  n: number; mean_pct?: number; median_pct?: number; win_rate?: number;
  p10_pct?: number; p90_pct?: number;
}

interface SignalBlock {
  triggers_total: number;
  by_type: Record<string, number>;
  by_hour_et: Record<string, number>;
  top_symbols: Record<string, number>;
  forward_returns: Record<string, FwdStat | number | boolean> & {
    population_n?: number; sampled?: boolean;
  };
}

interface SimResult {
  signal?: SignalBlock;
  triggers_total: number;
  entries_simulated: number;
  entries_skipped: Record<string, number>;
  metrics: SimMetrics;
  daily_pnl: Record<string, number>;
  equity_curve: [number, number][];
  trades_sample: {
    symbol: string; dt: string; event_type: string; entry_ts: string;
    entry_px: number; exit_px: number; shares: number; reason: string;
    pnl: number; ret_pct: number;
  }[];
  assumptions: string[];
  warnings: { code: string; detail: string; days?: string[] }[];
  execution: Record<string, unknown>;
}

const HORIZONS = ['5min', '15min', '60min', 'close'] as const;

const num0 = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 });
const pct = (v: number | undefined) =>
  v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
const pctColor = (v: number | undefined) =>
  v === undefined ? '' : v > 0 ? 'text-emerald-600' : v < 0 ? 'text-rose-500 dark:text-rose-400' : '';

/* ══════════════════════════════════════════════════════════════════════ */

export function PortfolioPanel({
  events, setEvents, filters, setFilters,
}: {
  events: string[];
  setEvents: Dispatch<SetStateAction<string[]>>;
  filters: Record<string, number | null>;
  setFilters: Dispatch<SetStateAction<Record<string, number | null>>>;
}) {
  const { t } = useTranslation();
  const { triggerEntries, dataAxis } = useCatalog();

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [picker, setPicker] = useState<null | { kinds: readonly EntryKind[]; target: 'events' | 'filters' }>(null);

  const [direction, setDirection] = useState<'long' | 'short'>('long');
  const [stopPct, setStopPct] = useState<number | null>(5);
  const [targetPct, setTargetPct] = useState<number | null>(10);
  const [maxHoldMin, setMaxHoldMin] = useState<number | null>(null);
  const [capital, setCapital] = useState<number | null>(100_000);
  const [sizePct, setSizePct] = useState<number | null>(10);
  const [maxPositions, setMaxPositions] = useState<number | null>(10);
  const [slippageBps, setSlippageBps] = useState<number | null>(10);
  const [commission, setCommission] = useState<number | null>(0);

  const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<SimResult | null>(null);
  const [error, setError] = useState('');

  const lake = dataAxis?.events_lake?.range ?? null;
  useEffect(() => {
    if (lake && !dateFrom && !dateTo) {
      setDateFrom(lake.from);
      setDateTo(lake.to);
    }
  }, [lake, dateFrom, dateTo]);

  const selectedUids = useMemo(() => {
    const s = new Set<string>();
    for (const e of events) s.add(`event:${e}`);
    for (const k of Object.keys(filters)) {
      if (k.startsWith('aq:')) continue;
      s.add(`filter:${k.replace(/^(min|max)_/, '')}`);
    }
    return s;
  }, [events, filters]);

  const filterKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const k of Object.keys(filters)) {
      // aq: viaja en la estrategia pero no es una fila min/max editable
      if (k.startsWith('aq:')) continue;
      keys.add(k.replace(/^(min|max)_/, ''));
    }
    return [...keys];
  }, [filters]);

  const problem = !events.length
    ? t('backtester.needEvent')
    : (!dateFrom || !dateTo || dateFrom > dateTo)
      ? t('backtester.badDates')
      : (!stopPct || stopPct <= 0)
        ? t('backtester.needStop')
        : null;

  const run = useCallback(async () => {
    if (problem) return;
    setStatus('running');
    setError('');
    try {
      const clean = Object.fromEntries(
        Object.entries(filters).filter(([, v]) => v !== null && v !== undefined),
      );
      const res = await fetch('/api/backtest/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: { event_types: events, ...clean },
          date_from: dateFrom,
          date_to: dateTo,
          execution: {
            direction,
            stop_pct: stopPct,
            target_pct: targetPct ?? undefined,
            max_hold_min: maxHoldMin ?? undefined,
            initial_capital: capital ?? 100_000,
            position_size_pct: sizePct ?? 10,
            max_positions: maxPositions ?? 10,
            slippage_bps: slippageBps ?? 10,
            commission_per_trade: commission ?? 0,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const d = data?.detail ?? data;
        setError(typeof d === 'string' ? d : JSON.stringify(d));
        setStatus('error');
        return;
      }
      setResult(data as SimResult);
      setStatus('done');
    } catch (e: any) {
      setError(e?.message || 'network');
      setStatus('error');
    }
  }, [problem, filters, events, dateFrom, dateTo, direction, stopPct, targetPct,
      maxHoldMin, capital, sizePct, maxPositions, slippageBps, commission]);

  const onPick = useCallback((entry: CatalogEntry) => {
    if (picker?.target === 'events' && entry.kind === 'event') {
      setEvents(prev => (prev.includes(entry.id) ? prev : [...prev, entry.id]));
    } else if (picker?.target === 'filters' && entry.kind === 'filter') {
      setFilters(prev => ({ ...prev, [`min_${entry.id}`]: prev[`min_${entry.id}`] ?? null }));
    }
    setPicker(null);
  }, [picker]);

  return (
    <div className="flex-1 min-h-0 flex flex-col relative">
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 flex flex-col gap-5">

        {/* ── Estrategia ─────────────────────────────────────────────── */}
        <section className="flex flex-col gap-2">
          <SectionHead
            title={t('backtester.events')}
            action={<TextButton onClick={() => setPicker({ kinds: ['event'], target: 'events' })}>{t('backtester.add')}</TextButton>}
          />
          {events.length === 0
            ? <p className="m-0 text-[11px] text-foreground/45">{t('backtester.eventsEmpty')}</p>
            : (
              <div className="flex flex-wrap gap-1.5">
                {events.map(e => (
                  <span key={e} className="inline-flex items-center gap-1.5 h-6 px-2 rounded text-[11px] bg-foreground/[0.06] border" style={{ borderColor: RULE }}>
                    {eventLabel(e)}
                    <button
                      type="button"
                      aria-label={`${t('backtester.remove')} ${eventLabel(e)}`}
                      onClick={() => setEvents(prev => prev.filter(x => x !== e))}
                      className="text-foreground/30 hover:text-foreground leading-none"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
        </section>

        <section className="flex flex-col gap-2">
          <SectionHead
            title={t('backtester.filters')}
            action={<TextButton onClick={() => setPicker({ kinds: ['filter'], target: 'filters' })}>{t('backtester.add')}</TextButton>}
          />
          <TriggerFilterRows filters={filters} keys={filterKeys} catalog={triggerEntries} onChange={setFilters} />
        </section>

        {/* ── Salidas ────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-2.5">
          <SectionHead title={t('backtester.exits')} />
          <div className="flex flex-wrap items-start gap-3">
            <Field label={t('backtester.direction')} className="w-[120px]">
              {() => (
                <Seg
                  value={direction}
                  onChange={setDirection}
                  ariaLabel={t('backtester.direction')}
                  options={[
                    { value: 'long', label: t('backtester.long') },
                    { value: 'short', label: t('backtester.short') },
                  ]}
                />
              )}
            </Field>
            <Field label={t('backtester.stopPct')} className="w-[76px]">
              {(p) => <NumericField id={p.id} value={stopPct} onChange={setStopPct} spec={{ suffix: '%', min: 0.1 }} />}
            </Field>
            <Field label={t('backtester.targetPct')} className="w-[86px]" hint={t('backtester.hintNoTarget')}>
              {(p) => <NumericField id={p.id} value={targetPct} onChange={setTargetPct} spec={{ suffix: '%', min: 0.1 }} />}
            </Field>
            <Field label={t('backtester.maxHold')} className="w-[96px]" hint={t('backtester.hintHold')}>
              {(p) => <NumericField id={p.id} value={maxHoldMin} onChange={setMaxHoldMin} spec={{ suffix: 'min', min: 1 }} />}
            </Field>
          </div>
          <p className="m-0 text-[11px] text-foreground/45">{t('backtester.eodNote')}</p>
        </section>

        {/* ── Capital y costes ───────────────────────────────────────── */}
        <section className="flex flex-col gap-2.5">
          <SectionHead title={t('backtester.capitalCosts')} />
          <div className="flex flex-wrap items-start gap-3">
            <Field label={t('backtester.capital')} className="w-[96px]">
              {(p) => <NumericField id={p.id} value={capital} onChange={setCapital} spec={{ suffix: '$', compact: true, min: 100 }} />}
            </Field>
            <Field label={t('backtester.positionPct')} className="w-[80px]">
              {(p) => <NumericField id={p.id} value={sizePct} onChange={setSizePct} spec={{ suffix: '%', min: 0.1, max: 100 }} />}
            </Field>
            <Field label={t('backtester.maxPositions')} className="w-[96px]">
              {(p) => <NumericField id={p.id} value={maxPositions} onChange={setMaxPositions} spec={{ min: 1, max: 100 }} />}
            </Field>
            <Field label={t('backtester.slippage')} className="w-[86px]">
              {(p) => <NumericField id={p.id} value={slippageBps} onChange={setSlippageBps} spec={{ suffix: 'bps', min: 0 }} />}
            </Field>
            <Field label={t('backtester.commission')} className="w-[100px]">
              {(p) => <NumericField id={p.id} value={commission} onChange={setCommission} spec={{ suffix: '$', min: 0 }} />}
            </Field>
          </div>
        </section>

        {/* ── Rango ──────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-2">
          <SectionHead title={t('backtester.range')} />
          <div className="flex flex-wrap items-start gap-3">
            <Field label={t('backtester.from')} className="w-[132px]">
              {(p) => (
                <input
                  id={p.id} type="date" value={dateFrom} min={lake?.from} max={lake?.to}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="h-7 px-1.5 rounded bg-transparent text-[12px] font-mono border border-transparent focus:border-foreground/25 outline-none"
                />
              )}
            </Field>
            <Field label={t('backtester.to')} className="w-[132px]">
              {(p) => (
                <input
                  id={p.id} type="date" value={dateTo} min={lake?.from} max={lake?.to}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="h-7 px-1.5 rounded bg-transparent text-[12px] font-mono border border-transparent focus:border-foreground/25 outline-none"
                />
              )}
            </Field>
            <span className="text-[11px] text-foreground/45 self-end pb-1.5">
              {lake
                ? t('backtester.coverage', { from: lake.from, to: lake.to, days: lake.days })
                : t('backtester.coverageLoading')}
            </span>
          </div>
        </section>

        {status === 'error' && (
          <CenterMessage tone="error">
            <span className="block text-[12px] font-medium mb-1">{t('backtester.engineRejected')}</span>
            <span className="font-mono text-[11px] break-all">{error}</span>
          </CenterMessage>
        )}
        {status === 'done' && result && <SimResults r={result} />}
      </div>

      {/* ── Pie ────────────────────────────────────────────────────────── */}
      <div className="shrink-0 flex items-center gap-3 px-4 h-11 border-t" style={{ borderColor: RULE }}>
        <span className="flex-1" />
        {problem && <span className="text-[11px] text-foreground/55">{problem}</span>}
        <ActionButton onClick={run} disabled={status === 'running'}>
          {status === 'running' ? t('backtester.running') : t('backtester.run')}
        </ActionButton>
      </div>

      {picker && (
        <CatalogPicker
          entries={triggerEntries}
          kinds={picker.kinds}
          selected={selectedUids}
          onPick={onPick}
          onClose={() => setPicker(null)}
          title={picker.target === 'events' ? t('backtester.events') : t('backtester.filters')}
        />
      )}
    </div>
  );
}

/* ── Resultados ─────────────────────────────────────────────────────────── */

function SimResults({ r }: { r: SimResult }) {
  const { t } = useTranslation();
  const m = r.metrics;
  const pnlPos = m.total_pnl >= 0;

  return (
    <div className="flex flex-col gap-5 pt-1 border-t" style={{ borderColor: RULE }}>

      <div className="flex items-baseline gap-x-6 gap-y-3 pt-3 flex-wrap">
        <Headline label={t('backtester.pnl')} value={`${pnlPos ? '+' : ''}${num0(m.total_pnl)} $`} accent={pnlPos ? 'up' : 'down'} sub={`${m.total_return_pct > 0 ? '+' : ''}${m.total_return_pct}%`} />
        <Headline label={t('backtester.trades')} value={String(m.trades)} sub={t('backtester.ofTriggers', { n: r.entries_simulated, total: num0(r.triggers_total) })} />
        <Headline label={t('backtester.winRate')} value={m.win_rate === null ? '—' : `${(m.win_rate * 100).toFixed(1)}%`} />
        <Headline label={t('backtester.profitFactor')} value={m.profit_factor === null ? '—' : String(m.profit_factor)} />
        <Headline label={t('backtester.maxDrawdown')} value={`${m.max_drawdown_pct}%`} accent="down" />
        <Headline label={t('backtester.worstStreak')} value={String(m.max_consecutive_losses)} sub={t('backtester.lossesInARow')} />
      </div>

      {r.equity_curve.length > 1 && (
        <section className="flex flex-col gap-1.5">
          <SectionHead title={t('backtester.equityCurve')} />
          <EquityCurve points={r.equity_curve} />
        </section>
      )}

      {r.signal && <SignalSection sig={r.signal} />}

      <div className="flex flex-wrap gap-x-8 gap-y-5">
        <section className="flex flex-col gap-1.5 min-w-[160px]">
          <SectionHead title={t('backtester.exitsBreakdown')} />
          <KvList entries={Object.entries(m.by_exit_reason).map(([k, v]) => [t(`backtester.exitReasons.${k}`, k), v])} />
        </section>
        <section className="flex flex-col gap-1.5 min-w-[160px]">
          <SectionHead title={t('backtester.skipped')} />
          <KvList entries={Object.entries(r.entries_skipped).map(([k, v]) => [t(`backtester.skipReasons.${k}`, k), v])} />
        </section>
        <section className="flex flex-col gap-1.5 min-w-[160px]">
          <SectionHead title={t('backtester.dailyPnl')} />
          <KvList entries={Object.entries(r.daily_pnl).map(([d, v]) => [d.slice(5), `${v >= 0 ? '+' : ''}${num0(v)} $`])} />
        </section>
      </div>

      {r.trades_sample.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <SectionHead title={t('backtester.tradesTable', { n: Math.min(r.trades_sample.length, 20) })} />
          <div className="overflow-x-auto">
            <div className="min-w-[520px] grid grid-cols-[56px_52px_1fr_68px_68px_84px_70px] gap-x-2 text-[11px] font-mono tabular-nums">
              <span className="text-foreground/45 font-sans">{t('backtester.day')}</span>
              <span className="text-foreground/45 font-sans">{t('backtester.symbol')}</span>
              <span className="text-foreground/45 font-sans">{t('backtester.event')}</span>
              <span className="text-right text-foreground/45 font-sans">{t('backtester.entry')}</span>
              <span className="text-right text-foreground/45 font-sans">{t('backtester.exit')}</span>
              <span className="text-foreground/45 font-sans">{t('backtester.reason')}</span>
              <span className="text-right text-foreground/45 font-sans">{t('backtester.pnl')}</span>
              {r.trades_sample.slice(0, 20).map((x, i) => (
                <TradeRow key={i} x={x} />
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="flex flex-col gap-1.5 pb-2">
        <SectionHead title={t('backtester.assumptions')} />
        <ul className="m-0 pl-4 flex flex-col gap-1">
          {(t('backtester.assumptionsList', { returnObjects: true }) as string[]).map((a, i) => (
            <li key={i} className="text-[11px] text-foreground/60 leading-snug">{a}</li>
          ))}
          {r.warnings.map((w, i) => (
            <li key={`w${i}`} className="text-[11px] text-foreground/60 leading-snug">
              {t(`backtester.warnings.${w.code}`, {
                defaultValue: w.detail,
                days: w.days?.join(', ') ?? '',
              })}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function SignalSection({ sig }: { sig: SignalBlock }) {
  const { t } = useTranslation();
  const fwd = sig.forward_returns;
  const hours = Object.entries(sig.by_hour_et).map(([h, n]) => [Number(h), n] as const);
  const maxHour = Math.max(1, ...hours.map(([, n]) => n));
  return (
    <section className="flex flex-col gap-2.5">
      <SectionHead title={t('backtester.signal')} />
      <div className="overflow-x-auto">
        <div className="min-w-[420px] max-w-[560px] grid grid-cols-[64px_repeat(5,minmax(56px,1fr))] gap-x-3 text-[11px]">
          <span />
          <span className="text-right text-foreground/45">{t('backtester.mean')}</span>
          <span className="text-right text-foreground/45">{t('backtester.median')}</span>
          <span className="text-right text-foreground/45">{t('backtester.win')}</span>
          <span className="text-right text-foreground/45">p10</span>
          <span className="text-right text-foreground/45">p90</span>
          {HORIZONS.map(h => {
            const st = fwd[h] as FwdStat | undefined;
            const label = h === 'close' ? t('backtester.close') : h.replace('min', ' min');
            return <FwdRow key={h} label={label} s={st} />;
          })}
        </div>
      </div>
      <div className="flex items-end gap-1 h-12 max-w-[560px]">
        {hours.map(([h, n]) => (
          <div key={h} className="flex flex-col items-center gap-0.5 flex-1 min-w-0" title={`${h}:00 — ${n.toLocaleString()}`}>
            <div className="w-full rounded-sm bg-foreground/25" style={{ height: `${Math.max(3, (n / maxHour) * 36)}px` }} />
            <span className="text-[9px] font-mono text-foreground/45">{h}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(sig.top_symbols).slice(0, 10).map(([sym, n]) => (
          <span key={sym} className="inline-flex items-baseline gap-1 h-5 px-1.5 rounded text-[10px] bg-foreground/[0.05] border" style={{ borderColor: RULE }}>
            <span className="font-mono font-medium">{sym}</span>
            <span className="text-foreground/45 font-mono tabular-nums">{n.toLocaleString()}</span>
          </span>
        ))}
      </div>
      {fwd.sampled && (
        <p className="m-0 text-[10px] text-foreground/40">
          {t('backtester.sampledNote', { n: num0(fwd.population_n ?? 0) })}
        </p>
      )}
    </section>
  );
}

function FwdRow({ label, s }: { label: string; s?: FwdStat }) {
  return (
    <>
      <span className="text-foreground/60 py-1">{label}</span>
      <span className={cn('text-right font-mono tabular-nums py-1', pctColor(s?.mean_pct))}>{pct(s?.mean_pct)}</span>
      <span className={cn('text-right font-mono tabular-nums py-1', pctColor(s?.median_pct))}>{pct(s?.median_pct)}</span>
      <span className="text-right font-mono tabular-nums py-1">{s?.win_rate === undefined ? '—' : `${(s.win_rate * 100).toFixed(0)}%`}</span>
      <span className="text-right font-mono tabular-nums py-1 text-foreground/60">{pct(s?.p10_pct)}</span>
      <span className="text-right font-mono tabular-nums py-1 text-foreground/60">{pct(s?.p90_pct)}</span>
    </>
  );
}

function Headline({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: 'up' | 'down';
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-foreground/45">{label}</span>
      <span className={cn('font-mono tabular-nums text-[20px] leading-tight',
        accent === 'up' && 'text-emerald-600',
        accent === 'down' && 'text-rose-500 dark:text-rose-400')}>{value}</span>
      {sub && <span className="text-[10px] text-foreground/45">{sub}</span>}
    </div>
  );
}

function KvList({ entries }: { entries: [string, string | number][] }) {
  if (!entries.length) return <p className="m-0 text-[11px] text-foreground/45">—</p>;
  return (
    <div className="flex flex-col">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-6 py-0.5 text-[11px]">
          <span className="text-foreground/55">{k}</span>
          <span className="font-mono tabular-nums">{typeof v === 'number' ? v.toLocaleString() : v}</span>
        </div>
      ))}
    </div>
  );
}

function TradeRow({ x }: { x: SimResult['trades_sample'][number] }) {
  const { t } = useTranslation();
  return (
    <>
      <span>{x.dt.slice(5)}</span>
      <span>{x.symbol}</span>
      <span className="truncate font-sans text-foreground/60">{eventLabel(x.event_type)}</span>
      <span className="text-right">{x.entry_px}</span>
      <span className="text-right">{x.exit_px}</span>
      <span className="font-sans text-foreground/60">{t(`backtester.exitReasons.${x.reason}`, x.reason)}</span>
      <span className={cn('text-right', x.pnl >= 0 ? 'text-emerald-600' : 'text-rose-500 dark:text-rose-400')}>
        {x.pnl >= 0 ? '+' : ''}{num0(x.pnl)}
      </span>
    </>
  );
}

function EquityCurve({ points }: { points: [number, number][] }) {
  const w = 640, h = 96, pad = 4;
  const ys = points.map(p => p[1]);
  const min = Math.min(...ys), max = Math.max(...ys);
  const span = max - min || 1;
  const step = (w - pad * 2) / Math.max(points.length - 1, 1);
  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${(pad + i * step).toFixed(1)},${(h - pad - ((p[1] - min) / span) * (h - pad * 2)).toFixed(1)}`)
    .join(' ');
  const base = h - pad - ((points[0][1] - min) / span) * (h - pad * 2);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-[720px] h-24" preserveAspectRatio="none" aria-hidden="true">
      <line x1={pad} x2={w - pad} y1={base} y2={base} stroke="currentColor" strokeOpacity={0.15} strokeDasharray="3 3" />
      <path d={d} fill="none" stroke="currentColor" strokeOpacity={0.7} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
