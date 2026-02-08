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
  return <Minus className="w-3 h-3 text-slate-400" />;
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
  const inputCls = "flex-1 min-w-0 px-1.5 py-[3px] text-[11px] border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white font-mono text-right tabular-nums";
  return (
    <div className="flex items-center gap-1.5 px-3 py-[3px]">
      <span className="text-[11px] text-slate-600 w-16 flex-shrink-0 font-medium truncate">{label}</span>
      <FmtNum value={toDisp(minValue)} onChange={v => onMinChange(toRaw(v))} placeholder={phMin || 'min'} className={inputCls} />
      <span className="text-slate-300 text-[9px]">-</span>
      <FmtNum value={toDisp(maxValue)} onChange={v => onMaxChange(toRaw(v))} placeholder={phMax || 'max'} className={inputCls} />
      {unitOpts ? (
        <select value={unit} onChange={e => setUnit(e.target.value)}
          className="w-9 py-[2px] text-[10px] text-slate-500 border border-slate-200 rounded bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer appearance-none text-center">
          {unitOpts.map(u => <option key={u} value={u}>{u || 'sh'}</option>)}
        </select>
      ) : suffix ? (
        <span className="text-[10px] text-slate-400 w-4 text-center">{suffix}</span>
      ) : <span className="w-4" />}
    </div>
  );
}

