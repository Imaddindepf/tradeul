/**
 * SharedWorker para WebSocket - Desacoplado de Next.js
 * 
 * Se sirve desde /public/ como archivo estático.
 * NO pasa por el build de Next.js/webpack.
 * 
 * Ganancia: 10 tabs = 1 conexión WS en lugar de 10
 */

/* global self, WebSocket */

let ws = null;
const ports = new Set();
const subscriptions = new Map();

let connectionInfo = {
  url: '',
  isConnected: false,
  reconnectAttempts: 0,
  reconnectTimer: null,
};

let heartbeatTimer = null;

// ============================================================================
// LOGGING
// ============================================================================

function log(level, message, data) {
  const logMsg = {
    type: 'log',
    level: level,
    message: message,
    data: data || null,
    timestamp: Date.now(),
  };

  ports.forEach(function(port) {
    try {
      port.postMessage(logMsg);
    } catch (e) {
      // Port cerrado
    }
  });
}

// ============================================================================
// WEBSOCKET
// ============================================================================

function connectWebSocket(url) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  try {
    log('info', '🚀 SharedWorker connecting to: ' + url);
    ws = new WebSocket(url);
    connectionInfo.url = url;

    ws.onopen = function() {
      log('info', '✅ SharedWorker WebSocket connected');
      connectionInfo.isConnected = true;
      connectionInfo.reconnectAttempts = 0;

      broadcastStatus();
      resubscribeAllLists();
      startHeartbeat();
    };

    ws.onmessage = function(event) {
      try {
        // Parse JSON en el worker (fuera del main thread)
        const message = JSON.parse(event.data);
        broadcastMessage(message);
      } catch (error) {
        log('error', 'Parse error: ' + error.message);
      }
    };

    ws.onerror = function() {
      log('error', 'WebSocket error');
    };

    ws.onclose = function() {
      log('warn', '❌ SharedWorker WebSocket closed');
      connectionInfo.isConnected = false;
      stopHeartbeat();
      broadcastStatus();

      // Auto-reconnect si hay tabs abiertas
      if (ports.size > 0) {
        const backoff = Math.min(3000 * Math.pow(2, connectionInfo.reconnectAttempts), 60000);
        connectionInfo.reconnectAttempts++;

        if (connectionInfo.reconnectTimer) {
          clearTimeout(connectionInfo.reconnectTimer);
        }

        connectionInfo.reconnectTimer = setTimeout(function() {
          log('info', '🔄 Reconnecting (attempt ' + connectionInfo.reconnectAttempts + ')');
          connectWebSocket(connectionInfo.url);
        }, backoff);
      }
    };
  } catch (error) {
    log('error', 'Failed to create WebSocket: ' + error.message);
  }
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ action: 'ping' }));
      } catch (error) {
        log('error', 'Heartbeat failed');
      }
    }
  }, 30000);
}

// ============================================================================
// BROADCASTING
// ============================================================================

function broadcastMessage(message) {
  ports.forEach(function(port) {
    const sub = subscriptions.get(port);
    if (!sub) return;

    // Si es mensaje de news, verificar suscripción a news
    if (message.type === 'news' || message.type === 'benzinga_news') {
      if (!sub.subscribedNews) return;
    }
    // Si es mensaje de SEC, verificar suscripción a SEC
    else if (message.type === 'sec_filing') {
      if (!sub.subscribedSEC) return;
    }
    // Filtrar por lista para mensajes del scanner
    else if (message.list && !sub.lists.has(message.list)) {
      return;
    }

    try {
      port.postMessage({
        type: 'message',
        data: message,
      });
    } catch (error) {
      // Port cerrado
      ports.delete(port);
      subscriptions.delete(port);
    }
  });
}

function broadcastStatus() {
  const status = {
    type: 'status',
    isConnected: connectionInfo.isConnected,
    reconnectAttempts: connectionInfo.reconnectAttempts,
    activePorts: ports.size,
  };

  ports.forEach(function(port) {
    try {
      port.postMessage(status);
    } catch (error) {
      ports.delete(port);
      subscriptions.delete(port);
    }
  });
}

