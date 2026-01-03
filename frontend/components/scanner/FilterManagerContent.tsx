'use client';

import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useFiltersStore, type ActiveFilters } from '@/stores/useFiltersStore';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { X, Plus, ChevronDown, RotateCcw } from 'lucide-react';

// ============================================================================
// Types & Constants
// ============================================================================

type OperatorType = 'eq' | 'gt' | 'gte' | 'lt' | 'lte' | 'between';

interface FilterConfig {
  key: string;
  label: string;
  type: 'number' | 'percent' | 'units';
  unit?: string;
  minKey?: keyof ActiveFilters;  // Optional - some filters only have max (e.g., NBBO Distance)
  maxKey?: keyof ActiveFilters;
  defaultMin?: number;
  defaultMax?: number;
  step?: number;
  placeholder?: string;
}

interface ActiveFilter {
  config: FilterConfig;
  operator: OperatorType;
  value: number | null;
  value2: number | null; // For "between"
  multiplier: number; // For units (1, 1000, 1000000, 1000000000)
  displayValue: number | null; // Value shown in input (without multiplier)
  displayValue2: number | null; // For between
}

const FILTERS: FilterConfig[] = [
  {
    key: 'price',
    label: 'Price',
    type: 'number',
    unit: '$',
    minKey: 'min_price',
    maxKey: 'max_price',
    defaultMin: 1,
    defaultMax: 100,
    step: 0.01,
    placeholder: '5'
  },
  {
    key: 'volume',
    label: 'Volume',
    type: 'units',
    minKey: 'min_volume',
    defaultMin: 1000000,
    placeholder: '1'
  },
  {
    key: 'rvol',
    label: 'RVOL',
    type: 'number',
    unit: 'x',
    minKey: 'min_rvol',
    maxKey: 'max_rvol',
    defaultMin: 2,
    defaultMax: 10,
    step: 0.1,
    placeholder: '2'
  },
  {
    key: 'change',
    label: 'Change %',
    type: 'percent',
    unit: '%',
    minKey: 'min_change_percent',
    maxKey: 'max_change_percent',
    defaultMin: 5,
    defaultMax: 50,
    step: 0.1,
    placeholder: '5'
  },
  {
    key: 'market_cap',
    label: 'Market Cap',
    type: 'units',
    minKey: 'min_market_cap',
    maxKey: 'max_market_cap',
    defaultMin: 10000000,
    defaultMax: 1000000000,
    placeholder: '10'
  },
  {
    key: 'float',
    label: 'Float',
    type: 'units',
    minKey: 'min_float',
    maxKey: 'max_float',
    defaultMin: 10000000,
    defaultMax: 100000000,
    placeholder: '10'
  },
  {
    key: 'spread',
    label: 'Spread',
    type: 'number',
    unit: '¢',
    minKey: 'min_spread',
    maxKey: 'max_spread',
    defaultMin: 1,
    defaultMax: 50,
    step: 1,
    placeholder: '10'
  },
  {
    key: 'bid_size',
    label: 'Bid Size',
    type: 'units',
    minKey: 'min_bid_size',
    maxKey: 'max_bid_size',
    defaultMin: 1000,
    defaultMax: 100000,
    placeholder: '1'
  },
  {
    key: 'ask_size',
    label: 'Ask Size',
    type: 'units',
    minKey: 'min_ask_size',
    maxKey: 'max_ask_size',
    defaultMin: 1000,
    defaultMax: 100000,
    placeholder: '1'
  },
  {
    key: 'distance_from_nbbo',
    label: 'NBBO Distance',
    type: 'number',
    minKey: 'min_distance_from_nbbo',
    maxKey: 'max_distance_from_nbbo',
    defaultMin: 0,
    defaultMax: 0.1,
    step: 0.01,
    unit: '%',
    placeholder: '0.1'
  },
  {
    key: 'avg_volume_5d',
    label: 'Avg Volume (5D)',
    type: 'units',
    minKey: 'min_avg_volume_5d',
    maxKey: 'max_avg_volume_5d',
    defaultMin: 250000,
    defaultMax: 15000000,
    placeholder: '250'
  },
  {
    key: 'avg_volume_10d',
    label: 'Avg Volume (10D)',
    type: 'units',
    minKey: 'min_avg_volume_10d',
    maxKey: 'max_avg_volume_10d',
    defaultMin: 250000,
    defaultMax: 15000000,
    placeholder: '250'
  },
  {
    key: 'avg_volume_3m',
    label: 'Avg Volume (3M)',
    type: 'units',
    minKey: 'min_avg_volume_3m',
    maxKey: 'max_avg_volume_3m',
    defaultMin: 100000,
    defaultMax: 10000000,
    placeholder: '100'
  },
  {
    key: 'dollar_volume',
    label: 'Dollar Volume',
    type: 'units',
    minKey: 'min_dollar_volume',
    maxKey: 'max_dollar_volume',
    defaultMin: 1000000,
    defaultMax: 100000000,
    unit: '$',
    placeholder: '1'
  },
  {
    key: 'vol_1min',
    label: '1m vol',
    type: 'units',
    minKey: 'min_vol_1min',
    maxKey: 'max_vol_1min',
    defaultMin: 10000,
    defaultMax: 500000,
    placeholder: '10'
  },
  {
    key: 'vol_5min',
    label: '5m vol',
    type: 'units',
    minKey: 'min_vol_5min',
    maxKey: 'max_vol_5min',
    defaultMin: 50000,
    defaultMax: 2000000,
    placeholder: '50'
  },
  {
    key: 'vol_10min',
    label: '10m vol',
    type: 'units',
    minKey: 'min_vol_10min',
    maxKey: 'max_vol_10min',
    defaultMin: 100000,
    defaultMax: 5000000,
    placeholder: '100'
  },
  {
    key: 'vol_15min',
    label: '15m vol',
    type: 'units',
    minKey: 'min_vol_15min',
    maxKey: 'max_vol_15min',
    defaultMin: 150000,
    defaultMax: 7500000,
    placeholder: '150'
  },
  {
    key: 'vol_30min',
    label: '30m vol',
    type: 'units',
    minKey: 'min_vol_30min',
    maxKey: 'max_vol_30min',
    defaultMin: 300000,
    defaultMax: 15000000,
    placeholder: '300'
  },
];

