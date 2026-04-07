'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  X, Search, ChevronDown, ChevronRight, Check, RotateCcw,
  Trash2,
  TrendingUp, TrendingDown, Minus,
} from 'lucide-react';
import {
  ALERT_CATEGORIES, ALERT_CATALOG, getAlertsByCategory,
  searchAlerts, BUILT_IN_PRESETS, type AlertDefinition,
} from '@/lib/alert-catalog';
import { useAlertStrategies, type AlertStrategy } from '@/hooks/useAlertStrategies';
import { useAlertPresetsStore, type AlertPresetFilters } from '@/stores/useAlertPresetsStore';
import type { ActiveEventFilters } from '@/stores/useEventFiltersStore';

interface AlertConfigPanelProps {
  selectedEventTypes: string[];
  currentFilters: ActiveEventFilters;
  onEventTypesChange: (types: string[]) => void;
  onFiltersChange: (filters: ActiveEventFilters) => void;
  onClose: () => void;
  locale?: 'en' | 'es';
}

type TabId = 'alerts' | 'filters' | 'strategies';

function DirectionIcon({ direction }: { direction: string }) {
  if (direction === 'bullish') return <TrendingUp className="w-3 h-3 text-emerald-500" />;
  if (direction === 'bearish') return <TrendingDown className="w-3 h-3 text-rose-500" />;
  return <Minus className="w-3 h-3 text-muted-fg" />;
}

const UNIT_MUL: Record<string, number> = { '': 1, K: 1e3, M: 1e6, B: 1e9 };
const fmtLocale = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 6 });

