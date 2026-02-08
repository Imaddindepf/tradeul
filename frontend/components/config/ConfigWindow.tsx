'use client';

/**
 * ConfigWindow - Strategy Builder (estilo Trade Ideas Alert Config Window)
 *
 * Tabs: Strategies | Alerts | Filters | Symbols | Summary
 *
 * Strategies tab: carpetas (Recent, Favorites, Bullish, Bearish, Neutral, Custom, Built-in)
 *   - panel izquierdo: arbol de carpetas con estrategias
 *   - panel derecho: detalle de la estrategia seleccionada (alerts + filters)
 *   - Start from Scratch, Load Settings
 *
 * Crea/guarda estrategias en BD via useAlertStrategies + abre Alert Window
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { useAlertStrategies, type AlertStrategy, type CreateStrategyData } from '@/hooks/useAlertStrategies';
import { BUILT_IN_PRESETS, type AlertPreset, ALERT_CATEGORIES, ALERT_CATALOG, getAlertsByCategory, searchAlerts } from '@/lib/alert-catalog';
import type { ActiveEventFilters } from '@/stores/useEventFiltersStore';

// ============================================================================
// Types
// ============================================================================

type ConfigTab = 'strategies' | 'alerts' | 'filters' | 'symbols' | 'summary';

export interface AlertWindowConfig {
  name: string;
  eventTypes: string[];
  filters: ActiveEventFilters;
  symbolsInclude: string[];
  symbolsExclude: string[];
}

interface ConfigWindowProps {
  onCreateAlertWindow?: (config: AlertWindowConfig) => void;
  /** Pre-load existing config (for reconfiguring an existing window) */
  initialAlerts?: string[];
  initialFilters?: Record<string, any>;
  initialSymbolsInclude?: string;
  initialSymbolsExclude?: string;
  initialName?: string;
  /** Start on a specific tab */
  initialTab?: ConfigTab;
}

// ============================================================================
// Strategy folder definitions
// ============================================================================

const FOLDERS = [
  { id: 'recent', label: 'Recent', labelEs: 'Recientes' },
  { id: 'favorites', label: 'Favorites', labelEs: 'Favoritos' },
  { id: 'bullish', label: 'Bullish Strategies', labelEs: 'Estrategias Alcistas' },
  { id: 'bearish', label: 'Bearish Strategies', labelEs: 'Estrategias Bajistas' },
  { id: 'neutral', label: 'Neutral Strategies', labelEs: 'Estrategias Neutrales' },
  { id: 'custom', label: 'My Strategies', labelEs: 'Mis Estrategias' },
  { id: 'builtin', label: 'Built-in', labelEs: 'Del Sistema' },
] as const;

// ============================================================================
// Helpers
// ============================================================================

function fmtFilter(key: string, val: number): string {
  const fmtLarge = (v: number, prefix = '') => {
    const a = Math.abs(v);
    if (a >= 1e9) return `${prefix}${parseFloat((v / 1e9).toPrecision(3))}B`;
    if (a >= 1e6) return `${prefix}${parseFloat((v / 1e6).toPrecision(3))}M`;
    if (a >= 1e3) return `${prefix}${parseFloat((v / 1e3).toPrecision(3))}K`;
    return `${prefix}${v}`;
  };
  if (key.includes('market_cap') || key.includes('dollar_volume')) return fmtLarge(val, '$');
  if (key.includes('float') || key.includes('shares_outstanding') || key.includes('bid_size') || key.includes('ask_size')) return fmtLarge(val);
  if (key.includes('price') && !key.includes('percent') || key.includes('vwap') || key.includes('sma_') || key.includes('_atr') && !key.includes('percent')) return `$${val}`;
  if (key.includes('rvol')) return `${val}x`;
  if (key.includes('rsi')) return String(val);
  if (key.includes('percent') || key.includes('gap') || key.includes('atr') || key.includes('from_open') || key.includes('chg_') || key.includes('spread') || key.includes('nbbo') || key.includes('volatility') || key.includes('short_interest') || key.includes('today_pct') || key.includes('from_high')) return `${val}%`;
  if (key.includes('volume') || key.includes('vol_')) return fmtLarge(val);
  return String(val);
}

