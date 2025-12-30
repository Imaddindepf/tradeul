// ============================================================
/**
 * Multiple Security Window Injector
 * 
 * Standalone window for multi-ticker comparison charts
 */

import { getUserTimezoneForWindow, getUserFontForWindow, getFontConfig, WindowConfig } from './base';

// MULTIPLE SECURITY COMPARISON WINDOW (MP)
// ============================================================

export interface MultipleSecurityWindowData {
  initialTickers?: string[];
  period?: '1M' | '3M' | '6M' | '1Y' | '5Y' | 'ALL';
  chartType?: 'line' | 'area' | 'candlestick' | 'ohlc' | 'mountain';
  scaleType?: 'percent' | 'price';
}

export function openMultipleSecurityWindow(
  data: MultipleSecurityWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 950,
    height = 600,
    centered = true,
  } = config;

  const left = centered ? (window.screen.width - width) / 2 : 100;
  const top = centered ? (window.screen.height - height) / 2 : 100;

  const windowFeatures = [
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
    'resizable=yes',
    'scrollbars=yes',
    'status=yes',
  ].join(',');

  const newWindow = window.open('about:blank', '_blank', windowFeatures);

  if (!newWindow) {
    console.error('❌ Window blocked');
    return null;
  }

  injectMultipleSecurityContent(newWindow, data, config);

  return newWindow;
}

function injectMultipleSecurityContent(
  targetWindow: Window,
  data: MultipleSecurityWindowData,
  config: WindowConfig
): void {
  const { title } = config;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://api.tradeul.com';
  const userTimezone = getUserTimezoneForWindow();
  const userFont = getUserFontForWindow();
  const fontConfig = getFontConfig(userFont);

  const htmlContent = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=${fontConfig.googleFont}&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: [${fontConfig.cssFamily}]
          }
        }
      }
    };
  </script>
  
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: 'Inter', sans-serif; background: #fff; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
    .ticker-tag { transition: all 0.15s ease; }
    .ticker-tag:hover .remove-btn { opacity: 1; }
    .remove-btn { opacity: 0; transition: opacity 0.15s; }
  </style>