/** Numeric input with thousand-separator formatting on blur */
function FmtNum({ value, onChange, placeholder, className }: {
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  placeholder?: string;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [editStr, setEditStr] = useState('');
  const display = value !== undefined ? fmtLocale(value) : '';
  return (
    <input type="text" inputMode="decimal"
      value={editing ? editStr : display}
      onFocus={() => { setEditing(true); setEditStr(value !== undefined ? String(value) : ''); }}
      onBlur={() => {
        setEditing(false);
        const s = editStr.replace(/,/g, '').trim();
        onChange(s && !isNaN(Number(s)) ? Number(s) : undefined);
      }}
      onChange={e => setEditStr(e.target.value)}
      placeholder={placeholder} className={className} />
  );
}

function FilterInput({ label, minValue, maxValue, onMinChange, onMaxChange, suffix, unitOpts, defaultUnit, phMin, phMax }: {
  label: string; minValue?: number; maxValue?: number;
  onMinChange: (v?: number) => void; onMaxChange: (v?: number) => void;
  suffix?: string; unitOpts?: string[]; defaultUnit?: string;
  phMin?: string; phMax?: string;
}) {
  const [unit, setUnit] = useState(defaultUnit || '');
  const mul = UNIT_MUL[unit] || 1;
  const toDisp = (raw?: number) => raw !== undefined ? raw / mul : undefined;
  const toRaw = (v?: number) => v !== undefined ? v * mul : undefined;
  const inputCls = "flex-1 min-w-0 px-1.5 py-[3px] text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface font-mono text-right tabular-nums";
  return (
    <div className="flex items-center gap-1.5 px-3 py-[3px]">
      <span className="text-[11px] text-foreground/70 w-24 flex-shrink-0 font-medium">{label}</span>
      <FmtNum value={toDisp(minValue)} onChange={v => onMinChange(toRaw(v))} placeholder={phMin || 'min'} className={inputCls} />
      <span className="text-muted-fg/50 text-[9px]">-</span>
      <FmtNum value={toDisp(maxValue)} onChange={v => onMaxChange(toRaw(v))} placeholder={phMax || 'max'} className={inputCls} />
      {unitOpts ? (
        <select value={unit} onChange={e => setUnit(e.target.value)}
          className="w-9 py-[2px] text-[10px] text-muted-fg border border-border rounded bg-surface focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer appearance-none text-center">
          {unitOpts.map(u => <option key={u} value={u}>{u || 'sh'}</option>)}
        </select>
      ) : suffix ? (
        <span className="text-[10px] text-muted-fg w-4 text-center">{suffix}</span>
      ) : <span className="w-4" />}
    </div>
  );
}

function SelectAlertsTab({ selectedEventTypes, onEventTypesChange, currentFilters, onFiltersChange, locale }: {
  selectedEventTypes: string[]; onEventTypesChange: (t: string[]) => void;
  currentFilters: ActiveEventFilters; onFiltersChange: (f: ActiveEventFilters) => void;
  locale: 'en' | 'es';
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set(ALERT_CATEGORIES.map(c => c.id)));
  const selectedSet = useMemo(() => new Set(selectedEventTypes), [selectedEventTypes]);

  const groups = useMemo(() => {
    if (!searchQuery.trim()) return getAlertsByCategory();
    const results = searchAlerts(searchQuery, locale);
    const resultSet = new Set(results.map(a => a.eventType));
    return getAlertsByCategory()
      .map(g => ({ ...g, alerts: g.alerts.filter(a => resultSet.has(a.eventType)) }))
      .filter(g => g.alerts.length > 0);
  }, [searchQuery, locale]);

  const toggleCat = (id: string) => setExpanded(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const toggleAlert = (et: string) => {
    if (selectedSet.has(et)) {
      onEventTypesChange(selectedEventTypes.filter(t => t !== et));
    } else {
      onEventTypesChange([...selectedEventTypes, et]);
    }
  };

  const toggleCatAll = (alerts: AlertDefinition[]) => {
    const types = alerts.map(a => a.eventType);
    if (types.every(t => selectedSet.has(t))) {
      onEventTypesChange(selectedEventTypes.filter(t => !types.includes(t)));
    } else {
      onEventTypesChange([...selectedEventTypes, ...types.filter(t => !selectedSet.has(t))]);
    }
  };

  const total = ALERT_CATALOG.filter(a => a.active).length;

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-fg" />
          <input type="text"
            placeholder={locale === 'es' ? 'Buscar alertas...' : 'Search alerts...'}
            value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <span className="text-[10px] text-muted-fg">{selectedEventTypes.length}/{total} selected</span>
          <div className="flex gap-1.5">
            <button onClick={() => onEventTypesChange(ALERT_CATALOG.filter(a => a.active).map(a => a.eventType))}
              className="text-[10px] text-primary hover:text-primary font-medium">All</button>
            <span className="text-muted-fg/50">|</span>
            <button onClick={() => onEventTypesChange([])}
              className="text-[10px] text-primary hover:text-primary font-medium">None</button>
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0">
        {groups.map(({ category, alerts }) => {
          const isExp = expanded.has(category.id);
          const catTypes = alerts.map(a => a.eventType);
          const selCount = catTypes.filter(t => selectedSet.has(t)).length;
          const allSel = selCount === catTypes.length && catTypes.length > 0;
          return (
            <div key={category.id} className="border-b border-white/[0.06] last:border-0">
              <button onClick={() => toggleCat(category.id)}
                className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-[var(--color-table-row-hover)] transition-colors">
                {isExp
                  ? <ChevronDown className="w-3.5 h-3.5 text-muted-fg" />
                  : <ChevronRight className="w-3.5 h-3.5 text-muted-fg" />}
                <span className="text-xs font-semibold text-foreground flex-1 text-left">
                  {locale === 'es' ? category.nameEs : category.name}
                </span>
                <span
                  onClick={e => { e.stopPropagation(); toggleCatAll(alerts); }}
                  className={'px-1.5 py-0.5 rounded text-[10px] font-medium cursor-pointer '
                    + (allSel ? 'bg-primary/15 text-primary' : 'bg-surface-inset text-muted-fg')}>
                  {allSel ? '\u2713' : selCount + '/' + catTypes.length}
                </span>
              </button>
              {isExp && (
                <div className="pb-1">
                  {alerts.map(alert => {
                    const sel = selectedSet.has(alert.eventType);
                    const cs = alert.customSetting;
                    const csKey = `aq:${alert.eventType}` as const;
                    return (
                      <div key={alert.code} className="flex items-center gap-1 pr-2">
                        <button onClick={() => toggleAlert(alert.eventType)}
                          className={'flex-1 flex items-center gap-2 px-3 py-1 ml-3 rounded-md transition-colors text-left min-w-0 '
                            + (sel ? 'bg-primary/10 hover:bg-primary/15' : 'hover:bg-[var(--color-table-row-hover)]')}>
                          <div className={'w-3.5 h-3.5 rounded border flex-shrink-0 flex items-center justify-center '
                            + (sel ? 'bg-primary border-primary' : 'border-white/[0.1] bg-surface')}>
                            {sel && <Check className="w-2.5 h-2.5 text-white" />}
                          </div>
                          <DirectionIcon direction={alert.direction} />
                          <span className={'text-[10px] font-mono font-bold w-10 flex-shrink-0 '
                            + (sel ? 'text-primary' : 'text-muted-fg')}>{alert.code}</span>
                          <span className={'text-xs flex-1 truncate '
                            + (sel ? 'text-foreground font-medium' : 'text-foreground/80')}>
                            {locale === 'es' ? alert.nameEs : alert.name}
                          </span>
                        </button>
                        {sel && cs.type !== 'none' ? (
                          <input
                            type="number"
                            step="any"
                            placeholder={cs.defaultValue != null ? String(cs.defaultValue) : (locale === 'es' ? cs.labelEs : cs.label)}
                            title={`${locale === 'es' ? cs.labelEs : cs.label}${cs.unit ? ` (${cs.unit})` : ''}`}
                            value={currentFilters[csKey] ?? ''}
                            onClick={e => e.stopPropagation()}
                            onChange={e => {
                              const v = e.target.value;
                              const next = { ...currentFilters };
                              if (v === '') { delete next[csKey]; } else { next[csKey] = Number(v); }
                              onFiltersChange(next);
                            }}
                            className="w-14 px-1 py-[2px] text-[10px] tabular-nums border border-border rounded bg-surface text-foreground text-center focus:outline-none focus:ring-1 focus:ring-primary flex-shrink-0"
                          />
                        ) : cs.type !== 'none' ? (
                          <span className="w-14 flex-shrink-0" />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FiltersTab({ currentFilters, onFiltersChange, locale }: {
  currentFilters: ActiveEventFilters; onFiltersChange: (f: ActiveEventFilters) => void; locale: 'en' | 'es';
}) {
  const update = useCallback(
    <K extends keyof ActiveEventFilters>(key: K, value: ActiveEventFilters[K]) => {
      const u = { ...currentFilters };
      if (value === undefined || value === null) {
        delete u[key];
      } else {
        u[key] = value;
      }
      onFiltersChange(u);
    },
    [currentFilters, onFiltersChange],
  );

  const numCount = Object.entries(currentFilters)
    .filter(([k, v]) => k !== 'event_types' && v != null).length;

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">
          {locale === 'es' ? 'Filtros' : 'Filters'}
        </span>
        {numCount > 0 && (
          <button onClick={() => {
            const p: ActiveEventFilters = {};
            if (currentFilters.event_types) p.event_types = currentFilters.event_types;
            onFiltersChange(p);
          }} className="text-[10px] text-rose-600 hover:text-rose-800 font-medium flex items-center gap-1">
            <RotateCcw className="w-3 h-3" /> Clear ({numCount})
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 py-1 space-y-2">
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Price</div>
          <FilterInput label="Price" minValue={currentFilters.min_price} maxValue={currentFilters.max_price}
            onMinChange={v => update('min_price', v)} onMaxChange={v => update('max_price', v)} suffix="$" phMin="0.50" phMax="500" />
          <FilterInput label="VWAP" minValue={currentFilters.min_vwap} maxValue={currentFilters.max_vwap}
            onMinChange={v => update('min_vwap', v)} onMaxChange={v => update('max_vwap', v)} suffix="$" phMin="5" phMax="200" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Change</div>
          <FilterInput label="Change %" minValue={currentFilters.min_change_percent} maxValue={currentFilters.max_change_percent}
            onMinChange={v => update('min_change_percent', v)} onMaxChange={v => update('max_change_percent', v)} suffix="%" phMin="-10" phMax="50" />
          <FilterInput label="From Open" minValue={currentFilters.min_change_from_open} maxValue={currentFilters.max_change_from_open}
            onMinChange={v => update('min_change_from_open', v)} onMaxChange={v => update('max_change_from_open', v)} suffix="%" phMin="-5" phMax="20" />
          <FilterInput label="Gap %" minValue={currentFilters.min_gap_percent} maxValue={currentFilters.max_gap_percent}
            onMinChange={v => update('min_gap_percent', v)} onMaxChange={v => update('max_gap_percent', v)} suffix="%" phMin="-10" phMax="30" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Volume</div>
          <FilterInput label="RVOL" minValue={currentFilters.min_rvol} maxValue={currentFilters.max_rvol}
            onMinChange={v => update('min_rvol', v)} onMaxChange={v => update('max_rvol', v)} suffix="x" phMin="1" phMax="10" />
          <FilterInput label="Volume" minValue={currentFilters.min_volume} maxValue={currentFilters.max_volume}
            onMinChange={v => update('min_volume', v)} onMaxChange={v => update('max_volume', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="10" phMax="500" />
          <FilterInput label="Volume 1 Min" minValue={currentFilters.min_vol_1min} maxValue={currentFilters.max_vol_1min}
            onMinChange={v => update('min_vol_1min', v)} onMaxChange={v => update('max_vol_1min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="1" phMax="50" />
          <FilterInput label="Volume 5 Minute" minValue={currentFilters.min_vol_5min} maxValue={currentFilters.max_vol_5min}
            onMinChange={v => update('min_vol_5min', v)} onMaxChange={v => update('max_vol_5min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="1" phMax="100" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Volume (cont.)</div>
          <FilterInput label="Volume 10 Min" minValue={currentFilters.min_vol_10min} maxValue={currentFilters.max_vol_10min}
            onMinChange={v => update('min_vol_10min', v)} onMaxChange={v => update('max_vol_10min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="5" phMax="200" />
          <FilterInput label="Volume 15 Minute" minValue={currentFilters.min_vol_15min} maxValue={currentFilters.max_vol_15min}
            onMinChange={v => update('min_vol_15min', v)} onMaxChange={v => update('max_vol_15min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="10" phMax="500" />
          <FilterInput label="Volume 30 Min" minValue={currentFilters.min_vol_30min} maxValue={currentFilters.max_vol_30min}
            onMinChange={v => update('min_vol_30min', v)} onMaxChange={v => update('max_vol_30min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="20" phMax="1000" />
          <FilterInput label="Volume 1m %" minValue={currentFilters.min_vol_1min_pct} maxValue={currentFilters.max_vol_1min_pct}
            onMinChange={v => update('min_vol_1min_pct', v)} onMaxChange={v => update('max_vol_1min_pct', v)}
            suffix="%" phMin="100" phMax="500" />
          <FilterInput label="Volume 5m %" minValue={currentFilters.min_vol_5min_pct} maxValue={currentFilters.max_vol_5min_pct}
            onMinChange={v => update('min_vol_5min_pct', v)} onMaxChange={v => update('max_vol_5min_pct', v)}
            suffix="%" phMin="100" phMax="500" />
          <FilterInput label="Volume 10m %" minValue={currentFilters.min_vol_10min_pct} maxValue={currentFilters.max_vol_10min_pct}
            onMinChange={v => update('min_vol_10min_pct', v)} onMaxChange={v => update('max_vol_10min_pct', v)}
            suffix="%" phMin="100" phMax="500" />
          <FilterInput label="Volume 15m %" minValue={currentFilters.min_vol_15min_pct} maxValue={currentFilters.max_vol_15min_pct}
            onMinChange={v => update('min_vol_15min_pct', v)} onMaxChange={v => update('max_vol_15min_pct', v)}
            suffix="%" phMin="100" phMax="500" />
          <FilterInput label="Volume 30m %" minValue={currentFilters.min_vol_30min_pct} maxValue={currentFilters.max_vol_30min_pct}
            onMinChange={v => update('min_vol_30min_pct', v)} onMaxChange={v => update('max_vol_30min_pct', v)}
            suffix="%" phMin="100" phMax="500" />
          <FilterInput label="Range 2m $" minValue={currentFilters.min_range_2min} maxValue={currentFilters.max_range_2min}
            onMinChange={v => update('min_range_2min', v)} onMaxChange={v => update('max_range_2min', v)}
            suffix="$" phMin="0.10" phMax="2" />
          <FilterInput label="Range 5m $" minValue={currentFilters.min_range_5min} maxValue={currentFilters.max_range_5min}
            onMinChange={v => update('min_range_5min', v)} onMaxChange={v => update('max_range_5min', v)}
            suffix="$" phMin="0.20" phMax="5" />
          <FilterInput label="Range 15m $" minValue={currentFilters.min_range_15min} maxValue={currentFilters.max_range_15min}
            onMinChange={v => update('min_range_15min', v)} onMaxChange={v => update('max_range_15min', v)}
            suffix="$" phMin="0.50" phMax="10" />
          <FilterInput label="Range 30m $" minValue={currentFilters.min_range_30min} maxValue={currentFilters.max_range_30min}
            onMinChange={v => update('min_range_30min', v)} onMaxChange={v => update('max_range_30min', v)}
            suffix="$" phMin="1" phMax="15" />
          <FilterInput label="Range 60m $" minValue={currentFilters.min_range_60min} maxValue={currentFilters.max_range_60min}
            onMinChange={v => update('min_range_60min', v)} onMaxChange={v => update('max_range_60min', v)}
            suffix="$" phMin="1" phMax="20" />
          <FilterInput label="Range 120m $" minValue={currentFilters.min_range_120min} maxValue={currentFilters.max_range_120min}
            onMinChange={v => update('min_range_120min', v)} onMaxChange={v => update('max_range_120min', v)}
            suffix="$" phMin="2" phMax="30" />
          <FilterInput label="Range 2m %" minValue={currentFilters.min_range_2min_pct} maxValue={currentFilters.max_range_2min_pct}
            onMinChange={v => update('min_range_2min_pct', v)} onMaxChange={v => update('max_range_2min_pct', v)}
            suffix="%" phMin="50" phMax="300" />
          <FilterInput label="Range 5m %" minValue={currentFilters.min_range_5min_pct} maxValue={currentFilters.max_range_5min_pct}
            onMinChange={v => update('min_range_5min_pct', v)} onMaxChange={v => update('max_range_5min_pct', v)}
            suffix="%" phMin="50" phMax="300" />
          <FilterInput label="Range 15m %" minValue={currentFilters.min_range_15min_pct} maxValue={currentFilters.max_range_15min_pct}
            onMinChange={v => update('min_range_15min_pct', v)} onMaxChange={v => update('max_range_15min_pct', v)}
            suffix="%" phMin="50" phMax="300" />
          <FilterInput label="Range 30m %" minValue={currentFilters.min_range_30min_pct} maxValue={currentFilters.max_range_30min_pct}
            onMinChange={v => update('min_range_30min_pct', v)} onMaxChange={v => update('max_range_30min_pct', v)}
            suffix="%" phMin="50" phMax="300" />
          <FilterInput label="Range 60m %" minValue={currentFilters.min_range_60min_pct} maxValue={currentFilters.max_range_60min_pct}
            onMinChange={v => update('min_range_60min_pct', v)} onMaxChange={v => update('max_range_60min_pct', v)}
            suffix="%" phMin="50" phMax="300" />
          <FilterInput label="Range 120m %" minValue={currentFilters.min_range_120min_pct} maxValue={currentFilters.max_range_120min_pct}
            onMinChange={v => update('min_range_120min_pct', v)} onMaxChange={v => update('max_range_120min_pct', v)}
            suffix="%" phMin="50" phMax="300" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Fundamentals</div>
          <FilterInput label="Market Cap" minValue={currentFilters.min_market_cap} maxValue={currentFilters.max_market_cap}
            onMinChange={v => update('min_market_cap', v)} onMaxChange={v => update('max_market_cap', v)}
            unitOpts={['K', 'M', 'B']} defaultUnit="M" phMin="50" phMax="10" />
          <FilterInput label="Float" minValue={currentFilters.min_float_shares} maxValue={currentFilters.max_float_shares}
            onMinChange={v => update('min_float_shares', v)} onMaxChange={v => update('max_float_shares', v)}
            unitOpts={['K', 'M', 'B']} defaultUnit="M" phMin="1" phMax="100" />
          <FilterInput label="Shares Outstanding" minValue={currentFilters.min_shares_outstanding} maxValue={currentFilters.max_shares_outstanding}
            onMinChange={v => update('min_shares_outstanding', v)} onMaxChange={v => update('max_shares_outstanding', v)}
            unitOpts={['K', 'M', 'B']} defaultUnit="M" phMin="1" phMax="500" />
          <div className="flex items-center gap-1.5 px-3 py-[3px]">
            <span className="text-[11px] text-foreground/80 w-16 flex-shrink-0 font-medium truncate">Type</span>
            <select value={currentFilters.security_type || ''} onChange={e => update('security_type', e.target.value || undefined)}
              className="flex-1 px-1.5 py-[3px] text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface">
              <option value="">All</option>
              <option value="CS">Stocks (CS)</option>
              <option value="ETF">ETF</option>
              <option value="PFD">Preferred</option>
              <option value="WARRANT">Warrants</option>
            </select>
            <span className="w-4" />
          </div>
          <div className="flex items-center gap-1.5 px-3 py-[3px]">
            <span className="text-[11px] text-foreground/80 w-16 flex-shrink-0 font-medium truncate">Sector</span>
            <input type="text" value={currentFilters.sector || ''} onChange={e => update('sector', e.target.value || undefined)}
              placeholder="e.g. Technology"
              className="flex-1 px-1.5 py-[3px] text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
            <span className="w-4" />
          </div>
          <div className="flex items-center gap-1.5 px-3 py-[3px]">
            <span className="text-[11px] text-foreground/80 w-16 flex-shrink-0 font-medium truncate">Industry</span>
            <input type="text" value={currentFilters.industry || ''} onChange={e => update('industry', e.target.value || undefined)}
              placeholder="e.g. Biotechnology"
              className="flex-1 px-1.5 py-[3px] text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
            <span className="w-4" />
          </div>
        </div>

        {/* ====== DILUTION RISK ====== */}
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Dilution Risk</div>
          <div className="px-3 pb-1 text-[9px] text-muted-foreground/50">1=Low · 2=Medium · 3=High. Null tickers excluded.</div>
          {([
            { label: 'Overall',   minK: 'min_dilution_overall_risk_score',    maxK: 'max_dilution_overall_risk_score' },
            { label: 'Offering',  minK: 'min_dilution_offering_ability_score', maxK: 'max_dilution_offering_ability_score' },
            { label: 'Overhead',  minK: 'min_dilution_overhead_supply_score',  maxK: 'max_dilution_overhead_supply_score' },
            { label: 'Historical',minK: 'min_dilution_historical_score',       maxK: 'max_dilution_historical_score' },
            { label: 'Cash Need', minK: 'min_dilution_cash_need_score',        maxK: 'max_dilution_cash_need_score' },
          ] as { label: string; minK: string; maxK: string }[]).map(({ label, minK, maxK }) => (
            <div key={minK} className="flex items-center gap-1.5 px-3 py-[3px]">
              <span className="text-[11px] text-foreground/80 w-16 flex-shrink-0 font-medium truncate">{label}</span>
              <select value={(currentFilters as Record<string,unknown>)[minK] !== undefined ? String((currentFilters as Record<string,unknown>)[minK]) : ''}
                onChange={e => (update as (k: string, v: number | undefined) => void)(minK, e.target.value ? Number(e.target.value) : undefined)}
                className="flex-1 px-1.5 py-[3px] text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface">
                <option value="">Any</option>
                <option value="1">Low</option>
                <option value="2">Medium</option>
                <option value="3">High</option>
              </select>
              <span className="text-[9px] text-muted-foreground/40 mx-0.5">–</span>
              <select value={(currentFilters as Record<string,unknown>)[maxK] !== undefined ? String((currentFilters as Record<string,unknown>)[maxK]) : ''}
                onChange={e => (update as (k: string, v: number | undefined) => void)(maxK, e.target.value ? Number(e.target.value) : undefined)}
                className="flex-1 px-1.5 py-[3px] text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface">
                <option value="">Any</option>
                <option value="1">Low</option>
                <option value="2">Medium</option>
                <option value="3">High</option>
              </select>
              <span className="w-4" />
            </div>
          ))}
        </div>

        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Quote</div>
          <FilterInput label="Bid" minValue={currentFilters.min_bid} maxValue={currentFilters.max_bid}
            onMinChange={v => update('min_bid', v)} onMaxChange={v => update('max_bid', v)} suffix="$" />
          <FilterInput label="Ask" minValue={currentFilters.min_ask} maxValue={currentFilters.max_ask}
            onMinChange={v => update('min_ask', v)} onMaxChange={v => update('max_ask', v)} suffix="$" />
          <FilterInput label="Bid Size" minValue={currentFilters.min_bid_size} maxValue={currentFilters.max_bid_size}
            onMinChange={v => update('min_bid_size', v)} onMaxChange={v => update('max_bid_size', v)} phMin="100" phMax="10000" />
          <FilterInput label="Ask Size" minValue={currentFilters.min_ask_size} maxValue={currentFilters.max_ask_size}
            onMinChange={v => update('min_ask_size', v)} onMaxChange={v => update('max_ask_size', v)} phMin="100" phMax="10000" />
          <FilterInput label="Spread" minValue={currentFilters.min_spread} maxValue={currentFilters.max_spread}
            onMinChange={v => update('min_spread', v)} onMaxChange={v => update('max_spread', v)} suffix="$" phMin="0.01" phMax="0.50" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Intraday Technical</div>
          <FilterInput label="ATR %" minValue={currentFilters.min_atr_percent} maxValue={currentFilters.max_atr_percent}
            onMinChange={v => update('min_atr_percent', v)} onMaxChange={v => update('max_atr_percent', v)} suffix="%" phMin="2" phMax="10" />
          <FilterInput label="RSI" minValue={currentFilters.min_rsi} maxValue={currentFilters.max_rsi}
            onMinChange={v => update('min_rsi', v)} onMaxChange={v => update('max_rsi', v)} phMin="20" phMax="80" />
          <FilterInput label="EMA 20" minValue={currentFilters.min_ema_20} maxValue={currentFilters.max_ema_20}
            onMinChange={v => update('min_ema_20', v)} onMaxChange={v => update('max_ema_20', v)} suffix="$" />
          <FilterInput label="EMA 50" minValue={currentFilters.min_ema_50} maxValue={currentFilters.max_ema_50}
            onMinChange={v => update('min_ema_50', v)} onMaxChange={v => update('max_ema_50', v)} suffix="$" />
          <FilterInput label="SMA 5" minValue={currentFilters.min_sma_5} maxValue={currentFilters.max_sma_5}
            onMinChange={v => update('min_sma_5', v)} onMaxChange={v => update('max_sma_5', v)} suffix="$" />
          <FilterInput label="SMA 8" minValue={currentFilters.min_sma_8} maxValue={currentFilters.max_sma_8}
            onMinChange={v => update('min_sma_8', v)} onMaxChange={v => update('max_sma_8', v)} suffix="$" />
          <FilterInput label="SMA 20" minValue={currentFilters.min_sma_20} maxValue={currentFilters.max_sma_20}
            onMinChange={v => update('min_sma_20', v)} onMaxChange={v => update('max_sma_20', v)} suffix="$" />
          <FilterInput label="SMA 50" minValue={currentFilters.min_sma_50} maxValue={currentFilters.max_sma_50}
            onMinChange={v => update('min_sma_50', v)} onMaxChange={v => update('max_sma_50', v)} suffix="$" />
          <FilterInput label="SMA 200" minValue={currentFilters.min_sma_200} maxValue={currentFilters.max_sma_200}
            onMinChange={v => update('min_sma_200', v)} onMaxChange={v => update('max_sma_200', v)} suffix="$" />
          <FilterInput label="MACD" minValue={currentFilters.min_macd_line} maxValue={currentFilters.max_macd_line}
            onMinChange={v => update('min_macd_line', v)} onMaxChange={v => update('max_macd_line', v)} phMin="-5" phMax="5" />
          <FilterInput label="MACD Histogram" minValue={currentFilters.min_macd_hist} maxValue={currentFilters.max_macd_hist}
            onMinChange={v => update('min_macd_hist', v)} onMaxChange={v => update('max_macd_hist', v)} phMin="-2" phMax="2" />
          <FilterInput label="Stochastic %K" minValue={currentFilters.min_stoch_k} maxValue={currentFilters.max_stoch_k}
            onMinChange={v => update('min_stoch_k', v)} onMaxChange={v => update('max_stoch_k', v)} phMin="20" phMax="80" />
          <FilterInput label="Stochastic %D" minValue={currentFilters.min_stoch_d} maxValue={currentFilters.max_stoch_d}
            onMinChange={v => update('min_stoch_d', v)} onMaxChange={v => update('max_stoch_d', v)} phMin="20" phMax="80" />
          <FilterInput label="ADX" minValue={currentFilters.min_adx_14} maxValue={currentFilters.max_adx_14}
            onMinChange={v => update('min_adx_14', v)} onMaxChange={v => update('max_adx_14', v)} phMin="20" phMax="50" />
          <FilterInput label="Bollinger Upper" minValue={currentFilters.min_bb_upper} maxValue={currentFilters.max_bb_upper}
            onMinChange={v => update('min_bb_upper', v)} onMaxChange={v => update('max_bb_upper', v)} suffix="$" />
          <FilterInput label="Bollinger Lower" minValue={currentFilters.min_bb_lower} maxValue={currentFilters.max_bb_lower}
            onMinChange={v => update('min_bb_lower', v)} onMaxChange={v => update('max_bb_lower', v)} suffix="$" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Daily Indicators</div>
          <FilterInput label="Daily SMA 20" minValue={currentFilters.min_daily_sma_20} maxValue={currentFilters.max_daily_sma_20}
            onMinChange={v => update('min_daily_sma_20', v)} onMaxChange={v => update('max_daily_sma_20', v)} suffix="$" />
          <FilterInput label="Daily SMA 50" minValue={currentFilters.min_daily_sma_50} maxValue={currentFilters.max_daily_sma_50}
            onMinChange={v => update('min_daily_sma_50', v)} onMaxChange={v => update('max_daily_sma_50', v)} suffix="$" />
          <FilterInput label="Daily SMA 200" minValue={currentFilters.min_daily_sma_200} maxValue={currentFilters.max_daily_sma_200}
            onMinChange={v => update('min_daily_sma_200', v)} onMaxChange={v => update('max_daily_sma_200', v)} suffix="$" />
          <FilterInput label="Daily RSI" minValue={currentFilters.min_daily_rsi} maxValue={currentFilters.max_daily_rsi}
            onMinChange={v => update('min_daily_rsi', v)} onMaxChange={v => update('max_daily_rsi', v)} phMin="20" phMax="80" />
          <FilterInput label="52W High" minValue={currentFilters.min_high_52w} maxValue={currentFilters.max_high_52w}
            onMinChange={v => update('min_high_52w', v)} onMaxChange={v => update('max_high_52w', v)} suffix="$" />
          <FilterInput label="52W Low" minValue={currentFilters.min_low_52w} maxValue={currentFilters.max_low_52w}
            onMinChange={v => update('min_low_52w', v)} onMaxChange={v => update('max_low_52w', v)} suffix="$" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Time Windows</div>
          <FilterInput label="Change 1 Min" minValue={currentFilters.min_chg_1min} maxValue={currentFilters.max_chg_1min}
            onMinChange={v => update('min_chg_1min', v)} onMaxChange={v => update('max_chg_1min', v)} suffix="%" phMin="-2" phMax="5" />
          <FilterInput label="Change 1 Min $" minValue={currentFilters.min_chg_1min_dollars} maxValue={currentFilters.max_chg_1min_dollars}
            onMinChange={v => update('min_chg_1min_dollars', v)} onMaxChange={v => update('max_chg_1min_dollars', v)} suffix="$" phMin="-0.50" phMax="1.00" />
          <FilterInput label="Change 2 Min" minValue={currentFilters.min_chg_2min} maxValue={currentFilters.max_chg_2min}
            onMinChange={v => update('min_chg_2min', v)} onMaxChange={v => update('max_chg_2min', v)} suffix="%" phMin="-3" phMax="7" />
          <FilterInput label="Change 2 Min $" minValue={currentFilters.min_chg_2min_dollars} maxValue={currentFilters.max_chg_2min_dollars}
            onMinChange={v => update('min_chg_2min_dollars', v)} onMaxChange={v => update('max_chg_2min_dollars', v)} suffix="$" phMin="-0.75" phMax="1.50" />
          <FilterInput label="Change 5 Min" minValue={currentFilters.min_chg_5min} maxValue={currentFilters.max_chg_5min}
            onMinChange={v => update('min_chg_5min', v)} onMaxChange={v => update('max_chg_5min', v)} suffix="%" phMin="-5" phMax="10" />
          <FilterInput label="Change 5 Min $" minValue={currentFilters.min_chg_5min_dollars} maxValue={currentFilters.max_chg_5min_dollars}
            onMinChange={v => update('min_chg_5min_dollars', v)} onMaxChange={v => update('max_chg_5min_dollars', v)} suffix="$" phMin="-1.00" phMax="2.50" />
          <FilterInput label="Change 10 Min" minValue={currentFilters.min_chg_10min} maxValue={currentFilters.max_chg_10min}
            onMinChange={v => update('min_chg_10min', v)} onMaxChange={v => update('max_chg_10min', v)} suffix="%" phMin="-5" phMax="15" />
          <FilterInput label="Change 10 Min $" minValue={currentFilters.min_chg_10min_dollars} maxValue={currentFilters.max_chg_10min_dollars}
            onMinChange={v => update('min_chg_10min_dollars', v)} onMaxChange={v => update('max_chg_10min_dollars', v)} suffix="$" phMin="-1.50" phMax="4.00" />
          <FilterInput label="Change 15 Min" minValue={currentFilters.min_chg_15min} maxValue={currentFilters.max_chg_15min}
            onMinChange={v => update('min_chg_15min', v)} onMaxChange={v => update('max_chg_15min', v)} suffix="%" phMin="-8" phMax="20" />
          <FilterInput label="Change 15 Min $" minValue={currentFilters.min_chg_15min_dollars} maxValue={currentFilters.max_chg_15min_dollars}
            onMinChange={v => update('min_chg_15min_dollars', v)} onMaxChange={v => update('max_chg_15min_dollars', v)} suffix="$" phMin="-2.00" phMax="5.00" />
          <FilterInput label="Change 30 Min" minValue={currentFilters.min_chg_30min} maxValue={currentFilters.max_chg_30min}
            onMinChange={v => update('min_chg_30min', v)} onMaxChange={v => update('max_chg_30min', v)} suffix="%" phMin="-10" phMax="25" />
          <FilterInput label="Change 30 Min $" minValue={currentFilters.min_chg_30min_dollars} maxValue={currentFilters.max_chg_30min_dollars}
            onMinChange={v => update('min_chg_30min_dollars', v)} onMaxChange={v => update('max_chg_30min_dollars', v)} suffix="$" phMin="-3.00" phMax="7.00" />
          <FilterInput label="Change 60 Min" minValue={currentFilters.min_chg_60min} maxValue={currentFilters.max_chg_60min}
            onMinChange={v => update('min_chg_60min', v)} onMaxChange={v => update('max_chg_60min', v)} suffix="%" phMin="-15" phMax="30" />
          <FilterInput label="Change 60 Min $" minValue={currentFilters.min_chg_60min_dollars} maxValue={currentFilters.max_chg_60min_dollars}
            onMinChange={v => update('min_chg_60min_dollars', v)} onMaxChange={v => update('max_chg_60min_dollars', v)} suffix="$" phMin="-5.00" phMax="10.00" />
          <FilterInput label="Change 120 Min" minValue={currentFilters.min_chg_120min} maxValue={currentFilters.max_chg_120min}
            onMinChange={v => update('min_chg_120min', v)} onMaxChange={v => update('max_chg_120min', v)} suffix="%" phMin="-20" phMax="40" />
          <FilterInput label="Change 120 Min $" minValue={currentFilters.min_chg_120min_dollars} maxValue={currentFilters.max_chg_120min_dollars}
            onMinChange={v => update('min_chg_120min_dollars', v)} onMaxChange={v => update('max_chg_120min_dollars', v)} suffix="$" phMin="-8.00" phMax="15.00" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Trades Anomaly</div>
          <FilterInput label="Trades" minValue={currentFilters.min_trades_today} maxValue={currentFilters.max_trades_today}
            onMinChange={v => update('min_trades_today', v)} onMaxChange={v => update('max_trades_today', v)}
            unitOpts={['', 'K']} defaultUnit="" phMin="100" phMax="10000" />
          <FilterInput label="Z-Score" minValue={currentFilters.min_trades_z_score} maxValue={currentFilters.max_trades_z_score}
            onMinChange={v => update('min_trades_z_score', v)} onMaxChange={v => update('max_trades_z_score', v)} phMin="1" phMax="5" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Derived</div>
          <FilterInput label="Dollar Volume" minValue={currentFilters.min_dollar_volume} maxValue={currentFilters.max_dollar_volume}
            onMinChange={v => update('min_dollar_volume', v)} onMaxChange={v => update('max_dollar_volume', v)}
            unitOpts={['', 'K', 'M', 'B']} defaultUnit="M" phMin="1" phMax="100" />
          <FilterInput label="Today's Range $" minValue={currentFilters.min_todays_range} maxValue={currentFilters.max_todays_range}
            onMinChange={v => update('min_todays_range', v)} onMaxChange={v => update('max_todays_range', v)} phMin="0.1" phMax="10" />
          <FilterInput label="Today's Range %" minValue={currentFilters.min_todays_range_pct} maxValue={currentFilters.max_todays_range_pct}
            onMinChange={v => update('min_todays_range_pct', v)} onMaxChange={v => update('max_todays_range_pct', v)} phMin="1" phMax="20" />
          <FilterInput label="Bid/Ask Ratio" minValue={currentFilters.min_bid_ask_ratio} maxValue={currentFilters.max_bid_ask_ratio}
            onMinChange={v => update('min_bid_ask_ratio', v)} onMaxChange={v => update('max_bid_ask_ratio', v)} phMin="0.5" phMax="3" />
          <FilterInput label="Float Turnover" minValue={currentFilters.min_float_turnover} maxValue={currentFilters.max_float_turnover}
            onMinChange={v => update('min_float_turnover', v)} onMaxChange={v => update('max_float_turnover', v)} phMin="0.01" phMax="5" />
          <FilterInput label="Position in Range" minValue={currentFilters.min_pos_in_range} maxValue={currentFilters.max_pos_in_range}
            onMinChange={v => update('min_pos_in_range', v)} onMaxChange={v => update('max_pos_in_range', v)} phMin="0" phMax="100" />
          <FilterInput label="Below High" minValue={currentFilters.min_below_high} maxValue={currentFilters.max_below_high}
            onMinChange={v => update('min_below_high', v)} onMaxChange={v => update('max_below_high', v)} phMin="0" phMax="5" />
          <FilterInput label="Above Low" minValue={currentFilters.min_above_low} maxValue={currentFilters.max_above_low}
            onMinChange={v => update('min_above_low', v)} onMaxChange={v => update('max_above_low', v)} phMin="0" phMax="5" />
          <FilterInput label="Position of Open" minValue={currentFilters.min_pos_of_open} maxValue={currentFilters.max_pos_of_open}
            onMinChange={v => update('min_pos_of_open', v)} onMaxChange={v => update('max_pos_of_open', v)} suffix="%" phMin="0" phMax="100" />
          <FilterInput label="Previous Volume" minValue={currentFilters.min_prev_day_volume} maxValue={currentFilters.max_prev_day_volume}
            onMinChange={v => update('min_prev_day_volume', v)} onMaxChange={v => update('max_prev_day_volume', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="100" phMax="10000" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Distance %</div>
          <FilterInput label="Distance VWAP" minValue={currentFilters.min_dist_from_vwap} maxValue={currentFilters.max_dist_from_vwap}
            onMinChange={v => update('min_dist_from_vwap', v)} onMaxChange={v => update('max_dist_from_vwap', v)} phMin="-10" phMax="10" />
          <FilterInput label="Distance SMA 5" minValue={currentFilters.min_dist_sma_5} maxValue={currentFilters.max_dist_sma_5}
            onMinChange={v => update('min_dist_sma_5', v)} onMaxChange={v => update('max_dist_sma_5', v)} phMin="-5" phMax="5" />
          <FilterInput label="Distance SMA 8" minValue={currentFilters.min_dist_sma_8} maxValue={currentFilters.max_dist_sma_8}
            onMinChange={v => update('min_dist_sma_8', v)} onMaxChange={v => update('max_dist_sma_8', v)} phMin="-5" phMax="5" />
          <FilterInput label="Distance SMA 20" minValue={currentFilters.min_dist_sma_20} maxValue={currentFilters.max_dist_sma_20}
            onMinChange={v => update('min_dist_sma_20', v)} onMaxChange={v => update('max_dist_sma_20', v)} phMin="-10" phMax="10" />
          <FilterInput label="Distance SMA 50" minValue={currentFilters.min_dist_sma_50} maxValue={currentFilters.max_dist_sma_50}
            onMinChange={v => update('min_dist_sma_50', v)} onMaxChange={v => update('max_dist_sma_50', v)} phMin="-20" phMax="20" />
          <FilterInput label="Distance SMA 200" minValue={currentFilters.min_dist_sma_200} maxValue={currentFilters.max_dist_sma_200}
            onMinChange={v => update('min_dist_sma_200', v)} onMaxChange={v => update('max_dist_sma_200', v)} phMin="-50" phMax="50" />
          <FilterInput label="Dist Daily SMA 20" minValue={currentFilters.min_dist_daily_sma_20} maxValue={currentFilters.max_dist_daily_sma_20}
            onMinChange={v => update('min_dist_daily_sma_20', v)} onMaxChange={v => update('max_dist_daily_sma_20', v)} phMin="-10" phMax="10" />
          <FilterInput label="Dist Daily SMA 50" minValue={currentFilters.min_dist_daily_sma_50} maxValue={currentFilters.max_dist_daily_sma_50}
            onMinChange={v => update('min_dist_daily_sma_50', v)} onMaxChange={v => update('max_dist_daily_sma_50', v)} phMin="-20" phMax="20" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Multi-Day Change %</div>
          <FilterInput label="Change Previous Day" minValue={currentFilters.min_change_1d} maxValue={currentFilters.max_change_1d}
            onMinChange={v => update('min_change_1d', v)} onMaxChange={v => update('max_change_1d', v)} phMin="-10" phMax="10" />
          <FilterInput label="3 Days" minValue={currentFilters.min_change_3d} maxValue={currentFilters.max_change_3d}
            onMinChange={v => update('min_change_3d', v)} onMaxChange={v => update('max_change_3d', v)} phMin="-20" phMax="20" />
          <FilterInput label="Change in 5 Days" minValue={currentFilters.min_change_5d} maxValue={currentFilters.max_change_5d}
            onMinChange={v => update('min_change_5d', v)} onMaxChange={v => update('max_change_5d', v)} phMin="-20" phMax="50" />
          <FilterInput label="Change in 10 Days" minValue={currentFilters.min_change_10d} maxValue={currentFilters.max_change_10d}
            onMinChange={v => update('min_change_10d', v)} onMaxChange={v => update('max_change_10d', v)} phMin="-30" phMax="100" />
          <FilterInput label="20 Days" minValue={currentFilters.min_change_20d} maxValue={currentFilters.max_change_20d}
            onMinChange={v => update('min_change_20d', v)} onMaxChange={v => update('max_change_20d', v)} phMin="-50" phMax="200" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Avg Volume</div>
          <FilterInput label="Avg Daily Volume 5D" minValue={currentFilters.min_avg_volume_5d} maxValue={currentFilters.max_avg_volume_5d}
            onMinChange={v => update('min_avg_volume_5d', v)} onMaxChange={v => update('max_avg_volume_5d', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="100" phMax="5000" />
          <FilterInput label="Average 10 Day" minValue={currentFilters.min_avg_volume_10d} maxValue={currentFilters.max_avg_volume_10d}
            onMinChange={v => update('min_avg_volume_10d', v)} onMaxChange={v => update('max_avg_volume_10d', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="100" phMax="5000" />
          <FilterInput label="Avg Daily Volume 20D" minValue={currentFilters.min_avg_volume_20d} maxValue={currentFilters.max_avg_volume_20d}
            onMinChange={v => update('min_avg_volume_20d', v)} onMaxChange={v => update('max_avg_volume_20d', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="100" phMax="5000" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">52W / Daily Extra</div>
          <FilterInput label="From 52W High %" minValue={currentFilters.min_from_52w_high} maxValue={currentFilters.max_from_52w_high}
            onMinChange={v => update('min_from_52w_high', v)} onMaxChange={v => update('max_from_52w_high', v)} phMin="-80" phMax="0" />
          <FilterInput label="From 52W Low %" minValue={currentFilters.min_from_52w_low} maxValue={currentFilters.max_from_52w_low}
            onMinChange={v => update('min_from_52w_low', v)} onMaxChange={v => update('max_from_52w_low', v)} phMin="0" phMax="500" />
          <FilterInput label="Daily ADX" minValue={currentFilters.min_daily_adx_14} maxValue={currentFilters.max_daily_adx_14}
            onMinChange={v => update('min_daily_adx_14', v)} onMaxChange={v => update('max_daily_adx_14', v)} phMin="20" phMax="50" />
          <FilterInput label="Daily ATR %" minValue={currentFilters.min_daily_atr_percent} maxValue={currentFilters.max_daily_atr_percent}
            onMinChange={v => update('min_daily_atr_percent', v)} onMaxChange={v => update('max_daily_atr_percent', v)} phMin="1" phMax="15" />
          <FilterInput label="Daily BB Position" minValue={currentFilters.min_daily_bb_position} maxValue={currentFilters.max_daily_bb_position}
            onMinChange={v => update('min_daily_bb_position', v)} onMaxChange={v => update('max_daily_bb_position', v)} phMin="0" phMax="100" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Pivot Points (%)</div>
          <FilterInput label="Dist Pivot" minValue={currentFilters.min_dist_pivot} maxValue={currentFilters.max_dist_pivot} onMinChange={v => update('min_dist_pivot', v)} onMaxChange={v => update('max_dist_pivot', v)} phMin="-5" phMax="5" />
          <FilterInput label="Dist R1" minValue={currentFilters.min_dist_pivot_r1} maxValue={currentFilters.max_dist_pivot_r1} onMinChange={v => update('min_dist_pivot_r1', v)} onMaxChange={v => update('max_dist_pivot_r1', v)} phMin="-5" phMax="5" />
          <FilterInput label="Dist S1" minValue={currentFilters.min_dist_pivot_s1} maxValue={currentFilters.max_dist_pivot_s1} onMinChange={v => update('min_dist_pivot_s1', v)} onMaxChange={v => update('max_dist_pivot_s1', v)} phMin="-5" phMax="5" />
          <FilterInput label="Dist R2" minValue={currentFilters.min_dist_pivot_r2} maxValue={currentFilters.max_dist_pivot_r2} onMinChange={v => update('min_dist_pivot_r2', v)} onMaxChange={v => update('max_dist_pivot_r2', v)} phMin="-5" phMax="5" />
          <FilterInput label="Dist S2" minValue={currentFilters.min_dist_pivot_s2} maxValue={currentFilters.max_dist_pivot_s2} onMinChange={v => update('min_dist_pivot_s2', v)} onMaxChange={v => update('max_dist_pivot_s2', v)} phMin="-5" phMax="5" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Candles / Range TF</div>
          <FilterInput label="Consec Candles 1m" minValue={currentFilters.min_consecutive_candles} maxValue={currentFilters.max_consecutive_candles} onMinChange={v => update('min_consecutive_candles', v)} onMaxChange={v => update('max_consecutive_candles', v)} phMin="-10" phMax="10" />
          <FilterInput label="Consec Candles 2m" minValue={currentFilters.min_consecutive_candles_2m} maxValue={currentFilters.max_consecutive_candles_2m} onMinChange={v => update('min_consecutive_candles_2m', v)} onMaxChange={v => update('max_consecutive_candles_2m', v)} phMin="-10" phMax="10" />
          <FilterInput label="Consec Candles 5m" minValue={currentFilters.min_consecutive_candles_5m} maxValue={currentFilters.max_consecutive_candles_5m} onMinChange={v => update('min_consecutive_candles_5m', v)} onMaxChange={v => update('max_consecutive_candles_5m', v)} phMin="-10" phMax="10" />
          <FilterInput label="Consec Candles 10m" minValue={currentFilters.min_consecutive_candles_10m} maxValue={currentFilters.max_consecutive_candles_10m} onMinChange={v => update('min_consecutive_candles_10m', v)} onMaxChange={v => update('max_consecutive_candles_10m', v)} phMin="-10" phMax="10" />
          <FilterInput label="Consec Candles 15m" minValue={currentFilters.min_consecutive_candles_15m} maxValue={currentFilters.max_consecutive_candles_15m} onMinChange={v => update('min_consecutive_candles_15m', v)} onMaxChange={v => update('max_consecutive_candles_15m', v)} phMin="-10" phMax="10" />
          <FilterInput label="Consec Candles 30m" minValue={currentFilters.min_consecutive_candles_30m} maxValue={currentFilters.max_consecutive_candles_30m} onMinChange={v => update('min_consecutive_candles_30m', v)} onMaxChange={v => update('max_consecutive_candles_30m', v)} phMin="-10" phMax="10" />
          <FilterInput label="Consec Candles 60m" minValue={currentFilters.min_consecutive_candles_60m} maxValue={currentFilters.max_consecutive_candles_60m} onMinChange={v => update('min_consecutive_candles_60m', v)} onMaxChange={v => update('max_consecutive_candles_60m', v)} phMin="-10" phMax="10" />
          <FilterInput label="Pos Range 5m" minValue={currentFilters.min_pos_in_range_5m} maxValue={currentFilters.max_pos_in_range_5m} onMinChange={v => update('min_pos_in_range_5m', v)} onMaxChange={v => update('max_pos_in_range_5m', v)} phMin="0" phMax="100" />
          <FilterInput label="Pos Range 15m" minValue={currentFilters.min_pos_in_range_15m} maxValue={currentFilters.max_pos_in_range_15m} onMinChange={v => update('min_pos_in_range_15m', v)} onMaxChange={v => update('max_pos_in_range_15m', v)} phMin="0" phMax="100" />
          <FilterInput label="Pos Range 30m" minValue={currentFilters.min_pos_in_range_30m} maxValue={currentFilters.max_pos_in_range_30m} onMinChange={v => update('min_pos_in_range_30m', v)} onMaxChange={v => update('max_pos_in_range_30m', v)} phMin="0" phMax="100" />
          <FilterInput label="Pos Range 60m" minValue={currentFilters.min_pos_in_range_60m} maxValue={currentFilters.max_pos_in_range_60m} onMinChange={v => update('min_pos_in_range_60m', v)} onMaxChange={v => update('max_pos_in_range_60m', v)} phMin="0" phMax="100" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">RSI / BB Multi-TF</div>
          <FilterInput label="RSI 2m" minValue={currentFilters.min_rsi_2m} maxValue={currentFilters.max_rsi_2m} onMinChange={v => update('min_rsi_2m', v)} onMaxChange={v => update('max_rsi_2m', v)} phMin="20" phMax="80" />
          <FilterInput label="RSI 5m" minValue={currentFilters.min_rsi_5m} maxValue={currentFilters.max_rsi_5m} onMinChange={v => update('min_rsi_5m', v)} onMaxChange={v => update('max_rsi_5m', v)} phMin="20" phMax="80" />
          <FilterInput label="RSI 15m" minValue={currentFilters.min_rsi_15m} maxValue={currentFilters.max_rsi_15m} onMinChange={v => update('min_rsi_15m', v)} onMaxChange={v => update('max_rsi_15m', v)} phMin="20" phMax="80" />
          <FilterInput label="RSI 60m" minValue={currentFilters.min_rsi_60m} maxValue={currentFilters.max_rsi_60m} onMinChange={v => update('min_rsi_60m', v)} onMaxChange={v => update('max_rsi_60m', v)} phMin="20" phMax="80" />
          <FilterInput label="BB Pos 1m" minValue={currentFilters.min_bb_position_1m} maxValue={currentFilters.max_bb_position_1m} onMinChange={v => update('min_bb_position_1m', v)} onMaxChange={v => update('max_bb_position_1m', v)} phMin="0" phMax="100" />
          <FilterInput label="BB Pos 5m" minValue={currentFilters.min_bb_position_5m} maxValue={currentFilters.max_bb_position_5m} onMinChange={v => update('min_bb_position_5m', v)} onMaxChange={v => update('max_bb_position_5m', v)} phMin="0" phMax="100" />
          <FilterInput label="BB Pos 15m" minValue={currentFilters.min_bb_position_15m} maxValue={currentFilters.max_bb_position_15m} onMinChange={v => update('min_bb_position_15m', v)} onMaxChange={v => update('max_bb_position_15m', v)} phMin="0" phMax="100" />
          <FilterInput label="BB Pos 60m" minValue={currentFilters.min_bb_position_60m} maxValue={currentFilters.max_bb_position_60m} onMinChange={v => update('min_bb_position_60m', v)} onMaxChange={v => update('max_bb_position_60m', v)} phMin="0" phMax="100" />
          <FilterInput label="Change 2 Min" minValue={currentFilters.min_chg_2min} maxValue={currentFilters.max_chg_2min} onMinChange={v => update('min_chg_2min', v)} onMaxChange={v => update('max_chg_2min', v)} phMin="-5" phMax="5" />
          <FilterInput label="Change 120 Min" minValue={currentFilters.min_chg_120min} maxValue={currentFilters.max_chg_120min} onMinChange={v => update('min_chg_120min', v)} onMaxChange={v => update('max_chg_120min', v)} phMin="-10" phMax="10" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Extra Filters</div>
          <FilterInput label="Volume Today %" minValue={currentFilters.min_volume_today_pct} maxValue={currentFilters.max_volume_today_pct} onMinChange={v => update('min_volume_today_pct', v)} onMaxChange={v => update('max_volume_today_pct', v)} phMin="50" phMax="200" />
          <FilterInput label="Volume Yesterday %" minValue={currentFilters.min_volume_yesterday_pct} maxValue={currentFilters.max_volume_yesterday_pct} onMinChange={v => update('min_volume_yesterday_pct', v)} onMaxChange={v => update('max_volume_yesterday_pct', v)} phMin="50" phMax="200" />
          <FilterInput label="Minute Volume" minValue={currentFilters.min_minute_volume} maxValue={currentFilters.max_minute_volume} onMinChange={v => update('min_minute_volume', v)} onMaxChange={v => update('max_minute_volume', v)} phMin="1000" phMax="1000000" />
          <FilterInput label="From High" minValue={currentFilters.min_price_from_high} maxValue={currentFilters.max_price_from_high} onMinChange={v => update('min_price_from_high', v)} onMaxChange={v => update('max_price_from_high', v)} phMin="-20" phMax="0" />
          <FilterInput label="From Low" minValue={currentFilters.min_price_from_low} maxValue={currentFilters.max_price_from_low} onMinChange={v => update('min_price_from_low', v)} onMaxChange={v => update('max_price_from_low', v)} phMin="0" phMax="20" />
          <FilterInput label="From Intraday High" minValue={currentFilters.min_price_from_intraday_high} maxValue={currentFilters.max_price_from_intraday_high} onMinChange={v => update('min_price_from_intraday_high', v)} onMaxChange={v => update('max_price_from_intraday_high', v)} phMin="-10" phMax="0" />
          <FilterInput label="From Intraday Low" minValue={currentFilters.min_price_from_intraday_low} maxValue={currentFilters.max_price_from_intraday_low} onMinChange={v => update('min_price_from_intraday_low', v)} onMaxChange={v => update('max_price_from_intraday_low', v)} phMin="0" phMax="10" />
          <FilterInput label="Pre-Market Change %" minValue={currentFilters.min_premarket_change_percent} maxValue={currentFilters.max_premarket_change_percent} onMinChange={v => update('min_premarket_change_percent', v)} onMaxChange={v => update('max_premarket_change_percent', v)} phMin="-10" phMax="10" />
          <FilterInput label="Post-Market Change %" minValue={currentFilters.min_postmarket_change_percent} maxValue={currentFilters.max_postmarket_change_percent} onMinChange={v => update('min_postmarket_change_percent', v)} onMaxChange={v => update('max_postmarket_change_percent', v)} phMin="-10" phMax="10" />
          <FilterInput label="Post-Market Volume" minValue={currentFilters.min_postmarket_volume} maxValue={currentFilters.max_postmarket_volume} onMinChange={v => update('min_postmarket_volume', v)} onMaxChange={v => update('max_postmarket_volume', v)} phMin="10000" phMax="1000000" />
          <FilterInput label="Avg Volume 3M" minValue={currentFilters.min_avg_volume_3m} maxValue={currentFilters.max_avg_volume_3m} onMinChange={v => update('min_avg_volume_3m', v)} onMaxChange={v => update('max_avg_volume_3m', v)} phMin="100000" phMax="10000000" />
          <FilterInput label="Change Open $" minValue={currentFilters.min_change_from_open_dollars} maxValue={currentFilters.max_change_from_open_dollars} onMinChange={v => update('min_change_from_open_dollars', v)} onMaxChange={v => update('max_change_from_open_dollars', v)} phMin="-5" phMax="5" />
          <FilterInput label="Distance NBBO" minValue={currentFilters.min_distance_from_nbbo} maxValue={currentFilters.max_distance_from_nbbo} onMinChange={v => update('min_distance_from_nbbo', v)} onMaxChange={v => update('max_distance_from_nbbo', v)} phMin="0" phMax="5" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-muted-fg uppercase tracking-wider">Symbols</div>
          <div className="px-3 py-1.5">
            <span className="text-xs text-foreground/80 font-medium block mb-1">Include</span>
            <input type="text" value={(currentFilters.symbols_include || []).join(', ')}
              onChange={e => {
                const v = e.target.value.trim();
                update('symbols_include',
                  v ? v.split(',').map(s => s.trim().toUpperCase()).filter(Boolean) : undefined);
              }}
              placeholder="AAPL, TSLA..."
              className="w-full px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface font-mono" />
          </div>
          <div className="px-3 py-1.5">
            <span className="text-xs text-foreground/80 font-medium block mb-1">Exclude</span>
            <input type="text" value={(currentFilters.symbols_exclude || []).join(', ')}
              onChange={e => {
                const v = e.target.value.trim();
                update('symbols_exclude',
                  v ? v.split(',').map(s => s.trim().toUpperCase()).filter(Boolean) : undefined);
              }}
              placeholder="SPY, QQQ..."
              className="w-full px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface font-mono" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Strategy folders
// ============================================================================

const STRATEGY_FOLDERS = [
  { id: 'recent', label: 'Recent', labelEs: 'Recientes' },
  { id: 'favorites', label: 'Favorites', labelEs: 'Favoritos' },
  { id: 'bullish', label: 'Bullish Strategies', labelEs: 'Estrategias Alcistas' },
  { id: 'bearish', label: 'Bearish Strategies', labelEs: 'Estrategias Bajistas' },
  { id: 'neutral', label: 'Neutral Strategies', labelEs: 'Estrategias Neutrales' },
  { id: 'custom', label: 'My Strategies', labelEs: 'Mis Estrategias' },
  { id: 'builtin', label: 'Built-in', labelEs: 'Del Sistema' },
] as const;

function StrategyItem({ name, description, alertCount, useCount, isFavorite, onLoad, onDelete, onToggleFav }: {
  name: string; description?: string | null; alertCount: number; useCount?: number;
  isFavorite?: boolean; onLoad: () => void; onDelete?: () => void; onToggleFav?: () => void;
}) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-[var(--color-table-row-hover)] transition-colors group">
      <button onClick={onLoad} className="flex-1 text-left min-w-0">
        <div className="text-xs font-medium text-foreground truncate">{name}</div>
        {description && <div className="text-[10px] text-muted-fg truncate">{description}</div>}
        <div className="text-[10px] text-muted-fg">
          {alertCount} alerts{useCount ? ` \u00b7 ${useCount}x used` : ''}
        </div>
      </button>
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        {onToggleFav && (
          <button onClick={onToggleFav}
            className={`p-0.5 rounded text-[10px] ${isFavorite ? 'text-primary' : 'text-muted-fg/50 hover:text-muted-fg'}`}
            title="Favorite"
          >\u2605</button>
        )}
        {onDelete && (
          <button onClick={onDelete}
            className="p-0.5 text-muted-fg/50 hover:text-rose-500 rounded transition-colors">
            <Trash2 className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  );
}

function StrategiesTab({ selectedEventTypes, currentFilters, onApplyPreset, locale }: {
  selectedEventTypes: string[]; currentFilters: ActiveEventFilters;
  onApplyPreset: (et: string[], f: AlertPresetFilters) => void; locale: 'en' | 'es';
}) {
  const {
    strategies, loading, createStrategy, deleteStrategy,
    useStrategy, toggleFavorite, getRecent, getFavorites, getByCategory,
  } = useAlertStrategies();

  // Migrate localStorage presets on first load
  const localPresets = useAlertPresetsStore(s => s.presets);
  const clearLocalPresets = useAlertPresetsStore(s => s.deletePreset);
  const migratedRef = useMemo(() => ({ done: false }), []);

  useEffect(() => {
    if (migratedRef.done || loading || localPresets.length === 0) return;
    migratedRef.done = true;
    // Migrate each localStorage preset to server
    localPresets.forEach(async (p) => {
      const exists = strategies.some(s => s.name === p.name);
      if (!exists) {
        await createStrategy({
          name: p.name,
          category: 'custom',
          event_types: p.eventTypes,
          filters: p.filters as Record<string, number | string | undefined>,
        });
      }
      clearLocalPresets(p.id);
    });
  }, [loading, localPresets, strategies, createStrategy, clearLocalPresets, migratedRef]);

  const [saveName, setSaveName] = useState('');
  const [saveCategory, setSaveCategory] = useState('custom');
  const [showSave, setShowSave] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['recent', 'custom', 'builtin']));

  const toggleFolder = (id: string) => setExpandedFolders(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });

  const handleSave = async () => {
    if (!saveName.trim() || selectedEventTypes.length === 0) return;
    const { event_types, symbols_include, symbols_exclude, watchlist_only, ...numFilters } = currentFilters;
    await createStrategy({
      name: saveName.trim(),
      category: saveCategory,
      event_types: selectedEventTypes,
      filters: numFilters,
    });
    setSaveName('');
    setShowSave(false);
  };

  const handleLoadStrategy = async (s: AlertStrategy) => {
    onApplyPreset(s.eventTypes, s.filters);
    await useStrategy(s.id);
  };

  const handleLoadBuiltIn = (preset: typeof BUILT_IN_PRESETS[number]) => {
    onApplyPreset(preset.eventTypes, preset.filters);
  };

  const recent = getRecent(5);
  const favorites = getFavorites();
  const bullish = getByCategory('bullish');
  const bearish = getByCategory('bearish');
  const neutral = getByCategory('neutral');
  const custom = getByCategory('custom');

  const folderData: Record<string, { items: AlertStrategy[]; empty: string }> = {
    recent: { items: recent, empty: locale === 'es' ? 'Sin uso reciente' : 'No recent usage' },
    favorites: { items: favorites, empty: locale === 'es' ? 'Sin favoritos' : 'No favorites' },
    bullish: { items: bullish, empty: locale === 'es' ? 'Sin estrategias alcistas' : 'No bullish strategies' },
    bearish: { items: bearish, empty: locale === 'es' ? 'Sin estrategias bajistas' : 'No bearish strategies' },
    neutral: { items: neutral, empty: locale === 'es' ? 'Sin estrategias neutrales' : 'No neutral strategies' },
    custom: { items: custom, empty: locale === 'es' ? 'Sin estrategias custom' : 'No custom strategies' },
  };

  return (
    <div className="flex flex-col h-full">
      {/* Save bar */}
      <div className="px-3 py-2 border-b border-border">
        {showSave ? (
          <div className="space-y-1.5">
            <div className="flex gap-1.5">
              <input type="text" value={saveName} onChange={e => setSaveName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
                placeholder={locale === 'es' ? 'Nombre...' : 'Name...'} autoFocus
                className="flex-1 px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
              <button onClick={handleSave} disabled={!saveName.trim()}
                className="px-2 py-1 text-xs bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-40 transition-colors font-medium">
                Save
              </button>
              <button onClick={() => { setShowSave(false); setSaveName(''); }}
                className="px-1.5 py-1 text-xs text-muted-fg hover:text-foreground/80 transition-colors">
                x
              </button>
            </div>
            <select value={saveCategory} onChange={e => setSaveCategory(e.target.value)}
              className="w-full px-2 py-1 text-[11px] border border-border rounded bg-surface text-foreground/80 focus:outline-none focus:ring-1 focus:ring-primary">
              <option value="custom">Custom</option>
              <option value="bullish">Bullish</option>
              <option value="bearish">Bearish</option>
              <option value="neutral">Neutral</option>
            </select>
          </div>
        ) : (
          <button onClick={() => setShowSave(true)} disabled={selectedEventTypes.length === 0}
            className="w-full px-3 py-1.5 text-xs font-medium text-primary border border-primary/30 rounded hover:bg-primary/10 disabled:opacity-40 transition-colors">
            {locale === 'es' ? 'Guardar Estrategia' : 'Save Strategy'}
          </button>
        )}
      </div>

      {/* Folders */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {loading && (
          <div className="px-3 py-3 text-[10px] text-muted-fg text-center">
            {locale === 'es' ? 'Cargando...' : 'Loading...'}
          </div>
        )}

        {/* Start from Scratch */}
        <button onClick={() => { onApplyPreset([], {}); }}
          className="w-full text-left px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 border-b border-border-subtle transition-colors">
          {locale === 'es' ? 'Empezar de Cero' : 'Start from Scratch'}
        </button>

        {/* User strategy folders */}
        {STRATEGY_FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
          const data = folderData[folder.id];
          if (!data) return null;
          const exp = expandedFolders.has(folder.id);
          const count = data.items.length;
          return (
            <div key={folder.id} className="border-b border-border-subtle">
              <button onClick={() => toggleFolder(folder.id)}
                className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left hover:bg-[var(--color-table-row-hover)] transition-colors">
                <span className="text-[10px] text-muted-fg">{exp ? '\u25BC' : '\u25B6'}</span>
                <span className="text-xs font-semibold text-foreground/80 flex-1">
                  {locale === 'es' ? folder.labelEs : folder.label}
                </span>
                {count > 0 && <span className="text-[10px] text-muted-fg">{count}</span>}
              </button>
              {exp && (
                <div className="pb-1">
                  {data.items.length === 0 ? (
                    <div className="px-5 py-1 text-[10px] text-muted-fg/50">{data.empty}</div>
                  ) : (
                    data.items.map(s => (
                      <StrategyItem key={s.id} name={s.name} description={s.description}
                        alertCount={s.eventTypes.length} useCount={s.useCount} isFavorite={s.isFavorite}
                        onLoad={() => handleLoadStrategy(s)}
                        onDelete={() => deleteStrategy(s.id)}
                        onToggleFav={() => toggleFavorite(s.id)}
                      />
                    ))
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Built-in strategies */}
        <div className="border-b border-border-subtle">
          <button onClick={() => toggleFolder('builtin')}
            className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left hover:bg-[var(--color-table-row-hover)] transition-colors">
            <span className="text-[10px] text-muted-fg">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
            <span className="text-xs font-semibold text-foreground/80 flex-1">
              {locale === 'es' ? 'Del Sistema' : 'Built-in'}
            </span>
            <span className="text-[10px] text-muted-fg">{BUILT_IN_PRESETS.length}</span>
          </button>
          {expandedFolders.has('builtin') && (
            <div className="pb-1">
              {BUILT_IN_PRESETS.map(preset => (
                <div key={preset.id} className="px-3 py-1.5 hover:bg-[var(--color-table-row-hover)] transition-colors">
                  <button onClick={() => handleLoadBuiltIn(preset)} className="w-full text-left">
                    <div className="text-xs font-medium text-foreground">
                      {locale === 'es' ? preset.nameEs : preset.name}
                    </div>
                    <div className="text-[10px] text-muted-fg truncate">
                      {locale === 'es' ? preset.descriptionEs : preset.description}
                    </div>
                    <div className="text-[10px] text-muted-fg">{preset.eventTypes.length} alerts</div>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function AlertConfigPanel({
  selectedEventTypes, currentFilters, onEventTypesChange,
  onFiltersChange, onClose, locale = 'en',
}: AlertConfigPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('alerts');

  const handleApplyPreset = useCallback(
    (eventTypes: string[], filters: AlertPresetFilters) => {
      onEventTypesChange(eventTypes);
      onFiltersChange({ ...filters, event_types: eventTypes });
    },
    [onEventTypesChange, onFiltersChange],
  );

  const tabs: { id: TabId; label: string }[] = [
    { id: 'alerts', label: locale === 'es' ? 'Alertas' : 'Alerts' },
    { id: 'filters', label: locale === 'es' ? 'Filtros' : 'Filters' },
    { id: 'strategies', label: locale === 'es' ? 'Estrategias' : 'Strategies' },
  ];

  return (
    <div className="flex flex-col h-full bg-surface border-l border-border ">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-surface-hover">
        <span className="text-xs font-bold text-foreground">
          {locale === 'es' ? 'Config de Alertas' : 'Alert Config'}
        </span>
        <button onClick={onClose} className="p-0.5 hover:bg-muted rounded transition-colors">
          <X className="w-3.5 h-3.5 text-muted-fg" />
        </button>
      </div>
      <div className="flex border-b border-border bg-surface">
        {tabs.map(tab => {
          const isActive = activeTab === tab.id;

          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={'flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-medium transition-colors border-b-2 '
                + (isActive
                  ? 'text-primary border-primary bg-primary/10'
                  : 'text-muted-fg border-transparent hover:text-foreground hover:bg-[var(--color-table-row-hover)]')}>
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-hidden min-h-0">
        {activeTab === 'alerts' && (
          <SelectAlertsTab
            selectedEventTypes={selectedEventTypes}
            onEventTypesChange={onEventTypesChange}
            currentFilters={currentFilters}
            onFiltersChange={onFiltersChange}
            locale={locale} />
        )}
        {activeTab === 'filters' && (
          <FiltersTab
            currentFilters={currentFilters}
            onFiltersChange={onFiltersChange}
            locale={locale} />
        )}
        {activeTab === 'strategies' && (
          <StrategiesTab
            selectedEventTypes={selectedEventTypes}
            currentFilters={currentFilters}
            onApplyPreset={handleApplyPreset}
            locale={locale} />
        )}
      </div>
      <div className="px-3 py-2 border-t border-border bg-surface-hover flex items-center justify-between">
        <span className="text-[10px] text-muted-fg">
          {selectedEventTypes.length > 0
            ? selectedEventTypes.length + ' active alerts'
            : 'All alerts'}
        </span>
        <button
          onClick={() => { onEventTypesChange([]); onFiltersChange({}); }}
          className="px-2 py-0.5 text-[10px] font-medium text-muted-fg border border-border rounded hover:bg-surface-hover transition-colors">
          Reset
        </button>
      </div>
    </div>
  );
}
