/**
 * Chat Window Injector
 * 
 * Standalone window for community chat
 */

import { getUserTimezoneForWindow, getUserFontForWindow, getFontConfig, WindowConfig } from './base';

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
    body { font-family: ${fontConfig.cssFamily}; color: #0F172A; background: #ffffff; margin: 0; font-size: 12px; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
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
    const USER_TIMEZONE = '${userTimezone}';
    
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
        return d.toLocaleTimeString('en-US', { timeZone: USER_TIMEZONE, hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase();
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