function SelectAlertsTab({ selectedEventTypes, onEventTypesChange, locale }: {
  selectedEventTypes: string[]; onEventTypesChange: (t: string[]) => void; locale: 'en' | 'es';
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
      <div className="px-3 py-2 border-b border-slate-200">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input type="text"
            placeholder={locale === 'es' ? 'Buscar alertas...' : 'Search alerts...'}
            value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <span className="text-[10px] text-slate-500">{selectedEventTypes.length}/{total} selected</span>
          <div className="flex gap-1.5">
            <button onClick={() => onEventTypesChange(ALERT_CATALOG.filter(a => a.active).map(a => a.eventType))}
              className="text-[10px] text-blue-600 hover:text-blue-800 font-medium">All</button>
            <span className="text-slate-300">|</span>
            <button onClick={() => onEventTypesChange([])}
              className="text-[10px] text-blue-600 hover:text-blue-800 font-medium">None</button>
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
            <div key={category.id} className="border-b border-slate-100 last:border-0">
              <button onClick={() => toggleCat(category.id)}
                className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 transition-colors">
                {isExp
                  ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                  : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
                <span className="text-xs font-semibold text-slate-700 flex-1 text-left">
                  {locale === 'es' ? category.nameEs : category.name}
                </span>
                <span
                  onClick={e => { e.stopPropagation(); toggleCatAll(alerts); }}
                  className={'px-1.5 py-0.5 rounded text-[10px] font-medium cursor-pointer '
                    + (allSel ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-500')}>
                  {allSel ? '\u2713' : selCount + '/' + catTypes.length}
                </span>
              </button>
              {isExp && (
                <div className="pb-1">
                  {alerts.map(alert => {
                    const sel = selectedSet.has(alert.eventType);
                    return (
                      <button key={alert.code} onClick={() => toggleAlert(alert.eventType)}
                        className={'w-full flex items-center gap-2 px-3 py-1 ml-3 mr-2 rounded-md transition-colors text-left '
                          + (sel ? 'bg-blue-50 hover:bg-blue-100' : 'hover:bg-slate-50')}>
                        <div className={'w-3.5 h-3.5 rounded border flex-shrink-0 flex items-center justify-center '
                          + (sel ? 'bg-blue-600 border-blue-600' : 'border-slate-300 bg-white')}>
                          {sel && <Check className="w-2.5 h-2.5 text-white" />}
                        </div>
                        <DirectionIcon direction={alert.direction} />
                        <span className={'text-[10px] font-mono font-bold w-10 flex-shrink-0 '
                          + (sel ? 'text-blue-700' : 'text-slate-500')}>{alert.code}</span>
                        <span className={'text-xs flex-1 truncate '
                          + (sel ? 'text-slate-800 font-medium' : 'text-slate-600')}>
                          {locale === 'es' ? alert.nameEs : alert.name}
                        </span>
                        {alert.phase > 1 && (
                          <span className="text-[9px] font-medium px-1 py-0.5 rounded bg-amber-50 text-amber-600">
                            P{alert.phase}
                          </span>
                        )}
                      </button>
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
      <div className="px-3 py-2 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700">
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
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Price</div>
          <FilterInput label="Price" minValue={currentFilters.min_price} maxValue={currentFilters.max_price}
            onMinChange={v => update('min_price', v)} onMaxChange={v => update('max_price', v)} suffix="$" phMin="0.50" phMax="500" />
          <FilterInput label="VWAP" minValue={currentFilters.min_vwap} maxValue={currentFilters.max_vwap}
            onMinChange={v => update('min_vwap', v)} onMaxChange={v => update('max_vwap', v)} suffix="$" phMin="5" phMax="200" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Change</div>
          <FilterInput label="Change %" minValue={currentFilters.min_change_percent} maxValue={currentFilters.max_change_percent}
            onMinChange={v => update('min_change_percent', v)} onMaxChange={v => update('max_change_percent', v)} suffix="%" phMin="-10" phMax="50" />
          <FilterInput label="From Open" minValue={currentFilters.min_change_from_open} maxValue={currentFilters.max_change_from_open}
            onMinChange={v => update('min_change_from_open', v)} onMaxChange={v => update('max_change_from_open', v)} suffix="%" phMin="-5" phMax="20" />
          <FilterInput label="Gap %" minValue={currentFilters.min_gap_percent} maxValue={currentFilters.max_gap_percent}
            onMinChange={v => update('min_gap_percent', v)} onMaxChange={v => update('max_gap_percent', v)} suffix="%" phMin="-10" phMax="30" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Volume</div>
          <FilterInput label="RVOL" minValue={currentFilters.min_rvol} maxValue={currentFilters.max_rvol}
            onMinChange={v => update('min_rvol', v)} onMaxChange={v => update('max_rvol', v)} suffix="x" phMin="1" phMax="10" />
          <FilterInput label="Volume" minValue={currentFilters.min_volume} maxValue={currentFilters.max_volume}
            onMinChange={v => update('min_volume', v)} onMaxChange={v => update('max_volume', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="10" phMax="500" />
          <FilterInput label="Vol 1m" minValue={currentFilters.min_vol_1min} maxValue={currentFilters.max_vol_1min}
            onMinChange={v => update('min_vol_1min', v)} onMaxChange={v => update('max_vol_1min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="1" phMax="50" />
          <FilterInput label="Vol 5m" minValue={currentFilters.min_vol_5min} maxValue={currentFilters.max_vol_5min}
            onMinChange={v => update('min_vol_5min', v)} onMaxChange={v => update('max_vol_5min', v)}
            unitOpts={['', 'K', 'M']} defaultUnit="K" phMin="1" phMax="100" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Fundamentals</div>
          <FilterInput label="Mkt Cap" minValue={currentFilters.min_market_cap} maxValue={currentFilters.max_market_cap}
            onMinChange={v => update('min_market_cap', v)} onMaxChange={v => update('max_market_cap', v)}
            unitOpts={['K', 'M', 'B']} defaultUnit="M" phMin="50" phMax="10" />
          <FilterInput label="Float" minValue={currentFilters.min_float_shares} maxValue={currentFilters.max_float_shares}
            onMinChange={v => update('min_float_shares', v)} onMaxChange={v => update('max_float_shares', v)}
            unitOpts={['K', 'M', 'B']} defaultUnit="M" phMin="1" phMax="100" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Technical</div>
          <FilterInput label="ATR %" minValue={currentFilters.min_atr_percent} maxValue={currentFilters.max_atr_percent}
            onMinChange={v => update('min_atr_percent', v)} onMaxChange={v => update('max_atr_percent', v)} suffix="%" phMin="2" phMax="10" />
          <FilterInput label="RSI" minValue={currentFilters.min_rsi} maxValue={currentFilters.max_rsi}
            onMinChange={v => update('min_rsi', v)} onMaxChange={v => update('max_rsi', v)} phMin="20" phMax="80" />
          <FilterInput label="SMA 20" minValue={currentFilters.min_sma_20} maxValue={currentFilters.max_sma_20}
            onMinChange={v => update('min_sma_20', v)} onMaxChange={v => update('max_sma_20', v)} suffix="$" phMin="5" phMax="500" />
          <FilterInput label="SMA 50" minValue={currentFilters.min_sma_50} maxValue={currentFilters.max_sma_50}
            onMinChange={v => update('min_sma_50', v)} onMaxChange={v => update('max_sma_50', v)} suffix="$" phMin="5" phMax="500" />
          <FilterInput label="SMA 200" minValue={currentFilters.min_sma_200} maxValue={currentFilters.max_sma_200}
            onMinChange={v => update('min_sma_200', v)} onMaxChange={v => update('max_sma_200', v)} suffix="$" phMin="5" phMax="500" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Time Windows</div>
          <FilterInput label="Chg 1m" minValue={currentFilters.min_chg_1min} maxValue={currentFilters.max_chg_1min}
            onMinChange={v => update('min_chg_1min', v)} onMaxChange={v => update('max_chg_1min', v)} suffix="%" phMin="-2" phMax="5" />
          <FilterInput label="Chg 5m" minValue={currentFilters.min_chg_5min} maxValue={currentFilters.max_chg_5min}
            onMinChange={v => update('min_chg_5min', v)} onMaxChange={v => update('max_chg_5min', v)} suffix="%" phMin="-5" phMax="10" />
          <FilterInput label="Chg 10m" minValue={currentFilters.min_chg_10min} maxValue={currentFilters.max_chg_10min}
            onMinChange={v => update('min_chg_10min', v)} onMaxChange={v => update('max_chg_10min', v)} suffix="%" phMin="-5" phMax="15" />
          <FilterInput label="Chg 15m" minValue={currentFilters.min_chg_15min} maxValue={currentFilters.max_chg_15min}
            onMinChange={v => update('min_chg_15min', v)} onMaxChange={v => update('max_chg_15min', v)} suffix="%" phMin="-8" phMax="20" />
          <FilterInput label="Chg 30m" minValue={currentFilters.min_chg_30min} maxValue={currentFilters.max_chg_30min}
            onMinChange={v => update('min_chg_30min', v)} onMaxChange={v => update('max_chg_30min', v)} suffix="%" phMin="-10" phMax="25" />
        </div>
        <div>
          <div className="px-3 py-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Symbols</div>
          <div className="px-3 py-1.5">
            <span className="text-xs text-slate-600 font-medium block mb-1">Include</span>
            <input type="text" value={(currentFilters.symbols_include || []).join(', ')}
              onChange={e => {
                const v = e.target.value.trim();
                update('symbols_include',
                  v ? v.split(',').map(s => s.trim().toUpperCase()).filter(Boolean) : undefined);
              }}
              placeholder="AAPL, TSLA..."
              className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white font-mono" />
          </div>
          <div className="px-3 py-1.5">
            <span className="text-xs text-slate-600 font-medium block mb-1">Exclude</span>
            <input type="text" value={(currentFilters.symbols_exclude || []).join(', ')}
              onChange={e => {
                const v = e.target.value.trim();
                update('symbols_exclude',
                  v ? v.split(',').map(s => s.trim().toUpperCase()).filter(Boolean) : undefined);
              }}
              placeholder="SPY, QQQ..."
              className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white font-mono" />
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
    <div className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-slate-50 transition-colors group">
      <button onClick={onLoad} className="flex-1 text-left min-w-0">
        <div className="text-xs font-medium text-slate-700 truncate">{name}</div>
        {description && <div className="text-[10px] text-slate-400 truncate">{description}</div>}
        <div className="text-[10px] text-slate-400">
          {alertCount} alerts{useCount ? ` \u00b7 ${useCount}x used` : ''}
        </div>
      </button>
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        {onToggleFav && (
          <button onClick={onToggleFav}
            className={`p-0.5 rounded text-[10px] ${isFavorite ? 'text-blue-600' : 'text-slate-300 hover:text-slate-500'}`}
            title="Favorite"
          >\u2605</button>
        )}
        {onDelete && (
          <button onClick={onDelete}
            className="p-0.5 text-slate-300 hover:text-rose-500 rounded transition-colors">
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
          filters: p.filters,
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
      <div className="px-3 py-2 border-b border-slate-200">
        {showSave ? (
          <div className="space-y-1.5">
            <div className="flex gap-1.5">
              <input type="text" value={saveName} onChange={e => setSaveName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
                placeholder={locale === 'es' ? 'Nombre...' : 'Name...'} autoFocus
                className="flex-1 px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
              <button onClick={handleSave} disabled={!saveName.trim()}
                className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40 transition-colors font-medium">
                Save
              </button>
              <button onClick={() => { setShowSave(false); setSaveName(''); }}
                className="px-1.5 py-1 text-xs text-slate-400 hover:text-slate-600 transition-colors">
                x
              </button>
            </div>
            <select value={saveCategory} onChange={e => setSaveCategory(e.target.value)}
              className="w-full px-2 py-1 text-[11px] border border-slate-200 rounded bg-white text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500">
              <option value="custom">Custom</option>
              <option value="bullish">Bullish</option>
              <option value="bearish">Bearish</option>
              <option value="neutral">Neutral</option>
            </select>
          </div>
        ) : (
          <button onClick={() => setShowSave(true)} disabled={selectedEventTypes.length === 0}
            className="w-full px-3 py-1.5 text-xs font-medium text-blue-600 border border-blue-300 rounded hover:bg-blue-50 disabled:opacity-40 transition-colors">
            {locale === 'es' ? 'Guardar Estrategia' : 'Save Strategy'}
          </button>
        )}
      </div>

      {/* Folders */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {loading && (
          <div className="px-3 py-3 text-[10px] text-slate-400 text-center">
            {locale === 'es' ? 'Cargando...' : 'Loading...'}
          </div>
        )}

        {/* Start from Scratch */}
        <button onClick={() => { onApplyPreset([], {}); }}
          className="w-full text-left px-3 py-1.5 text-xs font-semibold text-blue-600 hover:bg-blue-50/50 border-b border-slate-100 transition-colors">
          {locale === 'es' ? 'Empezar de Cero' : 'Start from Scratch'}
        </button>

        {/* User strategy folders */}
        {STRATEGY_FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
          const data = folderData[folder.id];
          if (!data) return null;
          const exp = expandedFolders.has(folder.id);
          const count = data.items.length;
          return (
            <div key={folder.id} className="border-b border-slate-100">
              <button onClick={() => toggleFolder(folder.id)}
                className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left hover:bg-slate-50 transition-colors">
                <span className="text-[10px] text-slate-400">{exp ? '\u25BC' : '\u25B6'}</span>
                <span className="text-xs font-semibold text-slate-600 flex-1">
                  {locale === 'es' ? folder.labelEs : folder.label}
                </span>
                {count > 0 && <span className="text-[10px] text-slate-400">{count}</span>}
              </button>
              {exp && (
                <div className="pb-1">
                  {data.items.length === 0 ? (
                    <div className="px-5 py-1 text-[10px] text-slate-300">{data.empty}</div>
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
        <div className="border-b border-slate-100">
          <button onClick={() => toggleFolder('builtin')}
            className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left hover:bg-slate-50 transition-colors">
            <span className="text-[10px] text-slate-400">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
            <span className="text-xs font-semibold text-slate-600 flex-1">
              {locale === 'es' ? 'Del Sistema' : 'Built-in'}
            </span>
            <span className="text-[10px] text-slate-400">{BUILT_IN_PRESETS.length}</span>
          </button>
          {expandedFolders.has('builtin') && (
            <div className="pb-1">
              {BUILT_IN_PRESETS.map(preset => (
                <div key={preset.id} className="px-3 py-1.5 hover:bg-slate-50 transition-colors">
                  <button onClick={() => handleLoadBuiltIn(preset)} className="w-full text-left">
                    <div className="text-xs font-medium text-slate-700">
                      {locale === 'es' ? preset.nameEs : preset.name}
                    </div>
                    <div className="text-[10px] text-slate-400 truncate">
                      {locale === 'es' ? preset.descriptionEs : preset.description}
                    </div>
                    <div className="text-[10px] text-slate-400">{preset.eventTypes.length} alerts</div>
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
    <div className="flex flex-col h-full bg-white border-l border-slate-200 ">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-slate-50">
        <span className="text-xs font-bold text-slate-800">
          {locale === 'es' ? 'Config de Alertas' : 'Alert Config'}
        </span>
        <button onClick={onClose} className="p-0.5 hover:bg-slate-200 rounded transition-colors">
          <X className="w-3.5 h-3.5 text-slate-500" />
        </button>
      </div>
      <div className="flex border-b border-slate-200 bg-white">
        {tabs.map(tab => {
          const isActive = activeTab === tab.id;
          
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={'flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-medium transition-colors border-b-2 '
                + (isActive
                  ? 'text-blue-600 border-blue-600 bg-blue-50/50'
                  : 'text-slate-500 border-transparent hover:text-slate-700 hover:bg-slate-50')}>
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
      <div className="px-3 py-2 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
        <span className="text-[10px] text-slate-500">
          {selectedEventTypes.length > 0
            ? selectedEventTypes.length + ' active alerts'
            : 'All alerts'}
        </span>
        <button
          onClick={() => { onEventTypesChange([]); onFiltersChange({}); }}
          className="px-2 py-0.5 text-[10px] font-medium text-slate-500 border border-slate-200 rounded hover:bg-slate-100 transition-colors">
          Reset
        </button>
      </div>
    </div>
  );
}
