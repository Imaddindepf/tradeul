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
  waitingForToken: false, // Flag: esperando token nuevo antes de reconectar
  tokenTimeout: null,     // Timer de fallback si el token no llega
};

let heartbeatTimer = null;

// Trading day tracking para detectar cambio de sesión
// Se actualiza cuando:
// 1. Recibimos mensaje "connected" del servidor (al conectar)
// 2. Recibimos "market_session_change" con is_new_day o trading_date diferente
let currentTradingDate = null;

// ============================================================================
// LOGGING - Solo errores en producción
// ============================================================================

// Solo enviar logs de error al main thread
// Los logs de info/warn están desactivados para reducir ruido en consola
function log(level, message, data) {
  // Solo enviar errores críticos
  if (level !== 'error') {
    return;
  }
  
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

  // Limpiar WS anterior que no está OPEN (CONNECTING, CLOSING, CLOSED)
  if (ws) {
    try { ws.onclose = null; ws.onerror = null; ws.onopen = null; ws.onmessage = null; ws.close(); } catch(e) {}
    ws = null;
  }

  try {
    // Log silenciado - descomentar para debug
    // log('info', '🚀 SharedWorker connecting to: ' + url);
    ws = new WebSocket(url);
    connectionInfo.url = url;

    ws.onopen = function() {
      // Log silenciado - descomentar para debug
      // log('info', '✅ SharedWorker WebSocket connected');
      connectionInfo.isConnected = true;
      connectionInfo.reconnectAttempts = 0;
      connectionInfo.waitingForToken = false; // Limpiar flag
      
      // Limpiar timeout de token si existe
      if (connectionInfo.tokenTimeout) {
        clearTimeout(connectionInfo.tokenTimeout);
        connectionInfo.tokenTimeout = null;
      }

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
      // Log silenciado - descomentar para debug
      // log('warn', '❌ SharedWorker WebSocket closed');
      connectionInfo.isConnected = false;
      connectionInfo.waitingForToken = true; // Flag: esperando token nuevo
      stopHeartbeat();
      broadcastStatus();

      // Auto-reconnect: pedir token fresco, NUNCA reconectar con viejo
      if (ports.size > 0) {
        var backoff = Math.min(1000 * Math.pow(2, connectionInfo.reconnectAttempts), 30000);
        connectionInfo.reconnectAttempts++;

        if (connectionInfo.reconnectTimer) {
          clearTimeout(connectionInfo.reconnectTimer);
        }

        connectionInfo.reconnectTimer = setTimeout(function() {
          // Pedir token fresco al frontend
          ports.forEach(function(port) {
            try {
              port.postMessage({
                type: 'request_fresh_token',
                message: 'SharedWorker needs fresh token for reconnection'
              });
            } catch (e) { /* port cerrado */ }
          });
          
          // NO hay fallback con token viejo.
          // Solo reconectamos cuando frontend envía 'update_token'.
          // Safety: si no llega en 60s, re-pedir
          connectionInfo.tokenTimeout = setTimeout(function() {
            if (connectionInfo.waitingForToken && ports.size > 0) {
              ports.forEach(function(port) {
                try {
                  port.postMessage({
                    type: 'request_fresh_token',
                    message: 'SharedWorker retry: still waiting for fresh token'
                  });
                } catch (e) { /* port cerrado */ }
              });
            }
          }, 60000);
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
  // =========================================================================
  // DETECTAR CAMBIO DE DÍA DE TRADING
  // El servidor envía trading_date en:
  // 1. Mensaje "connected" (al conectar)
  // 2. Mensaje "market_session_change" (cuando cambia la sesión)
  // =========================================================================
  
  // CASO 1: Mensaje de conexión inicial - guardar trading_date
  if (message.type === 'connected' && message.trading_date) {
    const serverTradingDate = message.trading_date;
    
    // Si ya teníamos un trading_date y es diferente, es un cambio de día
    if (currentTradingDate && currentTradingDate !== serverTradingDate) {
      log('error', '🔄 Trading day changed (reconnect): ' + currentTradingDate + ' → ' + serverTradingDate);
      
      // Broadcast a todos los ports para que limpien su caché
      ports.forEach(function(port) {
        try {
          port.postMessage({
            type: 'trading_day_changed',
            data: {
              previousDate: currentTradingDate,
              newDate: serverTradingDate,
              session: message.current_session,
              timestamp: message.timestamp,
            },
          });
        } catch (e) {
          // Port cerrado
        }
      });
    }
    
    currentTradingDate = serverTradingDate;
  }
  
  // CASO 2: Cambio de sesión en tiempo real
  if (message.type === 'market_session_change' && message.data) {
    const newTradingDate = message.data.trading_date;
    const isNewDay = message.data.is_new_day;
    
    // Detectar cambio de día
    if (isNewDay || (newTradingDate && currentTradingDate && newTradingDate !== currentTradingDate)) {
      log('error', '🔄 Trading day changed: ' + currentTradingDate + ' → ' + newTradingDate);
      
      // Broadcast a todos los ports para que limpien su caché
      ports.forEach(function(port) {
        try {
          port.postMessage({
            type: 'trading_day_changed',
            data: {
              previousDate: currentTradingDate,
              newDate: newTradingDate,
              session: message.data.current_session,
              timestamp: message.data.timestamp,
            },
          });
        } catch (e) {
          // Port cerrado
        }
      });
    }
    
    // Actualizar el día de trading conocido
    if (newTradingDate) {
      currentTradingDate = newTradingDate;
    }
  }
  
  // =========================================================================
  // BROADCAST NORMAL DEL MENSAJE
  // =========================================================================
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
    // Market events: route by sub_id matching
    else if (message.type === 'market_event') {
      if (!sub.eventSubIds || sub.eventSubIds.size === 0) return;
      // Only forward if this port has at least one matching sub_id
      var matchedSubs = message.matched_subs || [];
      var hasMatch = false;
      for (var mi = 0; mi < matchedSubs.length; mi++) {
        if (sub.eventSubIds.has(matchedSubs[mi])) { hasMatch = true; break; }
      }
      if (!hasMatch) return;
    }
    else if (message.type === 'events_snapshot') {
      if (!sub.eventSubIds || sub.eventSubIds.size === 0) return;
      // Only forward snapshot to the port that owns this sub_id
      if (message.sub_id && !sub.eventSubIds.has(message.sub_id)) return;
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
    // Log silenciado - descomentar para debug
    // log('info', '📋 Re-subscribed to ' + allLists.size + ' lists');
    }
    
    if (hasNewsSubscribers) {
      ws.send(JSON.stringify({ action: 'subscribe_benzinga_news' }));
      // log('info', '📰 Re-subscribed to news');
    }
    
    if (hasSECSubscribers) {
      ws.send(JSON.stringify({ action: 'subscribe_sec' }));
      // log('info', '📄 Re-subscribed to SEC');
    }
    
    // Events are NOT re-subscribed here. Each EventTableContent component
    // re-subscribes with its own sub_id + filters via useEffect on ws.isConnected.
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
        // Limpiar CUALQUIER estado de reconexión pendiente
        if (connectionInfo.reconnectTimer) {
          clearTimeout(connectionInfo.reconnectTimer);
          connectionInfo.reconnectTimer = null;
        }
        if (connectionInfo.tokenTimeout) {
          clearTimeout(connectionInfo.tokenTimeout);
          connectionInfo.tokenTimeout = null;
        }
        connectionInfo.waitingForToken = false;
        connectionInfo.reconnectAttempts = 0;

        // Si ya estamos conectados, enviar status a este port específico
        // (necesario para ventanas popup que se conectan después)
        if (ws && ws.readyState === WebSocket.OPEN) {
          port.postMessage({
            type: 'status',
            isConnected: true,
            reconnectAttempts: 0,
            activePorts: ports.size,
          });
          return;
        }

        // Cerrar WS anterior roto (CONNECTING, CLOSING, etc.)
        if (ws && ws.readyState !== WebSocket.OPEN) {
          try { ws.onclose = null; ws.onerror = null; ws.close(); } catch(e) {}
          ws = null;
        }

        connectWebSocket(data.url);
      }
      break;

    // 🔐 ACTUALIZAR TOKEN SIN DESCONECTAR (para refresh periódico)
    case 'update_token':
      if (data.url) {
        connectionInfo.url = data.url; // Actualizar URL para futuras reconexiones
        
        // Si estamos esperando token para reconectar, hacerlo ahora
        if (connectionInfo.waitingForToken) {
          connectionInfo.waitingForToken = false;
          
          // Cancelar el timeout de fallback
          if (connectionInfo.tokenTimeout) {
            clearTimeout(connectionInfo.tokenTimeout);
            connectionInfo.tokenTimeout = null;
          }
          
          // log('info', '🔐 Got fresh token, reconnecting now...');
          connectWebSocket(data.url);
        }
        // Si ya estamos conectados, enviar refresh_token al servidor
        else if (ws && ws.readyState === WebSocket.OPEN && data.token) {
          ws.send(JSON.stringify({ action: 'refresh_token', token: data.token }));
          // log('info', '🔐 Sent refresh_token to server');
        }
      }
      break;

    // 🔐 RECONECTAR CON NUEVO TOKEN (cuando el servidor rechaza por token expirado)
    case 'reconnect_with_token':
      if (data.url) {
        // Log silenciado - descomentar para debug
        // log('info', '🔐 Reconnecting with fresh token');
        connectionInfo.url = data.url;
        if (ws) {
          ws.close();
        }
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
          } else if (data.payload.action === 'subscribe_events' || data.payload.action === 'subscribe_market_events') {
            if (!sub.eventSubIds) sub.eventSubIds = new Set();
            sub.eventSubIds.add(data.payload.sub_id || '_default');
          } else if (data.payload.action === 'unsubscribe_events' || data.payload.action === 'unsubscribe_market_events') {
            if (sub.eventSubIds) sub.eventSubIds.delete(data.payload.sub_id || '_default');
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

// Periodic dead-port cleanup: probe each port with a no-op message.
// If postMessage throws, the tab crashed/closed without sending disconnect.
setInterval(function pruneDeadPorts() {
  ports.forEach(function(port) {
    try {
      port.postMessage({ type: 'ping' });
    } catch (e) {
      ports.delete(port);
      subscriptions.delete(port);
    }
  });
}, 30000);

self.onconnect = function(e) {
  const port = e.ports[0];

  ports.add(port);
  subscriptions.set(port, {
    lists: new Set(),
    subscribedNews: false,
    subscribedSEC: false,
    eventSubIds: new Set(),
    connectionId: null,
  });

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




