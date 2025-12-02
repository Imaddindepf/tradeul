'use client';

import { useCallback } from 'react';
import { useFiltersStore } from '@/stores/useFiltersStore';
import { parseHumanNumber, formatHumanNumber } from '@/lib/utils/numberFormat';
import { X, Sliders, Check } from 'lucide-react';

// ============================================================================
// Filter Config
// ============================================================================

interface FilterConfig {
  key: string;
  minKey: string;
  maxKey?: string;
  label: string;
  unit?: string;
  defaultMin?: number;
  defaultMax?: number;
  examples?: string;
}

const FILTERS: FilterConfig[] = [
  { key: 'price', minKey: 'min_price', maxKey: 'max_price', label: 'Price', unit: '$', defaultMin: 1, defaultMax: 100, examples: '1, 5, 10, 50, 100' },
  { key: 'volume', minKey: 'min_volume', label: 'Volume', defaultMin: 1000000, examples: '100k, 500k, 1m, 10m' },
  { key: 'rvol', minKey: 'min_rvol', maxKey: 'max_rvol', label: 'RVOL', defaultMin: 2, defaultMax: 10, examples: '1.5, 2, 3, 5, 10' },
  { key: 'change', minKey: 'min_change_percent', maxKey: 'max_change_percent', label: 'Change %', unit: '%', defaultMin: 5, defaultMax: 50, examples: '5, 10, 20, 50' },
  { key: 'market_cap', minKey: 'min_market_cap', maxKey: 'max_market_cap', label: 'Market Cap', defaultMin: 10000000, defaultMax: 1000000000, examples: '10m, 100m, 1b, 10b' },
  { key: 'float', minKey: 'min_float', maxKey: 'max_float', label: 'Float', defaultMin: 10000000, defaultMax: 100000000, examples: '1m, 10m, 50m, 100m' },
];

// ============================================================================
// Main Component
// ============================================================================

