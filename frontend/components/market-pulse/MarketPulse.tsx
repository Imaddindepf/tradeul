'use client';

/**
 * MarketPulse 2.0 — rediseño completo (2026-07)
 *
 * - Chrome estándar de FloatingWindow (fuera hideHeader, grip y botones duplicados)
 * - UI monocroma: el color queda reservado a los números vía --color-tick-up/down
 * - Market strip permanente (resumen cap-wtd / equal-weight / A/D / $vol / vol%)
 * - Segmented controls para ámbito y las 7 vistas (antes dropdown + tabs a ancho completo)
 * - Filtros unificados con chips y presets guardables (cap server-side, resto client-side)
 * - Presets de columnas + gestor con grupos y modo bar/num/heat explícito
 * - Drilldown en panel lateral (ventana ancha) o a pantalla completa (ventana estrecha)
 * - Filas expandibles con los movers del grupo (dato del API que antes se descartaba)
 */

import { useState, useCallback, useMemo, useRef, useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useMarketPulse, useDrilldown, useTickerContext, type PulseTab, type PerformanceEntry, type DrilldownTicker } from '@/hooks/useMarketPulse';
import { useCurrentWindowId } from '@/contexts/FloatingWindowContext';
import { registerTickerSearch } from '@/lib/tickerSearchRegistry';
import { ArrowLeft, RefreshCw, ChevronRight, ChevronDown, ArrowDown, ArrowUp, X, ExternalLink, Search, Columns3, SlidersHorizontal } from 'lucide-react';
import { ALL_COLUMNS, DD_COLUMNS, DEFAULT_DD_COLUMNS, type ColumnDef, type RenderMode } from './columns';
import type { PulseViewType } from './types';
import { VIEW_DEFINITIONS } from './viewRegistry';
import RotationBarsView from './views/RotationBarsView';
import BreadthMonitorView from './views/BreadthMonitorView';
import RRGView from './views/RRGView';
import BubbleScatterView from './views/BubbleScatterView';
import OverviewView from './views/OverviewView';
import TreemapView from './views/TreemapView';
import TickerContextView from './views/TickerContextView';

