/**
 * WebSocket Server for Real-Time Stock Data
 *
 * NEW: Soporte para Snapshot + Deltas
 * - Envía snapshot inicial al conectar
 * - Consume stream:ranking:deltas
 * - Broadcast deltas incrementales a clientes
 * - Manejo de sequence numbers
 */

const WebSocket = require("ws");
const http = require("http");
const Redis = require("ioredis");
const pino = require("pino");
const { v4: uuidv4 } = require("uuid");

// Logger
const logger = pino({
  level: process.env.LOG_LEVEL || "info",
});

// Configuración
const PORT = parseInt(process.env.WS_PORT || "9000", 10);
const REDIS_HOST = process.env.REDIS_HOST || "redis";
const REDIS_PORT = parseInt(process.env.REDIS_PORT || "6379", 10);

// Conexión a Redis (lectura de streams)
const redis = new Redis({
  host: REDIS_HOST,
  port: REDIS_PORT,
  retryStrategy: (times) => {
    const delay = Math.min(times * 50, 2000);
    logger.warn({ times, delay }, "Redis retry");
    return delay;
  },
  maxRetriesPerRequest: null,
});

// Cliente Redis adicional para comandos normales (XADD, GET, etc.)
const redisCommands = new Redis({
  host: REDIS_HOST,
  port: REDIS_PORT,
  retryStrategy: (times) => Math.min(times * 50, 2000),
});

redis.on("connect", () => {
  logger.info("📡 Connected to Redis");
});

redis.on("error", (err) => {
  logger.error({ err }, "Redis error");
});

// Gestión de conexiones
// connectionId -> { ws, subscriptions: Set<string>, sequence_numbers: Map<string, number> }
const connections = new Map();

// Últimos snapshots por lista (para nuevas conexiones)
// list_name -> { sequence, rows, timestamp }
const lastSnapshots = new Map();

// =============================================
// SNAPSHOT & DELTAS - CORE FUNCTIONS
// =============================================

/**
 * Obtiene snapshot inicial desde Redis para una lista
 */
async function getInitialSnapshot(listName) {
  try {
    // Intentar obtener del cache en memoria primero
    if (lastSnapshots.has(listName)) {
      const cached = lastSnapshots.get(listName);
      const age = Date.now() - new Date(cached.timestamp).getTime();

      // Si el snapshot es reciente (< 1 minuto), usarlo
      if (age < 60000) {
        logger.info({ listName, age_ms: age }, "Using cached snapshot");
        return cached;
      }
    }

    // Obtener desde Redis key (guardado por scanner)
    const key = `scanner:category:${listName}`;
    const data = await redisCommands.get(key);

    if (!data) {
      logger.warn({ listName }, "No snapshot found in Redis");
      return null;
    }

    const rows = JSON.parse(data);

    // Obtener sequence number
    const sequenceKey = `scanner:sequence:${listName}`;
    const sequence = await redisCommands.get(sequenceKey);

    const snapshot = {
      type: "snapshot",
      list: listName,
      sequence: parseInt(sequence || "0", 10),
      rows,
      timestamp: new Date().toISOString(),
      count: rows.length,
    };

    // Guardar en cache
    lastSnapshots.set(listName, snapshot);

    logger.info(
      { listName, sequence: snapshot.sequence, count: rows.length },
      "📸 Retrieved snapshot from Redis"
    );

    return snapshot;
  } catch (err) {
    logger.error({ err, listName }, "Error getting initial snapshot");
    return null;
  }
}

/**
 * Envía snapshot inicial a un cliente
 */
async function sendInitialSnapshot(connectionId, listName) {
  const snapshot = await getInitialSnapshot(listName);

  if (!snapshot) {
    sendMessage(connectionId, {
      type: "error",
      message: `No snapshot available for list: ${listName}`,
      list: listName,
    });
    return;
  }

  // Actualizar sequence number del cliente
  const conn = connections.get(connectionId);
  if (conn) {
    conn.sequence_numbers.set(listName, snapshot.sequence);
  }

  // Enviar snapshot
  sendMessage(connectionId, snapshot);

  logger.info(
    {
      connectionId,
      listName,
      sequence: snapshot.sequence,
      count: snapshot.count,
    },
    "📸 Sent initial snapshot to client"
  );
}

/**
 * Procesa mensaje delta del stream
 */