function filtersToDisplay(filters: Record<string, any>): string[] {
  const labels: Record<string, string> = {
    min_price: 'Price >', max_price: 'Price <',
    min_vwap: 'VWAP >', max_vwap: 'VWAP <',
    min_spread: 'Spread >', max_spread: 'Spread <',
    min_bid_size: 'Bid >', max_bid_size: 'Bid <',
    min_ask_size: 'Ask >', max_ask_size: 'Ask <',
    min_distance_from_nbbo: 'NBBO >', max_distance_from_nbbo: 'NBBO <',
    min_change_percent: 'Chg% >', max_change_percent: 'Chg% <',
    min_change_from_open: 'Open >', max_change_from_open: 'Open <',
    min_gap_percent: 'Gap% >', max_gap_percent: 'Gap% <',
    min_premarket_change_percent: 'PreMkt >', max_premarket_change_percent: 'PreMkt <',
    min_postmarket_change_percent: 'PostMkt >', max_postmarket_change_percent: 'PostMkt <',
    min_price_from_high: 'FrHigh >', max_price_from_high: 'FrHigh <',
    min_rvol: 'RVOL >', max_rvol: 'RVOL <',
    min_volume: 'Vol >', max_volume: 'Vol <',
    min_avg_volume_5d: 'AvgV5D >', max_avg_volume_5d: 'AvgV5D <',
    min_avg_volume_10d: 'AvgV10D >', max_avg_volume_10d: 'AvgV10D <',
    min_avg_volume_3m: 'AvgV3M >', max_avg_volume_3m: 'AvgV3M <',
    min_dollar_volume: '$Vol >', max_dollar_volume: '$Vol <',
    min_volume_today_pct: 'VPct >', max_volume_today_pct: 'VPct <',
    min_vol_1min: 'V1m >', max_vol_1min: 'V1m <',
    min_vol_5min: 'V5m >', max_vol_5min: 'V5m <',
    min_chg_1min: '1m >', max_chg_1min: '1m <',
    min_chg_5min: '5m >', max_chg_5min: '5m <',
    min_chg_10min: '10m >', max_chg_10min: '10m <',
    min_chg_15min: '15m >', max_chg_15min: '15m <',
    min_chg_30min: '30m >', max_chg_30min: '30m <',
    min_atr: 'ATR >', max_atr: 'ATR <',
    min_atr_percent: 'ATR% >', max_atr_percent: 'ATR% <',
    min_volatility: 'Vola >', max_volatility: 'Vola <',
    min_rsi: 'RSI >', max_rsi: 'RSI <',
    min_sma_20: 'SMA20 >', max_sma_20: 'SMA20 <',
    min_sma_50: 'SMA50 >', max_sma_50: 'SMA50 <',
    min_sma_200: 'SMA200 >', max_sma_200: 'SMA200 <',
    min_market_cap: 'MCap >', max_market_cap: 'MCap <',
    min_float_shares: 'Float >', max_float_shares: 'Float <',
    min_shares_outstanding: 'ShOut >', max_shares_outstanding: 'ShOut <',
    min_short_interest: 'SI% >', max_short_interest: 'SI% <',
  };
  return Object.entries(filters)
    .filter(([, v]) => v != null && typeof v === 'number')
    .map(([k, v]) => `${labels[k] || k} ${fmtFilter(k, v)}`);
}

function alertTypeLabel(eventType: string): string {
  const a = ALERT_CATALOG.find(x => x.eventType === eventType);
  return a ? a.name : eventType;
}

// ============================================================================
// Unit system & formatted numeric input
// ============================================================================

const UNIT_MUL: Record<string, number> = { '': 1, K: 1e3, M: 1e6, B: 1e9 };

const fmtLocale = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 6 });

/** Numeric input with thousand-separator formatting on blur, raw editing on focus */
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

// ============================================================================
// Component
// ============================================================================

