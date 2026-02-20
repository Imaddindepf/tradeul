'use client';

import { memo, useState, useMemo, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import dynamic from 'next/dynamic';
import type {
  BacktestResult,
  CoreMetrics,
  AdvancedMetrics,
  TradeRecord,
  WalkForwardResult,
  MonteCarloResult,
} from './BacktestTypes';

const LazyPlot = dynamic(() => import('react-plotly.js'), {
  ssr: false,
  loading: () => <div className="h-[260px] bg-slate-50 rounded-lg animate-pulse" />,
});

// ── Formatting Helpers ─────────────────────────────────────────────────────

function fmtPct(v: number, decimals = 1): string {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(decimals)}%`;
}

function fmtPctRaw(v: number, decimals = 1): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}%`;
}

function fmtMoney(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtNum(v: number, d = 2): string {
  return v.toFixed(d);
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: '2-digit' });
}

type Quality = 'excellent' | 'good' | 'fair' | 'poor';

function metricQuality(key: string, val: number): Quality {
  const rules: Record<string, [number, number, number]> = {
    sharpe_ratio: [1.5, 1.0, 0.5],
    sortino_ratio: [2.0, 1.3, 0.7],
    calmar_ratio: [2.0, 1.0, 0.5],
    win_rate: [0.6, 0.5, 0.4],
    profit_factor: [2.0, 1.5, 1.0],
    recovery_factor: [3.0, 1.5, 0.8],
    total_return_pct: [50, 20, 5],
    annualized_return_pct: [30, 15, 5],
  };
  const r = rules[key];
  if (!r) return 'fair';
  if (val >= r[0]) return 'excellent';
  if (val >= r[1]) return 'good';
  if (val >= r[2]) return 'fair';
  return 'poor';
}

function qualityColor(q: Quality): string {
  switch (q) {
    case 'excellent': return 'text-emerald-600';
    case 'good': return 'text-emerald-500';
    case 'fair': return 'text-slate-700';
    case 'poor': return 'text-red-500';
  }
}

function qualityBorder(q: Quality): string {
  switch (q) {
    case 'excellent': return 'border-emerald-200';
    case 'good': return 'border-emerald-100';
    case 'fair': return 'border-slate-200/80';
    case 'poor': return 'border-red-200';
  }
}

// ── Metric Card ────────────────────────────────────────────────────────────

interface MetricDef {
  key: string;
  label: string;
  format: (v: number) => string;
  tooltip: string;
  invert?: boolean;
}

const PRIMARY_METRICS: MetricDef[] = [
  { key: 'total_return_pct', label: 'Retorno Total', format: v => fmtPctRaw(v), tooltip: 'Retorno acumulado del periodo completo' },
  { key: 'sharpe_ratio', label: 'Sharpe Ratio', format: v => fmtNum(v), tooltip: 'Retorno ajustado al riesgo (>1.0 bueno, >2.0 excelente)' },
  { key: 'sortino_ratio', label: 'Sortino Ratio', format: v => fmtNum(v), tooltip: 'Similar a Sharpe pero solo penaliza volatilidad negativa' },
  { key: 'win_rate', label: 'Win Rate', format: v => fmtPct(v), tooltip: 'Porcentaje de operaciones ganadoras' },
  { key: 'max_drawdown_pct', label: 'Max Drawdown', format: v => fmtPctRaw(v), tooltip: 'Maxima caida desde un pico de equity', invert: true },
  { key: 'profit_factor', label: 'Profit Factor', format: v => fmtNum(v), tooltip: 'Ratio de ganancias brutas / perdidas brutas' },
  { key: 'calmar_ratio', label: 'Calmar Ratio', format: v => fmtNum(v), tooltip: 'Retorno anualizado / Max Drawdown' },
  { key: 'recovery_factor', label: 'Recovery Factor', format: v => fmtNum(v), tooltip: 'Retorno neto / Max Drawdown' },
];

