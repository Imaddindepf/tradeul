'use client';

import { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  createSeriesMarkers,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
  type UTCTimestamp,
  type SeriesMarker,
} from 'lightweight-charts';
import { LineChart, CandlestickChart, ZoomIn, ZoomOut, RotateCcw, X } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// ============================================================================
// Types
// ============================================================================

interface OHLCBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface InsiderTransaction {
  date: string;
  code: string;
  shares: number;
  value: number;
  insider_name?: string;
}

type ChartType = 'line' | 'candlestick';

interface TransactionGroup {
  date: string;
  timestamp: UTCTimestamp;
  transactions: InsiderTransaction[];
  totalBuyShares: number;
  totalSellShares: number;
  totalOtherShares: number;
  price: number;
}

// ============================================================================
// Constants
// ============================================================================

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

const TX_LABELS: Record<string, string> = {
  'P': 'BUY', 'S': 'SELL', 'M': 'EXERCISE', 'A': 'GRANT', 'F': 'TAX', 'G': 'GIFT', 'J': 'TRANSFER'
};

const TX_COLORS: Record<string, string> = {
  'P': '#10b981', 'S': '#ef4444', 'M': '#8b5cf6', 'A': '#3b82f6',
  'F': '#f59e0b', 'G': '#06b6d4', 'J': '#64748b'
};

const getVar = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function getChartColors() {
  return {
    background: getVar('--color-bg') || '#ffffff',
    gridColor: getVar('--color-border-subtle') || '#f1f5f9',
    borderColor: getVar('--color-border') || '#e2e8f0',
    textColor: getVar('--color-muted-fg') || '#64748b',
    upColor: '#10b981',
    downColor: '#ef4444',
    lineColor: '#3b82f6',
  };
}

const CHART_COLORS = {
  background: '#ffffff',
  gridColor: '#f1f5f9',
  borderColor: '#e2e8f0',
  textColor: '#64748b',
  upColor: '#10b981',
  downColor: '#ef4444',
  lineColor: '#3b82f6',
};

