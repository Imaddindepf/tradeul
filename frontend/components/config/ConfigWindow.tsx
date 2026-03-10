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
import { useUserFilters } from '@/hooks/useUserFilters';
import { BUILT_IN_PRESETS, type AlertPreset, BUILT_IN_TOP_LISTS, type TopListPreset, ALERT_CATEGORIES, ALERT_CATALOG, getAlertsByCategory, searchAlerts } from '@/lib/alert-catalog';
import type { ActiveEventFilters } from '@/stores/useEventFiltersStore';
import type { UserFilter } from '@/lib/types/scannerFilters';
import { SECURITY_TYPES, SECTORS, INDUSTRIES } from '@/lib/constants/filters';

// ============================================================================
// Types
// ============================================================================

type BuilderMode = 'strategy' | 'toplist';
type ConfigTab = 'saved' | 'alerts' | 'filters' | 'symbols' | 'summary';

export interface AlertWindowConfig {
  name: string;
  eventTypes: string[];
  filters: ActiveEventFilters;
  symbolsInclude: string[];
  symbolsExclude: string[];
}

export interface BacktestFromConfigData {
  eventTypes: string[];
  filters: Record<string, any>;
  name: string;
}

interface ConfigWindowProps {
  onCreateAlertWindow?: (config: AlertWindowConfig) => void;
  onBacktestStrategy?: (data: BacktestFromConfigData) => void;
  onCreateScannerWindow?: (filter: UserFilter) => void;
  /** Pre-load existing config (for reconfiguring an existing window) */
  initialAlerts?: string[];
  initialFilters?: Record<string, any>;
  initialSymbolsInclude?: string;
  initialSymbolsExclude?: string;
  initialName?: string;
  /** Start on a specific tab */
  initialTab?: ConfigTab;
  /** Start in a specific mode */
  initialMode?: BuilderMode;
}

// ============================================================================
// Strategy folder definitions
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

const TOPLIST_FOLDERS = [
  { id: 'all', label: 'All Top Lists', labelEs: 'Todas las Listas' },
  { id: 'active', label: 'Active', labelEs: 'Activas' },
  { id: 'inactive', label: 'Inactive', labelEs: 'Inactivas' },
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
  if (key.includes('price') && !key.includes('percent') || key.includes('vwap') || key.includes('ema_') || key.includes('sma_') || key.includes('_atr') && !key.includes('percent')) return `$${val}`;
  if (key.includes('rvol')) return `${val}x`;
  if (key.includes('rsi')) return String(val);
  if (key.includes('percent') || key.includes('gap') || key.includes('atr') || key.includes('from_open') || key.includes('chg_') || key.includes('spread') || key.includes('nbbo') || key.includes('volatility') || key.includes('short_interest') || key.includes('today_pct') || key.includes('from_high')) return `${val}%`;
  if (key.includes('volume') || key.includes('vol_')) return fmtLarge(val);
  if (key.includes('range') && !key.includes('_pct')) return `$${val}`;
  if (key.includes('range') && key.includes('_pct')) return `${val}%`;
  return String(val);
}

