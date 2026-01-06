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
  height = 300
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Altura responsive - usa el valor dado o calcula basado en viewport
  const chartHeight = typeof height === 'number' ? Math.min(height, 400) : height;

  // Configuracion de layout con tema azul/blanco
  const baseLayout = plotlyConfig.layout || {};
  const layout = {
    ...baseLayout,
    autosize: true,
    height: chartHeight,
    margin: { t: 40, b: 40, l: 50, r: 20 },
    paper_bgcolor: 'rgba(255,255,255,1)',
    plot_bgcolor: 'rgba(249,250,251,1)', // gray-50
    font: {
      family: 'system-ui, -apple-system, sans-serif',
      size: 12,
      color: '#374151' // gray-700
    },
    title: {
      text: title,
      font: {
        size: 14,
        color: '#1f2937' // gray-800
      }
    },
    xaxis: {
      ...(typeof baseLayout.xaxis === 'object' ? baseLayout.xaxis : {}),
      gridcolor: 'rgba(229,231,235,0.8)', // gray-200
      zerolinecolor: 'rgba(209,213,219,1)', // gray-300
      tickfont: { color: '#6b7280' } // gray-500
    },
    yaxis: {
      ...(typeof baseLayout.yaxis === 'object' ? baseLayout.yaxis : {}),
      gridcolor: 'rgba(229,231,235,0.8)',
      zerolinecolor: 'rgba(209,213,219,1)',
      tickfont: { color: '#6b7280' }
    },
    legend: {
      font: { color: '#6b7280' },
      bgcolor: 'rgba(255,255,255,0)'
    },
    hoverlabel: {
      bgcolor: '#ffffff',
      bordercolor: '#e5e7eb', // gray-200
      font: { color: '#1f2937' } // gray-800
    }
  };

  // Configuracion de Plotly
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
      className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm"
    >
      <Plot
        data={plotlyConfig.data as any}
        layout={layout as any}
        config={config as any}
        style={{ width: '100%', height: chartHeight }}
        useResizeHandler
      />
    </div>
  );
});
