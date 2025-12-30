/**
 * Financial Chart Window Injector
 * 
 * Standalone window for financial metric charts
 */

import { WindowConfig, formatValueJS, getUserFontForWindow, getFontConfig } from './base';

// ============================================================
// FINANCIAL METRIC CHART WINDOW
// ============================================================

export interface FinancialChartData {
  ticker: string;
  metricLabel: string;
  metricKey: string;
  currency: string;
  valueType: 'currency' | 'percent' | 'ratio' | 'eps' | 'shares';
  isNegativeBad: boolean;
  data: Array<{
    period: string;
    fiscalYear: string;
    value: number | null;
    isAnnual: boolean;
  }>;
}

export function openFinancialChartWindow(
  chartData: FinancialChartData,
  config: WindowConfig
): Window | null {
  const {
    width = 1000,
    height = 650,
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

  injectFinancialChartContent(newWindow, chartData, config);

  return newWindow;
}

function injectFinancialChartContent(
  targetWindow: Window,
  chartData: FinancialChartData,
  config: WindowConfig
): void {
  const { title } = config;
  const userFont = getUserFontForWindow();
  const fontConfig = getFontConfig(userFont);
  const validData = chartData.data.filter(d => d.value !== null && d.value !== undefined);

  // Calculate stats
  const values = validData.map(d => d.value as number);
  const latest = values[values.length - 1] || 0;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;

  // YoY growth
  const periodsBack = validData[validData.length - 1]?.isAnnual ? 1 : 4;
  const previousValue = values.length > periodsBack ? values[values.length - 1 - periodsBack] : null;
  const yoyGrowth = previousValue && previousValue !== 0
    ? ((latest - previousValue) / Math.abs(previousValue)) * 100
    : null;

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <!-- Fuentes -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=${fontConfig.googleFont}&display=swap" rel="stylesheet">
  
  <!-- Tailwind CSS -->
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
    }
  </script>
  
  <!-- Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  
  <style>
    body { font-family: 'Inter', sans-serif; margin: 0; padding: 0; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
    .stat-card { transition: transform 0.2s; }
    .stat-card:hover { transform: translateY(-2px); }
    
    /* Responsive adjustments */
    @media (max-width: 900px) {
      .stats-grid { grid-template-columns: repeat(3, 1fr) !important; }
      .header-content { flex-direction: column; align-items: flex-start !important; gap: 12px; }
      .header-value { font-size: 1.5rem !important; }
    }
    @media (max-width: 600px) {
      .stats-grid { grid-template-columns: repeat(2, 1fr) !important; gap: 8px !important; padding: 12px !important; }
      .stat-card { padding: 8px !important; }
      .stat-card p:first-child { font-size: 9px !important; }
      .stat-card p:last-child { font-size: 14px !important; }
      .chart-container { padding: 12px !important; }
      .footer-content { flex-direction: column; gap: 12px; align-items: flex-start !important; }
      .footer-legend { flex-wrap: wrap; gap: 8px !important; }
      .header-title { font-size: 16px !important; }
      .header-subtitle { font-size: 12px !important; }
    }
    @media (max-width: 400px) {
      .stats-grid { grid-template-columns: repeat(2, 1fr) !important; }
      .header-value { font-size: 1.25rem !important; }
    }
  </style>
</head>
<body class="bg-slate-50">
  <div class="h-screen flex flex-col">
    <!-- Header -->
    <div class="px-4 sm:px-6 py-3 sm:py-4 bg-white border-b border-slate-200 shadow-sm">
      <div class="header-content flex items-center justify-between">
        <div>
          <h1 class="header-title text-lg sm:text-xl font-bold text-slate-900">${chartData.metricLabel}</h1>
          <p class="header-subtitle text-xs sm:text-sm text-slate-500">${chartData.ticker} • ${chartData.currency} • ${validData.length} periods</p>
        </div>
        <div class="flex items-center gap-2 sm:gap-3">
          <span class="header-value text-2xl sm:text-3xl font-bold ${yoyGrowth !== null && yoyGrowth >= 0 ? 'text-emerald-600' : 'text-red-600'}">
            ${formatValueJS(latest, '${chartData.valueType}')}
          </span>
          ${yoyGrowth !== null ? `
            <span class="px-2 py-1 rounded text-xs sm:text-sm font-medium ${yoyGrowth >= 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}">
              ${yoyGrowth >= 0 ? '↑' : '↓'} ${Math.abs(yoyGrowth).toFixed(1)}%
            </span>
          ` : ''}
        </div>
      </div>
    </div>

    <!-- Stats Grid -->
    <div class="stats-grid grid grid-cols-5 gap-3 sm:gap-4 px-4 sm:px-6 py-3 sm:py-4 bg-slate-100 border-b border-slate-200">
      <div class="stat-card bg-white rounded-lg p-3 shadow-sm">
        <p class="text-xs uppercase text-slate-500 font-medium">Latest</p>
        <p class="text-lg font-bold text-slate-800">${formatValueJS(latest, chartData.valueType)}</p>
      </div>
      <div class="stat-card bg-white rounded-lg p-3 shadow-sm">
        <p class="text-xs uppercase text-slate-500 font-medium">YoY Growth</p>
        <p class="text-lg font-bold ${yoyGrowth !== null && yoyGrowth >= 0 ? 'text-emerald-600' : 'text-red-600'}">
          ${yoyGrowth !== null ? `${yoyGrowth >= 0 ? '+' : ''}${yoyGrowth.toFixed(1)}%` : '--'}
        </p>
      </div>
      <div class="stat-card bg-white rounded-lg p-3 shadow-sm">
        <p class="text-xs uppercase text-slate-500 font-medium">Maximum</p>
        <p class="text-lg font-bold text-slate-800">${formatValueJS(max, chartData.valueType)}</p>
      </div>
      <div class="stat-card bg-white rounded-lg p-3 shadow-sm">
        <p class="text-xs uppercase text-slate-500 font-medium">Minimum</p>
        <p class="text-lg font-bold text-slate-800">${formatValueJS(min, chartData.valueType)}</p>
      </div>
      <div class="stat-card bg-white rounded-lg p-3 shadow-sm">
        <p class="text-xs uppercase text-slate-500 font-medium">Average</p>
        <p class="text-lg font-bold text-slate-800">${formatValueJS(avg, chartData.valueType)}</p>
      </div>
    </div>

    <!-- Chart Container -->
    <div class="chart-container flex-1 p-3 sm:p-6 min-h-0">
      <div class="bg-white rounded-xl shadow-sm border border-slate-200 h-full p-2 sm:p-4">
        <canvas id="chartCanvas"></canvas>
      </div>
    </div>

    <!-- Footer -->
    <div class="footer-content px-4 sm:px-6 py-2 sm:py-3 bg-white border-t border-slate-200 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
      <div class="footer-legend flex flex-wrap items-center gap-3 sm:gap-5">
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 rounded bg-blue-600"></div>
          <span>Latest</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 rounded bg-blue-300"></div>
          <span>Historical</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 rounded-full bg-blue-900 border border-white"></div>
          <span>Trend</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-4 h-2 rounded" style="background: linear-gradient(180deg, rgba(59,130,246,0.4) 0%, rgba(59,130,246,0.05) 100%);"></div>
          <span>Area</span>
        </div>
        <div class="flex items-center gap-1.5">
          <svg width="16" height="2" class="text-slate-400">
            <line x1="0" y1="1" x2="16" y2="1" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"/>
          </svg>
          <span>Avg</span>
        </div>
      </div>
      <p class="text-slate-400 text-[10px] sm:text-xs">${validData[0]?.period || '--'} → ${validData[validData.length - 1]?.period || '--'}</p>
    </div>
  </div>

  <script>
    // Data from parent
    const chartData = ${JSON.stringify(validData)};
    const valueType = '${chartData.valueType}';
    const avgValue = ${avg};

    // Format value helper
    function formatValue(value, type) {
      if (value === null || value === undefined) return '--';
      
      if (type === 'percent') return value.toFixed(2) + '%';
      if (type === 'ratio') return value.toFixed(2);
      if (type === 'eps') return (value < 0 ? '-' : '') + '$' + Math.abs(value).toFixed(2);
      if (type === 'shares') {
        const abs = Math.abs(value);
        if (abs >= 1e9) return (value / 1e9).toFixed(2) + 'B';
        if (abs >= 1e6) return (value / 1e6).toFixed(2) + 'M';
        if (abs >= 1e3) return (value / 1e3).toFixed(2) + 'K';
        return value.toFixed(0);
      }
      
      const abs = Math.abs(value);
      const sign = value < 0 ? '-' : '';
      if (abs >= 1e12) return sign + '$' + (abs / 1e12).toFixed(2) + 'T';
      if (abs >= 1e9) return sign + '$' + (abs / 1e9).toFixed(2) + 'B';
      if (abs >= 1e6) return sign + '$' + (abs / 1e6).toFixed(2) + 'M';
      if (abs >= 1e3) return sign + '$' + (abs / 1e3).toFixed(2) + 'K';
      return sign + '$' + abs.toFixed(0);
    }

    // Create chart
    const ctx = document.getElementById('chartCanvas').getContext('2d');
    
    const labels = chartData.map(d => d.period);
    const values = chartData.map(d => d.value);
    const backgroundColors = chartData.map((d, i) => 
      i === chartData.length - 1 ? '#2563eb' : '#93c5fd'
    );
    
    // Create gradient for area
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.4)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.02)');

    // Average line data (same value for all points)
    const avgData = values.map(() => avgValue);

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          // 1. Area fill (behind everything)
          {
            type: 'line',
            label: 'Trend Area',
            data: values,
            fill: true,
            backgroundColor: gradient,
            borderWidth: 0,
            tension: 0.4,
            pointRadius: 0,
            order: 3
          },
          // 2. Bars
          {
            type: 'bar',
            label: '${chartData.metricLabel}',
            data: values,
            backgroundColor: backgroundColors,
            borderRadius: 6,
            maxBarThickness: 50,
            order: 2
          },
          // 3. Line with points (on top)
          {
            type: 'line',
            label: 'Trend Line',
            data: values,
            borderColor: '#1e40af',
            borderWidth: 2.5,
            tension: 0.4,
            fill: false,
            pointBackgroundColor: '#1e40af',
            pointBorderColor: '#ffffff',
            pointBorderWidth: 2,
            pointRadius: 5,
            pointHoverRadius: 7,
            order: 1
          },
          // 4. Average line (dashed)
          {
            type: 'line',
            label: 'Average',
            data: avgData,
            borderColor: '#94a3b8',
            borderWidth: 2,
            borderDash: [8, 4],
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 0,
            order: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1e293b',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            padding: 12,
            cornerRadius: 8,
            displayColors: false,
            callbacks: {
              label: function(context) {
                if (context.dataset.label === 'Average') {
                  return 'Avg: ' + formatValue(context.parsed.y, valueType);
                }
                if (context.dataset.label === 'Trend Area' || context.dataset.label === 'Trend Line') {
                  return null; // Hide these from tooltip
                }
                return formatValue(context.parsed.y, valueType);
              },
              filter: function(tooltipItem) {
                return tooltipItem.dataset.label !== 'Trend Area' && tooltipItem.dataset.label !== 'Trend Line';
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { 
              maxRotation: 45, 
              minRotation: 45,
              font: { size: 11, family: 'Inter' },
              color: '#64748b'
            }
          },
          y: {
            grid: { 
              color: '#e2e8f0',
              drawBorder: false
            },
            ticks: {
              font: { size: 11, family: 'Inter' },
              color: '#64748b',
              callback: function(value) {
                return formatValue(value, valueType);
              }
            }
          }
        }
      }
    });

    // Handle window resize
    let resizeTimeout;
    window.addEventListener('resize', function() {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(function() {
        // Chart.js auto-resizes with responsive: true
        console.log('📐 Window resized');
      }, 100);
    });

    console.log('✅ Financial Chart initialized with full styling');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Financial Chart injected');
}

