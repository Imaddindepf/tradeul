'use client';

import { useState, useMemo, useRef, useCallback } from 'react';
import { LineChart, CandlestickChart } from 'lucide-react';
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

// ============================================================================
// Constants
// ============================================================================

const FONT_CLASSES: Record<string, string> = {
  'oxygen-mono': 'font-oxygen-mono',
  'ibm-plex-mono': 'font-ibm-plex-mono',
  'jetbrains-mono': 'font-jetbrains-mono',
  'fira-code': 'font-fira-code',
};

const TX_TYPES = [
  { code: 'P', label: 'BUY', color: '#10b981' },
  { code: 'S', label: 'SELL', color: '#ef4444' },
  { code: 'M', label: 'EXER', color: '#8b5cf6' },
  { code: 'A', label: 'GRANT', color: '#3b82f6' },
  { code: 'F', label: 'TAX', color: '#f59e0b' },
  { code: 'G', label: 'GIFT', color: '#06b6d4' },
  { code: 'J', label: 'XFER', color: '#64748b' },
] as const;

const TX_COLOR_MAP: Record<string, string> = Object.fromEntries(TX_TYPES.map(t => [t.code, t.color]));
TX_COLOR_MAP.default = '#94a3b8';

const TX_LABEL_MAP: Record<string, string> = Object.fromEntries(TX_TYPES.map(t => [t.code, t.label]));

// Fixed virtual dimensions - browser scales automatically via viewBox
const VW = 800;  // Virtual width
const VH = 400;  // Virtual height
const PADDING = { top: 45, right: 55, bottom: 25, left: 10 };
const CHART_W = VW - PADDING.left - PADDING.right;
const CHART_H = VH - PADDING.top - PADDING.bottom;

// ============================================================================
// Helpers
// ============================================================================

