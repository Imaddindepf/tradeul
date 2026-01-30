'use client';

import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useUserFilters } from '@/hooks/useUserFilters';
import { 
  Save, Trash2, Edit2, Check, X, Search, Plus,
  RotateCcw, Zap, ChevronDown, ChevronRight,
  TrendingUp, BarChart3, DollarSign, Activity, Clock, Layers
} from 'lucide-react';
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
  { id: 'price', label: 'Price', icon: DollarSign, color: 'text-green-600' },
  { id: 'volume', label: 'Volume', icon: BarChart3, color: 'text-blue-600' },
  { id: 'change', label: 'Change %', icon: TrendingUp, color: 'text-orange-600' },
  { id: 'technical', label: 'Technical', icon: Activity, color: 'text-purple-600' },
  { id: 'fundamental', label: 'Fundamental', icon: Layers, color: 'text-cyan-600' },
  { id: 'time', label: 'Time Windows', icon: Clock, color: 'text-pink-600' },
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

function formatValue(value: number | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return '';
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(unit === '$' || unit === '%' ? 2 : 0);
}

function parseInput(value: string): number | null {
  if (!value.trim()) return null;
  let cleaned = value.toUpperCase().trim();
  let multiplier = 1;
  if (cleaned.endsWith('B')) { multiplier = 1_000_000_000; cleaned = cleaned.slice(0, -1); }
  else if (cleaned.endsWith('M')) { multiplier = 1_000_000; cleaned = cleaned.slice(0, -1); }
  else if (cleaned.endsWith('K')) { multiplier = 1_000; cleaned = cleaned.slice(0, -1); }
  const num = parseFloat(cleaned);
  return isNaN(num) ? null : num * multiplier;
}