function filtersToDisplay(filters: Record<string, any>): string[] {
  const labels: Record<string, string> = {
    // String filters
    security_type: 'Type',
    sector: 'Sector',
    industry: 'Industry',
    // Numeric filters
    min_price: 'Price >', max_price: 'Price <',
    min_vwap: 'VWAP >', max_vwap: 'VWAP <',
    min_spread: 'Spread >', max_spread: 'Spread <',
    min_bid_size: 'Bid >', max_bid_size: 'Bid <',
    min_ask_size: 'Ask >', max_ask_size: 'Ask <',
    min_distance_from_nbbo: 'NBBO >', max_distance_from_nbbo: 'NBBO <',
    min_change_percent: 'Change % >', max_change_percent: 'Change % <',
    min_change_from_open: 'From Open >', max_change_from_open: 'From Open <',
    min_gap_percent: 'Gap % >', max_gap_percent: 'Gap % <',
    min_premarket_change_percent: 'Pre-Market >', max_premarket_change_percent: 'Pre-Market <',
    min_postmarket_change_percent: 'Post-Market >', max_postmarket_change_percent: 'Post-Market <',
    min_price_from_high: 'From High >', max_price_from_high: 'From High <',
    min_price_from_low: 'From Low >', max_price_from_low: 'From Low <',
    min_price_from_intraday_high: 'From Intra Hi >', max_price_from_intraday_high: 'From Intra Hi <',
    min_price_from_intraday_low: 'From Intra Lo >', max_price_from_intraday_low: 'From Intra Lo <',
    min_change_from_open_dollars: 'Open $ >', max_change_from_open_dollars: 'Open $ <',
    min_rvol: 'RVOL >', max_rvol: 'RVOL <',
    min_volume: 'Vol >', max_volume: 'Vol <',
    min_avg_volume_5d: 'Avg Vol 5D >', max_avg_volume_5d: 'Avg Vol 5D <',
    min_avg_volume_10d: 'Avg Vol 10D >', max_avg_volume_10d: 'Avg Vol 10D <',
    min_avg_volume_3m: 'Avg Vol 3M >', max_avg_volume_3m: 'Avg Vol 3M <',
    min_dollar_volume: 'Dollar Vol >', max_dollar_volume: 'Dollar Vol <',
    min_volume_today_pct: 'Vol Today % >', max_volume_today_pct: 'Vol Today % <',
    min_vol_1min: 'Vol 1m >', max_vol_1min: 'Vol 1m <',
    min_vol_5min: 'Vol 5m >', max_vol_5min: 'Vol 5m <',
    min_vol_1min_pct: 'Vol 1m % >', max_vol_1min_pct: 'Vol 1m % <',
    min_vol_5min_pct: 'Vol 5m % >', max_vol_5min_pct: 'Vol 5m % <',
    min_vol_10min_pct: 'Vol 10m % >', max_vol_10min_pct: 'Vol 10m % <',
    min_vol_15min_pct: 'Vol 15m % >', max_vol_15min_pct: 'Vol 15m % <',
    min_vol_30min_pct: 'Vol 30m % >', max_vol_30min_pct: 'Vol 30m % <',
    min_range_2min: 'Range 2m $ >', max_range_2min: 'Range 2m $ <',
    min_range_5min: 'Range 5m $ >', max_range_5min: 'Range 5m $ <',
    min_range_15min: 'Range 15m $ >', max_range_15min: 'Range 15m $ <',
    min_range_30min: 'Range 30m $ >', max_range_30min: 'Range 30m $ <',
    min_range_60min: 'Range 60m $ >', max_range_60min: 'Range 60m $ <',
    min_range_120min: 'Range 120m $ >', max_range_120min: 'Range 120m $ <',
    min_range_2min_pct: 'Range 2m % >', max_range_2min_pct: 'Range 2m % <',
    min_range_5min_pct: 'Range 5m % >', max_range_5min_pct: 'Range 5m % <',
    min_range_15min_pct: 'Range 15m % >', max_range_15min_pct: 'Range 15m % <',
    min_range_30min_pct: 'Range 30m % >', max_range_30min_pct: 'Range 30m % <',
    min_range_60min_pct: 'Range 60m % >', max_range_60min_pct: 'Range 60m % <',
    min_range_120min_pct: 'Range 120m % >', max_range_120min_pct: 'Range 120m % <',
    min_chg_1min: 'Chg 1m >', max_chg_1min: 'Chg 1m <',
    min_chg_5min: 'Chg 5m >', max_chg_5min: 'Chg 5m <',
    min_chg_10min: 'Chg 10m >', max_chg_10min: 'Chg 10m <',
    min_chg_15min: 'Chg 15m >', max_chg_15min: 'Chg 15m <',
    min_chg_30min: 'Chg 30m >', max_chg_30min: 'Chg 30m <',
    min_atr: 'ATR >', max_atr: 'ATR <',
    min_atr_percent: 'ATR % >', max_atr_percent: 'ATR % <',
    min_volatility: 'Volatility >', max_volatility: 'Volatility <',
    min_rsi: 'RSI >', max_rsi: 'RSI <',
    min_ema_20: 'EMA20 >', max_ema_20: 'EMA20 <',
    min_ema_50: 'EMA50 >', max_ema_50: 'EMA50 <',
    min_market_cap: 'Market Cap >', max_market_cap: 'Market Cap <',
    min_float_shares: 'Float >', max_float_shares: 'Float <',
    min_shares_outstanding: 'Shares Out >', max_shares_outstanding: 'Shares Out <',
    min_sma_5: 'SMA5 >', max_sma_5: 'SMA5 <',
    min_sma_8: 'SMA8 >', max_sma_8: 'SMA8 <',
    min_sma_20: 'SMA20 >', max_sma_20: 'SMA20 <',
    min_sma_50: 'SMA50 >', max_sma_50: 'SMA50 <',
    min_sma_200: 'SMA200 >', max_sma_200: 'SMA200 <',
    min_macd_line: 'MACD >', max_macd_line: 'MACD <',
    min_macd_hist: 'MACD Hist >', max_macd_hist: 'MACD Hist <',
    min_stoch_k: 'Stoch %K >', max_stoch_k: 'Stoch %K <',
    min_stoch_d: 'Stoch %D >', max_stoch_d: 'Stoch %D <',
    min_adx_14: 'ADX >', max_adx_14: 'ADX <',
    min_bb_upper: 'BB Upper >', max_bb_upper: 'BB Upper <',
    min_bb_lower: 'BB Lower >', max_bb_lower: 'BB Lower <',
  };
  return Object.entries(filters)
    .filter(([, v]) => v != null && (typeof v === 'number' || typeof v === 'string'))
    .map(([k, v]) => {
      const label = labels[k] || k;
      // Handle string filters differently (no formatting needed)
      if (typeof v === 'string') {
        return `${label}: ${v}`;
      }
      return `${label} ${fmtFilter(k, v as number)}`;
    });
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
  onCreateScannerWindow,
  onBacktestStrategy,
  initialAlerts, initialFilters, initialSymbolsInclude, initialSymbolsExclude,
  initialName, initialTab, initialMode,
}: ConfigWindowProps) {
  const [builderMode, setBuilderMode] = useState<BuilderMode>(initialMode || 'strategy');
  const [activeTab, setActiveTab] = useState<ConfigTab>(initialTab || 'saved');

  // Strategy state
  const {
    strategies, loading, createStrategy, updateStrategy, deleteStrategy,
    useStrategy, toggleFavorite, getRecent, getFavorites, getByCategory,
  } = useAlertStrategies();

  // Top List state (scanner filters)
  const {
    filters: scannerFilters, loading: loadingScans,
    createFilter: createScanFilter, updateFilter: updateScanFilter,
    deleteFilter: deleteScanFilter, refreshFilters: refreshScanFilters,
  } = useUserFilters();

  // Current config being built
  const [strategyName, setStrategyName] = useState(initialName || '');
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set(initialAlerts || []));
  const [filters, setFilters] = useState<Record<string, number | string | undefined>>(
    initialFilters ? Object.fromEntries(Object.entries(initialFilters).filter(([, v]) => typeof v === 'number' || typeof v === 'string')) : {}
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

  // Loaded scan (top list) state
  const [loadedScanId, setLoadedScanId] = useState<number | null>(null);
  const [loadedScanSnapshot, setLoadedScanSnapshot] = useState<{ filters: Record<string, any>; name: string } | null>(null);

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
    const allFilters: Record<string, number | string | undefined> = {};
    for (const [k, v] of Object.entries(stratFilters)) {
      if (typeof v === 'number' || typeof v === 'string') allFilters[k] = v;
    }
    setFilters(allFilters);
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
    setLoadedScanId(null);
    setLoadedScanSnapshot(null);
    setActiveTab(builderMode === 'strategy' ? 'alerts' : 'filters');
  }, [builderMode]);

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
  const setFilter = useCallback((key: string, val: number | string | undefined) => {
    setFilters(prev => {
      const n = { ...prev };
      if (val === undefined || val === null) delete n[key]; else n[key] = val;
      return n;
    });
  }, []);

  // Validation - different rules per mode
  const canCreate = useMemo(() => {
    if (!strategyName.trim()) return false;
    if (builderMode === 'strategy') return selectedAlerts.size > 0;
    // Top List: requires at least 1 filter
    return Object.values(filters).some(v => v !== undefined);
  }, [strategyName, selectedAlerts, filters, builderMode]);

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
      const saved = await createStrategy({
        name: strategyName.trim(),
        category: saveCategory,
        event_types: Array.from(selectedAlerts),
        filters,
      });

      // CRITICAL: Don't open window if save failed (JWT expired, 409 conflict, etc.)
      if (!saved) {
        return;
      }

      // Transition to "loaded" state so subsequent edits use Update (not Create again → 409)
      setLoadedStrategyId(String(saved.id));
      setLoadedSnapshot({
        alerts: Array.from(selectedAlerts),
        filters: { ...filters },
        name: strategyName.trim(),
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

  // Detect if top list was modified from loaded snapshot
  const isScanDirty = useMemo(() => {
    if (!loadedScanSnapshot) return false;
    if (strategyName !== loadedScanSnapshot.name) return true;
    const curKeys = Object.keys(filters).filter(k => filters[k] !== undefined).sort();
    const snapKeys = Object.keys(loadedScanSnapshot.filters).filter(k => loadedScanSnapshot.filters[k] != null).sort();
    if (curKeys.length !== snapKeys.length || curKeys.some((k, i) => k !== snapKeys[i])) return true;
    if (curKeys.some(k => filters[k] !== loadedScanSnapshot.filters[k])) return true;
    return false;
  }, [filters, strategyName, loadedScanSnapshot]);

  // ── Top List handlers ──

  const handleLoadScan = useCallback((scan: UserFilter) => {
    const numFilters: Record<string, number | string | undefined> = {};
    for (const [k, v] of Object.entries(scan.parameters || {})) {
      if (typeof v === 'number') numFilters[k] = v;
      if (typeof v === 'string') numFilters[k] = v;
    }
    setFilters(numFilters);
    setSelectedAlerts(new Set()); // Top lists have no alerts
    setStrategyName(scan.name);
    setLoadedScanId(scan.id);
    setLoadedScanSnapshot({ filters: { ...numFilters }, name: scan.name });
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
    setActiveTab('summary');
  }, []);

  const handleLoadBuiltInTopList = useCallback((preset: TopListPreset) => {
    const numFilters: Record<string, number | string | undefined> = {};
    for (const [k, v] of Object.entries(preset.filters)) {
      numFilters[k] = v;
    }
    setFilters(numFilters);
    setSelectedAlerts(new Set());
    setStrategyName(preset.name);
    setLoadedScanId(null);
    setLoadedScanSnapshot(null);
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
    setActiveTab('summary');
  }, []);

  const handleCreateTopList = useCallback(async () => {
    if (!canCreate || saving) return;
    setSaving(true);
    try {
      // Build parameters from filters
      const params: Record<string, any> = {};
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined) params[k] = v;
      }
      const saved = await createScanFilter({
        name: strategyName.trim(),
        description: `${Object.keys(params).length} filters`,
        enabled: true,
        filter_type: 'custom',
        parameters: params,
        priority: 0,
      });
      if (!saved) return;
      setLoadedScanId(saved.id);
      setLoadedScanSnapshot({ filters: { ...filters }, name: strategyName.trim() });
      if (onCreateScannerWindow) {
        onCreateScannerWindow(saved);
      }
    } finally { setSaving(false); }
  }, [canCreate, saving, strategyName, filters, createScanFilter, onCreateScannerWindow]);

  // Open scanner for an already-saved scan (no save needed)
  const handleOpenScanDirect = useCallback(() => {
    if (!loadedScanId) return;
    // Build a minimal UserFilter-like object to pass to the callback
    const params: Record<string, any> = {};
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined) params[k] = v;
    }
    if (onCreateScannerWindow) {
      onCreateScannerWindow({
        id: loadedScanId,
        userId: '',
        name: strategyName.trim(),
        enabled: true,
        filter_type: 'custom',
        parameters: params,
        priority: 0,
        isShared: false,
        isPublic: false,
        createdAt: '',
        updatedAt: '',
      });
    }
  }, [loadedScanId, strategyName, filters, onCreateScannerWindow]);

  const handleUpdateTopList = useCallback(async () => {
    if (!loadedScanId || saving) return;
    setSaving(true);
    try {
      const params: Record<string, any> = {};
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined) params[k] = v;
      }
      const updated = await updateScanFilter(loadedScanId, {
        name: strategyName.trim(),
        parameters: params,
      });
      if (!updated) return;
      setLoadedScanSnapshot({ filters: { ...filters }, name: strategyName.trim() });
      if (onCreateScannerWindow) {
        onCreateScannerWindow(updated);
      }
    } finally { setSaving(false); }
  }, [loadedScanId, saving, strategyName, filters, updateScanFilter, onCreateScannerWindow]);

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

  // Top List folder data
  const topListFolderData: Record<string, UserFilter[]> = useMemo(() => ({
    all: scannerFilters,
    active: scannerFilters.filter(s => s.enabled),
    inactive: scannerFilters.filter(s => !s.enabled),
  }), [scannerFilters]);

  const tabs: { id: ConfigTab; label: string }[] = useMemo(() => {
    if (builderMode === 'toplist') {
      return [
        { id: 'saved', label: 'Top Lists' },
        { id: 'filters', label: 'Filters' },
        { id: 'symbols', label: 'Symbols' },
        { id: 'summary', label: 'Summary' },
      ];
    }
    return [
      { id: 'saved', label: 'Strategies' },
      { id: 'alerts', label: `Alerts (${selectedAlerts.size})` },
      { id: 'filters', label: 'Filters' },
      { id: 'symbols', label: 'Symbols' },
      { id: 'summary', label: 'Summary' },
    ];
  }, [builderMode, selectedAlerts.size]);

  const activeFilterCount = Object.values(filters).filter(v => v !== undefined).length;

  // When switching modes, clear selection and redirect incompatible tabs
  const handleModeSwitch = useCallback((mode: BuilderMode) => {
    setBuilderMode(mode);
    setSelectedStrategy(null);
    if (mode === 'toplist' && activeTab === 'alerts') {
      setActiveTab('filters');
    }
  }, [activeTab]);

  return (
    <div className="h-full flex flex-col bg-surface text-foreground text-xs">
      {/* Mode toggle + Tabs */}
      <div className="flex-shrink-0 border-b border-border bg-surface-hover">
        {/* Mode selector */}
        <div className="flex items-center gap-1 px-3 pt-1.5 pb-1">
          <div className="flex bg-muted rounded-md p-0.5 gap-0.5">
            <button
              onClick={() => handleModeSwitch('strategy')}
              className={`px-2.5 py-[3px] text-[10px] font-semibold rounded transition-all ${builderMode === 'strategy'
                  ? 'bg-surface text-primary shadow-sm'
                  : 'text-muted-fg hover:text-foreground'
                }`}
            >Strategy</button>
            <button
              onClick={() => handleModeSwitch('toplist')}
              className={`px-2.5 py-[3px] text-[10px] font-semibold rounded transition-all ${builderMode === 'toplist'
                  ? 'bg-surface text-emerald-600 shadow-sm'
                  : 'text-muted-fg hover:text-foreground'
                }`}
            >Top List</button>
          </div>
          <span className="text-[9px] text-muted-fg ml-1.5">
            {builderMode === 'strategy' ? 'Events + Filters' : 'Filters only → Scanner'}
          </span>
        </div>
        {/* Tabs */}
        <div className="flex">
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 text-xs border-b-2 transition-colors ${activeTab === tab.id
                ? (builderMode === 'toplist' ? 'border-emerald-600 text-emerald-600 bg-emerald-500/10' : 'border-primary text-primary bg-primary/10')
                : 'border-transparent text-muted-fg hover:text-foreground hover:bg-surface-hover'
                }`}
            >{tab.label}</button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden">

        {/* ====== SAVED TAB (Strategies or Top Lists) ====== */}
        {activeTab === 'saved' && builderMode === 'strategy' && (
          <div className="h-full flex">
            {/* Left: folder tree */}
            <div className="w-52 border-r border-border flex flex-col overflow-hidden">
              <button onClick={handleStartFromScratch}
                className="w-full text-left px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 border-b border-border-subtle transition-colors flex-shrink-0">
                Start from Scratch
              </button>
              <div className="flex-1 overflow-y-auto">
                {STRATEGY_FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
                  const items = folderData[folder.id] || [];
                  const exp = expandedFolders.has(folder.id);
                  return (
                    <div key={folder.id} className="border-b border-border-subtle">
                      <button onClick={() => toggleFolder(folder.id)}
                        className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                        <span className="text-[10px] text-muted-fg">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-xs font-semibold text-foreground/80 flex-1">{folder.label}</span>
                        {items.length > 0 && <span className="text-[10px] text-muted-fg">{items.length}</span>}
                      </button>
                      {exp && items.length === 0 && (
                        <div className="px-5 py-1 text-[10px] text-muted-fg/50">Empty</div>
                      )}
                      {exp && items.map(s => (
                        <button key={s.id}
                          onClick={() => setSelectedStrategy(s)}
                          onDoubleClick={() => handleLoadUserStrategy(s)}
                          className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'id' in selectedStrategy && selectedStrategy.id === s.id
                            ? 'bg-primary/10 text-primary font-medium'
                            : 'text-foreground/80 hover:bg-surface-hover'
                            }`}
                        >{s.name}</button>
                      ))}
                    </div>
                  );
                })}
                {/* Built-in strategies folder */}
                <div className="border-b border-border-subtle">
                  <button onClick={() => toggleFolder('builtin')}
                    className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                    <span className="text-[10px] text-muted-fg">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-xs font-semibold text-foreground/80 flex-1">Built-in</span>
                    <span className="text-[10px] text-muted-fg">{BUILT_IN_PRESETS.length}</span>
                  </button>
                  {expandedFolders.has('builtin') && BUILT_IN_PRESETS.map(p => (
                    <button key={p.id}
                      onClick={() => setSelectedStrategy(p)}
                      onDoubleClick={() => handleLoadBuiltIn(p)}
                      className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'isBuiltIn' in selectedStrategy && selectedStrategy.id === p.id
                        ? 'bg-blue-500/10 text-blue-700 font-medium'
                        : 'text-foreground/80 hover:bg-surface-hover'
                        }`}
                    >{p.name}</button>
                  ))}
                </div>
              </div>
              {loading && <div className="px-3 py-1 text-[10px] text-muted-fg text-center flex-shrink-0">Loading...</div>}
            </div>
            {/* Right: strategy detail */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedStrategy ? (
                <>
                  <div className="flex-1 overflow-y-auto p-3">
                    {'isBuiltIn' in selectedStrategy ? (
                      <>
                        <div className="text-xs font-bold text-foreground mb-1">{selectedStrategy.name}</div>
                        <p className="text-[11px] text-muted-fg mb-3">{selectedStrategy.description}</p>
                        <div className="mb-2">
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Alerts</div>
                          <div className="flex flex-wrap gap-1">
                            {selectedStrategy.eventTypes.map(et => (
                              <span key={et} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] text-foreground/80">{alertTypeLabel(et)}</span>
                            ))}
                          </div>
                        </div>
                        {Object.keys(selectedStrategy.filters).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                            <div className="flex flex-wrap gap-1">
                              {filtersToDisplay(selectedStrategy.filters).map(f => (
                                <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-xs font-bold text-foreground">{(selectedStrategy as AlertStrategy).name}</div>
                          <div className="flex items-center gap-1">
                            <button onClick={() => toggleFavorite((selectedStrategy as AlertStrategy).id)}
                              className={`text-[11px] ${(selectedStrategy as AlertStrategy).isFavorite ? 'text-primary' : 'text-muted-fg/50 hover:text-muted-fg'}`}
                            >{'\u2605'}</button>
                            <button onClick={async () => { await deleteStrategy((selectedStrategy as AlertStrategy).id); setSelectedStrategy(null); }}
                              className="text-[10px] text-muted-fg/50 hover:text-rose-500">x</button>
                          </div>
                        </div>
                        {(selectedStrategy as AlertStrategy).description && (
                          <p className="text-[11px] text-muted-fg mb-2">{(selectedStrategy as AlertStrategy).description}</p>
                        )}
                        <div className="text-[10px] text-muted-fg mb-3">
                          {(selectedStrategy as AlertStrategy).useCount > 0 && `Used ${(selectedStrategy as AlertStrategy).useCount}x`}
                          {(selectedStrategy as AlertStrategy).lastUsedAt && ` \u00b7 Last: ${new Date((selectedStrategy as AlertStrategy).lastUsedAt!).toLocaleDateString()}`}
                        </div>
                        <div className="mb-2">
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Alerts ({(selectedStrategy as AlertStrategy).eventTypes.length})</div>
                          <div className="flex flex-wrap gap-1">
                            {(selectedStrategy as AlertStrategy).eventTypes.map(et => (
                              <span key={et} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] text-foreground/80">{alertTypeLabel(et)}</span>
                            ))}
                          </div>
                        </div>
                        {Object.keys((selectedStrategy as AlertStrategy).filters).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                            <div className="flex flex-wrap gap-1">
                              {filtersToDisplay((selectedStrategy as AlertStrategy).filters).map(f => (
                                <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover">
                    <button
                      onClick={() => {
                        if ('isBuiltIn' in selectedStrategy) handleLoadBuiltIn(selectedStrategy as AlertPreset);
                        else handleLoadUserStrategy(selectedStrategy as AlertStrategy);
                      }}
                      className="w-full py-1.5 text-xs font-semibold bg-primary text-white rounded hover:bg-primary-hover transition-colors"
                    >Load Settings</button>
                  </div>
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-muted-fg text-[11px] p-4 text-center">
                  Select a strategy to see details, or double-click to load
                </div>
              )}
            </div>
          </div>
        )}

        {/* ====== SAVED TAB — TOP LIST MODE ====== */}
        {activeTab === 'saved' && builderMode === 'toplist' && (
          <div className="h-full flex">
            {/* Left: folder tree */}
            <div className="w-52 border-r border-border flex flex-col overflow-hidden">
              <button onClick={handleStartFromScratch}
                className="w-full text-left px-3 py-1.5 text-xs font-semibold text-emerald-600 hover:bg-emerald-500/10 border-b border-border-subtle transition-colors flex-shrink-0">
                Start from Scratch
              </button>
              <div className="flex-1 overflow-y-auto">
                {TOPLIST_FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
                  const items = topListFolderData[folder.id] || [];
                  const exp = expandedFolders.has(folder.id);
                  return (
                    <div key={folder.id} className="border-b border-border-subtle">
                      <button onClick={() => toggleFolder(folder.id)}
                        className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                        <span className="text-[10px] text-muted-fg">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-xs font-semibold text-foreground/80 flex-1">{folder.label}</span>
                        {items.length > 0 && <span className="text-[10px] text-muted-fg">{items.length}</span>}
                      </button>
                      {exp && items.length === 0 && (
                        <div className="px-5 py-1 text-[10px] text-muted-fg/50">Empty</div>
                      )}
                      {exp && items.map(scan => (
                        <button key={scan.id}
                          onClick={() => setSelectedStrategy(scan as any)}
                          onDoubleClick={() => handleLoadScan(scan)}
                          className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'userId' in selectedStrategy && (selectedStrategy as any).id === scan.id
                            ? 'bg-emerald-500/10 text-emerald-700 font-medium'
                            : 'text-foreground/80 hover:bg-surface-hover'
                            }`}
                        >
                          <span className="flex items-center gap-1">
                            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${scan.enabled ? 'bg-emerald-400' : 'bg-muted'}`} />
                            {scan.name}
                          </span>
                        </button>
                      ))}
                    </div>
                  );
                })}
                {/* Built-in top lists */}
                <div className="border-b border-border-subtle">
                  <button onClick={() => toggleFolder('builtin')}
                    className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                    <span className="text-[10px] text-muted-fg">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-xs font-semibold text-foreground/80 flex-1">Built-in</span>
                    <span className="text-[10px] text-muted-fg">{BUILT_IN_TOP_LISTS.length}</span>
                  </button>
                  {expandedFolders.has('builtin') && BUILT_IN_TOP_LISTS.map(p => (
                    <button key={p.id}
                      onClick={() => setSelectedStrategy(p as any)}
                      onDoubleClick={() => handleLoadBuiltInTopList(p)}
                      className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'isTopList' in selectedStrategy && (selectedStrategy as any).id === p.id
                        ? 'bg-emerald-500/10 text-emerald-700 font-medium'
                        : 'text-foreground/80 hover:bg-surface-hover'
                        }`}
                    >{p.name}</button>
                  ))}
                </div>
              </div>
              {loadingScans && <div className="px-3 py-1 text-[10px] text-muted-fg text-center flex-shrink-0">Loading...</div>}
            </div>
            {/* Right: top list detail */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedStrategy ? (
                <>
                  <div className="flex-1 overflow-y-auto p-3">
                    {'isTopList' in selectedStrategy ? (
                      // Built-in top list preset
                      <>
                        <div className="text-xs font-bold text-foreground mb-1">{(selectedStrategy as any).name}</div>
                        <p className="text-[11px] text-muted-fg mb-3">{(selectedStrategy as any).description}</p>
                        <div>
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                          <div className="flex flex-wrap gap-1">
                            {filtersToDisplay((selectedStrategy as any).filters).map(f => (
                              <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                            ))}
                          </div>
                        </div>
                      </>
                    ) : 'userId' in selectedStrategy ? (
                      // User scanner filter
                      <>
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-xs font-bold text-foreground">{(selectedStrategy as any).name}</div>
                          <button onClick={async () => { await deleteScanFilter((selectedStrategy as any).id); setSelectedStrategy(null); }}
                            className="text-[10px] text-muted-fg/50 hover:text-rose-500">x</button>
                        </div>
                        <div className="flex items-center gap-2 mb-3">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${(selectedStrategy as any).enabled ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-200' : 'bg-surface-hover text-muted-fg border border-border'}`}>
                            {(selectedStrategy as any).enabled ? 'Active' : 'Inactive'}
                          </span>
                          <span className="text-[10px] text-muted-fg">
                            {new Date((selectedStrategy as any).createdAt).toLocaleDateString()}
                          </span>
                        </div>
                        <div>
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                          <div className="flex flex-wrap gap-1">
                            {filtersToDisplay((selectedStrategy as any).parameters || {}).map(f => (
                              <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                            ))}
                          </div>
                        </div>
                      </>
                    ) : (
                      // Fallback: could be a strategy loaded while in toplist mode
                      <div className="text-[11px] text-muted-fg">Select a top list</div>
                    )}
                  </div>
                  <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover">
                    <button
                      onClick={() => {
                        if ('isTopList' in selectedStrategy) handleLoadBuiltInTopList(selectedStrategy as TopListPreset);
                        else if ('userId' in selectedStrategy) handleLoadScan(selectedStrategy as unknown as UserFilter);
                      }}
                      className="w-full py-1.5 text-xs font-semibold bg-emerald-600 text-white rounded hover:bg-emerald-700 transition-colors"
                    >Load Settings</button>
                  </div>
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-muted-fg text-[11px] p-4 text-center">
                  Select a top list to see details, or double-click to load
                </div>
              )}
            </div>
          </div>
        )}

        {/* ====== ALERTS TAB ====== */}
        {activeTab === 'alerts' && (
          <div className="h-full flex flex-col">
            <div className="flex-shrink-0 px-2 pt-1.5 pb-1 border-b border-border flex items-center gap-2">
              <input type="text" value={alertSearch} onChange={(e) => setAlertSearch(e.target.value)}
                placeholder="Search..."
                className="flex-1 px-1.5 py-0.5 text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)] text-foreground" />
              <span className="text-[10px] text-muted-fg tabular-nums">{selectedAlerts.size}</span>
              <button onClick={() => setSelectedAlerts(new Set(ALERT_CATALOG.filter(a => a.active).map(a => a.eventType)))}
                className="text-[10px] text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300">all</button>
              <button onClick={() => setSelectedAlerts(new Set())}
                className="text-[10px] text-muted-fg hover:text-foreground/80">clear</button>
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
                      className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover/80 transition-colors border-b border-border-subtle">
                      <span className="text-[9px] text-muted-fg w-3">{exp ? '\u25BC' : '\u25B6'}</span>
                      <span className="text-[11px] font-medium text-foreground/90 flex-1">{category.name}</span>
                      {selCount > 0 && <span className="text-[9px] text-blue-600 dark:text-blue-400 font-semibold tabular-nums">{selCount}/{catTypes.length}</span>}
                      <button onClick={(e) => { e.stopPropagation(); toggleAlertCat(catTypes); }}
                        className="text-[9px] text-muted-fg hover:text-blue-600 dark:hover:text-blue-400 px-1">
                        {allSel ? 'none' : 'all'}
                      </button>
                    </button>
                    {exp && (
                      <div className="px-2 py-1 flex flex-wrap gap-[3px]">
                        {alerts.map(a => (
                          <button key={a.eventType} onClick={() => toggleAlert(a.eventType)}
                            className={`px-1.5 py-[2px] text-[11px] rounded border transition-colors ${selectedAlerts.has(a.eventType)
                              ? 'bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400 font-medium'
                              : 'border-border-subtle text-foreground/80 hover:bg-surface-hover hover:text-foreground'
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
            {
              id: 'price', group: 'Price', filters: [
                { label: 'Price', minK: 'min_price', maxK: 'max_price', suf: '$', phMin: '0.50', phMax: '500' },
                { label: 'VWAP', minK: 'min_vwap', maxK: 'max_vwap', suf: '$', phMin: '5', phMax: '200' },
                { label: 'Spread', minK: 'min_spread', maxK: 'max_spread', suf: '%', phMin: '0.01', phMax: '1' },
                { label: 'Bid Size', minK: 'min_bid_size', maxK: 'max_bid_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Ask Size', minK: 'min_ask_size', maxK: 'max_ask_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'NBBO Distance', minK: 'min_distance_from_nbbo', maxK: 'max_distance_from_nbbo', suf: '%', phMin: '0', phMax: '1' },
              ]
            },
            {
              id: 'change', group: 'Change', filters: [
                { label: 'Change %', minK: 'min_change_percent', maxK: 'max_change_percent', suf: '%', phMin: '-10', phMax: '50' },
                { label: 'Change from Open', minK: 'min_change_from_open', maxK: 'max_change_from_open', suf: '%', phMin: '-5', phMax: '20' },
                { label: 'Gap %', minK: 'min_gap_percent', maxK: 'max_gap_percent', suf: '%', phMin: '-10', phMax: '30' },
                { label: 'Pre-Market %', minK: 'min_premarket_change_percent', maxK: 'max_premarket_change_percent', suf: '%', phMin: '-5', phMax: '20' },
                { label: 'Post-Market %', minK: 'min_postmarket_change_percent', maxK: 'max_postmarket_change_percent', suf: '%', phMin: '-5', phMax: '10' },
                { label: 'From High %', minK: 'min_price_from_high', maxK: 'max_price_from_high', suf: '%', phMin: '-20', phMax: '0' },
                { label: 'From Low %', minK: 'min_price_from_low', maxK: 'max_price_from_low', suf: '%', phMin: '0', phMax: '50' },
                { label: 'Change Open $', minK: 'min_change_from_open_dollars', maxK: 'max_change_from_open_dollars', suf: '$', phMin: '-5', phMax: '10' },
                { label: 'From Intraday High', minK: 'min_price_from_intraday_high', maxK: 'max_price_from_intraday_high', suf: '%', phMin: '-10', phMax: '0' },
                { label: 'From Intraday Low', minK: 'min_price_from_intraday_low', maxK: 'max_price_from_intraday_low', suf: '%', phMin: '0', phMax: '20' },
              ]
            },
            {
              id: 'volume', group: 'Volume', filters: [
                { label: 'RVOL', minK: 'min_rvol', maxK: 'max_rvol', suf: 'x', phMin: '1', phMax: '10' },
                { label: 'Volume', minK: 'min_volume', maxK: 'max_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
                { label: 'Volume 1 Min', minK: 'min_vol_1min', maxK: 'max_vol_1min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '50' },
                { label: 'Volume 5 Min', minK: 'min_vol_5min', maxK: 'max_vol_5min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '100' },
                { label: 'Volume 10 Min', minK: 'min_vol_10min', maxK: 'max_vol_10min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '5', phMax: '200' },
                { label: 'Volume 15 Min', minK: 'min_vol_15min', maxK: 'max_vol_15min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
                { label: 'Volume 30 Min', minK: 'min_vol_30min', maxK: 'max_vol_30min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '20', phMax: '1000' },
                { label: 'Volume 1m %', minK: 'min_vol_1min_pct', maxK: 'max_vol_1min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Volume 5m %', minK: 'min_vol_5min_pct', maxK: 'max_vol_5min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Volume 10m %', minK: 'min_vol_10min_pct', maxK: 'max_vol_10min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Volume 15m %', minK: 'min_vol_15min_pct', maxK: 'max_vol_15min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Volume 30m %', minK: 'min_vol_30min_pct', maxK: 'max_vol_30min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Range 2m $', minK: 'min_range_2min', maxK: 'max_range_2min', suf: '$', phMin: '0.10', phMax: '2' },
                { label: 'Range 5m $', minK: 'min_range_5min', maxK: 'max_range_5min', suf: '$', phMin: '0.20', phMax: '5' },
                { label: 'Range 15m $', minK: 'min_range_15min', maxK: 'max_range_15min', suf: '$', phMin: '0.50', phMax: '10' },
                { label: 'Range 30m $', minK: 'min_range_30min', maxK: 'max_range_30min', suf: '$', phMin: '1', phMax: '15' },
                { label: 'Range 60m $', minK: 'min_range_60min', maxK: 'max_range_60min', suf: '$', phMin: '1', phMax: '20' },
                { label: 'Range 120m $', minK: 'min_range_120min', maxK: 'max_range_120min', suf: '$', phMin: '2', phMax: '30' },
                { label: 'Range 2m %', minK: 'min_range_2min_pct', maxK: 'max_range_2min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: 'Range 5m %', minK: 'min_range_5min_pct', maxK: 'max_range_5min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: 'Range 15m %', minK: 'min_range_15min_pct', maxK: 'max_range_15min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: 'Range 30m %', minK: 'min_range_30min_pct', maxK: 'max_range_30min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: 'Range 60m %', minK: 'min_range_60min_pct', maxK: 'max_range_60min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: 'Range 120m %', minK: 'min_range_120min_pct', maxK: 'max_range_120min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: 'Volume Today %', minK: 'min_volume_today_pct', maxK: 'max_volume_today_pct', suf: '%', phMin: '50', phMax: '500' },
              ]
            },
            {
              id: 'windows', group: 'Time Windows', filters: [
                { label: 'Change 1 Min', minK: 'min_chg_1min', maxK: 'max_chg_1min', suf: '%', phMin: '-2', phMax: '5' },
                { label: 'Change 5 Min', minK: 'min_chg_5min', maxK: 'max_chg_5min', suf: '%', phMin: '-5', phMax: '10' },
                { label: 'Change 10 Min', minK: 'min_chg_10min', maxK: 'max_chg_10min', suf: '%', phMin: '-5', phMax: '15' },
                { label: 'Change 15 Min', minK: 'min_chg_15min', maxK: 'max_chg_15min', suf: '%', phMin: '-8', phMax: '20' },
                { label: 'Change 30 Min', minK: 'min_chg_30min', maxK: 'max_chg_30min', suf: '%', phMin: '-10', phMax: '25' },
                { label: 'Change 60 Min', minK: 'min_chg_60min', maxK: 'max_chg_60min', suf: '%', phMin: '-15', phMax: '30' },
              ]
            },
            {
              id: 'quote', group: 'Quote', filters: [
                { label: 'Bid', minK: 'min_bid', maxK: 'max_bid', suf: '$', phMin: '1', phMax: '500' },
                { label: 'Ask', minK: 'min_ask', maxK: 'max_ask', suf: '$', phMin: '1', phMax: '500' },
                { label: 'Bid Size', minK: 'min_bid_size', maxK: 'max_bid_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Ask Size', minK: 'min_ask_size', maxK: 'max_ask_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Spread', minK: 'min_spread', maxK: 'max_spread', suf: '$', phMin: '0.01', phMax: '0.50' },
              ]
            },
            {
              id: 'tech', group: 'Intraday Technical', filters: [
                { label: 'ATR (14)', minK: 'min_atr', maxK: 'max_atr', suf: '$', phMin: '0.1', phMax: '5' },
                { label: 'ATR %', minK: 'min_atr_percent', maxK: 'max_atr_percent', suf: '%', phMin: '2', phMax: '10' },
                { label: 'RSI', minK: 'min_rsi', maxK: 'max_rsi', suf: '', phMin: '20', phMax: '80' },
                { label: 'EMA 20', minK: 'min_ema_20', maxK: 'max_ema_20', suf: '$', phMin: '5', phMax: '500' },
                { label: 'EMA 50', minK: 'min_ema_50', maxK: 'max_ema_50', suf: '$', phMin: '5', phMax: '500' },
                { label: 'SMA 5', minK: 'min_sma_5', maxK: 'max_sma_5', suf: '$', phMin: '1', phMax: '500' },
                { label: 'SMA 8', minK: 'min_sma_8', maxK: 'max_sma_8', suf: '$', phMin: '1', phMax: '500' },
                { label: 'SMA 20', minK: 'min_sma_20', maxK: 'max_sma_20', suf: '$', phMin: '5', phMax: '500' },
                { label: 'SMA 50', minK: 'min_sma_50', maxK: 'max_sma_50', suf: '$', phMin: '5', phMax: '500' },
                { label: 'SMA 200', minK: 'min_sma_200', maxK: 'max_sma_200', suf: '$', phMin: '5', phMax: '500' },
                { label: 'MACD', minK: 'min_macd_line', maxK: 'max_macd_line', suf: '', phMin: '-5', phMax: '5' },
                { label: 'MACD Hist', minK: 'min_macd_hist', maxK: 'max_macd_hist', suf: '', phMin: '-2', phMax: '2' },
                { label: 'Stochastic %K', minK: 'min_stoch_k', maxK: 'max_stoch_k', suf: '', phMin: '20', phMax: '80' },
                { label: 'Stochastic %D', minK: 'min_stoch_d', maxK: 'max_stoch_d', suf: '', phMin: '20', phMax: '80' },
                { label: 'ADX', minK: 'min_adx_14', maxK: 'max_adx_14', suf: '', phMin: '20', phMax: '50' },
                { label: 'Bollinger Upper', minK: 'min_bb_upper', maxK: 'max_bb_upper', suf: '$', phMin: '', phMax: '' },
                { label: 'Bollinger Lower', minK: 'min_bb_lower', maxK: 'max_bb_lower', suf: '$', phMin: '', phMax: '' },
              ]
            },
            {
              id: 'daily', group: 'Daily Indicators', filters: [
                { label: 'Daily SMA 20', minK: 'min_daily_sma_20', maxK: 'max_daily_sma_20', suf: '$', phMin: '', phMax: '' },
                { label: 'Daily SMA 50', minK: 'min_daily_sma_50', maxK: 'max_daily_sma_50', suf: '$', phMin: '', phMax: '' },
                { label: 'Daily SMA 200', minK: 'min_daily_sma_200', maxK: 'max_daily_sma_200', suf: '$', phMin: '', phMax: '' },
                { label: 'Daily RSI', minK: 'min_daily_rsi', maxK: 'max_daily_rsi', suf: '', phMin: '20', phMax: '80' },
                { label: '52w High', minK: 'min_high_52w', maxK: 'max_high_52w', suf: '$', phMin: '', phMax: '' },
                { label: '52w Low', minK: 'min_low_52w', maxK: 'max_low_52w', suf: '$', phMin: '', phMax: '' },
              ]
            },
            {
              id: 'fund', group: 'Fundamentals', filters: [
                { label: 'Market Cap', minK: 'min_market_cap', maxK: 'max_market_cap', suf: '$', units: ['K', 'M', 'B'], defU: 'M', phMin: '50', phMax: '10' },
                { label: 'Float', minK: 'min_float_shares', maxK: 'max_float_shares', suf: '', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '100' },
                { label: 'Shares Outstanding', minK: 'min_shares_outstanding', maxK: 'max_shares_outstanding', suf: '', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '500' },
              ]
            },
            {
              id: 'classification', group: 'Classification', filters: [
                // String filters - estos se manejan con selects, no con inputs numéricos
              ]
            },
            {
              id: 'trades', group: 'Trades Anomaly', filters: [
                { label: 'Trades', minK: 'min_trades_today', maxK: 'max_trades_today', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Z-Score', minK: 'min_trades_z_score', maxK: 'max_trades_z_score', suf: '', phMin: '1', phMax: '5' },
              ]
            },
            {
              id: 'derived', group: 'Derived', filters: [
                { label: '$ Volume', minK: 'min_dollar_volume', maxK: 'max_dollar_volume', suf: '$', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '100' },
                { label: 'Range $', minK: 'min_todays_range', maxK: 'max_todays_range', suf: '$', phMin: '0.1', phMax: '10' },
                { label: 'Range %', minK: 'min_todays_range_pct', maxK: 'max_todays_range_pct', suf: '%', phMin: '1', phMax: '20' },
                { label: 'Bid/Ask Ratio', minK: 'min_bid_ask_ratio', maxK: 'max_bid_ask_ratio', suf: '', phMin: '0.5', phMax: '3' },
                { label: 'Float Turnover', minK: 'min_float_turnover', maxK: 'max_float_turnover', suf: 'x', phMin: '0.01', phMax: '5' },
                { label: 'Position in Range', minK: 'min_pos_in_range', maxK: 'max_pos_in_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Below High', minK: 'min_below_high', maxK: 'max_below_high', suf: '$', phMin: '0', phMax: '5' },
                { label: 'Above Low', minK: 'min_above_low', maxK: 'max_above_low', suf: '$', phMin: '0', phMax: '5' },
                { label: 'Position of Open', minK: 'min_pos_of_open', maxK: 'max_pos_of_open', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Previous Volume', minK: 'min_prev_day_volume', maxK: 'max_prev_day_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '10000' },
              ]
            },
            {
              id: 'dist', group: 'Distance %', filters: [
                { label: 'Distance VWAP', minK: 'min_dist_from_vwap', maxK: 'max_dist_from_vwap', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Distance SMA 5', minK: 'min_dist_sma_5', maxK: 'max_dist_sma_5', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Distance SMA 8', minK: 'min_dist_sma_8', maxK: 'max_dist_sma_8', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Distance SMA 20', minK: 'min_dist_sma_20', maxK: 'max_dist_sma_20', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Distance SMA 50', minK: 'min_dist_sma_50', maxK: 'max_dist_sma_50', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Distance SMA 200', minK: 'min_dist_sma_200', maxK: 'max_dist_sma_200', suf: '%', phMin: '-50', phMax: '50' },
                { label: 'Dist Daily SMA 20', minK: 'min_dist_daily_sma_20', maxK: 'max_dist_daily_sma_20', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Dist Daily SMA 50', minK: 'min_dist_daily_sma_50', maxK: 'max_dist_daily_sma_50', suf: '%', phMin: '-20', phMax: '20' },
              ]
            },
            {
              id: 'multiday', group: 'Multi-Day Change %', filters: [
                { label: '1 Day', minK: 'min_change_1d', maxK: 'max_change_1d', suf: '%', phMin: '-10', phMax: '10' },
                { label: '3 Days', minK: 'min_change_3d', maxK: 'max_change_3d', suf: '%', phMin: '-20', phMax: '20' },
                { label: '5 Days', minK: 'min_change_5d', maxK: 'max_change_5d', suf: '%', phMin: '-20', phMax: '50' },
                { label: '10 Days', minK: 'min_change_10d', maxK: 'max_change_10d', suf: '%', phMin: '-30', phMax: '100' },
                { label: '20 Days', minK: 'min_change_20d', maxK: 'max_change_20d', suf: '%', phMin: '-50', phMax: '200' },
              ]
            },
            {
              id: 'avgvol', group: 'Avg Volume', filters: [
                { label: 'Average 5 Day', minK: 'min_avg_volume_5d', maxK: 'max_avg_volume_5d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
                { label: 'Average 10 Day', minK: 'min_avg_volume_10d', maxK: 'max_avg_volume_10d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
                { label: 'Average 20 Day', minK: 'min_avg_volume_20d', maxK: 'max_avg_volume_20d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
                { label: 'Average 3 Month', minK: 'min_avg_volume_3m', maxK: 'max_avg_volume_3m', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
              ]
            },
            {
              id: '52wextra', group: '52W / Daily Extra', filters: [
                { label: 'From 52W High %', minK: 'min_from_52w_high', maxK: 'max_from_52w_high', suf: '%', phMin: '-80', phMax: '0' },
                { label: 'From 52W Low %', minK: 'min_from_52w_low', maxK: 'max_from_52w_low', suf: '%', phMin: '0', phMax: '500' },
                { label: 'Daily ADX', minK: 'min_daily_adx_14', maxK: 'max_daily_adx_14', suf: '', phMin: '20', phMax: '50' },
                { label: 'Daily ATR %', minK: 'min_daily_atr_percent', maxK: 'max_daily_atr_percent', suf: '%', phMin: '1', phMax: '15' },
                { label: 'Daily BB Position', minK: 'min_daily_bb_position', maxK: 'max_daily_bb_position', suf: '%', phMin: '0', phMax: '100' },
              ]
            },
          ] as const;

          type FDef = (typeof FG)[number]['filters'][number];
          const hasUnits = (f: FDef): f is FDef & { units: readonly string[]; defU: string } => 'units' in f;
          const q = filterSearch.trim().toLowerCase();
          const visibleGroups = q
            ? FG.map(g => ({ ...g, filters: g.filters.filter(f => f.label.toLowerCase().includes(q)) })).filter(g => g.filters.length > 0)
            : FG;

          return (
            <div className="h-full flex flex-col">
              <div className="flex-shrink-0 px-2 pt-1.5 pb-1 border-b border-border flex items-center gap-2">
                <input type="text" value={filterSearch} onChange={(e) => setFilterSearch(e.target.value)}
                  placeholder="Search filters..."
                  className="flex-1 px-1.5 py-0.5 text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
                <span className="text-[10px] text-muted-fg tabular-nums">{activeFilterCount}</span>
                {activeFilterCount > 0 && (
                  <button onClick={() => { setFilters({}); setFilterUnits({}); }} className="text-[10px] text-muted-fg hover:text-blue-600">clear</button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto">
                {visibleGroups.map(g => {
                  const exp = expandedFilterGroups.has(g.id) || !!q;
                  const activeInGroup = g.filters.filter(f => filters[f.minK] !== undefined || filters[f.maxK] !== undefined).length;
                  return (
                    <div key={g.id}>
                      <button onClick={() => toggleFilterGroup(g.id)}
                        className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover transition-colors border-b border-border-subtle">
                        <span className="text-[9px] text-muted-fg/50 w-3">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-[11px] font-medium text-foreground/80 flex-1">{g.group}</span>
                        {activeInGroup > 0 && <span className="text-[9px] text-primary font-semibold tabular-nums">{activeInGroup}</span>}
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
                                <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">{f.label}</span>
                                <FmtNum
                                  value={toDisp(filters[f.minK] as number | undefined)}
                                  onChange={v => setFilter(f.minK, toRaw(v))}
                                  placeholder={f.phMin}
                                  className="w-[72px] px-1.5 py-[3px] text-[11px] font-mono border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)] text-foreground text-right tabular-nums" />
                                <span className="text-muted-fg/50 text-[8px]">-</span>
                                <FmtNum
                                  value={toDisp(filters[f.maxK] as number | undefined)}
                                  onChange={v => setFilter(f.maxK, toRaw(v))}
                                  placeholder={f.phMax}
                                  className="w-[72px] px-1.5 py-[3px] text-[11px] font-mono border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)] text-foreground text-right tabular-nums" />
                                {wu ? (
                                  <select value={curUnit} onChange={e => setUnitFor(uid, e.target.value)}
                                    className="w-8 py-[1px] text-[9px] text-muted-fg border border-border rounded bg-[var(--color-input-bg)] focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer appearance-none text-center">
                                    {f.units.map(u => <option key={u} value={u}>{u || 'sh'}</option>)}
                                  </select>
                                ) : (
                                  f.suf ? <span className="text-[9px] text-muted-fg/50 w-3 text-center">{f.suf}</span> : <span className="w-3" />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* String filters (not min/max) */}
                <div>
                  <button onClick={() => toggleFilterGroup('strings')}
                    className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover/80 transition-colors border-b border-border-subtle/80">
                    <span className="text-[9px] text-muted-fg/50 w-3">{expandedFilterGroups.has('strings') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-[11px] font-medium text-foreground/80 flex-1">Classification</span>
                    {(filters.security_type || filters.sector || filters.industry) && <span className="text-[9px] text-blue-600 dark:text-blue-400 font-semibold">active</span>}
                  </button>
                  {expandedFilterGroups.has('strings') && (
                    <div className="px-2 py-1 space-y-[3px]">
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">Type</span>
                        <select value={(filters.security_type as string) || ''} onChange={e => setFilter('security_type', e.target.value || undefined)}
                          className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]">
                          <option value="">All Types</option>
                          {SECURITY_TYPES.map(st => (
                            <option key={st.value} value={st.value}>{st.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">Sector</span>
                        <select value={(filters.sector as string) || ''} onChange={e => setFilter('sector', e.target.value || undefined)}
                          className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]">
                          <option value="">All Sectors</option>
                          {SECTORS.map(s => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">Industry</span>
                        <select value={(filters.industry as string) || ''} onChange={e => setFilter('industry', e.target.value || undefined)}
                          className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]">
                          <option value="">All Industries</option>
                          {INDUSTRIES.map(i => (
                            <option key={i.value} value={i.value}>{i.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })()}

        {/* ====== SYMBOLS TAB ====== */}
        {activeTab === 'symbols' && (
          <div className="h-full p-3 space-y-3">
            <div>
              <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Include only</label>
              <textarea value={symbolsInclude} onChange={(e) => setSymbolsInclude(e.target.value)}
                placeholder="AAPL, TSLA, NVDA..."
                className="w-full h-16 px-2 py-1 text-xs font-mono border border-border rounded resize-none focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
              <p className="text-[10px] text-muted-fg">Empty = all symbols</p>
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Exclude</label>
              <textarea value={symbolsExclude} onChange={(e) => setSymbolsExclude(e.target.value)}
                placeholder="SPY, QQQ, IWM..."
                className="w-full h-16 px-2 py-1 text-xs font-mono border border-border rounded resize-none focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
            </div>
          </div>
        )}

        {/* ====== SUMMARY TAB ====== */}
        {activeTab === 'summary' && builderMode === 'strategy' && (
          <div className="h-full flex flex-col">
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              <div>
                <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Strategy Name</label>
                <input type="text" value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="My Strategy..."
                  className="w-full px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Category</label>
                <select value={saveCategory} onChange={e => setSaveCategory(e.target.value)}
                  className="w-full px-2 py-1 text-xs border border-border rounded bg-surface text-foreground/80 focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="custom">Custom</option>
                  <option value="bullish">Bullish</option>
                  <option value="bearish">Bearish</option>
                  <option value="neutral">Neutral</option>
                </select>
              </div>
              <div className="py-1 border-t border-border-subtle">
                <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Alerts ({selectedAlerts.size})</div>
                {selectedAlerts.size === 0
                  ? <span className="text-[10px] text-muted-fg/50">none selected</span>
                  : <div className="flex flex-wrap gap-1">
                    {Array.from(selectedAlerts).map(et => (
                      <span key={et} className="px-1.5 py-0.5 bg-primary/10 border border-border rounded text-[10px] text-primary">{alertTypeLabel(et)}</span>
                    ))}
                  </div>
                }
              </div>
              <div className="py-1 border-t border-border-subtle">
                <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters ({activeFilterCount})</div>
                {activeFilterCount === 0
                  ? <span className="text-[10px] text-muted-fg/50">none</span>
                  : <div className="flex flex-wrap gap-1">
                    {filtersToDisplay(filters).map(f => (
                      <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                    ))}
                  </div>
                }
              </div>
              {(symbolsInclude.trim() || symbolsExclude.trim()) && (
                <div className="py-1 border-t border-border-subtle">
                  <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Symbols</div>
                  {symbolsInclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">+ {symbolsInclude.trim()}</div>}
                  {symbolsExclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">- {symbolsExclude.trim()}</div>}
                </div>
              )}
            </div>
            {/* Strategy action buttons */}
            <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover space-y-1.5">
              {loadedStrategyId && !isDirty ? (
                <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                  className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${selectedAlerts.size > 0 ? 'bg-primary text-white hover:bg-primary-hover' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                  Open
                </button>
              ) : loadedStrategyId && isDirty ? (
                <>
                  <button onClick={handleUpdate} disabled={saving || selectedAlerts.size === 0}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${!saving && selectedAlerts.size > 0 ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                    {saving ? 'Saving...' : 'Update & Open'}
                  </button>
                  <div className="flex gap-1.5">
                    <button onClick={handleCreate} disabled={!canCreate || saving}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">Save as new</button>
                    <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">Open only</button>
                  </div>
                </>
              ) : (
                <>
                  <button onClick={handleCreate} disabled={!canCreate || saving}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${canCreate && !saving ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                    {saving ? 'Saving...' : 'Save & Open'}
                  </button>
                  <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                    className="w-full py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">
                    Open without saving
                  </button>
                </>
              )}
              {onBacktestStrategy && selectedAlerts.size > 0 && (
                <button onClick={() => onBacktestStrategy({
                  eventTypes: Array.from(selectedAlerts),
                  filters: { ...filters },
                  name: strategyName.trim() || 'Strategy Backtest',
                })}
                  className="w-full py-1 text-xs text-amber-700 bg-amber-500/10 border border-amber-200 rounded hover:bg-amber-500/15 font-medium transition-colors">
                  Backtest Strategy
                </button>
              )}
              {selectedAlerts.size === 0 && (
                <p className="text-[10px] text-muted-fg text-center">Select alerts first</p>
              )}
            </div>
          </div>
        )}

        {/* ====== SUMMARY TAB — TOP LIST MODE ====== */}
        {activeTab === 'summary' && builderMode === 'toplist' && (
          <div className="h-full flex flex-col">
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              <div>
                <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Top List Name</label>
                <input type="text" value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="My Top List..."
                  className="w-full px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-emerald-500 bg-surface" />
              </div>

              {/* Mode indicator */}
              <div className="py-1 border-t border-border-subtle">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 rounded text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                    Scanner / Top List
                  </span>
                  <span className="text-[10px] text-muted-fg">Real-time ticker list updated every scan cycle</span>
                </div>
              </div>

              {/* Filters summary */}
              <div className="py-1 border-t border-border-subtle">
                <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters ({activeFilterCount})</div>
                {activeFilterCount === 0
                  ? <span className="text-[10px] text-amber-500">Add at least 1 filter</span>
                  : <div className="flex flex-wrap gap-1">
                    {filtersToDisplay(filters).map(f => (
                      <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                    ))}
                  </div>
                }
              </div>

              {/* Symbols summary */}
              {(symbolsInclude.trim() || symbolsExclude.trim()) && (
                <div className="py-1 border-t border-border-subtle">
                  <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Symbols</div>
                  {symbolsInclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">+ {symbolsInclude.trim()}</div>}
                  {symbolsExclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">- {symbolsExclude.trim()}</div>}
                </div>
              )}
            </div>

            {/* Top List action buttons — 3 states */}
            <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover space-y-1.5">
              {loadedScanId && !isScanDirty ? (
                /* Saved scan, no changes → just Open */
                <button onClick={handleOpenScanDirect}
                  className="w-full py-1.5 text-xs rounded font-semibold transition-colors bg-emerald-600 text-white hover:bg-emerald-700">
                  Open Scanner
                </button>
              ) : loadedScanId && isScanDirty ? (
                /* Saved scan, modified → Update or Save as new */
                <>
                  <button onClick={handleUpdateTopList} disabled={!canCreate || saving}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${canCreate && !saving ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                    {saving ? 'Saving...' : 'Update & Open Scanner'}
                  </button>
                  <div className="flex gap-1.5">
                    <button onClick={handleCreateTopList} disabled={!canCreate || saving}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">
                      Save as new
                    </button>
                    <button onClick={handleOpenScanDirect}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover transition-colors">
                      Open only
                    </button>
                  </div>
                </>
              ) : (
                /* New / built-in top list → Save & Open */
                <button onClick={handleCreateTopList} disabled={!canCreate || saving}
                  className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${canCreate && !saving ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                  {saving ? 'Saving...' : 'Save & Open Scanner'}
                </button>
              )}
              {activeFilterCount === 0 && !loadedScanId && (
                <p className="text-[10px] text-muted-fg text-center">Add filters first</p>
              )}
              {!strategyName.trim() && activeFilterCount > 0 && !loadedScanId && (
                <p className="text-[10px] text-muted-fg text-center">Enter a name</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
