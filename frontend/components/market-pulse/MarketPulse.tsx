'use client';

import { useState, useCallback, useMemo, useRef, useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useVirtualizer, type Virtualizer } from '@tanstack/react-virtual';
import { useMarketPulse, useDrilldown, useTickerContext, type PulseTab, type PerformanceEntry, type DrilldownTicker } from '@/hooks/useMarketPulse';
import { useCloseCurrentWindow } from '@/contexts/FloatingWindowContext';
import { ArrowLeft, RefreshCw, ChevronRight, ChevronDown, ArrowDown, ArrowUp, Plus, X, GripHorizontal, ExternalLink, Search, Columns3 } from 'lucide-react';
import { ALL_COLUMNS, DEFAULT_COLUMNS, DD_COLUMNS, DEFAULT_DD_COLUMNS, type ColumnDef, type RenderMode } from './columns';
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

// ── Grid layout constants (px) ──
const NAME_W = 196;   // frozen first column
const COL_W = 116;    // each data column
const HEADER_H = 30;
const ROW_H = 28;

// ── LocalStorage persistence for user preferences ──
const LS_KEY = 'market-pulse-prefs';
interface PulsePrefs {
  visCols?: string[];
  ddVisCols?: string[];
  modes?: Record<string, string>;
  ddModes?: Record<string, string>;
  minCap?: number;
  view?: PulseViewType;
}
function loadPrefs(): PulsePrefs {
  try { const s = localStorage.getItem(LS_KEY); return s ? JSON.parse(s) : {}; } catch { return {}; }
}
function savePrefs(p: PulsePrefs) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(p)); } catch { }
}

const BAR_BLUE = '#2563eb';
const BAR_PINK = '#ec4899';

function LiveDot({ tick }: { tick: number }) {
  const [on, setOn] = useState(false);
  const prev = useRef(tick);
  useEffect(() => { if (tick !== prev.current) { prev.current = tick; setOn(true); const t = setTimeout(() => setOn(false), 500); return () => clearTimeout(t); } }, [tick]);
  return (
    <span className="relative flex items-center">
      <span className={`w-[5px] h-[5px] rounded-full ${on ? 'bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.7)]' : 'bg-emerald-500'}`} />
      {on && <span className="absolute w-[5px] h-[5px] rounded-full bg-emerald-400 animate-ping" />}
    </span>
  );
}

// ── Shared cell renderers ──

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
          style={{ width: `${pct}%`, backgroundColor: pos ? BAR_BLUE : BAR_PINK }} />
      </div>
      <span className={`text-[11px] font-semibold font-mono tabular-nums w-[46px] text-right shrink-0 transition-colors duration-400 ${flash ? (pos ? 'text-primary' : 'text-pink-800') : (pos ? 'text-primary' : 'text-pink-600')
        }`}>{label}</span>
    </div>
  );
}

function PosBar({ value, domain, label }: { value: number; domain: [number, number]; label: string }) {
  const norm = clamp((value - domain[0]) / ((domain[1] - domain[0]) || 1), 0, 1);
  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0 h-full">
      <div className="relative flex-1 h-[13px] rounded-[3px] overflow-hidden bg-surface-inset">
        <div className="absolute top-0 bottom-0 left-0 rounded-[3px] transition-all duration-500 ease-out" style={{ width: `${norm * 100}%`, backgroundColor: BAR_BLUE }} />
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
    <span className={`text-[12px] font-semibold font-mono tabular-nums text-right block transition-colors duration-400 ${flash ? (pos ? 'text-primary' : 'text-pink-800') : (div ? (pos ? 'text-primary' : 'text-red-500') : 'text-foreground')
      }`}>{col.format(value)}</span>
  );
}