function formatPrice(num: number): string {
  return num > 0 ? `$${num.toFixed(2)}` : '';
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
  } catch {
    return dateStr;
  }
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function formatCurrency(num: number): string {
  if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `$${(num / 1_000).toFixed(1)}K`;
  return `$${num.toFixed(2)}`;
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

  const svgRef = useRef<SVGSVGElement>(null);
  const [chartType, setChartType] = useState<ChartType>('candlestick');
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set(['P', 'S', 'M', 'A', 'F', 'G', 'J']));
  const [hoveredTx, setHoveredTx] = useState<{ tx: InsiderTransaction; x: number; y: number; price: number } | null>(null);

  // Filter transactions
  const filteredTransactions = useMemo(() => {
    return transactions.filter(tx => activeFilters.has(tx.code));
  }, [transactions, activeFilters]);

  const toggleFilter = (code: string) => {
    setActiveFilters(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  // All chart calculations - computed once, no dependency on container size
  const chartData = useMemo(() => {
    if (priceData.length === 0) return null;

    const dates = priceData.map(d => new Date(d.date).getTime());
    const minDate = Math.min(...dates);
    const maxDate = Math.max(...dates);
    const minPrice = Math.min(...priceData.map(d => d.low)) * 0.97;
    const maxPrice = Math.max(...priceData.map(d => d.high)) * 1.03;

    const xScale = (date: string) => {
      const d = new Date(date).getTime();
      if (maxDate === minDate) return PADDING.left;
      return PADDING.left + ((d - minDate) / (maxDate - minDate)) * CHART_W;
    };

    const yScale = (price: number) => {
      if (maxPrice === minPrice) return PADDING.top + CHART_H / 2;
      return PADDING.top + CHART_H - ((price - minPrice) / (maxPrice - minPrice)) * CHART_H;
    };

    // Pre-compute price lookup
    const priceLookup = new Map<string, OHLCBar>();
    priceData.forEach(bar => priceLookup.set(bar.date, bar));

    const findBar = (date: string): OHLCBar => {
      const exact = priceLookup.get(date);
      if (exact) return exact;
      const txTime = new Date(date).getTime();
      return priceData.reduce((closest, bar) => {
        const diff = Math.abs(new Date(bar.date).getTime() - txTime);
        const closestDiff = Math.abs(new Date(closest.date).getTime() - txTime);
        return diff < closestDiff ? bar : closest;
      });
    };

    const candleWidth = Math.max(1, Math.min(5, CHART_W / priceData.length - 1));

    // Pre-compute all candle positions
    const candles = priceData.map(bar => {
      const x = xScale(bar.date);
      const isGreen = bar.close >= bar.open;
      return {
        x,
        high: yScale(bar.high),
        low: yScale(bar.low),
        bodyTop: yScale(Math.max(bar.open, bar.close)),
        bodyBottom: yScale(Math.min(bar.open, bar.close)),
        color: isGreen ? '#22c55e' : '#ef4444',
        close: bar.close
      };
    });

    // Pre-compute line path
    const linePath = `M${priceData.map(d => `${xScale(d.date)},${yScale(d.close)}`).join('L')}`;
    const areaPath = `${linePath}L${VW - PADDING.right},${PADDING.top + CHART_H}L${PADDING.left},${PADDING.top + CHART_H}Z`;

    // Pre-compute grid
    const gridLines = [0.2, 0.4, 0.6, 0.8].map(pct => ({
      y: PADDING.top + CHART_H * pct,
      price: maxPrice - (maxPrice - minPrice) * pct
    }));

    return {
      xScale,
      yScale,
      findBar,
      candles,
      candleWidth,
      linePath,
      areaPath,
      gridLines,
      minPrice,
      maxPrice,
      firstDate: priceData[0].date,
      lastDate: priceData[priceData.length - 1].date
    };
  }, [priceData]);

  // Pre-compute transaction markers
  const txMarkers = useMemo(() => {
    if (!chartData) return [];
    return filteredTransactions.map(tx => {
      const bar = chartData.findBar(tx.date);
      const x = chartData.xScale(tx.date);
      const y = chartData.yScale(bar.close);
      const size = Math.min(7, 3.5 + Math.log10(tx.shares + 1) * 0.5);
      const color = TX_COLOR_MAP[tx.code] || TX_COLOR_MAP.default;
      return { tx, x, y, size, color, price: bar.close };
    }).filter(m => m.x >= PADDING.left && m.x <= VW - PADDING.right);
  }, [filteredTransactions, chartData]);

  // Mouse handlers for transaction hover
  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current || txMarkers.length === 0) return;
    
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = VW / rect.width;
    const scaleY = VH / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;
    
    // Find hovered transaction
    const hovered = txMarkers.find(m => {
      const dist = Math.sqrt((m.x - x) ** 2 + (m.y - y) ** 2);
      return dist < 12;
    });
    
    setHoveredTx(hovered ? { tx: hovered.tx, x: hovered.x, y: hovered.y, price: hovered.price } : null);
  }, [txMarkers]);

  const handleMouseLeave = useCallback(() => setHoveredTx(null), []);

  if (!chartData) {
    return (
      <div className={`h-full flex items-center justify-center bg-slate-50 text-slate-500 text-sm ${fontClass}`}>
        No price data available
      </div>
    );
  }

  return (
    <div className={`h-full flex flex-col bg-white ${fontClass}`}>
      {/* Controls bar */}
      <div className="flex-shrink-0 flex items-center gap-3 px-3 py-2 bg-slate-50 border-b border-slate-200">
        <span className="text-sm font-mono font-bold text-slate-800">{ticker}</span>
        <div className="w-px h-5 bg-slate-300" />
        <div className="flex items-center gap-1">
          <button
            onClick={() => setChartType('line')}
            className={`p-1.5 rounded transition-colors ${chartType === 'line' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-200'}`}
          >
            <LineChart className="w-4 h-4" />
          </button>
          <button
            onClick={() => setChartType('candlestick')}
            className={`p-1.5 rounded transition-colors ${chartType === 'candlestick' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-200'}`}
          >
            <CandlestickChart className="w-4 h-4" />
          </button>
        </div>
        <div className="w-px h-5 bg-slate-300" />
        <div className="flex items-center gap-1">
          {TX_TYPES.map(t => (
            <button
              key={t.code}
              onClick={() => toggleFilter(t.code)}
              className={`px-2 py-1 text-[10px] font-bold rounded transition-all ${
                activeFilters.has(t.code) ? 'text-white shadow-sm' : 'text-slate-400 bg-slate-100 hover:bg-slate-200'
              }`}
              style={activeFilters.has(t.code) ? { backgroundColor: t.color } : {}}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <span className="text-[10px] text-slate-500">{filteredTransactions.length} tx · {priceData.length}d</span>
      </div>

      {/* Chart container - isolated for performance */}
      <div className="flex-1 relative min-h-0" style={{ contain: 'strict' }}>
        <svg 
          ref={svgRef}
          viewBox={`0 0 ${VW} ${VH}`}
          preserveAspectRatio="xMidYMid slice"
          className="absolute inset-0 w-full h-full"
          style={{ willChange: 'transform' }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          {/* Grid */}
          {chartData.gridLines.map((g, i) => (
            <g key={i}>
              <line x1={PADDING.left} y1={g.y} x2={VW - PADDING.right} y2={g.y} stroke="#e2e8f0" />
              <text x={VW - PADDING.right + 4} y={g.y + 3} fontSize={9} fill="#94a3b8">{formatPrice(g.price)}</text>
            </g>
          ))}

          {/* Price chart */}
          {chartType === 'line' ? (
            <>
              <path d={chartData.areaPath} fill="url(#areaGradient)" />
              <path d={chartData.linePath} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
            </>
          ) : (
            chartData.candles.map((c, i) => (
              <g key={i}>
                <line x1={c.x} y1={c.high} x2={c.x} y2={c.low} stroke={c.color} />
                <rect 
                  x={c.x - chartData.candleWidth / 2} 
                  y={c.bodyTop} 
                  width={chartData.candleWidth} 
                  height={Math.max(1, c.bodyBottom - c.bodyTop)} 
                  fill={c.color} 
                />
              </g>
            ))
          )}

          {/* Transaction markers */}
          {txMarkers.map((m, i) => (
            <g key={i}>
              <line x1={m.x} y1={PADDING.top} x2={m.x} y2={PADDING.top + CHART_H} stroke={m.color} opacity={0.25} strokeDasharray="2,2" />
              <circle 
                cx={m.x} 
                cy={m.y} 
                r={hoveredTx?.tx === m.tx ? m.size + 2 : m.size} 
                fill={m.color} 
                stroke="white" 
                strokeWidth={1.5}
                style={{ cursor: 'pointer' }}
              />
            </g>
          ))}

          {/* X-axis labels */}
          <text x={PADDING.left} y={VH - 8} fontSize={8} fill="#94a3b8">{formatDate(chartData.firstDate)}</text>
          <text x={VW - PADDING.right} y={VH - 8} fontSize={8} fill="#94a3b8" textAnchor="end">{formatDate(chartData.lastDate)}</text>

          <defs>
            <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
        </svg>

        {/* Tooltip - HTML overlay */}
        {hoveredTx && (
          <div 
            className="absolute z-20 pointer-events-none"
            style={{ 
              left: `${(hoveredTx.x / VW) * 100}%`,
              top: `${(hoveredTx.y / VH) * 100}%`,
              transform: 'translate(10px, -50%)'
            }}
          >
            <div className="bg-white border border-slate-200 rounded-lg shadow-xl px-3 py-2 text-[11px] min-w-[160px]">
              <div className="flex items-center gap-2 mb-1.5 pb-1.5 border-b border-slate-100">
                <span 
                  className="px-1.5 py-0.5 rounded text-[9px] font-bold text-white"
                  style={{ backgroundColor: TX_COLOR_MAP[hoveredTx.tx.code] }}
                >
                  {TX_LABEL_MAP[hoveredTx.tx.code] || hoveredTx.tx.code}
                </span>
                <span className="text-slate-500 text-[10px]">{formatDate(hoveredTx.tx.date)}</span>
              </div>
              {hoveredTx.tx.insider_name && (
                <div className="text-slate-800 font-semibold mb-1.5 text-xs">{hoveredTx.tx.insider_name}</div>
              )}
              <div className="space-y-0.5 text-[10px]">
                <div className="flex justify-between gap-4">
                  <span className="text-slate-500">Shares</span>
                  <span className="font-mono font-medium text-slate-800">{formatNumber(hoveredTx.tx.shares)}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-slate-500">Value</span>
                  <span className="font-mono font-medium text-slate-800">{formatCurrency(hoveredTx.tx.value)}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-slate-500">Price</span>
                  <span className="font-mono font-medium text-slate-800">{formatPrice(hoveredTx.price)}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
