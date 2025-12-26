/**
 * Sistema de Ventanas Inyectadas para Scanner
 * 
 * - Abre about:blank
 * - Inyecta HTML con Tailwind CSS
 * - Conecta al SharedWorker existente
 * - Diseño IDÉNTICO al scanner original
 */

export interface ScannerWindowData {
  listName: string;
  categoryName: string;
  wsUrl: string;
  workerUrl: string; // URL absoluta del SharedWorker
}

export interface WindowConfig {
  title: string;
  width?: number;
  height?: number;
  centered?: boolean;
}

export function openScannerWindow(
  data: ScannerWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 1400,
    height = 900,
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

  injectScannerContent(newWindow, data, config);

  return newWindow;
}

function injectScannerContent(
  targetWindow: Window,
  data: ScannerWindowData,
  config: WindowConfig
): void {
  const { title } = config;

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <!-- Fuentes EXACTAS del proyecto -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <!-- Tailwind CSS with custom configuration -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          },
          colors: {
            background: '#FFFFFF',
            foreground: '#0F172A',
            primary: {
              DEFAULT: '#2563EB',
              hover: '#1D4ED8'
            },
            border: '#E2E8F0',
            muted: '#F8FAFC',
            success: '#10B981',
            danger: '#EF4444'
          }
        }
      }
    }
  </script>
  
  <style>
    /* CSS Global EXACTO del proyecto */
    * {
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    
    body {
      font-family: Inter, sans-serif;
      color: #171717;
      background: #ffffff;
    }
    
    /* Estilos de tabla EXACTOS */
    table {
      color: #171717 !important;
    }
    
    table td, table th {
      color: inherit !important;
      transition: width 0.1s ease-out, background-color 0.15s ease;
    }
    
    /* Font-mono con configuración EXACTA */
    .font-mono {
      font-family: 'JetBrains Mono', monospace !important;
      color: #0f172a !important;
      font-weight: 500;
    }
    
    /* Scrollbar personalizada */
    *::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    
    *::-webkit-scrollbar-track {
      background: #f1f5f9;
      border-left: 1px solid #e2e8f0;
    }
    
    *::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      transition: background 0.2s;
    }
    
    *::-webkit-scrollbar-thumb:hover {
      background: #3b82f6;
    }
    
    /* Header sticky con sombra */
    .sticky-header {
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
      backdrop-filter: blur(10px);
      background-color: rgba(255, 255, 255, 0.98);
    }
    
    /* Cursor pointer */
    .cursor-pointer {
      cursor: pointer;
    }
    
    /* Helpers para flexbox */
    .flex {
      display: flex;
    }
    
    .items-center {
      align-items: center;
    }
    
    .justify-end {
      justify-content: flex-end;
    }
    
    .gap-1 {
      gap: 0.25rem;
    }
    
    /* Sort icon styling */
    .sort-icon {
      display: inline-flex;
      align-items: center;
    }
  </style>