// ============================================================================
// Main Component - Trade Ideas Style
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
  
  const searchRef = useRef<HTMLInputElement>(null);
  const { filters: savedScans, loading, createFilter, updateFilter, deleteFilter, refreshFilters } = useUserFilters();

  const activeIds = useMemo(() => new Set(activeFilters.map(f => f.def.id)), [activeFilters]);

  // Filtered results based on search
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

  // Toggle category expansion
  const toggleCategory = useCallback((categoryId: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
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
    } finally {
      setSaving(false);
    }
  }, [scanName, activeFilters, createFilter, refreshFilters]);

  // Delete scan
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

  return (
    <div className="h-full flex flex-col bg-white text-slate-800 text-xs">
      {/* Header with Search - Trade Ideas Style */}
      <div className="flex-shrink-0 p-2 border-b border-slate-200 bg-slate-50">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            ref={searchRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search filters... (price, volume, rvol, market cap)"
            className="w-full pl-7 pr-3 py-1.5 text-xs border border-slate-300 rounded bg-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Search Results Dropdown */}
        {searchResults && searchResults.length > 0 && (
          <div className="absolute left-2 right-2 mt-1 bg-white border border-slate-200 rounded shadow-lg z-10 max-h-48 overflow-y-auto">
            {searchResults.map(f => (
              <button
                key={f.id}
                onClick={() => addFilter(f)}
                disabled={activeIds.has(f.id)}
                className={`w-full text-left px-3 py-2 flex items-center justify-between hover:bg-slate-50 ${
                  activeIds.has(f.id) ? 'opacity-50 cursor-default bg-blue-50' : ''
                }`}
              >
                <div>
                  <span className="font-medium">{f.label}</span>
                  <span className="ml-2 text-slate-400 text-[10px]">{f.description}</span>
                </div>
                {!activeIds.has(f.id) && <Plus className="w-3.5 h-3.5 text-blue-500" />}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Content - Split View */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - Filter Categories */}
        <div className="w-48 border-r border-slate-200 overflow-y-auto bg-slate-50/50">
          {FILTER_CATEGORIES.map(cat => {
            const Icon = cat.icon;
            const filters = filtersByCategory.get(cat.id) || [];
            const isExpanded = expandedCategories.has(cat.id);
            const activeInCategory = filters.filter(f => activeIds.has(f.id)).length;

            return (
              <div key={cat.id} className="border-b border-slate-100">
                <button
                  onClick={() => toggleCategory(cat.id)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-slate-100 transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown className="w-3 h-3 text-slate-400" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-slate-400" />
                  )}
                  <Icon className={`w-3.5 h-3.5 ${cat.color}`} />
                  <span className="flex-1 text-left font-medium text-slate-700">{cat.label}</span>
                  {activeInCategory > 0 && (
                    <span className="px-1.5 py-0.5 text-[9px] bg-blue-100 text-blue-600 rounded-full">
                      {activeInCategory}
                    </span>
                  )}
                </button>
                
                {isExpanded && (
                  <div className="pb-1">
                    {filters.map(f => {
                      const isActive = activeIds.has(f.id);
                      return (
                        <button
                          key={f.id}
                          onClick={() => addFilter(f)}
                          disabled={isActive}
                          className={`w-full text-left px-6 py-1 text-[11px] transition-colors ${
                            isActive 
                              ? 'bg-blue-50 text-blue-600 cursor-default' 
                              : 'text-slate-600 hover:bg-slate-100'
                          }`}
                        >
                          {f.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right Panel - Active Filters & Save */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Active Filters Header */}
          <div className="flex-shrink-0 flex items-center justify-between px-3 py-2 border-b border-slate-100 bg-white">
            <span className="font-semibold text-slate-600">
              Active Filters ({activeFilters.length})
            </span>
            <div className="flex items-center gap-2">
              {activeFilters.length > 0 && (
                <button
                  onClick={() => setActiveFilters([])}
                  className="text-[10px] text-slate-400 hover:text-red-500 flex items-center gap-1"
                >
                  <RotateCcw className="w-3 h-3" />
                  Clear
                </button>
              )}
              <button
                onClick={() => setShowSavedScans(!showSavedScans)}
                className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                  showSavedScans 
                    ? 'bg-blue-50 border-blue-200 text-blue-600' 
                    : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                }`}
              >
                My Scans ({savedScans.length})
              </button>
            </div>
          </div>

          {/* Active Filters List */}
          <div className="flex-1 overflow-y-auto p-2">
            {showSavedScans ? (
              // Saved Scans View
              <div className="space-y-1.5">
                {loading ? (
                  <div className="text-center py-4 text-slate-400">Loading...</div>
                ) : savedScans.length === 0 ? (
                  <div className="text-center py-4 text-slate-400">
                    <p>No saved scans</p>
                    <p className="text-[10px] mt-1">Create one using the filters</p>
                  </div>
                ) : (
                  savedScans.map(scan => (
                    <div
                      key={scan.id}
                      className={`p-2 rounded border ${
                        scan.enabled ? 'border-blue-200 bg-blue-50/30' : 'border-slate-200 bg-slate-50/50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        {editingId === scan.id ? (
                          <div className="flex items-center gap-1 flex-1">
                            <input
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              className="flex-1 px-2 py-0.5 text-xs border rounded"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  updateFilter(scan.id, { name: editName });
                                  setEditingId(null);
                                }
                                if (e.key === 'Escape') setEditingId(null);
                              }}
                            />
                            <button onClick={() => { updateFilter(scan.id, { name: editName }); setEditingId(null); }}>
                              <Check className="w-3.5 h-3.5 text-green-500" />
                            </button>
                            <button onClick={() => setEditingId(null)}>
                              <X className="w-3.5 h-3.5 text-red-500" />
                            </button>
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => updateFilter(scan.id, { enabled: !scan.enabled })}
                                className={`w-7 h-3.5 rounded-full transition-colors ${scan.enabled ? 'bg-blue-500' : 'bg-slate-300'}`}
                              >
                                <div className={`w-2.5 h-2.5 rounded-full bg-white transition-transform ${scan.enabled ? 'translate-x-3.5' : 'translate-x-0.5'}`} />
                              </button>
                              <span className="font-medium text-slate-700">{scan.name}</span>
                            </div>
                            <div className="flex items-center gap-0.5">
                              <button onClick={() => { setEditingId(scan.id); setEditName(scan.name); }} className="p-1 hover:bg-slate-100 rounded">
                                <Edit2 className="w-3 h-3 text-slate-400" />
                              </button>
                              <button onClick={() => handleDelete(scan)} className="p-1 hover:bg-red-50 rounded">
                                <Trash2 className="w-3 h-3 text-slate-400 hover:text-red-500" />
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {Object.entries(scan.parameters || {}).filter(([_, v]) => v != null).map(([key, value]) => (
                          <span key={key} className="px-1 py-0.5 bg-white rounded text-[9px] text-slate-500 border border-slate-200">
                            {key.replace(/^(min_|max_)/, '').replace(/_/g, ' ')}: {formatValue(value as number)}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            ) : activeFilters.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-400">
                <div className="text-center">
                  <Zap className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  <p>Click filters from the left panel</p>
                  <p className="text-[10px] mt-1">or search above</p>
                </div>
              </div>
            ) : (
              <div className="space-y-1.5">
                {activeFilters.map((state, index) => {
                  const { def, minValue, maxValue } = state;
                  return (
                    <div key={def.id} className="flex items-center gap-2 p-2 bg-slate-50 rounded border border-slate-200 group">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-slate-700">{def.label}</div>
                        <div className="text-[10px] text-slate-400">{def.description}</div>
                      </div>
                      
                      <div className="flex items-center gap-1">
                        {def.minKey && (
                          <input
                            type="text"
                            value={minValue !== null ? String(minValue) : ''}
                            onChange={(e) => updateFilterValue(index, 'minValue', parseInput(e.target.value))}
                            placeholder="min"
                            className="w-14 px-1.5 py-0.5 text-[11px] border border-slate-200 rounded text-center focus:outline-none focus:border-blue-400"
                          />
                        )}
                        {def.minKey && def.maxKey && <span className="text-slate-300">-</span>}
                        {def.maxKey && (
                          <input
                            type="text"
                            value={maxValue !== null ? String(maxValue) : ''}
                            onChange={(e) => updateFilterValue(index, 'maxValue', parseInput(e.target.value))}
                            placeholder="max"
                            className="w-14 px-1.5 py-0.5 text-[11px] border border-slate-200 rounded text-center focus:outline-none focus:border-blue-400"
                          />
                        )}
                        {def.unit && <span className="text-[10px] text-slate-400 w-3">{def.unit}</span>}
                      </div>
                      
                      <button
                        onClick={() => removeFilter(index)}
                        className="p-0.5 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Save Section */}
          {activeFilters.length > 0 && !showSavedScans && (
            <div className="flex-shrink-0 p-2 border-t border-slate-200 bg-slate-50">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={scanName}
                  onChange={(e) => setScanName(e.target.value)}
                  placeholder="Scan name..."
                  className="flex-1 px-2 py-1.5 text-xs border border-slate-200 rounded focus:outline-none focus:border-blue-400"
                  onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                />
                <button
                  onClick={handleSave}
                  disabled={!scanName.trim() || saving}
                  className="flex items-center gap-1 px-3 py-1.5 bg-blue-500 text-white text-xs rounded hover:bg-blue-600 disabled:opacity-50"
                >
                  <Save className="w-3.5 h-3.5" />
                  Save
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

      {/* Delete Confirmation */}
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
