/**
 * News Window Injector
 * 
 * Standalone window for real-time news display with:
 * - WebSocket connection via SharedWorker
 * - Ticker filtering
 * - Pagination
 * - Article detail view
 * - Squawk (text-to-speech)
 */

import { getUserTimezoneForWindow, getUserFontForWindow, getFontConfig, WindowConfig } from './base';

// ============================================================================
// NEWS WINDOW
// ============================================================================

export interface NewsWindowData {
  wsUrl: string;
  workerUrl: string;
  apiBaseUrl: string;
  ticker?: string;
  existingArticles?: any[]; // Pass existing articles from store
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

  // Use existing articles from store if provided, otherwise fetch
  let initialNews: any[] = [];

  if (data.existingArticles && data.existingArticles.length > 0) {
    // Use articles from the store (already accumulated)
    initialNews = data.existingArticles;
    console.log(`✅ [News Window] Using ${initialNews.length} existing articles from store`);
  } else {
    // Fallback: Pre-fetch news data BEFORE opening about:blank
    try {
      const tickerParam = data.ticker ? `&ticker=${data.ticker}` : '';
      const response = await fetch(`${data.apiBaseUrl}/news/api/v1/news?limit=1000${tickerParam}`);
      if (response.ok) {
        const json = await response.json();
        initialNews = json.results || [];
      }
    } catch (error) {
      console.error('❌ Pre-fetch news failed:', error);
    }
  }

  const newWindow = window.open('about:blank', '_blank', windowFeatures);

  if (!newWindow) {
    console.error('❌ Window blocked');
    return null;
  }

  injectNewsContent(newWindow, data, config, initialNews);

  return newWindow;
}

// Helper to safely escape JSON for HTML script tags
function escapeJsonForHtml(obj: any): string {
  return JSON.stringify(obj)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/'/g, '\\u0027');
}