const SECONDARY_METRICS: MetricDef[] = [
  { key: 'annualized_return_pct', label: 'Ret. Anualizado', format: v => fmtPctRaw(v), tooltip: 'Retorno anualizado compuesto' },
  { key: 'total_pnl', label: 'PnL Total', format: v => fmtMoney(v), tooltip: 'Ganancia/perdida neta en dolares' },
  { key: 'total_trades', label: 'Total Trades', format: v => v.toString(), tooltip: 'Numero total de operaciones ejecutadas' },
  { key: 'avg_holding_bars', label: 'Avg Hold', format: v => `${fmtNum(v, 1)} bars`, tooltip: 'Duracion media de las posiciones en barras' },
  { key: 'expectancy', label: 'Expectancy', format: v => fmtMoney(v), tooltip: 'Ganancia esperada por operacion' },
  { key: 'avg_winner_pct', label: 'Avg Winner', format: v => fmtPct(v), tooltip: 'Retorno medio de operaciones ganadoras' },
  { key: 'avg_loser_pct', label: 'Avg Loser', format: v => fmtPct(v), tooltip: 'Retorno medio de operaciones perdedoras' },
  { key: 'best_trade_pct', label: 'Best Trade', format: v => fmtPct(v), tooltip: 'Mejor operacion individual' },
  { key: 'worst_trade_pct', label: 'Worst Trade', format: v => fmtPct(v), tooltip: 'Peor operacion individual' },
  { key: 'ulcer_index', label: 'Ulcer Index', format: v => fmtNum(v), tooltip: 'Indice de dolor - mide profundidad y duracion de drawdowns', invert: true },
  { key: 'tail_ratio', label: 'Tail Ratio', format: v => fmtNum(v), tooltip: 'Ratio entre colas positivas y negativas de la distribucion' },
  { key: 'common_sense_ratio', label: 'CSR', format: v => fmtNum(v), tooltip: 'Common Sense Ratio = Tail Ratio x Profit Factor' },
];

const MetricCard = memo(function MetricCard({
  def,
  value,
  compact,
}: {
  def: MetricDef;
  value: number;
  compact?: boolean;
}) {
  const q = def.invert
    ? metricQuality(def.key, -Math.abs(value))
    : metricQuality(def.key, value);
  const isNeg = value < 0;

  return (
    <div
      className={`rounded-lg border px-2 py-1.5 ${qualityBorder(q)} bg-white hover:shadow-sm transition-shadow`}
      title={def.tooltip}
    >
      <span className="text-[9px] font-medium text-slate-500 uppercase tracking-wider block truncate">
        {def.label}
      </span>
      <span className={`${compact ? 'text-[12px]' : 'text-[13px]'} font-bold tabular-nums block mt-0.5 ${
        def.invert
          ? (isNeg ? 'text-red-500' : 'text-emerald-600')
          : qualityColor(q)
      }`}>
        {def.format(value)}
      </span>
    </div>
  );
});

// ── Strategy Header ────────────────────────────────────────────────────────

