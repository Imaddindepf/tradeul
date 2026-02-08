'use client';

import { useState, useCallback, useMemo, useRef } from 'react';
import { useUserFilters } from '@/hooks/useUserFilters';
import type { UserFilterCreate, UserFilter } from '@/lib/types/scannerFilters';
import { ConfirmModal } from '@/components/ui/ConfirmModal';

// ============================================================================
// Types
// ============================================================================

interface FilterDef {
  id: string;
  label: string;
  category: string;
  minKey?: string;
  maxKey?: string;
  unit?: string;
  step?: number;
  defaultMin?: number;
  defaultMax?: number;
  description?: string;
}

interface ActiveFilterState {
  def: FilterDef;
  minValue: number | null;
  maxValue: number | null;
}

// ============================================================================
// Filter Definitions
// ============================================================================

const FILTER_CATEGORIES = [
  { id: 'price', label: 'Price' },
  { id: 'volume', label: 'Volume' },
  { id: 'change', label: 'Change %' },
  { id: 'technical', label: 'Technical' },
  { id: 'fundamental', label: 'Fundamental' },
  { id: 'time', label: 'Time Windows' },
];

const ALL_FILTERS: FilterDef[] = [
  // Price
  { id: 'price', label: 'Price', category: 'price', minKey: 'min_price', maxKey: 'max_price', unit: '$', step: 0.01, description: 'Current stock price' },
  { id: 'spread', label: 'Spread', category: 'price', minKey: 'min_spread', maxKey: 'max_spread', unit: '%', step: 0.01, description: 'Bid-ask spread percentage' },
  { id: 'bid_size', label: 'Bid Size', category: 'price', minKey: 'min_bid_size', maxKey: 'max_bid_size', unit: 'sh', description: 'Shares at bid' },
  { id: 'ask_size', label: 'Ask Size', category: 'price', minKey: 'min_ask_size', maxKey: 'max_ask_size', unit: 'sh', description: 'Shares at ask' },
  { id: 'distance_nbbo', label: 'NBBO Distance', category: 'price', minKey: 'min_distance_from_nbbo', maxKey: 'max_distance_from_nbbo', unit: '%', description: 'Distance from NBBO' },
  // Volume
  { id: 'volume', label: 'Volume Today', category: 'volume', minKey: 'min_volume', unit: 'sh', description: 'Total volume today' },
  { id: 'rvol', label: 'Relative Volume', category: 'volume', minKey: 'min_rvol', maxKey: 'max_rvol', unit: 'x', step: 0.1, description: 'Volume vs average' },
  { id: 'avg_volume_5d', label: 'Avg Vol 5D', category: 'volume', minKey: 'min_avg_volume_5d', maxKey: 'max_avg_volume_5d', unit: 'sh', description: '5-day average volume' },
  { id: 'avg_volume_10d', label: 'Avg Vol 10D', category: 'volume', minKey: 'min_avg_volume_10d', maxKey: 'max_avg_volume_10d', unit: 'sh', description: '10-day average volume' },
  { id: 'avg_volume_3m', label: 'Avg Vol 3M', category: 'volume', minKey: 'min_avg_volume_3m', maxKey: 'max_avg_volume_3m', unit: 'sh', description: '3-month average volume' },
  { id: 'dollar_volume', label: 'Dollar Volume', category: 'volume', minKey: 'min_dollar_volume', maxKey: 'max_dollar_volume', unit: '$', description: 'Price x Volume' },
  { id: 'volume_today_pct', label: 'Vol Today %', category: 'volume', minKey: 'min_volume_today_pct', maxKey: 'max_volume_today_pct', unit: '%', description: '% of average' },
  // Change
  { id: 'change_percent', label: 'Change %', category: 'change', minKey: 'min_change_percent', maxKey: 'max_change_percent', unit: '%', step: 0.1, description: 'Percent change today' },
  { id: 'premarket_change', label: 'Pre-Market %', category: 'change', minKey: 'min_premarket_change_percent', maxKey: 'max_premarket_change_percent', unit: '%', description: 'Pre-market change' },
  { id: 'postmarket_change', label: 'Post-Market %', category: 'change', minKey: 'min_postmarket_change_percent', maxKey: 'max_postmarket_change_percent', unit: '%', description: 'Post-market change' },
  { id: 'price_from_high', label: 'From High', category: 'change', minKey: 'min_price_from_high', maxKey: 'max_price_from_high', unit: '%', description: '% from day high' },
  // Technical
  { id: 'atr', label: 'ATR', category: 'technical', minKey: 'min_atr', maxKey: 'max_atr', unit: '$', step: 0.01, description: 'Average True Range' },
  { id: 'volatility', label: 'Volatility', category: 'technical', minKey: 'min_volatility', maxKey: 'max_volatility', unit: '%', description: 'Price volatility' },
  // Fundamental
  { id: 'market_cap', label: 'Market Cap', category: 'fundamental', minKey: 'min_market_cap', maxKey: 'max_market_cap', unit: '$', description: 'Market capitalization' },
  { id: 'float', label: 'Float', category: 'fundamental', minKey: 'min_float', maxKey: 'max_float', unit: 'sh', description: 'Free float shares' },
  { id: 'shares_outstanding', label: 'Shares Out', category: 'fundamental', minKey: 'min_shares_outstanding', maxKey: 'max_shares_outstanding', unit: 'sh', description: 'Total shares' },
  { id: 'short_interest', label: 'Short Interest', category: 'fundamental', minKey: 'min_short_interest', maxKey: 'max_short_interest', unit: '%', description: '% shorted' },
  // Time Windows
  { id: 'chg_1min', label: 'Chg 1min', category: 'time', minKey: 'min_chg_1min', maxKey: 'max_chg_1min', unit: '%', description: 'Change last 1 min' },
  { id: 'chg_5min', label: 'Chg 5min', category: 'time', minKey: 'min_chg_5min', maxKey: 'max_chg_5min', unit: '%', description: 'Change last 5 min' },
  { id: 'chg_10min', label: 'Chg 10min', category: 'time', minKey: 'min_chg_10min', maxKey: 'max_chg_10min', unit: '%', description: 'Change last 10 min' },
  { id: 'chg_15min', label: 'Chg 15min', category: 'time', minKey: 'min_chg_15min', maxKey: 'max_chg_15min', unit: '%', description: 'Change last 15 min' },
  { id: 'chg_30min', label: 'Chg 30min', category: 'time', minKey: 'min_chg_30min', maxKey: 'max_chg_30min', unit: '%', description: 'Change last 30 min' },
  { id: 'vol_1min', label: 'Vol 1min', category: 'time', minKey: 'min_vol_1min', maxKey: 'max_vol_1min', unit: 'sh', description: 'Volume last 1 min' },
  { id: 'vol_5min', label: 'Vol 5min', category: 'time', minKey: 'min_vol_5min', maxKey: 'max_vol_5min', unit: 'sh', description: 'Volume last 5 min' },
];

