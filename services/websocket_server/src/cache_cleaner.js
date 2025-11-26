/**
 * Cache Cleaner Module
 * 
 * Escucha eventos de cambio de día y limpia caches en memoria
 * para asegurar que no se mantengan datos del día anterior.
 */

const logger = require("pino")();

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
  createClearCacheEndpoint,
};


