'use client';

import { memo, useRef } from 'react';
import dynamic from 'next/dynamic';
import type { PlotlyConfig } from './types';

// Importar Plotly de forma dinamica para evitar SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface ChartProps {
  title: string;
  plotlyConfig: PlotlyConfig;
  height?: number | string;
}

export const Chart = memo(function Chart({
  title,
  plotlyConfig,
  height
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Use backend height if provided in layout, otherwise fallback
  const backendHeight = plotlyConfig.layout?.height;
  const chartHeight: number = typeof backendHeight === 'number' 
    ? backendHeight 
    : (typeof height === 'number' ? height : 500);

  // Merge layout - preserve backend config, only add minimal defaults
  const baseLayout = plotlyConfig.layout || {};
  const layout = {
    ...baseLayout,
    autosize: true,
    height: chartHeight,
    // Preserve backend margins if provided, otherwise use defaults
    margin: baseLayout.margin || { t: 50, b: 40, l: 50, r: 50 },
    paper_bgcolor: baseLayout.paper_bgcolor || 'rgba(255,255,255,1)',
    plot_bgcolor: baseLayout.plot_bgcolor || 'rgba(249,250,251,1)',
    font: {
      family: 'system-ui, -apple-system, sans-serif',
      size: 11,
      color: '#374151',
      ...(baseLayout.font || {})
    },
    // Only set title if not provided by backend
    title: baseLayout.title || {
      text: title,
      font: { size: 14, color: '#1f2937' }
    },
    // CRITICAL: Preserve backend legend config (position, orientation)
    legend: {
      font: { color: '#6b7280', size: 10 },
      bgcolor: 'rgba(255,255,255,0)',
      ...(baseLayout.legend || {})
    },
    // Preserve all axis configs from backend
    xaxis: {
      gridcolor: 'rgba(229,231,235,0.5)',
      zerolinecolor: 'rgba(209,213,219,0.5)',
      tickfont: { color: '#6b7280', size: 10 },
      ...(typeof baseLayout.xaxis === 'object' ? baseLayout.xaxis : {})
    },
    yaxis: {
      gridcolor: 'rgba(229,231,235,0.5)',
      zerolinecolor: 'rgba(209,213,219,0.5)',
      tickfont: { color: '#6b7280', size: 10 },
      ...(typeof baseLayout.yaxis === 'object' ? baseLayout.yaxis : {})
    },
    // Preserve additional axes for multi-subplot charts
    xaxis2: baseLayout.xaxis2,
    xaxis3: baseLayout.xaxis3,
    yaxis2: baseLayout.yaxis2,
    yaxis3: baseLayout.yaxis3,
    // Preserve shapes (subplot separators)
    shapes: baseLayout.shapes,
    hoverlabel: baseLayout.hoverlabel || {
      bgcolor: '#ffffff',
      bordercolor: '#e5e7eb',
      font: { color: '#1f2937' }
    },
    hovermode: baseLayout.hovermode || 'x unified'
  };

  // Plotly config
  const config = {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: [
      'pan2d',
      'select2d',
      'lasso2d',
      'autoScale2d',
      'hoverClosestCartesian',
      'hoverCompareCartesian',
      'toggleSpikelines'
    ],
    responsive: true
  };

  return (
    <div
      ref={containerRef}
      className="w-full rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm"
    >
      <Plot
        data={plotlyConfig.data as any}
        layout={layout as any}
        config={config as any}
        className="w-full"
        style={{ width: '100%', height: chartHeight }}
        useResizeHandler
      />
    </div>
  );
});