</head>
<body class="bg-white overflow-hidden font-sans">
  <div id="root" class="h-screen flex flex-col">
    <div class="flex items-center justify-center h-full bg-slate-50">
      <div class="text-center">
        <div class="animate-spin rounded-full h-14 w-14 border-b-4 border-blue-600 mx-auto mb-4"></div>
        <p class="text-slate-900 font-semibold text-base">Conectando...</p>
        <p class="text-slate-600 text-sm mt-2">Establishing WebSocket connection</p>
      </div>
    </div>
  </div>

  <script>
    const CONFIG = ${JSON.stringify(data)};
    
    let sharedWorker = null;
    let workerPort = null;
    let isConnected = false;
    let tickersData = new Map();
    let tickerOrder = [];
    
    // Estado de ordenamiento
    let sortColumn = null;
    let sortDirection = 'desc'; // 'asc' o 'desc'
    
    console.log('🚀 [Scanner Window] Init:', CONFIG.listName);
    
    // ============================================================
    // WEBSOCKET (SharedWorker)
    // ============================================================
    function initWebSocket() {
      try {
        console.log('🔌 [Scanner Window] Connecting to SharedWorker:', CONFIG.workerUrl);
        
        sharedWorker = new SharedWorker(CONFIG.workerUrl, {
          name: 'tradeul-websocket'
        });
        
        workerPort = sharedWorker.port;
        
        workerPort.onmessage = (event) => {
          const msg = event.data;
          
          switch (msg.type) {
            case 'message':
              handleWebSocketMessage(msg.data);
              break;
            case 'status':
              updateConnectionStatus(msg.isConnected);
              
              // Re-renderizar para actualizar el status en el header
              if (tickersData.size > 0) {
                renderTable();
              }
              
              if (msg.isConnected) {
                console.log('📡 [Scanner Window] Subscribing to list:', CONFIG.listName);
                workerPort.postMessage({
                  action: 'subscribe_list',
                  list: CONFIG.listName
                });
                console.log('✅ [Scanner Window] Subscription sent');
              }
              break;
          }
        };
        
        workerPort.start();
        console.log('✅ [Scanner Window] Worker port started');
        
        // Escuchar errores del worker
        sharedWorker.onerror = (error) => {
          console.error('❌ [Scanner Window] SharedWorker error:', error);
        };
        
        workerPort.postMessage({
          action: 'connect',
          url: CONFIG.wsUrl
        });
        console.log('📡 [Scanner Window] Connect message sent to worker');
        
      } catch (error) {
        console.error('❌ [Scanner Window] Failed to initialize WebSocket:', error);
      }
    }
    
    function handleWebSocketMessage(message) {
      switch (message.type) {
        case 'snapshot':
          if (message.list === CONFIG.listName) {
            handleSnapshot(message);
          }
          break;
        case 'delta':
          if (message.list === CONFIG.listName) {
            handleDelta(message);
          }
          break;
        case 'aggregate':
          handleAggregate(message);
          break;
      }
    }
    
    function handleSnapshot(snapshot) {
      const rows = snapshot.rows || [];
      
      tickersData.clear();
      tickerOrder = [];
      
      rows.forEach(ticker => {
        tickersData.set(ticker.symbol, ticker);
        tickerOrder.push(ticker.symbol);
      });
      
      renderTable();
    }
    
    function handleDelta(delta) {
      if (!delta.deltas || !Array.isArray(delta.deltas)) return;
      
      let needsRender = false;
      
      delta.deltas.forEach(action => {
        switch (action.action) {
          case 'add':
            if (action.data) {
              tickersData.set(action.symbol, action.data);
              if (!tickerOrder.includes(action.symbol)) {
                tickerOrder.splice(action.rank ?? tickerOrder.length, 0, action.symbol);
                needsRender = true;
              }
            }
            break;
          case 'remove':
            tickersData.delete(action.symbol);
            tickerOrder = tickerOrder.filter(s => s !== action.symbol);
            needsRender = true;
            break;
          case 'update':
            if (action.data) {
              const existing = tickersData.get(action.symbol);
              tickersData.set(action.symbol, { ...existing, ...action.data });
              needsRender = true;
            }
            break;
          case 'rerank':
            tickerOrder = tickerOrder.filter(s => s !== action.symbol);
            tickerOrder.splice(action.new_rank, 0, action.symbol);
            needsRender = true;
            break;
        }
      });
      
      if (needsRender) renderTable();
    }
    
    function handleAggregate(aggregate) {
      if (!aggregate.symbol || !aggregate.data) return;
      
      const ticker = tickersData.get(aggregate.symbol);
      if (!ticker) return;
      
      // Actualizar datos del ticker
      const aggData = aggregate.data;
      ticker.price = aggData.c ?? aggData.close ?? ticker.price;
      ticker.volume_today = aggData.av ?? ticker.volume_today;
      ticker.high = aggData.h ?? ticker.high;
      ticker.low = aggData.l ?? ticker.low;
      
      // Recalcular change_percent si tenemos prev_close
      if (ticker.prev_close && ticker.price) {
        ticker.change_percent = ((ticker.price - ticker.prev_close) / ticker.prev_close) * 100;
      }
      
      // Actualizar celda de precio
      const priceCell = document.querySelector(\`#row-\${aggregate.symbol} .price-cell\`);
      if (priceCell) {
        priceCell.textContent = formatPrice(ticker.price);
      }
      
      // Actualizar celda de change_percent
      const changeCell = document.querySelector(\`#row-\${aggregate.symbol} .change-cell\`);
      if (changeCell && ticker.change_percent !== null) {
        const isPositive = ticker.change_percent >= 0;
        changeCell.textContent = formatPercent(ticker.change_percent);
        changeCell.className = \`font-mono font-semibold \${isPositive ? 'text-emerald-600' : 'text-rose-600'}\`;
      }
    }
    
    function updateConnectionStatus(connected) {
      isConnected = connected;
      
      // Actualizar elementos si existen (antes de re-render)
      const dot = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      
      if (dot) {
        dot.className = connected 
          ? 'w-1.5 h-1.5 rounded-full bg-emerald-500' 
          : 'w-1.5 h-1.5 rounded-full bg-slate-300';
      }
      
      if (text) {
        text.textContent = connected ? 'Live' : 'Offline';
        text.className = connected
          ? 'text-xs font-medium text-emerald-600'
          : 'text-xs font-medium text-slate-500';
      }
    }
    
    // ============================================================
    // SORTING
    // ============================================================
    function getSortIcon(column) {
      if (sortColumn !== column) {
        // No ordenado - icono gris de arriba/abajo
        return '<svg class="w-3 h-3 text-slate-400 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"/></svg>';
      }
      
      if (sortDirection === 'asc') {
        // Ordenado ascendente - flecha arriba
        return '<svg class="w-3 h-3 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"/></svg>';
      } else {
        // Ordenado descendente - flecha abajo
        return '<svg class="w-3 h-3 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>';
      }
    }
    
    window.handleSort = function(column) {
      if (sortColumn === column) {
        // Toggle direction
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        // Nueva columna, ordenar descendente por defecto
        sortColumn = column;
        sortDirection = 'desc';
      }
      
      console.log('🔄 [Scanner Window] Sorting by', column, sortDirection);
      renderTable();
    }
    
    function getTickerValue(ticker, column) {
      switch (column) {
        case 'symbol':
          return ticker.symbol || '';
        case 'price':
          return ticker.price || 0;
        case 'change_percent':
          return ticker.change_percent || 0;
        case 'volume_today':
          return ticker.volume_today || 0;
        case 'rvol':
          return ticker.rvol_slot ?? ticker.rvol ?? 0;
        case 'market_cap':
          return ticker.market_cap || 0;
        case 'float_shares':
          return ticker.float_shares || 0;
        case 'atr_percent':
          return ticker.atr_percent || 0;
        case 'atr_used':
          // Calcular ATR Used igual que en el renderRow
          const atr_percent = ticker.atr_percent;
          const prev_close = ticker.prev_close;
          const change_percent = ticker.change_percent || 0;
          
          if (!atr_percent || !prev_close || atr_percent === 0) return 0;
          
          const high = ticker.intraday_high ?? ticker.high;
          const low = ticker.intraday_low ?? ticker.low;
          
          if (!high || !low) {
            return (Math.abs(change_percent) / atr_percent) * 100;
          }
          
          let range_percent;
          if (change_percent >= 0) {
            range_percent = ((high - prev_close) / prev_close) * 100;
          } else {
            range_percent = ((prev_close - low) / prev_close) * 100;
          }
          return (Math.abs(range_percent) / atr_percent) * 100;
        default:
          return 0;
      }
    }
    
    function sortTickers(tickers) {
      if (!sortColumn) return tickers;
      
      return [...tickers].sort((a, b) => {
        const aVal = getTickerValue(a, sortColumn);
        const bVal = getTickerValue(b, sortColumn);
        
        // Manejar strings vs números
        if (typeof aVal === 'string') {
          const comparison = aVal.localeCompare(bVal);
          return sortDirection === 'asc' ? comparison : -comparison;
        }
        
        const comparison = aVal - bVal;
        return sortDirection === 'asc' ? comparison : -comparison;
      });
    }
    
    // ============================================================
    // RENDER (clases Tailwind IDÉNTICAS al scanner)
    // ============================================================
    function renderTable() {
      let tickers = tickerOrder.map(s => tickersData.get(s)).filter(Boolean);
      
      // Aplicar ordenamiento si está activo
      if (sortColumn) {
        tickers = sortTickers(tickers);
      }
      
      // Clases de status según conexión
      const statusDotClass = isConnected 
        ? 'w-1.5 h-1.5 rounded-full bg-emerald-500' 
        : 'w-1.5 h-1.5 rounded-full bg-slate-300';
      const statusTextClass = isConnected
        ? 'text-xs font-medium text-emerald-600'
        : 'text-xs font-medium text-slate-500';
      const statusText = isConnected ? 'Live' : 'Offline';
      
      if (tickers.length === 0) {
        document.getElementById('root').innerHTML = \`
          <div class="h-screen flex flex-col bg-white">
            <div class="flex items-center justify-between px-3 py-2 bg-white border-b-2 border-blue-500">
              <div class="flex items-center gap-4">
                <div class="flex items-center gap-2">
                  <div class="w-1 h-6 bg-blue-500 rounded-full"></div>
                  <h2 class="text-base font-bold text-slate-900">\${CONFIG.categoryName}</h2>
                </div>
                <div class="flex items-center gap-1.5">
                  <div id="status-dot" class="\${statusDotClass}"></div>
                  <span id="status-text" class="\${statusTextClass}">\${statusText}</span>
                </div>
                <div class="flex items-center gap-1 px-2 py-0.5 bg-blue-50 rounded border border-blue-200">
                  <span class="text-xs font-semibold text-blue-600">0</span>
                  <span class="text-xs text-slate-600">tickers</span>
                </div>
              </div>
            </div>
            <div class="flex-1 flex items-center justify-center bg-slate-50">
              <p class="text-slate-500">No hay datos disponibles</p>
            </div>
          </div>
        \`;
        return;
      }
      
      const html = \`
        <div class="h-screen flex flex-col bg-white">
          <!-- Header (IDENTICAL to MarketTableLayout) -->
          <div class="flex items-center justify-between px-3 py-2 bg-white border-b-2 border-blue-500">
            <div class="flex items-center gap-4">
              <div class="flex items-center gap-2">
                <div class="w-1 h-6 bg-blue-500 rounded-full"></div>
                <h2 class="text-base font-bold text-slate-900 tracking-tight">\${CONFIG.categoryName}</h2>
              </div>
              
              <div class="flex items-center gap-1.5">
                <div id="status-dot" class="\${statusDotClass}"></div>
                <span id="status-text" class="\${statusTextClass}">\${statusText}</span>
              </div>
              
              <div class="flex items-center gap-1 px-2 py-0.5 bg-blue-50 rounded border border-blue-200">
                <span class="text-xs font-semibold text-blue-600">\${tickers.length}</span>
                <span class="text-xs text-slate-600">tickers</span>
              </div>
            </div>
            
            <div class="flex items-center gap-1.5 text-xs">
              <span class="text-slate-500">Updated</span>
              <span id="timestamp" class="font-mono font-medium text-slate-700">\${new Date().toLocaleTimeString()}</span>
            </div>
          </div>
          
          <!-- Table Container -->
          <div class="flex-1 overflow-auto bg-white">
            <table class="w-full border-collapse">
              <thead class="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                <tr style="height:24px;line-height:24px">
                  <th class="px-1 py-0.5 text-center text-[10px] font-semibold text-slate-600 uppercase tracking-wide" style="width:40px;height:24px;line-height:24px">#</th>
                  <th onclick="handleSort('symbol')" class="px-1 py-0.5 text-left text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:75px;height:24px;line-height:24px">
                    <div class="flex items-center gap-1">
                      Symbol
                      <span class="sort-icon">\${getSortIcon('symbol')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('price')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:80px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      Price
                      <span class="sort-icon">\${getSortIcon('price')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('change_percent')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:85px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      Gap %
                      <span class="sort-icon">\${getSortIcon('change_percent')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('volume_today')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:90px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      Volume
                      <span class="sort-icon">\${getSortIcon('volume_today')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('rvol')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:70px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      RVOL
                      <span class="sort-icon">\${getSortIcon('rvol')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('market_cap')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:100px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      Market Cap
                      <span class="sort-icon">\${getSortIcon('market_cap')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('float_shares')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:90px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      Float
                      <span class="sort-icon">\${getSortIcon('float_shares')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('atr_percent')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:70px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      ATR%
                      <span class="sort-icon">\${getSortIcon('atr_percent')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('atr_used')" class="px-1 py-0.5 text-right text-[10px] font-semibold text-slate-600 uppercase tracking-wide cursor-pointer hover:bg-slate-100 transition-colors" style="width:85px;height:24px;line-height:24px">
                    <div class="flex items-center justify-end gap-1">
                      ATR Used
                      <span class="sort-icon">\${getSortIcon('atr_used')}</span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 bg-white">
                \${tickers.map((ticker, index) => renderRow(ticker, index + 1)).join('')}
              </tbody>
            </table>
          </div>
        </div>
      \`;
      
      document.getElementById('root').innerHTML = html;
    }
    
    function renderRow(ticker, rank) {
      const gapPercent = ticker.change_percent ?? ticker.gap_percent ?? 0;
      const isPositive = gapPercent >= 0;
      const volume = ticker.volume_today ?? ticker.volume ?? 0;
      const rvol = ticker.rvol_slot ?? ticker.rvol ?? 0;
      
      // RVOL color (igual que scanner)
      let rvolColor = 'text-slate-500';
      if (rvol > 3) rvolColor = 'text-blue-700';
      else if (rvol > 1.5) rvolColor = 'text-blue-600';
      
      // ATR% (igual que scanner)
      const atrPercent = ticker.atr_percent;
      let atrPercentHtml = '<div class="text-slate-400">-</div>';
      if (atrPercent !== null && atrPercent !== undefined) {
        const atrColorClass = atrPercent > 5 ? 'text-orange-600 font-semibold' : 'text-slate-600';
        atrPercentHtml = \`<div class="font-mono \${atrColorClass}">\${atrPercent.toFixed(1)}%</div>\`;
      }
      
      // ATR Used (igual que scanner)
      let atrUsedHtml = '<div class="text-slate-400">-</div>';
      const atr_percent = ticker.atr_percent;
      const prev_close = ticker.prev_close;
      const change_percent = ticker.change_percent || 0;
      
      if (atr_percent && atr_percent !== 0 && prev_close) {
        const high = ticker.intraday_high ?? ticker.high;
        const low = ticker.intraday_low ?? ticker.low;
        
        let atrUsedValue;
        if (!high || !low) {
          atrUsedValue = (Math.abs(change_percent) / atr_percent) * 100;
        } else {
          let range_percent;
          if (change_percent >= 0) {
            range_percent = ((high - prev_close) / prev_close) * 100;
          } else {
            range_percent = ((prev_close - low) / prev_close) * 100;
          }
          atrUsedValue = (Math.abs(range_percent) / atr_percent) * 100;
        }
        
        let atrUsedColorClass = 'text-slate-600';
        if (atrUsedValue > 150) {
          atrUsedColorClass = 'text-red-600 font-bold';
        } else if (atrUsedValue > 100) {
          atrUsedColorClass = 'text-orange-600 font-semibold';
        } else if (atrUsedValue > 75) {
          atrUsedColorClass = 'text-yellow-600 font-medium';
        } else if (atrUsedValue > 50) {
          atrUsedColorClass = 'text-blue-600';
        }
        
        atrUsedHtml = \`<div class="font-mono \${atrUsedColorClass}">\${atrUsedValue.toFixed(0)}%</div>\`;
      }
      
      return \`
        <tr id="row-\${ticker.symbol}" class="hover:bg-slate-50 transition-colors" style="height:18px;line-height:18px">
          <td class="px-1 text-center text-slate-400 text-[10px]" style="height:18px;line-height:18px;padding:0 4px">\${rank}</td>
          <td class="px-1 text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="font-bold text-blue-600 cursor-pointer hover:text-blue-800 hover:underline">\${ticker.symbol}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="price-cell font-mono font-semibold text-slate-900">\${formatPrice(ticker.price)}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="change-cell font-mono font-semibold" style="color:\${isPositive ? '#10b981' : '#ef4444'}">\${formatPercent(gapPercent)}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="font-mono text-slate-700">\${formatNumber(volume)}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="font-mono font-semibold" style="color:\${rvolColor === 'text-blue-700' ? '#1d4ed8' : rvolColor === 'text-blue-600' ? '#2563eb' : '#64748b'}">\${formatRVOL(rvol)}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="font-mono text-slate-600">\${formatNumber(ticker.market_cap)}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            <span class="font-mono text-slate-600">\${formatNumber(ticker.float_shares)}</span>
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            \${atrPercentHtml}
          </td>
          <td class="px-1 text-right text-[10px]" style="height:18px;line-height:18px;padding:0 4px">
            \${atrUsedHtml}
          </td>
        </tr>
      \`;
    }
    
    // ============================================================
    // FORMATTERS (idénticos al scanner)
    // ============================================================
    function formatPrice(value) {
      if (value == null || isNaN(value)) return '-';
      if (value >= 1000) return \`$\${value.toFixed(2)}\`;
      if (value >= 1) return \`$\${value.toFixed(2)}\`;
      if (value >= 0.01) return \`$\${value.toFixed(3)}\`;
      return \`$\${value.toFixed(4)}\`;
    }
    
    function formatPercent(value) {
      if (value == null || isNaN(value)) return '-';
      const sign = value > 0 ? '+' : '';
      return \`\${sign}\${value.toFixed(2)}%\`;
    }
    
    function formatNumber(value) {
      if (value == null || isNaN(value)) return '-';
      if (value >= 1e9) return \`\${(value / 1e9).toFixed(2)}B\`;
      if (value >= 1e6) return \`\${(value / 1e6).toFixed(2)}M\`;
      if (value >= 1e3) return \`\${(value / 1e3).toFixed(2)}K\`;
      return value.toLocaleString('en-US');
    }
    
    function formatRVOL(value) {
      if (value == null || isNaN(value)) return '-';
      return \`\${value.toFixed(2)}x\`;
    }
    
    // ============================================================
    // INIT
    // ============================================================
    initWebSocket();
    console.log('✅ Initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Injected');
}

// ============================================================================
// DILUTION TRACKER WINDOW
// ============================================================================

export interface DilutionTrackerWindowData {
  ticker?: string;
  apiBaseUrl: string;
}

export function openDilutionTrackerWindow(
  data: DilutionTrackerWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 1400,
    height = 900,
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

  injectDilutionTrackerContent(newWindow, data, config);

  return newWindow;
}

function injectDilutionTrackerContent(
  targetWindow: Window,
  data: DilutionTrackerWindowData,
  config: WindowConfig
): void {
  const { title } = config;

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          }
        }
      }
    }
  </script>
  
  <style>
    * {
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    
    body {
      font-family: Inter, sans-serif;
      color: #171717;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }
  </style>
</head>
<body class="bg-white">
  <div id="root" class="h-screen flex flex-col">
    <div class="flex items-center justify-center h-full bg-slate-50">
      <div class="text-center">
        <div class="animate-spin rounded-full h-14 w-14 border-b-4 border-blue-600 mx-auto mb-4"></div>
        <p class="text-slate-900 font-semibold text-base">Cargando Dilution Tracker...</p>
      </div>
    </div>
  </div>

  <script>
    const CONFIG = ${JSON.stringify(data)};
    
    // Renderizar iframe con la página standalone
    const tickerParam = CONFIG.ticker ? \`?ticker=\${CONFIG.ticker}\` : '';
    const iframeSrc = \`\${CONFIG.apiBaseUrl}/standalone/dilution-tracker\${tickerParam}\`;
    
    document.getElementById('root').innerHTML = \`
      <iframe 
        src="\${iframeSrc}" 
        style="width:100%;height:100%;border:0;display:block;" 
        title="Dilution Tracker"
      ></iframe>
    \`;
    
    console.log('✅ Dilution Tracker loaded in about:blank');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Dilution Tracker injected');
}

// ============================================================================
// NEWS WINDOW
// ============================================================================

export interface NewsWindowData {
  wsUrl: string;
  workerUrl: string;
  apiBaseUrl: string;
  ticker?: string;
}

export async function openNewsWindow(
  data: NewsWindowData,
  config: WindowConfig
): Promise<Window | null> {
  const {
    width = 1200,
    height = 800,
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

  // Pre-fetch news data BEFORE opening about:blank (to avoid CORS issues)
  let initialNews: any[] = [];
  try {
    const tickerParam = data.ticker ? `&ticker=${data.ticker}` : '';
    const response = await fetch(`${data.apiBaseUrl}/news/api/v1/news?limit=200${tickerParam}`);
    if (response.ok) {
      const json = await response.json();
      initialNews = json.results || [];
    }
  } catch (error) {
    console.error('❌ Pre-fetch news failed:', error);
  }

  const newWindow = window.open('about:blank', '_blank', windowFeatures);

  if (!newWindow) {
    console.error('❌ Window blocked');
    return null;
  }

  injectNewsContent(newWindow, data, config, initialNews);

  return newWindow;
}

function injectNewsContent(
  targetWindow: Window,
  data: NewsWindowData,
  config: WindowConfig,
  initialNews: any[]
): void {
  const { title } = config;

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          }
        }
      }
    }
  </script>
  
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: Inter, sans-serif; color: #171717; background: #ffffff; margin: 0; }
    *::-webkit-scrollbar { width: 8px; height: 8px; }
    *::-webkit-scrollbar-track { background: #f1f5f9; }
    *::-webkit-scrollbar-thumb { background: #cbd5e1; }
    *::-webkit-scrollbar-thumb:hover { background: #3b82f6; }
    .news-row:hover { background-color: #f8fafc; }
    .news-row.live { background-color: rgba(16, 185, 129, 0.05); }
  </style>
</head>
<body class="bg-white overflow-hidden">
  <div id="root" class="h-screen flex flex-col"></div>

  <script>
    const CONFIG = ${JSON.stringify(data)};
    const INITIAL_NEWS = ${JSON.stringify(initialNews)};
    
    let sharedWorker = null;
    let workerPort = null;
    let isConnected = false;
    let isPaused = false;
    let isSquawkEnabled = false;
    let squawkQueue = [];
    let isSquawkPlaying = false;
    let newsData = INITIAL_NEWS || [];
    let seenIds = new Set(newsData.map(a => a.benzinga_id));
    let pausedBuffer = [];
    
    const VOICE_ID = '21m00Tcm4TlvDq8ikWAM'; // Rachel
    
    console.log('🚀 [News Window] Init with', newsData.length, 'articles');
    
    // ============================================================
    // WEBSOCKET (SharedWorker)
    // ============================================================
    function initWebSocket() {
      try {
        console.log('🔌 [News Window] Connecting to SharedWorker');
        
        sharedWorker = new SharedWorker(CONFIG.workerUrl, { name: 'tradeul-websocket' });
        workerPort = sharedWorker.port;
        
        workerPort.onmessage = (event) => {
          const msg = event.data;
          
          switch (msg.type) {
            case 'message':
              handleWebSocketMessage(msg.data);
              break;
            case 'status':
              updateConnectionStatus(msg.isConnected);
              if (msg.isConnected) {
                workerPort.postMessage({ action: 'subscribe_news' });
                console.log('✅ [News Window] Subscribed to news');
              }
              break;
          }
        };
        
        workerPort.start();
        workerPort.postMessage({ action: 'connect', url: CONFIG.wsUrl });
        
      } catch (error) {
        console.error('❌ [News Window] WebSocket init failed:', error);
      }
    }
    
    function handleWebSocketMessage(message) {
      if ((message.type === 'news' || message.type === 'benzinga_news') && message.article) {
        const article = message.article;
        const id = article.benzinga_id || article.id;
        
        if (!seenIds.has(id)) {
          seenIds.add(id);
          
          if (isPaused) {
            pausedBuffer.unshift({ ...article, isLive: true });
          } else {
            newsData.unshift({ ...article, isLive: true });
            renderTable();
            
            // Squawk: leer la noticia
            const ticker = (article.tickers && article.tickers[0]) || '';
            const squawkText = ticker ? ticker + '. ' + article.title : article.title;
            speakNews(squawkText);
          }
        }
      }
    }
    
    function updateConnectionStatus(connected) {
      isConnected = connected;
      const dot = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      
      if (dot) {
        dot.className = connected 
          ? 'w-1.5 h-1.5 rounded-full bg-emerald-500' 
          : 'w-1.5 h-1.5 rounded-full bg-slate-300';
      }
      if (text) {
        text.textContent = connected ? 'Live' : 'Offline';
        text.className = connected ? 'text-xs font-medium text-emerald-600' : 'text-xs font-medium text-slate-500';
      }
    }
    
    // ============================================================
    // PAUSE/PLAY
    // ============================================================
    window.togglePause = function() {
      isPaused = !isPaused;
      
      if (!isPaused && pausedBuffer.length > 0) {
        newsData = [...pausedBuffer, ...newsData];
        pausedBuffer = [];
      }
      
      renderTable();
    }
    
    // ============================================================
    // SQUAWK (Text-to-Speech)
    // ============================================================
    window.toggleSquawk = function() {
      isSquawkEnabled = !isSquawkEnabled;
      if (!isSquawkEnabled) {
        squawkQueue = [];
      }
      renderTable();
    }
    
    async function processSquawkQueue() {
      if (isSquawkPlaying || squawkQueue.length === 0) return;
      
      isSquawkPlaying = true;
      
      while (squawkQueue.length > 0) {
        const text = squawkQueue.shift();
        renderTable(); // Update queue badge
        
        try {
          // Usar proxy del API Gateway para evitar CORS
          const response = await fetch(CONFIG.apiBaseUrl + '/api/v1/tts/speak', {
            method: 'POST',
            headers: {
              'Accept': 'audio/mpeg',
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              text: text,
              voice_id: VOICE_ID,
            }),
          });
          
          if (!response.ok) continue;
          
          const audioBlob = await response.blob();
          const audioUrl = URL.createObjectURL(audioBlob);
          
          await new Promise((resolve) => {
            const audio = new Audio(audioUrl);
            audio.onended = () => { URL.revokeObjectURL(audioUrl); resolve(); };
            audio.onerror = () => { URL.revokeObjectURL(audioUrl); resolve(); };
            audio.play().catch(() => resolve());
          });
          
        } catch (error) {
          console.error('Squawk error:', error);
        }
      }
      
      isSquawkPlaying = false;
      renderTable();
    }
    
    function speakNews(text) {
      if (!isSquawkEnabled) return;
      const cleanText = text.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '').substring(0, 200);
      squawkQueue.push(cleanText);
      renderTable();
      processSquawkQueue();
    }
    
    // ============================================================
    // RENDER
    // ============================================================
    function formatDateTime(isoString) {
      if (!isoString) return { date: '—', time: '—' };
      try {
        const d = new Date(isoString);
        return {
          date: d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' }),
          time: d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
        };
      } catch { return { date: '—', time: '—' }; }
    }
    
    function renderTable() {
      const liveCount = newsData.filter(a => a.isLive).length;
      const statusDotClass = isConnected ? 'w-1.5 h-1.5 rounded-full bg-emerald-500' : 'w-1.5 h-1.5 rounded-full bg-slate-300';
      const statusText = isConnected ? 'Live' : 'Offline';
      const statusTextClass = isConnected ? 'text-xs font-medium text-emerald-600' : 'text-xs font-medium text-slate-500';
      
      const pauseBtnClass = isPaused 
        ? 'px-2 py-0.5 text-xs font-medium rounded bg-emerald-600 hover:bg-emerald-700 text-white'
        : 'px-2 py-0.5 text-xs font-medium rounded bg-amber-600 hover:bg-amber-700 text-white';
      const pauseBtnText = isPaused ? '▶ Play' : '❚❚ Pause';
      const pausedInfo = isPaused && pausedBuffer.length > 0 
        ? \`<span class="text-amber-600 text-xs font-medium">(+\${pausedBuffer.length})</span>\` 
        : '';
      
      const squawkBtnClass = isSquawkEnabled 
        ? 'px-2 py-0.5 text-xs font-medium rounded bg-violet-600 hover:bg-violet-700 text-white relative'
        : 'px-2 py-0.5 text-xs font-medium rounded bg-slate-200 hover:bg-slate-300 text-slate-600';
      const squawkBtnText = isSquawkEnabled ? '🔊 Squawk' : '🔇 Squawk';
      const squawkQueueBadge = squawkQueue.length > 0 
        ? \`<span class="absolute -top-1 -right-1 bg-amber-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">\${squawkQueue.length}</span>\`
        : '';
      
      const html = \`
        <div class="h-screen flex flex-col bg-white">
          <!-- Header -->
          <div class="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
            <div class="flex items-center gap-4">
              <div class="flex items-center gap-2">
                <div class="w-1 h-6 bg-blue-500 rounded-full"></div>
                <h2 class="text-base font-bold text-slate-900">News</h2>
              </div>
              <div class="flex items-center gap-1.5">
                <div id="status-dot" class="\${statusDotClass}"></div>
                <span id="status-text" class="\${statusTextClass}">\${statusText}</span>
              </div>
              <button onclick="togglePause()" class="\${pauseBtnClass}">\${pauseBtnText}</button>
              <button onclick="toggleSquawk()" class="\${squawkBtnClass}">\${squawkBtnText}\${squawkQueueBadge}</button>
              \${pausedInfo}
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-600 font-mono">\${newsData.length}</span>
              \${liveCount > 0 ? \`<span class="text-xs text-emerald-600">(\${liveCount} live)</span>\` : ''}
            </div>
          </div>
          
          <!-- Table -->
          <div class="flex-1 overflow-auto">
            <table class="w-full border-collapse text-xs">
              <thead class="bg-slate-100 sticky top-0">
                <tr class="text-left text-slate-600 uppercase tracking-wide">
                  <th class="px-2 py-1.5 font-medium">Headline</th>
                  <th class="px-2 py-1.5 font-medium w-24 text-center">Date</th>
                  <th class="px-2 py-1.5 font-medium w-20 text-center">Time</th>
                  <th class="px-2 py-1.5 font-medium w-16 text-center">Ticker</th>
                  <th class="px-2 py-1.5 font-medium w-36">Source</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                \${newsData.length === 0 ? \`
                  <tr>
                    <td colspan="5" class="px-4 py-8 text-center text-slate-500">
                      No hay noticias disponibles. Esperando datos...
                    </td>
                  </tr>
                \` : newsData.map(article => {
                  const dt = formatDateTime(article.published);
                  const ticker = (article.tickers && article.tickers[0]) || '—';
                  const isLive = article.isLive;
                  
                  return \`
                    <tr class="news-row cursor-pointer \${isLive ? 'live' : ''}" onclick="window.open('\${article.url}', '_blank')">
                      <td class="px-2 py-1">
                        <div class="flex items-center gap-1.5">
                          \${isLive ? '<span class="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>' : ''}
                          <span class="text-slate-800 truncate" style="max-width:500px">\${article.title}</span>
                        </div>
                      </td>
                      <td class="px-2 py-1 text-center text-slate-500 font-mono">\${dt.date}</td>
                      <td class="px-2 py-1 text-center text-slate-500 font-mono">\${dt.time}</td>
                      <td class="px-2 py-1 text-center">
                        <span class="text-blue-600 font-mono font-semibold">\${ticker}</span>
                      </td>
                      <td class="px-2 py-1 text-slate-500 truncate" style="max-width:140px">\${article.author}</td>
                    </tr>
                  \`;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      \`;
      
      document.getElementById('root').innerHTML = html;
    }
    
    // ============================================================
    // INIT
    // ============================================================
    renderTable();
    initWebSocket();
    console.log('✅ News Window initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] News injected');
}

// ============================================================================
// SEC FILINGS WINDOW
// ============================================================================

export interface SECFilingsWindowData {
  wsUrl: string;
  workerUrl: string;
  secApiBaseUrl: string;
}

export function openSECFilingsWindow(
  data: SECFilingsWindowData,
  config: WindowConfig
): Window | null {
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

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          }
        }
      }
    }
  </script>
  
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: Inter, sans-serif; color: #171717; background: #ffffff; margin: 0; }
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
    
    let sharedWorker = null;
    let workerPort = null;
    let isConnected = false;
    let isPaused = false;
    let filingsData = [];
    let seenIds = new Set();
    let pausedBuffer = [];
    
    console.log('🚀 [SEC Window] Init');
    
    // ============================================================
    // FETCH INITIAL FILINGS
    // ============================================================
    async function fetchInitialFilings() {
      try {
        console.log('📄 Fetching from:', CONFIG.secApiBaseUrl + '/api/v1/filings/live?page_size=200');
        const response = await fetch(CONFIG.secApiBaseUrl + '/api/v1/filings/live?page_size=200');
        
        if (!response.ok) throw new Error('HTTP ' + response.status);
        
        const data = await response.json();
        
        if (data.filings && data.filings.length > 0) {
          filingsData = data.filings;
          data.filings.forEach(f => seenIds.add(f.accessionNo));
        }
        renderTable();
      } catch (error) {
        console.error('❌ Error fetching filings:', error);
        renderTable();
      }
    }
    
    // ============================================================
    // WEBSOCKET (SharedWorker)
    // ============================================================
    function initWebSocket() {
      try {
        console.log('🔌 [SEC Window] Connecting to SharedWorker');
        
        sharedWorker = new SharedWorker(CONFIG.workerUrl, { name: 'tradeul-websocket' });
        workerPort = sharedWorker.port;
        
        workerPort.onmessage = (event) => {
          const msg = event.data;
          
          switch (msg.type) {
            case 'message':
              handleWebSocketMessage(msg.data);
              break;
            case 'status':
              updateConnectionStatus(msg.isConnected);
              if (msg.isConnected) {
                workerPort.postMessage({ action: 'subscribe_sec' });
                console.log('✅ [SEC Window] Subscribed to SEC filings');
              }
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
        
        if (id && !seenIds.has(id)) {
          seenIds.add(id);
          const liveFiling = { ...filing, isLive: true };
          
          if (isPaused) {
            pausedBuffer.unshift(liveFiling);
          } else {
            filingsData.unshift(liveFiling);
            renderTable();
          }
        }
      }
    }
    
    function updateConnectionStatus(connected) {
      isConnected = connected;
      const dot = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      
      if (dot) {
        dot.className = connected 
          ? 'w-1.5 h-1.5 rounded-full bg-emerald-500' 
          : 'w-1.5 h-1.5 rounded-full bg-slate-300';
      }
      if (text) {
        text.textContent = connected ? 'Live' : 'Offline';
        text.className = connected ? 'text-xs font-medium text-emerald-600' : 'text-xs font-medium text-slate-500';
      }
    }
    
    // ============================================================
    // PAUSE/PLAY
    // ============================================================
    window.togglePause = function() {
      isPaused = !isPaused;
      
      if (!isPaused && pausedBuffer.length > 0) {
        filingsData = [...pausedBuffer, ...filingsData];
        pausedBuffer = [];
      }
      
      renderTable();
    }
    
    // ============================================================
    // RENDER
    // ============================================================
    function formatDateTime(isoString) {
      if (!isoString) return { date: '—', time: '—' };
      try {
        const d = new Date(isoString);
        return {
          date: d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' }),
          time: d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
        };
      } catch { return { date: '—', time: '—' }; }
    }
    
    function getFormTypeColor(formType) {
      const t = (formType || '').toUpperCase();
      if (t.includes('S-1') || t.includes('S-3') || t.includes('S-4') || t.includes('S-8') || t.includes('S-11')) 
        return 'bg-red-100 text-red-700';
      if (t.includes('10-K') || t.includes('10-Q')) 
        return 'bg-blue-100 text-blue-700';
      if (t.includes('8-K')) 
        return 'bg-amber-100 text-amber-700';
      if (t.includes('4') || t.includes('3') || t.includes('5')) 
        return 'bg-purple-100 text-purple-700';
      if (t.includes('SC 13') || t.includes('13D') || t.includes('13G') || t.includes('13F')) 
        return 'bg-emerald-100 text-emerald-700';
      return 'bg-slate-100 text-slate-700';
    }
    
    function renderTable() {
      const liveCount = filingsData.filter(f => f.isLive).length;
      const statusDotClass = isConnected ? 'w-1.5 h-1.5 rounded-full bg-emerald-500' : 'w-1.5 h-1.5 rounded-full bg-slate-300';
      const statusText = isConnected ? 'Live' : 'Offline';
      const statusTextClass = isConnected ? 'text-xs font-medium text-emerald-600' : 'text-xs font-medium text-slate-500';
      
      const pauseBtnClass = isPaused 
        ? 'px-2 py-0.5 text-xs font-medium rounded bg-emerald-600 hover:bg-emerald-700 text-white'
        : 'px-2 py-0.5 text-xs font-medium rounded bg-amber-600 hover:bg-amber-700 text-white';
      const pauseBtnText = isPaused ? '▶ Play' : '❚❚ Pause';
      const pausedInfo = isPaused && pausedBuffer.length > 0 
        ? '<span class="text-amber-600 text-xs font-medium">(+' + pausedBuffer.length + ')</span>' 
        : '';
      
      const html = \`
        <div class="h-screen flex flex-col bg-white">
          <!-- Header -->
          <div class="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
            <div class="flex items-center gap-4">
              <div class="flex items-center gap-2">
                <div class="w-1 h-6 bg-blue-500 rounded-full"></div>
                <h2 class="text-base font-bold text-slate-900">SEC Filings</h2>
              </div>
              <div class="flex items-center gap-1.5">
                <div id="status-dot" class="\${statusDotClass}"></div>
                <span id="status-text" class="\${statusTextClass}">\${statusText}</span>
              </div>
              <button onclick="togglePause()" class="\${pauseBtnClass}">\${pauseBtnText}</button>
              \${pausedInfo}
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-600 font-mono">\${filingsData.length}</span>
              \${liveCount > 0 ? '<span class="text-xs text-emerald-600">(' + liveCount + ' live)</span>' : ''}
            </div>
          </div>
          
          <!-- Table -->
          <div class="flex-1 overflow-auto">
            <table class="w-full border-collapse text-xs">
              <thead class="bg-slate-100 sticky top-0">
                <tr class="text-left text-slate-600 uppercase tracking-wide">
                  <th class="px-2 py-1.5 font-medium w-16 text-center">Ticker</th>
                  <th class="px-2 py-1.5 font-medium w-20 text-center">Form</th>
                  <th class="px-2 py-1.5 font-medium">Company</th>
                  <th class="px-2 py-1.5 font-medium w-24 text-center">Date</th>
                  <th class="px-2 py-1.5 font-medium w-20 text-center">Time</th>
                  <th class="px-2 py-1.5 font-medium w-20 text-center">Link</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                \${filingsData.length === 0 ? \`
                  <tr>
                    <td colspan="6" class="px-4 py-8 text-center text-slate-500">
                      No hay filings disponibles. Esperando datos...
                    </td>
                  </tr>
                \` : filingsData.map(filing => {
                  const dt = formatDateTime(filing.filedAt);
                  const formColorClass = getFormTypeColor(filing.formType);
                  const isLive = filing.isLive;
                  const link = filing.linkToHtml || filing.linkToFilingDetails || '';
                  
                  return \`
                    <tr class="filing-row cursor-pointer \${isLive ? 'live' : ''}" onclick="window.open('\${link}', '_blank')">
                      <td class="px-2 py-1 text-center">
                        <div class="flex items-center justify-center gap-1">
                          \${isLive ? '<span class="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>' : ''}
                          <span class="text-blue-600 font-mono font-semibold">\${filing.ticker || '—'}</span>
                        </div>
                      </td>
                      <td class="px-2 py-1 text-center">
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-medium \${formColorClass}">\${filing.formType}</span>
                      </td>
                      <td class="px-2 py-1 text-slate-700 truncate" style="max-width:400px">\${filing.companyName || '—'}</td>
                      <td class="px-2 py-1 text-center text-slate-500 font-mono">\${dt.date}</td>
                      <td class="px-2 py-1 text-center text-slate-500 font-mono">\${dt.time}</td>
                      <td class="px-2 py-1 text-center">
                        <a href="\${link}" target="_blank" class="text-blue-600 hover:text-blue-800" onclick="event.stopPropagation()">
                          <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
                          </svg>
                        </a>
                      </td>
                    </tr>
                  \`;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      \`;
      
      document.getElementById('root').innerHTML = html;
    }
    
    // ============================================================
    // INIT
    // ============================================================
    fetchInitialFilings();
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
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          }
        }
      }
    }
  </script>
  
  <!-- Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  
  <style>
    body { font-family: 'Inter', sans-serif; margin: 0; padding: 0; }
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

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          }
        }
      }
    }
  </script>
  
  <style>
    body { font-family: 'Inter', sans-serif; margin: 0; padding: 0; }
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
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
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
    console.log('✅ IPO Window initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] IPO injected');
}


// Helper for HTML template
function formatValueJS(value: number | null, type: string): string {
  if (value === null || value === undefined) return '--';

  if (type === 'percent') return `${value.toFixed(2)}%`;
  if (type === 'ratio') return value.toFixed(2);
  if (type === 'eps') return `${value < 0 ? '-' : ''}$${Math.abs(value).toFixed(2)}`;
  if (type === 'shares') {
    const abs = Math.abs(value);
    if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
    return value.toFixed(0);
  }

  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(2)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}


// ============================================================================
// CHAT WINDOW
// ============================================================================

export interface ChatWindowData {
  wsUrl: string;
  apiUrl: string;
  token: string;
  userId: string;
  userName: string;
  userAvatar?: string;
  activeTarget?: { type: 'channel' | 'group'; id: string };
}

export function openChatWindow(
  data: ChatWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 900,
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
    console.error('❌ Chat window blocked');
    return null;
  }

  injectChatContent(newWindow, data, config);

  return newWindow;
}

function injectChatContent(
  targetWindow: Window,
  data: ChatWindowData,
  config: WindowConfig
): void {
  const { title } = config;

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          },
          colors: {
            background: '#FFFFFF',
            foreground: '#0F172A',
            primary: { DEFAULT: '#2563EB', hover: '#1D4ED8' },
            border: '#E2E8F0',
            muted: '#F8FAFC',
            success: '#10B981',
            danger: '#EF4444'
          }
        }
      }
    }
  </script>
  
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: 'JetBrains Mono', monospace; color: #0F172A; background: #ffffff; margin: 0; font-size: 12px; }
    *::-webkit-scrollbar { width: 6px; height: 6px; }
    *::-webkit-scrollbar-track { background: #F8FAFC; border-left: 1px solid #E2E8F0; }
    *::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
    *::-webkit-scrollbar-thumb:hover { background: #2563EB; }
    .message:hover { background-color: rgba(0,0,0,0.03); }
    .channel-item { transition: all 0.15s; }
    .channel-item:hover { background-color: rgba(0,0,0,0.05); }
    .channel-item.active { background-color: rgba(37, 99, 235, 0.1); color: #2563eb; font-weight: 500; }
    .ticker-mention { display: inline-flex; align-items: center; gap: 2px; padding: 0 4px; border-radius: 4px; border: 1px solid rgba(37, 99, 235, 0.4); font-size: 11px; cursor: pointer; }
    .ticker-mention:hover { border-color: #2563EB; background-color: rgba(37, 99, 235, 0.05); }
    .ticker-mention .symbol { color: #2563EB; font-weight: 500; }
    .ticker-mention .price { color: #0F172A; font-size: 10px; }
    .ticker-mention .change-positive { color: #10B981; font-size: 10px; }
    .ticker-mention .change-negative { color: #EF4444; font-size: 10px; }
    .typing-dot { animation: typing 1.4s infinite both; }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing { 0%, 60%, 100% { opacity: 0.3; } 30% { opacity: 1; } }
  </style>
</head>
<body class="bg-white overflow-hidden">
  <div id="root" class="h-screen flex flex-col">
    <div class="flex items-center justify-center h-full bg-slate-50">
      <div class="text-center">
        <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-3"></div>
        <p class="text-slate-600 text-sm">Conectando al chat...</p>
      </div>
    </div>
  </div>

  <script>
    const CONFIG = ${JSON.stringify(data)};
    
    let ws = null;
    let isConnected = false;
    let channels = [];
    let groups = [];
    let messages = [];
    let activeTarget = CONFIG.activeTarget || null;
    let typingUsers = [];
    let heartbeatInterval = null;
    let typingTimeout = null;
    
    console.log('🚀 [Chat Window] Init', CONFIG.userName);
    
    // ============================================================
    // WEBSOCKET
    // ============================================================
    function initWebSocket() {
      const url = CONFIG.wsUrl + '?token=' + encodeURIComponent(CONFIG.token);
      console.log('🔌 [Chat] Connecting to:', CONFIG.wsUrl);
      
      ws = new WebSocket(url);
      
      ws.onopen = () => {
        console.log('✅ [Chat] Connected');
        isConnected = true;
        
        // Start heartbeat
        heartbeatInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);
        
        // Subscribe to active target
        if (activeTarget) {
          subscribe(activeTarget);
        }
        
        render();
      };
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleMessage(msg);
        } catch (e) {
          console.error('[Chat] Parse error:', e);
        }
      };
      
      ws.onerror = (error) => {
        console.error('[Chat] Error:', error);
        isConnected = false;
        render();
      };
      
      ws.onclose = () => {
        console.log('[Chat] Disconnected');
        isConnected = false;
        clearInterval(heartbeatInterval);
        render();
        
        // Reconnect after 3s
        setTimeout(initWebSocket, 3000);
      };
    }
    
    function handleMessage(msg) {
      switch (msg.type) {
        case 'new_message':
          if (isActiveMessage(msg.payload)) {
            // Check if message already exists (avoid duplicates)
            const exists = messages.some(m => m.id === msg.payload.id);
            if (!exists) {
              // Add new message at the START (array is newest-first)
              messages.unshift(msg.payload);
              renderMessages();
              scrollToBottom();
            }
          }
          break;
        case 'typing':
          if (isActiveMessage(msg.payload) && msg.payload.user_id !== CONFIG.userId) {
            const existing = typingUsers.find(u => u.user_id === msg.payload.user_id);
            if (!existing) {
              typingUsers.push(msg.payload);
              renderTyping();
            }
            // Remove after 3s
            setTimeout(() => {
              typingUsers = typingUsers.filter(u => u.user_id !== msg.payload.user_id);
              renderTyping();
            }, 3000);
          }
          break;
        case 'online_users':
          document.getElementById('online-count').textContent = msg.payload.count || 0;
          break;
        case 'pong':
          break;
      }
    }
    
    function isActiveMessage(payload) {
      if (!activeTarget) return false;
      if (activeTarget.type === 'channel' && payload.channel_id === activeTarget.id) return true;
      if (activeTarget.type === 'group' && payload.group_id === activeTarget.id) return true;
      return false;
    }
    
    function subscribe(target) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: 'subscribe',
        payload: target.type === 'channel' 
          ? { channel_id: target.id }
          : { group_id: target.id }
      }));
      console.log('[Chat] Subscribed to', target);
    }
    
    function unsubscribe(target) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: 'unsubscribe',
        payload: target.type === 'channel'
          ? { channel_id: target.id }
          : { group_id: target.id }
      }));
    }
    
    function sendTyping() {
      if (!ws || ws.readyState !== WebSocket.OPEN || !activeTarget) return;
      ws.send(JSON.stringify({
        type: 'typing',
        payload: activeTarget.type === 'channel'
          ? { channel_id: activeTarget.id }
          : { group_id: activeTarget.id }
      }));
    }
    
    // ============================================================
    // API CALLS
    // ============================================================
    async function fetchChannels() {
      try {
        const res = await fetch(CONFIG.apiUrl + '/api/chat/channels');
        if (res.ok) {
          channels = await res.json();
          if (!activeTarget && channels.length > 0) {
            const general = channels.find(c => c.name === 'general') || channels[0];
            activeTarget = { type: 'channel', id: general.id };
          }
        }
      } catch (e) {
        console.error('[Chat] Fetch channels error:', e);
      }
    }
    
    async function fetchGroups() {
      try {
        const res = await fetch(CONFIG.apiUrl + '/api/chat/groups', {
          headers: { Authorization: 'Bearer ' + CONFIG.token }
        });
        if (res.ok) {
          groups = await res.json();
        }
      } catch (e) {
        console.error('[Chat] Fetch groups error:', e);
      }
    }
    
    async function fetchMessages() {
      if (!activeTarget) return;
      
      try {
        const endpoint = activeTarget.type === 'channel'
          ? '/api/chat/messages/channel/' + activeTarget.id
          : '/api/chat/messages/group/' + activeTarget.id;
        
        const headers = activeTarget.type === 'group' 
          ? { Authorization: 'Bearer ' + CONFIG.token }
          : {};
        
        const res = await fetch(CONFIG.apiUrl + endpoint, { headers });
        if (res.ok) {
          const data = await res.json();
          // API returns newest first (DESC), store as-is
          messages = data;
        }
      } catch (e) {
        console.error('[Chat] Fetch messages error:', e);
      }
    }
    
    async function sendMessage(content) {
      if (!activeTarget || !content.trim()) return;
      
      try {
        const res = await fetch(CONFIG.apiUrl + '/api/chat/messages', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + CONFIG.token
          },
          body: JSON.stringify({
            content: content.trim(),
            channel_id: activeTarget.type === 'channel' ? activeTarget.id : undefined,
            group_id: activeTarget.type === 'group' ? activeTarget.id : undefined,
            user_name: CONFIG.userName,
            user_avatar: CONFIG.userAvatar
          })
        });
        
        if (res.ok) {
          const msg = await res.json();
          // Check if already exists (WebSocket might have added it first)
          const exists = messages.some(m => m.id === msg.id);
          if (!exists) {
            // Add at START (array is newest-first)
            messages.unshift(msg);
            renderMessages();
            scrollToBottom();
          }
        }
      } catch (e) {
        console.error('[Chat] Send message error:', e);
      }
    }
    
    // ============================================================
    // UI ACTIONS
    // ============================================================
    window.selectChannel = async function(id) {
      if (activeTarget) unsubscribe(activeTarget);
      activeTarget = { type: 'channel', id };
      messages = [];
      render();
      await fetchMessages();
      subscribe(activeTarget);
      renderMessages();
      scrollToBottom();
    };
    
    window.selectGroup = async function(id) {
      if (activeTarget) unsubscribe(activeTarget);
      activeTarget = { type: 'group', id };
      messages = [];
      render();
      await fetchMessages();
      subscribe(activeTarget);
      renderMessages();
      scrollToBottom();
    };
    
    // Ticker search state
    let tickerSearchVisible = false;
    let tickerResults = [];
    let tickerSelectedIndex = 0;
    let tickerSearchTimeout = null;
    
    window.handleInput = function(e) {
      // Send typing indicator (debounced)
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(sendTyping, 300);
      
      // Update send button color
      const sendBtn = document.getElementById('send-btn');
      if (sendBtn) {
        if (e.target.value.trim()) {
          sendBtn.className = 'p-1 rounded bg-blue-600 text-white shrink-0 transition-colors hover:bg-blue-700';
        } else {
          sendBtn.className = 'p-1 rounded bg-slate-100 text-slate-400/40 shrink-0 transition-colors';
        }
      }
      
      // Check for $ at end to open ticker search
      if (e.target.value.endsWith('$')) {
        showTickerSearch();
      }
    };
    
    window.toggleTickerSearch = function() {
      if (tickerSearchVisible) {
        hideTickerSearch();
      } else {
        showTickerSearch();
      }
    };
    
    function showTickerSearch() {
      tickerSearchVisible = true;
      const dropdown = document.getElementById('ticker-dropdown');
      const tickerBtn = document.getElementById('ticker-btn');
      if (dropdown) {
        dropdown.classList.remove('hidden');
        const input = document.getElementById('ticker-search-input');
        if (input) {
          input.value = '';
          input.focus();
        }
      }
      if (tickerBtn) {
        tickerBtn.className = 'p-1 rounded bg-blue-600 text-white shrink-0';
      }
      tickerResults = [];
      tickerSelectedIndex = 0;
      renderTickerResults();
    }
    
    function hideTickerSearch() {
      tickerSearchVisible = false;
      const dropdown = document.getElementById('ticker-dropdown');
      const tickerBtn = document.getElementById('ticker-btn');
      if (dropdown) dropdown.classList.add('hidden');
      if (tickerBtn) tickerBtn.className = 'p-1 rounded transition-colors hover:bg-slate-100 text-slate-400 shrink-0';
      document.getElementById('message-input')?.focus();
    }
    
    window.handleTickerSearch = function(e) {
      const query = e.target.value.toUpperCase();
      clearTimeout(tickerSearchTimeout);
      
      if (!query) {
        tickerResults = [];
        renderTickerResults();
        return;
      }
      
      tickerSearchTimeout = setTimeout(async () => {
        try {
          const res = await fetch('https://tradeul.com/api/v1/metadata/search?q=' + encodeURIComponent(query) + '&limit=10');
          if (res.ok) {
            tickerResults = await res.json();
            tickerSelectedIndex = 0;
            renderTickerResults();
          }
        } catch (e) {
          console.error('[Chat] Ticker search error:', e);
        }
      }, 200);
    };
    
    window.handleTickerKeyDown = function(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        hideTickerSearch();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        tickerSelectedIndex = Math.min(tickerSelectedIndex + 1, tickerResults.length - 1);
        renderTickerResults();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        tickerSelectedIndex = Math.max(tickerSelectedIndex - 1, 0);
        renderTickerResults();
      } else if (e.key === 'Enter' && tickerResults.length > 0) {
        e.preventDefault();
        insertTicker(tickerResults[tickerSelectedIndex].symbol);
      }
    };
    
    window.selectTicker = function(symbol) {
      insertTicker(symbol);
    };
    
    function insertTicker(symbol) {
      const input = document.getElementById('message-input');
      if (input) {
        // Replace trailing $ with $TICKER
        if (input.value.endsWith('$')) {
          input.value = input.value.slice(0, -1) + '$' + symbol + ' ';
        } else {
          input.value += '$' + symbol + ' ';
        }
        
        // Update send button
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) {
          sendBtn.className = 'p-1 rounded bg-blue-600 text-white shrink-0 transition-colors hover:bg-blue-700';
        }
      }
      hideTickerSearch();
    }
    
    function renderTickerResults() {
      const container = document.getElementById('ticker-results');
      if (!container) return;
      
      if (tickerResults.length === 0) {
        container.innerHTML = '<div class="px-3 py-2 text-[10px] text-slate-400 text-center">Type to search...</div>';
        return;
      }
      
      container.innerHTML = tickerResults.map((t, i) => \`
        <button 
          onclick="selectTicker('\${t.symbol}')"
          class="w-full text-left px-3 py-1.5 text-xs hover:bg-slate-100 \${i === tickerSelectedIndex ? 'bg-slate-100' : ''}"
        >
          <span class="text-blue-600 font-mono">$\${t.symbol}</span>
          <span class="text-slate-500 ml-1">- \${t.name || ''}</span>
        </button>
      \`).join('');
    }
    
    window.handleKeyDown = function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const input = document.getElementById('message-input');
        if (input.value.trim()) {
          sendMessage(input.value);
          input.value = '';
        }
      }
    };
    
    window.handleSend = function() {
      const input = document.getElementById('message-input');
      if (input.value.trim()) {
        sendMessage(input.value);
        input.value = '';
      }
    };
    
    // ============================================================
    // RENDER
    // ============================================================
    function formatTime(isoString) {
      if (!isoString) return '';
      try {
        const d = new Date(isoString);
        return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase();
      } catch { return ''; }
    }
    
    function getUserColor(userId) {
      const colors = ['text-red-500', 'text-orange-500', 'text-amber-500', 'text-emerald-500', 
                      'text-cyan-500', 'text-blue-500', 'text-violet-500', 'text-pink-500'];
      const hash = userId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
      return colors[hash % colors.length];
    }
    
    function render() {
      const activeName = activeTarget?.type === 'channel'
        ? (channels.find(c => c.id === activeTarget.id)?.name || 'Chat')
        : (groups.find(g => g.id === activeTarget.id)?.name || 'Group');
      
      const statusDot = isConnected ? 'bg-emerald-500' : 'bg-slate-300 animate-pulse';
      const statusText = isConnected ? 'OK' : '...';
      const isGroup = activeTarget?.type === 'group';
      
      document.getElementById('root').innerHTML = \`
        <div class="h-screen flex bg-white text-xs" style="font-family: 'JetBrains Mono', monospace;">
          <!-- Sidebar - w-36 like ChatContent -->
          <div class="w-36 border-r border-slate-200 flex flex-col overflow-hidden" style="background: rgba(248, 250, 252, 0.2);">
            
            <!-- DMs / Groups Section FIRST (top) -->
            <div class="p-1.5 border-b border-slate-200">
              <div class="flex items-center justify-between px-1 mb-1">
                <div class="flex items-center gap-0.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider">
                  <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
                  DMs / Groups
                </div>
              </div>
              \${groups.length === 0 ? \`
                <div class="text-[10px] text-slate-400 px-1.5 py-0.5 italic">No groups yet</div>
              \` : groups.map(g => \`
                <button 
                  onclick="selectGroup('\${g.id}')"
                  class="w-full flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors text-left \${activeTarget?.type === 'group' && activeTarget?.id === g.id ? 'bg-blue-600 text-white' : 'hover:bg-slate-100 text-slate-700'}"
                >
                  <svg class="w-2.5 h-2.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/>
                  </svg>
                  <span class="truncate">\${g.name}</span>
                </button>
              \`).join('')}
            </div>
            
            <!-- Public Channels Section SECOND (bottom) -->
            <div class="p-1.5 flex-1 overflow-y-auto">
              <div class="flex items-center gap-0.5 text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-1">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
                Public Channels
              </div>
              \${channels.map(ch => \`
                <button 
                  onclick="selectChannel('\${ch.id}')"
                  class="w-full flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors text-left \${activeTarget?.type === 'channel' && activeTarget?.id === ch.id ? 'bg-blue-600 text-white' : 'hover:bg-slate-100 text-slate-700'}"
                >
                  <svg class="w-2.5 h-2.5 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14"/></svg>
                  <span class="truncate">\${ch.name}</span>
                </button>
              \`).join('')}
            </div>
            
            <!-- Connection Status -->
            <div class="p-1.5 border-t border-slate-200">
              <div class="flex items-center gap-1 px-1 text-[9px] text-slate-400">
                <span class="w-1.5 h-1.5 rounded-full \${statusDot}"></span>
                <span>\${statusText}</span>
              </div>
            </div>
          </div>
          
          <!-- Main Chat Area -->
          <div class="flex-1 flex flex-col min-w-0 relative">
            <!-- Header - h-7 like ChatContent -->
            <div class="h-7 px-2 flex items-center gap-2 border-b border-slate-200" style="background: rgba(248, 250, 252, 0.3);">
              <div class="flex items-center gap-1">
                \${isGroup ? \`
                  <svg class="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/>
                  </svg>
                \` : \`
                  <svg class="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14"/></svg>
                \`}
                <span class="font-medium text-xs">\${activeName}</span>
              </div>
              <div class="flex items-center gap-1 text-[9px] text-slate-400 ml-auto">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                <span id="online-count">0</span>
              </div>
            </div>
            
            <!-- Ticker Search Dropdown (hidden by default) -->
            <div id="ticker-dropdown" class="hidden absolute left-2 right-2 bottom-14 bg-white border border-slate-200 rounded shadow-lg z-10">
              <div class="p-1.5 border-b border-slate-200">
                <input 
                  id="ticker-search-input"
                  type="text" 
                  placeholder="Search ticker..."
                  oninput="handleTickerSearch(event)"
                  onkeydown="handleTickerKeyDown(event)"
                  class="w-full px-2 py-1 text-xs bg-slate-100 rounded focus:outline-none focus:ring-1 focus:ring-blue-400/50"
                  autocomplete="off"
                />
              </div>
              <div id="ticker-results" class="py-1 max-h-48 overflow-y-auto">
                <div class="px-3 py-2 text-[10px] text-slate-400 text-center">Type to search...</div>
              </div>
            </div>
            
            <!-- Messages Container -->
            <div id="messages-container" class="flex-1 overflow-y-auto">
              <div class="flex items-center justify-center h-full text-slate-400 text-[10px]">
                Loading messages...
              </div>
            </div>
            
            <!-- Typing Indicator -->
            <div id="typing-indicator" class="h-5 px-2 text-[10px] text-slate-400/60"></div>
            
            <!-- Input Area -->
            <div class="px-2 py-1.5 border-t border-slate-200 flex items-center gap-1.5">
              <button 
                onclick="toggleTickerSearch()"
                id="ticker-btn"
                class="p-1 rounded transition-colors hover:bg-slate-100 text-slate-400 shrink-0"
                title="Insert ticker ($)"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </button>
              <input 
                id="message-input"
                type="text" 
                placeholder="Message... ($ for ticker)"
                oninput="handleInput(event)"
                onkeydown="handleKeyDown(event)"
                class="flex-1 px-2 py-1 text-xs bg-slate-100 rounded border-0 focus:ring-1 focus:ring-blue-400/50 focus:outline-none placeholder:text-slate-400/60"
              />
              <button 
                onclick="handleSend()"
                id="send-btn"
                class="p-1 rounded bg-slate-100 text-slate-400/40 shrink-0 transition-colors"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
              </button>
            </div>
          </div>
        </div>
      \`;
      
      renderMessages();
    }
    
    function renderMessages() {
      const container = document.getElementById('messages-container');
      if (!container) return;
      
      if (messages.length === 0) {
        container.innerHTML = \`
          <div class="flex items-center justify-center h-full text-slate-400 text-[10px]">
            No messages yet. Start the conversation!
          </div>
        \`;
        return;
      }
      
      // Messages array is newest-first (from API DESC order)
      // We need to display oldest-first (scroll down = newer)
      // So we slice and reverse for display
      const sortedMessages = messages.slice().sort((a, b) => {
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      });
      
      console.log('[Chat] Rendering', messages.length, 'messages. First:', messages[0]?.created_at, 'After sort first:', sortedMessages[0]?.created_at);
      
      container.innerHTML = sortedMessages.map(msg => {
        const time = formatTime(msg.created_at);
        const colorClass = getUserColor(msg.user_id);
        const isSystem = msg.content_type === 'system';
        
        if (isSystem) {
          return \`
            <div class="flex justify-center my-1">
              <div class="px-2 py-0.5 rounded-full bg-slate-100/50 text-slate-500 text-[10px] italic">
                \${msg.content}
              </div>
            </div>
          \`;
        }
        
        // Parse ticker mentions ($AAPL)
        const content = parseTickerMentions(msg.content, msg.ticker_prices);
        
        return \`
          <div class="message group relative px-1 leading-tight hover:bg-slate-50/50">
            <span class="text-[9px] text-slate-400/40">\${time}</span>
            <span class="\${colorClass}">\${msg.user_name || 'anon'}</span><span class="text-slate-400/30">:</span>
            <span class="text-slate-700">\${content}</span>
          </div>
        \`;
      }).join('') + '<div style="height: 20px;"></div>'; // Padding at bottom
    }
    
    function parseTickerMentions(content, tickerPrices) {
      if (!content) return '';
      
      // Replace $TICKER with styled mentions
      return escapeHtml(content).replace(/\\$([A-Z]{1,5})/g, (match, symbol) => {
        const priceData = tickerPrices?.[symbol];
        if (priceData) {
          const changeClass = priceData.change > 0 ? 'change-positive' : priceData.change < 0 ? 'change-negative' : '';
          const changeSign = priceData.change > 0 ? '+' : '';
          return \`<span class="ticker-mention">
            <span class="symbol">$\${symbol}</span>
            <span class="text-slate-400/80">·</span>
            <span class="price">\${priceData.price.toFixed(2)}</span>
            <span class="\${changeClass}">\${changeSign}\${priceData.changePercent.toFixed(2)}%</span>
          </span>\`;
        }
        return \`<span class="ticker-mention"><span class="symbol">$\${symbol}</span></span>\`;
      });
    }
    
    function renderTyping() {
      const el = document.getElementById('typing-indicator');
      if (!el) return;
      
      if (typingUsers.length === 0) {
        el.innerHTML = '';
        return;
      }
      
      const names = typingUsers.length === 1 
        ? typingUsers[0].user_name + '...'
        : typingUsers.length + ' typing...';
      el.innerHTML = \`<span class="text-[10px] text-slate-400/60">\${names}</span>\`;
    }
    
    function scrollToBottom() {
      const container = document.getElementById('messages-container');
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
    
    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
    
    // ============================================================
    // INIT
    // ============================================================
    async function init() {
      await Promise.all([fetchChannels(), fetchGroups()]);
      render();
      await fetchMessages();
      renderMessages();
      scrollToBottom();
      initWebSocket();
    }
    
    init();
    console.log('✅ [Chat Window] Initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Chat injected');
}

// ============================================================
// NOTES WINDOW
// ============================================================

interface NotesNote {
  id: string;
  title: string;
  content: string;
  createdAt: number;
  updatedAt: number;
}

interface NotesWindowData {
  notes: NotesNote[];
  activeNoteId: string | null;
}

export function openNotesWindow(
  data: NotesWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 600,
    height = 550,
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
    console.error('❌ Notes window blocked');
    return null;
  }

  injectNotesContent(newWindow, data, config);

  return newWindow;
}

function injectNotesContent(
  targetWindow: Window,
  data: NotesWindowData,
  config: WindowConfig
): void {
  const { title } = config;

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace']
          },
          colors: {
            background: '#FFFFFF',
            foreground: '#0F172A',
            primary: { DEFAULT: '#2563EB', hover: '#1D4ED8' },
            border: '#E2E8F0',
            muted: '#F8FAFC',
            success: '#10B981',
            danger: '#EF4444'
          }
        }
      }
    }
  </script>
  
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; box-sizing: border-box; }
    body { font-family: 'Inter', sans-serif; color: #0F172A; background: #ffffff; margin: 0; font-size: 14px; }
    *::-webkit-scrollbar { width: 6px; height: 6px; }
    *::-webkit-scrollbar-track { background: #F8FAFC; }
    *::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
    *::-webkit-scrollbar-thumb:hover { background: #2563EB; }
    
    .note-tab { transition: all 0.15s; }
    .note-tab:hover { background-color: #F1F5F9; }
    .note-tab.active { background-color: white; border-bottom-color: #2563EB; color: #1E293B; }
    
    .toolbar-btn { transition: all 0.15s; }
    .toolbar-btn:hover { background-color: #F1F5F9; color: #1E293B; }
    .toolbar-btn.active { background-color: #2563EB; color: white; }
    
    #editor { outline: none; min-height: 100%; }
    #editor h1 { font-size: 1.125rem; font-weight: 700; margin: 0.75rem 0 0.5rem; }
    #editor h2 { font-size: 1rem; font-weight: 600; margin: 0.5rem 0 0.5rem; }
    #editor h3 { font-size: 0.875rem; font-weight: 600; margin: 0.5rem 0 0.25rem; }
    #editor ul { list-style-type: disc; padding-left: 1.25rem; margin: 0.25rem 0; }
    #editor ol { list-style-type: decimal; padding-left: 1.25rem; margin: 0.25rem 0; }
    #editor li { margin: 0.125rem 0; }
    #editor a { color: #2563EB; text-decoration: underline; }
    #editor p { margin: 0.25rem 0; }
  </style>
</head>
<body class="bg-white overflow-hidden">
  <div id="root" class="h-screen flex flex-col">
    <!-- Header with tabs -->
    <div class="flex items-center border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
      <!-- Tabs container -->
      <div id="tabs-container" class="flex-1 flex items-end gap-0.5 px-2 pt-1.5 overflow-x-auto">
        <!-- Tabs will be rendered here -->
      </div>
      
      <!-- Actions -->
      <div class="flex items-center gap-1 px-2 py-1.5">
        <!-- Save status -->
        <div id="save-status" class="hidden items-center gap-1 text-[9px] px-1.5 py-0.5 rounded"></div>
        
        <!-- New note button -->
        <button id="btn-new-note" class="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors" title="Nueva Nota">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
          </svg>
        </button>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-0.5 px-2 py-1.5 border-b border-slate-200 bg-slate-50/80">
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="bold" title="Bold (Ctrl+B)">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
          <path d="M6 4h8a4 4 0 014 4 4 4 0 01-4 4H6V4zM6 12h9a4 4 0 014 4 4 4 0 01-4 4H6v-8z"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="italic" title="Italic (Ctrl+I)">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M19 4h-9M14 20H5M15 4L9 20"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="underline" title="Underline (Ctrl+U)">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M6 3v7a6 6 0 006 6 6 6 0 006-6V3M4 21h16"></path>
        </svg>
      </button>
      
      <div class="w-px h-4 bg-slate-200 mx-1"></div>
      
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-block="h1" title="Heading 1">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M4 12h8M4 6v12M12 6v12M17 12l3-2v8"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-block="h2" title="Heading 2">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M4 12h8M4 6v12M12 6v12M17 10c.7-.5 1.5-.8 2.3-.8 1 0 2 .5 2.5 1.3.5.8.5 1.7 0 2.5s-1.5 1.3-2.5 1.3H17v2h5"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-block="h3" title="Heading 3">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M4 12h8M4 6v12M12 6v12M17.5 10.5c1-.7 2.5-.5 3.3.5s.5 2.5-.5 3.3M17.5 17.5c1 .7 2.5.5 3.3-.5s.5-2.5-.5-3.3"></path>
        </svg>
      </button>
      
      <div class="w-px h-4 bg-slate-200 mx-1"></div>
      
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="insertUnorderedList" title="Bullet List">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="insertOrderedList" title="Numbered List">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M10 6h11M10 12h11M10 18h11M4 6h1v4M4 10h2M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"></path>
        </svg>
      </button>
      
      <div class="w-px h-4 bg-slate-200 mx-1"></div>
      
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-action="link" title="Insert Link">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"></path>
        </svg>
      </button>
    </div>

    <!-- Editor container -->
    <div class="flex-1 relative overflow-hidden">
      <div id="placeholder" class="absolute inset-0 pointer-events-none p-3 text-slate-400 text-sm">
        Escribe algo...
      </div>
      <div id="editor" contenteditable="true" class="h-full overflow-y-auto p-3 text-sm text-slate-800"></div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between px-3 py-1.5 border-t border-slate-100 bg-slate-50/50 text-[9px] text-slate-400">
      <span>Auto-guardado activo</span>
      <span id="last-updated"></span>
    </div>
  </div>

  <script>
    // ============================================================
    // STATE
    // ============================================================
    const STORAGE_KEY = 'tradeul-notes-storage';
    let notes = ${JSON.stringify(data.notes)};
    let activeNoteId = ${JSON.stringify(data.activeNoteId)};
    let saveTimeout = null;
    
    console.log('📝 [Notes] Init with', notes.length, 'notes');
    
    // ============================================================
    // PERSISTENCE
    // ============================================================
    function loadFromStorage() {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed.state) {
            notes = parsed.state.notes || [];
            activeNoteId = parsed.state.activeNoteId || null;
          }
        }
      } catch (e) {
        console.error('[Notes] Load error:', e);
      }
    }
    
    function saveToStorage() {
      try {
        const data = {
          state: { notes, activeNoteId },
          version: 1
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      } catch (e) {
        console.error('[Notes] Save error:', e);
      }
    }
    
    // ============================================================
    // NOTES MANAGEMENT
    // ============================================================
    function generateId() {
      return 'note-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }
    
    function getActiveNote() {
      return notes.find(n => n.id === activeNoteId) || null;
    }
    
    function createNote() {
      const id = generateId();
      const now = Date.now();
      let titleNum = notes.length + 1;
      let title = 'Note ' + titleNum;
      while (notes.some(n => n.title === title)) {
        titleNum++;
        title = 'Note ' + titleNum;
      }
      
      const newNote = { id, title, content: '', createdAt: now, updatedAt: now };
      notes.push(newNote);
      activeNoteId = id;
      saveToStorage();
      render();
    }
    
    function deleteNote(id) {
      if (notes.length === 1) {
        // Last note - just clear it
        notes[0].content = '';
        notes[0].title = 'Note 1';
        notes[0].updatedAt = Date.now();
      } else {
        const idx = notes.findIndex(n => n.id === id);
        notes.splice(idx, 1);
        if (activeNoteId === id) {
          activeNoteId = notes[0]?.id || null;
        }
      }
      saveToStorage();
      render();
    }
    
    function selectNote(id) {
      activeNoteId = id;
      saveToStorage();
      render();
    }
    
    function updateNoteContent(content) {
      const note = getActiveNote();
      if (note) {
        note.content = content;
        note.updatedAt = Date.now();
        showSaveStatus('saving');
        
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
          saveToStorage();
          showSaveStatus('saved');
          updateLastModified();
        }, 500);
      }
    }
    
    function renameNote(id, newTitle) {
      const note = notes.find(n => n.id === id);
      if (note && newTitle.trim()) {
        note.title = newTitle.trim();
        note.updatedAt = Date.now();
        saveToStorage();
        render();
      }
    }
    
    // ============================================================
    // UI HELPERS
    // ============================================================
    function showSaveStatus(status) {
      const el = document.getElementById('save-status');
      el.classList.remove('hidden');
      el.classList.add('flex');
      
      if (status === 'saved') {
        el.className = 'flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded text-green-600 bg-green-50';
        el.innerHTML = '<svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg><span>Guardado</span>';
        setTimeout(() => { el.classList.add('hidden'); el.classList.remove('flex'); }, 1500);
      } else {
        el.className = 'flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded text-slate-500 bg-slate-100';
        el.innerHTML = '<svg class="w-2.5 h-2.5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path></svg><span>Guardando...</span>';
      }
    }
    
    function updateLastModified() {
      const note = getActiveNote();
      if (note) {
        const date = new Date(note.updatedAt);
        document.getElementById('last-updated').textContent = date.toLocaleString(undefined, {
          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
      }
    }
    
    function updatePlaceholder() {
      const editor = document.getElementById('editor');
      const placeholder = document.getElementById('placeholder');
      const isEmpty = !editor.textContent.trim();
      placeholder.style.display = isEmpty ? 'block' : 'none';
    }
    
    // ============================================================
    // RENDER
    // ============================================================
    function renderTabs() {
      const container = document.getElementById('tabs-container');
      container.innerHTML = notes.map(note => {
        const isActive = note.id === activeNoteId;
        return \`
          <div class="note-tab group flex items-center gap-1 px-2 py-1 rounded-t-md border-b-2 cursor-pointer min-w-0 max-w-[140px] \${isActive ? 'active bg-white border-blue-500 text-slate-800' : 'bg-slate-50 border-transparent text-slate-500 hover:text-slate-700'}" data-id="\${note.id}">
            <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            <span class="tab-title text-[10px] font-medium truncate">\${escapeHtml(note.title)}</span>
            <button class="btn-close ml-auto opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 hover:text-red-600 transition-all" data-delete="\${note.id}">
              <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
          </div>
        \`;
      }).join('');
      
      // Add click handlers
      container.querySelectorAll('.note-tab').forEach(tab => {
        const id = tab.dataset.id;
        tab.addEventListener('click', (e) => {
          if (!e.target.closest('.btn-close')) {
            selectNote(id);
          }
        });
        
        // Double click to rename
        const titleEl = tab.querySelector('.tab-title');
        titleEl.addEventListener('dblclick', (e) => {
          e.stopPropagation();
          const note = notes.find(n => n.id === id);
          if (note) {
            const input = document.createElement('input');
            input.type = 'text';
            input.value = note.title;
            input.className = 'w-full text-[10px] font-medium bg-transparent border-none outline-none px-0';
            titleEl.replaceWith(input);
            input.focus();
            input.select();
            
            const finish = () => {
              renameNote(id, input.value);
            };
            input.addEventListener('blur', finish);
            input.addEventListener('keydown', (e) => {
              if (e.key === 'Enter') finish();
              if (e.key === 'Escape') { input.value = note.title; finish(); }
            });
          }
        });
      });
      
      container.querySelectorAll('.btn-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          deleteNote(btn.dataset.delete);
        });
      });
    }
    
    function renderEditor() {
      const editor = document.getElementById('editor');
      const note = getActiveNote();
      
      if (note) {
        editor.innerHTML = note.content;
      } else {
        editor.innerHTML = '';
      }
      updatePlaceholder();
      updateLastModified();
    }
    
    function render() {
      renderTabs();
      renderEditor();
    }
    
    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
    
    // ============================================================
    // EVENT HANDLERS
    // ============================================================
    function setupEventHandlers() {
      const editor = document.getElementById('editor');
      
      // Editor input
      editor.addEventListener('input', () => {
        updateNoteContent(editor.innerHTML);
        updatePlaceholder();
      });
      
      // New note button
      document.getElementById('btn-new-note').addEventListener('click', createNote);
      
      // Toolbar buttons
      document.querySelectorAll('.toolbar-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const cmd = btn.dataset.cmd;
          const block = btn.dataset.block;
          const action = btn.dataset.action;
          
          if (cmd) {
            document.execCommand(cmd, false);
            editor.focus();
          } else if (block) {
            document.execCommand('formatBlock', false, block);
            editor.focus();
          } else if (action === 'link') {
            const url = prompt('Introduce la URL:');
            if (url) {
              document.execCommand('createLink', false, url);
              editor.focus();
            }
          }
        });
      });
      
      // Keyboard shortcuts
      document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          // Force save
          const note = getActiveNote();
          if (note) {
            clearTimeout(saveTimeout);
            saveToStorage();
            showSaveStatus('saved');
            updateLastModified();
          }
        }
      });
    }
    
    // ============================================================
    // INIT
    // ============================================================
    function init() {
      // Load fresh from storage (in case it was updated)
      loadFromStorage();
      
      // Create first note if none exist
      if (notes.length === 0) {
        const id = generateId();
        const now = Date.now();
        notes.push({ id, title: 'Note 1', content: '', createdAt: now, updatedAt: now });
        activeNoteId = id;
        saveToStorage();
      }
      
      // Set active note if not set
      if (!activeNoteId && notes.length > 0) {
        activeNoteId = notes[0].id;
      }
      
      render();
      setupEventHandlers();
    }
    
    init();
    console.log('✅ [Notes] Initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Notes injected');
}
