'use client';

/**
 * Panel de resultados.
 *
 * Solo se monta la pestaña activa: las otras no existen en el DOM, así que
 * cambiar de pestaña no arrastra el coste de las demás y el gráfico no vive
 * escondido consumiendo memoria.
 *
 * Honestidad medida: con más de un símbolo el motor recorre los tickers uno
 * tras otro compartiendo una `equity`, así que la curva, el Sharpe y el
 * drawdown dejan de ser de fiar; y el bloque de robustez entero está medido
 * como no utilizable. En vez de esconderlo o de presentarlo como si nada, se
 * marca donde toca.
 */

import { memo, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import type { BacktestResult } from '@/components/ai-agent/backtest/BacktestTypes';
import { ResultsChart, type Overlay } from './ResultsChart';
import { TradesTable } from './TradesTable';
import { CenterMessage, Chip, RULE } from './ui';

const nf0 = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (v: number | null | undefined, d = 1) =>
  v == null ? '–' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)} %`;
const money = (v: number | null | undefined) =>
  v == null ? '–' : `${v >= 0 ? '+' : '−'}${nf0.format(Math.abs(v))} $`;

const UP = 'text-[var(--color-chart-up,#22c55e)]';
const DOWN = 'text-[var(--color-chart-down,#f87171)]';
const dir = (v: number) => (v >= 0 ? UP : DOWN);

type Tab = 'resumen' | 'trades' | 'diario' | 'filtros' | 'robustez';

export const ResultsPane = memo(function ResultsPane({
  result, overlays, warnings, unreliablePortfolio,
}: {
  result: BacktestResult;
  overlays: Overlay[];
  /** Diagnóstico calculado en el cliente, aparte de `result.warnings`. */
  warnings: string[];
  unreliablePortfolio: boolean;
}) {
  const [tab, setTab] = useState<Tab>('resumen');

  const engineWarnings = result.warnings ?? [];
  const allWarnings = useMemo(
    () => [...warnings, ...engineWarnings],
    [warnings, engineWarnings],
  );

  const tabs: { value: Tab; label: string; n?: number }[] = [
    { value: 'resumen', label: 'Resumen' },
    { value: 'trades', label: 'Operaciones', n: result.trades?.length },
    { value: 'diario', label: 'Diario', n: result.daily_stats?.length },
    { value: 'filtros', label: 'Por filtro', n: Object.keys(result.optimization ?? {}).length || undefined },
    { value: 'robustez', label: 'Robustez' },
  ];

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex items-center px-2 border-b overflow-x-auto" style={{ borderColor: RULE }}>
        {tabs.map(t => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={cn(
              'relative shrink-0 h-8 px-2.5 text-[11px] transition-colors',
              tab === t.value ? 'text-foreground font-semibold' : 'text-foreground/55 hover:text-foreground/85',
            )}
          >
            {t.label}
            {t.n != null && <span className="ml-1.5 font-mono text-[10px] text-foreground/35">{t.n}</span>}
            {tab === t.value && (
              <span className="absolute left-2.5 right-2.5 -bottom-px h-[1.5px] bg-foreground/55" />
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === 'resumen' && (
          <Summary result={result} overlays={overlays} warnings={allWarnings} unreliable={unreliablePortfolio} />
        )}
        {tab === 'trades' && <TradesTable trades={result.trades ?? []} />}
        {tab === 'diario' && <DailyTab result={result} />}
        {tab === 'filtros' && <OptimizationTab result={result} />}
        {tab === 'robustez' && <RobustnessTab result={result} />}
      </div>
    </div>
  );
});

/* ══════════════════════════ RESUMEN ══════════════════════════ */

const Summary = memo(function Summary({
  result, overlays, warnings, unreliable,
}: {
  result: BacktestResult; overlays: Overlay[]; warnings: string[]; unreliable: boolean;
}) {
  const cm = result.core_metrics;
  const [openWarnings, setOpenWarnings] = useState(false);

  const dailyPnl = useMemo(
    () => (result.daily_stats ?? []).map(d => ({ date: d.date, pnl: d.pnl })),
    [result.daily_stats],
  );

  const finalEquity = result.equity_curve?.length
    ? result.equity_curve[result.equity_curve.length - 1][1]
    : result.strategy.initial_capital;

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex items-end gap-7 px-4 pt-3 pb-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <span className="text-[10px] uppercase tracking-wider text-foreground/45">Retorno</span>
          <span className={cn('font-mono text-[20px] font-semibold tabular-nums leading-tight', dir(cm.total_return_pct))}>
            {pct(cm.total_return_pct)}
          </span>
          <span className="font-mono text-[11px] tabular-nums text-foreground/50">
            {nf0.format(finalEquity)} $ · {cm.total_trades} operaciones
          </span>
        </div>

        <div className="flex gap-6 pb-0.5">
          <Stat k="Profit factor" v={cm.profit_factor.toFixed(2)} />
          <Stat k="Aciertos" v={`${(cm.win_rate * 100).toFixed(1)} %`} />
          <Stat k="Drawdown" v={pct(-Math.abs(cm.max_drawdown_pct))} tone={DOWN} />
        </div>
      </div>

      <div className="flex-1 min-h-[180px]">
        <ResultsChart
          equity={result.equity_curve ?? []}
          drawdown={result.drawdown_curve}
          dailyPnl={dailyPnl}
          initialCapital={result.strategy.initial_capital}
          overlays={overlays}
          className="h-full"
        />
      </div>

      {warnings.length > 0 && (
        <div className="shrink-0 border-t" style={{ borderColor: RULE }}>
          <button
            type="button"
            aria-expanded={openWarnings}
            onClick={() => setOpenWarnings(v => !v)}
            className="w-full flex items-center gap-2 px-4 h-7 text-left hover:bg-foreground/[0.03] transition-colors"
          >
            <span className="text-[10px] uppercase tracking-wider text-foreground/45">Revisar</span>
            <span className="font-mono text-[11px] font-semibold tabular-nums">{warnings.length}</span>
            <span className="flex-1 truncate text-[11px] text-foreground/55">
              {!openWarnings && warnings[0]}
            </span>
            <span className="text-foreground/35 text-[11px]">{openWarnings ? '−' : '+'}</span>
          </button>
          {openWarnings && (
            <ul className="px-4 pb-2.5 flex flex-col gap-1.5 max-h-28 overflow-auto">
              {warnings.map((w, i) => (
                <li key={i} className="flex gap-2 text-[11px] leading-snug text-foreground/65">
                  <span className="text-foreground/30 shrink-0">·</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="shrink-0 grid grid-cols-3 gap-x-6 px-4 py-2.5 border-t" style={{ borderColor: RULE }}>
        <div>
          <Row k="Sharpe" v={cm.sharpe_ratio.toFixed(2)} dim={unreliable} />
          <Row k="Sortino" v={cm.sortino_ratio.toFixed(2)} dim={unreliable} />
          <Row k="Calmar" v={cm.calmar_ratio.toFixed(2)} dim={unreliable} />
        </div>
        <div>
          <Row k="Expectativa" v={money(cm.expectancy)} tone={dir(cm.expectancy)} />
          <Row k="Media ganadora" v={pct(cm.avg_winner_pct * 100)} tone={UP} />
          <Row k="Media perdedora" v={pct(cm.avg_loser_pct * 100)} tone={DOWN} />
        </div>
        <div>
          <Row k="Duración media" v={`${cm.avg_holding_bars.toFixed(1)} barras`} />
          <Row k="Recuperación" v={cm.recovery_factor.toFixed(2)} dim={unreliable} />
          <Row k="Ulcer" v={cm.ulcer_index.toFixed(2)} dim={unreliable} />
        </div>
      </div>
    </div>
  );
});

const Stat = memo(function Stat({ k, v, tone }: { k: string; v: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-foreground/45 whitespace-nowrap">{k}</span>
      <span className={cn('font-mono text-[13px] font-semibold tabular-nums', tone)}>{v}</span>
    </div>
  );
});

const Row = memo(function Row({
  k, v, tone, dim,
}: { k: string; v: string; tone?: string; dim?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 border-b last:border-b-0" style={{ borderColor: RULE }}>
      <span className="text-[11px] text-foreground/55">{k}</span>
      <span
        className={cn('font-mono text-[12px] font-semibold tabular-nums', tone, dim && 'text-foreground/30 font-normal')}
        title={dim ? 'No es de fiar con varios símbolos: el motor no simula cartera' : undefined}
      >
        {v}
      </span>
    </div>
  );
});

/* ══════════════════════════ DIARIO ══════════════════════════ */

const DailyTab = memo(function DailyTab({ result }: { result: BacktestResult }) {
  const days = result.daily_stats ?? [];
  if (!days.length) return <CenterMessage>Sin estadísticas diarias</CenterMessage>;

  return (
    <div className="h-full overflow-auto">
      <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
        <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--color-surface)' }}>
          <tr style={{ borderBottom: `1px solid ${RULE}` }}>
            {['Fecha', 'Operaciones', 'Aciertos', 'Media', 'PnL', 'Equity'].map((h, i) => (
              <th
                key={h}
                className={cn(
                  'px-2 py-2 text-[10px] uppercase tracking-wider text-foreground/55 font-medium',
                  i === 0 ? 'text-left pl-3' : 'text-right',
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((d, i) => (
            <tr key={d.date} className={cn('hover:bg-foreground/[0.06]', i % 2 === 1 && 'bg-foreground/[0.025]')}>
              <td className="pl-3 pr-2 py-1.5 text-[12px] tabular-nums">{d.date}</td>
              <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">{d.trades_count}</td>
              <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">
                {d.winners}/{d.trades_count}
              </td>
              <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">{nf0.format(d.avg_gain)}</td>
              <td className={cn('px-2 py-1.5 text-[12px] text-right tabular-nums font-semibold', dir(d.pnl))}>
                {money(d.pnl)}
              </td>
              <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">
                {nf0.format(d.net_equity)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

/* ══════════════════════════ POR FILTRO ══════════════════════════ */

const OptimizationTab = memo(function OptimizationTab({ result }: { result: BacktestResult }) {
  const opt = result.optimization ?? {};
  const keys = Object.keys(opt);
  const [active, setActive] = useState(keys[0] ?? '');

  if (!keys.length) {
    return <CenterMessage>Sin desglose por filtro. Hace falta una corrida con más operaciones.</CenterMessage>;
  }

  const bd = opt[active] ?? opt[keys[0]];

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 flex flex-wrap items-center gap-1.5 px-3 py-2 border-b" style={{ borderColor: RULE }}>
        {keys.map(k => (
          <Chip key={k} label={opt[k].filter_name} active={k === active} onClick={() => setActive(k)} />
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
          <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--color-surface)' }}>
            <tr style={{ borderBottom: `1px solid ${RULE}` }}>
              {[bd.filter_name, 'PF', 'Aciertos', 'Media', 'Total', 'Ops.', '% del total'].map((h, i) => (
                <th
                  key={h}
                  className={cn(
                    'px-2 py-2 text-[10px] uppercase tracking-wider text-foreground/55 font-medium',
                    i === 0 ? 'text-left pl-3' : 'text-right',
                  )}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bd.buckets.map((b, i) => (
              <tr key={i} className={cn('hover:bg-foreground/[0.06]', i % 2 === 1 && 'bg-foreground/[0.025]')}>
                <td className="pl-3 pr-2 py-1.5 text-[12px]">{b.label}</td>
                <td className={cn('px-2 py-1.5 text-[12px] text-right tabular-nums font-semibold',
                  b.profit_factor >= 1 ? UP : DOWN)}>
                  {b.profit_factor.toFixed(2)}
                </td>
                <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">
                  {b.win_rate.toFixed(1)} %
                </td>
                <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">{nf0.format(b.avg_gain)}</td>
                <td className={cn('px-2 py-1.5 text-[12px] text-right tabular-nums', dir(b.total_gain))}>
                  {money(b.total_gain)}
                </td>
                <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/65">{b.trades}</td>
                <td className="px-2 py-1.5 text-[12px] text-right tabular-nums text-foreground/45">
                  {b.pct_of_total.toFixed(1)} %
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});

/* ══════════════════════════ ROBUSTEZ ══════════════════════════ */

/**
 * Walk-forward y Monte Carlo se muestran, pero con lo que sabemos de ellos.
 * Medido: el walk-forward no reoptimiza nada entre tramos, así que la
 * degradación que reporta no es la de un walk-forward de verdad; y el Monte
 * Carlo remuestrea el retorno por posición como si fuera de cartera.
 * Enseñarlos sin decirlo sería exactamente el problema que este rediseño ataca.
 */
const RobustnessTab = memo(function RobustnessTab({ result }: { result: BacktestResult }) {
  const wf = result.walk_forward;
  const mc = result.monte_carlo;
  const am = result.advanced_metrics;

  if (!wf && !mc && !am) return <CenterMessage>Esta corrida no incluyó análisis de robustez</CenterMessage>;

  return (
    <div className="h-full overflow-auto px-4 py-3 flex flex-col gap-5">
      {am && (
        <section className="flex flex-col gap-2">
          <Head title="Métricas estadísticas" note="El DSR no llega a deflactar con un solo ensayo, y el PSR se satura en 1,0." />
          <div className="grid grid-cols-5 gap-4">
            <Stat k="Sharpe deflactado" v={am.deflated_sharpe_ratio.toFixed(2)} />
            <Stat k="Sharpe prob." v={`${(am.probabilistic_sharpe_ratio * 100).toFixed(1)} %`} />
            <Stat k="Histórico mín." v={`${am.min_track_record_length} m`} />
            <Stat k="Asimetría" v={am.skewness.toFixed(3)} />
            <Stat k="Curtosis" v={am.kurtosis.toFixed(3)} />
          </div>
        </section>
      )}

      {wf && (
        <section className="flex flex-col gap-2">
          <Head
            title={`Walk-forward · ${wf.n_splits} tramos`}
            note="No reoptimiza los parámetros entre tramos: la degradación no es la de un walk-forward completo."
          />
          <div className="flex flex-col">
            {wf.splits.map(s => (
              <div key={s.split_idx} className="flex items-center gap-3 py-1.5 border-b last:border-b-0" style={{ borderColor: RULE }}>
                <span className="w-5 text-right font-mono text-[11px] text-foreground/45 tabular-nums">{s.split_idx + 1}</span>
                <span className="font-mono text-[11px] tabular-nums text-foreground/65 w-[92px]">
                  {String(s.test_start).slice(0, 10)}
                </span>
                <span className="font-mono text-[11px] tabular-nums w-[76px]">
                  <span className="text-foreground/45">ent.</span> {s.train_sharpe.toFixed(2)}
                </span>
                <span className="font-mono text-[11px] tabular-nums w-[76px]">
                  <span className="text-foreground/45">val.</span> {s.test_sharpe.toFixed(2)}
                </span>
                <span className={cn('ml-auto font-mono text-[11px] font-semibold tabular-nums', dir(s.degradation_pct))}>
                  {pct(s.degradation_pct, 0)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {mc && (
        <section className="flex flex-col gap-2">
          <Head
            title={`Monte Carlo · ${nf0.format(mc.n_simulations)} simulaciones`}
            note="Remuestrea el retorno por posición como si fuera de cartera, así que el abanico sale más estrecho de lo real."
          />
          <div className="grid grid-cols-2 gap-x-8">
            <Row k="Probabilidad de ganar" v={`${(mc.prob_profit * 100).toFixed(0)} %`} />
            <Row k="Equity mediana" v={`${nf0.format(mc.median_final_equity)} $`} />
            <Row k="Percentil 5" v={`${nf0.format(mc.percentile_5_equity)} $`} />
            <Row k="Percentil 95" v={`${nf0.format(mc.percentile_95_equity)} $`} />
            <Row k="Drawdown medio" v={pct(-Math.abs(mc.mean_max_drawdown_pct))} tone={DOWN} />
            <Row k="Peor drawdown" v={pct(-Math.abs(mc.worst_max_drawdown_pct))} tone={DOWN} />
          </div>
        </section>
      )}
    </div>
  );
});

const Head = memo(function Head({ title, note }: { title: string; note?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground/55 shrink-0">{title}</span>
        <span className="flex-1 h-px" style={{ backgroundColor: RULE }} />
      </div>
      {note && <p className="m-0 text-[11px] leading-snug text-foreground/45 max-w-[70ch]">{note}</p>}
    </div>
  );
});