export function ConfigWindow({
  onCreateAlertWindow,
  initialAlerts, initialFilters, initialSymbolsInclude, initialSymbolsExclude,
  initialName, initialTab,
}: ConfigWindowProps) {
  const [activeTab, setActiveTab] = useState<ConfigTab>(initialTab || 'strategies');

  // Strategy state
  const {
    strategies, loading, createStrategy, updateStrategy, deleteStrategy,
    useStrategy, toggleFavorite, getRecent, getFavorites, getByCategory,
  } = useAlertStrategies();

  // Current config being built
  const [strategyName, setStrategyName] = useState(initialName || '');
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set(initialAlerts || []));
  const [filters, setFilters] = useState<Record<string, number | undefined>>(
    initialFilters ? Object.fromEntries(Object.entries(initialFilters).filter(([, v]) => typeof v === 'number')) : {}
  );
  const [filterUnits, setFilterUnits] = useState<Record<string, string>>({});
  const [symbolsInclude, setSymbolsInclude] = useState(initialSymbolsInclude || '');
  const [symbolsExclude, setSymbolsExclude] = useState(initialSymbolsExclude || '');
  const [saving, setSaving] = useState(false);
  const [saveCategory, setSaveCategory] = useState('custom');
  const [loadedStrategyId, setLoadedStrategyId] = useState<string | null>(null);
  // Snapshot of loaded strategy to detect modifications
  const [loadedSnapshot, setLoadedSnapshot] = useState<{ alerts: string[]; filters: Record<string, any>; name: string } | null>(null);

  // Unit helpers: raw value <-> display value
  const getUnit = useCallback((id: string, def?: string) => filterUnits[id] || def || '', [filterUnits]);
  const getMul = useCallback((id: string, def?: string) => UNIT_MUL[filterUnits[id] || def || ''] || 1, [filterUnits]);
  const setUnitFor = useCallback((id: string, u: string) => setFilterUnits(p => ({ ...p, [id]: u })), []);
  const rawToDisplay = useCallback((raw: number | undefined, id: string, def?: string): string => {
    if (raw === undefined) return '';
    return parseFloat((raw / (UNIT_MUL[filterUnits[id] || def || ''] || 1)).toPrecision(10)).toString();
  }, [filterUnits]);
  const displayToRaw = useCallback((val: string, id: string, def?: string): number | undefined => {
    if (!val) return undefined;
    return Number(val) * (UNIT_MUL[filterUnits[id] || def || ''] || 1);
  }, [filterUnits]);

  // Strategies tab state
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['builtin', 'custom']));
  const [selectedStrategy, setSelectedStrategy] = useState<AlertStrategy | AlertPreset | null>(null);
  const [alertSearch, setAlertSearch] = useState('');

  const toggleFolder = (id: string) => setExpandedFolders(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });

  // Load strategy into editor
  const loadStrategy = useCallback((eventTypes: string[], stratFilters: Record<string, any>, name?: string) => {
    setSelectedAlerts(new Set(eventTypes));
    const numFilters: Record<string, number | undefined> = {};
    for (const [k, v] of Object.entries(stratFilters)) {
      if (typeof v === 'number') numFilters[k] = v;
    }
    setFilters(numFilters);
    if (name) setStrategyName(name);
    setActiveTab('summary');
  }, []);

  const handleLoadUserStrategy = useCallback(async (s: AlertStrategy) => {
    loadStrategy(s.eventTypes, s.filters, s.name);
    setLoadedStrategyId(String(s.id));
    setLoadedSnapshot({ alerts: [...s.eventTypes], filters: { ...s.filters }, name: s.name });
    await useStrategy(s.id);
  }, [loadStrategy, useStrategy]);

  const handleLoadBuiltIn = useCallback((p: AlertPreset) => {
    loadStrategy(p.eventTypes, p.filters, p.name);
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
  }, [loadStrategy]);

  const handleStartFromScratch = useCallback(() => {
    setSelectedAlerts(new Set());
    setFilters({});
    setSymbolsInclude('');
    setSymbolsExclude('');
    setStrategyName('');
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
    setActiveTab('alerts');
  }, []);

  // Alert handlers
  const toggleAlert = useCallback((id: string) => {
    setSelectedAlerts(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }, []);

  const toggleAlertCat = useCallback((catAlerts: string[]) => {
    setSelectedAlerts(prev => {
      const n = new Set(prev);
      const all = catAlerts.every(a => n.has(a));
      catAlerts.forEach(a => { if (all) n.delete(a); else n.add(a); });
      return n;
    });
  }, []);

  // Filter handlers
  const setFilter = useCallback((key: string, val: number | undefined) => {
    setFilters(prev => {
      const n = { ...prev };
      if (val === undefined || val === null) delete n[key]; else n[key] = val;
      return n;
    });
  }, []);

  // Validation
  const canCreate = useMemo(() => {
    return strategyName.trim().length > 0 && selectedAlerts.size > 0;
  }, [strategyName, selectedAlerts]);

  // Detect if config was modified from loaded snapshot
  const isDirty = useMemo(() => {
    if (!loadedSnapshot) return false;
    const curAlerts = Array.from(selectedAlerts).sort();
    const snapAlerts = [...loadedSnapshot.alerts].sort();
    if (curAlerts.length !== snapAlerts.length || curAlerts.some((a, i) => a !== snapAlerts[i])) return true;
    if (strategyName !== loadedSnapshot.name) return true;
    const curFilterKeys = Object.keys(filters).filter(k => filters[k] !== undefined).sort();
    const snapFilterKeys = Object.keys(loadedSnapshot.filters).filter(k => loadedSnapshot.filters[k] != null && typeof loadedSnapshot.filters[k] === 'number').sort();
    if (curFilterKeys.length !== snapFilterKeys.length || curFilterKeys.some((k, i) => k !== snapFilterKeys[i])) return true;
    if (curFilterKeys.some(k => filters[k] !== loadedSnapshot.filters[k])) return true;
    return false;
  }, [selectedAlerts, filters, strategyName, loadedSnapshot]);

  // Create / Open
  const handleCreate = useCallback(async () => {
    if (!canCreate || saving) return;
    setSaving(true);
    try {
      // Save strategy to BD
      await createStrategy({
        name: strategyName.trim(),
        category: saveCategory,
        event_types: Array.from(selectedAlerts),
        filters,
      });

      // Build ActiveEventFilters for the window
      const inc = symbolsInclude.trim() ? symbolsInclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
      const exc = symbolsExclude.trim() ? symbolsExclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
      const ef: ActiveEventFilters = {
        event_types: Array.from(selectedAlerts),
        symbols_include: inc.length ? inc : undefined,
        symbols_exclude: exc.length ? exc : undefined,
        ...filters,
      };

      if (onCreateAlertWindow) {
        onCreateAlertWindow({
          name: strategyName.trim(),
          eventTypes: Array.from(selectedAlerts),
          filters: ef,
          symbolsInclude: inc,
          symbolsExclude: exc,
        });
      }
    } finally { setSaving(false); }
  }, [canCreate, saving, strategyName, saveCategory, selectedAlerts, filters, symbolsInclude, symbolsExclude, createStrategy, onCreateAlertWindow]);

  // Update existing strategy & open
  const handleUpdate = useCallback(async () => {
    if (!loadedStrategyId || saving) return;
    setSaving(true);
    try {
      await updateStrategy(Number(loadedStrategyId), {
        name: strategyName.trim(),
        event_types: Array.from(selectedAlerts),
        filters,
      });
      // Update snapshot to reflect saved state
      setLoadedSnapshot({ alerts: Array.from(selectedAlerts), filters: { ...filters }, name: strategyName.trim() });

      const inc = symbolsInclude.trim() ? symbolsInclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
      const exc = symbolsExclude.trim() ? symbolsExclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
      const ef: ActiveEventFilters = {
        event_types: Array.from(selectedAlerts),
        symbols_include: inc.length ? inc : undefined,
        symbols_exclude: exc.length ? exc : undefined,
        ...filters,
      };
      if (onCreateAlertWindow) {
        onCreateAlertWindow({
          name: strategyName.trim(),
          eventTypes: Array.from(selectedAlerts),
          filters: ef,
          symbolsInclude: inc,
          symbolsExclude: exc,
        });
      }
    } finally { setSaving(false); }
  }, [loadedStrategyId, saving, strategyName, selectedAlerts, filters, symbolsInclude, symbolsExclude, updateStrategy, onCreateAlertWindow]);

  // Open without saving (just launch the window)
  const handleOpenDirect = useCallback(() => {
    if (selectedAlerts.size === 0) return;
    const inc = symbolsInclude.trim() ? symbolsInclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
    const exc = symbolsExclude.trim() ? symbolsExclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
    const ef: ActiveEventFilters = {
      event_types: Array.from(selectedAlerts),
      symbols_include: inc.length ? inc : undefined,
      symbols_exclude: exc.length ? exc : undefined,
      ...filters,
    };
    if (onCreateAlertWindow) {
      onCreateAlertWindow({
        name: strategyName.trim() || `Custom ${new Date().toLocaleTimeString()}`,
        eventTypes: Array.from(selectedAlerts),
        filters: ef,
        symbolsInclude: inc,
        symbolsExclude: exc,
      });
    }
  }, [selectedAlerts, filters, symbolsInclude, symbolsExclude, strategyName, onCreateAlertWindow]);

  // Folder data
  const folderData: Record<string, AlertStrategy[]> = {
    recent: getRecent(8),
    favorites: getFavorites(),
    bullish: getByCategory('bullish'),
    bearish: getByCategory('bearish'),
    neutral: getByCategory('neutral'),
    custom: getByCategory('custom'),
  };

  // Alert categories expand state (collapsed by default)
  const [expandedAlertCats, setExpandedAlertCats] = useState<Set<string>>(new Set());
  const toggleAlertCatExpand = (id: string) => setExpandedAlertCats(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });

  // Filter groups expand state + search
  const [expandedFilterGroups, setExpandedFilterGroups] = useState<Set<string>>(new Set());
  const toggleFilterGroup = (id: string) => setExpandedFilterGroups(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });
  const [filterSearch, setFilterSearch] = useState('');

  // Search alerts
  const alertGroups = useMemo(() => {
    if (!alertSearch.trim()) return getAlertsByCategory();
    const results = searchAlerts(alertSearch, 'en');
    const resultSet = new Set(results.map(a => a.eventType));
    return getAlertsByCategory()
      .map(g => ({ ...g, alerts: g.alerts.filter(a => resultSet.has(a.eventType)) }))
      .filter(g => g.alerts.length > 0);
  }, [alertSearch]);

  const tabs: { id: ConfigTab; label: string }[] = [
    { id: 'strategies', label: 'Strategies' },
    { id: 'alerts', label: `Alerts (${selectedAlerts.size})` },
    { id: 'filters', label: 'Filters' },
    { id: 'symbols', label: 'Symbols' },
    { id: 'summary', label: 'Summary' },
  ];

  const activeFilterCount = Object.values(filters).filter(v => v !== undefined).length;

  return (
    <div className="h-full flex flex-col bg-white text-slate-700 text-xs">
      {/* Tabs */}
      <div className="flex-shrink-0 flex border-b border-slate-200 bg-slate-50">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-xs border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >{tab.label}</button>
        ))}
      </div>

      <div className="flex-1 overflow-hidden">

        {/* ====== STRATEGIES TAB ====== */}
        {activeTab === 'strategies' && (
          <div className="h-full flex">
            {/* Left: folder tree */}
            <div className="w-52 border-r border-slate-200 flex flex-col overflow-hidden">
              {/* Start from scratch */}
              <button onClick={handleStartFromScratch}
                className="w-full text-left px-3 py-1.5 text-xs font-semibold text-blue-600 hover:bg-blue-50/50 border-b border-slate-100 transition-colors flex-shrink-0">
                Start from Scratch
              </button>

              <div className="flex-1 overflow-y-auto">
                {FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
                  const items = folderData[folder.id] || [];
                  const exp = expandedFolders.has(folder.id);
                  return (
                    <div key={folder.id} className="border-b border-slate-100">
                      <button onClick={() => toggleFolder(folder.id)}
                        className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-slate-50 transition-colors">
                        <span className="text-[10px] text-slate-400">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-xs font-semibold text-slate-600 flex-1">{folder.label}</span>
                        {items.length > 0 && <span className="text-[10px] text-slate-400">{items.length}</span>}
                      </button>
                      {exp && items.length === 0 && (
                        <div className="px-5 py-1 text-[10px] text-slate-300">Empty</div>
                      )}
                      {exp && items.map(s => (
                        <button key={s.id}
                          onClick={() => setSelectedStrategy(s)}
                          onDoubleClick={() => handleLoadUserStrategy(s)}
                          className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${
                            selectedStrategy && 'id' in selectedStrategy && selectedStrategy.id === s.id
                              ? 'bg-blue-50 text-blue-700 font-medium'
                              : 'text-slate-600 hover:bg-slate-50'
                          }`}
                        >{s.name}</button>
                      ))}
                    </div>
                  );
                })}

                {/* Built-in folder */}
                <div className="border-b border-slate-100">
                  <button onClick={() => toggleFolder('builtin')}
                    className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-slate-50 transition-colors">
                    <span className="text-[10px] text-slate-400">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-xs font-semibold text-slate-600 flex-1">Built-in</span>
                    <span className="text-[10px] text-slate-400">{BUILT_IN_PRESETS.length}</span>
                  </button>
                  {expandedFolders.has('builtin') && BUILT_IN_PRESETS.map(p => (
                    <button key={p.id}
                      onClick={() => setSelectedStrategy(p)}
                      onDoubleClick={() => handleLoadBuiltIn(p)}
                      className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${
                        selectedStrategy && 'isBuiltIn' in selectedStrategy && selectedStrategy.id === p.id
                          ? 'bg-blue-50 text-blue-700 font-medium'
                          : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >{p.name}</button>
                  ))}
                </div>
              </div>

              {loading && <div className="px-3 py-1 text-[10px] text-slate-400 text-center flex-shrink-0">Loading...</div>}
            </div>

            {/* Right: strategy detail */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedStrategy ? (
                <>
                  <div className="flex-1 overflow-y-auto p-3">
                    {'isBuiltIn' in selectedStrategy ? (
                      // Built-in preset detail
                      <>
                        <div className="text-xs font-bold text-slate-800 mb-1">{selectedStrategy.name}</div>
                        <p className="text-[11px] text-slate-500 mb-3">{selectedStrategy.description}</p>
                        <div className="mb-2">
                          <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Alerts</div>
                          <div className="flex flex-wrap gap-1">
                            {selectedStrategy.eventTypes.map(et => (
                              <span key={et} className="px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded text-[10px] text-slate-600">
                                {alertTypeLabel(et)}
                              </span>
                            ))}
                          </div>
                        </div>
                        {Object.keys(selectedStrategy.filters).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Filters</div>
                            <div className="flex flex-wrap gap-1">
                              {filtersToDisplay(selectedStrategy.filters).map(f => (
                                <span key={f} className="px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded text-[10px] font-mono text-slate-600">{f}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      // User strategy detail
                      <>
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-xs font-bold text-slate-800">{(selectedStrategy as AlertStrategy).name}</div>
                          <div className="flex items-center gap-1">
                            <button onClick={() => toggleFavorite((selectedStrategy as AlertStrategy).id)}
                              className={`text-[11px] ${(selectedStrategy as AlertStrategy).isFavorite ? 'text-blue-600' : 'text-slate-300 hover:text-slate-500'}`}
                            >{'\u2605'}</button>
                            <button onClick={async () => { await deleteStrategy((selectedStrategy as AlertStrategy).id); setSelectedStrategy(null); }}
                              className="text-[10px] text-slate-300 hover:text-rose-500">x</button>
                          </div>
                        </div>
                        {(selectedStrategy as AlertStrategy).description && (
                          <p className="text-[11px] text-slate-500 mb-2">{(selectedStrategy as AlertStrategy).description}</p>
                        )}
                        <div className="text-[10px] text-slate-400 mb-3">
                          {(selectedStrategy as AlertStrategy).useCount > 0 && `Used ${(selectedStrategy as AlertStrategy).useCount}x`}
                          {(selectedStrategy as AlertStrategy).lastUsedAt && ` \u00b7 Last: ${new Date((selectedStrategy as AlertStrategy).lastUsedAt!).toLocaleDateString()}`}
                        </div>
                        <div className="mb-2">
                          <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
                            Alerts ({(selectedStrategy as AlertStrategy).eventTypes.length})
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {(selectedStrategy as AlertStrategy).eventTypes.map(et => (
                              <span key={et} className="px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded text-[10px] text-slate-600">
                                {alertTypeLabel(et)}
                              </span>
                            ))}
                          </div>
                        </div>
                        {Object.keys((selectedStrategy as AlertStrategy).filters).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Filters</div>
                            <div className="flex flex-wrap gap-1">
                              {filtersToDisplay((selectedStrategy as AlertStrategy).filters).map(f => (
                                <span key={f} className="px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded text-[10px] font-mono text-slate-600">{f}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="flex-shrink-0 p-2 border-t border-slate-200 bg-slate-50">
                    <button
                      onClick={() => {
                        if ('isBuiltIn' in selectedStrategy) handleLoadBuiltIn(selectedStrategy as AlertPreset);
                        else handleLoadUserStrategy(selectedStrategy as AlertStrategy);
                      }}
                      className="w-full py-1.5 text-xs font-semibold bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                    >Load Settings</button>
                  </div>
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-slate-400 text-[11px] p-4 text-center">
                  Select a strategy to see details, or double-click to load
                </div>
              )}
            </div>
          </div>
        )}

        {/* ====== ALERTS TAB ====== */}
        {activeTab === 'alerts' && (
          <div className="h-full flex flex-col">
            <div className="flex-shrink-0 px-2 pt-1.5 pb-1 border-b border-slate-200 flex items-center gap-2">
              <input type="text" value={alertSearch} onChange={(e) => setAlertSearch(e.target.value)}
                placeholder="Search..."
                className="flex-1 px-1.5 py-0.5 text-[11px] border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
              <span className="text-[10px] text-slate-400 tabular-nums">{selectedAlerts.size}</span>
              <button onClick={() => setSelectedAlerts(new Set(ALERT_CATALOG.filter(a => a.active).map(a => a.eventType)))}
                className="text-[10px] text-blue-600 hover:text-blue-800">all</button>
              <button onClick={() => setSelectedAlerts(new Set())}
                className="text-[10px] text-slate-400 hover:text-slate-600">clear</button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {alertGroups.map(({ category, alerts }) => {
                const catTypes = alerts.map(a => a.eventType);
                const selCount = catTypes.filter(t => selectedAlerts.has(t)).length;
                const allSel = selCount === catTypes.length && catTypes.length > 0;
                const exp = expandedAlertCats.has(category.id);
                return (
                  <div key={category.id}>
                    <button onClick={() => toggleAlertCatExpand(category.id)}
                      className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100/80">
                      <span className="text-[9px] text-slate-300 w-3">{exp ? '\u25BC' : '\u25B6'}</span>
                      <span className="text-[11px] font-medium text-slate-600 flex-1">{category.name}</span>
                      {selCount > 0 && <span className="text-[9px] text-blue-600 font-semibold tabular-nums">{selCount}/{catTypes.length}</span>}
                      <button onClick={(e) => { e.stopPropagation(); toggleAlertCat(catTypes); }}
                        className="text-[9px] text-slate-400 hover:text-blue-600 px-1">
                        {allSel ? 'none' : 'all'}
                      </button>
                    </button>
                    {exp && (
                      <div className="px-2 py-1 flex flex-wrap gap-[3px]">
                        {alerts.map(a => (
                          <button key={a.eventType} onClick={() => toggleAlert(a.eventType)}
                            className={`px-1.5 py-[1px] text-[10px] rounded border transition-colors ${
                              selectedAlerts.has(a.eventType)
                                ? 'bg-blue-50/80 border-blue-200 text-blue-600 font-medium'
                                : 'border-slate-200/80 text-slate-500 hover:bg-slate-50'
                            }`}
                          >{a.name}</button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ====== FILTERS TAB ====== */}
        {activeTab === 'filters' && (() => {
          const FG = [
            { id: 'price', group: 'Price', filters: [
              { label: 'Price', minK: 'min_price', maxK: 'max_price', suf: '$', phMin: '0.50', phMax: '500' },
              { label: 'VWAP', minK: 'min_vwap', maxK: 'max_vwap', suf: '$', phMin: '5', phMax: '200' },
              { label: 'Spread', minK: 'min_spread', maxK: 'max_spread', suf: '%', phMin: '0.01', phMax: '1' },
              { label: 'Bid Size', minK: 'min_bid_size', maxK: 'max_bid_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
              { label: 'Ask Size', minK: 'min_ask_size', maxK: 'max_ask_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
              { label: 'NBBO Dist', minK: 'min_distance_from_nbbo', maxK: 'max_distance_from_nbbo', suf: '%', phMin: '0', phMax: '1' },
            ]},
            { id: 'change', group: 'Change', filters: [
              { label: 'Change %', minK: 'min_change_percent', maxK: 'max_change_percent', suf: '%', phMin: '-10', phMax: '50' },
              { label: 'From Open', minK: 'min_change_from_open', maxK: 'max_change_from_open', suf: '%', phMin: '-5', phMax: '20' },
              { label: 'Gap %', minK: 'min_gap_percent', maxK: 'max_gap_percent', suf: '%', phMin: '-10', phMax: '30' },
              { label: 'Pre-Mkt %', minK: 'min_premarket_change_percent', maxK: 'max_premarket_change_percent', suf: '%', phMin: '-5', phMax: '20' },
              { label: 'Post-Mkt %', minK: 'min_postmarket_change_percent', maxK: 'max_postmarket_change_percent', suf: '%', phMin: '-5', phMax: '10' },
              { label: 'From High', minK: 'min_price_from_high', maxK: 'max_price_from_high', suf: '%', phMin: '-20', phMax: '0' },
            ]},
            { id: 'volume', group: 'Volume', filters: [
              { label: 'RVOL', minK: 'min_rvol', maxK: 'max_rvol', suf: 'x', phMin: '1', phMax: '10' },
              { label: 'Volume', minK: 'min_volume', maxK: 'max_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
              { label: 'Avg Vol 5D', minK: 'min_avg_volume_5d', maxK: 'max_avg_volume_5d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
              { label: 'Avg Vol 10D', minK: 'min_avg_volume_10d', maxK: 'max_avg_volume_10d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
              { label: 'Avg Vol 3M', minK: 'min_avg_volume_3m', maxK: 'max_avg_volume_3m', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
              { label: 'Dollar Vol', minK: 'min_dollar_volume', maxK: 'max_dollar_volume', suf: '$', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '100' },
              { label: 'Vol Today %', minK: 'min_volume_today_pct', maxK: 'max_volume_today_pct', suf: '%', phMin: '50', phMax: '500' },
              { label: 'Vol 1m', minK: 'min_vol_1min', maxK: 'max_vol_1min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '50' },
              { label: 'Vol 5m', minK: 'min_vol_5min', maxK: 'max_vol_5min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '100' },
            ]},
            { id: 'windows', group: 'Time Windows', filters: [
              { label: 'Chg 1m', minK: 'min_chg_1min', maxK: 'max_chg_1min', suf: '%', phMin: '-2', phMax: '5' },
              { label: 'Chg 5m', minK: 'min_chg_5min', maxK: 'max_chg_5min', suf: '%', phMin: '-5', phMax: '10' },
              { label: 'Chg 10m', minK: 'min_chg_10min', maxK: 'max_chg_10min', suf: '%', phMin: '-5', phMax: '15' },
              { label: 'Chg 15m', minK: 'min_chg_15min', maxK: 'max_chg_15min', suf: '%', phMin: '-8', phMax: '20' },
              { label: 'Chg 30m', minK: 'min_chg_30min', maxK: 'max_chg_30min', suf: '%', phMin: '-10', phMax: '25' },
            ]},
            { id: 'tech', group: 'Technical', filters: [
              { label: 'ATR', minK: 'min_atr', maxK: 'max_atr', suf: '$', phMin: '0.5', phMax: '10' },
              { label: 'ATR %', minK: 'min_atr_percent', maxK: 'max_atr_percent', suf: '%', phMin: '2', phMax: '10' },
              { label: 'Volatility', minK: 'min_volatility', maxK: 'max_volatility', suf: '%', phMin: '1', phMax: '20' },
              { label: 'RSI', minK: 'min_rsi', maxK: 'max_rsi', suf: '', phMin: '20', phMax: '80' },
              { label: 'SMA 20', minK: 'min_sma_20', maxK: 'max_sma_20', suf: '$', phMin: '5', phMax: '500' },
              { label: 'SMA 50', minK: 'min_sma_50', maxK: 'max_sma_50', suf: '$', phMin: '5', phMax: '500' },
              { label: 'SMA 200', minK: 'min_sma_200', maxK: 'max_sma_200', suf: '$', phMin: '5', phMax: '500' },
            ]},
            { id: 'fund', group: 'Fundamentals', filters: [
              { label: 'Mkt Cap', minK: 'min_market_cap', maxK: 'max_market_cap', suf: '$', units: ['K', 'M', 'B'], defU: 'M', phMin: '50', phMax: '10' },
              { label: 'Float', minK: 'min_float_shares', maxK: 'max_float_shares', suf: '', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '100' },
              { label: 'Shares Out', minK: 'min_shares_outstanding', maxK: 'max_shares_outstanding', suf: '', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '500' },
              { label: 'Short Int', minK: 'min_short_interest', maxK: 'max_short_interest', suf: '%', phMin: '5', phMax: '50' },
            ]},
          ] as const;

          type FDef = (typeof FG)[number]['filters'][number];
          const hasUnits = (f: FDef): f is FDef & { units: readonly string[]; defU: string } => 'units' in f;
          const q = filterSearch.trim().toLowerCase();
          const visibleGroups = q
            ? FG.map(g => ({ ...g, filters: g.filters.filter(f => f.label.toLowerCase().includes(q)) })).filter(g => g.filters.length > 0)
            : FG;

          return (
            <div className="h-full flex flex-col">
              <div className="flex-shrink-0 px-2 pt-1.5 pb-1 border-b border-slate-200 flex items-center gap-2">
                <input type="text" value={filterSearch} onChange={(e) => setFilterSearch(e.target.value)}
                  placeholder="Search filters..."
                  className="flex-1 px-1.5 py-0.5 text-[11px] border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
                <span className="text-[10px] text-slate-400 tabular-nums">{activeFilterCount}</span>
                {activeFilterCount > 0 && (
                  <button onClick={() => { setFilters({}); setFilterUnits({}); }} className="text-[10px] text-slate-400 hover:text-blue-600">clear</button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto">
                {visibleGroups.map(g => {
                  const exp = expandedFilterGroups.has(g.id) || !!q;
                  const activeInGroup = g.filters.filter(f => filters[f.minK] !== undefined || filters[f.maxK] !== undefined).length;
                  return (
                    <div key={g.id}>
                      <button onClick={() => toggleFilterGroup(g.id)}
                        className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-slate-50/80 transition-colors border-b border-slate-100/80">
                        <span className="text-[9px] text-slate-300 w-3">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-[11px] font-medium text-slate-600 flex-1">{g.group}</span>
                        {activeInGroup > 0 && <span className="text-[9px] text-blue-600 font-semibold tabular-nums">{activeInGroup}</span>}
                      </button>
                      {exp && (
                        <div className="px-2 py-1 space-y-[3px]">
                          {g.filters.map((f) => {
                            const wu = hasUnits(f);
                            const uid = f.label;
                            const curUnit = wu ? getUnit(uid, f.defU) : '';
                            const m = wu ? (UNIT_MUL[curUnit] || 1) : 1;
                            const toDisp = (raw: number | undefined) => raw !== undefined ? raw / m : undefined;
                            const toRaw = (v: number | undefined) => v !== undefined ? v * m : undefined;
                            return (
                              <div key={f.label} className="flex items-center gap-1">
                                <span className="text-[10px] text-slate-500 w-[50px] flex-shrink-0 truncate">{f.label}</span>
                                <FmtNum
                                  value={toDisp(filters[f.minK])}
                                  onChange={v => setFilter(f.minK, toRaw(v))}
                                  placeholder={f.phMin}
                                  className="w-[68px] px-1.5 py-[2px] text-[10px] font-mono border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white text-right tabular-nums" />
                                <span className="text-slate-300 text-[8px]">-</span>
                                <FmtNum
                                  value={toDisp(filters[f.maxK])}
                                  onChange={v => setFilter(f.maxK, toRaw(v))}
                                  placeholder={f.phMax}
                                  className="w-[68px] px-1.5 py-[2px] text-[10px] font-mono border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white text-right tabular-nums" />
                                {wu ? (
                                  <select value={curUnit} onChange={e => setUnitFor(uid, e.target.value)}
                                    className="w-8 py-[1px] text-[9px] text-slate-500 border border-slate-200 rounded bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer appearance-none text-center">
                                    {f.units.map(u => <option key={u} value={u}>{u || 'sh'}</option>)}
                                  </select>
                                ) : (
                                  f.suf ? <span className="text-[9px] text-slate-300 w-3 text-center">{f.suf}</span> : <span className="w-3" />
                                )}
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
        })()}

        {/* ====== SYMBOLS TAB ====== */}
        {activeTab === 'symbols' && (
          <div className="h-full p-3 space-y-3">
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Include only</label>
              <textarea value={symbolsInclude} onChange={(e) => setSymbolsInclude(e.target.value)}
                placeholder="AAPL, TSLA, NVDA..."
                className="w-full h-16 px-2 py-1 text-xs font-mono border border-slate-300 rounded resize-none focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
              <p className="text-[10px] text-slate-400">Empty = all symbols</p>
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Exclude</label>
              <textarea value={symbolsExclude} onChange={(e) => setSymbolsExclude(e.target.value)}
                placeholder="SPY, QQQ, IWM..."
                className="w-full h-16 px-2 py-1 text-xs font-mono border border-slate-300 rounded resize-none focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
            </div>
          </div>
        )}

        {/* ====== SUMMARY TAB ====== */}
        {activeTab === 'summary' && (
          <div className="h-full flex flex-col">
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {/* Name + Category */}
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Strategy Name</label>
                <input type="text" value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="My Strategy..."
                  className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Category</label>
                <select value={saveCategory} onChange={e => setSaveCategory(e.target.value)}
                  className="w-full px-2 py-1 text-xs border border-slate-200 rounded bg-white text-slate-600 focus:outline-none focus:ring-1 focus:ring-blue-500">
                  <option value="custom">Custom</option>
                  <option value="bullish">Bullish</option>
                  <option value="bearish">Bearish</option>
                  <option value="neutral">Neutral</option>
                </select>
              </div>

              {/* Alerts summary */}
              <div className="py-1 border-t border-slate-100">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
                  Alerts ({selectedAlerts.size})
                </div>
                {selectedAlerts.size === 0
                  ? <span className="text-[10px] text-slate-300">none selected</span>
                  : <div className="flex flex-wrap gap-1">
                      {Array.from(selectedAlerts).map(et => (
                        <span key={et} className="px-1.5 py-0.5 bg-blue-50 border border-blue-200 rounded text-[10px] text-blue-600">
                          {alertTypeLabel(et)}
                        </span>
                      ))}
                    </div>
                }
              </div>

              {/* Filters summary */}
              <div className="py-1 border-t border-slate-100">
                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">
                  Filters ({activeFilterCount})
                </div>
                {activeFilterCount === 0
                  ? <span className="text-[10px] text-slate-300">none</span>
                  : <div className="flex flex-wrap gap-1">
                      {filtersToDisplay(filters).map(f => (
                        <span key={f} className="px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded text-[10px] font-mono text-slate-600">{f}</span>
                      ))}
                    </div>
                }
              </div>

              {/* Symbols summary */}
              {(symbolsInclude.trim() || symbolsExclude.trim()) && (
                <div className="py-1 border-t border-slate-100">
                  <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Symbols</div>
                  {symbolsInclude.trim() && <div className="text-[10px] text-slate-600 font-mono">+ {symbolsInclude.trim()}</div>}
                  {symbolsExclude.trim() && <div className="text-[10px] text-slate-600 font-mono">- {symbolsExclude.trim()}</div>}
                </div>
              )}
            </div>

            {/* Action buttons - context-aware */}
            <div className="flex-shrink-0 p-2 border-t border-slate-200 bg-slate-50 space-y-1.5">
              {loadedStrategyId && !isDirty ? (
                /* Saved strategy, no changes → just Open */
                <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                  className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${
                    selectedAlerts.size > 0
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  }`}>
                  Open
                </button>
              ) : loadedStrategyId && isDirty ? (
                /* Saved strategy, modified → Update or Save as new */
                <>
                  <button onClick={handleUpdate} disabled={saving || selectedAlerts.size === 0}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${
                      !saving && selectedAlerts.size > 0
                        ? 'bg-blue-600 text-white hover:bg-blue-700'
                        : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                    }`}>
                    {saving ? 'Saving...' : 'Update & Open'}
                  </button>
                  <div className="flex gap-1.5">
                    <button onClick={handleCreate} disabled={!canCreate || saving}
                      className="flex-1 py-1 text-xs text-slate-500 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-40 transition-colors">
                      Save as new
                    </button>
                    <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                      className="flex-1 py-1 text-xs text-slate-500 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-40 transition-colors">
                      Open only
                    </button>
                  </div>
                </>
              ) : (
                /* New / built-in strategy → Save & Open */
                <>
                  <button onClick={handleCreate} disabled={!canCreate || saving}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${
                      canCreate && !saving
                        ? 'bg-blue-600 text-white hover:bg-blue-700'
                        : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                    }`}>
                    {saving ? 'Saving...' : 'Save & Open'}
                  </button>
                  <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                    className="w-full py-1 text-xs text-slate-500 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-40 transition-colors">
                    Open without saving
                  </button>
                </>
              )}
              {selectedAlerts.size === 0 && (
                <p className="text-[10px] text-slate-400 text-center">Select alerts first</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