export function FilterManagerContent() {
  const { activeFilters, hasActiveFilters, setFilter, clearFilter, clearAllFilters } = useFiltersStore();

  // Obtener filtros activos
  const getActiveFilterKeys = useCallback(() => {
    const active: string[] = [];
    FILTERS.forEach(config => {
      const minVal = activeFilters[config.minKey as keyof typeof activeFilters];
      const maxVal = config.maxKey ? activeFilters[config.maxKey as keyof typeof activeFilters] : undefined;
      if (minVal !== undefined || maxVal !== undefined) {
        active.push(config.key);
      }
    });
    return active;
  }, [activeFilters]);

  const activeFilterKeys = getActiveFilterKeys();

  const handleToggleFilter = useCallback((config: FilterConfig) => {
    const isActive = activeFilterKeys.includes(config.key);
    if (isActive) {
      // Desactivar
      clearFilter(config.minKey as any);
      if (config.maxKey) {
        clearFilter(config.maxKey as any);
      }
    } else {
      // Activar con valor por defecto
      setFilter(config.minKey as any, config.defaultMin ?? 0);
    }
  }, [activeFilterKeys, setFilter, clearFilter]);

  const handleMinChange = useCallback((config: FilterConfig, value: string) => {
    const parsed = parseHumanNumber(value);
    setFilter(config.minKey as any, parsed);
  }, [setFilter]);

  const handleMaxChange = useCallback((config: FilterConfig, value: string) => {
    if (!config.maxKey) return;
    const parsed = parseHumanNumber(value);
    setFilter(config.maxKey as any, parsed);
  }, [setFilter]);

  const activeCount = activeFilterKeys.length;

  return (
    <div className="h-full flex flex-col bg-white text-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-blue-600" />
          <h2 className="text-sm font-bold text-slate-800">Scanner Filters</h2>
          {hasActiveFilters && (
            <span className="px-2 py-0.5 bg-blue-600 text-white rounded-full text-[9px] font-bold">
              {activeCount} active
            </span>
          )}
        </div>
        {hasActiveFilters && (
          <button
            onClick={clearAllFilters}
            className="text-[9px] px-2 py-1 text-red-600 hover:bg-red-50 rounded transition-colors font-medium"
          >
            Clear All
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        
        {/* Filter Selection Chips */}
        <div>
          <label className="text-[9px] font-semibold text-slate-500 uppercase tracking-wider mb-2 block">
            Select Filters
          </label>
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map(config => {
              const isActive = activeFilterKeys.includes(config.key);
              return (
                <button
                  key={config.key}
                  onClick={() => handleToggleFilter(config)}
                  className={`
                    inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-semibold
                    transition-all border-2
                    ${isActive 
                      ? 'bg-blue-600 text-white border-blue-600 shadow-sm' 
                      : 'bg-white text-slate-600 border-slate-200 hover:border-blue-400 hover:text-blue-600'
                    }
                  `}
                >
                  {isActive && <Check className="w-3 h-3" />}
                  {config.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Filters - Stacked Fields */}
        {activeFilterKeys.length > 0 && (
          <div className="space-y-3">
            <label className="text-[9px] font-semibold text-slate-500 uppercase tracking-wider block">
              Filter Values
            </label>
            
            {FILTERS.filter(c => activeFilterKeys.includes(c.key)).map(config => {
              const minVal = activeFilters[config.minKey as keyof typeof activeFilters] as number | undefined;
              const maxVal = config.maxKey ? activeFilters[config.maxKey as keyof typeof activeFilters] as number | undefined : undefined;
              
              return (
                <div key={config.key} className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-bold text-blue-800">{config.label}</span>
                    <button
                      onClick={() => handleToggleFilter(config)}
                      className="p-1 text-blue-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                  
                  <div className={`grid gap-3 ${config.maxKey ? 'grid-cols-2' : 'grid-cols-1'}`}>
                    {/* Min */}
                    <div>
                      <label className="text-[8px] font-semibold text-blue-600 uppercase mb-1 block">
                        Min {config.unit || ''}
                      </label>
                      <input
                        type="text"
                        value={minVal !== undefined ? formatHumanNumber(minVal) : ''}
                        onChange={(e) => handleMinChange(config, e.target.value)}
                        placeholder={config.examples?.split(',')[0]?.trim() || '0'}
                        className="w-full text-[11px] px-2.5 py-2 border-2 border-blue-300 rounded-lg bg-white focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 font-medium"
                      />
                    </div>
                    
                    {/* Max */}
                    {config.maxKey && (
                      <div>
                        <label className="text-[8px] font-semibold text-blue-600 uppercase mb-1 block">
                          Max {config.unit || ''}
                        </label>
                        <input
                          type="text"
                          value={maxVal !== undefined ? formatHumanNumber(maxVal) : ''}
                          onChange={(e) => handleMaxChange(config, e.target.value)}
                          placeholder={config.examples?.split(',').pop()?.trim() || '∞'}
                          className="w-full text-[11px] px-2.5 py-2 border-2 border-blue-300 rounded-lg bg-white focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 font-medium"
                        />
                      </div>
                    )}
                  </div>
                  
                  {/* Examples */}
                  {config.examples && (
                    <p className="mt-2 text-[8px] text-blue-500">
                      Examples: {config.examples}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Empty State */}
        {activeFilterKeys.length === 0 && (
          <div className="text-center py-8">
            <Sliders className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-[10px] text-slate-400">
              Click on a filter above to activate it
            </p>
          </div>
        )}

        {/* Format Help */}
        <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
          <p className="text-[9px] text-slate-500 leading-relaxed">
            <span className="font-bold text-slate-700">Format:</span>{' '}
            <code className="bg-slate-200 px-1 rounded">1k</code> = 1,000 • 
            <code className="bg-slate-200 px-1 rounded ml-1">1m</code> = 1 million • 
            <code className="bg-slate-200 px-1 rounded ml-1">1b</code> = 1 billion
          </p>
        </div>
      </div>
    </div>
  );
}