// ============================================================================
// Helpers
// ============================================================================

const UNIT_MUL: Record<string, number> = { '': 1, K: 1e3, M: 1e6, B: 1e9 };

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '';
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${parseFloat((value / 1e9).toPrecision(3))}B`;
  if (abs >= 1e6) return `${parseFloat((value / 1e6).toPrecision(3))}M`;
  if (abs >= 1e3) return `${parseFloat((value / 1e3).toPrecision(3))}K`;
  return String(value);
}

function parseInput(value: string): number | null {
  if (!value.trim()) return null;
  let cleaned = value.toUpperCase().trim();
  let multiplier = 1;
  if (cleaned.endsWith('B')) { multiplier = 1e9; cleaned = cleaned.slice(0, -1); }
  else if (cleaned.endsWith('M')) { multiplier = 1e6; cleaned = cleaned.slice(0, -1); }
  else if (cleaned.endsWith('K')) { multiplier = 1e3; cleaned = cleaned.slice(0, -1); }
  const num = parseFloat(cleaned);
  return isNaN(num) ? null : num * multiplier;
}

/** Formatted numeric input: thousand separators on blur, raw on focus */
function FmtNum({ value, onChange, placeholder, className }: {
  value: number | null;
  onChange: (v: number | null) => void;
  placeholder?: string;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [editStr, setEditStr] = useState('');
  const display = value !== null ? value.toLocaleString('en-US', { maximumFractionDigits: 6 }) : '';
  return (
    <input type="text" inputMode="decimal"
      value={editing ? editStr : display}
      onFocus={() => { setEditing(true); setEditStr(value !== null ? String(value) : ''); }}
      onBlur={() => {
        setEditing(false);
        onChange(parseInput(editStr.replace(/,/g, '')));
      }}
      onChange={e => setEditStr(e.target.value)}
      placeholder={placeholder} className={className} />
  );
}

// ============================================================================
// Scan Folders
// ============================================================================

const SCAN_FOLDERS = [
  { id: 'all', label: 'All Scans' },
  { id: 'enabled', label: 'Active' },
  { id: 'disabled', label: 'Inactive' },
];

// ============================================================================
// Main Component
// ============================================================================

export function ScanBuilderContent() {
  const [search, setSearch] = useState('');
  const [activeFilters, setActiveFilters] = useState<ActiveFilterState[]>([]);
  const [scanName, setScanName] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [saving, setSaving] = useState(false);
  const [showSavedScans, setShowSavedScans] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['price', 'volume']));
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; scan: UserFilter | null }>({ isOpen: false, scan: null });
  const [scanFolder, setScanFolder] = useState('all');

  const searchRef = useRef<HTMLInputElement>(null);
  const { filters: savedScans, loading, createFilter, updateFilter, deleteFilter, refreshFilters } = useUserFilters();

  const activeIds = useMemo(() => new Set(activeFilters.map(f => f.def.id)), [activeFilters]);

  // Filtered search results
  const searchResults = useMemo(() => {
    if (!search.trim()) return null;
    const s = search.toLowerCase();
    return ALL_FILTERS.filter(f =>
      f.label.toLowerCase().includes(s) ||
      f.description?.toLowerCase().includes(s) ||
      f.category.toLowerCase().includes(s)
    );
  }, [search]);

  // Group filters by category
  const filtersByCategory = useMemo(() => {
    const map = new Map<string, FilterDef[]>();
    ALL_FILTERS.forEach(f => {
      const list = map.get(f.category) || [];
      list.push(f);
      map.set(f.category, list);
    });
    return map;
  }, []);

  // Filtered saved scans by folder
  const filteredScans = useMemo(() => {
    if (scanFolder === 'enabled') return savedScans.filter(s => s.enabled);
    if (scanFolder === 'disabled') return savedScans.filter(s => !s.enabled);
    return savedScans;
  }, [savedScans, scanFolder]);

  // Add filter
  const addFilter = useCallback((def: FilterDef) => {
    if (activeIds.has(def.id)) return;
    setActiveFilters(prev => [...prev, { def, minValue: null, maxValue: null }]);
    setSearch('');
    searchRef.current?.focus();
  }, [activeIds]);

  // Update filter value
  const updateFilterValue = useCallback((index: number, field: 'minValue' | 'maxValue', value: number | null) => {
    setActiveFilters(prev => {
      const newFilters = [...prev];
      newFilters[index] = { ...newFilters[index], [field]: value };
      return newFilters;
    });
  }, []);

  // Remove filter
  const removeFilter = useCallback((index: number) => {
    setActiveFilters(prev => prev.filter((_, i) => i !== index));
  }, []);

  // Toggle category
  const toggleCategory = useCallback((categoryId: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId); else next.add(categoryId);
      return next;
    });
  }, []);

  // Save scan
  const handleSave = useCallback(async () => {
    if (!scanName.trim() || activeFilters.length === 0) return;
    setSaving(true);
    try {
      const params: Record<string, number> = {};
      activeFilters.forEach(({ def, minValue, maxValue }) => {
        if (minValue !== null && def.minKey) params[def.minKey] = minValue;
        if (maxValue !== null && def.maxKey) params[def.maxKey] = maxValue;
      });
      await createFilter({
        name: scanName.trim(),
        description: `${activeFilters.length} filters`,
        enabled: true,
        filter_type: 'custom',
        parameters: params,
        priority: 0,
      });
      setScanName('');
      setActiveFilters([]);
      refreshFilters();
    } finally { setSaving(false); }
  }, [scanName, activeFilters, createFilter, refreshFilters]);

  // Load scan into editor
  const loadScan = useCallback((scan: UserFilter) => {
    const loaded: ActiveFilterState[] = [];
    Object.entries(scan.parameters || {}).forEach(([key, value]) => {
      if (value == null) return;
      const isMin = key.startsWith('min_');
      const baseKey = key.replace(/^(min_|max_)/, '');
      // Find existing entry or the filter def
      const existing = loaded.find(f => f.def.id === baseKey ||
        f.def.minKey === key || f.def.maxKey === key ||
        f.def.minKey?.replace('min_', '') === baseKey || f.def.maxKey?.replace('max_', '') === baseKey);
      if (existing) {
        if (isMin) existing.minValue = value as number;
        else existing.maxValue = value as number;
      } else {
        const def = ALL_FILTERS.find(f => f.minKey === key || f.maxKey === key);
        if (def) {
          loaded.push({
            def,
            minValue: isMin ? value as number : null,
            maxValue: !isMin ? value as number : null,
          });
        }
      }
    });
    setActiveFilters(loaded);
    setScanName(scan.name);
    setShowSavedScans(false);
  }, []);

  // Delete
  const handleDelete = useCallback((scan: UserFilter) => {
    setDeleteConfirm({ isOpen: true, scan });
  }, []);

  const confirmDelete = useCallback(async () => {
    if (deleteConfirm.scan) {
      await deleteFilter(deleteConfirm.scan.id);
      setDeleteConfirm({ isOpen: false, scan: null });
      refreshFilters();
    }
  }, [deleteConfirm.scan, deleteFilter, refreshFilters]);

  const inputCls = "w-16 px-1.5 py-[3px] text-[10px] font-mono border border-slate-200 rounded text-right tabular-nums focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white";

  return (
    <div className="h-full flex flex-col bg-white text-slate-800 text-xs">
      {/* Search */}
      <div className="flex-shrink-0 p-2 border-b border-slate-200 bg-slate-50">
        <div className="relative">
          <input
            ref={searchRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search filters... (price, volume, rvol, market cap)"
            className="w-full px-2 py-1.5 text-xs border border-slate-200 rounded bg-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {search && (
            <button onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-[10px]">
              x
            </button>
          )}
        </div>

        {/* Search results dropdown */}
        {searchResults && searchResults.length > 0 && (
          <div className="absolute left-2 right-2 mt-1 bg-white border border-slate-200 rounded shadow-lg z-10 max-h-48 overflow-y-auto">
            {searchResults.map(f => (
              <button key={f.id} onClick={() => addFilter(f)} disabled={activeIds.has(f.id)}
                className={`w-full text-left px-3 py-1.5 flex items-center justify-between hover:bg-slate-50 ${
                  activeIds.has(f.id) ? 'opacity-50 cursor-default bg-blue-50' : ''
                }`}>
                <div>
                  <span className="font-medium text-[11px]">{f.label}</span>
                  <span className="ml-2 text-slate-400 text-[10px]">{f.description}</span>
                </div>
                {!activeIds.has(f.id) && <span className="text-[10px] text-blue-500">+ add</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main split view */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Filter categories */}
        <div className="w-44 border-r border-slate-200 overflow-y-auto bg-slate-50/50">
          {FILTER_CATEGORIES.map(cat => {
            const filters = filtersByCategory.get(cat.id) || [];
            const isExpanded = expandedCategories.has(cat.id);
            const activeInCategory = filters.filter(f => activeIds.has(f.id)).length;
            return (
              <div key={cat.id} className="border-b border-slate-100">
                <button onClick={() => toggleCategory(cat.id)}
                  className="w-full flex items-center gap-1 px-2 py-[5px] hover:bg-slate-100 transition-colors">
                  <span className="text-[9px] text-slate-300 w-3">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                  <span className="flex-1 text-left text-[11px] font-medium text-slate-700">{cat.label}</span>
                  {activeInCategory > 0 && (
                    <span className="text-[9px] text-blue-600 font-semibold tabular-nums">{activeInCategory}</span>
                  )}
                </button>
                {isExpanded && (
                  <div className="pb-0.5">
                    {filters.map(f => {
                      const isActive = activeIds.has(f.id);
                      return (
                        <button key={f.id} onClick={() => addFilter(f)} disabled={isActive}
                          className={`w-full text-left px-5 py-[3px] text-[10px] transition-colors ${
                            isActive ? 'bg-blue-50 text-blue-600 cursor-default' : 'text-slate-600 hover:bg-slate-100'
                          }`}>
                          {f.label}
                          {f.unit && <span className="text-slate-300 ml-1">{f.unit}</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right: Active filters or My Scans */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex-shrink-0 flex items-center justify-between px-3 py-1.5 border-b border-slate-100 bg-white">
            <span className="text-[11px] font-semibold text-slate-600">
              {showSavedScans ? 'My Scans' : `Active Filters (${activeFilters.length})`}
            </span>
            <div className="flex items-center gap-2">
              {!showSavedScans && activeFilters.length > 0 && (
                <button onClick={() => setActiveFilters([])}
                  className="text-[10px] text-slate-400 hover:text-red-500">
                  clear
                </button>
              )}
              <button onClick={() => setShowSavedScans(!showSavedScans)}
                className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                  showSavedScans
                    ? 'bg-blue-50 border-blue-200 text-blue-600'
                    : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                }`}>
                {showSavedScans ? 'Builder' : `My Scans (${savedScans.length})`}
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {showSavedScans ? (
              <div className="flex flex-col h-full">
                {/* Folder tabs */}
                <div className="flex-shrink-0 flex gap-0 border-b border-slate-100">
                  {SCAN_FOLDERS.map(f => (
                    <button key={f.id} onClick={() => setScanFolder(f.id)}
                      className={`px-3 py-1.5 text-[10px] border-b-2 transition-colors ${
                        scanFolder === f.id
                          ? 'border-blue-500 text-blue-600 font-semibold'
                          : 'border-transparent text-slate-400 hover:text-slate-600'
                      }`}>
                      {f.label}
                      {f.id === 'enabled' && <span className="ml-1 tabular-nums">({savedScans.filter(s => s.enabled).length})</span>}
                    </button>
                  ))}
                </div>

                {/* Scans list */}
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                  {loading ? (
                    <div className="text-center py-4 text-slate-400 text-[11px]">Loading...</div>
                  ) : filteredScans.length === 0 ? (
                    <div className="text-center py-4 text-slate-400">
                      <p className="text-[11px]">No scans</p>
                      <p className="text-[10px] mt-1">Create one using the filters</p>
                    </div>
                  ) : (
                    filteredScans.map(scan => (
                      <div key={scan.id}
                        className={`p-2 rounded border transition-colors ${
                          scan.enabled ? 'border-blue-200 bg-blue-50/30' : 'border-slate-200 bg-slate-50/50'
                        }`}>
                        <div className="flex items-center justify-between">
                          {editingId === scan.id ? (
                            <div className="flex items-center gap-1 flex-1">
                              <input type="text" value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                className="flex-1 px-2 py-0.5 text-xs border rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                                autoFocus
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') { updateFilter(scan.id, { name: editName }); setEditingId(null); }
                                  if (e.key === 'Escape') setEditingId(null);
                                }} />
                              <button onClick={() => { updateFilter(scan.id, { name: editName }); setEditingId(null); }}
                                className="text-[10px] text-blue-600 hover:text-blue-800 px-1">ok</button>
                              <button onClick={() => setEditingId(null)}
                                className="text-[10px] text-slate-400 hover:text-slate-600 px-1">x</button>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-2">
                                <button onClick={() => updateFilter(scan.id, { enabled: !scan.enabled })}
                                  className={`w-7 h-3.5 rounded-full transition-colors ${scan.enabled ? 'bg-blue-500' : 'bg-slate-300'}`}>
                                  <div className={`w-2.5 h-2.5 rounded-full bg-white transition-transform ${scan.enabled ? 'translate-x-3.5' : 'translate-x-0.5'}`} />
                                </button>
                                <span className="text-[11px] font-medium text-slate-700">{scan.name}</span>
                              </div>
                              <div className="flex items-center gap-1">
                                <button onClick={() => loadScan(scan)}
                                  className="text-[10px] text-blue-500 hover:text-blue-700 px-1">edit</button>
                                <button onClick={() => { setEditingId(scan.id); setEditName(scan.name); }}
                                  className="text-[10px] text-slate-400 hover:text-slate-600 px-1">rename</button>
                                <button onClick={() => handleDelete(scan)}
                                  className="text-[10px] text-slate-400 hover:text-red-500 px-1">del</button>
                              </div>
                            </>
                          )}
                        </div>
                        {/* Filter tags */}
                        <div className="mt-1 flex flex-wrap gap-1">
                          {Object.entries(scan.parameters || {}).filter(([_, v]) => v != null).map(([key, value]) => (
                            <span key={key} className="px-1 py-0.5 bg-white rounded text-[9px] text-slate-500 border border-slate-100">
                              {key.replace(/^(min_|max_)/, (m) => m === 'min_' ? '>' : '<').replace(/_/g, ' ')}: {formatValue(value as number)}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : activeFilters.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-400">
                <div className="text-center">
                  <p className="text-[11px]">Click filters from the left panel</p>
                  <p className="text-[10px] mt-1">or search above</p>
                </div>
              </div>
            ) : (
              <div className="p-2 space-y-1">
                {activeFilters.map((state, index) => {
                  const { def, minValue, maxValue } = state;
                  return (
                    <div key={def.id} className="flex items-center gap-1.5 p-1.5 bg-slate-50 rounded border border-slate-200 group">
                      <div className="flex-1 min-w-0">
                        <span className="text-[11px] font-medium text-slate-700">{def.label}</span>
                        {def.unit && <span className="text-[9px] text-slate-300 ml-1">{def.unit}</span>}
                      </div>
                      <div className="flex items-center gap-1">
                        {def.minKey && (
                          <FmtNum value={minValue} onChange={v => updateFilterValue(index, 'minValue', v)}
                            placeholder="min" className={inputCls} />
                        )}
                        {def.minKey && def.maxKey && <span className="text-slate-300 text-[8px]">-</span>}
                        {def.maxKey && (
                          <FmtNum value={maxValue} onChange={v => updateFilterValue(index, 'maxValue', v)}
                            placeholder="max" className={inputCls} />
                        )}
                      </div>
                      <button onClick={() => removeFilter(index)}
                        className="text-[10px] text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 px-0.5">
                        x
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Save section */}
          {activeFilters.length > 0 && !showSavedScans && (
            <div className="flex-shrink-0 p-2 border-t border-slate-200 bg-slate-50">
              <div className="flex gap-2">
                <input type="text" value={scanName} onChange={(e) => setScanName(e.target.value)}
                  placeholder="Scan name..."
                  className="flex-1 px-2 py-1.5 text-xs border border-slate-200 rounded focus:outline-none focus:border-blue-400"
                  onKeyDown={(e) => e.key === 'Enter' && handleSave()} />
                <button onClick={handleSave} disabled={!scanName.trim() || saving}
                  className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50 font-semibold">
                  {saving ? '...' : 'Save'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 px-2 py-1 border-t border-slate-200 bg-slate-50 text-[9px] text-slate-400 text-center">
        {ALL_FILTERS.length} filters | Enabled scans run via RETE engine in real-time
      </div>

      {/* Delete confirmation */}
      <ConfirmModal
        isOpen={deleteConfirm.isOpen}
        title="Delete Scan"
        message={`Delete "${deleteConfirm.scan?.name}"? This cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm({ isOpen: false, scan: null })}
      />
    </div>
  );
}