function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)); }
function fmtTheme(n: string) { return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '); }
function fmtBig(v: number) {
  if (v >= 1e12) return `${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
  return v.toFixed(0);
}

// ── Colores de datos: los únicos colores de la ventana (personalizables por el usuario) ──
const UP = 'var(--color-tick-up)';
const DOWN = 'var(--color-tick-down)';
const UP_SOFT = 'color-mix(in srgb, var(--color-tick-up) 22%, transparent)';
const DOWN_SOFT = 'color-mix(in srgb, var(--color-tick-down) 20%, transparent)';
const FG = 'var(--color-fg)';

// ── Grid layout constants (px) ──
const NAME_W = 208;   // frozen first column
const COL_W = 116;    // each data column
const HEADER_H = 30;
const ROW_H = 28;
const MOVERS_H = 34;  // fila expandida de movers
const PANEL_MIN_CONTENT = 480; // ancho mínimo de tabla para permitir panel lateral
const PANEL_W = 360;

// ── Column presets ──
const COLUMN_PRESETS: { id: string; label: string; cols: string[] }[] = [
  { id: 'momentum', label: 'Momentum', cols: ['weighted_change', '_spread', 'avg_change_from_open', 'avg_change_5d', '_accel'] },
  { id: 'volume', label: 'Volumen & Flujo', cols: ['weighted_change', 'breadth', 'avg_rvol', 'high_rvol_count', 'avg_vol_today_pct', 'total_dollar_volume'] },
  { id: 'technicals', label: 'Técnicos', cols: ['weighted_change', 'avg_daily_rsi', 'avg_adx', 'avg_bb_position', 'avg_dist_vwap', 'avg_dist_sma20'] },
  { id: 'multiday', label: 'Multi-día', cols: ['weighted_change', 'avg_change_5d', 'avg_change_10d', 'avg_change_20d', 'avg_from_52w_high', 'avg_dist_sma50'] },
];

const COLUMN_GROUPS: { id: string; label: string; keys: string[] }[] = [
  { id: 'mom', label: 'Precio & Momentum', keys: ['weighted_change', 'avg_change', 'median_change', 'avg_gap_pct', 'avg_change_from_open', '_spread', '_accel'] },
  { id: 'vol', label: 'Amplitud & Volumen', keys: ['breadth', 'avg_rvol', 'high_rvol_count', 'count', 'avg_vol_today_pct', 'total_dollar_volume', 'total_market_cap'] },
  { id: 'tec', label: 'Técnicos', keys: ['avg_rsi', 'avg_daily_rsi', 'avg_atr_pct', 'avg_adx', 'avg_dist_vwap', 'avg_pos_in_range', 'avg_bb_position', 'avg_dist_sma20', 'avg_dist_sma50'] },
  { id: 'mul', label: 'Multi-día', keys: ['avg_change_5d', 'avg_change_10d', 'avg_change_20d', 'avg_from_52w_high'] },
];

// ── Filtros (cap es server-side; el resto client-side sobre los grupos) ──
interface PulseFilters {
  minCap: number;
  minRvol: number;        // 0 = off
  breadth: 'any' | 'ge60' | 'ge50' | 'le40';
  rsi: 'any' | 'lt30' | 'mid' | 'gt70';
  divergentOnly: boolean;
}
const DEFAULT_FILTERS: PulseFilters = { minCap: 0, minRvol: 0, breadth: 'any', rsi: 'any', divergentOnly: false };

interface FilterPreset { name: string; filters: PulseFilters; }

function countActiveFilters(f: PulseFilters): number {
  let n = 0;
  if (f.minCap > 0) n++;
  if (f.minRvol > 0) n++;
  if (f.breadth !== 'any') n++;
  if (f.rsi !== 'any') n++;
  if (f.divergentOnly) n++;
  return n;
}

function capLabel(v: number) {
  if (v >= 1e11) return 'Cap ≥ $100B';
  if (v >= 1e10) return 'Cap ≥ $10B';
  if (v >= 2e9) return 'Cap ≥ $2B';
  if (v >= 3e8) return 'Cap ≥ $300M';
  return '';
}
const BREADTH_LABEL: Record<string, string> = { ge60: 'Breadth ≥ 60%', ge50: 'Breadth ≥ 50%', le40: 'Breadth ≤ 40%' };
const RSI_LABEL: Record<string, string> = { lt30: 'RSI < 30', mid: 'RSI 30–70', gt70: 'RSI > 70' };

// ── LocalStorage persistence ──
const LS_KEY = 'market-pulse-prefs';
interface PulsePrefs {
  visCols?: string[];
  ddVisCols?: string[];
  modes?: Record<string, string>;
  ddModes?: Record<string, string>;
  minCap?: number; // legado — migrado a filters.minCap
  view?: PulseViewType;
  colPreset?: string;
  filters?: PulseFilters;
  filterPresets?: FilterPreset[];
}
function loadPrefs(): PulsePrefs {
  try { const s = localStorage.getItem(LS_KEY); return s ? JSON.parse(s) : {}; } catch { return {}; }
}
function savePrefs(p: PulsePrefs) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(p)); } catch { }
}

// ── Shared cell renderers (color solo en números) ──

function DivBar({ value, domain, label, changed }: { value: number; domain: [number, number]; label: string; changed: boolean }) {
  const mid = (domain[0] + domain[1]) / 2;
  const range = (domain[1] - domain[0]) / 2 || 1;
  const norm = clamp((value - mid) / range, -1, 1);
  const pct = Math.abs(norm) * 50;
  const pos = norm >= 0;
  const [flash, setFlash] = useState(false);
  useEffect(() => { if (changed) { setFlash(true); const t = setTimeout(() => setFlash(false), 600); return () => clearTimeout(t); } }, [changed, value]);
  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0 h-full">
      <div className="relative flex-1 h-[13px] rounded-[3px] overflow-hidden bg-surface-inset">
        <div className="absolute top-0 left-1/2 h-full w-px bg-muted" />
        <div className={`absolute top-0 bottom-0 rounded-[3px] transition-all duration-500 ease-out ${pos ? 'left-1/2' : 'right-1/2'}`}
          style={{ width: `${pct}%`, backgroundColor: pos ? UP : DOWN }} />
      </div>
      <span className={`text-[11px] font-mono tabular-nums w-[46px] text-right shrink-0 transition-all duration-400 ${flash ? 'font-extrabold' : 'font-semibold'}`}
        style={{ color: pos ? UP : DOWN }}>{label}</span>
    </div>
  );
}

function PosBar({ value, domain, label }: { value: number; domain: [number, number]; label: string }) {
  const norm = clamp((value - domain[0]) / ((domain[1] - domain[0]) || 1), 0, 1);
  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0 h-full">
      <div className="relative flex-1 h-[13px] rounded-[3px] overflow-hidden bg-surface-inset">
        <div className="absolute top-0 bottom-0 left-0 rounded-[3px] transition-all duration-500 ease-out opacity-70"
          style={{ width: `${norm * 100}%`, backgroundColor: FG }} />
      </div>
      <span className="text-[11px] font-semibold font-mono tabular-nums w-[48px] text-right shrink-0 text-foreground">{label}</span>
    </div>
  );
}

function NumCell({ value, col, changed }: { value: number; col: ColumnDef; changed: boolean }) {
  const [flash, setFlash] = useState(false);
  useEffect(() => { if (changed) { setFlash(true); const t = setTimeout(() => setFlash(false), 600); return () => clearTimeout(t); } }, [changed, value]);
  const pos = value >= 0;
  const div = col.colorScale === 'diverging';
  return (
    <span className={`text-[12px] font-mono tabular-nums text-right block transition-all duration-400 ${flash ? 'font-extrabold' : 'font-semibold'}`}
      style={{ color: div ? (pos ? UP : DOWN) : undefined }}>{col.format(value)}</span>
  );
}

function HeatCell({ value, col }: { value: number; col: ColumnDef }) {
  const domain = col.domain || [0, 100];
  let bg: string;
  if (col.colorScale === 'diverging') {
    const mid = (domain[0] + domain[1]) / 2, range = (domain[1] - domain[0]) / 2 || 1;
    const norm = clamp((value - mid) / range, -1, 1);
    const alpha = Math.round(Math.abs(norm) * 40);
    bg = norm >= 0
      ? `color-mix(in srgb, var(--color-tick-up) ${alpha}%, transparent)`
      : `color-mix(in srgb, var(--color-tick-down) ${alpha}%, transparent)`;
  } else {
    const norm = clamp((value - domain[0]) / ((domain[1] - domain[0]) || 1), 0, 1);
    bg = `color-mix(in srgb, var(--color-fg) ${Math.round(norm * 22)}%, transparent)`;
  }
  return <span className="text-[12px] font-semibold font-mono tabular-nums text-right block rounded px-1.5 py-px text-foreground" style={{ backgroundColor: bg }}>{col.format(value)}</span>;
}

function ColCell({ value, col, mode, changed }: { value: number; col: ColumnDef; mode: RenderMode; changed: boolean }) {
  if (value == null || isNaN(value)) return <span className="text-[11px] text-muted-fg/60 text-right block w-full">·</span>;
  if (mode === 'bar') return col.colorScale === 'diverging'
    ? <DivBar value={value} domain={col.domain || [-1, 1]} label={col.format(value)} changed={changed} />
    : <PosBar value={value} domain={col.domain || [0, 1]} label={col.format(value)} />;
  if (mode === 'heatmap') return <HeatCell value={value} col={col} />;
  return <NumCell value={value} col={col} changed={changed} />;
}

// ── Popover genérico (portal, cierra en click fuera) ──

function usePopover() {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; right: number }>({ top: 0, right: 0 });

  useEffect(() => {
    if (!open) return;
    const update = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (r) setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
    };
    update();
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node) || btnRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('resize', update);
    return () => { document.removeEventListener('mousedown', onDoc); window.removeEventListener('resize', update); };
  }, [open]);

  return { open, setOpen, btnRef, menuRef, pos };
}

// ── Segmented control mono ──

function Seg<T extends string>({ options, value, onChange, small }: {
  options: { key: T; label: string }[]; value: T; onChange: (v: T) => void; small?: boolean;
}) {
  return (
    <div className="flex bg-surface-inset border border-border rounded-md p-px gap-px flex-wrap">
      {options.map(o => (
        <button key={o.key} onClick={() => onChange(o.key)}
          className={`${small ? 'px-1.5 py-0.5 text-[9.5px]' : 'px-2 py-0.5 text-[10.5px]'} font-semibold rounded-[5px] transition-colors whitespace-nowrap ${value === o.key ? 'bg-surface text-foreground shadow-sm' : 'text-muted-fg hover:text-foreground'
            }`}>{o.label}</button>
      ))}
    </div>
  );
}

// ── Panel de filtros ──

function FiltersPanel({ filters, onChange, presets, onSavePreset, onDeletePreset, onApplyPreset }: {
  filters: PulseFilters;
  onChange: (f: PulseFilters) => void;
  presets: FilterPreset[];
  onSavePreset: (name: string) => void;
  onDeletePreset: (name: string) => void;
  onApplyPreset: (p: FilterPreset) => void;
}) {
  const pop = usePopover();
  const n = countActiveFilters(filters);
  const [presetName, setPresetName] = useState('');

  const Row = ({ label, children }: { label: string; children: ReactNode }) => (
    <div className="flex items-center gap-2 px-3 py-1">
      <span className="text-[10.5px] font-semibold text-foreground/80 w-[92px] shrink-0">{label}</span>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );

  return (
    <>
      <button ref={pop.btnRef} onClick={() => pop.setOpen(o => !o)}
        className={`flex items-center gap-1.5 px-2 py-0.5 text-[10.5px] font-semibold rounded-md border transition-colors ${pop.open ? 'border-foreground text-foreground' : 'border-border text-muted-fg hover:text-foreground hover:border-foreground/50'}`}>
        <SlidersHorizontal className="w-3 h-3" />
        Filtros
        {n > 0 && <span className="text-[9px] font-extrabold font-mono rounded-full px-1.5 py-px" style={{ background: FG, color: 'var(--color-bg)' }}>{n}</span>}
      </button>
      {pop.open && createPortal(
        <div ref={pop.menuRef} style={{ position: 'fixed', top: pop.pos.top, right: pop.pos.right, zIndex: 1000 }}
          className="bg-surface border border-border rounded-lg shadow-2xl py-2 w-[320px]">
          {presets.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap px-3 pb-2 border-b border-border-subtle mb-1">
              {presets.map(p => (
                <span key={p.name} className="inline-flex items-center gap-1 border border-border rounded-full pl-2 pr-1 py-px text-[10px] font-semibold text-foreground/80 hover:border-foreground/60">
                  <button onClick={() => { onApplyPreset(p); pop.setOpen(false); }}>{p.name}</button>
                  <button onClick={() => onDeletePreset(p.name)} className="text-muted-fg hover:text-foreground px-0.5" title="Eliminar preset">
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <Row label="Market cap">
            <Seg small value={String(filters.minCap) as any} onChange={v => onChange({ ...filters, minCap: Number(v) })}
              options={[{ key: '0', label: 'Todos' }, { key: '300000000', label: '>300M' }, { key: '2000000000', label: '>2B' }, { key: '10000000000', label: '>10B' }, { key: '100000000000', label: '>100B' }] as any} />
          </Row>
          <Row label="RVOL medio ≥">
            <Seg small value={String(filters.minRvol) as any} onChange={v => onChange({ ...filters, minRvol: Number(v) })}
              options={[{ key: '0', label: 'Any' }, { key: '1', label: '1×' }, { key: '1.5', label: '1.5×' }, { key: '2', label: '2×' }] as any} />
          </Row>
          <Row label="Breadth">
            <Seg small value={filters.breadth} onChange={v => onChange({ ...filters, breadth: v })}
              options={[{ key: 'any', label: 'Any' }, { key: 'ge60', label: '≥60%' }, { key: 'ge50', label: '≥50%' }, { key: 'le40', label: '≤40%' }]} />
          </Row>
          <Row label="RSI diario">
            <Seg small value={filters.rsi} onChange={v => onChange({ ...filters, rsi: v })}
              options={[{ key: 'any', label: 'Any' }, { key: 'lt30', label: '<30' }, { key: 'mid', label: '30–70' }, { key: 'gt70', label: '>70' }]} />
          </Row>
          <Row label="Divergencias">
            <Seg small value={filters.divergentOnly ? 'y' : 'n'} onChange={v => onChange({ ...filters, divergentOnly: v === 'y' })}
              options={[{ key: 'n', label: 'Todas' }, { key: 'y', label: 'Solo divergentes' }]} />
          </Row>
          <div className="flex items-center gap-1.5 px-3 pt-2 mt-1 border-t border-border-subtle">
            <input value={presetName} onChange={e => setPresetName(e.target.value)} placeholder="Nombre del preset…"
              className="flex-1 min-w-0 h-[22px] text-[10.5px] px-1.5 rounded border border-border bg-surface text-foreground placeholder:text-muted-fg/50 focus:border-foreground outline-none" />
            <button
              disabled={!presetName.trim() || n === 0}
              onClick={() => { onSavePreset(presetName.trim()); setPresetName(''); }}
              className="text-[10px] font-bold px-2 py-1 rounded disabled:opacity-40"
              style={{ background: FG, color: 'var(--color-bg)' }}>Guardar</button>
            <button onClick={() => onChange(DEFAULT_FILTERS)} className="text-[10px] text-muted-fg hover:text-foreground px-1">Limpiar</button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

// ── Gestor de columnas (presets + grupos + modo explícito) ──

function ColumnsPanel({ visCols, modes, preset, onSetPreset, onToggleCol, onSetMode, allCols }: {
  visCols: string[]; modes: Record<string, RenderMode>; preset: string;
  onSetPreset: (id: string) => void;
  onToggleCol: (key: string) => void;
  onSetMode: (key: string, m: RenderMode) => void;
  allCols: ColumnDef[];
}) {
  const pop = usePopover();
  const presetLabel = COLUMN_PRESETS.find(p => p.id === preset)?.label || 'Custom';
  const byKey = useMemo(() => new Map(allCols.map(c => [c.key, c])), [allCols]);

  return (
    <>
      <button ref={pop.btnRef} onClick={() => pop.setOpen(o => !o)}
        className={`flex items-center gap-1.5 px-2 py-0.5 text-[10.5px] font-semibold rounded-md border transition-colors ${pop.open ? 'border-foreground text-foreground' : 'border-border text-muted-fg hover:text-foreground hover:border-foreground/50'}`}>
        <Columns3 className="w-3 h-3" />
        {presetLabel}
        <ChevronDown className="w-2.5 h-2.5 opacity-60" />
      </button>
      {pop.open && createPortal(
        <div ref={pop.menuRef} style={{ position: 'fixed', top: pop.pos.top, right: pop.pos.right, zIndex: 1000 }}
          className="bg-surface border border-border rounded-lg shadow-2xl py-2 w-[340px] max-h-[420px] overflow-auto pulse-scroll">
          <div className="flex items-center gap-1.5 flex-wrap px-3 pb-2 border-b border-border-subtle">
            {COLUMN_PRESETS.map(p => (
              <button key={p.id} onClick={() => onSetPreset(p.id)}
                className={`text-[10px] font-semibold border rounded-full px-2.5 py-0.5 transition-colors ${preset === p.id ? 'border-foreground text-foreground bg-surface-inset' : 'border-border text-muted-fg hover:text-foreground'}`}>
                {p.label}
              </button>
            ))}
            <span className={`text-[10px] font-semibold border rounded-full px-2.5 py-0.5 ${preset === 'custom' ? 'border-foreground text-foreground bg-surface-inset' : 'border-border-subtle text-muted-fg/50'}`}>Custom</span>
          </div>
          {COLUMN_GROUPS.map(g => (
            <div key={g.id} className="px-3 pt-2">
              <div className="text-[9px] font-bold uppercase tracking-[0.12em] text-muted-fg mb-1">{g.label}</div>
              {g.keys.map(k => {
                const col = byKey.get(k);
                if (!col) return null;
                const on = visCols.includes(k);
                const mode = modes[k] || col.defaultMode;
                return (
                  <div key={k} className="flex items-center gap-2 py-[3px] rounded hover:bg-surface-hover px-1 -mx-1">
                    <button onClick={() => onToggleCol(k)}
                      className="w-[13px] h-[13px] rounded-[3.5px] border flex items-center justify-center shrink-0"
                      style={on ? { background: FG, borderColor: FG } : { borderColor: 'var(--color-border)' }}
                      title={col.description}>
                      {on && <span className="text-[8px] font-black" style={{ color: 'var(--color-bg)' }}>✓</span>}
                    </button>
                    <span className={`text-[11px] font-medium flex-1 min-w-0 ${on ? 'text-foreground' : 'text-muted-fg'}`} title={col.description}>{col.label}</span>
                    {on && (
                      <div className="flex bg-surface-inset rounded p-px gap-px shrink-0">
                        {(['bar', 'numeric', 'heatmap'] as RenderMode[]).map(m => (
                          <button key={m} onClick={() => onSetMode(k, m)}
                            className={`px-1 py-px text-[8px] font-black font-mono rounded-sm transition-colors ${mode === m ? 'bg-surface text-foreground shadow-sm' : 'text-muted-fg hover:text-foreground'}`}>
                            {m === 'bar' ? 'BAR' : m === 'numeric' ? 'NUM' : 'HEAT'}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>,
        document.body
      )}
    </>
  );
}

// ── Market strip ──

function MarketStrip({ data, accel }: { data: PerformanceEntry[]; accel: number }) {
  const m = useMemo(() => {
    if (!data.length) return null;
    const totalCount = data.reduce((s, d) => s + d.count, 0);
    const totalAdv = data.reduce((s, d) => s + d.advancing, 0);
    const totalDec = data.reduce((s, d) => s + d.declining, 0);
    const totalMcap = data.reduce((s, d) => s + d.total_market_cap, 0);
    const totalDv = data.reduce((s, d) => s + d.total_dollar_volume, 0);
    const wtd = totalMcap > 0 ? data.reduce((s, d) => s + d.weighted_change * d.total_market_cap, 0) / totalMcap : 0;
    const eq = totalCount > 0 ? data.reduce((s, d) => s + d.avg_change * d.count, 0) / totalCount : 0;
    const volPct = totalCount > 0 ? data.reduce((s, d) => s + (d.avg_vol_today_pct || 0) * d.count, 0) / totalCount : 0;
    const rvol = totalCount > 0 ? data.reduce((s, d) => s + (d.avg_rvol || 0) * d.count, 0) / totalCount : 0;
    return { totalCount, totalAdv, totalDec, totalDv, wtd, eq, spread: wtd - eq, volPct, rvol, adRatio: totalDec > 0 ? totalAdv / totalDec : 0 };
  }, [data]);

  if (!m) return null;
  const pct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const advPct = (m.totalAdv + m.totalDec) > 0 ? (m.totalAdv / (m.totalAdv + m.totalDec)) * 100 : 50;

  const Kpi = ({ label, children, sub }: { label: string; children: ReactNode; sub?: ReactNode }) => (
    <div className="px-3 py-1.5 border-r border-b border-border-subtle min-w-0">
      <div className="text-[8.5px] font-bold uppercase tracking-[0.1em] text-muted-fg leading-tight">{label}</div>
      <div className="text-[13.5px] font-bold font-mono tabular-nums leading-tight">{children}</div>
      {sub && <div className="text-[9px] text-muted-fg font-mono tabular-nums leading-tight mt-px">{sub}</div>}
    </div>
  );

  return (
    <div className="grid border-b border-border shrink-0" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(128px, 1fr))' }}>
      <Kpi label="Cap-Weighted" sub={`${m.totalCount.toLocaleString()} tickers`}>
        <span style={{ color: m.wtd >= 0 ? UP : DOWN }}>{pct(m.wtd)}</span>
      </Kpi>
      <Kpi label="Equal-Weight" sub={`spread ${pct(m.spread)}`}>
        <span style={{ color: m.eq >= 0 ? UP : DOWN }}>{pct(m.eq)}</span>
      </Kpi>
      <Kpi label="Adv / Dec" sub={<span>{m.totalAdv.toLocaleString()} ▲ · {m.totalDec.toLocaleString()} ▼</span>}>
        {m.adRatio.toFixed(2)}
        <div className="flex h-[3px] rounded-full overflow-hidden mt-[3px]">
          <span style={{ width: `${advPct}%`, background: UP }} />
          <span style={{ width: `${100 - advPct}%`, background: DOWN }} />
        </div>
      </Kpi>
      <Kpi label="$ Volumen" sub={`RVOL medio ${m.rvol.toFixed(1)}×`}>{fmtBig(m.totalDv)}</Kpi>
      <Kpi label="Vol. del día" sub={
        <div className="h-[3px] rounded-full bg-surface-inset overflow-hidden mt-[3px]">
          <div className="h-full rounded-full" style={{ width: `${clamp(m.volPct, 0, 100)}%`, background: FG }} />
        </div>
      }>{m.volPct.toFixed(0)}%</Kpi>
      <Kpi label="Momentum" sub={`Δ ${accel >= 0 ? '+' : ''}${accel.toFixed(2)} / 3s`}>
        <span style={{ color: accel >= 0 ? UP : DOWN }}>{accel >= 0 ? '▲' : '▼'} {Math.abs(accel) < 0.005 ? 'estable' : accel > 0 ? 'acelerando' : 'frenando'}</span>
      </Kpi>
    </div>
  );
}

// ── Grid header / rows ──

function GridHeader({ columns, sortKey, sortDir, onSort, onRemove, firstColLabel, totalWidth }: {
  columns: ColumnDef[]; sortKey: string; sortDir: 'asc' | 'desc';
  onSort: (k: string) => void; onRemove?: (k: string) => void;
  firstColLabel: string; totalWidth: number;
}) {
  return (
    <div className="sticky top-0 z-20 flex bg-surface-inset border-b border-border" style={{ height: HEADER_H, minWidth: totalWidth }}>
      <div className="sticky left-0 z-30 flex items-center bg-surface-inset border-r border-border px-3 shrink-0 shadow-[3px_0_6px_-3px_rgba(0,0,0,0.45)]" style={{ width: NAME_W }}>
        <span className="text-[10px] font-bold text-muted-fg uppercase tracking-[0.14em]">{firstColLabel}</span>
      </div>
      {columns.map(col => {
        const active = sortKey === col.key;
        return (
          <div key={col.key} className="group/hd relative flex items-center justify-end border-r border-border-subtle/70 px-2 shrink-0" style={{ width: COL_W }}>
            <button onClick={() => onSort(col.key)} className="flex items-center gap-1 min-w-0" title={col.description}>
              {active && (sortDir === 'desc' ? <ArrowDown className="w-3 h-3 text-foreground shrink-0" /> : <ArrowUp className="w-3 h-3 text-foreground shrink-0" />)}
              {/* Nombre completo, hasta 2 líneas — nada de abreviaturas crípticas */}
              <span className={`text-[9.5px] font-bold uppercase tracking-[0.05em] leading-[1.2] text-right line-clamp-2 transition-colors ${active ? 'text-foreground' : 'text-muted-fg hover:text-foreground'}`}>{col.label}</span>
            </button>
            {onRemove && (
              <div className="absolute right-1 top-0 bottom-0 hidden group-hover/hd:flex items-center bg-surface-inset pl-2">
                <button onClick={() => onRemove(col.key)} className="w-4 h-4 rounded text-muted-fg hover:text-red-500 hover:bg-red-500/10 transition-colors flex items-center justify-center" title="Quitar columna">
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>
        );
      })}
      <div className="flex-1" />
    </div>
  );
}

function MoversStrip({ entry, onOpenTicker, onOpenGroup }: {
  entry: PerformanceEntry; onOpenTicker?: (s: string) => void; onOpenGroup: () => void;
}) {
  const g = entry.movers?.gainers?.slice(0, 4) || [];
  const l = entry.movers?.losers?.slice(0, 3) || [];
  const chip = (t: DrilldownTicker, up: boolean) => (
    <button key={t.symbol} onClick={(e) => { e.stopPropagation(); onOpenTicker?.(t.symbol); }}
      className="inline-flex items-baseline gap-1 rounded px-1.5 py-px text-[10px] font-bold font-mono whitespace-nowrap"
      style={{ background: up ? UP_SOFT : DOWN_SOFT }}>
      <span className="text-foreground">{t.symbol}</span>
      <span style={{ color: up ? UP : DOWN }}>{`${(t.change_percent ?? 0) >= 0 ? '+' : ''}${(t.change_percent ?? 0).toFixed(1)}%`}</span>
    </button>
  );
  return (
    <div className="flex items-center gap-1.5 px-3 h-full bg-surface-inset/60 overflow-hidden">
      {g.length > 0 && <span className="text-[8px] font-black uppercase tracking-[0.1em] text-muted-fg shrink-0">G</span>}
      {g.map(t => chip(t, true))}
      {l.length > 0 && <span className="text-[8px] font-black uppercase tracking-[0.1em] text-muted-fg shrink-0 ml-1.5">L</span>}
      {l.map(t => chip(t, false))}
      {g.length === 0 && l.length === 0 && <span className="text-[10px] text-muted-fg">Sin movers destacados</span>}
      <button onClick={(e) => { e.stopPropagation(); onOpenGroup(); }}
        className="ml-auto shrink-0 text-[10px] font-semibold text-foreground underline underline-offset-2 decoration-border hover:decoration-foreground">
        Ver los {entry.count} →
      </button>
    </div>
  );
}

// ── Drilldown table (compartida por panel lateral y modo estrecho) ──

function DrilldownTable({ tickers, cols, modes, sortKey, sortDir, onSort, onRemoveCol, onOpenTicker, loading }: {
  tickers: DrilldownTicker[]; cols: ColumnDef[]; modes: Record<string, RenderMode>;
  sortKey: string; sortDir: 'asc' | 'desc'; onSort: (k: string) => void; onRemoveCol?: (k: string) => void;
  onOpenTicker?: (s: string) => void; loading: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: tickers.length, getScrollElement: () => ref.current, estimateSize: () => ROW_H, overscan: 14 });
  const totalWidth = NAME_W + cols.length * COL_W;
  const items = virt.getVirtualItems();

  return (
    <div ref={ref} className="flex-1 overflow-auto pulse-scroll">
      <div style={{ minWidth: totalWidth, position: 'relative' }}>
        <GridHeader columns={cols} sortKey={sortKey} sortDir={sortDir} onSort={onSort} onRemove={onRemoveCol} firstColLabel="Símbolo" totalWidth={totalWidth} />
        {loading && !tickers.length ? (
          <div className="flex items-center justify-center py-16"><RefreshCw className="w-4 h-4 text-muted-fg animate-spin" /></div>
        ) : !tickers.length ? (
          <div className="px-4 py-10 text-center text-[11px] text-muted-fg">Sin tickers que cumplan el filtro</div>
        ) : (
          <div style={{ height: virt.getTotalSize(), position: 'relative', minWidth: totalWidth }}>
            {items.map(vi => {
              const t = tickers[vi.index];
              return (
                <div key={t.symbol} className="absolute left-0" style={{ top: 0, transform: `translateY(${vi.start}px)`, height: vi.size, minWidth: totalWidth, width: '100%' }}>
                  <div className="group/row flex items-stretch h-full border-b border-border-subtle hover:bg-surface-hover transition-colors" style={{ minWidth: totalWidth }}>
                    <div className="sticky left-0 z-10 flex items-center bg-surface group-hover/row:bg-surface-hover border-r border-border px-3 shrink-0 transition-colors shadow-[3px_0_6px_-3px_rgba(0,0,0,0.35)]" style={{ width: NAME_W }}>
                      <button onClick={() => onOpenTicker?.(t.symbol)} className="flex items-center gap-1 w-full min-w-0 text-left" title={`Abrir ${t.symbol}`}>
                        <span className="text-[11px] font-bold text-foreground underline underline-offset-[3px] decoration-border group-hover/row:decoration-foreground/60 truncate">{t.symbol}</span>
                        <ExternalLink className="w-2.5 h-2.5 text-muted-fg/50 group-hover/row:text-foreground transition-colors shrink-0" />
                      </button>
                    </div>
                    {cols.map(col => (
                      <div key={col.key} className="flex items-center justify-end border-r border-border-subtle/40 px-2 shrink-0" style={{ width: COL_W }}>
                        <ColCell value={(t as any)[col.key]} col={col} mode={modes[col.key] || col.defaultMode} changed={t._changedKeys?.has(col.key) || false} />
                      </div>
                    ))}
                    <div className="flex-1" />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

const TABS: { key: PulseTab; label: string }[] = [
  { key: 'sectors', label: 'Sectores' },
  { key: 'industries', label: 'Industrias' },
  { key: 'themes', label: 'Temas' },
];

type DdTab = 'all' | 'gainers' | 'losers' | 'rvol';

// ── Main ──

export function MarketPulseContent({ onOpenTicker }: { onOpenTicker?: (sym: string) => void }) {
  const [tab, setTab] = useState<PulseTab>('sectors');
  const [dd, setDd] = useState<{ type: string; name: string; label: string; avgChange: number } | null>(null);
  const [ddTab, setDdTab] = useState<DdTab>('all');
  const [expanded, setExpanded] = useState<string | null>(null);

  // Ancho del contenedor: decide split lateral vs drilldown a pantalla completa
  const rootRef = useRef<HTMLDivElement>(null);
  const [rootW, setRootW] = useState(0);
  useEffect(() => {
    if (!rootRef.current) return;
    const ro = new ResizeObserver(entries => { for (const e of entries) setRootW(e.contentRect.width); });
    ro.observe(rootRef.current);
    return () => ro.disconnect();
  }, []);
  const wide = rootW >= PANEL_MIN_CONTENT + PANEL_W;

  // ── Filtros ──
  const [filters, setFilters] = useState<PulseFilters>(() => {
    const p = loadPrefs();
    if (p.filters) return { ...DEFAULT_FILTERS, ...p.filters };
    return { ...DEFAULT_FILTERS, minCap: p.minCap || 0 };
  });
  const [filterPresets, setFilterPresets] = useState<FilterPreset[]>(() => loadPrefs().filterPresets || []);

  // ── Ticker search ──
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { data: tickerCtx, loading: searchLoading, error: searchError, fetchContext, clear: clearSearch } = useTickerContext();

  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      fetchContext(searchInput.trim());
      setDd(null);
    }
  }, [searchInput, fetchContext]);

  const handleSearchClear = useCallback(() => {
    setSearchInput('');
    clearSearch();
    setSearchOpen(false);
  }, [clearSearch]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  // Type-ahead: teclear con la ventana enfocada abre el buscador
  const mpWindowId = useCurrentWindowId();
  useEffect(() => {
    if (!mpWindowId) return;
    return registerTickerSearch(mpWindowId, {
      getInput: () => searchInputRef.current,
      type: (char: string) => {
        setSearchOpen(true);
        setSearchInput(char.toUpperCase());
        requestAnimationFrame(() => searchInputRef.current?.focus());
      },
    });
  }, [mpWindowId]);

  // ── Vistas ──
  const [activeView, setActiveView] = useState<PulseViewType>(() => loadPrefs().view || 'table');
  const handleViewChange = useCallback((v: PulseViewType) => {
    setActiveView(v);
  }, []);

  // ── Columnas (presets + custom) ──
  const [colPreset, setColPreset] = useState<string>(() => loadPrefs().colPreset || (loadPrefs().visCols ? 'custom' : 'momentum'));
  const [visCols, setVisCols] = useState<string[]>(() => {
    const p = loadPrefs();
    if (p.visCols) return p.visCols;
    return COLUMN_PRESETS[0].cols;
  });
  const [modes, setModes] = useState<Record<string, RenderMode>>(() => (loadPrefs().modes || {}) as Record<string, RenderMode>);

  const [sortKey, setSortKey] = useState('weighted_change');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Drilldown columns
  const [ddSortKey, setDdSortKey] = useState('change_percent');
  const [ddSortDir, setDdSortDir] = useState<'asc' | 'desc'>('desc');
  const [ddVisCols, setDdVisCols] = useState<string[]>(() => loadPrefs().ddVisCols || DEFAULT_DD_COLUMNS);
  const [ddModes, setDdModes] = useState<Record<string, RenderMode>>(() => (loadPrefs().ddModes || {}) as Record<string, RenderMode>);

  const { data, loading, error, lastUpdate, totalTickers, refetch } = useMarketPulse({ tab, refreshInterval: 3000, minMarketCap: filters.minCap || undefined });
  const { data: ddData, loading: ddLoad, total: ddTotal, fetchDrilldown, reset: resetDrilldown } = useDrilldown();

  // Drilldown polling
  const ddRef = useRef(dd); ddRef.current = dd;
  const ddIntRef = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => {
    if (ddIntRef.current) clearInterval(ddIntRef.current);
    if (dd) {
      ddIntRef.current = setInterval(() => {
        const d = ddRef.current;
        if (d) fetchDrilldown(d.type, d.name, d.avgChange, filters.minCap || undefined);
      }, 3000);
    }
    return () => { if (ddIntRef.current) clearInterval(ddIntRef.current); };
  }, [dd, fetchDrilldown, filters.minCap]);

  // Persistencia
  useEffect(() => {
    savePrefs({
      visCols, ddVisCols,
      modes: modes as Record<string, string>, ddModes: ddModes as Record<string, string>,
      minCap: filters.minCap, view: activeView, colPreset, filters, filterPresets,
    });
  }, [visCols, ddVisCols, modes, ddModes, activeView, colPreset, filters, filterPresets]);

  // Columnas resueltas
  const cols = useMemo(() => visCols.map(k => ALL_COLUMNS.find(c => c.key === k)!).filter(Boolean), [visCols]);
  const ddCols = useMemo(() => ddVisCols.map(k => DD_COLUMNS.find(c => c.key === k)!).filter(Boolean), [ddVisCols]);

  // ── Filtrado client-side + orden ──
  const filtered = useMemo(() => {
    let rows = data;
    if (filters.minRvol > 0) rows = rows.filter(r => (r.avg_rvol || 0) >= filters.minRvol);
    if (filters.breadth === 'ge60') rows = rows.filter(r => (r.breadth || 0) >= 0.6);
    if (filters.breadth === 'ge50') rows = rows.filter(r => (r.breadth || 0) >= 0.5);
    if (filters.breadth === 'le40') rows = rows.filter(r => (r.breadth || 0) <= 0.4);
    if (filters.rsi === 'lt30') rows = rows.filter(r => (r.avg_daily_rsi || 50) < 30);
    if (filters.rsi === 'mid') rows = rows.filter(r => (r.avg_daily_rsi || 50) >= 30 && (r.avg_daily_rsi || 50) <= 70);
    if (filters.rsi === 'gt70') rows = rows.filter(r => (r.avg_daily_rsi || 50) > 70);
    if (filters.divergentOnly) rows = rows.filter(r => r._divergence);
    return rows;
  }, [data, filters]);

  const sorted = useMemo(() => {
    if (!filtered.length) return filtered;
    return [...filtered].sort((a, b) => { const va = (a as any)[sortKey] ?? 0, vb = (b as any)[sortKey] ?? 0; return sortDir === 'desc' ? vb - va : va - vb; });
  }, [filtered, sortKey, sortDir]);

  // Momentum agregado (accel medio ponderado) para el strip
  const marketAccel = useMemo(() => {
    if (!data.length) return 0;
    const tot = data.reduce((s, d) => s + d.count, 0) || 1;
    return data.reduce((s, d) => s + (d._accel || 0) * d.count, 0) / tot;
  }, [data]);

  // Drilldown: orden + tabs
  const ddSorted = useMemo(() => {
    let rows = ddData;
    if (ddTab === 'gainers') rows = rows.filter(t => (t.change_percent || 0) > 0);
    if (ddTab === 'losers') rows = rows.filter(t => (t.change_percent || 0) < 0);
    if (ddTab === 'rvol') rows = rows.filter(t => (t.rvol || 0) >= 2);
    if (!rows.length) return rows;
    return [...rows].sort((a, b) => {
      if (ddSortKey === 'symbol') {
        const cmp = a.symbol.localeCompare(b.symbol);
        return ddSortDir === 'asc' ? cmp : -cmp;
      }
      const va = (a as any)[ddSortKey] ?? 0, vb = (b as any)[ddSortKey] ?? 0;
      return ddSortDir === 'desc' ? vb - va : va - vb;
    });
  }, [ddData, ddSortKey, ddSortDir, ddTab]);

  // Handlers
  const doSort = useCallback((k: string) => { setSortKey(p => { if (p === k) { setSortDir(d => d === 'desc' ? 'asc' : 'desc'); return p; } setSortDir('desc'); return k; }); }, []);
  const doDdSort = useCallback((k: string) => { setDdSortKey(p => { if (p === k) { setDdSortDir(d => d === 'desc' ? 'asc' : 'desc'); return p; } setDdSortDir('desc'); return k; }); }, []);

  const applyPresetCols = useCallback((id: string) => {
    const p = COLUMN_PRESETS.find(x => x.id === id);
    if (!p) return;
    setColPreset(id);
    setVisCols(p.cols);
  }, []);
  const toggleCol = useCallback((k: string) => {
    setColPreset('custom');
    setVisCols(prev => prev.includes(k) ? prev.filter(x => x !== k) : [...prev, k]);
  }, []);
  const setColMode = useCallback((k: string, m: RenderMode) => {
    setModes(prev => ({ ...prev, [k]: m }));
  }, []);
  const rmCol = useCallback((k: string) => { setColPreset('custom'); setVisCols(p => p.filter(x => x !== k)); }, []);
  const ddRmCol = useCallback((k: string) => { setDdVisCols(p => p.filter(x => x !== k)); }, []);

  const doSelect = useCallback((e: PerformanceEntry) => {
    const gt = tab === 'themes' ? 'theme' : tab === 'industries' ? 'industry' : 'sector';
    const avgChg = e.weighted_change || e.avg_change || 0;
    setDd({ type: gt, name: e.name, label: tab === 'themes' ? fmtTheme(e.name) : e.name, avgChange: avgChg });
    setDdTab('all');
    resetDrilldown();
    fetchDrilldown(gt, e.name, avgChg, filters.minCap || undefined);
  }, [tab, fetchDrilldown, resetDrilldown, filters.minCap]);

  const doCloseDd = useCallback(() => { setDd(null); setDdSortKey('change_percent'); setDdSortDir('desc'); }, []);
  const doTab = useCallback((t: PulseTab) => { setTab(t); setDd(null); setExpanded(null); }, []);

  // "actualizado hace Xs"
  const [nowTick, setNowTick] = useState(0);
  useEffect(() => { const t = setInterval(() => setNowTick(n => n + 1), 1000); return () => clearInterval(t); }, []);
  const agoSec = lastUpdate ? Math.max(0, Math.round(Date.now() / 1000 - lastUpdate)) : null;
  void nowTick;

  // Virtualizer principal (altura dinámica para la fila expandida de movers)
  const pRef = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => pRef.current,
    estimateSize: (i) => (expanded && sorted[i]?.name === expanded ? ROW_H + MOVERS_H : ROW_H),
    overscan: 12,
  });
  useEffect(() => { virt.measure(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [expanded, sorted.length]);

  const totalWidth = NAME_W + cols.length * COL_W;
  const activeFilterCount = countActiveFilters(filters);
  const firstColLabel = tab === 'themes' ? 'Tema' : tab === 'industries' ? 'Industria' : 'Sector';
  const sortCol = ALL_COLUMNS.find(c => c.key === sortKey);

  // ── Chips de filtros activos ──
  const filterChips: { label: string; clear: () => void }[] = [];
  if (filters.minCap > 0) filterChips.push({ label: capLabel(filters.minCap), clear: () => setFilters(f => ({ ...f, minCap: 0 })) });
  if (filters.minRvol > 0) filterChips.push({ label: `RVOL ≥ ${filters.minRvol}×`, clear: () => setFilters(f => ({ ...f, minRvol: 0 })) });
  if (filters.breadth !== 'any') filterChips.push({ label: BREADTH_LABEL[filters.breadth], clear: () => setFilters(f => ({ ...f, breadth: 'any' })) });
  if (filters.rsi !== 'any') filterChips.push({ label: RSI_LABEL[filters.rsi], clear: () => setFilters(f => ({ ...f, rsi: 'any' })) });
  if (filters.divergentOnly) filterChips.push({ label: 'Solo divergencias', clear: () => setFilters(f => ({ ...f, divergentOnly: false })) });

  // ── First cell del grid principal ──
  const renderGroupFirst = useCallback((entry: PerformanceEntry, isTheme: boolean): ReactNode => {
    const name = isTheme ? fmtTheme(entry.name) : entry.name;
    const isExp = expanded === entry.name;
    return (
      <div className="flex items-center gap-1.5 w-full min-w-0">
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(p => p === entry.name ? null : entry.name); }}
          className="shrink-0 w-4 h-4 flex items-center justify-center rounded hover:bg-surface-inset text-muted-fg hover:text-foreground transition-colors"
          title={isExp ? 'Ocultar movers' : 'Ver movers del grupo'}>
          <ChevronRight className={`w-3 h-3 transition-transform ${isExp ? 'rotate-90' : ''}`} />
        </button>
        <span className="text-[11px] font-semibold text-foreground truncate" title={name}>{name}</span>
        {entry._rankShift !== undefined && entry._rankShift !== 0 && (
          <span className="text-[8px] font-mono font-bold shrink-0" style={{ color: entry._rankShift > 0 ? UP : DOWN }}>
            {entry._rankShift > 0 ? `▲${entry._rankShift}` : `▼${Math.abs(entry._rankShift)}`}
          </span>
        )}
        {entry._divergence && (
          <span className="w-[7px] h-[7px] rounded-full border-[1.5px] border-foreground shrink-0" title="Divergencia de breadth: precio y amplitud no cuadran" />
        )}
        <span className="ml-auto text-[9px] text-muted-fg font-mono tabular-nums shrink-0">{entry.count}</span>
      </div>
    );
  }, [expanded]);

  const showFullDrilldown = dd && !wide;

  return (
    <div ref={rootRef} className="flex flex-col h-full bg-surface overflow-hidden">

      {/* ── Toolbar (sin chrome: el título/cerrar/pop-out los pone FloatingWindow) ── */}
      <div className="flex items-center gap-2 flex-wrap px-2.5 py-1.5 border-b border-border shrink-0">
        {tickerCtx ? (
          <>
            <button onClick={handleSearchClear} className="flex items-center gap-1 text-[11px] text-foreground/80 hover:text-foreground font-medium">
              <ArrowLeft className="w-3.5 h-3.5" /> Volver
            </button>
            <span className="text-[13px] font-black text-foreground">{tickerCtx.symbol}</span>
            <span className="text-[10px] text-muted-fg font-medium truncate">{tickerCtx.sector} · {tickerCtx.industry}</span>
          </>
        ) : showFullDrilldown ? (
          <>
            <button onClick={doCloseDd} className="flex items-center gap-1 text-[11px] text-foreground/80 hover:text-foreground font-medium">
              <ArrowLeft className="w-3.5 h-3.5" /> Volver
            </button>
            <span className="text-[12px] font-bold text-foreground truncate">{dd!.label}</span>
            <span className="text-[10px] text-muted-fg font-mono shrink-0">{ddTotal}</span>
            <span className="text-[10px] font-mono font-bold shrink-0" style={{ color: dd!.avgChange >= 0 ? UP : DOWN }}>
              avg {dd!.avgChange >= 0 ? '+' : ''}{dd!.avgChange.toFixed(2)}%
            </span>
          </>
        ) : (
          <>
            <Seg options={TABS.map(t => ({ key: t.key, label: t.label }))} value={tab} onChange={doTab} />
            <Seg small options={VIEW_DEFINITIONS.map(v => ({ key: v.key, label: v.shortLabel }))} value={activeView} onChange={handleViewChange} />
          </>
        )}

        <span className="flex-1 min-w-[8px]" />

        {!tickerCtx && (
          <>
            {searchOpen ? (
              <form onSubmit={handleSearch} className="flex items-center gap-1">
                <div className="relative">
                  <input
                    ref={searchInputRef}
                    value={searchInput}
                    onChange={e => setSearchInput(e.target.value.toUpperCase())}
                    placeholder="Ticker…"
                    className="w-[84px] h-[22px] text-[11px] font-mono font-semibold pl-1.5 pr-5 rounded border border-border focus:border-foreground outline-none bg-surface text-foreground placeholder:text-muted-fg/50"
                    maxLength={10}
                  />
                  {searchLoading && <RefreshCw className="absolute right-1 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-fg animate-spin" />}
                </div>
                <button type="button" onClick={handleSearchClear} className="p-0.5 hover:bg-surface-hover rounded">
                  <X className="w-3 h-3 text-muted-fg" />
                </button>
              </form>
            ) : (
              <button onClick={() => setSearchOpen(true)}
                className="flex items-center gap-1.5 px-2 py-0.5 text-[10.5px] font-semibold rounded-md border border-border text-muted-fg hover:text-foreground hover:border-foreground/50 transition-colors"
                title="Buscar ticker (o teclea directamente)">
                <Search className="w-3 h-3" /> Buscar
              </button>
            )}
            {searchError === 'not_found' && <span className="text-[9px] text-muted-fg font-medium">No encontrado</span>}
            {!showFullDrilldown && (
              <>
                <FiltersPanel
                  filters={filters}
                  onChange={setFilters}
                  presets={filterPresets}
                  onSavePreset={(name) => setFilterPresets(prev => [...prev.filter(p => p.name !== name), { name, filters }])}
                  onDeletePreset={(name) => setFilterPresets(prev => prev.filter(p => p.name !== name))}
                  onApplyPreset={(p) => setFilters({ ...DEFAULT_FILTERS, ...p.filters })}
                />
                <ColumnsPanel
                  visCols={visCols} modes={modes} preset={colPreset}
                  onSetPreset={applyPresetCols} onToggleCol={toggleCol} onSetMode={setColMode}
                  allCols={ALL_COLUMNS}
                />
              </>
            )}
          </>
        )}
      </div>

      {/* ── Market strip ── */}
      {!tickerCtx && !error && data.length > 0 && <MarketStrip data={data} accel={marketAccel} />}

      {/* ── Chips de filtros activos ── */}
      {!tickerCtx && !showFullDrilldown && filterChips.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap px-2.5 py-1 border-b border-border shrink-0">
          {filterChips.map(c => (
            <span key={c.label} className="inline-flex items-center gap-1.5 bg-surface-inset border border-border rounded-full pl-2 pr-1 py-px text-[10px] font-semibold font-mono">
              {c.label}
              <button onClick={c.clear} className="text-muted-fg hover:text-red-500 p-px" title="Quitar filtro">
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
          <button onClick={() => setFilters(DEFAULT_FILTERS)} className="text-[10px] text-muted-fg hover:text-foreground font-medium ml-1">Limpiar todo</button>
        </div>
      )}

      {/* ── Ticker Context (búsqueda) ── */}
      {tickerCtx && <TickerContextView data={tickerCtx} onOpenTicker={onOpenTicker} />}

      {error && !tickerCtx && (
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 text-center">
          <div className="w-10 h-10 rounded-full bg-surface-inset flex items-center justify-center mb-3">
            <RefreshCw className="w-5 h-5 text-muted-fg" />
          </div>
          <p className="text-[13px] font-medium text-foreground mb-1">Datos de mercado no disponibles</p>
          <p className="text-[11px] text-muted-fg mb-4">{error}</p>
          <button onClick={refetch} className="px-3 py-1.5 text-[11px] font-semibold rounded-md" style={{ background: FG, color: 'var(--color-bg)' }}>
            Reintentar
          </button>
        </div>
      )}

      {/* ── Contenido principal: vista + panel lateral ── */}
      {!error && !tickerCtx && !showFullDrilldown && (
        <div className="flex-1 flex min-h-0">
          <div className="flex-1 min-w-0 flex flex-col">
            {activeView === 'table' ? (
              <>
                <div ref={pRef} className="flex-1 overflow-auto pulse-scroll">
                  <div style={{ minWidth: totalWidth, position: 'relative' }}>
                    <GridHeader columns={cols} sortKey={sortKey} sortDir={sortDir} onSort={doSort} onRemove={rmCol} firstColLabel={firstColLabel} totalWidth={totalWidth} />
                    {loading && !sorted.length ? (
                      <div className="flex items-center justify-center py-20"><RefreshCw className="w-4 h-4 text-muted-fg animate-spin" /></div>
                    ) : !sorted.length ? (
                      <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
                        <p className="text-[13px] font-medium text-foreground mb-1">{data.length ? 'Ningún grupo pasa los filtros' : 'Mercado cerrado'}</p>
                        <p className="text-[11px] text-muted-fg">{data.length ? 'Relaja los filtros para ver grupos' : 'Los datos se refrescan al abrir el mercado'}</p>
                      </div>
                    ) : (
                      <div style={{ height: virt.getTotalSize(), position: 'relative', minWidth: totalWidth }}>
                        {virt.getVirtualItems().map(vi => {
                          const entry = sorted[vi.index];
                          const isExp = expanded === entry.name;
                          const isSel = dd?.name === entry.name;
                          return (
                            <div key={entry.name} className="absolute left-0" style={{ top: 0, transform: `translateY(${vi.start}px)`, height: vi.size, minWidth: totalWidth, width: '100%' }}>
                              <button
                                onClick={() => doSelect(entry)}
                                className={`group/row flex items-stretch w-full text-left border-b border-border-subtle transition-colors ${isSel ? 'bg-surface-hover shadow-[inset_2px_0_0_var(--color-fg)]' : 'hover:bg-surface-hover'}`}
                                style={{ minWidth: totalWidth, height: ROW_H }}
                              >
                                <div className={`sticky left-0 z-10 flex items-center border-r border-border px-2 shrink-0 transition-colors shadow-[3px_0_6px_-3px_rgba(0,0,0,0.35)] ${isSel ? 'bg-surface-hover' : 'bg-surface group-hover/row:bg-surface-hover'}`} style={{ width: NAME_W }}>
                                  {renderGroupFirst(entry, tab === 'themes')}
                                </div>
                                {cols.map(col => (
                                  <div key={col.key} className="flex items-center justify-end border-r border-border-subtle/40 px-2 shrink-0" style={{ width: COL_W }}>
                                    <ColCell value={(entry as any)[col.key]} col={col} mode={modes[col.key] || col.defaultMode} changed={entry._changedKeys?.has(col.key) || false} />
                                  </div>
                                ))}
                                <div className="flex-1" />
                              </button>
                              {isExp && (
                                <div style={{ height: MOVERS_H, minWidth: totalWidth }} className="border-b border-border-subtle">
                                  <MoversStrip entry={entry} onOpenTicker={onOpenTicker} onOpenGroup={() => doSelect(entry)} />
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
                {/* Statusbar */}
                <div className="flex items-center gap-3 flex-wrap px-3 py-1 border-t border-border bg-surface-hover shrink-0 text-[9.5px] font-mono text-muted-fg">
                  <span>{totalTickers > 0 ? `${totalTickers.toLocaleString()} tickers` : '—'} · {sorted.length} {firstColLabel.toLowerCase()}{sorted.length === 1 ? '' : 's'}</span>
                  {agoSec != null && <span>actualizado hace {agoSec} s</span>}
                  <span className="ml-auto">orden: {sortCol?.label || sortKey} {sortDir === 'desc' ? '↓' : '↑'}</span>
                </div>
              </>
            ) : (
              loading && !data.length ? (
                <div className="flex-1 flex items-center justify-center"><RefreshCw className="w-4 h-4 text-muted-fg animate-spin" /></div>
              ) : !sorted.length ? (
                <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 text-center">
                  <p className="text-[13px] font-medium text-foreground mb-1">{data.length ? 'Ningún grupo pasa los filtros' : 'Mercado cerrado'}</p>
                  <p className="text-[11px] text-muted-fg">{data.length ? 'Relaja los filtros para ver grupos' : 'Los datos se refrescan al abrir el mercado'}</p>
                </div>
              ) : (
                <>
                  {activeView === 'overview' && <OverviewView data={sorted} activeTab={tab} onSelect={doSelect} />}
                  {activeView === 'treemap' && <TreemapView data={sorted} activeTab={tab} onSelect={doSelect} />}
                  {activeView === 'bubble' && <BubbleScatterView data={sorted} activeTab={tab} onSelect={doSelect} />}
                  {activeView === 'rotation' && <RotationBarsView data={sorted} activeTab={tab} onSelect={doSelect} />}
                  {activeView === 'breadth' && <BreadthMonitorView data={sorted} activeTab={tab} onSelect={doSelect} />}
                  {activeView === 'rrg' && <RRGView data={sorted} activeTab={tab} onSelect={doSelect} />}
                </>
              )
            )}
          </div>

          {/* ── Panel lateral de drilldown ── */}
          {dd && wide && (
            <div className="flex flex-col border-l border-border shrink-0 min-h-0" style={{ width: PANEL_W }}>
              <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
                <span className="text-[12px] font-bold text-foreground truncate" title={dd.label}>{dd.label}</span>
                <span className="text-[9.5px] text-muted-fg font-mono shrink-0">{ddTotal} tickers</span>
                <span className="text-[10.5px] font-mono font-bold shrink-0" style={{ color: dd.avgChange >= 0 ? UP : DOWN }}>
                  {dd.avgChange >= 0 ? '+' : ''}{dd.avgChange.toFixed(2)}%
                </span>
                <button onClick={doCloseDd} className="ml-auto p-0.5 rounded hover:bg-red-500/10 text-muted-fg hover:text-red-500 transition-colors" title="Cerrar panel">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex gap-0.5 px-2 pt-1 border-b border-border shrink-0">
                {([['all', 'Todos'], ['gainers', 'Gainers'], ['losers', 'Losers'], ['rvol', 'RVOL ≥ 2×']] as [DdTab, string][]).map(([k, l]) => (
                  <button key={k} onClick={() => setDdTab(k)}
                    className={`px-2 pb-1 pt-0.5 text-[10px] font-semibold border-b-2 transition-colors ${ddTab === k ? 'border-foreground text-foreground' : 'border-transparent text-muted-fg hover:text-foreground'}`}>
                    {l}
                  </button>
                ))}
              </div>
              <DrilldownTable
                tickers={ddSorted} cols={ddCols} modes={ddModes}
                sortKey={ddSortKey} sortDir={ddSortDir} onSort={doDdSort} onRemoveCol={ddRmCol}
                onOpenTicker={onOpenTicker} loading={ddLoad}
              />
              <div className="flex items-center px-3 py-1 border-t border-border bg-surface-hover shrink-0 text-[9.5px] font-mono text-muted-fg">
                <span>{ddSorted.length} de {ddTotal}</span>
                <span className="ml-auto">clic en símbolo → chart</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Drilldown a pantalla completa (ventana estrecha) ── */}
      {!error && !tickerCtx && showFullDrilldown && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex gap-0.5 px-2 pt-1 border-b border-border shrink-0">
            {([['all', 'Todos'], ['gainers', 'Gainers'], ['losers', 'Losers'], ['rvol', 'RVOL ≥ 2×']] as [DdTab, string][]).map(([k, l]) => (
              <button key={k} onClick={() => setDdTab(k)}
                className={`px-2 pb-1 pt-0.5 text-[10px] font-semibold border-b-2 transition-colors ${ddTab === k ? 'border-foreground text-foreground' : 'border-transparent text-muted-fg hover:text-foreground'}`}>
                {l}
              </button>
            ))}
          </div>
          <DrilldownTable
            tickers={ddSorted} cols={ddCols} modes={ddModes}
            sortKey={ddSortKey} sortDir={ddSortDir} onSort={doDdSort} onRemoveCol={ddRmCol}
            onOpenTicker={onOpenTicker} loading={ddLoad}
          />
          <div className="flex items-center px-3 py-1 border-t border-border bg-surface-hover shrink-0 text-[9.5px] font-mono text-muted-fg">
            <span>{ddSorted.length} de {ddTotal}</span>
            <span className="ml-auto">clic en símbolo → chart</span>
          </div>
        </div>
      )}
    </div>
  );
}