function resubscribeAllLists() {
  const allLists = new Set();
  let hasNewsSubscribers = false;
  let hasSECSubscribers = false;

  subscriptions.forEach(function(sub) {
    sub.lists.forEach(function(list) {
      allLists.add(list);
    });
    if (sub.subscribedNews) {
      hasNewsSubscribers = true;
    }
    if (sub.subscribedSEC) {
      hasSECSubscribers = true;
    }
  });

  if (ws && ws.readyState === WebSocket.OPEN) {
    if (allLists.size > 0) {
    allLists.forEach(function(list) {
      ws.send(JSON.stringify({ action: 'subscribe_list', list: list }));
    });
    log('info', '📋 Re-subscribed to ' + allLists.size + ' lists');
    }
    
    if (hasNewsSubscribers) {
      ws.send(JSON.stringify({ action: 'subscribe_benzinga_news' }));
      log('info', '📰 Re-subscribed to news');
    }
    
    if (hasSECSubscribers) {
      ws.send(JSON.stringify({ action: 'subscribe_sec' }));
      log('info', '📄 Re-subscribed to SEC');
    }
  }
}

// ============================================================================
// MESSAGE HANDLERS
// ============================================================================

function handlePortMessage(port, data) {
  const sub = subscriptions.get(port);
  if (!sub) return;

  switch (data.action) {
    case 'connect':
      if (data.url) {
        connectWebSocket(data.url);
      }
      break;

    case 'subscribe_list':
      if (data.list) {
        sub.lists.add(data.list);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'subscribe_list', list: data.list }));
        }
      }
      break;

    case 'unsubscribe_list':
      if (data.list) {
        sub.lists.delete(data.list);

        // Solo desuscribir del WS si ninguna otra tab lo tiene
        let otherTabsHave = false;
        subscriptions.forEach(function(s, p) {
          if (p !== port && s.lists.has(data.list)) {
            otherTabsHave = true;
          }
        });

        if (!otherTabsHave && ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'unsubscribe_list', list: data.list }));
        }
      }
      break;

    case 'send':
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data.payload));
        
        // Auto-detectar suscripciones en payloads enviados
        if (data.payload && data.payload.action) {
          if (data.payload.action === 'subscribe_benzinga_news' || data.payload.action === 'subscribe_news') {
            sub.subscribedNews = true;
          } else if (data.payload.action === 'unsubscribe_benzinga_news' || data.payload.action === 'unsubscribe_news') {
            sub.subscribedNews = false;
          } else if (data.payload.action === 'subscribe_sec' || data.payload.action === 'subscribe_sec_filings') {
            sub.subscribedSEC = true;
          } else if (data.payload.action === 'unsubscribe_sec' || data.payload.action === 'unsubscribe_sec_filings') {
            sub.subscribedSEC = false;
          }
        }
      }
      break;

    case 'subscribe_news':
      sub.subscribedNews = true;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'subscribe_benzinga_news' }));
      }
      break;

    case 'unsubscribe_news':
      sub.subscribedNews = false;
      // Solo desuscribir si ningún otro port está suscrito
      let otherNewsSubscribers = false;
      subscriptions.forEach(function(s, p) {
        if (p !== port && s.subscribedNews) {
          otherNewsSubscribers = true;
        }
      });
      if (!otherNewsSubscribers && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'unsubscribe_benzinga_news' }));
      }
      break;

    case 'subscribe_sec':
      sub.subscribedSEC = true;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'subscribe_sec' }));
      }
      break;

    case 'unsubscribe_sec':
      sub.subscribedSEC = false;
      // Solo desuscribir si ningún otro port está suscrito
      let otherSECSubscribers = false;
      subscriptions.forEach(function(s, p) {
        if (p !== port && s.subscribedSEC) {
          otherSECSubscribers = true;
        }
      });
      if (!otherSECSubscribers && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'unsubscribe_sec' }));
      }
      break;
  }
}

// ============================================================================
// SHARED WORKER ENTRY
// ============================================================================

self.onconnect = function(e) {
  const port = e.ports[0];

  ports.add(port);
  subscriptions.set(port, {
    lists: new Set(),
    subscribedNews: false,
    subscribedSEC: false,
    connectionId: null,
  });

  log('info', '📱 Tab connected (total: ' + ports.size + ')');

  // Enviar estado actual
  port.postMessage({
    type: 'status',
    isConnected: connectionInfo.isConnected,
    reconnectAttempts: connectionInfo.reconnectAttempts,
    activePorts: ports.size,
  });

  port.onmessage = function(event) {
    handlePortMessage(port, event.data);
  };

  port.start();
};