const StrategyHeader = memo(function StrategyHeader({
  result,
}: {
  result: BacktestResult;
}) {
  const s = result.strategy;
  return (
    <div className="px-3 py-2 border-b border-slate-200/60 bg-white">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[12px] font-bold text-slate-800 truncate">{s.name}</h3>
          {s.description && (
            <p className="text-[10px] text-slate-500 mt-0.5 truncate">{s.description}</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[9px] text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200/60">
            {s.start_date} → {s.end_date}
          </span>
          <span className="text-[9px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-100">
            {s.timeframe}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 mt-1.5 text-[9px] text-slate-400">
        <span>{fmtMoney(s.initial_capital)} capital</span>
        <span className="text-slate-200">|</span>
        <span>{result.symbols_tested} tickers</span>
        <span className="text-slate-200">|</span>
        <span>{result.bars_processed.toLocaleString()} bars</span>
        <span className="text-slate-200">|</span>
        <span>{result.execution_time_ms < 1000 ? `${result.execution_time_ms}ms` : `${(result.execution_time_ms / 1000).toFixed(1)}s`}</span>
        <span className="text-slate-200">|</span>
        <span>{s.direction}</span>
        <span className="text-slate-200">|</span>
        <span>{s.slippage_bps}bps slippage</span>
      </div>
    </div>
  );
});

// ── Tab Bar ────────────────────────────────────────────────────────────────

type TabId = 'overview' | 'trades' | 'analysis';

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Resumen' },
  { id: 'trades', label: 'Operaciones' },
  { id: 'analysis', label: 'Analisis' },
];

const TabBar = memo(function TabBar({
  active,
  onChange,
  tradeCount,
}: {
  active: TabId;
  onChange: (t: TabId) => void;
  tradeCount: number;
}) {
  return (
    <div className="flex items-center gap-0 border-b border-slate-200/60 px-3 bg-white">
      {TABS.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`relative px-3 py-1.5 text-[10px] font-medium transition-colors ${
            active === tab.id
              ? 'text-indigo-600'
              : 'text-slate-400 hover:text-slate-600'
          }`}
        >
          {tab.label}
          {tab.id === 'trades' && (
            <span className="ml-1 text-[8px] text-slate-400 tabular-nums">({tradeCount})</span>
          )}
          {active === tab.id && (
            <motion.div
              layoutId="backtest-tab-indicator"
              className="absolute bottom-0 left-0 right-0 h-[2px] bg-indigo-500 rounded-full"
              transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            />
          )}
        </button>
      ))}
    </div>
  );
});

// ── Equity Chart ───────────────────────────────────────────────────────────

