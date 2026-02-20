/**
 * IPO Window Injector
 * 
 * Standalone window for IPO calendar
 */

import { getUserTimezoneForWindow, getUserFontForWindow, getFontConfig, WindowConfig, formatValueJS } from './base';

// ============================================================
// IPO WINDOW
// ============================================================

export interface IPOWindowData {
  apiBaseUrl: string;
}

export function openIPOWindow(
  data: IPOWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 1000,
    height = 700,
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

  injectIPOContent(newWindow, data, config);

  return newWindow;
}

function injectIPOContent(
  targetWindow: Window,
  data: IPOWindowData,
  config: WindowConfig
): void {
  const { title } = config;
  const userTimezone = getUserTimezoneForWindow();
  const userFont = getUserFontForWindow();
  const fontConfig = getFontConfig(userFont);

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
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
    }
  </script>
  
  <style>
    body { font-family: 'Inter', sans-serif; margin: 0; padding: 0; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
    tr:hover { background-color: rgba(59, 130, 246, 0.05); }
    .status-pending { background: #fef3c7; color: #92400e; }
    .status-new { background: #d1fae5; color: #065f46; }
    .status-history { background: #dbeafe; color: #1e40af; }
    .status-rumor { background: #f3e8ff; color: #6b21a8; }
    .status-withdrawn { background: #fee2e2; color: #991b1b; }
    .status-direct_listing_process { background: #cffafe; color: #0e7490; }
  </style>
</head>
<body class="bg-slate-50">
  <div id="root" class="h-screen flex flex-col"></div>

  <script>
    const API_URL = '${data.apiBaseUrl}';
    const USER_TIMEZONE = '${userTimezone}';
    let allIPOs = [];
    let currentFilter = 'pending';
    let isLoading = true;

    const STATUS_MAP = {
      pending: { label: 'PENDING', class: 'status-pending' },
      new: { label: 'NEW', class: 'status-new' },
      history: { label: 'LISTED', class: 'status-history' },
      rumor: { label: 'RUMOR', class: 'status-rumor' },
      withdrawn: { label: 'WITHDRAWN', class: 'status-withdrawn' },
      direct_listing_process: { label: 'DLP', class: 'status-direct_listing_process' },
      postponed: { label: 'POSTPONED', class: 'status-pending' }
    };

    const EXCHANGE_MAP = {
      XNAS: 'NASDAQ', XNYS: 'NYSE', XASE: 'AMEX', ARCX: 'ARCA', BATS: 'BATS'
    };

    function formatPrice(p) {
      return p ? '$' + p.toFixed(2) : '—';
    }

    function formatSize(s) {
      if (!s) return '—';
      if (s >= 1e9) return '$' + (s / 1e9).toFixed(1) + 'B';
      if (s >= 1e6) return '$' + (s / 1e6).toFixed(1) + 'M';
      if (s >= 1e3) return '$' + (s / 1e3).toFixed(0) + 'K';
      return '$' + s;
    }

    function formatShares(s) {
      if (!s) return '—';
      if (s >= 1e6) return (s / 1e6).toFixed(1) + 'M';
      if (s >= 1e3) return (s / 1e3).toFixed(0) + 'K';
      return s.toString();
    }

    function formatDate(d) {
      if (!d) return '—';
      try {
        const dt = new Date(d);
        return dt.toLocaleDateString('en-US', { timeZone: USER_TIMEZONE, month: 'short', day: 'numeric', year: '2-digit' });
      } catch { return d; }
    }

    async function fetchIPOs(forceRefresh = false) {
      isLoading = true;
      render();
      
      try {
        const url = API_URL + '/api/v1/ipos?limit=500' + (forceRefresh ? '&force_refresh=true' : '');
        const res = await fetch(url);
        const data = await res.json();
        allIPOs = data.results || [];
      } catch (e) {
        console.error('Error fetching IPOs:', e);
      }
      
      isLoading = false;
      render();
    }

    function getFilteredIPOs() {
      if (currentFilter === 'all') return allIPOs;
      return allIPOs.filter(ipo => ipo.ipo_status === currentFilter);
    }

    function getStatusCounts() {
      const counts = { all: allIPOs.length };
      allIPOs.forEach(ipo => {
        const s = ipo.ipo_status || 'unknown';
        counts[s] = (counts[s] || 0) + 1;
      });
      return counts;
    }

    function setFilter(f) {
      currentFilter = f;
      render();
    }

    function render() {
      const filtered = getFilteredIPOs();
      const counts = getStatusCounts();
      
      const tabs = [
        { id: 'pending', label: 'Pending (' + (counts.pending || 0) + ')' },
        { id: 'new', label: 'New (' + (counts.new || 0) + ')' },
        { id: 'direct_listing_process', label: 'DLP (' + (counts.direct_listing_process || 0) + ')' },
        { id: 'rumor', label: 'Rumor (' + (counts.rumor || 0) + ')' },
        { id: 'history', label: 'Listed (' + (counts.history || 0) + ')' },
        { id: 'all', label: 'All (' + allIPOs.length + ')' }
      ];

      document.getElementById('root').innerHTML = \`
        <div class="h-screen flex flex-col bg-white">
          <!-- Header -->
          <div class="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
            <div class="flex items-center gap-2">
              <svg class="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
              </svg>
              <span class="text-sm font-semibold text-slate-700">IPOs</span>
              <span class="text-xs text-slate-400">(\${filtered.length})</span>
            </div>
            <button onclick="fetchIPOs(true)" class="p-1 text-slate-400 hover:text-blue-600">
              <svg class="w-4 h-4 \${isLoading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
              </svg>
            </button>
          </div>

          <!-- Tabs -->
          <div class="flex items-center gap-1 px-2 py-1.5 bg-slate-100 border-b border-slate-200 overflow-x-auto">
            \${tabs.map(t => \`
              <button onclick="setFilter('\${t.id}')" 
                class="px-2 py-0.5 text-[10px] font-medium rounded whitespace-nowrap \${currentFilter === t.id ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-200'}">
                \${t.label}
              </button>
            \`).join('')}
          </div>

          <!-- Table -->
          <div class="flex-1 overflow-auto">
            \${isLoading && allIPOs.length === 0 ? \`
              <div class="flex items-center justify-center h-full">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            \` : \`
              <table class="w-full text-[10px] border-collapse">
                <thead class="bg-slate-100 sticky top-0">
                  <tr class="text-left text-slate-500 uppercase tracking-wide">
                    <th class="px-1 py-1 font-medium w-14">Ticker</th>
                    <th class="px-1 py-1 font-medium w-12 text-center">Status</th>
                    <th class="px-1 py-1 font-medium">Company</th>
                    <th class="px-1 py-1 font-medium w-14 text-center">Exch</th>
                    <th class="px-1 py-1 font-medium w-16 text-right">Price</th>
                    <th class="px-1 py-1 font-medium w-16 text-right">Size</th>
                    <th class="px-1 py-1 font-medium w-14 text-right">Shares</th>
                    <th class="px-1 py-1 font-medium w-16 text-center">Date</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-50">
                  \${filtered.length === 0 ? \`
                    <tr><td colspan="8" class="px-2 py-4 text-center text-slate-400">No IPOs found</td></tr>
                  \` : filtered.map(ipo => {
                    const st = STATUS_MAP[ipo.ipo_status] || STATUS_MAP.pending;
                    const priceRange = ipo.lowest_offer_price && ipo.highest_offer_price && ipo.lowest_offer_price !== ipo.highest_offer_price
                      ? '$' + ipo.lowest_offer_price + '-' + ipo.highest_offer_price
                      : ipo.final_issue_price ? formatPrice(ipo.final_issue_price) : ipo.lowest_offer_price ? formatPrice(ipo.lowest_offer_price) : '—';
                    return \`
                      <tr>
                        <td class="px-1 py-0.5"><span class="font-mono font-semibold text-blue-600">\${ipo.ticker}</span></td>
                        <td class="px-1 py-0.5 text-center"><span class="px-1 py-0 rounded text-[8px] font-medium \${st.class}">\${st.label}</span></td>
                        <td class="px-1 py-0.5 text-slate-700 truncate max-w-[220px]" title="\${ipo.issuer_name}">\${ipo.issuer_name}</td>
                        <td class="px-1 py-0.5 text-center text-slate-500 font-mono">\${EXCHANGE_MAP[ipo.primary_exchange] || ipo.primary_exchange || '—'}</td>
                        <td class="px-1 py-0.5 text-right font-mono text-slate-700">\${priceRange}</td>
                        <td class="px-1 py-0.5 text-right font-mono text-slate-600">\${formatSize(ipo.total_offer_size)}</td>
                        <td class="px-1 py-0.5 text-right font-mono text-slate-500">\${formatShares(ipo.max_shares_offered)}</td>
                        <td class="px-1 py-0.5 text-center font-mono text-slate-500">\${formatDate(ipo.listing_date || ipo.announced_date)}</td>
                      </tr>
                    \`;
                  }).join('')}
                </tbody>
              </table>
            \`}
          </div>

          <!-- Footer -->
          <div class="px-2 py-1 bg-slate-50 border-t border-slate-200 text-[9px] text-slate-400 flex justify-between">
            <span>Polygon.io • Updated daily • 24h cache</span>
            <span>\${filtered.length} of \${allIPOs.length} IPOs</span>
          </div>
        </div>
      \`;
    }

    // Init
    fetchIPOs();
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

}


// Helper for HTML template