function HeatCell({ value, col }: { value: number; col: ColumnDef }) {
  const domain = col.domain || [0, 100];
  let bg: string;
  if (col.colorScale === 'diverging') {
    const mid = (domain[0] + domain[1]) / 2, range = (domain[1] - domain[0]) / 2 || 1;
    const norm = clamp((value - mid) / range, -1, 1);
    bg = norm >= 0 ? `rgba(37,99,235,${(Math.abs(norm) * 0.45).toFixed(2)})` : `rgba(236,72,153,${(Math.abs(norm) * 0.4).toFixed(2)})`;
  } else {
    const norm = clamp((value - domain[0]) / ((domain[1] - domain[0]) || 1), 0, 1);
    bg = `rgba(37,99,235,${(norm * 0.45).toFixed(2)})`;
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

// ── Column Menu (portal — never clipped by the scroll container) ──

function ColumnMenu({ visible, allCols, onAdd }: { visible: string[]; allCols: ColumnDef[]; onAdd: (k: string) => void }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; right: number }>({ top: 0, right: 0 });
  const avail = allCols.filter(c => !visible.includes(c.key));

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

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setOpen(o => !o)}
        onMouseDown={e => e.stopPropagation()}
        className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors ${open ? 'bg-primary/10 text-primary' : 'text-muted-fg hover:text-foreground hover:bg-surface-inset'}`}
        title="Add / manage columns"
      >
        <Columns3 className="w-3.5 h-3.5" />
      </button>
      {open && createPortal(
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: pos.top, right: pos.right, zIndex: 1000 }}
          className="bg-surface border border-border rounded-lg shadow-2xl py-1 w-[230px] max-h-[340px] overflow-auto pulse-scroll"
        >
          <div className="px-3 py-1 text-[9px] font-bold uppercase tracking-[0.14em] text-muted-fg">Add column</div>
          {avail.length === 0 && <div className="px-3 py-2 text-[11px] text-muted-fg">All columns are visible</div>}
          {avail.map(c => (
            <button
              key={c.key}
              onClick={() => { onAdd(c.key); setOpen(false); }}
              className="w-full text-left px-3 py-1.5 hover:bg-primary/10 transition-colors group/mi"
            >
              <span className="block text-[12px] font-medium text-foreground group-hover/mi:text-primary">{c.label}</span>
              <span className="block text-[10px] text-muted-fg leading-tight truncate">{c.description}</span>
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  );
}

// ── Grid Header (sticky vertically, frozen first cell horizontally) ──

function GridHeader({ columns, sortKey, sortDir, modes, onSort, onCycleMode, onRemove, firstColLabel, totalWidth }: {
  columns: ColumnDef[]; sortKey: string; sortDir: 'asc' | 'desc'; modes: Record<string, RenderMode>;
  onSort: (k: string) => void; onCycleMode: (k: string) => void; onRemove: (k: string) => void;
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
            <button onClick={() => onSort(col.key)} className="flex items-center gap-0.5 min-w-0" title={col.description}>
              {active && (sortDir === 'desc' ? <ArrowDown className="w-3 h-3 text-primary shrink-0" /> : <ArrowUp className="w-3 h-3 text-primary shrink-0" />)}
              <span className={`text-[10px] font-bold uppercase tracking-wider truncate transition-colors ${active ? 'text-primary' : 'text-foreground hover:text-primary'}`}>{col.shortLabel}</span>
            </button>
            <div className="absolute right-1 top-0 bottom-0 hidden group-hover/hd:flex items-center gap-px bg-surface-inset pl-2">
              <button onClick={() => onCycleMode(col.key)} className="w-4 h-4 rounded text-[8px] font-bold text-muted-fg hover:text-primary hover:bg-primary/10 transition-colors flex items-center justify-center" title="Cycle: bar / numeric / heatmap">
                {(modes[col.key] || col.defaultMode)[0].toUpperCase()}
              </button>
              <button onClick={() => onRemove(col.key)} className="w-4 h-4 rounded text-muted-fg hover:text-red-500 hover:bg-red-500/10 transition-colors flex items-center justify-center" title="Remove column">
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        );
      })}
      <div className="flex-1" />
    </div>
  );
}

// ── Grid Row (frozen first cell horizontally) ──

function GridRow({ columns, modes, firstCell, cells, onClick, totalWidth }: {
  columns: ColumnDef[]; modes: Record<string, RenderMode>;
  firstCell: ReactNode; cells: { value: number; col: ColumnDef; changed: boolean }[];
  onClick?: () => void; totalWidth: number;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className="group/row flex items-stretch h-full text-left border-b border-border-subtle hover:bg-surface-hover transition-colors"
      style={{ minWidth: totalWidth, width: '100%' }}
    >
      <div className="sticky left-0 z-10 flex items-center bg-surface group-hover/row:bg-surface-hover border-r border-border px-3 shrink-0 transition-colors shadow-[3px_0_6px_-3px_rgba(0,0,0,0.35)]" style={{ width: NAME_W }}>
        {firstCell}
      </div>
      {cells.map((c, i) => (
        <div key={columns[i].key} className="flex items-center justify-end border-r border-border-subtle/40 px-2 shrink-0" style={{ width: COL_W }}>
          <ColCell value={c.value} col={c.col} mode={modes[c.col.key] || c.col.defaultMode} changed={c.changed} />
        </div>
      ))}
      <div className="flex-1" />
    </Tag>
  );
}

// ── Generic virtualized grid (header + frozen column + sticky header) ──

function PulseGrid({
  scrollRef, virtualizer, columns, modes, firstColLabel,
  sortKey, sortDir, onSort, onCycleMode, onRemove,
  renderRow, rowKey, state, emptyTitle, emptySubtitle,
}: {
  scrollRef: React.RefObject<HTMLDivElement>;
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  columns: ColumnDef[];
  modes: Record<string, RenderMode>;
  firstColLabel: string;
  sortKey: string; sortDir: 'asc' | 'desc';
  onSort: (k: string) => void; onCycleMode: (k: string) => void; onRemove: (k: string) => void;
  renderRow: (index: number) => ReactNode;
  rowKey: (index: number) => string;
  state: 'loading' | 'empty' | 'ready';
  emptyTitle: string; emptySubtitle: string;
}) {
  const totalWidth = NAME_W + columns.length * COL_W;
  const items = virtualizer.getVirtualItems();
  return (
    <div ref={scrollRef} className="flex-1 overflow-auto pulse-scroll">
      <div style={{ minWidth: totalWidth, position: 'relative' }}>
        <GridHeader
          columns={columns} sortKey={sortKey} sortDir={sortDir} modes={modes}
          onSort={onSort} onCycleMode={onCycleMode} onRemove={onRemove}
          firstColLabel={firstColLabel} totalWidth={totalWidth}
        />
        {state === 'loading' ? (
          <div className="flex items-center justify-center py-20"><RefreshCw className="w-4 h-4 text-muted-fg animate-spin" /></div>
        ) : state === 'empty' ? (
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <div className="w-10 h-10 rounded-full bg-surface-inset flex items-center justify-center mb-3">
              <span className="w-2.5 h-2.5 rounded-full bg-muted-fg/40" />
            </div>
            <p className="text-[13px] font-medium text-foreground mb-1">{emptyTitle}</p>
            <p className="text-[11px] text-muted-fg">{emptySubtitle}</p>
          </div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative', minWidth: totalWidth }}>
            {items.map(vi => (
              <div
                key={rowKey(vi.index)}
                className="absolute left-0"
                style={{ top: 0, transform: `translateY(${vi.start}px)`, height: vi.size, minWidth: totalWidth, width: '100%' }}
              >
                {renderRow(vi.index)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const TABS: { key: PulseTab; label: string }[] = [
  { key: 'sectors', label: 'Sectors' },
  { key: 'industries', label: 'Industries' },
  { key: 'themes', label: 'Themes' },
];

// ── Main ──

export function MarketPulseContent({ onOpenTicker }: { onOpenTicker?: (sym: string) => void }) {
  const closeWindow = useCloseCurrentWindow();

  const [tab, setTab] = useState<PulseTab>('sectors');
  const [dd, setDd] = useState<{ type: string; name: string; label: string; avgChange: number } | null>(null);
  const [sectorFilter, setSF] = useState<string>();
  const [minCap, setMinCap] = useState(() => loadPrefs().minCap || 0);

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

  // ── View switching ──
  const [activeView, setActiveView] = useState<PulseViewType>(() => loadPrefs().view || 'table');
  const [viewMenuOpen, setViewMenuOpen] = useState(false);
  const viewMenuRef = useRef<HTMLDivElement>(null);

  const handleViewChange = useCallback((v: PulseViewType) => {
    setActiveView(v);
    setViewMenuOpen(false);
    setDd(null); // exit drilldown on view switch
  }, []);

  // Close view menu on outside click
  useEffect(() => {
    if (!viewMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (viewMenuRef.current && !viewMenuRef.current.contains(e.target as Node)) {
        setViewMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [viewMenuOpen]);

  const activeViewDef = VIEW_DEFINITIONS.find(v => v.key === activeView) || VIEW_DEFINITIONS[0];

  // Main view state
  const [sortKey, setSortKey] = useState('weighted_change');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [visCols, setVisCols] = useState<string[]>(() => loadPrefs().visCols || DEFAULT_COLUMNS);
  const [modes, setModes] = useState<Record<string, RenderMode>>(() => (loadPrefs().modes || {}) as Record<string, RenderMode>);

  // Drilldown state
  const [ddSortKey, setDdSortKey] = useState('change_percent');
  const [ddSortDir, setDdSortDir] = useState<'asc' | 'desc'>('desc');
  const [ddVisCols, setDdVisCols] = useState<string[]>(() => loadPrefs().ddVisCols || DEFAULT_DD_COLUMNS);
  const [ddModes, setDdModes] = useState<Record<string, RenderMode>>(() => (loadPrefs().ddModes || {}) as Record<string, RenderMode>);

  const { data, loading, error, lastUpdate, totalTickers, tickCount, refetch } = useMarketPulse({ tab, refreshInterval: 3000, sectorFilter, minMarketCap: minCap || undefined });
  const { data: ddData, loading: ddLoad, total: ddTotal, ddTickCount, fetchDrilldown, reset: resetDrilldown } = useDrilldown();

  // Drilldown polling
  const ddRef = useRef(dd); ddRef.current = dd;
  const ddIntRef = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => {
    if (ddIntRef.current) clearInterval(ddIntRef.current);
    if (dd) {
      ddIntRef.current = setInterval(() => {
        const d = ddRef.current;
        if (d) fetchDrilldown(d.type, d.name, d.avgChange, minCap || undefined);
      }, 3000);
    }
    return () => { if (ddIntRef.current) clearInterval(ddIntRef.current); };
  }, [dd, fetchDrilldown, minCap]);

  // Persist user preferences (including active view)
  useEffect(() => {
    savePrefs({ visCols, ddVisCols, modes: modes as Record<string, string>, ddModes: ddModes as Record<string, string>, minCap, view: activeView });
  }, [visCols, ddVisCols, modes, ddModes, minCap, activeView]);

  // Resolved columns
  const cols = useMemo(() => visCols.map(k => ALL_COLUMNS.find(c => c.key === k)!).filter(Boolean), [visCols]);
  const ddCols = useMemo(() => ddVisCols.map(k => DD_COLUMNS.find(c => c.key === k)!).filter(Boolean), [ddVisCols]);

  // Sorted main data
  const sorted = useMemo(() => {
    if (!data.length) return data;
    return [...data].sort((a, b) => { const va = (a as any)[sortKey] ?? 0, vb = (b as any)[sortKey] ?? 0; return sortDir === 'desc' ? vb - va : va - vb; });
  }, [data, sortKey, sortDir]);

  // Sorted drilldown data (client-side)
  const ddSorted = useMemo(() => {
    if (!ddData.length) return ddData;
    return [...ddData].sort((a, b) => {
      if (ddSortKey === 'symbol') {
        const cmp = a.symbol.localeCompare(b.symbol);
        return ddSortDir === 'asc' ? cmp : -cmp;
      }
      const va = (a as any)[ddSortKey] ?? 0, vb = (b as any)[ddSortKey] ?? 0;
      return ddSortDir === 'desc' ? vb - va : va - vb;
    });
  }, [ddData, ddSortKey, ddSortDir]);

  // Main view handlers
  const doSort = useCallback((k: string) => { setSortKey(p => { if (p === k) { setSortDir(d => d === 'desc' ? 'asc' : 'desc'); return p; } setSortDir('desc'); return k; }); }, []);
  const cycleMode = useCallback((k: string) => { setModes(p => { const c = ALL_COLUMNS.find(x => x.key === k); const cur = p[k] || c?.defaultMode || 'numeric'; const o: RenderMode[] = ['bar', 'numeric', 'heatmap']; return { ...p, [k]: o[(o.indexOf(cur) + 1) % o.length] }; }); }, []);
  const addCol = useCallback((k: string) => { setVisCols(p => [...p, k]); }, []);
  const rmCol = useCallback((k: string) => { setVisCols(p => p.filter(x => x !== k)); }, []);

  // Drilldown handlers
  const doDdSort = useCallback((k: string) => { setDdSortKey(p => { if (p === k) { setDdSortDir(d => d === 'desc' ? 'asc' : 'desc'); return p; } setDdSortDir('desc'); return k; }); }, []);
  const ddCycleMode = useCallback((k: string) => { setDdModes(p => { const c = DD_COLUMNS.find(x => x.key === k); const cur = p[k] || c?.defaultMode || 'numeric'; const o: RenderMode[] = ['bar', 'numeric', 'heatmap']; return { ...p, [k]: o[(o.indexOf(cur) + 1) % o.length] }; }); }, []);
  const ddAddCol = useCallback((k: string) => { setDdVisCols(p => [...p, k]); }, []);
  const ddRmCol = useCallback((k: string) => { setDdVisCols(p => p.filter(x => x !== k)); }, []);

  const doSelect = useCallback((e: PerformanceEntry) => {
    const gt = tab === 'themes' ? 'theme' : tab === 'industries' ? 'industry' : 'sector';
    const avgChg = e.weighted_change || e.avg_change || 0;
    setDd({ type: gt, name: e.name, label: tab === 'themes' ? fmtTheme(e.name) : e.name, avgChange: avgChg });
    resetDrilldown();
    fetchDrilldown(gt, e.name, avgChg, minCap || undefined);
  }, [tab, fetchDrilldown, resetDrilldown, minCap]);

  const doBack = useCallback(() => { setDd(null); setDdSortKey('change_percent'); setDdSortDir('desc'); }, []);
  const doTab = useCallback((t: PulseTab) => { setTab(t); setDd(null); setSF(undefined); }, []);

  const ts = lastUpdate ? new Date(lastUpdate * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';

  // Virtualizers — the sticky opaque header overlaps the top band, so no scrollMargin is needed
  const pRef = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: sorted.length, getScrollElement: () => pRef.current, estimateSize: () => ROW_H, overscan: 12 });
  const ddPRef = useRef<HTMLDivElement>(null);
  const ddVirt = useVirtualizer({ count: ddSorted.length, getScrollElement: () => ddPRef.current, estimateSize: () => ROW_H, overscan: 14 });

  const avgChgLabel = dd ? `avg ${dd.avgChange >= 0 ? '+' : ''}${dd.avgChange.toFixed(2)}%` : '';
  const showColumnMenu = !tickerCtx && !error && ((activeView === 'table' && !dd) || !!dd);

  // First-cell renderers (frozen column content)
  const renderGroupFirst = useCallback((entry: PerformanceEntry, isTheme: boolean): ReactNode => {
    const name = isTheme ? fmtTheme(entry.name) : entry.name;
    return (
      <div className="flex items-center gap-1.5 w-full min-w-0">
        <span className="text-[11px] font-semibold text-foreground truncate">{name}</span>
        {entry._rankShift !== undefined && entry._rankShift !== 0 && (
          <span className={`text-[8px] font-mono font-bold shrink-0 ${entry._rankShift > 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
            {entry._rankShift > 0 ? `\u25B2${entry._rankShift}` : `\u25BC${Math.abs(entry._rankShift)}`}
          </span>
        )}
        {entry._divergence && (
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" title="Breadth divergence" />
        )}
        <span className="ml-auto text-[9px] text-muted-fg font-mono tabular-nums shrink-0">{entry.count}</span>
        <ChevronRight className="w-3.5 h-3.5 text-muted-fg/40 group-hover/row:text-muted-fg transition-colors shrink-0" />
      </div>
    );
  }, []);

  const renderDdFirst = useCallback((t: DrilldownTicker): ReactNode => (
    <button
      onClick={() => onOpenTicker?.(t.symbol)}
      onMouseDown={e => e.stopPropagation()}
      className="flex items-center gap-1 w-full min-w-0 text-left"
      title={`Open ${t.symbol}`}
    >
      <span className="text-[11px] font-bold text-primary truncate">{t.symbol}</span>
      <ExternalLink className="w-2.5 h-2.5 text-muted-fg/50 group-hover/row:text-primary transition-colors shrink-0" />
    </button>
  ), [onOpenTicker]);

  return (
    <div className="flex flex-col h-full bg-surface rounded-lg overflow-hidden">
      {/* Header / toolbar */}
      <div className="table-drag-handle flex items-center justify-between px-3 py-1.5 border-b border-border bg-surface-hover shrink-0 cursor-move select-none">
        <div className="flex items-center gap-2 min-w-0">
          <GripHorizontal className="w-4 h-4 text-muted-fg shrink-0" />
          {tickerCtx ? (
            <>
              <button onClick={handleSearchClear} onMouseDown={e => e.stopPropagation()} className="flex items-center gap-1 text-[12px] text-foreground/80 hover:text-foreground font-medium">
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <span className="text-[13px] font-black text-primary ml-1">{tickerCtx.symbol}</span>
              <span className="text-[10px] text-muted-fg font-medium truncate">{tickerCtx.sector} · {tickerCtx.industry}</span>
            </>
          ) : dd ? (
            <>
              <button onClick={doBack} onMouseDown={e => e.stopPropagation()} className="flex items-center gap-1 text-[12px] text-foreground/80 hover:text-foreground font-medium">
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <span className="text-[13px] font-semibold text-foreground ml-1 truncate">{dd.label}</span>
              <span className="text-[10px] text-muted-fg font-medium shrink-0">{ddTotal}</span>
              <span className={`text-[10px] font-mono font-semibold ml-1 shrink-0 ${dd.avgChange >= 0 ? 'text-primary' : 'text-pink-600'}`}>{avgChgLabel}</span>
            </>
          ) : (
            <>
              <span className="text-[11px] font-semibold text-foreground">Market Pulse</span>
              {/* View switcher dropdown */}
              <div ref={viewMenuRef} className="relative" onMouseDown={e => e.stopPropagation()}>
                <button
                  onClick={() => setViewMenuOpen(v => !v)}
                  className={`flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-medium rounded transition-colors ${viewMenuOpen
                      ? 'bg-primary/10 text-primary border border-primary'
                      : 'bg-surface-inset text-muted-fg border border-transparent hover:border-border hover:text-foreground'
                    }`}
                >
                  {activeViewDef.shortLabel}
                  <ChevronDown className="w-2.5 h-2.5" />
                </button>
                {viewMenuOpen && (
                  <div className="absolute top-full left-0 mt-1 w-36 bg-surface border border-border rounded-lg shadow-lg z-50 py-0.5">
                    {VIEW_DEFINITIONS.map(v => (
                      <button
                        key={v.key}
                        onClick={() => handleViewChange(v.key)}
                        className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors ${activeView === v.key
                            ? 'text-primary bg-primary/10 font-semibold'
                            : 'text-foreground hover:bg-surface-hover font-medium'
                          }`}
                      >
                        {v.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-2.5 shrink-0" onMouseDown={e => e.stopPropagation()}>
          {/* Search */}
          {!tickerCtx && (
            searchOpen ? (
              <form onSubmit={handleSearch} className="flex items-center gap-1">
                <div className="relative">
                  <input
                    ref={searchInputRef}
                    value={searchInput}
                    onChange={e => setSearchInput(e.target.value.toUpperCase())}
                    placeholder="Ticker..."
                    className="w-[80px] h-[22px] text-[11px] font-mono font-semibold pl-1.5 pr-5 rounded border border-border focus:border-primary focus:ring-1 focus:ring-primary/20 outline-none bg-surface text-foreground placeholder:text-muted-fg/50"
                    maxLength={10}
                  />
                  {searchLoading && <RefreshCw className="absolute right-1 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-fg animate-spin" />}
                </div>
                <button type="button" onClick={handleSearchClear} className="p-0.5 hover:bg-surface-hover rounded">
                  <X className="w-3 h-3 text-muted-fg" />
                </button>
              </form>
            ) : (
              <button onClick={() => setSearchOpen(true)} className="p-0.5 hover:bg-primary/10 rounded transition-colors group" title="Search ticker">
                <Search className="w-3.5 h-3.5 text-muted-fg group-hover:text-primary" />
              </button>
            )
          )}
          {searchError === 'not_found' && !tickerCtx && (
            <span className="text-[9px] text-amber-600 font-medium">Not found</span>
          )}
          {!dd && !tickerCtx && (
            <div className="flex bg-surface-inset rounded p-px gap-px">
              {[{ l: 'All', v: 0 }, { l: '>300M', v: 3e8 }, { l: '>2B', v: 2e9 }, { l: '>10B', v: 1e10 }].map(p => (
                <button key={p.v} onClick={() => setMinCap(p.v)}
                  className={`px-1.5 py-0.5 text-[9px] font-medium rounded transition-colors ${minCap === p.v ? 'bg-surface text-foreground shadow-sm' : 'text-muted-fg hover:text-foreground/80'
                    }`}>{p.l}</button>
              ))}
            </div>
          )}
          {showColumnMenu && (
            dd
              ? <ColumnMenu visible={ddVisCols} allCols={DD_COLUMNS} onAdd={ddAddCol} />
              : <ColumnMenu visible={visCols} allCols={ALL_COLUMNS} onAdd={addCol} />
          )}
          {!dd && !tickerCtx && totalTickers > 0 && <span className="text-[10px] text-muted-fg font-medium tabular-nums">{totalTickers.toLocaleString()}</span>}
          <LiveDot tick={dd ? ddTickCount : tickCount} />
          <span className="text-[10px] text-muted-fg font-mono tabular-nums">{ts}</span>
          <button className="p-0.5 hover:bg-primary/10 rounded transition-colors group" title="Pop out"><ExternalLink className="w-3.5 h-3.5 text-muted-fg group-hover:text-primary" /></button>
          <button onClick={closeWindow} className="p-0.5 hover:bg-red-500/15 rounded transition-colors" title="Close"><X className="w-3.5 h-3.5 text-muted-fg hover:text-red-600" /></button>
        </div>
      </div>

      {/* Tabs (main view only — visible for all view types) */}
      {!dd && !tickerCtx && (
        <div className="flex shrink-0 border-b border-border">
          {TABS.map(t => (
            <button key={t.key} onClick={() => doTab(t.key)} className={`flex-1 py-1.5 text-[10px] font-bold tracking-widest uppercase transition-colors ${tab === t.key ? 'text-primary border-b-2 border-primary' : 'text-muted-fg hover:text-foreground'
              }`}>{t.label}</button>
          ))}
        </div>
      )}

      {/* ── Ticker Context View (search result) ── */}
      {tickerCtx && (
        <TickerContextView data={tickerCtx} onOpenTicker={onOpenTicker} />
      )}

      {error && !tickerCtx && (
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 text-center">
          <div className="w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center mb-3">
            <RefreshCw className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-[13px] font-medium text-foreground mb-1">Market data unavailable</p>
          <p className="text-[11px] text-muted-fg mb-4">{error}</p>
          <button onClick={refetch} className="px-3 py-1.5 text-[11px] font-medium text-primary hover:text-primary bg-primary/10 hover:bg-primary/20 rounded-md transition-colors">
            Retry
          </button>
        </div>
      )}

      {/* ── TABLE VIEW ── */}
      {!error && !dd && !tickerCtx && activeView === 'table' && (
        <PulseGrid
          scrollRef={pRef}
          virtualizer={virt}
          columns={cols}
          modes={modes}
          firstColLabel={tab === 'themes' ? 'Theme' : tab === 'industries' ? 'Industry' : 'Sector'}
          sortKey={sortKey} sortDir={sortDir}
          onSort={doSort} onCycleMode={cycleMode} onRemove={rmCol}
          rowKey={(i) => sorted[i].name}
          renderRow={(i) => (
            <GridRow
              columns={cols} modes={modes} totalWidth={NAME_W + cols.length * COL_W}
              firstCell={renderGroupFirst(sorted[i], tab === 'themes')}
              cells={cols.map(col => ({ value: (sorted[i] as any)[col.key], col, changed: sorted[i]._changedKeys?.has(col.key) || false }))}
              onClick={() => doSelect(sorted[i])}
            />
          )}
          state={loading && !sorted.length ? 'loading' : !sorted.length ? 'empty' : 'ready'}
          emptyTitle="Market closed"
          emptySubtitle="Data will refresh when the market opens"
        />
      )}

      {/* ── CHART VIEWS (only when no drilldown, no error, data loaded) ── */}
      {!error && !dd && !tickerCtx && activeView !== 'table' && (
        loading && !data.length ? (
          <div className="flex-1 flex items-center justify-center"><RefreshCw className="w-4 h-4 text-muted-fg animate-spin" /></div>
        ) : !data.length ? (
          <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 text-center">
            <p className="text-[13px] font-medium text-foreground mb-1">Market closed</p>
            <p className="text-[11px] text-muted-fg">Data will refresh when the market opens</p>
          </div>
        ) : (
          <>
            {activeView === 'overview' && (
              <OverviewView data={data} activeTab={tab} onSelect={doSelect} />
            )}
            {activeView === 'treemap' && (
              <TreemapView data={data} activeTab={tab} onSelect={doSelect} />
            )}
            {activeView === 'bubble' && (
              <BubbleScatterView data={data} activeTab={tab} onSelect={doSelect} />
            )}
            {activeView === 'rotation' && (
              <RotationBarsView data={data} activeTab={tab} onSelect={doSelect} />
            )}
            {activeView === 'breadth' && (
              <BreadthMonitorView data={data} activeTab={tab} onSelect={doSelect} />
            )}
            {activeView === 'rrg' && (
              <RRGView data={data} activeTab={tab} onSelect={doSelect} />
            )}
          </>
        )
      )}

      {/* Drilldown list */}
      {!error && !tickerCtx && dd && (
        <PulseGrid
          scrollRef={ddPRef}
          virtualizer={ddVirt}
          columns={ddCols}
          modes={ddModes}
          firstColLabel="Symbol"
          sortKey={ddSortKey} sortDir={ddSortDir}
          onSort={doDdSort} onCycleMode={ddCycleMode} onRemove={ddRmCol}
          rowKey={(i) => ddSorted[i].symbol}
          renderRow={(i) => (
            <GridRow
              columns={ddCols} modes={ddModes} totalWidth={NAME_W + ddCols.length * COL_W}
              firstCell={renderDdFirst(ddSorted[i])}
              cells={ddCols.map(col => ({ value: (ddSorted[i] as any)[col.key], col, changed: ddSorted[i]._changedKeys?.has(col.key) || false }))}
            />
          )}
          state={ddLoad && !ddSorted.length ? 'loading' : !ddSorted.length ? 'empty' : 'ready'}
          emptyTitle="No tickers"
          emptySubtitle="No matching tickers in this group"
        />
      )}
    </div>
  );
}