const OPERATORS: { value: OperatorType; label: string; needsMax?: boolean }[] = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'eq', label: '=' },
  { value: 'between', label: 'Between', needsMax: true },
];

const UNIT_MULTIPLIERS = [
  { value: 1, label: '' },
  { value: 1_000, label: 'K' },
  { value: 1_000_000, label: 'M' },
  { value: 1_000_000_000, label: 'B' },
];

// ============================================================================
// Helper Functions
// ============================================================================

function getDefaultMultiplier(config: FilterConfig): number {
  if (config.type !== 'units') return 1;
  const defaultVal = config.defaultMin ?? 1000000;
  if (defaultVal >= 1_000_000_000) return 1_000_000_000;
  if (defaultVal >= 1_000_000) return 1_000_000;
  if (defaultVal >= 1_000) return 1_000;
  return 1;
}

function parseNumberInput(value: string): number | null {
  if (!value || value.trim() === '') return null;
  // Normalize: replace comma decimal separator with dot, remove thousand separators
  let cleaned = value.trim();
  // If there's a comma that looks like decimal separator (e.g., "1,5" or "10,25")
  // vs thousand separator (e.g., "1,000")
  if (/^\d+,\d{1,2}$/.test(cleaned)) {
    // Looks like decimal comma (European format): 1,5 → 1.5
    cleaned = cleaned.replace(',', '.');
  } else {
    // Remove commas as thousand separators
    cleaned = cleaned.replace(/,/g, '');
  }
  // Remove spaces
  cleaned = cleaned.replace(/\s/g, '');
  const num = parseFloat(cleaned);
  return isNaN(num) ? null : num;
}

function formatDisplayNumber(value: number | null): string {
  if (value === null || value === undefined) return '';
  // Format with up to 4 decimals, no thousand separators to avoid confusion
  if (Number.isInteger(value)) {
    return value.toString();
  }
  return value.toFixed(Math.min(4, (value.toString().split('.')[1]?.length || 0)));
}

// ============================================================================
// Number Input Component - handles local state for smooth typing
// ============================================================================

interface NumberInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  placeholder?: string;
  className?: string;
}

