/**
 * HeatmapTreemap Component
 * 
 * Professional treemap visualization using Plotly.js
 * Optimized for performance with React.memo and memoization.
 */

'use client';

import React, { useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import type { HeatmapData, ColorMetric, SizeMetric } from './useHeatmapData';
import { useHeatmapWorker } from './useHeatmapWorker';

// Dynamic import for Plotly (SSR-incompatible)
const Plot = dynamic(
  () => import('react-plotly.js').then((mod) => mod.default),
  { 
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        Loading chart...
      </div>
    )
  }
);

interface HeatmapTreemapProps {
  data: HeatmapData;
  colorMetric: ColorMetric;
  sizeMetric: SizeMetric;
  onTickerClick?: (symbol: string) => void;
  onSectorClick?: (sector: string) => void;
  viewLevel: 'market' | 'sector';
  selectedSector?: string | null;
  height?: number;
  width?: number;
}

function HeatmapTreemap({
  data,
  colorMetric,
  sizeMetric,
  onTickerClick,
  onSectorClick,
  viewLevel,
  selectedSector,
  height = 600,
  width,
}: HeatmapTreemapProps) {
  // Process data
  const { treemapData } = useHeatmapWorker({
    data,
    colorMetric,
    sizeMetric,
    viewLevel,
    selectedSector: selectedSector || null,
  });

  // Handle click events
  const handleClick = useCallback((event: any) => {
    if (!event.points?.[0]?.customdata) return;
    
    const customData = event.points[0].customdata;
    
    if (customData.type === 'ticker' && onTickerClick) {
      onTickerClick(customData.symbol);
    } else if (customData.type === 'sector' && onSectorClick) {
      onSectorClick(customData.sector);
    }
  }, [onTickerClick, onSectorClick]);

  // Memoize Plotly data
  const plotlyData = useMemo(() => {
    if (!treemapData) return null;
    
    return [{
      type: 'treemap' as const,
      ids: treemapData.ids,
      labels: treemapData.labels,
      parents: treemapData.parents,
      values: treemapData.values,
      customdata: treemapData.customdata,
      marker: {
        colors: treemapData.colors,
        line: { color: '#e2e8f0', width: 1 },
      },
      textinfo: 'label+text',
      texttemplate: '<b>%{label}</b><br>%{customdata.change:.2f}%',
      textfont: { family: 'Inter, system-ui, sans-serif', size: 12, color: '#ffffff' },
      insidetextfont: { family: 'Inter, system-ui, sans-serif', size: 11, color: '#ffffff' },
      outsidetextfont: { family: 'Inter, system-ui, sans-serif', size: 10, color: '#64748b' },
      hovertemplate: 
        '<b>%{label}</b> - %{customdata.name}<br>' +
        'Price: $%{customdata.price:.2f}<br>' +
        'Change: %{customdata.change:.2f}%<br>' +
        'Mkt Cap: $%{customdata.market_cap:,.0f}<br>' +
        'RVOL: %{customdata.rvol:.1f}x<br>' +
        '<extra>%{customdata.sector}</extra>',
      pathbar: { 
        visible: true, 
        side: 'top', 
        thickness: 24, 
        textfont: { size: 12, color: '#334155' }, 
        edgeshape: '>' 
      },
      tiling: { packing: 'squarify', pad: 3 },
      maxdepth: 2,
      branchvalues: 'remainder',
    }];
  }, [treemapData]);

  // Memoize layout
  const plotlyLayout = useMemo(() => ({
    margin: { t: 0, l: 0, r: 0, b: 0 },
    paper_bgcolor: '#ffffff',
    plot_bgcolor: '#ffffff',
    font: { family: 'Inter, system-ui, sans-serif', color: '#334155' },
    autosize: false,
    width: width || undefined,
    height: height,
  }), [width, height]);

  // Static config
  const plotlyConfig = useMemo(() => ({
    displayModeBar: false,
    responsive: false,
    displaylogo: false,
    staticPlot: false,
  }), []);

  // No data state
  if (!treemapData || !plotlyData) {
    return (
      <div 
        className="flex items-center justify-center bg-white text-slate-400"
        style={{ height, width: width || '100%' }}
      >
        No data available
      </div>
    );
  }

  return (
    <div 
      className="w-full h-full bg-white"
      style={{ width: width || '100%', height }}
    >
      <Plot
        data={plotlyData as any}
        layout={plotlyLayout}
        config={plotlyConfig}
        style={{ width: '100%', height: '100%' }}
        onClick={handleClick}
      />
    </div>
  );
}

export default React.memo(HeatmapTreemap);
