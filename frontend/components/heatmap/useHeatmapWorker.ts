/**
 * Heatmap Data Processing Hook
 * 
 * Processes heatmap data for Plotly treemap visualization.
 * Uses useMemo for efficient memoization.
 */

import { useMemo } from 'react';
import type { HeatmapData, HeatmapTicker, ColorMetric, SizeMetric } from './useHeatmapData';

interface TreemapData {
  ids: string[];
  labels: string[];
  parents: string[];
  values: number[];
  colors: string[];
  customdata: any[];
}

interface UseHeatmapWorkerOptions {
  data: HeatmapData | null;
  colorMetric: ColorMetric;
  sizeMetric: SizeMetric;
  viewLevel: 'market' | 'sector';
  selectedSector: string | null;
}

interface UseHeatmapWorkerReturn {
  treemapData: TreemapData | null;
  isProcessing: boolean;
}

// Color functions
function getChangeColor(value: number): string {
  const clamped = Math.max(-10, Math.min(10, value));
  if (clamped >= 0) {
    const intensity = Math.min(clamped / 10, 1);
    return `rgb(${Math.round(30 - intensity * 30)}, ${Math.round(30 + intensity * 170)}, ${Math.round(30 - intensity * 30)})`;
  } else {
    const intensity = Math.min(Math.abs(clamped) / 10, 1);
    return `rgb(${Math.round(30 + intensity * 170)}, ${Math.round(30 - intensity * 30)}, ${Math.round(30 - intensity * 30)})`;
  }
}

function getRvolColor(value: number): string {
  if (value >= 1) {
    const intensity = Math.min((value - 1) / 4, 1);
    return `rgb(${Math.round(50 - intensity * 50)}, ${Math.round(100 + intensity * 50)}, ${Math.round(150 + intensity * 100)})`;
  }
  const intensity = Math.min((1 - value), 1);
  return `rgb(${Math.round(200 + intensity * 50)}, ${Math.round(150 + intensity * 50)}, 50)`;
}

function getTickerColor(ticker: HeatmapTicker, metric: ColorMetric): string {
  switch (metric) {
    case 'change_percent': return getChangeColor(ticker.change_percent || 0);
    case 'chg_5min': return getChangeColor((ticker.chg_5min || 0) * 2);
    case 'rvol': return getRvolColor(ticker.rvol || 1);
    case 'price_vs_vwap': return getChangeColor(ticker.price_vs_vwap || 0);
    default: return getChangeColor(ticker.change_percent || 0);
  }
}

export function useHeatmapWorker({
  data,
  colorMetric,
  sizeMetric,
  viewLevel,
  selectedSector,
}: UseHeatmapWorkerOptions): UseHeatmapWorkerReturn {

  const treemapData = useMemo(() => {
    if (!data?.sectors?.length) {
      return null;
    }

    const start = performance.now();

    const ids: string[] = [];
    const labels: string[] = [];
    const parents: string[] = [];
    const values: number[] = [];
    const colors: string[] = [];
    const customdata: any[] = [];

    const sectorsToShow = viewLevel === 'sector' && selectedSector
      ? data.sectors.filter(s => s.sector === selectedSector)
      : data.sectors;

    for (const sector of sectorsToShow) {
      // Add tickers
      for (const industry of sector.industries) {
        for (const ticker of industry.tickers) {
          let sizeValue: number;
          switch (sizeMetric) {
            case 'volume_today': sizeValue = (ticker.volume_today || 1) / 1e6; break;
            case 'dollar_volume': sizeValue = (ticker.dollar_volume || 1) / 1e9; break;
            default: sizeValue = (ticker.market_cap || 1) / 1e9;
          }

          ids.push(ticker.symbol);
          labels.push(ticker.symbol);
          parents.push(sector.sector);
          values.push(Math.max(sizeValue, 0.0001));
          colors.push(getTickerColor(ticker, colorMetric));
          customdata.push({
            type: 'ticker',
            symbol: ticker.symbol,
            name: ticker.name || ticker.symbol,
            sector: sector.sector,
            industry: industry.industry,
            price: ticker.price || 0,
            change: ticker.change_percent || 0,
            market_cap: ticker.market_cap || 0,
            volume: ticker.volume_today || 0,
            rvol: ticker.rvol || 0,
            chg_5min: ticker.chg_5min || 0,
            price_vs_vwap: ticker.price_vs_vwap || 0,
            logo_url: ticker.logo_url,
          });
        }
      }

      // Add sector
      ids.push(sector.sector);
      labels.push(sector.sector);
      parents.push('');
      values.push(0);
      colors.push(sector.color);
      customdata.push({
        type: 'sector',
        symbol: sector.sector,
        sector: sector.sector,
        name: sector.sector,
        ticker_count: sector.ticker_count,
        market_cap: sector.total_market_cap || 0,
        change: sector.avg_change_percent || 0,
        price: 0,
        volume: sector.total_volume || 0,
        rvol: 0,
        chg_5min: 0,
        price_vs_vwap: 0,
        industry: '',
      });
    }

    const duration = performance.now() - start;
    console.log(`[Heatmap] Processed ${ids.length} items in ${duration.toFixed(1)}ms`);

    return { ids, labels, parents, values, colors, customdata };
  }, [data, colorMetric, sizeMetric, viewLevel, selectedSector]);

  return { treemapData, isProcessing: false };
}
