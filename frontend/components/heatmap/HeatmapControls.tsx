/**
 * HeatmapControls Component
 * 
 * Filter and configuration controls for the heatmap.
 * Minimalist light theme matching app style.
 */

'use client';

import React, { useCallback, memo } from 'react';
import type { HeatmapFilters, ColorMetric, SizeMetric } from './useHeatmapData';

interface HeatmapControlsProps {
  filters: HeatmapFilters;
  onFiltersChange: (filters: Partial<HeatmapFilters>) => void;
  availableSectors?: string[];
  isCompact?: boolean;
}

// Market cap presets
const MARKET_CAP_PRESETS = [
  { label: 'All', value: null },
  { label: '100M+', value: 100_000_000 },
  { label: '500M+', value: 500_000_000 },
  { label: '1B+', value: 1_000_000_000 },
  { label: '10B+', value: 10_000_000_000 },
  { label: '50B+', value: 50_000_000_000 },
];

// Color metric options
const COLOR_METRICS: { value: ColorMetric; label: string; description: string }[] = [
  { value: 'change_percent', label: 'Day', description: 'Change % from previous close' },
  { value: 'chg_5min', label: '5min', description: 'Change % in last 5 minutes' },
  { value: 'rvol', label: 'RVOL', description: 'Volume relative to average' },
  { value: 'price_vs_vwap', label: 'VWAP', description: 'Distance from VWAP' },
];

// Size metric options
const SIZE_METRICS: { value: SizeMetric; label: string }[] = [
  { value: 'market_cap', label: 'Mkt Cap' },
  { value: 'volume_today', label: 'Volume' },
  { value: 'dollar_volume', label: '$ Vol' },
];

function HeatmapControls({
  filters,
  onFiltersChange,
  availableSectors = [],
  isCompact = false,
}: HeatmapControlsProps) {
  
  const handleColorMetricChange = useCallback((metric: ColorMetric) => {
    onFiltersChange({ metric });
  }, [onFiltersChange]);
  
  const handleSizeMetricChange = useCallback((sizeBy: SizeMetric) => {
    onFiltersChange({ sizeBy });
  }, [onFiltersChange]);
  
  const handleMarketCapChange = useCallback((value: number | null) => {
    onFiltersChange({ minMarketCap: value });
  }, [onFiltersChange]);
  
  const handleSectorToggle = useCallback((sector: string) => {
    const currentSectors = filters.sectors || [];
    let newSectors: string[] | null;
    
    if (currentSectors.includes(sector)) {
      newSectors = currentSectors.filter(s => s !== sector);
      if (newSectors.length === 0) newSectors = null;
    } else {
      newSectors = [...currentSectors, sector];
    }
    
    onFiltersChange({ sectors: newSectors });
  }, [filters.sectors, onFiltersChange]);
  
  const handleClearSectors = useCallback(() => {
    onFiltersChange({ sectors: null });
  }, [onFiltersChange]);
  
  if (isCompact) {
    return (
      <div className="flex items-center gap-3 text-[10px]">
        {/* Color Metric */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400">Color:</span>
          <select
            value={filters.metric}
            onChange={(e) => handleColorMetricChange(e.target.value as ColorMetric)}
            className="bg-white border border-slate-200 rounded px-1.5 py-0.5 text-slate-700 focus:outline-none focus:border-blue-500 text-[10px]"
          >
            {COLOR_METRICS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
        
        {/* Size Metric */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400">Size:</span>
          <select
            value={filters.sizeBy}
            onChange={(e) => handleSizeMetricChange(e.target.value as SizeMetric)}
            className="bg-white border border-slate-200 rounded px-1.5 py-0.5 text-slate-700 focus:outline-none focus:border-blue-500 text-[10px]"
          >
            {SIZE_METRICS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
        
        {/* Market Cap */}
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400">Cap:</span>
          <select
            value={filters.minMarketCap?.toString() || ''}
            onChange={(e) => handleMarketCapChange(e.target.value ? parseInt(e.target.value) : null)}
            className="bg-white border border-slate-200 rounded px-1.5 py-0.5 text-slate-700 focus:outline-none focus:border-blue-500 text-[10px]"
          >
            {MARKET_CAP_PRESETS.map(p => (
              <option key={p.label} value={p.value?.toString() || ''}>{p.label}</option>
            ))}
          </select>
        </div>
      </div>
    );
  }
  
  return (
    <div className="px-3 py-2 bg-white border-b border-slate-200">
      {/* Row 1: Metrics */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Color Metric */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-medium">Color:</span>
          <div className="flex rounded overflow-hidden border border-slate-200">
            {COLOR_METRICS.map(m => (
              <button
                key={m.value}
                onClick={() => handleColorMetricChange(m.value)}
                className={`px-2 py-1 text-[10px] font-medium transition-colors ${
                  filters.metric === m.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
                title={m.description}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
        
        {/* Size Metric */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-medium">Size:</span>
          <div className="flex rounded overflow-hidden border border-slate-200">
            {SIZE_METRICS.map(m => (
              <button
                key={m.value}
                onClick={() => handleSizeMetricChange(m.value)}
                className={`px-2 py-1 text-[10px] font-medium transition-colors ${
                  filters.sizeBy === m.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
        
        {/* Market Cap Filter */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-medium">Min Cap:</span>
          <div className="flex rounded overflow-hidden border border-slate-200">
            {MARKET_CAP_PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => handleMarketCapChange(p.value)}
                className={`px-2 py-1 text-[10px] font-medium transition-colors ${
                  filters.minMarketCap === p.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        
        {/* Sector Filter (inline) */}
        {availableSectors.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400 font-medium">Sectors:</span>
            <div className="flex flex-wrap gap-1">
              {filters.sectors && filters.sectors.length > 0 && (
                <button
                  onClick={handleClearSectors}
                  className="px-1.5 py-0.5 text-[9px] font-medium rounded bg-slate-100 text-slate-500 hover:bg-slate-200"
                >
                  Clear
                </button>
              )}
              {availableSectors.slice(0, 6).map(sector => {
                const isSelected = filters.sectors?.includes(sector);
                const shortName = sector.length > 10 ? sector.slice(0, 8) + '..' : sector;
                return (
                  <button
                    key={sector}
                    onClick={() => handleSectorToggle(sector)}
                    className={`px-1.5 py-0.5 text-[9px] font-medium rounded transition-colors ${
                      isSelected
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-50 text-slate-500 hover:bg-slate-100'
                    }`}
                    title={sector}
                  >
                    {shortName}
                  </button>
                );
              })}
              {availableSectors.length > 6 && (
                <span className="px-1.5 py-0.5 text-[9px] text-slate-400">
                  +{availableSectors.length - 6}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default memo(HeatmapControls);
