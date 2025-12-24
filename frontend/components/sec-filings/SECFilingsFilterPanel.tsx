'use client';

import { useState, useCallback } from 'react';
import { X, RotateCcw } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';
import { FILING_CATEGORIES, FORM_8K_ITEMS, FORM_TYPE_INFO, EIGHT_K_GROUPS } from '@/lib/sec-filing-types';

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono', 
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

export interface SECFilters {
  ticker: string;
  categories: string[];
  formTypes: string[];
  items8K: string[];
  dateFrom: string;
  dateTo: string;
  importanceLevel: 'all' | 'critical' | 'high' | 'medium';
}

interface SECFilingsFilterPanelProps {
  isOpen: boolean;
  onClose: () => void;
  filters: SECFilters;
  onFiltersChange: (filters: SECFilters) => void;
  onApply: (filters?: SECFilters) => void;
  onReset: () => void;
}

// Derived from EIGHT_K_GROUPS (cast to string[] for TS compatibility)
const CRITICAL_8K_ITEMS = [...(EIGHT_K_GROUPS.distress.items as readonly string[]), '2.02', '1.05', '5.01'];
const HIGH_8K_ITEMS = [
  ...(EIGHT_K_GROUPS.deals.items as readonly string[]), 
  ...(EIGHT_K_GROUPS.dilution.items as readonly string[]), 
  ...(EIGHT_K_GROUPS.management.items as readonly string[])
];

