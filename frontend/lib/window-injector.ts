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
  
  <!-- Tailwind CSS con configuración personalizada -->
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
        <p class="text-slate-600 text-sm mt-2">Estableciendo conexión WebSocket</p>
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
          <!-- Header (IDÉNTICO a MarketTableLayout) -->
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
                <tr>
                  <th class="px-3 py-3 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider" style="width:40px">#</th>
                  <th onclick="handleSort('symbol')" class="px-3 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:75px">
                    <div class="flex items-center gap-1">
                      Symbol
                      <span class="sort-icon">\${getSortIcon('symbol')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('price')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:80px">
                    <div class="flex items-center justify-end gap-1">
                      Price
                      <span class="sort-icon">\${getSortIcon('price')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('change_percent')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:85px">
                    <div class="flex items-center justify-end gap-1">
                      Gap %
                      <span class="sort-icon">\${getSortIcon('change_percent')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('volume_today')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:90px">
                    <div class="flex items-center justify-end gap-1">
                      Volume
                      <span class="sort-icon">\${getSortIcon('volume_today')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('rvol')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:70px">
                    <div class="flex items-center justify-end gap-1">
                      RVOL
                      <span class="sort-icon">\${getSortIcon('rvol')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('market_cap')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:100px">
                    <div class="flex items-center justify-end gap-1">
                      Market Cap
                      <span class="sort-icon">\${getSortIcon('market_cap')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('float_shares')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:90px">
                    <div class="flex items-center justify-end gap-1">
                      Float
                      <span class="sort-icon">\${getSortIcon('float_shares')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('atr_percent')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:70px">
                    <div class="flex items-center justify-end gap-1">
                      ATR%
                      <span class="sort-icon">\${getSortIcon('atr_percent')}</span>
                    </div>
                  </th>
                  <th onclick="handleSort('atr_used')" class="px-3 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:bg-slate-100 transition-colors" style="width:85px">
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
        <tr id="row-\${ticker.symbol}" class="hover:bg-slate-50 transition-colors duration-150 border-b border-slate-100">
          <td class="px-3 py-2.5 text-center font-semibold text-slate-400">\${rank}</td>
          <td class="px-3 py-2.5">
            <div class="font-bold text-blue-600 cursor-pointer hover:text-blue-800 hover:underline transition-colors">\${ticker.symbol}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            <div class="price-cell font-mono font-semibold px-1 py-0.5 rounded text-slate-900">\${formatPrice(ticker.price)}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            <div class="change-cell font-mono font-semibold \${isPositive ? 'text-emerald-600' : 'text-rose-600'}">\${formatPercent(gapPercent)}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            <div class="font-mono text-slate-700 font-medium">\${formatNumber(volume)}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            <div class="font-mono font-semibold \${rvolColor}">\${formatRVOL(rvol)}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            <div class="font-mono text-slate-600">\${formatNumber(ticker.market_cap)}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            <div class="font-mono text-slate-600">\${formatNumber(ticker.float_shares)}</div>
          </td>
          <td class="px-3 py-2.5 text-right">
            \${atrPercentHtml}
          </td>
          <td class="px-3 py-2.5 text-right">
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