function NumberInput({ value, onChange, placeholder, className }: NumberInputProps) {
  const [localValue, setLocalValue] = useState(() =>
    value !== null ? formatDisplayNumber(value) : ''
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const isTypingRef = useRef(false);

  // Sync external value changes (only when not typing)
  useEffect(() => {
    if (!isTypingRef.current) {
      setLocalValue(value !== null ? formatDisplayNumber(value) : '');
    }
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    // Allow: digits, dot, comma, spaces (will be cleaned on blur)
    if (/^[\d.,\s]*$/.test(newValue) || newValue === '') {
      setLocalValue(newValue);
      isTypingRef.current = true;
    }
  };

  const handleBlur = () => {
    isTypingRef.current = false;
    const parsed = parseNumberInput(localValue);
    onChange(parsed);
    // Format the display value
    setLocalValue(parsed !== null ? formatDisplayNumber(parsed) : '');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      inputRef.current?.blur();
    }
  };

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode="decimal"
      value={localValue}
      onChange={handleChange}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      className={className}
      style={{ fontSize: '11px' }}
    />
  );
}

// ============================================================================
// Filter Row Component
// ============================================================================

interface FilterRowProps {
  filter: ActiveFilter;
  onChange: (updates: Partial<ActiveFilter>) => void;
  onRemove: () => void;
}

