'use client';

import { memo, useRef } from 'react';
import dynamic from 'next/dynamic';
import type { PlotlyConfig } from './types';
import { useThemeKey } from '@/hooks/useThemeKey';

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
  const themeKey = useThemeKey();
  
  // Use backend height if provided in layout, otherwise fallback
  const backendHeight = plotlyConfig.layout?.height;
  const chartHeight: number = typeof backendHeight === 'number' 
    ? backendHeight 
    : (typeof height === 'number' ? height : 500);

  const _v = (name: string, fb: string) =>
    typeof document !== 'undefined'
      ? getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb
      : fb;

  // Merge layout - preserve backend config, only add minimal defaults
  const baseLayout = plotlyConfig.layout || {};
  const layout = {
    ...baseLayout,
    autosize: true,
    height: chartHeight,
    margin: baseLayout.margin || { t: 50, b: 40, l: 50, r: 50 },
    paper_bgcolor: baseLayout.paper_bgcolor || _v('--color-bg', '#ffffff'),
    plot_bgcolor: baseLayout.plot_bgcolor || _v('--color-surface', '#f9fafb'),
    font: {
      family: 'system-ui, -apple-system, sans-serif',
      size: 11,
      color: _v('--color-fg', '#374151'),
      ...(baseLayout.font || {})
    },
    title: baseLayout.title || {
      text: title,
      font: { size: 14, color: _v('--color-fg', '#1f2937') }
    },
    legend: {
      font: { color: _v('--color-muted-fg', '#6b7280'), size: 10 },
      bgcolor: 'rgba(0,0,0,0)',
      ...(baseLayout.legend || {})
    },
    xaxis: {
      gridcolor: _v('--color-border', 'rgba(229,231,235,0.5)'),
      zerolinecolor: _v('--color-border', 'rgba(209,213,219,0.5)'),
      tickfont: { color: _v('--color-muted-fg', '#6b7280'), size: 10 },
      ...(typeof baseLayout.xaxis === 'object' ? baseLayout.xaxis : {})
    },
    yaxis: {
      gridcolor: _v('--color-border', 'rgba(229,231,235,0.5)'),
      zerolinecolor: _v('--color-border', 'rgba(209,213,219,0.5)'),
      tickfont: { color: _v('--color-muted-fg', '#6b7280'), size: 10 },
      ...(typeof baseLayout.yaxis === 'object' ? baseLayout.yaxis : {})
    },
    xaxis2: baseLayout.xaxis2,
    xaxis3: baseLayout.xaxis3,
    yaxis2: baseLayout.yaxis2,
    yaxis3: baseLayout.yaxis3,
    shapes: baseLayout.shapes,
    hoverlabel: baseLayout.hoverlabel || {
      bgcolor: _v('--color-surface', '#ffffff'),
      bordercolor: _v('--color-border', '#e5e7eb'),
      font: { color: _v('--color-fg', '#1f2937') }
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
      className="w-full rounded-lg border border-border bg-surface overflow-hidden shadow-sm"
    >
      <Plot
        key={themeKey}
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
