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

    // Filtrar por lista
    if (message.list && !sub.lists.has(message.list)) {
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

  subscriptions.forEach(function(sub) {
    sub.lists.forEach(function(list) {
      allLists.add(list);
    });
  });

  if (allLists.size > 0 && ws && ws.readyState === WebSocket.OPEN) {
    allLists.forEach(function(list) {
      ws.send(JSON.stringify({ action: 'subscribe_list', list: list }));
    });
    log('info', '📋 Re-subscribed to ' + allLists.size + ' lists');
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




