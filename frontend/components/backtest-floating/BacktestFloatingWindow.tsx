'use client';

import { useState, useCallback, useMemo, memo } from 'react';
import dynamic from 'next/dynamic';
import { useBacktestFloating } from '@/contexts/BacktestFloatingContext';
import {
  Play, RotateCcw, AlertCircle, Loader2, Plus, Trash2,
  ChevronDown, ChevronRight, Search, X,
} from 'lucide-react';
import type {
  StrategyConfig, Signal, ExitRule, Timeframe, SignalOperator,
  ExitType, SlippageModel, BacktestResult, TradeRecord,
  DailyStats, OptimizationBreakdown,
} from '@/components/ai-agent/backtest/BacktestTypes';
import { ALERT_CATALOG, getAlertsByCategory } from '@/lib/alert-catalog';
import type { AlertDefinition } from '@/lib/alert-catalog';

const LazyPlot = dynamic(() => import('react-plotly.js'), {
  ssr: false,
  loading: () => <div className="h-[200px] bg-surface-hover rounded animate-pulse" />,
});

// ── Constants ──────────────────────────────────────────────────────────────

const INDICATORS: { value: string; label: string; group: string }[] = [
  { value: 'close', label: 'Close', group: 'Price' },
  { value: 'open', label: 'Open', group: 'Price' },
  { value: 'high', label: 'High', group: 'Price' },
  { value: 'low', label: 'Low', group: 'Price' },
  { value: 'volume', label: 'Volume', group: 'Price' },
  { value: 'prev_close', label: 'Prev Close', group: 'Price' },
  { value: 'gap_pct', label: 'Gap %', group: 'Derived' },
  { value: 'rvol', label: 'Relative Volume', group: 'Derived' },
  { value: 'range_pct', label: 'Range %', group: 'Derived' },
  { value: 'change_pct', label: 'Change %', group: 'Derived' },
  { value: 'change_from_open', label: 'Chg from Open', group: 'Derived' },
  { value: 'dollar_volume', label: 'Dollar Volume', group: 'Derived' },
  { value: 'dist_from_vwap', label: 'Dist VWAP %', group: 'Derived' },
  { value: 'pos_in_range', label: 'Pos in Range', group: 'Derived' },
  { value: 'rsi_14', label: 'RSI (14)', group: 'Technical' },
  { value: 'sma_5', label: 'SMA 5', group: 'Moving Avg' },
  { value: 'sma_8', label: 'SMA 8', group: 'Moving Avg' },
  { value: 'sma_20', label: 'SMA 20', group: 'Moving Avg' },
  { value: 'sma_50', label: 'SMA 50', group: 'Moving Avg' },
  { value: 'sma_200', label: 'SMA 200', group: 'Moving Avg' },
  { value: 'ema_9', label: 'EMA 9', group: 'Moving Avg' },
  { value: 'ema_20', label: 'EMA 20', group: 'Moving Avg' },
  { value: 'ema_21', label: 'EMA 21', group: 'Moving Avg' },
  { value: 'ema_50', label: 'EMA 50', group: 'Moving Avg' },
  { value: 'macd_line', label: 'MACD Line', group: 'MACD' },
  { value: 'macd_signal', label: 'MACD Signal', group: 'MACD' },
  { value: 'macd_hist', label: 'MACD Hist', group: 'MACD' },
  { value: 'stoch_k', label: 'Stoch %K', group: 'Stochastic' },
  { value: 'stoch_d', label: 'Stoch %D', group: 'Stochastic' },
  { value: 'bb_upper', label: 'BB Upper', group: 'Bollinger' },
  { value: 'bb_middle', label: 'BB Middle', group: 'Bollinger' },
  { value: 'bb_lower', label: 'BB Lower', group: 'Bollinger' },
  { value: 'bb_width', label: 'BB Width', group: 'Bollinger' },
  { value: 'bb_pct_b', label: 'BB %B', group: 'Bollinger' },
  { value: 'adx_14', label: 'ADX (14)', group: 'Trend' },
  { value: 'plus_di', label: '+DI', group: 'Trend' },
  { value: 'minus_di', label: '-DI', group: 'Trend' },
  { value: 'atr_14', label: 'ATR (14)', group: 'Volatility' },
  { value: 'true_atr_14', label: 'True ATR (14)', group: 'Volatility' },
  { value: 'atr_pct', label: 'ATR %', group: 'Volatility' },
  { value: 'vwap', label: 'VWAP', group: 'Volume' },
  { value: 'high_20d', label: '20D High', group: 'Range' },
  { value: 'low_20d', label: '20D Low', group: 'Range' },
  { value: 'high_52w', label: '52W High', group: 'Range' },
  { value: 'low_52w', label: '52W Low', group: 'Range' },
  { value: 'avg_volume_5d', label: 'Avg Vol 5D', group: 'Volume' },
  { value: 'avg_volume_10d', label: 'Avg Vol 10D', group: 'Volume' },
  { value: 'avg_volume_20d', label: 'Avg Vol 20D', group: 'Volume' },
];

const FILTER_DEFS: { key: string; label: string; suffix: string; group: string }[] = [
  { key: 'price', label: 'Price', suffix: '$', group: 'Price' },
  { key: 'volume', label: 'Volume', suffix: '', group: 'Volume' },
  { key: 'rvol', label: 'RVOL', suffix: 'x', group: 'Volume' },
  { key: 'dollar_volume', label: '$ Volume', suffix: '$', group: 'Volume' },
  { key: 'change_percent', label: 'Change %', suffix: '%', group: 'Change' },
  { key: 'gap_percent', label: 'Gap %', suffix: '%', group: 'Change' },
  { key: 'change_from_open', label: 'From Open', suffix: '%', group: 'Change' },
  { key: 'rsi', label: 'RSI', suffix: '', group: 'Technical' },
  { key: 'atr_percent', label: 'ATR %', suffix: '%', group: 'Technical' },
  { key: 'adx_14', label: 'ADX', suffix: '', group: 'Technical' },
  { key: 'stoch_k', label: 'Stoch %K', suffix: '', group: 'Technical' },
  { key: 'macd_line', label: 'MACD', suffix: '', group: 'Technical' },
  { key: 'bb_upper', label: 'BB Upper', suffix: '$', group: 'Bollinger' },
  { key: 'bb_lower', label: 'BB Lower', suffix: '$', group: 'Bollinger' },
  { key: 'dist_from_vwap', label: 'Dist VWAP', suffix: '%', group: 'Distance' },
  { key: 'pos_in_range', label: 'Pos Range', suffix: '%', group: 'Position' },
  { key: 'below_high', label: 'Below High', suffix: '%', group: 'Position' },
  { key: 'above_low', label: 'Above Low', suffix: '%', group: 'Position' },
  { key: 'avg_volume_5d', label: 'Avg Vol 5D', suffix: '', group: 'Avg Volume' },
  { key: 'avg_volume_10d', label: 'Avg Vol 10D', suffix: '', group: 'Avg Volume' },
  { key: 'avg_volume_20d', label: 'Avg Vol 20D', suffix: '', group: 'Avg Volume' },
];

const OPERATORS: { value: SignalOperator; label: string }[] = [
  { value: '>', label: '>' }, { value: '>=', label: '>=' },
  { value: '<', label: '<' }, { value: '<=', label: '<=' },
  { value: '==', label: '==' },
  { value: 'crosses_above', label: 'X Above' },
  { value: 'crosses_below', label: 'X Below' },
];

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1d', label: 'Daily' }, { value: '1h', label: '1H' },
  { value: '30min', label: '30m' }, { value: '15min', label: '15m' },
  { value: '5min', label: '5m' }, { value: '1min', label: '1m' },
];

const EXIT_TYPES: { value: ExitType; label: string; hint: string }[] = [
  { value: 'stop_loss', label: 'Stop Loss', hint: '% from entry' },
  { value: 'target', label: 'Take Profit', hint: '% from entry' },
  { value: 'trailing_stop', label: 'Trailing Stop', hint: '% from peak' },
  { value: 'time', label: 'Time Exit', hint: 'bars' },
  { value: 'eod', label: 'End of Day', hint: '' },
];

const SLIPPAGE_MODELS: { value: SlippageModel; label: string }[] = [
  { value: 'fixed_bps', label: 'Fixed BPS' },
  { value: 'volume_based', label: 'Vol-Based' },
  { value: 'spread_based', label: 'Spread' },
];

// ── Helpers ────────────────────────────────────────────────────────────────

function todayStr(): string { return new Date().toISOString().slice(0, 10); }
function oneYearAgoStr(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
}
const defaultSignal = (): Signal => ({ indicator: 'rsi_14', operator: '<', value: 30 });
const defaultExit = (): ExitRule => ({ type: 'stop_loss', value: 0.05 });

