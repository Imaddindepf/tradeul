'use client';

import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useMarketPulse, useDrilldown, type PulseTab, type PerformanceEntry, type DrilldownTicker } from '@/hooks/useMarketPulse';
import { useCloseCurrentWindow } from '@/contexts/FloatingWindowContext';
import { ArrowLeft, RefreshCw, ChevronRight, ArrowDown, ArrowUp, Plus, X, GripHorizontal, ExternalLink } from 'lucide-react';
import { ALL_COLUMNS, DEFAULT_COLUMNS, DD_COLUMNS, DEFAULT_DD_COLUMNS, type ColumnDef, type RenderMode } from './columns';

function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)); }
function fmtTheme(n: string) { return n.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '); }

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
      <div className="relative flex-1 h-[14px] rounded-[3px] overflow-hidden bg-slate-100">
        <div className="absolute top-0 left-1/2 h-full w-px bg-slate-200" />
        <div className={`absolute top-0 bottom-0 rounded-[3px] transition-all duration-500 ease-out ${pos ? 'left-1/2' : 'right-1/2'}`}
          style={{ width: `${pct}%`, backgroundColor: pos ? BAR_BLUE : BAR_PINK }} />
      </div>
      <span className={`text-[11px] font-semibold font-mono tabular-nums w-[50px] text-right shrink-0 transition-colors duration-400 ${
        flash ? (pos ? 'text-blue-800' : 'text-pink-800') : (pos ? 'text-blue-600' : 'text-pink-600')
      }`}>{label}</span>
    </div>
  );
}

function PosBar({ value, domain, label }: { value: number; domain: [number, number]; label: string }) {
  const norm = clamp((value - domain[0]) / ((domain[1] - domain[0]) || 1), 0, 1);
  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0 h-full">
      <div className="relative flex-1 h-[14px] rounded-[3px] overflow-hidden bg-slate-100">
        <div className="absolute top-0 bottom-0 left-0 rounded-[3px] transition-all duration-500 ease-out" style={{ width: `${norm * 100}%`, backgroundColor: BAR_BLUE }} />
      </div>
      <span className="text-[12px] font-semibold font-mono tabular-nums w-[56px] text-right shrink-0 text-slate-700">{label}</span>
    </div>
  );
}