export function SECFilingsFilterPanel({
  isOpen,
  onClose,
  filters,
  onFiltersChange,
  onApply,
  onReset,
}: SECFilingsFilterPanelProps) {
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';
  
  const [activeTab, setActiveTab] = useState<'categories' | 'forms' | 'items' | 'dates'>('categories');

  const updateFilterAndApply = useCallback(<K extends keyof SECFilters>(key: K, value: SECFilters[K]) => {
    const newFilters = { ...filters, [key]: value };
    onFiltersChange(newFilters);
    // Apply immediately with the new filters
    setTimeout(() => onApply(newFilters), 50);
  }, [filters, onFiltersChange, onApply]);

  const toggleArrayItem = useCallback((key: 'categories' | 'formTypes' | 'items8K', item: string) => {
    const current = filters[key];
    const updated = current.includes(item)
      ? current.filter(i => i !== item)
      : [...current, item];
    updateFilterAndApply(key, updated);
  }, [filters, updateFilterAndApply]);

  const selectAllInCategory = useCallback((categoryKey: string) => {
    const category = FILING_CATEGORIES[categoryKey as keyof typeof FILING_CATEGORIES];
    if (category) {
      const newTypes = [...new Set([...filters.formTypes, ...category.types])];
      updateFilterAndApply('formTypes', newTypes);
    }
  }, [filters.formTypes, updateFilterAndApply]);

  const handleReset = useCallback(() => {
    onReset();
  }, [onReset]);

  if (!isOpen) return null;

  const activeFiltersCount = 
    filters.categories.length + 
    filters.formTypes.length + 
    filters.items8K.length + 
    (filters.dateFrom ? 1 : 0) + 
    (filters.dateTo ? 1 : 0) +
    (filters.importanceLevel !== 'all' ? 1 : 0);

  return (
    <div className={`absolute inset-0 z-50 bg-white flex flex-col ${fontClass}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">
            Filters
          </span>
          {activeFiltersCount > 0 && (
            <span className="text-[10px] text-slate-500">
              {activeFiltersCount} active
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            className="flex items-center gap-1 px-2 py-1 text-[10px] text-slate-500 hover:text-slate-700 transition-colors"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200">
        {[
          { id: 'categories', label: 'Categories', count: filters.categories.length },
          { id: 'forms', label: 'Forms', count: filters.formTypes.length },
          { id: 'items', label: '8-K Items', count: filters.items8K.length },
          { id: 'dates', label: 'Dates', count: (filters.dateFrom || filters.dateTo) ? 1 : 0 },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-[10px] border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-600 text-blue-600 font-medium'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className="text-[9px] text-slate-400">
                ({tab.count})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-3">
        {/* Categories Tab */}
        {activeTab === 'categories' && (
          <div className="space-y-2">
            <p className="text-[10px] text-slate-400 mb-3">
              Select categories to filter by related form types
            </p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(FILING_CATEGORIES).map(([key, category]) => {
                const isSelected = filters.categories.includes(key);
                return (
                  <button
                    key={key}
                    onClick={() => toggleArrayItem('categories', key)}
                    className={`text-left p-2 rounded border-2 transition-all ${
                      isSelected
                        ? 'border-blue-600'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <div className={`text-[11px] font-medium ${isSelected ? 'text-blue-600' : 'text-slate-700'}`}>
                      {category.label}
                    </div>
                    <div className="text-[9px] mt-0.5 text-slate-400">
                      {category.description}
                    </div>
                    <div className="text-[9px] mt-1 text-slate-400">
                      {category.types.slice(0, 4).join(', ')}{category.types.length > 4 ? '...' : ''}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Form Types Tab */}
        {activeTab === 'forms' && (
          <div className="space-y-3">
            <p className="text-[10px] text-slate-400">
              Select specific form types
            </p>
            
            {/* Quick selects */}
            <div className="flex flex-wrap gap-1 pb-2 border-b border-slate-100">
              {Object.entries(FILING_CATEGORIES).map(([key, cat]) => (
                <button
                  key={key}
                  onClick={() => selectAllInCategory(key)}
                  className="px-2 py-0.5 text-[9px] text-blue-600 hover:text-blue-700 border border-blue-200 hover:border-blue-300 rounded transition-colors"
                >
                  + {cat.label}
                </button>
              ))}
            </div>

            {/* Form type grid */}
            <div className="grid grid-cols-4 gap-1">
              {Object.entries(FORM_TYPE_INFO).map(([formType, info]) => {
                const isSelected = filters.formTypes.includes(formType);
                return (
                  <button
                    key={formType}
                    onClick={() => toggleArrayItem('formTypes', formType)}
                    title={info.description}
                    className={`px-2 py-1 text-[10px] rounded border-2 transition-all ${
                      isSelected
                        ? 'border-blue-600 text-blue-600 font-medium'
                        : 'border-slate-200 text-slate-500 hover:border-slate-300'
                    }`}
                  >
                    {formType}
                  </button>
                );
              })}
            </div>

            {/* Selected forms */}
            {filters.formTypes.length > 0 && (
              <div className="pt-2 border-t border-slate-100">
                <div className="text-[9px] text-slate-400 mb-1">Selected:</div>
                <div className="flex flex-wrap gap-1">
                  {filters.formTypes.map(ft => (
                    <span
                      key={ft}
                      onClick={() => toggleArrayItem('formTypes', ft)}
                      className="px-1.5 py-0.5 text-[9px] border-2 border-blue-600 text-blue-600 rounded cursor-pointer hover:border-blue-400 hover:text-blue-400"
                    >
                      {ft} x
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 8-K Items Tab */}
        {activeTab === 'items' && (
          <div className="space-y-3">
            <p className="text-[10px] text-slate-400">
              Filter 8-K filings by disclosure items
            </p>

            {/* Quick selects by group */}
            <div className="flex flex-wrap gap-1 pb-2 border-b border-slate-100">
              {Object.entries(EIGHT_K_GROUPS).map(([key, group]) => {
                const groupItems = group.items as readonly string[];
                const allSelected = groupItems.every(item => filters.items8K.includes(item));
                return (
                  <button
                    key={key}
                    onClick={() => {
                      if (allSelected) {
                        updateFilterAndApply('items8K', filters.items8K.filter(i => !groupItems.includes(i)));
                      } else {
                        updateFilterAndApply('items8K', [...new Set([...filters.items8K, ...groupItems])]);
                      }
                    }}
                    title={group.description}
                    className={`px-2 py-0.5 text-[9px] rounded border ${
                      allSelected
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'text-slate-600 border-slate-200 hover:border-slate-400'
                    }`}
                  >
                    {group.label}
                  </button>
                );
              })}
              <button
                onClick={() => updateFilterAndApply('items8K', [])}
                className="px-2 py-0.5 text-[9px] text-slate-400 hover:text-slate-600"
              >
                Clear
              </button>
            </div>

            {/* Items list */}
            <div className="space-y-1">
              {Object.entries(FORM_8K_ITEMS).map(([itemId, info]) => {
                const isSelected = filters.items8K.includes(itemId);
                return (
                  <button
                    key={itemId}
                    onClick={() => toggleArrayItem('items8K', itemId)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 text-left rounded border-2 transition-all ${
                      isSelected
                        ? 'border-blue-600'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <span className={`text-[10px] w-10 ${isSelected ? 'text-blue-600' : 'text-slate-400'}`}>
                      {itemId}
                    </span>
                    <span className={`text-[10px] flex-1 ${isSelected ? 'text-blue-600' : 'text-slate-600'}`}>
                      {info.description}
                    </span>
                    <span className="text-[8px] uppercase tracking-wider text-slate-400">
                      {info.importance}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Dates Tab */}
        {activeTab === 'dates' && (
          <div className="space-y-4">
            <p className="text-[10px] text-slate-400">
              Filter by date range
            </p>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] text-slate-500 mb-1">From</label>
                <input
                  type="date"
                  value={filters.dateFrom}
                  onChange={(e) => updateFilterAndApply('dateFrom', e.target.value)}
                  className="w-full px-2 py-1.5 text-xs border-2 border-slate-200 rounded focus:outline-none focus:border-blue-400"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-500 mb-1">To</label>
                <input
                  type="date"
                  value={filters.dateTo}
                  onChange={(e) => updateFilterAndApply('dateTo', e.target.value)}
                  className="w-full px-2 py-1.5 text-xs border-2 border-slate-200 rounded focus:outline-none focus:border-blue-400"
                />
              </div>
            </div>

            {/* Quick ranges */}
            <div className="pt-2 border-t border-slate-100">
              <div className="text-[10px] text-slate-500 mb-2">Quick</div>
              <div className="flex flex-wrap gap-1">
                {[
                  { label: 'Today', days: 0 },
                  { label: '7d', days: 7 },
                  { label: '30d', days: 30 },
                  { label: '90d', days: 90 },
                  { label: 'YTD', days: -1 },
                ].map(range => (
                  <button
                    key={range.label}
                    onClick={() => {
                      const today = new Date();
                      const toDate = today.toISOString().split('T')[0];
                      let fromDate: string;
                      if (range.days === -1) {
                        fromDate = `${today.getFullYear()}-01-01`;
                      } else if (range.days === 0) {
                        fromDate = toDate;
                      } else {
                        const from = new Date();
                        from.setDate(from.getDate() - range.days);
                        fromDate = from.toISOString().split('T')[0];
                      }
                      const newFilters = { ...filters, dateFrom: fromDate, dateTo: toDate };
                      onFiltersChange(newFilters);
                      setTimeout(() => onApply(newFilters), 50);
                    }}
                    className="px-2 py-1 text-[10px] text-blue-600 border-2 border-blue-200 hover:border-blue-400 rounded transition-colors"
                  >
                    {range.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Importance filter */}
            <div className="pt-3 border-t border-slate-100">
              <div className="text-[10px] text-slate-500 mb-2">Min Importance (8-K)</div>
              <div className="flex gap-1">
                {[
                  { value: 'all', label: 'All' },
                  { value: 'critical', label: 'Critical' },
                  { value: 'high', label: 'High+' },
                  { value: 'medium', label: 'Medium+' },
                ].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => updateFilterAndApply('importanceLevel', opt.value as SECFilters['importanceLevel'])}
                    className={`px-3 py-1 text-[10px] rounded border-2 transition-all ${
                      filters.importanceLevel === opt.value
                        ? 'border-blue-600 text-blue-600 font-medium'
                        : 'border-slate-200 text-slate-500 hover:border-slate-300'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      {activeFiltersCount > 0 && (
        <div className="px-3 py-2 border-t border-slate-200">
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-[9px] text-slate-400 mr-1">Active:</span>
            {filters.categories.map(cat => (
              <span key={cat} className="px-1.5 py-0.5 text-[9px] border border-blue-300 text-blue-600 rounded">
                {FILING_CATEGORIES[cat as keyof typeof FILING_CATEGORIES]?.label || cat}
              </span>
            ))}
            {filters.formTypes.slice(0, 5).map(ft => (
              <span key={ft} className="px-1.5 py-0.5 text-[9px] border border-blue-300 text-blue-600 rounded">
                {ft}
              </span>
            ))}
            {filters.formTypes.length > 5 && (
              <span className="text-[9px] text-slate-400">+{filters.formTypes.length - 5}</span>
            )}
            {filters.items8K.length > 0 && (
              <span className="px-1.5 py-0.5 text-[9px] border border-blue-300 text-blue-600 rounded">
                {filters.items8K.length} items
              </span>
            )}
            {(filters.dateFrom || filters.dateTo) && (
              <span className="px-1.5 py-0.5 text-[9px] border border-blue-300 text-blue-600 rounded">
                {filters.dateFrom || '*'} - {filters.dateTo || '*'}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
