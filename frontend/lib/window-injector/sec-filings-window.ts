/**
 * SEC Filings Window Injector
 * 
 * Standalone window for real-time SEC filings
 */

import { getUserTimezoneForWindow, getUserFontForWindow, getFontConfig, WindowConfig } from './base';

// ============================================================================
// SEC FILINGS WINDOW
// ============================================================================

export interface SECFilingsWindowData {
  wsUrl: string;
  workerUrl: string;
  secApiBaseUrl: string;
  token?: string; // JWT token for WebSocket authentication
}

export async function openSECFilingsWindow(
  data: SECFilingsWindowData,
  config: WindowConfig
): Promise<Window | null> {
  const {
    width = 1300,
    height = 850,
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

  injectSECFilingsContent(newWindow, data, config);

  return newWindow;
}

function injectSECFilingsContent(
  targetWindow: Window,
  data: SECFilingsWindowData,
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
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: Inter, sans-serif; color: #171717; background: #ffffff; margin: 0; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
    *::-webkit-scrollbar { width: 8px; height: 8px; }
    *::-webkit-scrollbar-track { background: #f1f5f9; }
    *::-webkit-scrollbar-thumb { background: #cbd5e1; }
    *::-webkit-scrollbar-thumb:hover { background: #3b82f6; }
    .filing-row:hover { background-color: #f8fafc; }
    .filing-row.live { background-color: rgba(16, 185, 129, 0.05); }
  </style>
</head>
<body class="bg-white overflow-hidden">
  <div id="root" class="h-screen flex flex-col"></div>

  <script>
    const CONFIG = ${JSON.stringify(data)};
    const USER_TIMEZONE = '${userTimezone}';
    
    // ============================================================
    // STATE (same as floating window React)
    // ============================================================
    let sharedWorker = null;
    let workerPort = null;
    let isConnected = false;
    let isPaused = false;
    let isLoading = false;
    let historicalFilings = [];
    let realtimeFilings = [];
    let seenAccessions = new Set();
    let realtimeAccessions = new Set();
    let pausedBuffer = [];
    let totalResults = 0;
    let currentPage = 1;
    const PAGE_SIZE = 100;
    
    // Filters state
    let filters = {
      ticker: '',
      categories: [],
      formTypes: [],
      items8K: [],
      dateFrom: '',
      dateTo: '',
    };
    
    // Filing categories (exact copy from sec-filing-types.ts)
    const FILING_CATEGORIES = {
      offerings: {
        label: 'Offerings',
        types: ['S-1', 'S-1/A', 'S-1MEF', 'S-3', 'S-3/A', 'S-3ASR', 'S-3MEF', 'S-3D', 'F-1', 'F-1/A', 'F-3', 'F-3ASR', '424B1', '424B2', '424B3', '424B4', '424B5', '424B7', '424B8', 'FWP', 'POS AM', 'EFFECT', '1-A', '1-A POS', 'D', 'D/A'],
      },
      insider: {
        label: 'Insider',
        types: ['3', '4', '5', '144'],
      },
      institutional: {
        label: 'Institutional',
        types: ['SC 13D', 'SC 13D/A', 'SC 13G', 'SC 13G/A', '13F-HR', '13F-NT'],
      },
      material: {
        label: '8-K Events',
        types: ['8-K', '8-K/A', '6-K', '6-K/A'],
      },
      mna: {
        label: 'M&A',
        types: ['S-4', 'S-4/A', 'F-4', 'F-4/A', '425', 'SC TO-T', 'SC TO-I', 'SC TO-C', 'SC 14D9', 'SC 14D9/A', 'SC 13E3', 'DEFM14A'],
      },
      distress: {
        label: 'Distress',
        types: ['NT 10-K', 'NT 10-Q', 'NT 20-F', '15-12B', '15-12G', '15-15D', '25-NSE', 'RW'],
      },
    };
    
    // Quick filters (exact copy from sec-filing-types.ts)
    const QUICK_FILTERS = {
      offerings: { label: 'Offerings', categories: ['offerings'], items8K: [] },
      insider: { label: 'Insider', categories: ['insider'], items8K: [] },
      institutional: { label: '13D/13F', categories: ['institutional'], items8K: [] },
      critical8K: { label: '8-K Critical', categories: [], items8K: ['1.03', '2.02', '2.04', '2.06', '3.01', '4.02', '5.01'] },
      mna: { label: 'M&A', categories: ['mna'], items8K: [] },
      distress: { label: 'Distress', categories: ['distress'], items8K: ['1.03', '2.04', '3.01'] },
    };
    
    console.log('🚀 [SEC Window] Init');
    
    // ============================================================
    // HELPERS
    // ============================================================
    function getFilterFormTypes() {
      const types = [];
      filters.categories.forEach(catKey => {
        const cat = FILING_CATEGORIES[catKey];
        if (cat) types.push(...cat.types);
      });
      types.push(...filters.formTypes);
      return [...new Set(types)];
    }
    
    function matchesRealtimeFilters(filing) {
      if (filters.ticker && filing.ticker !== filters.ticker.toUpperCase()) return false;
      
      const allowedTypes = getFilterFormTypes();
      if (allowedTypes.length > 0) {
        const matches = allowedTypes.some(t => filing.formType === t || filing.formType.startsWith(t + '/'));
        if (!matches) return false;
      }
      
      if (filters.items8K.length > 0) {
        if (!filing.formType.startsWith('8-K')) return false;
        const filingItems = format8KItems(filing.items);
        const hasItem = filters.items8K.some(item => filingItems.includes(item));
        if (!hasItem) return false;
      }
      
      return true;
    }
    
    function format8KItems(items) {
      if (!items || items.length === 0) return '';
      return items.map(item => {
        const match = item.match(/Item\\s+(\\d+\\.\\d+)/i);
        return match ? match[1] : null;
      }).filter(Boolean).join(', ');
    }
    
    // ============================================================
    // FETCH FILINGS (same logic as floating window)
    // ============================================================
    async function fetchFilings(page = 1) {
      isLoading = true;
      renderTable();
      
      try {
        const params = new URLSearchParams();
        if (filters.ticker) params.append('ticker', filters.ticker.toUpperCase());
        
        const formTypes = getFilterFormTypes();
        if (formTypes.length > 0) params.append('form_types', formTypes.join(','));
        if (filters.items8K.length > 0) params.append('items', filters.items8K.join(','));
        if (filters.dateFrom) params.append('date_from', filters.dateFrom);
        if (filters.dateTo) params.append('date_to', filters.dateTo);
        
        params.append('page_size', PAGE_SIZE.toString());
        params.append('from_index', ((page - 1) * PAGE_SIZE).toString());
        
        console.log('📄 SEC Query:', CONFIG.secApiBaseUrl + '/api/v1/filings/live?' + params);
        const response = await fetch(CONFIG.secApiBaseUrl + '/api/v1/filings/live?' + params);
        
        if (!response.ok) throw new Error('HTTP ' + response.status);
        
        const data = await response.json();
        
        historicalFilings = data.filings || [];
        totalResults = data.total || 0;
        currentPage = page;
        
        // Track seen accessions
        seenAccessions.clear();
        historicalFilings.forEach(f => seenAccessions.add(f.accessionNo));
        
      } catch (error) {
        console.error('❌ Error fetching filings:', error);
        historicalFilings = [];
        totalResults = 0;
      }
      
      isLoading = false;
      renderTable();
    }
    
    // ============================================================
    // WEBSOCKET (SharedWorker)
    // ============================================================
    function initWebSocket() {
      try {
        sharedWorker = new SharedWorker(CONFIG.workerUrl, { name: 'tradeul-websocket' });
        workerPort = sharedWorker.port;
        
        workerPort.onmessage = (event) => {
          const msg = event.data;
          
          switch (msg.type) {
            case 'message':
              handleWebSocketMessage(msg.data);
              break;
            case 'status':
              isConnected = msg.isConnected;
              if (msg.isConnected) {
                workerPort.postMessage({ action: 'subscribe_sec' });
              }
              renderTable();
              break;
          }
        };
        
        workerPort.start();
        workerPort.postMessage({ action: 'connect', url: CONFIG.wsUrl });
        
      } catch (error) {
        console.error('❌ [SEC Window] WebSocket init failed:', error);
      }
    }
    
    function handleWebSocketMessage(message) {
      if (message.type === 'sec_filing' && message.filing) {
        const filing = message.filing;
        const id = filing.accessionNo;
        
        if (id && !seenAccessions.has(id)) {
          seenAccessions.add(id);
          realtimeAccessions.add(id);
          const liveFiling = { ...filing, isLive: true };
          
          if (isPaused) {
            pausedBuffer.unshift(liveFiling);
          } else {
            realtimeFilings.unshift(liveFiling);
            realtimeFilings = realtimeFilings.slice(0, 50); // Keep max 50
            renderTable();
          }
        }
      }
    }
    
    // ============================================================
    // FILTER HANDLERS
    // ============================================================
    window.handleTickerSearch = function(e) {
      e.preventDefault();
      filters.ticker = document.getElementById('ticker-input').value.trim();
      fetchFilings(1);
    }
    
    window.clearTicker = function() {
      filters.ticker = '';
      document.getElementById('ticker-input').value = '';
      fetchFilings(1);
    }
    
    window.setDateFrom = function(val) {
      filters.dateFrom = val;
      fetchFilings(1);
    }
    
    window.setDateTo = function(val) {
      filters.dateTo = val;
      fetchFilings(1);
    }
    
    window.clearDates = function() {
      filters.dateFrom = '';
      filters.dateTo = '';
      fetchFilings(1);
    }
    
    window.toggleQuickFilter = function(key) {
      const qf = QUICK_FILTERS[key];
      const isActive = qf.categories.length > 0 
        ? qf.categories.every(c => filters.categories.includes(c))
        : qf.items8K.length > 0 
          ? qf.items8K.every(i => filters.items8K.includes(i))
          : false;
      
      if (isActive) {
        // Deactivate
        filters.categories = filters.categories.filter(c => !qf.categories.includes(c));
        filters.items8K = filters.items8K.filter(i => !qf.items8K.includes(i));
      } else {
        // Activate (replace)
        filters.categories = [...qf.categories];
        filters.items8K = [...qf.items8K];
      }
      fetchFilings(1);
    }
    
    window.clearAllFilters = function() {
      filters = { ticker: '', categories: [], formTypes: [], items8K: [], dateFrom: '', dateTo: '' };
      realtimeFilings = [];
      realtimeAccessions.clear();
      fetchFilings(1);
    }
    
    window.togglePause = function() {
      isPaused = !isPaused;
      if (!isPaused && pausedBuffer.length > 0) {
        realtimeFilings = [...pausedBuffer, ...realtimeFilings];
        pausedBuffer = [];
      }
      renderTable();
    }
    
    window.goToPage = function(page) {
      fetchFilings(page);
    }
    
    // ============================================================
    // RENDER (exact replica of floating window)
    // ============================================================
    function formatDateTime(isoString) {
      if (!isoString) return { date: '—', time: '—' };
      try {
        const d = new Date(isoString);
        return {
          date: d.toLocaleDateString('en-US', { timeZone: USER_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit' }),
          time: d.toLocaleTimeString('en-US', { timeZone: USER_TIMEZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
        };
      } catch { return { date: '—', time: '—' }; }
    }
    
    function getFormTypeColor(formType) {
      const ft = formType || '';
      for (const [key, cat] of Object.entries(FILING_CATEGORIES)) {
        if (cat.types.some(t => ft === t || ft.startsWith(t + '/'))) {
          switch (key) {
            case 'offerings': return 'bg-rose-50 text-rose-700 border-rose-200';
            case 'insider': return 'bg-amber-50 text-amber-700 border-amber-200';
            case 'institutional': return 'bg-emerald-50 text-emerald-700 border-emerald-200';
            case 'material': return 'bg-blue-50 text-blue-700 border-blue-200';
            case 'mna': return 'bg-purple-50 text-purple-700 border-purple-200';
            case 'distress': return 'bg-red-50 text-red-700 border-red-200';
          }
        }
      }
      return 'bg-slate-50 text-slate-600 border-slate-200';
    }
    
    function truncateDescription(desc, maxLen = 80) {
      if (!desc) return '';
      return desc.length > maxLen ? desc.substring(0, maxLen) + '...' : desc;
    }
    
    function renderTable() {
      // Merge realtime + historical (same logic as floating window)
      const filingMap = new Map();
      
      // Historical first
      historicalFilings.forEach(f => {
        if (f.accessionNo && !filingMap.has(f.accessionNo)) {
          filingMap.set(f.accessionNo, f);
        }
      });
      
      // Realtime (filtered) - goes on top
      realtimeFilings.filter(matchesRealtimeFilters).forEach(f => {
        if (f.accessionNo && !filingMap.has(f.accessionNo)) {
          filingMap.set(f.accessionNo, { ...f, isLive: true });
        }
      });
      
      const displayedFilings = Array.from(filingMap.values());
      displayedFilings.sort((a, b) => new Date(b.filedAt).getTime() - new Date(a.filedAt).getTime());
      
      const liveCount = realtimeFilings.filter(matchesRealtimeFilters).length;
      const hasFilters = filters.ticker || filters.categories.length > 0 || filters.items8K.length > 0 || filters.dateFrom || filters.dateTo;
      const totalPages = Math.max(1, Math.ceil(totalResults / PAGE_SIZE));
      
      const html = \`
        <div class="h-screen flex flex-col bg-white">
          <!-- Header Row 1: Search, Dates, Count -->
          <div class="flex items-center gap-2 px-3 py-1 border-b border-slate-100 bg-slate-50">
            <form onsubmit="handleTickerSearch(event)" class="flex items-center gap-1">
              <input id="ticker-input" type="text" value="\${filters.ticker}" placeholder="Ticker"
                class="w-20 px-2 py-0.5 text-[10px] border border-slate-200 rounded focus:outline-none focus:border-blue-400" />
              <button type="submit" class="px-2 py-0.5 text-[10px] font-medium bg-blue-600 text-white rounded hover:bg-blue-700">
                \${isLoading ? '...' : 'Go'}
              </button>
            </form>
            
            <span class="text-slate-300">|</span>
            
            <div class="flex items-center gap-1 text-[10px]">
              <input type="date" value="\${filters.dateFrom}" onchange="setDateFrom(this.value)" 
                class="w-[100px] px-1 py-0.5 text-[10px] border border-slate-200 rounded focus:outline-none focus:border-blue-400" />
              <span class="text-slate-300">-</span>
              <input type="date" value="\${filters.dateTo}" onchange="setDateTo(this.value)"
                class="w-[100px] px-1 py-0.5 text-[10px] border border-slate-200 rounded focus:outline-none focus:border-blue-400" />
              \${(filters.dateFrom || filters.dateTo) ? '<button onclick="clearDates()" class="p-0.5 text-slate-400 hover:text-slate-600">✕</button>' : ''}
            </div>
            
            <div class="flex-1"></div>
            
            <div class="flex items-center gap-2 text-[10px] text-slate-500">
              <span class="tabular-nums font-medium">\${displayedFilings.length}</span>
              \${liveCount > 0 ? \`<span class="text-emerald-600 flex items-center gap-1"><span class="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>\${liveCount}</span>\` : ''}
            </div>
            
            \${hasFilters ? '<button onclick="clearAllFilters()" class="px-1.5 py-0.5 text-[9px] text-slate-500 hover:text-slate-700 border border-slate-200 rounded">Clear</button>' : ''}
          </div>
          
          <!-- Header Row 2: Quick Filters -->
          <div class="flex items-center gap-1 px-3 py-1 border-b border-slate-200 bg-white">
            \${Object.entries(QUICK_FILTERS).map(([key, qf]) => {
              const isActive = qf.categories.length > 0 
                ? qf.categories.every(c => filters.categories.includes(c))
                : qf.items8K.length > 0 
                  ? qf.items8K.every(i => filters.items8K.includes(i))
                  : false;
              return \`<button onclick="toggleQuickFilter('\${key}')" class="px-2 py-0.5 text-[10px] rounded border \${isActive ? 'bg-blue-600 text-white border-blue-600' : 'text-slate-600 border-slate-200 hover:border-slate-400'}">\${qf.label}</button>\`;
            }).join('')}
            
            <div class="flex-1"></div>
            
            <button onclick="togglePause()" class="px-2 py-0.5 text-[10px] font-medium rounded \${isPaused ? 'bg-emerald-600 text-white' : 'bg-amber-600 text-white'}">\${isPaused ? '▶ Play' : '❚❚ Pause'}</button>
            \${isPaused && pausedBuffer.length > 0 ? '<span class="text-amber-600 text-xs">(+' + pausedBuffer.length + ')</span>' : ''}
          </div>
          
          <!-- Table -->
          <div class="flex-1 overflow-auto">
            <table class="w-full border-collapse text-[11px]">
              <thead class="bg-slate-50 sticky top-0">
                <tr>
                  <th class="px-3 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Ticker</th>
                  <th class="px-3 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Form</th>
                  <th class="px-3 py-1.5 text-left text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Description</th>
                  <th class="px-3 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Date</th>
                  <th class="px-3 py-1.5 text-right text-[9px] font-semibold text-slate-500 uppercase tracking-wider">Time</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                \${isLoading ? \`
                  <tr><td colspan="5" class="px-3 py-8 text-center text-slate-500">Loading filings...</td></tr>
                \` : displayedFilings.length === 0 ? \`
                  <tr><td colspan="5" class="px-3 py-8 text-center text-slate-500">No filings found</td></tr>
                \` : displayedFilings.map(filing => {
                  const dt = formatDateTime(filing.filedAt);
                  const formColorClass = getFormTypeColor(filing.formType);
                  const isRealtime = realtimeAccessions.has(filing.accessionNo);
                  const link = filing.linkToHtml || filing.linkToFilingDetails || '';
                  const itemsText = filing.formType && filing.formType.startsWith('8-K') ? format8KItems(filing.items) : '';
                  
                  return \`
                    <tr class="hover:bg-blue-50 cursor-pointer \${isRealtime ? 'bg-emerald-50/30' : ''}" onclick="window.open('\${link}', '_blank')">
                      <td class="px-3 py-1 whitespace-nowrap">
                        <span class="font-medium \${filing.ticker ? 'text-slate-900' : 'text-slate-400'}">\${filing.ticker || '--'}</span>
                      </td>
                      <td class="px-3 py-1 whitespace-nowrap">
                        <span class="inline-block px-1.5 py-0.5 text-[10px] rounded border \${formColorClass}">\${filing.formType}</span>
                      </td>
                      <td class="px-3 py-1">
                        <span class="text-slate-600 truncate">
                          \${itemsText ? '<span class="text-slate-400 mr-1">[' + itemsText + ']</span>' : ''}
                          \${truncateDescription(filing.description, itemsText ? 50 : 80)}
                        </span>
                      </td>
                      <td class="px-3 py-1 whitespace-nowrap text-right text-slate-500 tabular-nums">\${dt.date}</td>
                      <td class="px-3 py-1 whitespace-nowrap text-right text-slate-400 tabular-nums">\${dt.time}</td>
                    </tr>
                  \`;
                }).join('')}
              </tbody>
            </table>
          </div>
          
          <!-- Footer: Pagination -->
          <div class="flex items-center justify-between px-3 py-1 border-t border-slate-200 bg-slate-50 text-[10px] text-slate-500">
            <div class="flex items-center gap-2">
              <span class="tabular-nums">\${totalResults.toLocaleString()} total</span>
              <span class="text-slate-300">|</span>
              <span>Page \${currentPage} of \${totalPages}</span>
            </div>
            
            <div class="flex items-center gap-1">
              <button onclick="goToPage(1)" \${currentPage === 1 ? 'disabled' : ''} class="px-1.5 py-0.5 rounded text-slate-600 hover:bg-slate-100 disabled:opacity-30">«</button>
              <button onclick="goToPage(\${currentPage - 1})" \${currentPage === 1 ? 'disabled' : ''} class="px-1.5 py-0.5 rounded text-slate-600 hover:bg-slate-100 disabled:opacity-30">‹</button>
              \${[...Array(5)].map((_, i) => {
                const p = currentPage - 2 + i;
                if (p < 1 || p > totalPages) return '';
                return \`<button onclick="goToPage(\${p})" class="px-1.5 py-0.5 rounded tabular-nums \${p === currentPage ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'}">\${p}</button>\`;
              }).join('')}
              <button onclick="goToPage(\${currentPage + 1})" \${currentPage >= totalPages ? 'disabled' : ''} class="px-1.5 py-0.5 rounded text-slate-600 hover:bg-slate-100 disabled:opacity-30">›</button>
              <button onclick="goToPage(\${totalPages})" \${currentPage >= totalPages ? 'disabled' : ''} class="px-1.5 py-0.5 rounded text-slate-600 hover:bg-slate-100 disabled:opacity-30">»</button>
            </div>
            
            <div class="flex items-center gap-1.5">
              <span class="w-1.5 h-1.5 rounded-full \${isConnected ? 'bg-emerald-500' : 'bg-slate-300'}"></span>
              <span>\${isConnected ? 'Live' : 'Offline'}</span>
            </div>
          </div>
        </div>
      \`;
      
      document.getElementById('root').innerHTML = html;
    }
    
    // ============================================================
    // INIT
    // ============================================================
    fetchFilings(1);
    initWebSocket();
    console.log('✅ SEC Window initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] SEC Filings injected');
}