function processDeltaMessage(message) {
  try {
    const type = message.type;
    const list = message.list;
    const sequence = parseInt(message.sequence || "0", 10);

    if (type === "snapshot") {
      // Actualizar cache de snapshots
      const rows = JSON.parse(message.rows || "[]");
      const snapshot = {
        type: "snapshot",
        list,
        sequence,
        rows,
        timestamp: message.timestamp,
        count: parseInt(message.count || "0", 10),
      };

      lastSnapshots.set(list, snapshot);

      logger.info(
        { list, sequence, count: snapshot.count },
        "📸 Cached new snapshot"
      );

      // Broadcast snapshot a todos los clientes suscritos
      broadcastToListSubscribers(list, snapshot);
    } else if (type === "delta") {
      // Parsear deltas
      const deltas = JSON.parse(message.deltas || "[]");

      const deltaMessage = {
        type: "delta",
        list,
        sequence,
        deltas,
        timestamp: message.timestamp,
        change_count: parseInt(message.change_count || "0", 10),
      };

      logger.info(
        { list, sequence, changes: deltaMessage.change_count },
        "🔄 Broadcasting delta"
      );

      // Broadcast delta a todos los clientes suscritos
      broadcastToListSubscribers(list, deltaMessage);
    }
  } catch (err) {
    logger.error({ err, message }, "Error processing delta message");
  }
}

/**
 * Broadcast a clientes suscritos a una lista específica
 */
function broadcastToListSubscribers(listName, message) {
  let sentCount = 0;
  const disconnected = [];

  for (const [connectionId, conn] of connections.entries()) {
    // Verificar si está suscrito a esta lista
    if (!conn.subscriptions.has(listName)) continue;

    // Verificar sequence number (detectar gaps)
    if (message.type === "delta" || message.type === "snapshot") {
      const clientSeq = conn.sequence_numbers.get(listName) || 0;
      const messageSeq = message.sequence;

      // Si hay gap, enviar snapshot completo
      if (messageSeq > clientSeq + 1) {
        logger.warn(
          { connectionId, listName, clientSeq, messageSeq },
          "⚠️ Sequence gap detected, sending snapshot"
        );

        // Enviar snapshot en lugar de delta
        sendInitialSnapshot(connectionId, listName).catch((err) => {
          logger.error(
            { err, connectionId, listName },
            "Error sending snapshot"
          );
        });
        continue;
      }

      // Actualizar sequence number del cliente
      conn.sequence_numbers.set(listName, messageSeq);
    }

    // Enviar mensaje
    if (conn.ws.readyState === WebSocket.OPEN) {
      try {
        conn.ws.send(JSON.stringify(message));
        sentCount++;
      } catch (err) {
        logger.error({ connectionId, err }, "Error sending message");
        disconnected.push(connectionId);
      }
    } else {
      disconnected.push(connectionId);
    }
  }

  // Limpiar conexiones desconectadas
  disconnected.forEach((id) => connections.delete(id));

  if (sentCount > 0) {
    logger.debug(
      { listName, sentCount, type: message.type, sequence: message.sequence },
      "Broadcasted to subscribers"
    );
  }
}

// =============================================
// LEGACY FUNCTIONS (Aggregates & RVOL)
// =============================================

/**
 * Transformar datos de Redis a formato Polygon
 */
function transformToPolygonFormat(data) {
  return {
    o: parseFloat(data.open || 0),
    h: parseFloat(data.high || 0),
    l: parseFloat(data.low || 0),
    c: parseFloat(data.close || 0),
    v: parseInt(data.volume || 0, 10),
    vw: parseFloat(data.vwap || 0),
    av: parseInt(data.volume_accumulated || 0, 10),
    op: parseFloat(data.open || 0),
    ...(data.rvol ? { rvol: parseFloat(data.rvol) } : {}),
  };
}

/**
 * Enviar mensaje a conexión
 */
function sendMessage(connectionId, message) {
  const conn = connections.get(connectionId);
  if (!conn || conn.ws.readyState !== WebSocket.OPEN) return false;

  try {
    const json = JSON.stringify(message);
    conn.ws.send(json);
    return true;
  } catch (err) {
    logger.error({ connectionId, err }, "Error sending message");
    return false;
  }
}

/**
 * Publicar tickers a Polygon WS para suscripción/desuscripción
 */
async function publishTickersToPolygonWS(symbols, action) {
  try {
    const streamName = "polygon_ws:subscriptions";
    for (const symbol of symbols) {
      await redisCommands.xadd(
        streamName,
        "*",
        "symbol",
        symbol.toUpperCase(),
        "action",
        action,
        "timestamp",
        new Date().toISOString()
      );
    }
    logger.info(
      { symbols, action, count: symbols.length },
      "Published tickers to Polygon WS"
    );
  } catch (err) {
    logger.error({ err, symbols, action }, "Error publishing to Polygon WS");
  }
}

/**
 * Broadcast a suscriptores de un símbolo (legacy)
 */
