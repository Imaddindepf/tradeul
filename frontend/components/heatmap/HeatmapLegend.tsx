/**
 * HeatmapLegend Component
 * 
 * Displays the color scale legend for the current metric.
 * Minimalist design matching app style.
 */

'use client';

import React, { memo } from 'react';
import type { ColorMetric } from './useHeatmapData';

interface HeatmapLegendProps {
  metric: ColorMetric;
}

// Get legend config based on metric
const getLegendConfig = (metric: ColorMetric) => {
  switch (metric) {
    case 'change_percent':
    case 'chg_5min':
    case 'price_vs_vwap':
      return {
        leftLabel: metric === 'chg_5min' ? '-5%' : metric === 'price_vs_vwap' ? '-3%' : '-10%',
        rightLabel: metric === 'chg_5min' ? '+5%' : metric === 'price_vs_vwap' ? '+3%' : '+10%',
        gradient: 'linear-gradient(to right, #dc2626, #fecaca, #f5f5f5, #bbf7d0, #16a34a)',
        title: metric === 'change_percent' ? 'Day Change' : metric === 'chg_5min' ? '5min Change' : 'vs VWAP',
      };
    case 'rvol':
      return {
        leftLabel: '0x',
        rightLabel: '5x+',
        gradient: 'linear-gradient(to right, #fef3c7, #fbbf24, #f97316, #dc2626)',
        title: 'Rel. Volume',
      };
    default:
      return {
        leftLabel: '-',
        rightLabel: '+',
        gradient: 'linear-gradient(to right, #dc2626, #16a34a)',
        title: '',
      };
  }
};

function HeatmapLegend({ metric }: HeatmapLegendProps) {
  const config = getLegendConfig(metric);
  
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[9px] text-slate-400">{config.leftLabel}</span>
      <div
        className="w-20 h-2 rounded-sm"
        style={{ background: config.gradient }}
        title={config.title}
      />
      <span className="text-[9px] text-slate-400">{config.rightLabel}</span>
    </div>
  );
}

export default memo(HeatmapLegend);