function injectNewsContent(
  targetWindow: Window,
  data: NewsWindowData,
  config: WindowConfig,
  initialNews: any[]
): void {
  const { title } = config;
  const userTimezone = getUserTimezoneForWindow();
  const userFont = getUserFontForWindow();
  const fontConfig = getFontConfig(userFont);

  // Escape data for safe HTML embedding
  const safeConfig = escapeJsonForHtml(data);
  const safeNews = escapeJsonForHtml(initialNews);

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
  
  <script src="https://cdn.tailwindcss.com"><\/script>
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
  <\/script>
  
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
    body { font-family: Inter, sans-serif; color: #171717; background: #ffffff; margin: 0; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
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
    const CONFIG = ${safeConfig};
    const INITIAL_NEWS = ${safeNews};
    const USER_TIMEZONE = '${userTimezone}';
    
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
    
    // NEW: Filtering and pagination state
    let tickerFilter = '';
    let currentPage = 1;
    const ITEMS_PER_PAGE = 200;
    let selectedArticle = null;
    
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
            render();
            
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
      
      render();
    }
    
    // ============================================================
    // SQUAWK (Text-to-Speech)
    // ============================================================
    window.toggleSquawk = function() {
      isSquawkEnabled = !isSquawkEnabled;
      if (!isSquawkEnabled) {
        squawkQueue = [];
      }
      render();
    }
    
    async function processSquawkQueue() {
      if (isSquawkPlaying || squawkQueue.length === 0) return;
      
      isSquawkPlaying = true;
      
      while (squawkQueue.length > 0) {
        const text = squawkQueue.shift();
        render(); // Update queue badge
        
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
      render();
    }
    
    function speakNews(text) {
      if (!isSquawkEnabled) return;
      const cleanText = text.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '').substring(0, 200);
      squawkQueue.push(cleanText);
      render();
      processSquawkQueue();
    }
    
    // ============================================================
    // FILTERING & PAGINATION
    // ============================================================
    function getFilteredNews() {
      if (!tickerFilter) return newsData;
      const upperFilter = tickerFilter.toUpperCase();
      return newsData.filter(article => 
        article.tickers && article.tickers.some(t => t.toUpperCase() === upperFilter)
      );
    }
    
    function getPaginatedNews() {
      const filtered = getFilteredNews();
      const start = (currentPage - 1) * ITEMS_PER_PAGE;
      return filtered.slice(start, start + ITEMS_PER_PAGE);
    }
    
    function getTotalPages() {
      return Math.ceil(getFilteredNews().length / ITEMS_PER_PAGE);
    }
    
    window.applyTickerFilter = function() {
      const input = document.getElementById('ticker-filter-input');
      tickerFilter = input ? input.value.trim().toUpperCase() : '';
      currentPage = 1;
      render();
    }
    
    window.clearTickerFilter = function() {
      tickerFilter = '';
      currentPage = 1;
      const input = document.getElementById('ticker-filter-input');
      if (input) input.value = '';
      render();
    }
    
    window.goToPage = function(page) {
      const total = getTotalPages();
      if (page >= 1 && page <= total) {
        currentPage = page;
        render();
      }
    }
    
    window.selectArticle = function(id) {
      console.log('selectArticle called with id:', id);
      selectedArticle = newsData.find(a => String(a.benzinga_id || a.id) === String(id)) || null;
      console.log('selectedArticle:', selectedArticle ? selectedArticle.title : 'not found');
      render();
    }
    
    window.backToList = function() {
      selectedArticle = null;
      render();
    }
    
    window.openArticleUrl = function(url) {
      window.open(url, '_blank');
    }
    
    // Setup event delegation for article clicks
    function setupClickHandlers() {
      document.addEventListener('click', function(e) {
        const row = e.target.closest('[data-article-id]');
        if (row) {
          const id = row.getAttribute('data-article-id');
          console.log('Row clicked, article id:', id);
          selectArticle(id);
        }
      });
    }
    
    // ============================================================
    // RENDER
    // ============================================================
    function formatDateTime(isoString) {
      if (!isoString) return { date: '—', time: '—' };
      try {
        const d = new Date(isoString);
        return {
          date: d.toLocaleDateString('en-US', { timeZone: USER_TIMEZONE, month: '2-digit', day: '2-digit', year: '2-digit' }),
          time: d.toLocaleTimeString('en-US', { timeZone: USER_TIMEZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
        };
      } catch { return { date: '—', time: '—' }; }
    }
    
    function decodeHtmlEntities(text) {
      if (!text) return text;
      const textarea = document.createElement('textarea');
      textarea.innerHTML = text;
      return textarea.value;
    }
    
    function escapeForOnclick(str) {
      if (!str) return '';
      return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }
    
    function render() {
      if (selectedArticle) {
        renderArticleDetail();
      } else {
        renderTable();
      }
    }
    
    function renderArticleDetail() {
      const article = selectedArticle;
      const dt = formatDateTime(article.published);
      const ticker = (article.tickers && article.tickers[0]) || '';
      const hasBody = article.body && article.body.trim().length > 0;
      const hasTeaser = article.teaser && article.teaser.trim().length > 0;
      const safeUrl = escapeForOnclick(article.url);
      
      const html = \`
        <div class="h-screen flex flex-col bg-white">
          <!-- Header -->
          <div class="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
            <button onclick="backToList()" class="px-2 py-1 bg-slate-200 text-slate-700 rounded hover:bg-slate-300 text-xs font-medium flex items-center gap-1">
              ← Back
            </button>
            <div class="text-xs text-slate-600 font-mono flex items-center gap-2">
              \${ticker ? \`<span class="font-semibold text-blue-600">\${ticker}</span><span>·</span>\` : ''}
              <span>\${dt.date}</span>
              <span>·</span>
              <span>\${dt.time}</span>
            </div>
            <button onclick="openArticleUrl('\${safeUrl}')" class="px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-xs font-medium flex items-center gap-1">
              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
              Open Original
            </button>
          </div>
          
          <!-- Content -->
          <div class="flex-1 overflow-auto">
            <div class="p-4">
              <h1 class="text-lg font-semibold text-slate-900 mb-3">\${decodeHtmlEntities(article.title)}</h1>
              
              <div class="flex items-center gap-3 text-xs text-slate-500 mb-4">
                <span>By \${article.author || 'Unknown'}</span>
                \${article.channels && article.channels.length > 0 ? \`<span class="text-slate-400">\${article.channels.join(', ')}</span>\` : ''}
              </div>
              
              \${hasBody ? \`
                <div class="prose prose-sm max-w-none text-slate-700 leading-relaxed">\${article.body}</div>
              \` : hasTeaser ? \`
                <div class="text-slate-700 leading-relaxed">
                  <p class="mb-4">\${decodeHtmlEntities(article.teaser)}</p>
                  <button onclick="openArticleUrl('\${safeUrl}')" class="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 font-medium text-sm">
                    Read more
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                  </button>
                </div>
              \` : \`
                <div class="text-center py-8">
                  <p class="text-slate-500 mb-4">Full content not available in the API response.</p>
                  <button onclick="openArticleUrl('\${safeUrl}')" class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                    Open on Benzinga
                  </button>
                </div>
              \`}
            </div>
          </div>
        </div>
      \`;
      
      document.getElementById('root').innerHTML = html;
    }
    
    function renderTable() {
      const filteredNews = getFilteredNews();
      const paginatedNews = getPaginatedNews();
      const totalPages = getTotalPages();
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
            <div class="flex items-center gap-3">
              <!-- Connection Status -->
              <div class="flex items-center gap-1.5">
                <div id="status-dot" class="\${statusDotClass}"></div>
                <span id="status-text" class="\${statusTextClass}">\${statusText}</span>
              </div>
              
              <!-- Pause/Squawk buttons -->
              <button onclick="togglePause()" class="\${pauseBtnClass}">\${pauseBtnText}</button>
              <button onclick="toggleSquawk()" class="\${squawkBtnClass}">\${squawkBtnText}\${squawkQueueBadge}</button>
              \${pausedInfo}
              
              <!-- Ticker Filter -->
              <form onsubmit="event.preventDefault(); applyTickerFilter();" class="flex items-center gap-1.5 ml-2 pl-2 border-l border-slate-300">
                <input 
                  id="ticker-filter-input" 
                  type="text" 
                  value="\${tickerFilter}"
                  placeholder="Ticker"
                  class="w-20 px-2 py-0.5 text-xs border border-slate-200 rounded focus:outline-none focus:border-blue-400 font-mono uppercase"
                />
                <button type="submit" class="px-2 py-0.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 font-medium">Filter</button>
                \${tickerFilter ? '<button type="button" onclick="clearTickerFilter()" class="px-1.5 py-0.5 text-slate-400 hover:text-slate-600 text-xs">✕</button>' : ''}
              </form>
            </div>
            
            <div class="flex items-center gap-3">
              <!-- Stats -->
              <div class="flex items-center gap-2 text-xs">
                \${tickerFilter ? \`<span class="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded font-mono font-medium">\${tickerFilter}</span>\` : ''}
                <span class="text-slate-600 font-mono">\${filteredNews.length}\${tickerFilter ? ' / ' + newsData.length : ''}</span>
                \${liveCount > 0 ? \`<span class="text-emerald-600">(\${liveCount} live)</span>\` : ''}
              </div>
              
              <!-- Pagination -->
              \${totalPages > 1 ? \`
                <div class="flex items-center gap-1 border-l border-slate-300 pl-3">
                  <button onclick="goToPage(\${currentPage - 1})" \${currentPage === 1 ? 'disabled' : ''} class="p-1 rounded hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed">
                    <svg class="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                  </button>
                  <span class="text-xs text-slate-600 font-mono min-w-[60px] text-center">\${currentPage} / \${totalPages}</span>
                  <button onclick="goToPage(\${currentPage + 1})" \${currentPage >= totalPages ? 'disabled' : ''} class="p-1 rounded hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed">
                    <svg class="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                  </button>
                </div>
              \` : ''}
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
                \${paginatedNews.length === 0 ? \`
                  <tr>
                    <td colspan="5" class="px-4 py-8 text-center text-slate-500">
                      \${tickerFilter ? 'No news found for ' + tickerFilter : 'No news available. Waiting for data...'}
                    </td>
                  </tr>
                \` : paginatedNews.map(article => {
                  const dt = formatDateTime(article.published);
                  const ticker = (article.tickers && article.tickers[0]) || '—';
                  const isLive = article.isLive;
                  const articleId = article.benzinga_id || article.id;
                  
                  return \`
                    <tr class="news-row cursor-pointer \${isLive ? 'live' : ''}" data-article-id="\${articleId}">
                      <td class="px-2 py-1">
                        <div class="flex items-center gap-1.5">
                          \${isLive ? '<span class="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse shrink-0"></span>' : ''}
                          <span class="text-slate-800 truncate" style="max-width:500px">\${decodeHtmlEntities(article.title)}</span>
                        </div>
                      </td>
                      <td class="px-2 py-1 text-center text-slate-500 font-mono">\${dt.date}</td>
                      <td class="px-2 py-1 text-center text-slate-500 font-mono">\${dt.time}</td>
                      <td class="px-2 py-1 text-center">
                        <span class="text-blue-600 font-mono font-semibold">\${ticker}</span>
                      </td>
                      <td class="px-2 py-1 text-slate-500 truncate" style="max-width:140px">\${article.author || '—'}</td>
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
    setupClickHandlers();
    render();
    initWebSocket();
    console.log('✅ News Window initialized');
  <\/script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] News injected');
}