const EquityChart = memo(function EquityChart({
  equityCurve,
  drawdownCurve,
}: {
  equityCurve: [string, number][];
  drawdownCurve: [string, number][];
}) {
  const plotData = useMemo(() => {
    const dates = equityCurve.map(p => p[0]);
    const equity = equityCurve.map(p => p[1]);
    const dd = drawdownCurve.map(p => p[1]);

    return {
      data: [
        {
          x: dates,
          y: equity,
          type: 'scatter' as const,
          mode: 'lines' as const,
          name: 'Equity',
          line: { color: '#2563EB', width: 1.5 },
          xaxis: 'x',
          yaxis: 'y',
        },
        {
          x: dates,
          y: dd,
          type: 'scatter' as const,
          mode: 'lines' as const,
          fill: 'tozeroy' as const,
          name: 'Drawdown',
          line: { color: '#EF4444', width: 1 },
          fillcolor: 'rgba(239,68,68,0.1)',
          xaxis: 'x',
          yaxis: 'y2',
        },
      ],
      layout: {
        margin: { t: 8, r: 8, b: 28, l: 52 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Arial, sans-serif', size: 9, color: '#64748B' },
        showlegend: false,
        xaxis: {
          showgrid: false,
          tickfont: { size: 8 },
          type: 'date' as const,
        },
        yaxis: {
          title: { text: 'Equity ($)', font: { size: 9 } },
          gridcolor: '#F1F5F9',
          tickfont: { size: 8 },
          domain: [0.3, 1],
        },
        yaxis2: {
          title: { text: 'DD (%)', font: { size: 9 } },
          gridcolor: '#F1F5F9',
          tickfont: { size: 8 },
          domain: [0, 0.25],
          tickformat: '.1%',
        },
        hovermode: 'x unified' as const,
      },
      config: {
        displayModeBar: false,
        responsive: true,
      },
    };
  }, [equityCurve, drawdownCurve]);

  return (
    <div className="rounded-lg border border-slate-200/80 bg-white overflow-hidden">
      <div className="px-2.5 py-1.5 border-b border-slate-100">
        <span className="text-[10px] font-semibold text-slate-600">Curva de Equity & Drawdown</span>
      </div>
      <div className="h-[240px]">
        <LazyPlot
          data={plotData.data as any}
          layout={plotData.layout as any}
          config={plotData.config}
          style={{ width: '100%', height: '100%' }}
          useResizeHandler
        />
      </div>
    </div>
  );
});

// ── Monthly Returns Heatmap ────────────────────────────────────────────────

const MONTHS_SHORT = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

function returnColor(v: number): string {
  if (v >= 5) return 'bg-emerald-600 text-white';
  if (v >= 2) return 'bg-emerald-400 text-white';
  if (v >= 0.5) return 'bg-emerald-100 text-emerald-800';
  if (v >= -0.5) return 'bg-slate-50 text-slate-600';
  if (v >= -2) return 'bg-red-100 text-red-800';
  if (v >= -5) return 'bg-red-400 text-white';
  return 'bg-red-600 text-white';
}

const MonthlyHeatmap = memo(function MonthlyHeatmap({
  monthlyReturns,
}: {
  monthlyReturns: Record<string, number>;
}) {
  const grid = useMemo(() => {
    const years = new Map<string, (number | null)[]>();
    for (const [key, val] of Object.entries(monthlyReturns)) {
      const [year, month] = key.split('-');
      if (!years.has(year)) years.set(year, new Array(12).fill(null));
      const row = years.get(year)!;
      row[parseInt(month) - 1] = val * 100;
    }
    const sorted = [...years.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    return sorted.map(([year, months]) => {
      const filled = months.filter(v => v !== null) as number[];
      const ytd = filled.reduce((s, v) => s + v, 0);
      return { year, months, ytd };
    });
  }, [monthlyReturns]);

  if (grid.length === 0) return null;

  return (
    <div className="rounded-lg border border-slate-200/80 bg-white overflow-hidden">
      <div className="px-2.5 py-1.5 border-b border-slate-100">
        <span className="text-[10px] font-semibold text-slate-600">Retornos Mensuales</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[9px]">
          <thead>
            <tr className="bg-slate-50/80">
              <th className="px-1.5 py-1 text-left font-semibold text-slate-600 w-10">Year</th>
              {MONTHS_SHORT.map(m => (
                <th key={m} className="px-1 py-1 text-center font-semibold text-slate-500 w-9">{m}</th>
              ))}
              <th className="px-1.5 py-1 text-center font-bold text-slate-700 w-10">YTD</th>
            </tr>
          </thead>
          <tbody>
            {grid.map(row => (
              <tr key={row.year}>
                <td className="px-1.5 py-0.5 font-semibold text-slate-700">{row.year}</td>
                {row.months.map((val, idx) => (
                  <td key={idx} className="px-0.5 py-0.5 text-center">
                    {val !== null ? (
                      <span className={`inline-block w-full px-0.5 py-0.5 rounded text-[8px] font-mono tabular-nums ${returnColor(val)}`}>
                        {val >= 0 ? '+' : ''}{val.toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-slate-200">-</span>
                    )}
                  </td>
                ))}
                <td className="px-1 py-0.5 text-center">
                  <span className={`inline-block w-full px-0.5 py-0.5 rounded text-[8px] font-mono font-bold tabular-nums ${returnColor(row.ytd)}`}>
                    {row.ytd >= 0 ? '+' : ''}{row.ytd.toFixed(1)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});

// ── Overview Tab ───────────────────────────────────────────────────────────

const OverviewTab = memo(function OverviewTab({
  result,
}: {
  result: BacktestResult;
}) {
  const cm = result.core_metrics;
  return (
    <div className="space-y-2.5 p-3">
      <div className="grid grid-cols-4 gap-1.5">
        {PRIMARY_METRICS.map(def => (
          <MetricCard key={def.key} def={def} value={cm[def.key as keyof CoreMetrics] as number} />
        ))}
      </div>

      {result.equity_curve.length > 0 && (
        <EquityChart equityCurve={result.equity_curve} drawdownCurve={result.drawdown_curve} />
      )}

      {Object.keys(result.monthly_returns).length > 0 && (
        <MonthlyHeatmap monthlyReturns={result.monthly_returns} />
      )}

      <div className="grid grid-cols-4 gap-1.5">
        {SECONDARY_METRICS.map(def => (
          <MetricCard key={def.key} def={def} value={cm[def.key as keyof CoreMetrics] as number} compact />
        ))}
      </div>
    </div>
  );
});

// ── Virtual Trade Log ──────────────────────────────────────────────────────

const TRADE_COLS = ['#', 'Ticker', 'Dir', 'Entry', 'Px Entry', 'Exit', 'Px Exit', 'Return', 'PnL', 'Bars'] as const;
const PAGE_SIZE = 50;

const TradesTab = memo(function TradesTab({
  trades,
}: {
  trades: TradeRecord[];
}) {
  const [sortKey, setSortKey] = useState<keyof TradeRecord>('trade_id');
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => {
    const copy = [...trades];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    return copy;
  }, [trades, sortKey, sortAsc]);

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageData = useMemo(() => sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), [sorted, page]);

  const winners = useMemo(() => trades.filter(t => t.pnl > 0).length, [trades]);
  const losers = trades.length - winners;
  const totalPnl = useMemo(() => trades.reduce((s, t) => s + t.pnl, 0), [trades]);

  const handleSort = useCallback((key: keyof TradeRecord) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(true); }
    setPage(0);
  }, [sortKey, sortAsc]);

  const colMap: Record<string, keyof TradeRecord> = {
    '#': 'trade_id', 'Ticker': 'ticker', 'Dir': 'direction',
    'Entry': 'entry_date', 'Px Entry': 'entry_fill_price',
    'Exit': 'exit_date', 'Px Exit': 'exit_fill_price',
    'Return': 'return_pct', 'PnL': 'pnl', 'Bars': 'holding_bars',
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-3 py-1.5 bg-slate-50/80 border-b border-slate-200/60 text-[10px]">
        <span className="text-slate-600 font-medium">{trades.length} operaciones</span>
        <span className="text-slate-200">|</span>
        <span className="text-emerald-600">{winners} ganadoras</span>
        <span className="text-slate-200">|</span>
        <span className="text-red-500">{losers} perdedoras</span>
        <span className="text-slate-200">|</span>
        <span className={totalPnl >= 0 ? 'text-emerald-600 font-semibold' : 'text-red-500 font-semibold'}>
          PnL: {fmtMoney(totalPnl)}
        </span>
      </div>

      <div ref={containerRef} className="flex-1 overflow-auto">
        <table className="w-full text-[10px]">
          <thead className="sticky top-0 z-10">
            <tr className="bg-slate-50 border-b border-slate-200/60">
              {TRADE_COLS.map(col => (
                <th
                  key={col}
                  onClick={() => handleSort(colMap[col])}
                  className="px-1.5 py-1.5 font-semibold text-slate-600 cursor-pointer hover:bg-slate-100 transition-colors select-none whitespace-nowrap text-right first:text-left [&:nth-child(2)]:text-left [&:nth-child(3)]:text-left [&:nth-child(4)]:text-left [&:nth-child(6)]:text-left"
                >
                  <span className="inline-flex items-center gap-0.5">
                    {col}
                    {sortKey === colMap[col] && (
                      <span className="text-[8px] text-indigo-500">{sortAsc ? '\u25B2' : '\u25BC'}</span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {pageData.map(t => {
              const isWin = t.pnl > 0;
              return (
                <tr key={t.trade_id} className={`transition-colors ${isWin ? 'hover:bg-emerald-50/30' : 'hover:bg-red-50/30'}`}>
                  <td className="px-1.5 py-1 text-slate-400 tabular-nums">{t.trade_id}</td>
                  <td className="px-1.5 py-1 font-semibold text-indigo-600">{t.ticker}</td>
                  <td className="px-1.5 py-1">
                    <span className={`px-1 py-0.5 rounded text-[8px] font-bold ${
                      t.direction === 'long' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
                    }`}>
                      {t.direction === 'long' ? 'LONG' : 'SHORT'}
                    </span>
                  </td>
                  <td className="px-1.5 py-1 text-slate-600 tabular-nums">{fmtDate(t.entry_date)}</td>
                  <td className="px-1.5 py-1 text-right text-slate-700 font-mono tabular-nums">${t.entry_fill_price.toFixed(2)}</td>
                  <td className="px-1.5 py-1 text-slate-600 tabular-nums">{fmtDate(t.exit_date)}</td>
                  <td className="px-1.5 py-1 text-right text-slate-700 font-mono tabular-nums">${t.exit_fill_price.toFixed(2)}</td>
                  <td className={`px-1.5 py-1 text-right font-mono font-semibold tabular-nums ${isWin ? 'text-emerald-600' : 'text-red-500'}`}>
                    {fmtPct(t.return_pct)}
                  </td>
                  <td className={`px-1.5 py-1 text-right font-mono tabular-nums ${isWin ? 'text-emerald-600' : 'text-red-500'}`}>
                    {fmtMoney(t.pnl)}
                  </td>
                  <td className="px-1.5 py-1 text-right text-slate-500 tabular-nums">{t.holding_bars}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-slate-200/60 bg-white">
          <span className="text-[9px] text-slate-400 tabular-nums">
            {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, sorted.length)} de {sorted.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-2 py-0.5 text-[9px] text-slate-500 bg-slate-50 border border-slate-200 rounded hover:bg-slate-100 disabled:opacity-30 transition-colors"
            >
              Anterior
            </button>
            <span className="text-[9px] text-slate-400 tabular-nums px-1">
              {page + 1}/{totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-2 py-0.5 text-[9px] text-slate-500 bg-slate-50 border border-slate-200 rounded hover:bg-slate-100 disabled:opacity-30 transition-colors"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
});

// ── Walk-Forward Section ───────────────────────────────────────────────────

const WalkForwardSection = memo(function WalkForwardSection({
  wf,
}: {
  wf: WalkForwardResult;
}) {
  const maxSharpe = useMemo(() => {
    let mx = 0;
    for (const s of wf.splits) mx = Math.max(mx, Math.abs(s.train_sharpe), Math.abs(s.test_sharpe));
    return mx || 1;
  }, [wf]);

  const overfitColor = wf.overfitting_probability > 0.5
    ? 'text-red-600 bg-red-50'
    : wf.overfitting_probability > 0.3
      ? 'text-amber-600 bg-amber-50'
      : 'text-emerald-600 bg-emerald-50';

  return (
    <div className="rounded-lg border border-slate-200/80 bg-white overflow-hidden">
      <div className="px-2.5 py-1.5 border-b border-slate-100 flex items-center justify-between">
        <span className="text-[10px] font-semibold text-slate-600">Walk-Forward Analysis ({wf.n_splits} splits)</span>
        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${overfitColor}`}>
          P(overfit): {(wf.overfitting_probability * 100).toFixed(0)}%
        </span>
      </div>

      <div className="p-2.5">
        <div className="flex items-center gap-3 mb-2 text-[9px]">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-indigo-400" />
            <span className="text-slate-500">In-Sample</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-blue-300" />
            <span className="text-slate-500">Out-of-Sample</span>
          </div>
        </div>

        <div className="space-y-1">
          {wf.splits.map(split => (
            <div key={split.split_idx} className="flex items-center gap-2 text-[9px]">
              <span className="text-slate-400 w-4 text-right tabular-nums">{split.split_idx + 1}</span>
              <div className="flex-1 flex gap-0.5 h-4">
                <div
                  className="bg-indigo-400 rounded-sm flex items-center justify-center"
                  style={{ width: `${Math.max(2, (Math.abs(split.train_sharpe) / maxSharpe) * 100)}%` }}
                  title={`IS Sharpe: ${split.train_sharpe.toFixed(2)}`}
                >
                  <span className="text-[7px] text-white font-bold tabular-nums">{split.train_sharpe.toFixed(2)}</span>
                </div>
                <div
                  className="bg-blue-300 rounded-sm flex items-center justify-center"
                  style={{ width: `${Math.max(2, (Math.abs(split.test_sharpe) / maxSharpe) * 100)}%` }}
                  title={`OOS Sharpe: ${split.test_sharpe.toFixed(2)}`}
                >
                  <span className="text-[7px] text-white font-bold tabular-nums">{split.test_sharpe.toFixed(2)}</span>
                </div>
              </div>
              <span className={`w-10 text-right tabular-nums font-medium ${
                split.degradation_pct < -30 ? 'text-red-500' : split.degradation_pct < 0 ? 'text-amber-600' : 'text-emerald-600'
              }`}>
                {split.degradation_pct >= 0 ? '+' : ''}{split.degradation_pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>

        <div className="mt-2 pt-2 border-t border-slate-100 grid grid-cols-3 gap-2 text-[9px]">
          <div>
            <span className="text-slate-400 block">Avg IS Sharpe</span>
            <span className="font-bold text-slate-700 tabular-nums">{wf.mean_train_sharpe.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-400 block">Avg OOS Sharpe</span>
            <span className="font-bold text-slate-700 tabular-nums">{wf.mean_test_sharpe.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-400 block">Avg Degradation</span>
            <span className={`font-bold tabular-nums ${wf.mean_degradation_pct < -30 ? 'text-red-500' : 'text-slate-700'}`}>
              {wf.mean_degradation_pct.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
});

// ── Monte Carlo Section ────────────────────────────────────────────────────

const MonteCarloSection = memo(function MonteCarloSection({
  mc,
  initialCapital,
}: {
  mc: MonteCarloResult;
  initialCapital: number;
}) {
  const profitColor = mc.prob_profit >= 0.7
    ? 'text-emerald-600 bg-emerald-50'
    : mc.prob_profit >= 0.5
      ? 'text-amber-600 bg-amber-50'
      : 'text-red-600 bg-red-50';

  return (
    <div className="rounded-lg border border-slate-200/80 bg-white overflow-hidden">
      <div className="px-2.5 py-1.5 border-b border-slate-100 flex items-center justify-between">
        <span className="text-[10px] font-semibold text-slate-600">Monte Carlo ({mc.n_simulations.toLocaleString()} sims)</span>
        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${profitColor}`}>
          P(profit): {(mc.prob_profit * 100).toFixed(0)}%
        </span>
      </div>

      <div className="p-2.5">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[9px]">
          <StatRow label="Median Final Equity" value={fmtMoney(mc.median_final_equity)} />
          <StatRow label="Mean Final Equity" value={fmtMoney(mc.mean_final_equity)} />
          <StatRow label="5th Percentile" value={fmtMoney(mc.percentile_5_equity)} warn={mc.percentile_5_equity < initialCapital} />
          <StatRow label="95th Percentile" value={fmtMoney(mc.percentile_95_equity)} good />
          <StatRow label="25th Percentile" value={fmtMoney(mc.percentile_25_equity)} />
          <StatRow label="75th Percentile" value={fmtMoney(mc.percentile_75_equity)} />
          <StatRow label="Mean Max DD" value={fmtPctRaw(mc.mean_max_drawdown_pct)} warn={mc.mean_max_drawdown_pct < -25} />
          <StatRow label="Worst Max DD" value={fmtPctRaw(mc.worst_max_drawdown_pct)} warn={mc.worst_max_drawdown_pct < -40} />
        </div>
      </div>
    </div>
  );
});

function StatRow({ label, value, good, warn }: { label: string; value: string; good?: boolean; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={`font-bold tabular-nums ${warn ? 'text-red-500' : good ? 'text-emerald-600' : 'text-slate-700'}`}>
        {value}
      </span>
    </div>
  );
}

// ── Advanced Metrics Section ───────────────────────────────────────────────

const AdvancedMetricsSection = memo(function AdvancedMetricsSection({
  am,
}: {
  am: AdvancedMetrics;
}) {
  const dsrColor = am.deflated_sharpe_ratio > 1.0
    ? 'text-emerald-600'
    : am.deflated_sharpe_ratio > 0.5
      ? 'text-amber-600'
      : 'text-red-500';

  const psrColor = am.probabilistic_sharpe_ratio > 0.95
    ? 'text-emerald-600'
    : am.probabilistic_sharpe_ratio > 0.8
      ? 'text-amber-600'
      : 'text-red-500';

  return (
    <div className="rounded-lg border border-slate-200/80 bg-white overflow-hidden">
      <div className="px-2.5 py-1.5 border-b border-slate-100">
        <span className="text-[10px] font-semibold text-slate-600">Statistical Robustness (Lopez de Prado)</span>
      </div>
      <div className="p-2.5 grid grid-cols-3 gap-2">
        <div className="text-center">
          <span className="text-[9px] text-slate-400 block">Deflated Sharpe</span>
          <span className={`text-[14px] font-bold tabular-nums ${dsrColor}`}>{am.deflated_sharpe_ratio.toFixed(2)}</span>
        </div>
        <div className="text-center">
          <span className="text-[9px] text-slate-400 block">Prob. Sharpe</span>
          <span className={`text-[14px] font-bold tabular-nums ${psrColor}`}>{(am.probabilistic_sharpe_ratio * 100).toFixed(1)}%</span>
        </div>
        <div className="text-center">
          <span className="text-[9px] text-slate-400 block">Min Track Record</span>
          <span className="text-[14px] font-bold tabular-nums text-slate-700">{am.min_track_record_length} meses</span>
        </div>
        <div className="text-center">
          <span className="text-[9px] text-slate-400 block">Skewness</span>
          <span className={`text-[11px] font-bold tabular-nums ${am.skewness > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
            {am.skewness.toFixed(3)}
          </span>
        </div>
        <div className="text-center">
          <span className="text-[9px] text-slate-400 block">Kurtosis</span>
          <span className={`text-[11px] font-bold tabular-nums ${am.kurtosis > 3 ? 'text-amber-600' : 'text-slate-700'}`}>
            {am.kurtosis.toFixed(3)}
          </span>
        </div>
      </div>
    </div>
  );
});

// ── Analysis Tab ───────────────────────────────────────────────────────────

const AnalysisTab = memo(function AnalysisTab({
  result,
}: {
  result: BacktestResult;
}) {
  return (
    <div className="space-y-2.5 p-3">
      {result.advanced_metrics && (
        <AdvancedMetricsSection am={result.advanced_metrics} />
      )}
      {result.walk_forward && (
        <WalkForwardSection wf={result.walk_forward} />
      )}
      {result.monte_carlo && (
        <MonteCarloSection mc={result.monte_carlo} initialCapital={result.strategy.initial_capital} />
      )}
      {!result.advanced_metrics && !result.walk_forward && !result.monte_carlo && (
        <div className="text-center py-8 text-[11px] text-slate-400">
          No hay datos de analisis avanzado disponibles para este backtest.
        </div>
      )}
    </div>
  );
});

// ── Warnings Bar ───────────────────────────────────────────────────────────

const WarningsBar = memo(function WarningsBar({ warnings }: { warnings: string[] }) {
  const [expanded, setExpanded] = useState(false);
  if (warnings.length === 0) return null;

  return (
    <div className="px-3 py-1.5 bg-amber-50/80 border-t border-amber-200/60">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-[9px] text-amber-700 font-medium hover:text-amber-800 transition-colors"
      >
        {warnings.length} advertencia{warnings.length > 1 ? 's' : ''} {expanded ? '(ocultar)' : '(ver)'}
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <ul className="mt-1 space-y-0.5">
              {warnings.map((w, i) => (
                <li key={i} className="text-[9px] text-amber-600 pl-2 border-l-2 border-amber-300">{w}</li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

// ── Main Panel ─────────────────────────────────────────────────────────────

interface BacktestResultsPanelProps {
  result: BacktestResult;
}

export const BacktestResultsPanel = memo(function BacktestResultsPanel({
  result,
}: BacktestResultsPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-lg border border-slate-200/80 bg-[#f7f8fb] overflow-hidden"
    >
      <StrategyHeader result={result} />
      <TabBar active={activeTab} onChange={setActiveTab} tradeCount={result.trades.length} />

      <div className="max-h-[600px] overflow-y-auto">
        {activeTab === 'overview' && <OverviewTab result={result} />}
        {activeTab === 'trades' && <TradesTab trades={result.trades} />}
        {activeTab === 'analysis' && <AnalysisTab result={result} />}
      </div>

      <WarningsBar warnings={result.warnings} />
    </motion.div>
  );
});
