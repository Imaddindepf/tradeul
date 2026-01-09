/**
 * Cache Cleaner Module
 * 
 * Escucha eventos de cambio de día y limpia caches en memoria
 * para asegurar que no se mantengan datos del día anterior.
 * 
 * También escucha eventos de cambio de sesión del mercado
 * para notificar al frontend en tiempo real.
 */

const logger = require("pino")();
const WebSocket = require("ws");

// Referencia a las conexiones (se setea desde index.js)
let connectionsRef = null;

/**
 * Setear referencia a las conexiones WebSocket
 * @param {Map} connections - Mapa de conexiones
 */
function setConnectionsRef(connections) {
  connectionsRef = connections;
}

/**
 * Broadcast un mensaje a todos los clientes conectados
 * @param {Object} message - Mensaje a enviar
 */
function broadcastToAll(message) {
  if (!connectionsRef) return 0;
  
  let sentCount = 0;
  const messageStr = JSON.stringify(message);
  
  connectionsRef.forEach((conn, connectionId) => {
    if (conn.ws.readyState === WebSocket.OPEN) {
      try {
        conn.ws.send(messageStr);
        sentCount++;
      } catch (err) {
        logger.error({ connectionId, err }, "Error sending broadcast message");
      }
    }
  });
  
  return sentCount;
}

/**
 * Suscribirse al canal Redis para eventos de nuevo día
 * @param {Object} redisSubscriber - Cliente Redis para suscripción
 * @param {Map} lastSnapshots - Cache de snapshots a limpiar
 */
async function subscribeToNewDayEvents(redisSubscriber, lastSnapshots) {
  try {
    // Suscribirse al canal de eventos de nuevo día
    await redisSubscriber.subscribe("trading:new_day", (message, channel) => {
      try {
        // El mensaje puede venir como string o null en el primer callback
        if (!message) {
          logger.debug({ channel }, "Subscribed to channel (no message yet)");
          return;
        }
        
        const event = JSON.parse(message);
        
        if (event.event === "new_trading_day" && event.action === "clear_caches") {
          logger.info(
            {
              date: event.date,
              previousCacheSize: lastSnapshots.size,
            },
            "🔄 New trading day detected - clearing all caches"
          );
          
          // Limpiar cache de snapshots
          const clearedCount = lastSnapshots.size;
          lastSnapshots.clear();
          
          logger.info(
            {
              date: event.date,
              caches_cleared: clearedCount,
            },
            "✅ Cache cleared for new trading day"
          );
        }
      } catch (err) {
        logger.error({ err, message }, "Error processing new day event");
      }
    });
    
    logger.info(
      { channel: "trading:new_day" },
      "📡 Subscribed to new trading day events"
    );
  } catch (err) {
    logger.error({ err }, "Failed to subscribe to new day events");
  }
}

/**
 * Suscribirse al canal Redis para eventos de cambio de sesión del mercado
 * @param {Object} redisSubscriber - Cliente Redis para suscripción
 */
async function subscribeToSessionChangeEvents(redisSubscriber) {
  try {
    // IMPORTANTE: El canal debe coincidir con el que usa EventBus en Python
    // EventType.SESSION_CHANGED = "session:changed" → canal = "events:session:changed"
    await redisSubscriber.subscribe("events:session:changed", (message, channel) => {
      try {
        if (!message) {
          logger.debug({ channel }, "Subscribed to session change channel");
          return;
        }
        
        const event = JSON.parse(message);
        
        logger.info(
          {
            from: event.from_session,
            to: event.to_session,
            trading_date: event.trading_date,
            is_new_day: event.is_new_day,
          },
          "📊 Market session changed"
        );
        
        // Broadcast a todos los clientes conectados
        const wsMessage = {
          type: "market_session_change",
          data: {
            from_session: event.from_session,
            to_session: event.to_session,
            current_session: event.to_session,
            trading_date: event.trading_date,
            is_new_day: event.is_new_day,
            timestamp: event.timestamp || new Date().toISOString(),
          },
          timestamp: new Date().toISOString(),
        };
        
        const sentCount = broadcastToAll(wsMessage);
        
        logger.info(
          { sentCount, toSession: event.to_session },
          "📡 Broadcasted session change to clients"
        );
        
      } catch (err) {
        logger.error({ err, message }, "Error processing session change event");
      }
    });
    
    logger.info(
      { channel: "events:session:changed" },
      "📡 Subscribed to market session change events"
    );
  } catch (err) {
    logger.error({ err }, "Failed to subscribe to session change events");
  }
}

/**
 * Suscribirse al canal Redis para notificaciones de Morning News Call
 * @param {Object} redisSubscriber - Cliente Redis para suscripción
 */
async function subscribeToMorningNewsEvents(redisSubscriber) {
  try {
    await redisSubscriber.subscribe("notifications:morning_news", (message, channel) => {
      try {
        if (!message) {
          logger.debug({ channel }, "Subscribed to morning news channel");
          return;
        }
        
        const event = JSON.parse(message);
        
        logger.info(
          {
            date: event.date,
            title: event.title,
            manual: event.manual || false,
          },
          "📰 Morning News Call received"
        );
        
        // Broadcast a todos los clientes conectados
        const wsMessage = {
          type: "morning_news_call",
          data: {
            date: event.date,
            title: event.title,
            preview: event.preview,
            generated_at: event.generated_at,
            manual: event.manual || false,
          },
          timestamp: new Date().toISOString(),
        };
        
        const sentCount = broadcastToAll(wsMessage);
        
        logger.info(
          { sentCount, date: event.date },
          "📡 Broadcasted Morning News Call to clients"
        );
        
      } catch (err) {
        logger.error({ err, message }, "Error processing morning news event");
      }
    });
    
    logger.info(
      { channel: "notifications:morning_news" },
      "📡 Subscribed to Morning News Call events"
    );
  } catch (err) {
    logger.error({ err }, "Failed to subscribe to morning news events");
  }
}

/**
 * Endpoint HTTP para limpiar cache manualmente (fallback)
 * @param {Map} lastSnapshots - Cache de snapshots a limpiar
 * @returns {Function} Express middleware
 */
function createClearCacheEndpoint(lastSnapshots) {
  return (req, res) => {
    try {
      const { reason, date } = req.body || {};
      
      const clearedCount = lastSnapshots.size;
      lastSnapshots.clear();
      
      logger.info(
        {
          reason: reason || "manual",
          date: date || "unknown",
          caches_cleared: clearedCount,
        },
        "✅ Cache cleared via HTTP endpoint"
      );
      
      res.status(200).json({
        success: true,
        caches_cleared: clearedCount,
        reason: reason || "manual",
        date: date || new Date().toISOString(),
      });
    } catch (err) {
      logger.error({ err }, "Error clearing cache via HTTP");
      res.status(500).json({
        success: false,
        error: err.message,
      });
    }
  };
}

module.exports = {
  subscribeToNewDayEvents,
  subscribeToSessionChangeEvents,
  subscribeToMorningNewsEvents,
  setConnectionsRef,
  createClearCacheEndpoint,
};