function FilterRow({ filter, onChange, onRemove }: FilterRowProps) {
  const { config, operator, displayValue, displayValue2, multiplier } = filter;
  const isUnits = config.type === 'units';
  const isBetween = operator === 'between';
  const hasMax = config.maxKey !== undefined;

  // Only show between option if the filter has a max key
  const availableOperators = hasMax
    ? OPERATORS
    : OPERATORS.filter(op => op.value !== 'between');

  const handleValueChange = (num: number | null) => {
    const actualValue = num !== null ? num * multiplier : null;
    onChange({ displayValue: num, value: actualValue });
  };

  const handleValue2Change = (num: number | null) => {
    const actualValue = num !== null ? num * multiplier : null;
    onChange({ displayValue2: num, value2: actualValue });
  };

  const handleMultiplierChange = (newMult: number) => {
    // Recalculate actual values with new multiplier
    const actualValue = displayValue !== null ? displayValue * newMult : null;
    const actualValue2 = displayValue2 !== null ? displayValue2 * newMult : null;
    onChange({ multiplier: newMult, value: actualValue, value2: actualValue2 });
  };

  const handleOperatorChange = (newOp: OperatorType) => {
    if (newOp === 'between' && !isBetween) {
      // Switching to between - set default second value
      const defaultMax = config.defaultMax ?? (displayValue ? displayValue * 10 : 100);
      const displayMax = defaultMax / multiplier;
      onChange({
        operator: newOp,
        displayValue2: displayMax,
        value2: displayMax * multiplier
      });
    } else if (newOp !== 'between' && isBetween) {
      // Switching from between - clear second value
      onChange({ operator: newOp, displayValue2: null, value2: null });
    } else {
      onChange({ operator: newOp });
    }
  };

  return (
    <div className="flex items-center gap-1.5 bg-slate-50/80 rounded-lg border border-slate-200 px-2 py-1.5 hover:border-slate-300 transition-colors">
      {/* Field Label */}
      <span className="text-slate-700 font-medium min-w-[70px]" style={{ fontSize: '11px' }}>
        {config.label}
      </span>

      {/* Operator Select */}
      <div className="relative">
        <select
          value={operator}
          onChange={(e) => handleOperatorChange(e.target.value as OperatorType)}
          className="appearance-none bg-white border border-slate-200 rounded px-2 py-1 pr-5 text-slate-600 cursor-pointer hover:border-slate-300 focus:outline-none focus:border-blue-400"
          style={{ fontSize: '10px' }}
        >
          {availableOperators.map((op) => (
            <option key={op.value} value={op.value}>{op.label}</option>
          ))}
        </select>
        <ChevronDown className="absolute right-1 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400 pointer-events-none" />
      </div>

      {/* Value Input */}
      <div className="flex items-center gap-1">
        {config.unit === '$' && (
          <span className="text-slate-400" style={{ fontSize: '10px' }}>$</span>
        )}
        <NumberInput
          value={displayValue}
          onChange={handleValueChange}
          placeholder={config.placeholder || '0'}
          className="w-[60px] px-1.5 py-1 border border-slate-200 rounded bg-white text-slate-800 focus:outline-none focus:border-blue-400 placeholder:text-slate-300"
        />

        {/* Units Selector for units type */}
        {isUnits && (
          <select
            value={multiplier}
            onChange={(e) => handleMultiplierChange(parseInt(e.target.value))}
            className="appearance-none bg-slate-100 border border-slate-200 rounded px-1.5 py-1 text-slate-600 cursor-pointer hover:bg-slate-200 focus:outline-none"
            style={{ fontSize: '10px' }}
          >
            {UNIT_MULTIPLIERS.filter(u => u.value >= 1000).map((unit) => (
              <option key={unit.value} value={unit.value}>{unit.label}</option>
            ))}
          </select>
        )}

        {/* Unit suffix for non-units types */}
        {!isUnits && config.unit && config.unit !== '$' && (
          <span className="text-slate-400" style={{ fontSize: '10px' }}>{config.unit}</span>
        )}
      </div>

      {/* Between second value */}
      {isBetween && (
        <>
          <span className="text-slate-400" style={{ fontSize: '9px' }}>to</span>
          <div className="flex items-center gap-1">
            {config.unit === '$' && (
              <span className="text-slate-400" style={{ fontSize: '10px' }}>$</span>
            )}
            <NumberInput
              value={displayValue2}
              onChange={handleValue2Change}
              placeholder={config.placeholder || '0'}
              className="w-[60px] px-1.5 py-1 border border-slate-200 rounded bg-white text-slate-800 focus:outline-none focus:border-blue-400 placeholder:text-slate-300"
            />
            {isUnits && (
              <select
                value={multiplier}
                onChange={(e) => handleMultiplierChange(parseInt(e.target.value))}
                className="appearance-none bg-slate-100 border border-slate-200 rounded px-1.5 py-1 text-slate-600 cursor-pointer hover:bg-slate-200 focus:outline-none"
                style={{ fontSize: '10px' }}
              >
                {UNIT_MULTIPLIERS.filter(u => u.value >= 1000).map((unit) => (
                  <option key={unit.value} value={unit.value}>{unit.label}</option>
                ))}
              </select>
            )}
            {!isUnits && config.unit && config.unit !== '$' && (
              <span className="text-slate-400" style={{ fontSize: '10px' }}>{config.unit}</span>
            )}
          </div>
        </>
      )}

      {/* Remove Button */}
      <button
        onClick={onRemove}
        className="ml-auto p-0.5 text-slate-300 hover:text-red-500 transition-colors"
        title="Remove filter"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function FilterManagerContent() {
  const font = useUserPreferencesStore(selectFont);
  const fontFamily = `var(--font-${font})`;

  const { activeFilters, setFilter, clearFilter, clearAllFilters, hasActiveFilters } = useFiltersStore();

  // Local state for active filters with operators
  const [localFilters, setLocalFilters] = useState<ActiveFilter[]>(() => {
    // Initialize from activeFilters in store
    const initial: ActiveFilter[] = [];

    FILTERS.forEach(config => {
      const minVal = config.minKey ? activeFilters[config.minKey] as number | undefined : undefined;
      const maxVal = config.maxKey ? activeFilters[config.maxKey] as number | undefined : undefined;

      if (minVal !== undefined || maxVal !== undefined) {
        const mult = getDefaultMultiplier(config);

        // Determine operator based on which values exist
        let operator: OperatorType = 'gt';
        if (minVal !== undefined && maxVal !== undefined) {
          operator = 'between';
        } else if (maxVal !== undefined && minVal === undefined) {
          operator = 'lt';
        }

        initial.push({
          config,
          operator,
          value: minVal ?? null,
          value2: maxVal ?? null,
          multiplier: mult,
          displayValue: minVal !== undefined ? minVal / mult : null,
          displayValue2: maxVal !== undefined ? maxVal / mult : null,
        });
      }
    });

    return initial;
  });

  // Get available filters (not yet added)
  const availableFilters = useMemo(() => {
    const activeKeys = localFilters.map(f => f.config.key);
    return FILTERS.filter(f => !activeKeys.includes(f.key));
  }, [localFilters]);

  // Add a new filter
  const addFilter = useCallback((config: FilterConfig) => {
    const mult = getDefaultMultiplier(config);
    const defaultDisplay = (config.defaultMin ?? 0) / mult;

    const newFilter: ActiveFilter = {
      config,
      operator: 'gt',
      value: config.defaultMin ?? 0,
      value2: null,
      multiplier: mult,
      displayValue: defaultDisplay,
      displayValue2: null,
    };

    setLocalFilters(prev => [...prev, newFilter]);

    // Apply to store immediately
    // For filters with only max (like NBBO Distance), use maxKey
    if (config.minKey) {
      setFilter(config.minKey, config.defaultMin ?? 0);
    } else if (config.maxKey && config.defaultMax !== undefined) {
      setFilter(config.maxKey, config.defaultMax);
    }
  }, [setFilter]);

  // Update a filter
  const updateFilter = useCallback((index: number, updates: Partial<ActiveFilter>) => {
    setLocalFilters(prev => {
      const newFilters = [...prev];
      const filter = { ...newFilters[index], ...updates };
      newFilters[index] = filter;

      // Apply to store based on operator
      const { config, operator, value, value2 } = filter;

      // Clear previous values
      if (config.minKey) {
        clearFilter(config.minKey);
      }
      if (config.maxKey) {
        clearFilter(config.maxKey);
      }

      // Set new values based on operator
      if (value !== null) {
        switch (operator) {
          case 'gt':
          case 'gte':
          case 'eq':
            // For filters with only max, use maxKey for these operators too
            if (config.minKey) {
              setFilter(config.minKey, value);
            } else if (config.maxKey) {
              setFilter(config.maxKey, value);
            }
            break;
          case 'lt':
          case 'lte':
            if (config.maxKey) {
              setFilter(config.maxKey, value);
            }
            break;
          case 'between':
            if (config.minKey) {
              setFilter(config.minKey, value);
            }
            if (config.maxKey && value2 !== null) {
              setFilter(config.maxKey, value2);
            }
            break;
        }
      }

      return newFilters;
    });
  }, [setFilter, clearFilter]);

  // Remove a filter
  const removeFilter = useCallback((index: number) => {
    setLocalFilters(prev => {
      const filter = prev[index];
      const newFilters = prev.filter((_, i) => i !== index);

      // Clear from store
      if (filter.config.minKey) {
        clearFilter(filter.config.minKey);
      }
      if (filter.config.maxKey) {
        clearFilter(filter.config.maxKey);
      }

      return newFilters;
    });
  }, [clearFilter]);

  // Clear all filters
  const handleClearAll = useCallback(() => {
    setLocalFilters([]);
    clearAllFilters();
  }, [clearAllFilters]);

  return (
    <div className="h-full flex flex-col bg-white text-slate-800" style={{ fontFamily }}>
      {/* Quick Add Chips */}
      <div className="flex-shrink-0 px-3 py-2.5 border-b border-slate-100 bg-slate-50/50">
        <div className="flex flex-wrap gap-1.5">
          {availableFilters.map(config => (
            <button
              key={config.key}
              onClick={() => addFilter(config)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded border border-dashed border-slate-300 text-slate-500 hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50/50 transition-all"
              style={{ fontSize: '10px' }}
            >
              <Plus className="w-3 h-3" />
              {config.label}
            </button>
          ))}

          {availableFilters.length === 0 && (
            <span className="text-slate-400 italic" style={{ fontSize: '10px' }}>
              All filters active
            </span>
          )}
        </div>
      </div>

      {/* Active Filters */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {localFilters.length > 0 ? (
          <div className="space-y-2">
            {localFilters.map((filter, index) => (
              <FilterRow
                key={filter.config.key}
                filter={filter}
                onChange={(updates) => updateFilter(index, updates)}
                onRemove={() => removeFilter(index)}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-slate-400">
            <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mb-2">
              <Plus className="w-5 h-5" />
            </div>
            <p style={{ fontSize: '11px' }}>Click a filter above to add it</p>
            <p className="text-slate-300 mt-1" style={{ fontSize: '10px' }}>
              Supports: 1,000 · 1.5M · Between values
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      {hasActiveFilters && (
        <div className="flex-shrink-0 px-3 py-2 border-t border-slate-100 bg-slate-50/30">
          <div className="flex items-center justify-between">
            <span className="text-slate-400" style={{ fontSize: '9px' }}>
              {localFilters.length} filter{localFilters.length !== 1 ? 's' : ''} active
            </span>
            <button
              onClick={handleClearAll}
              className="inline-flex items-center gap-1 px-2 py-1 text-red-500 hover:bg-red-50 rounded transition-colors"
              style={{ fontSize: '10px' }}
            >
              <RotateCcw className="w-3 h-3" />
              Clear All
            </button>
          </div>
        </div>
      )}

      {/* Format Help */}
      <div className="flex-shrink-0 px-3 py-2 border-t border-slate-100 bg-slate-50/50">
        <p className="text-slate-400 leading-relaxed" style={{ fontSize: '9px' }}>
          <span className="font-medium text-slate-500">Tips:</span>{' '}
          Decimals: 1.5 or 1,5 · Units: K M B · Press Enter or blur to apply
        </p>
      </div>
    </div>
  );
}