// ============================================================================
// Helpers
// ============================================================================

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(0)}K`;
  return num.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function formatCurrency(num: number): string {
  if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `$${(num / 1_000).toFixed(1)}K`;
  return `$${num.toFixed(2)}`;
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  } catch {
    return dateStr;
  }
}

function dateToTimestamp(dateStr: string): UTCTimestamp {
  const d = new Date(dateStr);
  return Math.floor(d.getTime() / 1000) as UTCTimestamp;
}

// ============================================================================
// Props
// ============================================================================

interface InsiderChartContentProps {
  ticker: string;
  priceData: OHLCBar[];
  transactions: InsiderTransaction[];
}

// ============================================================================
// Component
// ============================================================================

export function InsiderChartContent({ ticker, priceData, transactions }: InsiderChartContentProps) {
  const font = useUserPreferencesStore(selectFont);
  const fontClass = FONT_CLASSES[font] || 'font-jetbrains-mono';

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<any> | null>(null);
  const markersRef = useRef<any>(null);

  const [chartType, setChartType] = useState<ChartType>('line');
  const [selectedGroup, setSelectedGroup] = useState<TransactionGroup | null>(null);

  // Convert price data to chart format
  const chartData = useMemo(() => {
    return priceData
      .map(bar => ({
        time: dateToTimestamp(bar.date),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
  }, [priceData]);

  // Group transactions by date with price info
  const transactionGroups = useMemo((): TransactionGroup[] => {
    const byDate = new Map<string, InsiderTransaction[]>();
    transactions.forEach(tx => {
      const existing = byDate.get(tx.date) || [];
      existing.push(tx);
      byDate.set(tx.date, existing);
    });

    const groups: TransactionGroup[] = [];
    byDate.forEach((txs, date) => {
      const bar = priceData.find(b => b.date === date);
      if (!bar) return;

      const buys = txs.filter(t => t.code === 'P');
      const sells = txs.filter(t => t.code === 'S');
      const others = txs.filter(t => !['P', 'S'].includes(t.code));

      groups.push({
        date,
        timestamp: dateToTimestamp(date),
        transactions: txs,
        totalBuyShares: buys.reduce((sum, t) => sum + t.shares, 0),
        totalSellShares: sells.reduce((sum, t) => sum + t.shares, 0),
        totalOtherShares: others.reduce((sum, t) => sum + t.shares, 0),
        price: bar.close,
      });
    });

    return groups.sort((a, b) => (a.timestamp as number) - (b.timestamp as number));
  }, [transactions, priceData]);

  // Create markers - simplified text-only style
  const markers = useMemo((): SeriesMarker<Time>[] => {
    const result: SeriesMarker<Time>[] = [];

    transactionGroups.forEach(group => {
      // Only show BUY markers (green, below bar) - NO TEXT
      if (group.totalBuyShares > 0) {
        result.push({
          time: group.timestamp,
          position: 'belowBar',
          color: '#10b981',
          shape: 'arrowUp',
          size: 1,
        });
      }

      // Only show SELL markers (red, above bar) - NO TEXT
      if (group.totalSellShares > 0) {
        result.push({
          time: group.timestamp,
          position: 'aboveBar',
          color: '#ef4444',
          shape: 'arrowDown',
          size: 1,
        });
      }

      // Show OTHER transactions with circle - NO TEXT
      if (group.totalOtherShares > 0 && group.totalBuyShares === 0 && group.totalSellShares === 0) {
        result.push({
          time: group.timestamp,
          position: 'aboveBar',
          color: '#64748b',
          shape: 'circle',
          size: 0.8,
        });
      }
    });

    return result.sort((a, b) => (a.time as number) - (b.time as number));
  }, [transactionGroups]);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const colors = getChartColors();
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.textColor,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: colors.gridColor, style: LineStyle.Dotted },
        horzLines: { color: colors.gridColor, style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: colors.textColor,
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#3b82f6',
        },
        horzLine: {
          color: colors.textColor,
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#3b82f6',
        },
      },
      rightPriceScale: {
        borderColor: colors.borderColor,
        scaleMargins: { top: 0.15, bottom: 0.15 },
      },
      timeScale: {
        borderColor: colors.borderColor,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 3,
        minBarSpacing: 1,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    chartRef.current = chart;

    // Handle click on chart to find nearest transaction
    chart.subscribeClick((param) => {
      if (!param.time) {
        setSelectedGroup(null);
        return;
      }

      const clickedTime = param.time as number;
      // Find closest transaction group
      const closest = transactionGroups.reduce((prev, curr) => {
        const prevDiff = Math.abs((prev.timestamp as number) - clickedTime);
        const currDiff = Math.abs((curr.timestamp as number) - clickedTime);
        return currDiff < prevDiff ? curr : prev;
      }, transactionGroups[0]);

      // Only select if within 3 days
      if (closest && Math.abs((closest.timestamp as number) - clickedTime) < 3 * 24 * 60 * 60) {
        setSelectedGroup(closest);
      } else {
        setSelectedGroup(null);
      }
    });

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(chartContainerRef.current);
    handleResize();

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [transactionGroups]);

  // Re-apply chart colors when theme changes (dark ↔ light)
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const chart = chartRef.current;
      if (!chart) return;
      const c = getChartColors();
      chart.applyOptions({
        layout: { background: { type: ColorType.Solid, color: c.background }, textColor: c.textColor },
        grid: { vertLines: { color: c.gridColor }, horzLines: { color: c.gridColor } },
        rightPriceScale: { borderColor: c.borderColor },
        timeScale: { borderColor: c.borderColor },
      });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  // Update series when chart type or data changes
  useEffect(() => {
    if (!chartRef.current || chartData.length === 0) return;

    // Remove existing series
    if (seriesRef.current) {
      chartRef.current.removeSeries(seriesRef.current);
      seriesRef.current = null;
    }

    const colors = getChartColors();
    // Create new series based on type (v5 API)
    if (chartType === 'candlestick') {
      const series = chartRef.current.addSeries(CandlestickSeries, {
        upColor: colors.upColor,
        downColor: colors.downColor,
        borderUpColor: colors.upColor,
        borderDownColor: colors.downColor,
        wickUpColor: colors.upColor,
        wickDownColor: colors.downColor,
      });
      series.setData(chartData as CandlestickData<Time>[]);
      markersRef.current = createSeriesMarkers(series, markers);
      seriesRef.current = series;
    } else {
      const series = chartRef.current.addSeries(LineSeries, {
        color: colors.lineColor,
        lineWidth: 2,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
      });
      series.setData(chartData.map(d => ({ time: d.time, value: d.close })));
      markersRef.current = createSeriesMarkers(series, markers);
      seriesRef.current = series;
    }

    // Fit content
    chartRef.current.timeScale().fitContent();
  }, [chartType, chartData, markers]);

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale();
      const currentRange = timeScale.getVisibleLogicalRange();
      if (currentRange) {
        const center = (currentRange.from + currentRange.to) / 2;
        const newRange = (currentRange.to - currentRange.from) * 0.5;
        timeScale.setVisibleLogicalRange({
          from: center - newRange / 2,
          to: center + newRange / 2,
        });
      }
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale();
      const currentRange = timeScale.getVisibleLogicalRange();
      if (currentRange) {
        const center = (currentRange.from + currentRange.to) / 2;
        const newRange = (currentRange.to - currentRange.from) * 2;
        timeScale.setVisibleLogicalRange({
          from: center - newRange / 2,
          to: center + newRange / 2,
        });
      }
    }
  }, []);

  const handleReset = useCallback(() => {
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, []);

  if (priceData.length === 0) {
    return (
      <div className={`h-full flex items-center justify-center bg-surface text-muted-fg text-sm ${fontClass}`}>
        No price data available
      </div>
    );
  }

  return (
    <div className={`h-full flex flex-col bg-surface ${fontClass}`}>
      {/* Controls bar */}
      <div className="flex-shrink-0 flex items-center gap-2 px-2 py-1.5 bg-surface-hover border-b border-border">
        <span className="text-[11px] font-mono font-bold text-foreground">{ticker}</span>

        <div className="w-px h-4 bg-muted" />

        {/* Chart type toggle */}
        <div className="flex items-center bg-surface rounded border border-border overflow-hidden">
          <button
            onClick={() => setChartType('line')}
            className={`p-1 transition-colors ${chartType === 'line' ? 'bg-primary text-white' : 'text-muted-fg hover:bg-surface-hover'}`}
            title="Line chart"
          >
            <LineChart className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setChartType('candlestick')}
            className={`p-1 transition-colors ${chartType === 'candlestick' ? 'bg-primary text-white' : 'text-muted-fg hover:bg-surface-hover'}`}
            title="Candlestick chart"
          >
            <CandlestickChart className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="w-px h-4 bg-muted" />

        {/* Zoom controls */}
        <div className="flex items-center gap-0.5">
          <button
            onClick={handleZoomIn}
            className="p-1 text-muted-fg hover:text-foreground hover:bg-surface-hover rounded transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-1 text-muted-fg hover:text-foreground hover:bg-surface-hover rounded transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleReset}
            className="p-1 text-muted-fg hover:text-foreground hover:bg-surface-hover rounded transition-colors"
            title="Reset view"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex-1" />

        {/* Legend */}
        <div className="flex items-center gap-3 text-[9px]">
          <span className="flex items-center gap-1">
            <span className="w-0 h-0 border-l-[4px] border-r-[4px] border-b-[6px] border-l-transparent border-r-transparent border-b-emerald-500" />
            <span className="text-foreground/80">Buy</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-0 h-0 border-l-[4px] border-r-[4px] border-t-[6px] border-l-transparent border-r-transparent border-t-red-500" />
            <span className="text-foreground/80">Sell</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-muted-fg" />
            <span className="text-foreground/80">Other</span>
          </span>
        </div>

        <span className="text-[9px] text-muted-fg">{transactions.length} tx</span>
      </div>

      {/* Chart container */}
      <div className="flex-1 min-h-0 relative">
        <div ref={chartContainerRef} className="absolute inset-0" />

        {/* Transaction detail popup */}
        {selectedGroup && (
          <div className="absolute top-2 right-2 bg-surface border border-border rounded-lg shadow-xl p-3 min-w-[220px] max-w-[280px] z-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-foreground">
                {formatDate(selectedGroup.date)}
              </span>
              <button
                onClick={() => setSelectedGroup(null)}
                className="p-0.5 text-muted-fg hover:text-foreground"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="text-[10px] text-muted-fg mb-2">
              Price: ${selectedGroup.price.toFixed(2)}
            </div>

            <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
              {selectedGroup.transactions.map((tx, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 py-1 border-b border-border-subtle last:border-0"
                >
                  <span
                    className="px-1.5 py-0.5 rounded text-[9px] font-bold text-white"
                    style={{ backgroundColor: TX_COLORS[tx.code] || '#64748b' }}
                  >
                    {TX_LABELS[tx.code] || tx.code}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] text-foreground truncate font-medium">
                      {tx.insider_name || 'Unknown'}
                    </div>
                    <div className="text-[9px] text-muted-fg">
                      {formatNumber(tx.shares)} shares • {formatCurrency(tx.value)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex-shrink-0 px-2 py-1 bg-surface-hover border-t border-border text-[9px] text-muted-fg">
        Scroll to zoom • Drag to pan • Click markers for details
      </div>
    </div>
  );
}