function fmtPct(v: number | null | undefined, d = 1): string { const n = v ?? 0; return `${n >= 0 ? '+' : ''}${(n * 100).toFixed(d)}%`; }
function fmtPctRaw(v: number | null | undefined, d = 1): string { const n = v ?? 0; return `${n >= 0 ? '+' : ''}${n.toFixed(d)}%`; }
function fmtMoney(v: number | null | undefined): string {
  const n = v ?? 0;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}
function fmtNum(v: number | null | undefined, d = 2): string { return (v ?? 0).toFixed(d); }
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: '2-digit' });
}

// ── Shared UI ──────────────────────────────────────────────────────────────

function Lbl({ children }: { children: React.ReactNode }) {
  return <span className="text-[9px] font-medium text-muted-fg uppercase tracking-wider">{children}</span>;
}

function Sel({ value, onChange, options, className = '' }: {
  value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; className?: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className={`px-1.5 py-[3px] text-[10px] border border-border rounded bg-surface text-foreground focus:ring-1 focus:ring-primary focus:border-primary outline-none ${className}`}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function Inp({ value, onChange, type = 'text', placeholder, className = '', ...rest }: {
  value: string | number; onChange: (v: string) => void; type?: string;
  placeholder?: string; className?: string;[k: string]: any;
}) {
  return (
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`px-1.5 py-[3px] text-[10px] border border-border rounded bg-surface text-foreground focus:ring-1 focus:ring-primary focus:border-primary outline-none ${className}`}
      {...rest} />
  );
}

function ConfigTab({ active, onClick, children, badge }: {
  active: boolean; onClick: () => void; children: React.ReactNode; badge?: string | number;
}) {
  return (
    <button type="button" onClick={onClick}
      className={`relative px-3 py-1.5 text-[10px] font-medium transition-colors whitespace-nowrap ${active ? 'text-primary' : 'text-muted-fg hover:text-foreground'
        }`}>
      {children}
      {badge !== undefined && badge !== '' && badge !== 0 && (
        <span className="ml-1 text-[8px] text-primary font-bold">{badge}</span>
      )}
      {active && <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary" />}
    </button>
  );
}

// ── Signal & Exit Row ──────────────────────────────────────────────────────

function SignalRow({ signal, onChange, onRemove }: {
  signal: Signal; onChange: (s: Signal) => void; onRemove: () => void;
}) {
  const isCross = signal.operator === 'crosses_above' || signal.operator === 'crosses_below';
  const isInd = INDICATORS.some((i) => i.value === String(signal.value));
  return (
    <div className="flex items-center gap-1 py-0.5">
      <Sel value={signal.indicator} onChange={(v) => onChange({ ...signal, indicator: v })} options={INDICATORS} className="w-[90px]" />
      <Sel value={signal.operator} onChange={(v) => onChange({ ...signal, operator: v as SignalOperator })} options={OPERATORS} className="w-[72px]" />
      {isCross || isInd ? (
        <Sel value={String(signal.value)} onChange={(v) => onChange({ ...signal, value: v })} options={INDICATORS} className="w-[90px]" />
      ) : (
        <Inp type="number" value={signal.value} onChange={(v) => onChange({ ...signal, value: parseFloat(v) || 0 })} className="w-[60px]" step="any" />
      )}
      <button type="button" onClick={onRemove} className="p-0.5 text-muted-fg hover:text-red-500"><Trash2 className="w-2.5 h-2.5" /></button>
    </div>
  );
}

function ExitRow({ rule, onChange, onRemove }: {
  rule: ExitRule; onChange: (r: ExitRule) => void; onRemove: () => void;
}) {
  const meta = EXIT_TYPES.find((e) => e.value === rule.type);
  const needsVal = rule.type !== 'eod';
  return (
    <div className="flex items-center gap-1 py-0.5">
      <Sel value={rule.type} onChange={(v) => onChange({ ...rule, type: v as ExitType, value: v === 'eod' ? null : (rule.value ?? 0.05) })}
        options={EXIT_TYPES.map((e) => ({ value: e.value, label: e.label }))} className="w-[100px]" />
      {needsVal && (
        <>
          <Inp type="number" value={rule.value ?? 0} onChange={(v) => onChange({ ...rule, value: parseFloat(v) || 0 })} className="w-[55px]" step="any" />
          {meta?.hint && <span className="text-[8px] text-muted-fg">{meta.hint}</span>}
        </>
      )}
      <button type="button" onClick={onRemove} className="p-0.5 text-muted-fg hover:text-red-500 ml-auto"><Trash2 className="w-2.5 h-2.5" /></button>
    </div>
  );
}

function ResultTabBtn({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick}
      className={`relative px-2.5 py-1.5 text-[9px] font-medium transition-colors whitespace-nowrap ${active ? 'text-primary' : 'text-muted-fg hover:text-foreground/80'
        }`}>
      {children}
      {active && <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary" />}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// RESULTS COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════

// ── Summary Tab ────────────────────────────────────────────────────────────

type Quality = 'excellent' | 'good' | 'fair' | 'poor';

function metricQ(key: string, val: number): Quality {
  const r: Record<string, [number, number, number]> = {
    sharpe_ratio: [1.5, 1.0, 0.5], sortino_ratio: [2.0, 1.3, 0.7],
    calmar_ratio: [2.0, 1.0, 0.5], win_rate: [0.6, 0.5, 0.4],
    profit_factor: [2.0, 1.5, 1.0], recovery_factor: [3.0, 1.5, 0.8],
    total_return_pct: [50, 20, 5], annualized_return_pct: [30, 15, 5],
  };
  const t = r[key]; if (!t) return 'fair';
  if (val >= t[0]) return 'excellent'; if (val >= t[1]) return 'good';
  if (val >= t[2]) return 'fair'; return 'poor';
}

function qCol(q: Quality): string {
  return q === 'excellent' ? 'text-emerald-600' : q === 'good' ? 'text-emerald-500' : q === 'fair' ? 'text-foreground' : 'text-red-500';
}
function qBorder(q: Quality): string {
  return q === 'excellent' ? 'border-emerald-500/30' : q === 'good' ? 'border-emerald-500/20' : q === 'fair' ? 'border-border/80' : 'border-red-500/30';
}

function dayColor(pnl: number): string {
  if (pnl > 200) return 'bg-emerald-600 text-white';
  if (pnl > 50) return 'bg-emerald-400 text-white';
  if (pnl > 0) return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400';
  if (pnl === 0) return 'bg-surface text-muted-fg';
  if (pnl > -50) return 'bg-red-500/15 text-red-700 dark:text-red-400';
  if (pnl > -200) return 'bg-red-400 text-white';
  return 'bg-red-600 text-white';
}

const SummaryTab = memo(function SummaryTab({ result }: { result: BacktestResult }) {
  const cm = result.core_metrics;
  const metrics = [
    { key: 'profit_factor', label: 'Profit Factor', val: cm.profit_factor, fmt: fmtNum(cm.profit_factor) },
    { key: 'total_trades', label: 'Total Trades', val: cm.total_trades, fmt: `${cm.total_trades} (${fmtPct(cm.win_rate)} winners)` },
    { key: 'win_rate', label: 'Win Rate', val: cm.win_rate, fmt: fmtPct(cm.win_rate) },
    { key: 'avg_winner_pct', label: 'Avg Winner/Loser', val: cm.avg_winner_pct, fmt: `${fmtPct(cm.avg_winner_pct)} / ${fmtPct(cm.avg_loser_pct)}` },
    { key: 'total_return_pct', label: 'Strategy Return', val: cm.total_return_pct, fmt: fmtPctRaw(cm.total_return_pct) },
    { key: 'annualized_return_pct', label: 'Proj. Annual Return', val: cm.annualized_return_pct, fmt: fmtPctRaw(cm.annualized_return_pct) },
    { key: 'max_drawdown_pct', label: 'Max Drawdown', val: cm.max_drawdown_pct, fmt: fmtPctRaw(cm.max_drawdown_pct), invert: true },
    { key: 'sharpe_ratio', label: 'Sharpe Ratio', val: cm.sharpe_ratio, fmt: fmtNum(cm.sharpe_ratio) },
    { key: 'sortino_ratio', label: 'Sortino Ratio', val: cm.sortino_ratio, fmt: fmtNum(cm.sortino_ratio) },
    { key: 'calmar_ratio', label: 'Calmar Ratio', val: cm.calmar_ratio, fmt: fmtNum(cm.calmar_ratio) },
    { key: 'recovery_factor', label: 'Recovery Factor', val: cm.recovery_factor, fmt: fmtNum(cm.recovery_factor) },
    { key: 'expectancy', label: 'Expectancy', val: cm.expectancy, fmt: fmtMoney(cm.expectancy) },
  ];

  return (
    <div className="space-y-2 p-2">
      {/* Metrics grid */}
      <div className="rounded border border-border bg-surface overflow-hidden">
        <table className="w-full text-[9px]">
          <tbody>
            {metrics.map(m => {
              const q = m.invert ? metricQ(m.key, -Math.abs(m.val)) : metricQ(m.key, m.val);
              const isNeg = m.val < 0;
              return (
                <tr key={m.key} className="border-b border-border-subtle last:border-0">
                  <td className="px-2 py-1 text-foreground/80 font-medium">{m.label}</td>
                  <td className={`px-2 py-1 text-right font-bold tabular-nums ${m.invert ? (isNeg ? 'text-red-500' : 'text-emerald-600') : qCol(q)
                    }`}>{m.fmt}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-1 text-[8px]">
        {[
          ['Capital', fmtMoney(result.strategy.initial_capital)],
          ['Slippage', `${result.strategy.slippage_bps}bps`],
          ['Win Streak', `${result.most_winning_days_in_row ?? 0}d`],
          ['Lose Streak', `${result.most_losing_days_in_row ?? 0}d`],
        ].map(([l, v]) => (
          <div key={l} className="bg-surface-hover rounded px-1.5 py-1 text-center">
            <span className="text-muted-fg block">{l}</span>
            <span className="font-bold text-foreground">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
});

// ── Equity Curve Tab ───────────────────────────────────────────────────────

const EquityCurveTab = memo(function EquityCurveTab({ result }: { result: BacktestResult }) {
  const ds = result.daily_stats ?? [];
  const grossEq = ds.map(d => d.gross_equity);
  const netEq = ds.map(d => d.net_equity);
  const dates = ds.map(d => d.date);
  const hasGrossNet = grossEq.length > 0 && grossEq.some((v, i) => v !== netEq[i]);

  const eqDates = result.equity_curve.map(p => p[0]);
  const eqVals = result.equity_curve.map(p => p[1]);

  return (
    <div className="p-2 space-y-2">
      <div className="rounded border border-border bg-surface overflow-hidden">
        <div className="px-2 py-1 border-b border-border-subtle text-[9px] font-semibold text-foreground/80">Equity Curve</div>
        <div className="h-[220px]">
          <LazyPlot
            data={[
              { x: eqDates, y: eqVals, type: 'scatter' as const, mode: 'lines' as const, name: 'Net Equity', line: { color: '#16a34a', width: 1.5 } },
              ...(hasGrossNet ? [{
                x: dates, y: grossEq, type: 'scatter' as const, mode: 'lines' as const, name: 'Gross Equity', line: { color: 'var(--color-fg)', width: 1.5 },
              }] : []),
            ] as any}
            layout={{
              margin: { t: 4, r: 8, b: 24, l: 48 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
              font: { size: 8, color: 'var(--color-muted-fg)' }, showlegend: hasGrossNet,
              legend: { x: 0.02, y: 0.98, font: { size: 8 }, bgcolor: 'rgba(255,255,255,0.8)' },
              xaxis: { showgrid: false, tickfont: { size: 7 }, type: 'date' as const },
              yaxis: { title: { text: 'Equity ($)', font: { size: 8 } }, gridcolor: 'var(--color-border-subtle)', tickfont: { size: 7 } },
              hovermode: 'x unified' as const,
            } as any}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }} useResizeHandler />
        </div>
      </div>
    </div>
  );
});

// ── Daily PnL Tab ──────────────────────────────────────────────────────────

const DailyTab = memo(function DailyTab({ result }: { result: BacktestResult }) {
  const ds = (result.daily_stats ?? []).filter(d => d.trades_count > 0);
  const dates = ds.map(d => d.date);
  const pnls = ds.map(d => d.pnl);
  const colors = pnls.map(p => p >= 0 ? '#16a34a' : '#ef4444');
  const tradeCounts = ds.map(d => d.trades_count);

  return (
    <div className="p-2 space-y-2">
      <div className="rounded border border-border bg-surface overflow-hidden">
        <div className="px-2 py-1 border-b border-border-subtle text-[9px] font-semibold text-foreground/80">Profit per Day</div>
        <div className="h-[160px]">
          <LazyPlot
            data={[{ x: dates, y: pnls, type: 'bar' as const, marker: { color: colors } }] as any}
            layout={{
              margin: { t: 4, r: 8, b: 24, l: 48 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
              font: { size: 8, color: 'var(--color-muted-fg)' }, showlegend: false,
              xaxis: { showgrid: false, tickfont: { size: 7 }, type: 'date' as const },
              yaxis: {
                title: { text: 'Profit ($)', font: { size: 8 } }, gridcolor: 'var(--color-border-subtle)', tickfont: { size: 7 },
                zeroline: true, zerolinecolor: '#ef4444', zerolinewidth: 1
              },
              hovermode: 'x unified' as const,
            } as any}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }} useResizeHandler />
        </div>
      </div>
      <div className="rounded border border-border bg-surface overflow-hidden">
        <div className="px-2 py-1 border-b border-border-subtle text-[9px] font-semibold text-foreground/80">Trades per Day</div>
        <div className="h-[120px]">
          <LazyPlot
            data={[{ x: dates, y: tradeCounts, type: 'bar' as const, marker: { color: '#3b82f6' } }] as any}
            layout={{
              margin: { t: 4, r: 8, b: 24, l: 48 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
              font: { size: 8, color: 'var(--color-muted-fg)' }, showlegend: false,
              xaxis: { showgrid: false, tickfont: { size: 7 }, type: 'date' as const },
              yaxis: { title: { text: 'Trades', font: { size: 8 } }, gridcolor: 'var(--color-border-subtle)', tickfont: { size: 7 } },
            } as any}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }} useResizeHandler />
        </div>
      </div>
    </div>
  );
});

// ── Drawdown Tab ───────────────────────────────────────────────────────────

const DrawdownTab = memo(function DrawdownTab({ result }: { result: BacktestResult }) {
  const dates = result.drawdown_curve.map(p => p[0]);
  const dd = result.drawdown_curve.map(p => p[1] * 100);
  return (
    <div className="p-2">
      <div className="rounded border border-border bg-surface overflow-hidden">
        <div className="px-2 py-1 border-b border-border-subtle text-[9px] font-semibold text-foreground/80">Drawdown (%)</div>
        <div className="h-[240px]">
          <LazyPlot
            data={[{
              x: dates, y: dd, type: 'scatter' as const, mode: 'lines' as const, fill: 'tozeroy' as const,
              line: { color: '#ef4444', width: 1 }, fillcolor: 'rgba(239,68,68,0.15)',
            }] as any}
            layout={{
              margin: { t: 4, r: 8, b: 24, l: 48 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
              font: { size: 8, color: 'var(--color-muted-fg)' }, showlegend: false,
              xaxis: { showgrid: false, tickfont: { size: 7 }, type: 'date' as const },
              yaxis: {
                title: { text: 'DD (%)', font: { size: 8 } }, gridcolor: 'var(--color-border-subtle)', tickfont: { size: 7 },
                zeroline: true, zerolinecolor: '#ef4444', zerolinewidth: 1
              },
            } as any}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }} useResizeHandler />
        </div>
      </div>
    </div>
  );
});

// ── Calendar Tab ───────────────────────────────────────────────────────────

const CalendarTab = memo(function CalendarTab({ result }: { result: BacktestResult }) {
  const ds = result.daily_stats ?? [];
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const dayMap = useMemo(() => new Map(ds.map(d => [d.date, d])), [ds]);
  const tradingDays = useMemo(() => ds.filter(d => d.trades_count > 0), [ds]);

  const months = useMemo(() => {
    if (tradingDays.length === 0) return [];
    const first = new Date(tradingDays[0].date);
    const last = new Date(tradingDays[tradingDays.length - 1].date);
    const result: { year: number; month: number; label: string }[] = [];
    const cur = new Date(first.getFullYear(), first.getMonth(), 1);
    while (cur <= last) {
      result.push({
        year: cur.getFullYear(), month: cur.getMonth(),
        label: cur.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }),
      });
      cur.setMonth(cur.getMonth() + 1);
    }
    return result;
  }, [tradingDays]);

  const dayTrades = useMemo(() => {
    if (!selectedDay) return [];
    return result.trades.filter(t => String(t.exit_date).slice(0, 10) === selectedDay);
  }, [selectedDay, result.trades]);

  return (
    <div className="p-2 space-y-2 text-[9px]">
      <div className="max-h-[350px] overflow-auto space-y-2">
        {months.map(m => {
          const firstDay = new Date(m.year, m.month, 1);
          const daysInMonth = new Date(m.year, m.month + 1, 0).getDate();
          const startDow = firstDay.getDay();
          return (
            <div key={m.label} className="rounded border border-border bg-surface overflow-hidden">
              <div className="px-2 py-1 bg-surface-hover border-b border-border-subtle font-semibold text-foreground/80 text-center">{m.label}</div>
              <div className="grid grid-cols-7 text-center">
                {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                  <div key={i} className="py-0.5 font-bold text-muted-fg border-b border-border-subtle text-[7px]">{d}</div>
                ))}
                {Array.from({ length: startDow }).map((_, i) => <div key={`p-${i}`} />)}
                {Array.from({ length: daysInMonth }).map((_, i) => {
                  const day = i + 1;
                  const dateStr = `${m.year}-${String(m.month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                  const stat = dayMap.get(dateStr);
                  const hasTrades = stat && stat.trades_count > 0;
                  return (
                    <div key={day}
                      onClick={() => hasTrades && setSelectedDay(dateStr === selectedDay ? null : dateStr)}
                      className={`py-1 px-0.5 cursor-pointer transition-colors ${hasTrades ? dayColor(stat.pnl) : 'bg-surface text-muted-fg/50'
                        } ${dateStr === selectedDay ? 'ring-2 ring-primary ring-inset' : ''}`}
                      title={hasTrades ? `WR: ${(stat.win_rate * 100).toFixed(0)}% (${stat.winners}/${stat.trades_count})\nPnL: $${stat.pnl.toFixed(0)}\nAvg: $${stat.avg_gain.toFixed(0)}` : ''}>
                      <div className="font-bold">{day}</div>
                      {hasTrades && (
                        <div className="text-[6px] leading-tight mt-0.5">
                          <div>WR: {(stat.win_rate * 100).toFixed(0)}%</div>
                          <div>${stat.pnl.toFixed(0)}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Trade detail for selected day */}
      {selectedDay && dayTrades.length > 0 && (
        <div className="rounded border border-border bg-surface overflow-hidden">
          <div className="px-2 py-1 bg-surface-hover border-b border-border-subtle font-semibold text-foreground/80">
            Trades on {selectedDay} ({dayTrades.length})
          </div>
          <div className="max-h-[150px] overflow-auto">
            <table className="w-full text-[8px]">
              <thead><tr className="bg-surface-hover">
                <th className="px-1 py-0.5 text-left">Symbol</th>
                <th className="px-1 py-0.5 text-left">Dir</th>
                <th className="px-1 py-0.5 text-right">Entry Px</th>
                <th className="px-1 py-0.5 text-right">Exit Px</th>
                <th className="px-1 py-0.5 text-right">Shares</th>
                <th className="px-1 py-0.5 text-right">Gross P/L</th>
              </tr></thead>
              <tbody>
                {dayTrades.map(t => (
                  <tr key={t.trade_id} className={t.pnl >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10'}>
                    <td className="px-1 py-0.5 font-bold text-primary">{t.ticker}</td>
                    <td className="px-1 py-0.5">{t.direction === 'long' ? '↑L' : '↓S'}</td>
                    <td className="px-1 py-0.5 text-right tabular-nums">${t.entry_fill_price.toFixed(2)}</td>
                    <td className="px-1 py-0.5 text-right tabular-nums">${t.exit_fill_price.toFixed(2)}</td>
                    <td className="px-1 py-0.5 text-right tabular-nums">{t.shares.toFixed(0)}</td>
                    <td className={`px-1 py-0.5 text-right font-bold tabular-nums ${t.pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                      {fmtMoney(t.pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
});

// ── Optimization Tab ───────────────────────────────────────────────────────

const OptimizationTab = memo(function OptimizationTab({ result }: { result: BacktestResult }) {
  const opt = result.optimization ?? {};
  const filterKeys = Object.keys(opt);
  const [activeFilter, setActiveFilter] = useState(filterKeys[0] ?? 'price');
  const [metric, setMetric] = useState<'profit_factor' | 'win_rate' | 'avg_gain' | 'total_gain' | 'trades'>('profit_factor');

  const breakdown = opt[activeFilter];
  if (!breakdown || breakdown.buckets.length === 0) {
    return <div className="p-4 text-center text-[10px] text-muted-fg">No optimization data available. Run a backtest with more trades.</div>;
  }

  const labels = breakdown.buckets.map(b => b.label);
  const values = breakdown.buckets.map(b => b[metric]);
  const refLine = metric === 'profit_factor' ? 1 : metric === 'win_rate' ? 50 : 0;

  return (
    <div className="p-2 space-y-2 text-[9px]">
      {/* Filter tabs */}
      <div className="flex items-center gap-1 flex-wrap">
        {filterKeys.map(k => (
          <button key={k} onClick={() => setActiveFilter(k)}
            className={`px-2 py-0.5 rounded text-[8px] font-medium transition-colors ${activeFilter === k ? 'bg-blue-600 text-white' : 'bg-surface-inset text-foreground/80 hover:bg-surface-inset'
              }`}>{opt[k].filter_name}</button>
        ))}
      </div>

      {/* Metric selector */}
      <div className="flex items-center gap-1">
        <Lbl>Metric</Lbl>
        <Sel value={metric} onChange={(v) => setMetric(v as any)} options={[
          { value: 'profit_factor', label: 'Profit Factor' },
          { value: 'win_rate', label: 'Win Rate' },
          { value: 'avg_gain', label: 'Avg Gain' },
          { value: 'total_gain', label: 'Total Gain' },
          { value: 'trades', label: 'Trades' },
        ]} />
      </div>

      <div className="flex gap-2">
        {/* Table */}
        <div className="flex-1 rounded border border-border bg-surface overflow-auto max-h-[250px]">
          <table className="w-full text-[8px]">
            <thead className="sticky top-0 bg-surface-hover">
              <tr>
                <th className="px-1 py-1 text-left">No.</th>
                <th className="px-1 py-1 text-left">{breakdown.filter_name}</th>
                <th className="px-1 py-1 text-right">PF</th>
                <th className="px-1 py-1 text-right">Win%</th>
                <th className="px-1 py-1 text-right">Avg $</th>
                <th className="px-1 py-1 text-right">Total $</th>
                <th className="px-1 py-1 text-right">Trds</th>
                <th className="px-1 py-1 text-right">% Tot</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.buckets.map((b, i) => {
                const pfColor = b.profit_factor >= 2 ? 'bg-emerald-500/15' : b.profit_factor >= 1 ? 'bg-emerald-500/10' : 'bg-red-500/10';
                return (
                  <tr key={i} className={`${pfColor} border-b border-border-subtle`}>
                    <td className="px-1 py-0.5 text-muted-fg">{i + 1}</td>
                    <td className="px-1 py-0.5 font-medium text-foreground max-w-[80px] truncate">{b.label}</td>
                    <td className={`px-1 py-0.5 text-right font-bold tabular-nums ${b.profit_factor >= 1 ? 'text-emerald-600' : 'text-red-500'}`}>{b.profit_factor.toFixed(2)}</td>
                    <td className="px-1 py-0.5 text-right tabular-nums">{b.win_rate.toFixed(1)}</td>
                    <td className={`px-1 py-0.5 text-right tabular-nums ${b.avg_gain >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{b.avg_gain.toFixed(0)}</td>
                    <td className={`px-1 py-0.5 text-right tabular-nums ${b.total_gain >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmtMoney(b.total_gain)}</td>
                    <td className="px-1 py-0.5 text-right tabular-nums">{b.trades}</td>
                    <td className="px-1 py-0.5 text-right tabular-nums text-muted-fg">{b.pct_of_total.toFixed(1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Chart */}
        <div className="w-[200px] flex-shrink-0 rounded border border-border bg-surface overflow-hidden">
          <div className="h-[250px]">
            <LazyPlot
              data={[{
                x: labels.map((_, i) => i + 1), y: values, type: 'bar' as const,
                marker: { color: '#3b82f6' }, text: labels, hovertemplate: '%{text}<br>%{y:.2f}<extra></extra>',
              }] as any}
              layout={{
                margin: { t: 4, r: 4, b: 24, l: 36 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
                font: { size: 7, color: 'var(--color-muted-fg)' }, showlegend: false,
                xaxis: { title: { text: 'Group No.', font: { size: 7 } }, tickfont: { size: 7 } },
                yaxis: { tickfont: { size: 7 }, gridcolor: 'var(--color-border-subtle)' },
                shapes: refLine ? [{
                  type: 'line' as const, x0: 0, x1: labels.length + 1, y0: refLine, y1: refLine,
                  line: { color: '#ef4444', width: 1, dash: 'dash' as const },
                }] : [],
              } as any}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '100%' }} useResizeHandler />
          </div>
        </div>
      </div>
    </div>
  );
});

// ── Trades Tab ─────────────────────────────────────────────────────────────

const TradesTab = memo(function TradesTab({ trades }: { trades: TradeRecord[] }) {
  const [sortKey, setSortKey] = useState<keyof TradeRecord>('trade_id');
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(0);
  const PAGE = 100;

  const sorted = useMemo(() => {
    const c = [...trades];
    c.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    return c;
  }, [trades, sortKey, sortAsc]);

  const totalPages = Math.ceil(sorted.length / PAGE);
  const pageData = sorted.slice(page * PAGE, (page + 1) * PAGE);
  const winners = trades.filter(t => t.pnl > 0).length;
  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0);

  const cols: { label: string; key: keyof TradeRecord; align: string }[] = [
    { label: '#', key: 'trade_id', align: 'text-left' },
    { label: 'Sym', key: 'ticker', align: 'text-left' },
    { label: 'Dir', key: 'direction', align: 'text-left' },
    { label: 'Entry', key: 'entry_date', align: 'text-left' },
    { label: 'Entry Px', key: 'entry_fill_price', align: 'text-right' },
    { label: 'Exit', key: 'exit_date', align: 'text-left' },
    { label: 'Exit Px', key: 'exit_fill_price', align: 'text-right' },
    { label: 'Shares', key: 'shares', align: 'text-right' },
    { label: 'PnL', key: 'pnl', align: 'text-right' },
  ];

  return (
    <div className="flex flex-col h-full text-[9px]">
      <div className="flex items-center gap-2 px-2 py-1 bg-surface-hover border-b border-border text-[9px]">
        <span className="font-medium text-foreground/80">{trades.length} trades</span>
        <span className="text-border">|</span>
        <span className="text-emerald-600">{winners} W</span>
        <span className="text-red-500">{trades.length - winners} L</span>
        <span className="text-border">|</span>
        <span className={`font-bold ${totalPnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>PnL: {fmtMoney(totalPnl)}</span>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-[8px]">
          <thead className="sticky top-0 z-10 bg-surface-hover">
            <tr>{cols.map(c => (
              <th key={c.key} onClick={() => { if (sortKey === c.key) setSortAsc(!sortAsc); else { setSortKey(c.key); setSortAsc(true); } setPage(0); }}
                className={`px-1 py-1 font-semibold text-foreground/80 cursor-pointer hover:bg-surface-hover select-none whitespace-nowrap ${c.align}`}>
                {c.label}{sortKey === c.key && <span className="text-primary ml-0.5">{sortAsc ? '▲' : '▼'}</span>}
              </th>
            ))}</tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {pageData.map(t => (
              <tr key={t.trade_id} className={t.pnl >= 0 ? 'hover:bg-emerald-500/10' : 'hover:bg-red-500/10'}>
                <td className="px-1 py-0.5 text-muted-fg tabular-nums">{t.trade_id}</td>
                <td className="px-1 py-0.5 font-bold text-primary">{t.ticker}</td>
                <td className="px-1 py-0.5"><span className={`px-0.5 rounded text-[7px] font-bold ${t.direction === 'long' ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-red-500/10 text-red-700 dark:text-red-400'}`}>{t.direction === 'long' ? 'L' : 'S'}</span></td>
                <td className="px-1 py-0.5 text-foreground/80 tabular-nums">{fmtDate(t.entry_date)}</td>
                <td className="px-1 py-0.5 text-right font-mono tabular-nums">${t.entry_fill_price.toFixed(2)}</td>
                <td className="px-1 py-0.5 text-foreground/80 tabular-nums">{fmtDate(t.exit_date)}</td>
                <td className="px-1 py-0.5 text-right font-mono tabular-nums">${t.exit_fill_price.toFixed(2)}</td>
                <td className="px-1 py-0.5 text-right tabular-nums">{t.shares.toFixed(0)}</td>
                <td className={`px-1 py-0.5 text-right font-bold tabular-nums ${t.pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{fmtMoney(t.pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-2 py-1 border-t border-border bg-surface text-[8px]">
          <span className="text-muted-fg">{page * PAGE + 1}-{Math.min((page + 1) * PAGE, sorted.length)} of {sorted.length}</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
              className="px-1.5 py-0.5 bg-surface-hover border border-border rounded hover:bg-surface-hover disabled:opacity-30">Prev</button>
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              className="px-1.5 py-0.5 bg-surface-hover border border-border rounded hover:bg-surface-hover disabled:opacity-30">Next</button>
          </div>
        </div>
      )}
    </div>
  );
});

// ── Analysis Tab (Walk-Forward + Monte Carlo) ──────────────────────────────

const AnalysisTab = memo(function AnalysisTab({ result }: { result: BacktestResult }) {
  const am = result.advanced_metrics;
  const wf = result.walk_forward;
  const mc = result.monte_carlo;
  if (!am && !wf && !mc) return <div className="p-4 text-center text-[10px] text-muted-fg">No advanced analysis data.</div>;

  return (
    <div className="p-2 space-y-2 text-[9px]">
      {am && (
        <div className="rounded border border-border bg-surface overflow-hidden">
          <div className="px-2 py-1 border-b border-border-subtle font-semibold text-foreground/80">Statistical Robustness</div>
          <div className="grid grid-cols-5 gap-1 p-2 text-center text-[8px]">
            <div><span className="text-muted-fg block">Deflated Sharpe</span><span className={`font-bold ${am.deflated_sharpe_ratio > 1 ? 'text-emerald-600' : am.deflated_sharpe_ratio > 0.5 ? 'text-amber-600' : 'text-red-500'}`}>{am.deflated_sharpe_ratio.toFixed(2)}</span></div>
            <div><span className="text-muted-fg block">Prob. Sharpe</span><span className={`font-bold ${am.probabilistic_sharpe_ratio > 0.95 ? 'text-emerald-600' : 'text-amber-600'}`}>{(am.probabilistic_sharpe_ratio * 100).toFixed(1)}%</span></div>
            <div><span className="text-muted-fg block">Min Track</span><span className="font-bold text-foreground">{am.min_track_record_length}mo</span></div>
            <div><span className="text-muted-fg block">Skewness</span><span className={`font-bold ${am.skewness > 0 ? 'text-emerald-600' : 'text-red-500'}`}>{am.skewness.toFixed(3)}</span></div>
            <div><span className="text-muted-fg block">Kurtosis</span><span className="font-bold text-foreground">{am.kurtosis.toFixed(3)}</span></div>
          </div>
        </div>
      )}
      {wf && (
        <div className="rounded border border-border bg-surface overflow-hidden">
          <div className="px-2 py-1 border-b border-border-subtle flex justify-between">
            <span className="font-semibold text-foreground/80">Walk-Forward ({wf.n_splits} splits)</span>
            <span className={`font-bold px-1 rounded ${wf.overfitting_probability > 0.5 ? 'text-red-600 dark:text-red-400 bg-red-500/10' : wf.overfitting_probability > 0.3 ? 'text-amber-600 dark:text-amber-400 bg-amber-500/10' : 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'}`}>
              P(overfit): {(wf.overfitting_probability * 100).toFixed(0)}%
            </span>
          </div>
          <div className="p-2 space-y-1">
            {wf.splits.map(s => (
              <div key={s.split_idx} className="flex items-center gap-1 text-[8px]">
                <span className="text-muted-fg w-3 text-right">{s.split_idx + 1}</span>
                <div className="flex-1 flex gap-0.5 h-3">
                  <div className="bg-indigo-400 rounded-sm flex items-center justify-center" style={{ width: `${Math.max(5, Math.abs(s.train_sharpe) * 20)}%` }}>
                    <span className="text-[6px] text-white font-bold">{s.train_sharpe.toFixed(2)}</span>
                  </div>
                  <div className="bg-blue-300 rounded-sm flex items-center justify-center" style={{ width: `${Math.max(5, Math.abs(s.test_sharpe) * 20)}%` }}>
                    <span className="text-[6px] text-white font-bold">{s.test_sharpe.toFixed(2)}</span>
                  </div>
                </div>
                <span className={`w-8 text-right font-medium ${s.degradation_pct < -30 ? 'text-red-500' : 'text-emerald-600'}`}>{s.degradation_pct.toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {mc && (
        <div className="rounded border border-border bg-surface overflow-hidden">
          <div className="px-2 py-1 border-b border-border-subtle flex justify-between">
            <span className="font-semibold text-foreground/80">Monte Carlo ({mc.n_simulations.toLocaleString()} sims)</span>
            <span className={`font-bold px-1 rounded ${mc.prob_profit >= 0.7 ? 'text-emerald-600 bg-emerald-500/10' : 'text-amber-600 bg-amber-500/10'}`}>
              P(profit): {(mc.prob_profit * 100).toFixed(0)}%
            </span>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 p-2 text-[8px]">
            {[
              ['Median Equity', fmtMoney(mc.median_final_equity)],
              ['Mean Equity', fmtMoney(mc.mean_final_equity)],
              ['5th Pctl', fmtMoney(mc.percentile_5_equity)],
              ['95th Pctl', fmtMoney(mc.percentile_95_equity)],
              ['Mean Max DD', fmtPctRaw(mc.mean_max_drawdown_pct)],
              ['Worst Max DD', fmtPctRaw(mc.worst_max_drawdown_pct)],
            ].map(([l, v]) => (
              <div key={l} className="flex justify-between"><span className="text-muted-fg">{l}</span><span className="font-bold text-foreground">{v}</span></div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

// ═══════════════════════════════════════════════════════════════════════════
// RESULTS VIEW
// ═══════════════════════════════════════════════════════════════════════════

type ResultTab = 'summary' | 'equity' | 'daily' | 'drawdown' | 'calendar' | 'optimization' | 'trades' | 'analysis';

const RESULT_TABS: { id: ResultTab; label: string }[] = [
  { id: 'summary', label: 'Summary' },
  { id: 'equity', label: 'Equity' },
  { id: 'daily', label: 'Daily PnL' },
  { id: 'drawdown', label: 'Drawdown' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'optimization', label: 'Optimization' },
  { id: 'trades', label: 'Trades' },
  { id: 'analysis', label: 'Analysis' },
];

function ResultsView({ result, onReset }: { result: BacktestResult; onReset: () => void }) {
  const [tab, setTab] = useState<ResultTab>('summary');
  const s = result.strategy;
  return (
    <div className="flex flex-col h-full min-h-0 bg-surface">
      <div className="flex-shrink-0 px-2.5 py-1.5 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="text-[11px] font-bold text-foreground truncate">{s.name}</h3>
          <span className="text-[8px] text-muted-fg">{s.start_date} → {s.end_date} | {s.timeframe} | {s.direction} | {fmtMoney(s.initial_capital)}</span>
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-[8px] text-muted-fg">
          <span>{result.symbols_tested} tickers</span><span>|</span>
          <span>{result.bars_processed.toLocaleString()} bars</span><span>|</span>
          <span>{result.execution_time_ms < 1000 ? `${result.execution_time_ms}ms` : `${(result.execution_time_ms / 1000).toFixed(1)}s`}</span>
        </div>
      </div>
      <div className="flex-shrink-0 flex items-center border-b border-border px-1 overflow-x-auto">
        {RESULT_TABS.map(t => (
          <ResultTabBtn key={t.id} active={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</ResultTabBtn>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {tab === 'summary' && <SummaryTab result={result} />}
        {tab === 'equity' && <EquityCurveTab result={result} />}
        {tab === 'daily' && <DailyTab result={result} />}
        {tab === 'drawdown' && <DrawdownTab result={result} />}
        {tab === 'calendar' && <CalendarTab result={result} />}
        {tab === 'optimization' && <OptimizationTab result={result} />}
        {tab === 'trades' && <TradesTab trades={result.trades} />}
        {tab === 'analysis' && <AnalysisTab result={result} />}
      </div>
      <div className="flex-shrink-0 p-1.5 border-t border-border bg-surface-hover">
        <button type="button" onClick={onReset}
          className="w-full py-1.5 text-[9px] font-medium text-foreground/80 bg-surface border border-border rounded hover:bg-surface-hover">
          New Backtest
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// EVENT SELECTOR
// ═══════════════════════════════════════════════════════════════════════════

function EventSelector({ selected, onChange, label }: {
  selected: Set<string>; onChange: (s: Set<string>) => void; label: string;
}) {
  const [search, setSearch] = useState('');
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const categories = useMemo(() => getAlertsByCategory(), []);

  const filtered = useMemo(() => {
    if (!search) return categories;
    const q = search.toLowerCase();
    return categories.map(c => ({
      ...c,
      alerts: c.alerts.filter(a =>
        a.name.toLowerCase().includes(q) || a.eventType.toLowerCase().includes(q) ||
        a.nameEs.toLowerCase().includes(q) || a.code.toLowerCase().includes(q)
      ),
    })).filter(c => c.alerts.length > 0);
  }, [categories, search]);

  const toggleCat = (catId: string) => {
    setExpandedCats(prev => {
      const n = new Set(prev);
      n.has(catId) ? n.delete(catId) : n.add(catId);
      return n;
    });
  };

  const toggleEvent = (eventType: string) => {
    const n = new Set(selected);
    n.has(eventType) ? n.delete(eventType) : n.add(eventType);
    onChange(n);
  };

  const toggleAllCat = (alerts: AlertDefinition[]) => {
    const n = new Set(selected);
    const allSelected = alerts.every(a => n.has(a.eventType));
    alerts.forEach(a => allSelected ? n.delete(a.eventType) : n.add(a.eventType));
    onChange(n);
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <div className="relative flex-1">
          <Search className="absolute left-1.5 top-1/2 -translate-y-1/2 w-2.5 h-2.5 text-muted-fg" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={`Search ${label}...`}
            className="w-full pl-5 pr-1.5 py-[3px] text-[9px] border border-border rounded bg-surface text-foreground focus:ring-1 focus:ring-primary outline-none" />
        </div>
        {selected.size > 0 && (
          <button onClick={() => onChange(new Set())}
            className="text-[7px] text-red-500 hover:text-red-700 px-1 py-0.5 rounded bg-red-500/10">
            Clear ({selected.size})
          </button>
        )}
      </div>
      <div className="max-h-[140px] overflow-auto border border-border rounded bg-surface">
        {filtered.map(({ category, alerts }) => (
          <div key={category.id}>
            <button onClick={() => toggleCat(category.id)}
              className="w-full flex items-center gap-1 px-1.5 py-[3px] bg-surface-hover hover:bg-surface-inset border-b border-border-subtle text-[8px]">
              {expandedCats.has(category.id) ? <ChevronDown className="w-2 h-2 text-muted-fg" /> : <ChevronRight className="w-2 h-2 text-muted-fg" />}
              <span className="font-semibold text-foreground/80 flex-1 text-left">{category.name}</span>
              <span className="text-muted-fg">{alerts.filter(a => selected.has(a.eventType)).length}/{alerts.length}</span>
              <button onClick={e => { e.stopPropagation(); toggleAllCat(alerts); }}
                className="text-[7px] text-primary hover:text-primary px-0.5">
                {alerts.every(a => selected.has(a.eventType)) ? 'none' : 'all'}
              </button>
            </button>
            {expandedCats.has(category.id) && (
              <div className="px-1 py-0.5">
                {alerts.map(a => (
                  <label key={a.eventType} className="flex items-center gap-1.5 py-[2px] cursor-pointer hover:bg-primary/10 rounded px-1">
                    <input type="checkbox" checked={selected.has(a.eventType)}
                      onChange={() => toggleEvent(a.eventType)}
                      className="w-2.5 h-2.5 rounded border-border text-primary focus:ring-primary" />
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${a.direction === 'bullish' ? 'bg-emerald-400' : a.direction === 'bearish' ? 'bg-red-400' : 'bg-muted'
                      }`} />
                    <span className="text-[8px] text-foreground flex-1">{a.name}</span>
                    <span className="text-[7px] text-muted-fg font-mono">{a.code}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {selected.size > 0 && (
        <div className="flex flex-wrap gap-0.5">
          {Array.from(selected).map(id => {
            const a = ALERT_CATALOG.find(x => x.eventType === id);
            return (
              <span key={id} className="inline-flex items-center gap-0.5 px-1 py-[1px] bg-primary/10 border border-border rounded text-[7px] text-primary">
                {a?.code ?? id}
                <button onClick={() => toggleEvent(id)} className="hover:text-red-500"><X className="w-2 h-2" /></button>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// FILTER SECTION
// ═══════════════════════════════════════════════════════════════════════════

function FilterSection({ filters, onChange, label = 'filters' }: {
  filters: Record<string, number | string | null>;
  onChange: (f: Record<string, number | string | null>) => void;
  label?: string;
}) {
  const [search, setSearch] = useState('');
  const activeCount = Object.values(filters).filter(v => v !== null && v !== undefined && v !== '').length;

  const filtered = useMemo(() => {
    if (!search) return FILTER_DEFS;
    const q = search.toLowerCase();
    return FILTER_DEFS.filter(f => f.label.toLowerCase().includes(q) || f.key.toLowerCase().includes(q));
  }, [search]);

  const setVal = (key: string, val: string) => {
    const n = { ...filters };
    if (val === '' || val === undefined) {
      delete n[key];
    } else {
      n[key] = parseFloat(val) || null;
    }
    onChange(n);
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <div className="relative flex-1">
          <Search className="absolute left-1.5 top-1/2 -translate-y-1/2 w-2.5 h-2.5 text-muted-fg" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={`Search ${label}...`}
            className="w-full pl-5 pr-1.5 py-[3px] text-[9px] border border-border rounded bg-surface text-foreground focus:ring-1 focus:ring-primary outline-none" />
        </div>
        {activeCount > 0 && (
          <button onClick={() => onChange({})}
            className="text-[7px] text-red-500 hover:text-red-700 px-1 py-0.5 rounded bg-red-500/10">
            Clear ({activeCount})
          </button>
        )}
      </div>
      <div className="max-h-[140px] overflow-auto border border-border rounded bg-surface">
        <table className="w-full text-[8px]">
          <thead className="sticky top-0 bg-surface-hover">
            <tr>
              <th className="px-1.5 py-1 text-left font-semibold text-foreground/80">Filter</th>
              <th className="px-1.5 py-1 text-center font-semibold text-foreground/80 w-[70px]">Min</th>
              <th className="px-1.5 py-1 text-center font-semibold text-foreground/80 w-[70px]">Max</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => {
              const minK = `min_${f.key}`;
              const maxK = `max_${f.key}`;
              const hasVal = (filters[minK] !== null && filters[minK] !== undefined) ||
                (filters[maxK] !== null && filters[maxK] !== undefined);
              return (
                <tr key={f.key} className={`border-b border-border-subtle ${hasVal ? 'bg-primary/10' : ''}`}>
                  <td className="px-1.5 py-0.5 text-foreground">{f.label} <span className="text-muted-fg">{f.suffix}</span></td>
                  <td className="px-0.5 py-0.5">
                    <input type="number" step="any"
                      value={filters[minK] ?? ''}
                      onChange={e => setVal(minK, e.target.value)}
                      placeholder="—"
                      className="w-full px-1 py-[2px] text-[8px] border border-border rounded bg-surface text-center focus:ring-1 focus:ring-primary outline-none" />
                  </td>
                  <td className="px-0.5 py-0.5">
                    <input type="number" step="any"
                      value={filters[maxK] ?? ''}
                      onChange={e => setVal(maxK, e.target.value)}
                      placeholder="—"
                      className="w-full px-1 py-[2px] text-[8px] border border-border rounded bg-surface text-center focus:ring-1 focus:ring-primary outline-none" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT — Tab-based config
// ═══════════════════════════════════════════════════════════════════════════

type CfgTab = 'strategy' | 'entry' | 'exit' | 'filters' | 'review';

export function BacktestPanelContent({ initialEvents, initialFilters, initialName }: {
  initialEvents?: string[];
  initialFilters?: Record<string, any>;
  initialName?: string;
} = {}) {
  const { status, result, error, progressText, runStructured, reset } = useBacktestFloating();
  const [cfgTab, setCfgTab] = useState<CfgTab>((initialEvents?.length ?? 0) > 0 ? 'entry' : 'strategy');

  // Strategy
  const [name, setName] = useState(initialName || 'My Strategy');
  const [direction, setDirection] = useState<'long' | 'short' | 'both'>('long');
  const [timeframe, setTimeframe] = useState<Timeframe>('1d');
  const [startDate, setStartDate] = useState(oneYearAgoStr());
  const [endDate, setEndDate] = useState(todayStr());
  const [entryTiming, setEntryTiming] = useState<'open' | 'close' | 'next_open'>('next_open');
  const [tickersStr, setTickersStr] = useState('SPY');
  const [capital, setCapital] = useState(100000);
  const [maxPositions, setMaxPositions] = useState(10);
  const [positionSizePct, setPositionSizePct] = useState(0.10);
  const [slippageModel, setSlippageModel] = useState<SlippageModel>('fixed_bps');
  const [slippageBps, setSlippageBps] = useState(10);
  const [commission, setCommission] = useState(0);
  const [riskFreeRate, setRiskFreeRate] = useState(0.05);
  const [walkForward, setWalkForward] = useState(true);
  const [monteCarlo, setMonteCarlo] = useState(true);

  // Entry
  const [entries, setEntries] = useState<Signal[]>([defaultSignal()]);
  const [entryEvents, setEntryEvents] = useState<Set<string>>(new Set(initialEvents ?? []));
  const [entryEventsCombine, setEntryEventsCombine] = useState<'or' | 'and'>('or');

  // Exit
  const [exits, setExits] = useState<ExitRule[]>([{ type: 'stop_loss', value: 0.05 }, { type: 'target', value: 0.10 }]);
  const [exitEvents, setExitEvents] = useState<Set<string>>(new Set());

  // Filters
  const [entryFilters, setEntryFilters] = useState<Record<string, number | string | null>>(initialFilters ?? {});
  const [universeFilters, setUniverseFilters] = useState<Record<string, number | string | null>>({});

  const entryFilterCount = Object.values(entryFilters).filter(v => v != null && v !== '').length;
  const universeFilterCount = Object.values(universeFilters).filter(v => v != null && v !== '').length;

  const buildConfig = useCallback((): StrategyConfig => {
    const tickers = tickersStr.split(/[\s,;]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
    const clean = (f: Record<string, number | string | null>) =>
      Object.fromEntries(Object.entries(f).filter(([, v]) => v != null && v !== ''));
    return {
      name, description: '',
      universe: { method: 'ticker_list', criteria: {}, tickers, sql_where: null },
      entry_signals: entries, entry_timing: entryTiming,
      entry_events: Array.from(entryEvents), entry_events_combine: entryEventsCombine,
      exit_rules: exits, exit_events: Array.from(exitEvents),
      entry_filters: clean(entryFilters), universe_filters: clean(universeFilters),
      timeframe, start_date: startDate, end_date: endDate,
      initial_capital: capital, max_positions: maxPositions, position_size_pct: positionSizePct,
      direction, slippage_model: slippageModel, slippage_bps: slippageBps,
      commission_per_trade: commission, risk_free_rate: riskFreeRate,
    };
  }, [name, direction, timeframe, startDate, endDate, entryTiming, tickersStr, entries, entryEvents, entryEventsCombine, exits, exitEvents, entryFilters, universeFilters, capital, maxPositions, positionSizePct, slippageModel, slippageBps, commission, riskFreeRate]);

  const handleRun = useCallback(async () => {
    await runStructured(buildConfig(), { includeWalkForward: walkForward, includeMonteCarlo: monteCarlo });
  }, [buildConfig, runStructured, walkForward, monteCarlo]);

  const isRunning = status === 'running';
  const showResults = status === 'complete' && result;

  const validation = useMemo(() => {
    const tickers = tickersStr.split(/[\s,;]+/).filter(Boolean);
    if (tickers.length === 0) return 'Add at least one ticker';
    if (entries.length === 0 && entryEvents.size === 0) return 'Add entry signals or events';
    if (!startDate || !endDate) return 'Set dates';
    if (new Date(endDate) <= new Date(startDate)) return 'End > Start';
    return null;
  }, [tickersStr, entries, entryEvents, startDate, endDate]);

  if (showResults) return <ResultsView result={result} onReset={reset} />;

  return (
    <div className="flex flex-col h-full min-h-0 bg-surface text-foreground text-[10px]">
      {/* Config tab bar */}
      <div className="flex-shrink-0 flex items-center border-b border-border px-1">
        <ConfigTab active={cfgTab === 'strategy'} onClick={() => setCfgTab('strategy')}>Strategy</ConfigTab>
        <ConfigTab active={cfgTab === 'entry'} onClick={() => setCfgTab('entry')} badge={entryEvents.size + entries.length}>Entry</ConfigTab>
        <ConfigTab active={cfgTab === 'exit'} onClick={() => setCfgTab('exit')} badge={exits.length + exitEvents.size}>Exit</ConfigTab>
        <ConfigTab active={cfgTab === 'filters'} onClick={() => setCfgTab('filters')} badge={entryFilterCount + universeFilterCount}>Filters</ConfigTab>
        <ConfigTab active={cfgTab === 'review'} onClick={() => setCfgTab('review')}>Review</ConfigTab>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-auto">
        {cfgTab === 'strategy' && (
          <div className="p-3 space-y-3">
            <div>
              <Lbl>Strategy Name</Lbl>
              <Inp value={name} onChange={setName} className="w-full mt-1" placeholder="My Strategy" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div><Lbl>Direction</Lbl><Sel value={direction} onChange={v => setDirection(v as any)} options={[{ value: 'long', label: 'Long' }, { value: 'short', label: 'Short' }, { value: 'both', label: 'Both' }]} className="w-full mt-1" /></div>
              <div><Lbl>Timeframe</Lbl><Sel value={timeframe} onChange={v => setTimeframe(v as Timeframe)} options={TIMEFRAMES} className="w-full mt-1" /></div>
              <div><Lbl>Entry Timing</Lbl><Sel value={entryTiming} onChange={v => setEntryTiming(v as any)} options={[{ value: 'next_open', label: 'Next Open' }, { value: 'open', label: 'Open' }, { value: 'close', label: 'Close' }]} className="w-full mt-1" /></div>
            </div>
            <div>
              <Lbl>Tickers</Lbl>
              <Inp value={tickersStr} onChange={setTickersStr} placeholder="SPY, AAPL, QQQ" className="w-full mt-1 font-mono" />
              <p className="mt-0.5 text-[7px] text-muted-fg">Comma separated. Split-adjusted Polygon data.</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><Lbl>Start Date</Lbl><Inp type="date" value={startDate} onChange={setStartDate} className="w-full mt-1" /></div>
              <div><Lbl>End Date</Lbl><Inp type="date" value={endDate} onChange={setEndDate} className="w-full mt-1" /></div>
            </div>
            <div className="border-t border-border-subtle pt-3">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider mb-2">Execution</div>
              <div className="grid grid-cols-3 gap-2">
                <div><Lbl>Capital ($)</Lbl><Inp type="number" value={capital} onChange={v => setCapital(Number(v) || 100000)} className="w-full mt-1" /></div>
                <div><Lbl>Max Positions</Lbl><Inp type="number" value={maxPositions} onChange={v => setMaxPositions(Number(v) || 1)} className="w-full mt-1" min="1" /></div>
                <div><Lbl>Position Size %</Lbl><Inp type="number" value={(positionSizePct * 100).toFixed(0)} onChange={v => setPositionSizePct((Number(v) || 10) / 100)} className="w-full mt-1" /></div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-2">
                <div><Lbl>Slippage Model</Lbl><Sel value={slippageModel} onChange={v => setSlippageModel(v as SlippageModel)} options={SLIPPAGE_MODELS} className="w-full mt-1" /></div>
                <div><Lbl>Slippage BPS</Lbl><Inp type="number" value={slippageBps} onChange={v => setSlippageBps(Number(v) || 0)} className="w-full mt-1" /></div>
                <div><Lbl>Commission ($)</Lbl><Inp type="number" value={commission} onChange={v => setCommission(Number(v) || 0)} className="w-full mt-1" step="0.01" /></div>
              </div>
            </div>
            <div className="border-t border-border-subtle pt-3">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider mb-2">Advanced</div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={walkForward} onChange={e => setWalkForward(e.target.checked)} className="w-3 h-3 rounded border-border text-primary" />
                <span className="text-[9px] text-foreground">Walk-Forward Analysis (5 splits)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer mt-1">
                <input type="checkbox" checked={monteCarlo} onChange={e => setMonteCarlo(e.target.checked)} className="w-3 h-3 rounded border-border text-primary" />
                <span className="text-[9px] text-foreground">Monte Carlo Simulation (1,000 runs)</span>
              </label>
            </div>
          </div>
        )}

        {cfgTab === 'entry' && (
          <div className="flex flex-col h-full">
            <div className="flex-shrink-0 px-3 pt-2 pb-1">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider">Events</div>
              <div className="flex items-center gap-2 mt-1">
                <Lbl>Combine</Lbl>
                <Sel value={entryEventsCombine} onChange={v => setEntryEventsCombine(v as 'or' | 'and')} options={[
                  { value: 'or', label: 'ANY event (OR)' }, { value: 'and', label: 'ALL events (AND)' },
                ]} />
                {entries.length > 0 && entryEvents.size > 0 && (
                  <span className="text-[7px] text-amber-600 dark:text-amber-400 bg-amber-500/10 px-1 py-0.5 rounded border border-amber-500/20">Events AND Signals</span>
                )}
              </div>
            </div>
            <div className="flex-1 min-h-0 px-3 pb-2">
              <EventSelector selected={entryEvents} onChange={setEntryEvents} label="entry events" />
            </div>
            <div className="flex-shrink-0 border-t border-border px-3 py-2">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider mb-1">Indicator Signals (AND)</div>
              <div className="space-y-0.5 max-h-[120px] overflow-auto">
                {entries.map((sig, i) => (
                  <SignalRow key={i} signal={sig}
                    onChange={s => { const n = [...entries]; n[i] = s; setEntries(n); }}
                    onRemove={() => setEntries(entries.filter((_, j) => j !== i))} />
                ))}
              </div>
              <button type="button" onClick={() => setEntries([...entries, defaultSignal()])}
                className="flex items-center gap-1 text-[8px] text-blue-600 hover:text-blue-800 mt-1">
                <Plus className="w-2.5 h-2.5" /> Add signal
              </button>
            </div>
          </div>
        )}

        {cfgTab === 'exit' && (
          <div className="flex flex-col h-full">
            <div className="flex-shrink-0 px-3 pt-2 pb-2 border-b border-border">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider mb-1">Risk Management Rules</div>
              <div className="space-y-0.5">
                {exits.map((rule, i) => (
                  <ExitRow key={i} rule={rule}
                    onChange={r => { const n = [...exits]; n[i] = r; setExits(n); }}
                    onRemove={() => setExits(exits.filter((_, j) => j !== i))} />
                ))}
              </div>
              <button type="button" onClick={() => setExits([...exits, defaultExit()])}
                className="flex items-center gap-1 text-[8px] text-primary hover:text-primary mt-1">
                <Plus className="w-2.5 h-2.5" /> Add exit rule
              </button>
            </div>
            <div className="flex-shrink-0 px-3 pt-2 pb-1">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider">Exit Events (OR)</div>
              <p className="text-[7px] text-muted-fg mt-0.5">Any of these events will trigger position exit</p>
            </div>
            <div className="flex-1 min-h-0 px-3 pb-2">
              <EventSelector selected={exitEvents} onChange={setExitEvents} label="exit events" />
            </div>
          </div>
        )}

        {cfgTab === 'filters' && (
          <div className="flex flex-col h-full">
            <div className="flex-shrink-0 px-3 pt-2 pb-1">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider">Entry Filters (Per-Bar)</div>
              <p className="text-[7px] text-muted-fg mt-0.5">Conditions that must be met on each bar for entry</p>
            </div>
            <div className="flex-1 min-h-0 px-3 pb-2">
              <FilterSection filters={entryFilters} onChange={setEntryFilters} label="entry filters" />
            </div>
            <div className="flex-shrink-0 border-t border-border px-3 pt-2 pb-1">
              <div className="text-[9px] font-semibold text-foreground/80 uppercase tracking-wider">Universe Filters (Pre-Filter)</div>
              <p className="text-[7px] text-muted-fg mt-0.5">Filter tickers before simulation</p>
            </div>
            <div className="flex-1 min-h-0 px-3 pb-2">
              <FilterSection filters={universeFilters} onChange={setUniverseFilters} label="universe filters" />
            </div>
          </div>
        )}

        {cfgTab === 'review' && (
          <div className="p-3 space-y-2 text-[9px]">
            <div className="rounded border border-border bg-surface overflow-hidden">
              <table className="w-full"><tbody>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Name</td><td className="px-2 py-1 text-right font-bold text-foreground">{name}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Direction</td><td className="px-2 py-1 text-right">{direction}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Timeframe</td><td className="px-2 py-1 text-right">{timeframe}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Period</td><td className="px-2 py-1 text-right">{startDate} → {endDate}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Tickers</td><td className="px-2 py-1 text-right font-mono">{tickersStr}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Capital</td><td className="px-2 py-1 text-right">{fmtMoney(capital)}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Entry Events</td><td className="px-2 py-1 text-right">{entryEvents.size > 0 ? `${entryEvents.size} (${entryEventsCombine.toUpperCase()})` : 'none'}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Entry Signals</td><td className="px-2 py-1 text-right">{entries.length > 0 ? entries.map(s => `${s.indicator} ${s.operator} ${s.value}`).join(', ') : 'none'}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Exit Rules</td><td className="px-2 py-1 text-right">{exits.map(e => `${e.type}${e.value != null ? ` ${e.value}` : ''}`).join(', ')}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Exit Events</td><td className="px-2 py-1 text-right">{exitEvents.size > 0 ? `${exitEvents.size} events` : 'none'}</td></tr>
                <tr className="border-b border-border-subtle"><td className="px-2 py-1 text-muted-fg font-medium">Entry Filters</td><td className="px-2 py-1 text-right">{entryFilterCount > 0 ? `${entryFilterCount} active` : 'none'}</td></tr>
                <tr><td className="px-2 py-1 text-muted-fg font-medium">Universe Filters</td><td className="px-2 py-1 text-right">{universeFilterCount > 0 ? `${universeFilterCount} active` : 'none'}</td></tr>
              </tbody></table>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 border-t border-border bg-surface-hover p-1.5 space-y-1">
        {status === 'error' && error && (
          <div className="flex items-start gap-1 p-1.5 bg-red-500/10 rounded border border-red-500/20">
            <AlertCircle className="w-3 h-3 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-[9px] text-red-700 dark:text-red-400">{error}</p>
              <button type="button" onClick={reset} className="text-[8px] text-red-600 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300 underline mt-0.5">Dismiss</button>
            </div>
          </div>
        )}
        {isRunning && (
          <div className="flex items-center gap-2 px-1">
            <Loader2 className="w-3 h-3 animate-spin text-primary flex-shrink-0" />
            <span className="text-[9px] text-foreground/80 truncate">{progressText || 'Running backtest…'}</span>
          </div>
        )}
        {validation && !isRunning && <p className="text-[8px] text-amber-600 dark:text-amber-400 px-1">{validation}</p>}
        <button type="button" onClick={handleRun} disabled={isRunning || !!validation}
          className="w-full py-1.5 text-[10px] font-semibold text-white bg-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors">
          {isRunning ? 'Running…' : 'Run Backtest'}
        </button>
      </div>
    </div>
  );
}