function broadcastToSubscribers(symbol, message) {
  let sentCount = 0;
  const disconnected = [];

  for (const [connectionId, conn] of connections.entries()) {
    if (conn.subscriptions.has("*") || conn.subscriptions.has(symbol)) {
      if (sendMessage(connectionId, message)) {
        sentCount++;
      } else {
        disconnected.push(connectionId);
      }
    }
  }

  disconnected.forEach((id) => connections.delete(id));
  return sentCount;
}

// =============================================
// REDIS STREAMS PROCESSING
// =============================================

/**
 * Procesa stream de ranking deltas
 * MEJORADO: Usa consumer groups + BLOCK reducido para baja latencia
 */
async function processRankingDeltasStream() {
  const streamName = "stream:ranking:deltas";
  const consumerGroup = "websocket_server_deltas";
  const consumerName = "ws_server_1";

  logger.info({ streamName }, "🔄 Starting ranking deltas stream consumer");

  // Crear consumer group si no existe
  try {
    await redisCommands.xgroup(
      "CREATE",
      streamName,
      consumerGroup,
      "$",
      "MKSTREAM"
    );
    logger.info({ streamName, consumerGroup }, "Created consumer group");
  } catch (err) {
    // Ignorar error si el grupo ya existe
    logger.debug({ err: err.message }, "Consumer group already exists");
  }

  while (true) {
    try {
      // MEJORADO: BLOCK 100ms (en lugar de 5000ms) para latencia mínima
      const results = await redis.xreadgroup(
        "GROUP",
        consumerGroup,
        consumerName,
        "BLOCK",
        100, // ← CAMBIADO: 100ms en lugar de 5000ms
        "COUNT",
        50,
        "STREAMS",
        streamName,
        ">" // Leer solo mensajes nuevos no entregados al grupo
      );

      if (results && results.length > 0) {
        const messageIds = [];

        for (const [stream, messages] of results) {
          for (const [messageId, fields] of messages) {
            const message = {};
            for (let i = 0; i < fields.length; i += 2) {
              message[fields[i]] = fields[i + 1];
            }

            // Procesar mensaje delta/snapshot
            processDeltaMessage(message);

            // Guardar ID para ACK
            messageIds.push(messageId);
          }
        }

        // ACK todos los mensajes procesados
        if (messageIds.length > 0) {
          try {
            await redisCommands.xack(streamName, consumerGroup, ...messageIds);
          } catch (err) {
            logger.error({ err }, "Error acknowledging messages");
          }
        }
      }

      // Pequeña pausa para no saturar CPU
      await new Promise((resolve) => setTimeout(resolve, 10));
    } catch (err) {
      logger.error({ err, streamName }, "Error in ranking deltas stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Procesa stream de aggregates (legacy - precio/volumen)
 * MEJORADO: Usa consumer groups + BLOCK reducido para latencia mínima
 */
async function processAggregatesStream() {
  const streamName = "stream:realtime:aggregates";
  const consumerGroup = "websocket_server_aggregates";
  const consumerName = "ws_server_1";

  logger.info({ streamName }, "Starting aggregates stream consumer");

  // Crear consumer group si no existe
  try {
    await redisCommands.xgroup(
      "CREATE",
      streamName,
      consumerGroup,
      "$",
      "MKSTREAM"
    );
    logger.info({ streamName, consumerGroup }, "Created consumer group");
  } catch (err) {
    logger.debug({ err: err.message }, "Consumer group already exists");
  }

  while (true) {
    try {
      // MEJORADO: BLOCK 100ms para latencia casi en tiempo real
      const results = await redis.xreadgroup(
        "GROUP",
        consumerGroup,
        consumerName,
        "BLOCK",
        100, // ← CAMBIADO: 100ms en lugar de 5000ms
        "COUNT",
        100, // Procesar hasta 100 mensajes por batch
        "STREAMS",
        streamName,
        ">"
      );

      if (results && results.length > 0) {
        const messageIds = [];

        for (const [stream, messages] of results) {
          for (const [messageId, fields] of messages) {
            const message = {};
            for (let i = 0; i < fields.length; i += 2) {
              message[fields[i]] = fields[i + 1];
            }

            const { symbol, ...data } = message;

            if (symbol) {
              const aggregateData = transformToPolygonFormat(data);
              const outMessage = {
                type: "aggregate",
                symbol: symbol.toUpperCase(),
                data: aggregateData,
                timestamp: new Date().toISOString(),
              };

              const sent = broadcastToSubscribers(symbol, outMessage);
              if (sent > 0) {
                logger.debug({ symbol, sent }, "Broadcasted aggregate");
              }
            }

            messageIds.push(messageId);
          }
        }

        // ACK mensajes procesados
        if (messageIds.length > 0) {
          try {
            await redisCommands.xack(streamName, consumerGroup, ...messageIds);
          } catch (err) {
            logger.error({ err }, "Error acknowledging aggregate messages");
          }
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 10));
    } catch (err) {
      logger.error({ err, streamName }, "Error in aggregates stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Procesa stream de RVOL (legacy)
 * MEJORADO: Usa consumer groups + BLOCK reducido para latencia mínima
 */
async function processRvolStream() {
  const streamName = "stream:analytics:rvol";
  const consumerGroup = "websocket_server_rvol";
  const consumerName = "ws_server_1";

  logger.info({ streamName }, "Starting RVOL stream consumer");

  // Crear consumer group si no existe
  try {
    await redisCommands.xgroup(
      "CREATE",
      streamName,
      consumerGroup,
      "$",
      "MKSTREAM"
    );
    logger.info({ streamName, consumerGroup }, "Created consumer group");
  } catch (err) {
    logger.debug({ err: err.message }, "Consumer group already exists");
  }

  while (true) {
    try {
      // MEJORADO: BLOCK 100ms para latencia casi en tiempo real
      const results = await redis.xreadgroup(
        "GROUP",
        consumerGroup,
        consumerName,
        "BLOCK",
        100, // ← CAMBIADO: 100ms en lugar de 5000ms
        "COUNT",
        100,
        "STREAMS",
        streamName,
        ">"
      );

      if (results && results.length > 0) {
        const messageIds = [];

        for (const [stream, messages] of results) {
          for (const [messageId, fields] of messages) {
            const message = {};
            for (let i = 0; i < fields.length; i += 2) {
              message[fields[i]] = fields[i + 1];
            }

            const { symbol, rvol, slot_number } = message;

            if (symbol && rvol) {
              const outMessage = {
                type: "rvol",
                symbol: symbol.toUpperCase(),
                data: {
                  rvol: parseFloat(rvol),
                  slot: slot_number ? parseInt(slot_number, 10) : null,
                },
                timestamp: new Date().toISOString(),
              };

              const sent = broadcastToSubscribers(symbol, outMessage);
              if (sent > 0) {
                logger.debug({ symbol, rvol, sent }, "Broadcasted RVOL");
              }
            }

            messageIds.push(messageId);
          }
        }

        // ACK mensajes procesados
        if (messageIds.length > 0) {
          try {
            await redisCommands.xack(streamName, consumerGroup, ...messageIds);
          } catch (err) {
            logger.error({ err }, "Error acknowledging RVOL messages");
          }
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 10));
    } catch (err) {
      logger.error({ err, streamName }, "Error in RVOL stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

// =============================================
// WEBSOCKET SERVER
// =============================================

// Crear servidor HTTP
const server = http.createServer();

// Crear servidor WebSocket
const wss = new WebSocket.Server({
  server,
  path: "/ws/scanner",
});

// Manejar conexiones WebSocket
wss.on("connection", (ws, req) => {
  const connectionId = uuidv4();
  ws.connectionId = connectionId;

  connections.set(connectionId, {
    ws,
    subscriptions: new Set(),
    sequence_numbers: new Map(), // NEW: Tracking de sequence numbers por lista
  });

  logger.info(
    { connectionId, ip: req.socket.remoteAddress },
    "✅ Client connected"
  );

  // Enviar mensaje de bienvenida
  sendMessage(connectionId, {
    type: "connected",
    connection_id: connectionId,
    message: "Connected to Tradeul Scanner (Snapshot + Deltas)",
    timestamp: new Date().toISOString(),
  });

  // Manejar mensajes del cliente
  ws.on("message", async (message) => {
    try {
      const json = Buffer.from(message).toString("utf-8");
      const data = JSON.parse(json);
      const conn = connections.get(connectionId);

      if (!conn) return;

      const { action } = data;

      // =============================================
      // NEW: Subscribe to list (recibe snapshot inicial)
      // =============================================
      if (action === "subscribe_list") {
        const listName = data.list;

        if (!listName) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'list' parameter",
          });
          return;
        }

        // Añadir a suscripciones
        conn.subscriptions.add(listName);

        logger.info({ connectionId, listName }, "📋 Client subscribed to list");

        // Enviar snapshot inicial
        await sendInitialSnapshot(connectionId, listName);

        sendMessage(connectionId, {
          type: "subscribed_list",
          list: listName,
          timestamp: new Date().toISOString(),
        });
      }

      // =============================================
      // NEW: Unsubscribe from list
      // =============================================
      else if (action === "unsubscribe_list") {
        const listName = data.list;

        conn.subscriptions.delete(listName);
        conn.sequence_numbers.delete(listName);

        logger.info(
          { connectionId, listName },
          "📋 Client unsubscribed from list"
        );

        sendMessage(connectionId, {
          type: "unsubscribed_list",
          list: listName,
          timestamp: new Date().toISOString(),
        });
      }

      // =============================================
      // NEW: Request resync (pide snapshot completo)
      // =============================================
      else if (action === "resync") {
        const listName = data.list;

        logger.info({ connectionId, listName }, "🔄 Client requested resync");

        await sendInitialSnapshot(connectionId, listName);
      }

      // =============================================
      // LEGACY: Subscribe to symbol (para aggregates)
      // =============================================
      else if (action === "subscribe") {
        const symbols = data.symbols || [];
        symbols.forEach((symbol) => conn.subscriptions.add(symbol));

        logger.info(
          { connectionId, symbols, total: conn.subscriptions.size },
          "Client subscribed to symbols"
        );

        if (symbols.length > 0) {
          publishTickersToPolygonWS(symbols, "subscribe").catch((err) => {
            logger.error({ err, symbols }, "Failed to publish to Polygon WS");
          });
        }

        sendMessage(connectionId, {
          type: "subscribed",
          symbols,
          timestamp: new Date().toISOString(),
        });
      }

      // =============================================
      // LEGACY: Unsubscribe from symbol
      // =============================================
      else if (action === "unsubscribe") {
        const symbols = data.symbols || [];
        symbols.forEach((symbol) => conn.subscriptions.delete(symbol));

        logger.info(
          { connectionId, symbols, total: conn.subscriptions.size },
          "Client unsubscribed from symbols"
        );

        if (symbols.length > 0) {
          publishTickersToPolygonWS(symbols, "unsubscribe").catch((err) => {
            logger.error({ err, symbols }, "Failed to publish to Polygon WS");
          });
        }

        sendMessage(connectionId, {
          type: "unsubscribed",
          symbols,
          timestamp: new Date().toISOString(),
        });
      }

      // =============================================
      // LEGACY: Subscribe all (deprecated)
      // =============================================
      else if (action === "subscribe_all") {
        conn.subscriptions.add("*");
        logger.info({ connectionId }, "Client subscribed to all");

        sendMessage(connectionId, {
          type: "subscribed_all",
          timestamp: new Date().toISOString(),
        });
      }

      // Acción desconocida
      else {
        logger.warn({ connectionId, action }, "Unknown action");
        sendMessage(connectionId, {
          type: "error",
          message: `Unknown action: ${action}`,
        });
      }
    } catch (err) {
      logger.error({ connectionId, err }, "Error handling message");
      sendMessage(connectionId, {
        type: "error",
        message: "Invalid message format",
      });
    }
  });

  // Manejar cierre de conexión
  ws.on("close", () => {
    connections.delete(connectionId);
    logger.info({ connectionId }, "❌ Client disconnected");
  });

  // Manejar errores
  ws.on("error", (err) => {
    logger.error({ connectionId, err }, "WebSocket error");
    connections.delete(connectionId);
  });
});

// =============================================
// STARTUP
// =============================================

// Iniciar procesadores de streams
processRankingDeltasStream().catch((err) => {
  logger.fatal({ err }, "Ranking deltas stream processor crashed");
  process.exit(1);
});

processAggregatesStream().catch((err) => {
  logger.fatal({ err }, "Aggregates stream processor crashed");
  process.exit(1);
});

processRvolStream().catch((err) => {
  logger.fatal({ err }, "RVOL stream processor crashed");
  process.exit(1);
});

// Iniciar servidor
server.listen(PORT, () => {
  logger.info({ port: PORT }, "🚀 WebSocket Server started");
  logger.info("Features enabled:");
  logger.info("  - Snapshot + Deltas (stream:ranking:deltas)");
  logger.info("  - Sequence number tracking");
  logger.info("  - Auto-resync on gaps");
  logger.info("  - Legacy aggregates support");
});

// Graceful shutdown
process.on("SIGTERM", () => {
  logger.info("SIGTERM received, shutting down gracefully");
  server.close(() => {
    redis.disconnect();
    redisCommands.disconnect();
    logger.info("Server shut down complete");
    process.exit(0);
  });
});

process.on("SIGINT", () => {
  logger.info("SIGINT received, shutting down gracefully");
  server.close(() => {
    redis.disconnect();
    redisCommands.disconnect();
    logger.info("Server shut down complete");
    process.exit(0);
  });
});