</head>
<body>
  <div id="root" class="h-screen flex flex-col bg-white text-slate-800"></div>
  
  <script>
    // ============================================================
    // STATE
    // ============================================================
    const API_URL = '${apiUrl}';
    const USER_TIMEZONE = '${userTimezone}';
    const TICKER_COLORS = [
      '#f43f5e', '#06b6d4', '#10b981', '#f59e0b', '#8b5cf6',
      '#ec4899', '#14b8a6', '#6366f1', '#84cc16', '#f97316'
    ];
    const PERIODS = [
      { id: '1M', label: '1M', days: 30 },
      { id: '3M', label: '3M', days: 90 },
      { id: '6M', label: '6M', days: 180 },
      { id: '1Y', label: '1Y', days: 365 },
      { id: '5Y', label: '5Y', days: 1825 },
      { id: 'ALL', label: 'All', days: 3650 },
    ];
    const CHART_TYPES = ['line', 'area', 'mountain', 'candlestick', 'ohlc'];
    
    let tickers = [];
    let period = '${data.period || '1Y'}';
    let chartType = '${data.chartType || 'line'}';
    let scaleType = '${data.scaleType || 'percent'}';
    let loading = false;
    let error = null;
    const initialTickers = ${JSON.stringify(data.initialTickers || [])};
    let tooltip = null;
    
    // ============================================================
    // DATA FETCHING
    // ============================================================
    async function fetchTickerData(symbol) {
      const periodConfig = PERIODS.find(p => p.id === period);
      if (!periodConfig) return null;
      
      const response = await fetch(
        API_URL + '/api/v1/chart/' + symbol.toUpperCase() + '?interval=1day&limit=' + periodConfig.days
      );
      
      if (!response.ok) throw new Error('Failed to fetch ' + symbol);
      
      const result = await response.json();
      const data = result.data || [];
      
      if (data.length === 0) throw new Error('No data for ' + symbol);
      
      const chartData = data.map(bar => ({
        date: new Date(bar.time * 1000).toISOString().split('T')[0],
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })).sort((a, b) => a.date.localeCompare(b.date));
      
      const firstPrice = chartData[0]?.close || 1;
      const lastPrice = chartData[chartData.length - 1]?.close || firstPrice;
      const changePercent = ((lastPrice / firstPrice) - 1) * 100;
      
      const usedColors = tickers.map(t => t.color);
      const availableColor = TICKER_COLORS.find(c => !usedColors.includes(c)) || TICKER_COLORS[0];
      
      return {
        symbol: symbol.toUpperCase(),
        color: availableColor,
        data: chartData,
        latestPrice: lastPrice,
        changePercent,
      };
    }
    
    async function addTicker(symbol) {
      if (!symbol.trim()) return;
      symbol = symbol.trim().toUpperCase();
      
      if (tickers.some(t => t.symbol === symbol)) {
        error = symbol + ' already added';
        render();
        return;
      }
      if (tickers.length >= 10) {
        error = 'Maximum 10 tickers';
        render();
        return;
      }
      
      loading = true;
      error = null;
      render();
      
      try {
        const tickerData = await fetchTickerData(symbol);
        if (tickerData) {
          tickers.push(tickerData);
          document.getElementById('ticker-input').value = '';
        }
      } catch (e) {
        error = e.message;
      } finally {
        loading = false;
        render();
      }
    }
    
    function removeTicker(symbol) {
      tickers = tickers.filter(t => t.symbol !== symbol);
      render();
    }
    
    async function changePeriod(newPeriod) {
      if (period === newPeriod || tickers.length === 0) {
        period = newPeriod;
        render();
        return;
      }
      
      period = newPeriod;
      loading = true;
      error = null;
      render();
      
      try {
        const symbols = tickers.map(t => t.symbol);
        const colors = tickers.map(t => t.color);
        tickers = [];
        
        for (let i = 0; i < symbols.length; i++) {
          try {
            const data = await fetchTickerData(symbols[i]);
            if (data) {
              data.color = colors[i];
              tickers.push(data);
            }
          } catch {}
        }
      } catch (e) {
        error = e.message;
      } finally {
        loading = false;
        render();
      }
    }
    
    // ============================================================
    // SVG CHART RENDERING
    // ============================================================
    function renderChart() {
      const container = document.getElementById('chart-container');
      if (!container) return;
      
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 400;
      const padding = { top: 20, right: 55, bottom: 30, left: 10 };
      const chartWidth = width - padding.left - padding.right;
      const chartHeight = height - padding.top - padding.bottom;
      
      if (tickers.length === 0) {
        container.innerHTML = '<svg width="' + width + '" height="' + height + '"><text x="' + (width/2) + '" y="' + (height/2) + '" text-anchor="middle" fill="#94a3b8" font-size="12">Add tickers to compare</text></svg>';
        return;
      }
      
      // Align data by date
      const allDates = new Set();
      tickers.forEach(t => t.data.forEach(d => allDates.add(d.date)));
      const sortedDates = Array.from(allDates).sort();
      
      const tickerMaps = tickers.map(t => {
        const map = new Map();
        t.data.forEach(d => map.set(d.date, d));
        return map;
      });
      
      const firstValues = tickers.map((t, i) => {
        for (const date of sortedDates) {
          const bar = tickerMaps[i].get(date);
          if (bar) return bar.close;
        }
        return 1;
      });
      
      const alignedData = sortedDates.map(date => {
        const values = tickers.map((t, i) => {
          const bar = tickerMaps[i].get(date);
          if (!bar) return null;
          
          if (scaleType === 'percent') {
            const baseValue = firstValues[i];
            return {
              close: ((bar.close / baseValue) - 1) * 100,
              open: ((bar.open / baseValue) - 1) * 100,
              high: ((bar.high / baseValue) - 1) * 100,
              low: ((bar.low / baseValue) - 1) * 100,
            };
          }
          return { close: bar.close, open: bar.open, high: bar.high, low: bar.low };
        });
        return { date, values };
      }).filter(d => d.values.some(v => v !== null));
      
      // Calculate value range
      let minVal = Infinity, maxVal = -Infinity;
      alignedData.forEach(d => {
        d.values.forEach(v => {
          if (v) {
            minVal = Math.min(minVal, v.low, v.close);
            maxVal = Math.max(maxVal, v.high, v.close);
          }
        });
      });
      const range = maxVal - minVal;
      minVal -= range * 0.05;
      maxVal += range * 0.05;
      
      // Scale functions
      const dates = alignedData.map(d => new Date(d.date).getTime());
      const dateMin = Math.min(...dates);
      const dateMax = Math.max(...dates);
      
      const xScale = (date) => {
        const d = new Date(date).getTime();
        if (dateMax === dateMin) return padding.left;
        return padding.left + ((d - dateMin) / (dateMax - dateMin)) * chartWidth;
      };
      
      const yScale = (value) => {
        if (maxVal === minVal) return padding.top + chartHeight / 2;
        return padding.top + chartHeight - ((value - minVal) / (maxVal - minVal)) * chartHeight;
      };
      
      // Calculate bar width for candlestick/ohlc
      const barWidth = Math.max(2, Math.min(12, (chartWidth * 0.8) / alignedData.length));
      
      // Build SVG
      let svg = '<svg width="' + width + '" height="' + height + '" style="cursor: crosshair;">';
      
      // Gradients for area charts
      tickers.forEach((ticker, i) => {
        const opacity = chartType === 'mountain' ? 0.5 : 0.2;
        svg += '<defs><linearGradient id="gradient-' + i + '" x1="0" y1="0" x2="0" y2="1">';
        svg += '<stop offset="0%" stop-color="' + ticker.color + '" stop-opacity="' + opacity + '"/>';
        svg += '<stop offset="100%" stop-color="' + ticker.color + '" stop-opacity="0.02"/>';
        svg += '</linearGradient></defs>';
      });
      
      // Grid lines
      const gridStep = (maxVal - minVal) / 5;
      for (let i = 0; i <= 5; i++) {
        const value = minVal + gridStep * i;
        const y = yScale(value);
        const label = scaleType === 'percent' 
          ? (value >= 0 ? '+' : '') + value.toFixed(0) + '%'
          : value.toFixed(0);
        svg += '<line x1="' + padding.left + '" y1="' + y + '" x2="' + (padding.left + chartWidth) + '" y2="' + y + '" stroke="#e2e8f0" stroke-dasharray="3 3" stroke-width="0.5"/>';
        svg += '<text x="' + (padding.left + chartWidth + 6) + '" y="' + (y + 3) + '" fill="#94a3b8" font-size="9" font-family="JetBrains Mono, monospace">' + label + '</text>';
      }
      
      // X axis labels
      const labelStep = Math.max(1, Math.floor(alignedData.length / 6));
      for (let i = 0; i < alignedData.length; i += labelStep) {
        const d = alignedData[i];
        const x = xScale(d.date);
        const date = new Date(d.date);
        const label = date.toLocaleDateString('en-US', { timeZone: USER_TIMEZONE, month: 'short', day: 'numeric' });
        svg += '<text x="' + x + '" y="' + (padding.top + chartHeight + 16) + '" fill="#94a3b8" font-size="9" text-anchor="middle">' + label + '</text>';
      }
      
      // Zero line for percent mode
      if (scaleType === 'percent') {
        const zeroY = yScale(0);
        if (zeroY >= padding.top && zeroY <= padding.top + chartHeight) {
          svg += '<line x1="' + padding.left + '" y1="' + zeroY + '" x2="' + (padding.left + chartWidth) + '" y2="' + zeroY + '" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 2"/>';
        }
      }
      
      // Render based on chart type
      if (chartType === 'candlestick' || chartType === 'ohlc') {
        // Candlestick / OHLC
        tickers.forEach((ticker, tickerIdx) => {
          const offsetX = tickers.length > 1 ? (tickerIdx - (tickers.length - 1) / 2) * (barWidth + 1) : 0;
          const candleWidth = tickers.length > 1 ? Math.max(2, barWidth / tickers.length) : barWidth;
          
          alignedData.forEach((d, idx) => {
            const val = d.values[tickerIdx];
            if (!val) return;
            
            const x = xScale(d.date) + offsetX;
            const openY = yScale(val.open);
            const closeY = yScale(val.close);
            const highY = yScale(val.high);
            const lowY = yScale(val.low);
            
            const isBullish = val.close >= val.open;
            const color = tickers.length === 1 ? (isBullish ? '#10b981' : '#f43f5e') : ticker.color;
            const opacity = tickers.length > 1 ? 0.8 : 1;
            
            if (chartType === 'candlestick') {
              const bodyTop = Math.min(openY, closeY);
              const bodyHeight = Math.max(1, Math.abs(closeY - openY));
              svg += '<line x1="' + x + '" y1="' + highY + '" x2="' + x + '" y2="' + lowY + '" stroke="' + color + '" stroke-width="1" opacity="' + opacity + '"/>';
              svg += '<rect x="' + (x - candleWidth/2) + '" y="' + bodyTop + '" width="' + candleWidth + '" height="' + bodyHeight + '" fill="' + (isBullish ? color : 'white') + '" stroke="' + color + '" stroke-width="1" rx="0.5" opacity="' + opacity + '"/>';
            } else {
              const tickW = tickers.length > 1 ? Math.max(2, barWidth / tickers.length / 2) : barWidth / 2;
              svg += '<line x1="' + x + '" y1="' + highY + '" x2="' + x + '" y2="' + lowY + '" stroke="' + color + '" stroke-width="1.5" opacity="' + opacity + '"/>';
              svg += '<line x1="' + (x - tickW) + '" y1="' + openY + '" x2="' + x + '" y2="' + openY + '" stroke="' + color + '" stroke-width="1.5" opacity="' + opacity + '"/>';
              svg += '<line x1="' + x + '" y1="' + closeY + '" x2="' + (x + tickW) + '" y2="' + closeY + '" stroke="' + color + '" stroke-width="1.5" opacity="' + opacity + '"/>';
            }
          });
        });
      } else {
        // Line / Area / Mountain
        if (chartType === 'area' || chartType === 'mountain') {
          tickers.forEach((ticker, tickerIdx) => {
            const points = [];
            alignedData.forEach(d => {
              const val = d.values[tickerIdx];
              if (val) points.push({ x: xScale(d.date), y: yScale(val.close) });
            });
            
            if (points.length >= 2) {
              const baseline = yScale(scaleType === 'percent' ? 0 : minVal);
              let areaPath = 'M ' + points[0].x + ' ' + baseline;
              points.forEach(p => areaPath += ' L ' + p.x + ' ' + p.y);
              areaPath += ' L ' + points[points.length - 1].x + ' ' + baseline + ' Z';
              svg += '<path d="' + areaPath + '" fill="url(#gradient-' + tickerIdx + ')"/>';
            }
          });
        }
        
        // Lines
        tickers.forEach((ticker, tickerIdx) => {
          let linePath = '';
          let started = false;
          
          alignedData.forEach(d => {
            const val = d.values[tickerIdx];
            if (val) {
              const x = xScale(d.date);
              const y = yScale(val.close);
              linePath += started ? ' L ' + x + ' ' + y : 'M ' + x + ' ' + y;
              started = true;
            }
          });
          
          const strokeWidth = chartType === 'mountain' ? 2 : 1.5;
          svg += '<path d="' + linePath + '" fill="none" stroke="' + ticker.color + '" stroke-width="' + strokeWidth + '" stroke-linecap="round" stroke-linejoin="round"/>';
        });
      }
      
      svg += '</svg>';
      container.innerHTML = svg;
    }
    
    // ============================================================
    // RENDER
    // ============================================================
    function render() {
      const root = document.getElementById('root');
      const periodConfig = PERIODS.find(p => p.id === period);
      const chartTypeLabel = chartType.charAt(0).toUpperCase() + chartType.slice(1);
      
      root.innerHTML = \`
        <div class="h-full flex flex-col">
          <!-- Search Bar -->
          <div class="flex-shrink-0 px-4 py-3 border-b border-slate-100">
            <div class="flex gap-2 items-center">
              <div class="w-32">
                <input id="ticker-input" type="text" placeholder="Add ticker" 
                  class="w-full px-2 py-1 text-sm border border-slate-200 rounded focus:outline-none focus:border-blue-400"
                  onkeydown="if(event.key==='Enter') addTicker(this.value)" />
              </div>
              
              <button onclick="addTicker(document.getElementById('ticker-input').value)" 
                class="p-1.5 rounded border border-slate-200 text-slate-400 hover:text-blue-600 hover:border-blue-300 disabled:opacity-50"
                \${loading ? 'disabled' : ''}>
                \${loading ? '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/></svg>' : '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>'}
              </button>

              <!-- Period selector -->
              <div class="flex items-center gap-1 text-slate-400 ml-2" style="font-size: 10px;">
                \${PERIODS.map(p => \`
                  <button onclick="changePeriod('\${p.id}')" 
                    class="px-1.5 py-0.5 rounded \${period === p.id ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}">
                    \${p.label}
                  </button>
                \`).join('')}
              </div>

              <div class="flex-1"></div>

              <!-- Chart type selector -->
              <div class="flex items-center gap-0.5 text-slate-400" style="font-size: 9px;">
                \${CHART_TYPES.map(ct => \`
                  <button onclick="chartType = '\${ct}'; render(); renderChart();" 
                    class="p-1 rounded transition-colors \${chartType === ct ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}"
                    title="\${ct.charAt(0).toUpperCase() + ct.slice(1)}">
                    \${ct === 'line' ? '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 17l6-6 4 4 8-8"/></svg>' :
                      ct === 'area' ? '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>' :
                      ct === 'mountain' ? '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>' :
                      ct === 'candlestick' ? '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6M9 6h6M9 18h6M12 3v3m0 12v3"/></svg>' :
                      '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>'}
                  </button>
                \`).join('')}
                <span class="text-slate-200 mx-0.5">|</span>
                <button onclick="scaleType = 'percent'; render(); renderChart();" 
                  class="px-1.5 py-0.5 rounded \${scaleType === 'percent' ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}">%</button>
                <button onclick="scaleType = 'price'; render(); renderChart();" 
                  class="px-1.5 py-0.5 rounded \${scaleType === 'price' ? 'bg-slate-100 text-slate-700' : 'hover:text-slate-600'}">$</button>
              </div>
            </div>
          </div>

          <!-- Tickers legend -->
          \${tickers.length > 0 ? \`
            <div class="flex-shrink-0 px-4 py-2 border-b border-slate-100 flex flex-wrap items-center gap-2">
              \${tickers.map(t => \`
                <div class="ticker-tag flex items-center gap-1.5">
                  <div class="w-3 h-0.5 rounded" style="background-color: \${t.color}"></div>
                  <span class="text-xs font-medium" style="color: \${t.color}">\${t.symbol}</span>
                  <span class="text-[10px] font-mono" style="color: \${t.changePercent >= 0 ? '#10b981' : '#f43f5e'}">
                    \${t.changePercent >= 0 ? '+' : ''}\${t.changePercent.toFixed(1)}%
                  </span>
                  <button onclick="removeTicker('\${t.symbol}')" class="remove-btn text-slate-300 hover:text-slate-500">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                  </button>
                </div>
              \`).join('')}
            </div>
          \` : ''}

          <!-- Error -->
          \${error ? \`
            <div class="flex items-center gap-2 text-red-600 px-4 py-2" style="font-size: 11px;">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              \${error}
              <button onclick="error = null; render();" class="ml-auto text-red-400 hover:text-red-600">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
          \` : ''}

          <!-- Chart area -->
          <div id="chart-container" class="flex-1 relative px-4 py-3">
            \${loading && tickers.length === 0 ? \`
              <div class="h-full flex flex-col items-center justify-center text-slate-400">
                <svg class="w-6 h-6 animate-spin mb-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/></svg>
                <span style="font-size: 11px;">Loading...</span>
              </div>
            \` : tickers.length === 0 ? \`
              <div class="h-full flex flex-col items-center justify-center text-slate-400">
                <svg class="w-8 h-8 mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                <p style="font-size: 12px;">Add tickers to compare their performance</p>
                <p style="font-size: 10px;" class="text-slate-300 mt-1">e.g., NVDA, MSFT, AAPL</p>
              </div>
            \` : ''}
          </div>

          <!-- Footer -->
          <div class="flex-shrink-0 px-4 py-1 border-t border-slate-100 flex items-center justify-between text-slate-400" style="font-size: 9px;">
            <span>
              \${tickers.length > 0
                ? tickers.length + ' ticker' + (tickers.length > 1 ? 's' : '') + ' · ' + periodConfig?.label + ' · ' + chartTypeLabel
                : 'Add tickers to begin'}
            </span>
            <span class="font-mono">MP</span>
          </div>
        </div>
      \`;
      
      // Render chart after DOM update
      setTimeout(renderChart, 0);
    }
    
    // ============================================================
    // RESIZE HANDLER
    // ============================================================
    window.addEventListener('resize', () => {
      renderChart();
    });
    
    // ============================================================
    // INIT
    // ============================================================
    async function init() {
      render();
      
      // Load initial tickers if provided
      if (initialTickers.length > 0) {
        loading = true;
        render();
        
        for (const symbol of initialTickers) {
          try {
            const tickerData = await fetchTickerData(symbol);
            if (tickerData) {
              tickers.push(tickerData);
            }
          } catch (e) {
            console.warn('Failed to load', symbol, e);
          }
        }
        
        loading = false;
        render();
        renderChart();
      }
      
      console.log('✅ [MP] Multiple Security Window initialized');
    }
    
    init();
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Multiple Security injected');
}