function NumCell({ value, col, changed }: { value: number; col: ColumnDef; changed: boolean }) {
  const [flash, setFlash] = useState(false);
  useEffect(() => { if (changed) { setFlash(true); const t = setTimeout(() => setFlash(false), 600); return () => clearTimeout(t); } }, [changed, value]);
  const pos = value >= 0;
  const div = col.colorScale === 'diverging';
  return (
    <span className={`text-[12px] font-semibold font-mono tabular-nums text-right block px-1 transition-colors duration-400 ${
      flash ? (pos ? 'text-blue-800' : 'text-pink-800') : (div ? (pos ? 'text-blue-600' : 'text-red-500') : 'text-slate-700')
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
  return <span className="text-[12px] font-semibold font-mono tabular-nums text-right block rounded px-1.5 py-px text-slate-800" style={{ backgroundColor: bg }}>{col.format(value)}</span>;
}

function ColCell({ value, col, mode, changed }: { value: number; col: ColumnDef; mode: RenderMode; changed: boolean }) {
  if (value == null || isNaN(value)) return <span className="text-[11px] text-slate-400 text-right block">-</span>;
  if (mode === 'bar') return col.colorScale === 'diverging'
    ? <DivBar value={value} domain={col.domain || [-1, 1]} label={col.format(value)} changed={changed} />
    : <PosBar value={value} domain={col.domain || [0, 1]} label={col.format(value)} />;
  if (mode === 'heatmap') return <HeatCell value={value} col={col} />;
  return <NumCell value={value} col={col} changed={changed} />;
}

// ── Column Picker (shared between main & drilldown) ──

function ColPicker({ visible, allCols, onAdd, onClose }: { visible: string[]; allCols: ColumnDef[]; onAdd: (k: string) => void; onClose: () => void }) {
  const avail = allCols.filter(c => !visible.includes(c.key));
  return (
    <div className="absolute right-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-lg shadow-xl py-1 w-[190px] max-h-[280px] overflow-auto">
      {avail.map(c => (
        <button key={c.key} onClick={() => onAdd(c.key)} className="w-full text-left px-3 py-1.5 text-[12px] text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-colors font-medium">{c.label}</button>
      ))}
      <div className="border-t border-slate-200 mt-0.5 pt-0.5">
        <button onClick={onClose} className="w-full py-1 text-[11px] text-slate-500 hover:text-slate-700 text-center font-medium">Close</button>
      </div>
    </div>
  );
}

// ── Column Header Row (shared) ──

function ColumnHeaders({ columns, sortKey, sortDir, modes, onSort, onCycleMode, onRemove, onPickerToggle, pickerOpen, pickerRef, visibleKeys, allCols, onAdd, onPickerClose, firstColLabel }: {
  columns: ColumnDef[]; sortKey: string; sortDir: 'asc' | 'desc'; modes: Record<string, RenderMode>;
  onSort: (k: string) => void; onCycleMode: (k: string) => void; onRemove: (k: string) => void;
  onPickerToggle: () => void; pickerOpen: boolean; pickerRef: React.RefObject<HTMLDivElement>;
  visibleKeys: string[]; allCols: ColumnDef[]; onAdd: (k: string) => void; onPickerClose: () => void;
  firstColLabel: string;
}) {
  return (
    <div className="flex items-center gap-2.5 pl-4 pr-2 py-1 border-b border-slate-200 bg-slate-50 shrink-0">
      <div className="w-[150px] min-w-[150px] shrink-0">
        <span className="text-[10px] font-bold text-slate-700 uppercase tracking-wider">{firstColLabel}</span>
      </div>
      {columns.map(col => (
        <div key={col.key} className="group/hd flex-1 min-w-[70px] flex items-center gap-0.5">
          <button onClick={() => onSort(col.key)} className="flex items-center gap-0.5" title={col.description}>
            <span className="text-[10px] font-bold text-slate-700 uppercase tracking-wider hover:text-blue-600 transition-colors">{col.shortLabel}</span>
            {sortKey === col.key && (sortDir === 'desc' ? <ArrowDown className="w-3 h-3 text-blue-600" /> : <ArrowUp className="w-3 h-3 text-blue-600" />)}
          </button>
          <button onClick={() => onCycleMode(col.key)} className="ml-0.5 w-4 h-4 rounded text-[8px] font-bold text-slate-500 hover:text-blue-600 hover:bg-blue-50 transition-colors flex items-center justify-center" title="bar / numeric / heatmap">
            {(modes[col.key] || col.defaultMode)[0].toUpperCase()}
          </button>
          <button onClick={() => onRemove(col.key)} className="w-4 h-4 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition-all flex items-center justify-center opacity-0 group-hover/hd:opacity-100">
            <X className="w-3 h-3" />
          </button>
        </div>
      ))}
      <div ref={pickerRef} className="relative shrink-0" onMouseDown={e => e.stopPropagation()}>
        <button onClick={onPickerToggle} className="w-5 h-5 rounded border border-dashed border-slate-300 hover:border-blue-500 hover:bg-blue-50 transition-colors flex items-center justify-center" title="Add column">
          <Plus className="w-3 h-3 text-slate-500" />
        </button>
        {pickerOpen && <ColPicker visible={visibleKeys} allCols={allCols} onAdd={onAdd} onClose={onPickerClose} />}
      </div>
      <div className="w-3.5 shrink-0" />
    </div>
  );
}

const TABS: { key: PulseTab; label: string }[] = [
  { key: 'sectors', label: 'Sectors' },
  { key: 'industries', label: 'Industries' },
  { key: 'themes', label: 'Themes' },
];

// ── Group Row ──

function GroupRow({ entry, columns, modes, onClick, isTheme }: {
  entry: PerformanceEntry; columns: ColumnDef[]; modes: Record<string, RenderMode>; onClick: () => void; isTheme?: boolean;
}) {
  const name = isTheme ? fmtTheme(entry.name) : entry.name;
  return (
    <button onClick={onClick} className="w-full flex items-center gap-2.5 pl-4 pr-2 h-full hover:bg-blue-50/40 transition-colors text-left group/row border-b border-slate-100">
      <div className="w-[150px] min-w-[150px] shrink-0 flex items-center gap-1.5">
        <span className="text-[11px] font-semibold text-slate-900 whitespace-nowrap">{name}</span>
        <span className="text-[9px] text-slate-400 font-mono tabular-nums shrink-0">{entry.count}</span>
      </div>
      {columns.map(col => (
        <div key={col.key} className="flex-1 min-w-[70px] flex items-center">
          <ColCell value={(entry as any)[col.key]} col={col} mode={modes[col.key] || col.defaultMode} changed={entry._changedKeys?.has(col.key) || false} />
        </div>
      ))}
      <ChevronRight className="w-3.5 h-3.5 text-slate-300 group-hover/row:text-slate-500 transition-colors shrink-0" />
    </button>
  );
}

// ── Drilldown Row ──

function DDRow({ t, columns, modes, onOpenTicker }: {
  t: DrilldownTicker; columns: ColumnDef[]; modes: Record<string, RenderMode>; onOpenTicker?: (sym: string) => void;
}) {
  return (
    <div className="flex items-center gap-2.5 pl-4 pr-2 h-full hover:bg-blue-50/40 transition-colors border-b border-slate-100 group/row">
      <button onClick={() => onOpenTicker?.(t.symbol)} className="w-[150px] min-w-[150px] shrink-0 text-left flex items-center gap-1" title={`Open ${t.symbol}`}>
        <span className="text-[11px] font-bold text-blue-600 hover:text-blue-800 transition-colors">{t.symbol}</span>
        <ExternalLink className="w-2.5 h-2.5 text-slate-300 group-hover/row:text-blue-400 transition-colors shrink-0" />
      </button>
      {columns.map(col => (
        <div key={col.key} className="flex-1 min-w-[70px] flex items-center">
          <ColCell value={(t as any)[col.key]} col={col} mode={modes[col.key] || col.defaultMode} changed={t._changedKeys?.has(col.key) || false} />
        </div>
      ))}
    </div>
  );
}

// ── Main ──

export function MarketPulseContent({ onOpenTicker }: { onOpenTicker?: (sym: string) => void }) {
  const closeWindow = useCloseCurrentWindow();

  const [tab, setTab] = useState<PulseTab>('sectors');
  const [dd, setDd] = useState<{ type: string; name: string; label: string; avgChange: number } | null>(null);
  const [sectorFilter, setSF] = useState<string>();

  // Main view state
  const [sortKey, setSortKey] = useState('weighted_change');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [visCols, setVisCols] = useState<string[]>(DEFAULT_COLUMNS);
  const [modes, setModes] = useState<Record<string, RenderMode>>({});
  const [picker, setPicker] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  // Drilldown state
  const [ddSortKey, setDdSortKey] = useState('change_percent');
  const [ddSortDir, setDdSortDir] = useState<'asc' | 'desc'>('desc');
  const [ddVisCols, setDdVisCols] = useState<string[]>(DEFAULT_DD_COLUMNS);
  const [ddModes, setDdModes] = useState<Record<string, RenderMode>>({});
  const [ddPicker, setDdPicker] = useState(false);
  const ddPickerRef = useRef<HTMLDivElement>(null);

  const { data, loading, error, lastUpdate, totalTickers, tickCount, refetch } = useMarketPulse({ tab, refreshInterval: 3000, sectorFilter });
  const { data: ddData, loading: ddLoad, total: ddTotal, ddTickCount, fetchDrilldown, resetPrevMap } = useDrilldown();

  // Drilldown polling
  const ddRef = useRef(dd); ddRef.current = dd;
  const ddIntRef = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => {
    if (ddIntRef.current) clearInterval(ddIntRef.current);
    if (dd) {
      ddIntRef.current = setInterval(() => {
        const d = ddRef.current;
        if (d) fetchDrilldown(d.type, d.name, d.avgChange);
      }, 3000);
    }
    return () => { if (ddIntRef.current) clearInterval(ddIntRef.current); };
  }, [dd, fetchDrilldown]);

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
  const cycleMode = useCallback((k: string) => { setModes(p => { const c = ALL_COLUMNS.find(x => x.key === k); const cur = p[k] || c?.defaultMode || 'numeric'; const o: RenderMode[] = ['bar','numeric','heatmap']; return { ...p, [k]: o[(o.indexOf(cur)+1)%o.length] }; }); }, []);
  const addCol = useCallback((k: string) => { setVisCols(p => [...p, k]); setPicker(false); }, []);
  const rmCol = useCallback((k: string) => { setVisCols(p => p.filter(x => x !== k)); }, []);

  // Drilldown handlers
  const doDdSort = useCallback((k: string) => { setDdSortKey(p => { if (p === k) { setDdSortDir(d => d === 'desc' ? 'asc' : 'desc'); return p; } setDdSortDir('desc'); return k; }); }, []);
  const ddCycleMode = useCallback((k: string) => { setDdModes(p => { const c = DD_COLUMNS.find(x => x.key === k); const cur = p[k] || c?.defaultMode || 'numeric'; const o: RenderMode[] = ['bar','numeric','heatmap']; return { ...p, [k]: o[(o.indexOf(cur)+1)%o.length] }; }); }, []);
  const ddAddCol = useCallback((k: string) => { setDdVisCols(p => [...p, k]); setDdPicker(false); }, []);
  const ddRmCol = useCallback((k: string) => { setDdVisCols(p => p.filter(x => x !== k)); }, []);

  const doSelect = useCallback((e: PerformanceEntry) => {
    const gt = tab === 'themes' ? 'theme' : tab === 'industries' ? 'industry' : 'sector';
    const avgChg = e.weighted_change || e.avg_change || 0;
    setDd({ type: gt, name: e.name, label: tab === 'themes' ? fmtTheme(e.name) : e.name, avgChange: avgChg });
    resetPrevMap();
    fetchDrilldown(gt, e.name, avgChg);
  }, [tab, fetchDrilldown, resetPrevMap]);

  const doBack = useCallback(() => { setDd(null); setDdSortKey('change_percent'); setDdSortDir('desc'); }, []);
  const doTab = useCallback((t: PulseTab) => { setTab(t); setDd(null); setSF(undefined); }, []);

  // Close pickers on outside click
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPicker(false);
      if (ddPickerRef.current && !ddPickerRef.current.contains(e.target as Node)) setDdPicker(false);
    };
    if (picker || ddPicker) document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [picker, ddPicker]);

  const ts = lastUpdate ? new Date(lastUpdate * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';

  // Virtualizers
  const pRef = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: sorted.length, getScrollElement: () => pRef.current, estimateSize: () => 26, overscan: 8 });
  const ddPRef = useRef<HTMLDivElement>(null);
  const ddVirt = useVirtualizer({ count: ddSorted.length, getScrollElement: () => ddPRef.current, estimateSize: () => 26, overscan: 12 });

  const avgChgLabel = dd ? `avg ${dd.avgChange >= 0 ? '+' : ''}${dd.avgChange.toFixed(2)}%` : '';

  return (
    <div className="flex flex-col h-full bg-white rounded-lg overflow-hidden">
      {/* Header */}
      <div className="table-drag-handle flex items-center justify-between px-4 py-1.5 border-b border-slate-200 bg-slate-50 shrink-0 cursor-move select-none">
        <div className="flex items-center gap-2">
          <GripHorizontal className="w-4 h-4 text-slate-500" />
          {dd ? (
            <>
              <button onClick={doBack} onMouseDown={e => e.stopPropagation()} className="flex items-center gap-1 text-[12px] text-slate-600 hover:text-slate-900 font-medium">
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
              <span className="text-[13px] font-semibold text-slate-900 ml-1">{dd.label}</span>
              <span className="text-[10px] text-slate-500 font-medium">{ddTotal}</span>
              <span className={`text-[10px] font-mono font-semibold ml-1 ${dd.avgChange >= 0 ? 'text-blue-600' : 'text-pink-600'}`}>{avgChgLabel}</span>
            </>
          ) : (
            <span className="text-[11px] font-bold text-slate-900 tracking-widest">MARKET PULSE</span>
          )}
        </div>
        <div className="flex items-center gap-2.5" onMouseDown={e => e.stopPropagation()}>
          {!dd && totalTickers > 0 && <span className="text-[10px] text-slate-500 font-medium tabular-nums">{totalTickers.toLocaleString()}</span>}
          <LiveDot tick={dd ? ddTickCount : tickCount} />
          <span className="text-[10px] text-slate-500 font-mono tabular-nums">{ts}</span>
          <button onClick={refetch} className="p-0.5 hover:bg-slate-200 rounded transition-colors"><RefreshCw className={`w-3.5 h-3.5 text-slate-500 ${loading ? 'animate-spin' : ''}`} /></button>
          <button onClick={closeWindow} className="p-0.5 hover:bg-red-100 rounded transition-colors" title="Close"><X className="w-3.5 h-3.5 text-slate-500 hover:text-red-600" /></button>
        </div>
      </div>

      {/* Tabs (main view only) */}
      {!dd && (
        <div className="flex shrink-0 border-b border-slate-200">
          {TABS.map(t => (
            <button key={t.key} onClick={() => doTab(t.key)} className={`flex-1 py-1.5 text-[10px] font-bold tracking-widest uppercase transition-colors ${
              tab === t.key ? 'text-blue-600 border-b-2 border-blue-600' : 'text-slate-500 hover:text-slate-700'
            }`}>{t.label}</button>
          ))}
        </div>
      )}

      {/* Column headers — MAIN */}
      {!dd && !error && (
        <ColumnHeaders
          columns={cols} sortKey={sortKey} sortDir={sortDir} modes={modes}
          onSort={doSort} onCycleMode={cycleMode} onRemove={rmCol}
          onPickerToggle={() => setPicker(v => !v)} pickerOpen={picker} pickerRef={pickerRef}
          visibleKeys={visCols} allCols={ALL_COLUMNS} onAdd={addCol} onPickerClose={() => setPicker(false)}
          firstColLabel={tab === 'themes' ? 'Theme' : tab === 'industries' ? 'Industry' : 'Sector'}
        />
      )}

      {/* Column headers — DRILLDOWN */}
      {dd && !error && (
        <ColumnHeaders
          columns={ddCols} sortKey={ddSortKey} sortDir={ddSortDir} modes={ddModes}
          onSort={doDdSort} onCycleMode={ddCycleMode} onRemove={ddRmCol}
          onPickerToggle={() => setDdPicker(v => !v)} pickerOpen={ddPicker} pickerRef={ddPickerRef}
          visibleKeys={ddVisCols} allCols={DD_COLUMNS} onAdd={ddAddCol} onPickerClose={() => setDdPicker(false)}
          firstColLabel="Symbol"
        />
      )}

      {error && <div className="px-4 py-8 text-center text-[13px] text-slate-500">{error}</div>}

      {/* Main list */}
      {!error && !dd && (
        loading && !sorted.length ? (
          <div className="flex-1 flex items-center justify-center"><RefreshCw className="w-4 h-4 text-slate-400 animate-spin" /></div>
        ) : (
          <div ref={pRef} className="flex-1 overflow-auto">
            <div style={{ height: virt.getTotalSize(), position: 'relative' }}>
              {virt.getVirtualItems().map(vi => (
                <div key={sorted[vi.index].name} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: vi.size, transform: `translateY(${vi.start}px)` }}>
                  <GroupRow entry={sorted[vi.index]} columns={cols} modes={modes} onClick={() => doSelect(sorted[vi.index])} isTheme={tab === 'themes'} />
                </div>
              ))}
            </div>
          </div>
        )
      )}

      {/* Drilldown list */}
      {!error && dd && (
        ddLoad && !ddSorted.length ? (
          <div className="flex-1 flex items-center justify-center"><RefreshCw className="w-4 h-4 text-slate-400 animate-spin" /></div>
        ) : (
          <div ref={ddPRef} className="flex-1 overflow-auto">
            <div style={{ height: ddVirt.getTotalSize(), position: 'relative' }}>
              {ddVirt.getVirtualItems().map(vi => (
                <div key={ddSorted[vi.index].symbol} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: vi.size, transform: `translateY(${vi.start}px)` }}>
                  <DDRow t={ddSorted[vi.index]} columns={ddCols} modes={ddModes} onOpenTicker={onOpenTicker} />
                </div>
              ))}
            </div>
          </div>
        )
      )}
    </div>
  );
}
