/**
 * WebSocket Server for Real-Time Stock Data + SEC Filings
 *
 * ARQUITECTURA HÍBRIDA:
 * 1. Rankings: Snapshot + Deltas (cada 10s desde Scanner)
 * 2. Precio/Volumen: Aggregates en tiempo real (cada 1s desde Polygon WS)
 * 3. SEC Filings: Stream en tiempo real desde SEC Stream API
 *
 * FLUJO:
 * - Cliente se suscribe a lista (ej: "GAPPERS_UP")
 * - Recibe snapshot inicial
 * - Recibe deltas de cambios en ranking
 * - Recibe aggregates de precio/volumen en tiempo real
 * - Recibe SEC filings en tiempo real (si está suscrito a "SEC_FILINGS")
 */

const WebSocket = require("ws");
const http = require("http");
const Redis = require("ioredis");
const pino = require("pino");
const { v4: uuidv4 } = require("uuid");
const { subscribeToNewDayEvents } = require("./cache_cleaner");

// Logger
const logger = pino({
  level: process.env.LOG_LEVEL || "info",
});

// Configuración
const PORT = parseInt(process.env.WS_PORT || "9000", 10);
const REDIS_HOST = process.env.REDIS_HOST || "redis";
const REDIS_PORT = parseInt(process.env.REDIS_PORT || "6379", 10);
const REDIS_PASSWORD = process.env.REDIS_PASSWORD;

// Configuración base de Redis
const redisConfig = {
  host: REDIS_HOST,
  port: REDIS_PORT,
  ...(REDIS_PASSWORD && { password: REDIS_PASSWORD }),
};

// Conexión a Redis (lectura de streams)
const redis = new Redis({
  ...redisConfig,
  retryStrategy: (times) => {
    const delay = Math.min(times * 50, 2000);
    logger.warn({ times, delay }, "Redis retry");
    return delay;
  },
  maxRetriesPerRequest: null,
});

// Cliente Redis adicional para comandos normales
const redisCommands = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
});

// Cliente Redis para Pub/Sub (escuchar eventos de nuevo día)
const redisSubscriber = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
});

redis.on("connect", () => {
  logger.info("📡 Connected to Redis");
});

redis.on("error", (err) => {
  logger.error({ err }, "Redis error");
});

// =============================================
// DATA STRUCTURES (OPTIMIZADAS)
// =============================================

// Conexiones: connectionId -> { ws, subscriptions: Set<listName>, sequence_numbers: Map<listName, number> }
const connections = new Map();

// Índice inverso para broadcasting eficiente: listName -> Set<connectionId>
const listSubscribers = new Map();

// Clientes suscritos a SEC Filings: Set<connectionId>
const secFilingsSubscribers = new Set();

// Clientes suscritos a Benzinga News: Set<connectionId>
const benzingaNewsSubscribers = new Set();

// Mapeo symbol → lists (para broadcast de aggregates)
// "TSLA" -> Set(["GAPPERS_UP", "MOMENTUM_UP"])
const symbolToLists = new Map();

// Últimos snapshots por lista (cache): listName -> { sequence, rows, timestamp }
const lastSnapshots = new Map();

// =============================================
// AGGREGATE SAMPLING & THROTTLING
// =============================================

// Sampling por símbolo: symbol -> { lastData, lastSentTime, count }
const aggregateSamplers = new Map();

// Configuración de throttling
const AGGREGATE_THROTTLE_MS = 1000; // Enviar máximo cada 1000ms (1s) por símbolo - coincide con Polygon
const AGGREGATE_BUFFER_FLUSH_INTERVAL = 500; // Flush buffer cada 500ms
const MAX_BUFFER_SIZE = 10000; // Máximo de aggregates en buffer (backpressure)

// Buffer de aggregates pendientes: Map<symbol, latestAggregate>
const aggregateBuffer = new Map();

// Estadísticas de performance
const aggregateStats = {
  received: 0,
  sent: 0,
  dropped: 0,
  lastReset: Date.now(),
};

/**
 * Agregar aggregate al buffer
 * CRÍTICO: SIEMPRE mantener el último valor, el throttle se aplica en flush
 */
function bufferAggregate(symbol, data) {
  // Backpressure: si el buffer está muy grande, dropeamos mensajes
  if (aggregateBuffer.size >= MAX_BUFFER_SIZE) {
    aggregateStats.dropped++;
    return false;
  }

  aggregateStats.received++;

  // Inicializar sampler si no existe
  if (!aggregateSamplers.has(symbol)) {
    aggregateSamplers.set(symbol, { lastSentTime: 0, count: 0 });
  }

  const sampler = aggregateSamplers.get(symbol);
  sampler.count++;

  // SIEMPRE actualizar el buffer con el último valor
  // El flush decidirá si enviarlo basado en throttle
  aggregateBuffer.set(symbol, data);

  return true;
}

/**
 * Flush del buffer de aggregates (batch broadcast)
 * Envía solo símbolos que cumplan con throttle, pero siempre con el último valor
 */
function flushAggregateBuffer() {
  if (aggregateBuffer.size === 0) return;

  const now = Date.now();
  const toSend = new Map();

  // Filtrar solo símbolos que cumplan con el throttle
  aggregateBuffer.forEach((data, symbol) => {
    const sampler = aggregateSamplers.get(symbol);
    if (!sampler) return;

    // Verificar si pasó el tiempo de throttle
    if (now - sampler.lastSentTime >= AGGREGATE_THROTTLE_MS) {
      toSend.set(symbol, data);
      sampler.lastSentTime = now;
    }
  });

  // Limpiar buffer después de procesar
  // Mantener símbolos que no se enviaron (aún en throttle)
  toSend.forEach((_, symbol) => {
    aggregateBuffer.delete(symbol);
  });

  if (toSend.size === 0) return;

  // Agrupar por lista para batch broadcast
  const messagesByList = new Map(); // listName -> [messages]

  toSend.forEach((data, symbol) => {
    const lists = symbolToLists.get(symbol);
    if (!lists || lists.size === 0) return;

    const aggregateData = transformToPolygonFormat(data);
    const message = {
      type: "aggregate",
      symbol: symbol,
      data: aggregateData,
      timestamp: new Date().toISOString(),
    };

    // Agrupar por lista
    lists.forEach((listName) => {
      if (!messagesByList.has(listName)) {
        messagesByList.set(listName, []);
      }
      messagesByList.get(listName).push(message);
    });
  });

  // Broadcast batched por lista
  let totalSent = 0;
  messagesByList.forEach((messages, listName) => {
    const subscribers = listSubscribers.get(listName);
    if (!subscribers || subscribers.size === 0) return;

    subscribers.forEach((connectionId) => {
      const conn = connections.get(connectionId);
      if (conn && conn.ws.readyState === WebSocket.OPEN) {
        messages.forEach((message) => {
          try {
            conn.ws.send(JSON.stringify(message));
            totalSent++;
          } catch (err) {
            logger.error({ connectionId, err }, "Error sending aggregate");
          }
        });
      }
    });
  });

  aggregateStats.sent += totalSent;

  if (totalSent > 0) {
    logger.debug(
      {
        buffered: aggregateBuffer.size,
        sent: totalSent,
        symbols: toSend.size,
        lists: messagesByList.size,
      },
      "📊 Flushed aggregate buffer"
    );
  }
}

/**
 * Log de estadísticas de aggregates cada minuto
 */
setInterval(() => {
  const elapsed = (Date.now() - aggregateStats.lastReset) / 1000;
  const recvRate = (aggregateStats.received / elapsed).toFixed(0);
  const sentRate = (aggregateStats.sent / elapsed).toFixed(0);
  const dropRate = (aggregateStats.dropped / elapsed).toFixed(0);
  const reduction =
    aggregateStats.received > 0
      ? (
          ((aggregateStats.received - aggregateStats.sent) /
            aggregateStats.received) *
          100
        ).toFixed(1)
      : 0;

  logger.info(
    {
      received: aggregateStats.received,
      sent: aggregateStats.sent,
      dropped: aggregateStats.dropped,
      recvRate: `${recvRate}/s`,
      sentRate: `${sentRate}/s`,
      dropRate: `${dropRate}/s`,
      reduction: `${reduction}%`,
      bufferSize: aggregateBuffer.size,
      samplers: aggregateSamplers.size,
    },
    "📊 Aggregate stats (last 60s)"
  );

  // Reset stats
  aggregateStats.received = 0;
  aggregateStats.sent = 0;
  aggregateStats.dropped = 0;
  aggregateStats.lastReset = Date.now();
}, 60000);

// Iniciar flush periódico del buffer
setInterval(() => {
  flushAggregateBuffer();
}, AGGREGATE_BUFFER_FLUSH_INTERVAL);

// =============================================
// UTILIDADES
// =============================================

/**
 * Parsear fields de Redis stream a objeto
 */
function parseRedisFields(fields) {
  const message = {};
  for (let i = 0; i < fields.length; i += 2) {
    message[fields[i]] = fields[i + 1];
  }
  return message;
}

/**
 * Enviar mensaje a conexión específica
 */
function sendMessage(connectionId, message) {
  const conn = connections.get(connectionId);
  if (!conn || conn.ws.readyState !== WebSocket.OPEN) return false;

  try {
    conn.ws.send(JSON.stringify(message));
    return true;
  } catch (err) {
    logger.error({ connectionId, err }, "Error sending message");
    return false;
  }
}

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
  };
}

// =============================================
// SNAPSHOT & DELTAS MANAGEMENT
// =============================================

/**
 * Obtener snapshot inicial desde Redis
 */
async function getInitialSnapshot(listName) {
  try {
    // Intentar obtener del cache en memoria primero
    if (lastSnapshots.has(listName)) {
      const cached = lastSnapshots.get(listName);
      const age = Date.now() - new Date(cached.timestamp).getTime();

      // Si es reciente (< 1 minuto), usarlo
      if (age < 60000) {
        logger.debug({ listName, age_ms: age }, "Using cached snapshot");
        return cached;
      }
    }

    // Obtener desde Redis
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
    logger.error({ err, listName }, "Error getting snapshot");
    return null;
  }
}

/**
 * Enviar snapshot inicial a cliente
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
    "📸 Sent snapshot to client"
  );
}

/**
 * Actualizar índice symbol → lists cuando llegan deltas
 */
function updateSymbolToListsIndex(listName, deltas) {
  deltas.forEach((delta) => {
    const symbol = delta.symbol;

    if (delta.action === "add") {
      // Agregar symbol a lista
      if (!symbolToLists.has(symbol)) {
        symbolToLists.set(symbol, new Set());
      }
      symbolToLists.get(symbol).add(listName);

      logger.debug(
        { symbol, listName, action: "add" },
        "Updated symbol→lists index"
      );
    } else if (delta.action === "remove") {
      // Remover symbol de lista
      const lists = symbolToLists.get(symbol);
      if (lists) {
        lists.delete(listName);
        // Si no está en ninguna lista, eliminar entrada
        if (lists.size === 0) {
          symbolToLists.delete(symbol);
        }
      }

      logger.debug(
        { symbol, listName, action: "remove" },
        "Updated symbol→lists index"
      );
    }
  });
}

// =============================================
// NOTA: websocket_server NO publica a polygon_ws:subscriptions
// Solo el scanner es dueño de esa verdad (Single Writer Principle)
// websocket_server solo mantiene symbolToLists para routing
// =============================================

/**
 * Procesar mensaje delta/snapshot del stream
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

      // Detectar símbolos añadidos/eliminados vs estado anterior
      const oldSymbols = new Set();
      symbolToLists.forEach((lists, symbol) => {
        if (lists.has(list)) {
          oldSymbols.add(symbol);
        }
      });

      const newSymbols = new Set(rows.map((ticker) => ticker.symbol));
      const addedSymbols = [...newSymbols].filter((s) => !oldSymbols.has(s));
      const removedSymbols = [...oldSymbols].filter((s) => !newSymbols.has(s));

      // Actualizar índice symbol→lists con snapshot completo
      symbolToLists.forEach((lists, symbol) => lists.delete(list));
      rows.forEach((ticker) => {
        const symbol = ticker.symbol;
        if (!symbolToLists.has(symbol)) {
          symbolToLists.set(symbol, new Set());
        }
        symbolToLists.get(symbol).add(list);
      });

      logger.info(
        {
          list,
          sequence,
          count: snapshot.count,
          added: addedSymbols.length,
          removed: removedSymbols.length,
        },
        "📸 Cached snapshot & updated index"
      );

      // Broadcast snapshot
      broadcastToListSubscribers(list, snapshot);
    } else if (type === "delta") {
      // Parsear deltas
      const deltas = JSON.parse(message.deltas || "[]");

      // Detectar símbolos añadidos/eliminados de los deltas
      const addedSymbols = deltas
        .filter((d) => d.action === "add")
        .map((d) => d.symbol);
      const removedSymbols = deltas
        .filter((d) => d.action === "remove")
        .map((d) => d.symbol);

      // Actualizar índice symbol→lists
      updateSymbolToListsIndex(list, deltas);

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

      // Broadcast delta
      broadcastToListSubscribers(list, deltaMessage);
    }
  } catch (err) {
    logger.error({ err, message }, "Error processing delta message");
  }
}

/**
 * Broadcast a clientes suscritos a una lista (OPTIMIZADO)
 */
function broadcastToListSubscribers(listName, message) {
  const subscribers = listSubscribers.get(listName);
  if (!subscribers || subscribers.size === 0) return;

  let sentCount = 0;
  const disconnected = [];

  subscribers.forEach((connectionId) => {
    const conn = connections.get(connectionId);

    if (!conn || conn.ws.readyState !== WebSocket.OPEN) {
      disconnected.push(connectionId);
      return;
    }

    // Verificar sequence gap para deltas/snapshots
    if (message.type === "delta" || message.type === "snapshot") {
      const clientSeq = conn.sequence_numbers.get(listName) || 0;
      const messageSeq = message.sequence;

      // Si hay gap, enviar snapshot completo
      if (messageSeq > clientSeq + 1) {
        logger.warn(
          { connectionId, listName, clientSeq, messageSeq },
          "⚠️ Sequence gap detected, sending snapshot"
        );
        sendInitialSnapshot(connectionId, listName).catch((err) => {
          logger.error(
            { err, connectionId, listName },
            "Error sending snapshot"
          );
        });
        return;
      }

      // Actualizar sequence number del cliente
      conn.sequence_numbers.set(listName, messageSeq);
    }

    // Enviar mensaje
    try {
      conn.ws.send(JSON.stringify(message));
      sentCount++;
    } catch (err) {
      logger.error({ connectionId, err }, "Error sending message");
      disconnected.push(connectionId);
    }
  });

  // Limpiar conexiones desconectadas
  disconnected.forEach((id) => {
    subscribers.delete(id);
    connections.delete(id);
  });

  if (sentCount > 0) {
    logger.debug(
      { listName, sentCount, type: message.type },
      "Broadcasted to subscribers"
    );
  }
}

// =============================================
// SUSCRIPCIÓN DE CLIENTES
// =============================================

/**
 * Suscribir cliente a lista
 */
function subscribeClientToList(connectionId, listName) {
  const conn = connections.get(connectionId);
  if (!conn) return false;

  // Agregar a suscripciones del cliente
  conn.subscriptions.add(listName);

  // Agregar a índice inverso
  if (!listSubscribers.has(listName)) {
    listSubscribers.set(listName, new Set());
  }
  listSubscribers.get(listName).add(connectionId);

  logger.info(
    {
      connectionId,
      listName,
      totalSubscribers: listSubscribers.get(listName).size,
    },
    "📋 Client subscribed to list"
  );

  return true;
}

/**
 * Desuscribir cliente de lista
 */
function unsubscribeClientFromList(connectionId, listName) {
  const conn = connections.get(connectionId);
  if (conn) {
    conn.subscriptions.delete(listName);
    conn.sequence_numbers.delete(listName);
  }

  // Remover de índice inverso
  const subscribers = listSubscribers.get(listName);
  if (subscribers) {
    subscribers.delete(connectionId);
    if (subscribers.size === 0) {
      listSubscribers.delete(listName);
    }
  }

  logger.info({ connectionId, listName }, "📋 Client unsubscribed from list");
}

/**
 * Desuscribir cliente de todas las listas
 */
function unsubscribeClientFromAll(connectionId) {
  const conn = connections.get(connectionId);
  if (!conn) return;

  // Remover de todas las listas
  conn.subscriptions.forEach((listName) => {
    const subscribers = listSubscribers.get(listName);
    if (subscribers) {
      subscribers.delete(connectionId);
      if (subscribers.size === 0) {
        listSubscribers.delete(listName);
      }
    }
  });

  conn.subscriptions.clear();
  conn.sequence_numbers.clear();
}

// =============================================
// REDIS STREAMS PROCESSING
// =============================================

/**
 * Procesar stream de ranking deltas
 */
async function processRankingDeltasStream() {
  const streamName = "stream:ranking:deltas";
  const consumerGroup = "websocket_server_deltas";
  const consumerName = "ws_server_1";

  logger.info({ streamName }, "🔄 Starting ranking deltas stream consumer");

  // Crear consumer group
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

  // INICIALIZACIÓN: Cargar snapshots existentes de todas las listas y publicar símbolos
  logger.info("🔄 Initializing: loading existing rankings from Redis...");
  const listNames = [
    "gappers_up",
    "gappers_down",
    "momentum_up",
    "momentum_down",
    "high_volume",
    "winners",
    "losers",
    "reversals",
    "anomalies",
    "new_highs",
    "new_lows",
  ];

  const initialSymbols = new Set();
  for (const listName of listNames) {
    try {
      const jsonData = await redisCommands.get(`scanner:category:${listName}`);
      if (jsonData) {
        const rows = JSON.parse(jsonData);
        rows.forEach((ticker) => {
          const symbol = ticker.symbol;
          initialSymbols.add(symbol);
          if (!symbolToLists.has(symbol)) {
            symbolToLists.set(symbol, new Set());
          }
          symbolToLists.get(symbol).add(listName);
        });
        logger.debug(
          { listName, count: rows.length },
          "Loaded initial snapshot"
        );
      }
    } catch (err) {
      logger.warn(
        { listName, err: err.message },
        "Failed to load initial snapshot"
      );
    }
  }

  // Solo log de inicialización (el scanner ya publica a Polygon WS)
  if (initialSymbols.size > 0) {
    logger.info(
      { count: initialSymbols.size },
      "✅ Loaded symbolToLists index from Redis (routing only)"
    );
  }

  while (true) {
    try {
      // BLOCK 100ms para baja latencia
      const results = await redis.xreadgroup(
        "GROUP",
        consumerGroup,
        consumerName,
        "BLOCK",
        100,
        "COUNT",
        50,
        "STREAMS",
        streamName,
        ">"
      );

      if (results && results.length > 0) {
        const messageIds = [];

        for (const [stream, messages] of results) {
          for (const [messageId, fields] of messages) {
            const message = parseRedisFields(fields);
            processDeltaMessage(message);
            messageIds.push(messageId);
          }
        }

        // ACK mensajes procesados
        if (messageIds.length > 0) {
          try {
            await redisCommands.xack(streamName, consumerGroup, ...messageIds);
          } catch (err) {
            logger.error({ err }, "Error acknowledging messages");
          }
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 10));
    } catch (err) {
      // Auto-healing: Si el consumer group fue borrado, recrearlo
      if (err.message && err.message.includes('NOGROUP')) {
        logger.warn({ streamName, consumerGroup }, "🔧 Consumer group missing - auto-recreating");
        try {
          await redisCommands.xgroup(
            "CREATE",
            streamName,
            consumerGroup,
            "0",  // Empezar desde el inicio del stream
            "MKSTREAM"
          );
          logger.info({ streamName, consumerGroup }, "✅ Consumer group recreated");
          // Reintentar inmediatamente
          continue;
        } catch (recreateErr) {
          logger.error({ err: recreateErr }, "Failed to recreate consumer group");
        }
      }
      
      logger.error({ err, streamName }, "Error in ranking deltas stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Procesar stream de aggregates (precio/volumen en tiempo real)
 */
async function processAggregatesStream() {
  const streamName = "stream:realtime:aggregates";
  const consumerGroup = "websocket_server_aggregates";
  const consumerName = "ws_server_1";

  logger.info({ streamName }, "📊 Starting aggregates stream consumer");

  // Crear consumer group
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
      // BLOCK 100ms para latencia casi en tiempo real
      const results = await redis.xreadgroup(
        "GROUP",
        consumerGroup,
        consumerName,
        "BLOCK",
        100,
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
            const message = parseRedisFields(fields);
            const { symbol, ...data } = message;

            if (symbol) {
              const symbolUpper = symbol.toUpperCase();

              // Verificar si el símbolo está en alguna lista
              const lists = symbolToLists.get(symbolUpper);

              if (lists && lists.size > 0) {
                // Agregar al buffer con sampling (no broadcast directo)
                bufferAggregate(symbolUpper, data);
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
      // Auto-healing: Si el consumer group fue borrado, recrearlo
      if (err.message && err.message.includes('NOGROUP')) {
        logger.warn({ streamName, consumerGroup }, "🔧 Consumer group missing - auto-recreating");
        try {
          await redisCommands.xgroup(
            "CREATE",
            streamName,
            consumerGroup,
            "0",  // Empezar desde el inicio del stream
            "MKSTREAM"
          );
          logger.info({ streamName, consumerGroup }, "✅ Consumer group recreated");
          // Reintentar inmediatamente
          continue;
        } catch (recreateErr) {
          logger.error({ err: recreateErr }, "Failed to recreate consumer group");
        }
      }
      
      logger.error({ err, streamName }, "Error in aggregates stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Procesador del stream de SEC Filings
 * Lee stream:sec:filings y broadcast a clientes suscritos
 */
async function processSECFilingsStream() {
  const STREAM_NAME = "stream:sec:filings";
  let lastId = "$"; // Leer solo mensajes nuevos

  logger.info("📋 Starting SEC Filings stream processor");

  while (true) {
    try {
      const result = await redis.xread(
        "BLOCK",
        5000,
        "COUNT",
        50,
        "STREAMS",
        STREAM_NAME,
        lastId
      );

      if (!result) continue;

      for (const [_stream, messages] of result) {
        for (const [id, fields] of messages) {
          lastId = id;
          const message = parseRedisFields(fields);

          // El mensaje viene con type="filing" y data=JSON
          if (message.type === "filing" && message.data) {
            try {
              const filingData = JSON.parse(message.data);
              
              // Broadcast a todos los clientes suscritos a SEC Filings
              broadcastSECFiling(filingData);
              
            } catch (parseErr) {
              logger.error({ err: parseErr }, "Error parsing SEC filing data");
            }
          }
        }
      }
    } catch (err) {
      logger.error({ err }, "Error reading SEC filings stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Broadcast de SEC filing a clientes suscritos
 */
function broadcastSECFiling(filingData) {
  if (secFilingsSubscribers.size === 0) return;

  const message = {
    type: "sec_filing",
    filing: filingData,
    timestamp: new Date().toISOString()
  };

  const messageStr = JSON.stringify(message);
  let sentCount = 0;
  const disconnected = [];

  secFilingsSubscribers.forEach((connectionId) => {
    const conn = connections.get(connectionId);

    if (!conn || conn.ws.readyState !== WebSocket.OPEN) {
      disconnected.push(connectionId);
      return;
    }

    try {
      conn.ws.send(messageStr);
      sentCount++;
    } catch (err) {
      logger.error({ connectionId, err }, "Error sending SEC filing");
      disconnected.push(connectionId);
    }
  });

  // Limpiar conexiones desconectadas
  disconnected.forEach((connectionId) => {
    secFilingsSubscribers.delete(connectionId);
  });

  if (sentCount > 0) {
    logger.debug(
      {
        accessionNo: filingData.accessionNo,
        ticker: filingData.ticker,
        formType: filingData.formType,
        sentTo: sentCount
      },
      "📋 Broadcasted SEC filing"
    );
  }
}

/**
 * Procesador del stream de Benzinga News
 * Lee stream:benzinga:news y broadcast a clientes suscritos
 */
async function processBenzingaNewsStream() {
  const STREAM_NAME = "stream:benzinga:news";
  let lastId = "$"; // Leer solo mensajes nuevos

  logger.info("📰 Starting Benzinga News stream processor");

  while (true) {
    try {
      const result = await redis.xread(
        "BLOCK",
        5000,
        "COUNT",
        50,
        "STREAMS",
        STREAM_NAME,
        lastId
      );

      if (!result) {
        logger.debug("📰 No new messages (timeout)");
        continue;
      }

      for (const [_stream, messages] of result) {
        for (const [id, fields] of messages) {
          lastId = id;
          const message = parseRedisFields(fields);

          // El mensaje viene con type="news" y data=JSON
          if (message.type === "news" && message.data) {
            try {
              const articleData = JSON.parse(message.data);
              
              // Broadcast a todos los clientes suscritos a Benzinga News
              broadcastBenzingaNews(articleData);
              
            } catch (parseErr) {
              logger.error({ err: parseErr }, "Error parsing Benzinga news data");
            }
          }
        }
      }
    } catch (err) {
      logger.error({ err }, "Error reading Benzinga news stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Broadcast de Benzinga News a clientes suscritos
 */
function broadcastBenzingaNews(articleData) {
  if (benzingaNewsSubscribers.size === 0) return;

  const message = {
    type: "benzinga_news",
    article: articleData,
    timestamp: new Date().toISOString()
  };

  const messageStr = JSON.stringify(message);
  let sentCount = 0;
  const disconnected = [];

  benzingaNewsSubscribers.forEach((connectionId) => {
    const conn = connections.get(connectionId);

    if (!conn || conn.ws.readyState !== WebSocket.OPEN) {
      disconnected.push(connectionId);
      return;
    }

    try {
      conn.ws.send(messageStr);
      sentCount++;
    } catch (err) {
      logger.error({ connectionId, err }, "Error sending Benzinga news");
      disconnected.push(connectionId);
    }
  });

  // Limpiar conexiones desconectadas
  disconnected.forEach((connectionId) => {
    benzingaNewsSubscribers.delete(connectionId);
  });

  if (sentCount > 0) {
    logger.debug(
      {
        benzingaId: articleData.benzinga_id,
        title: articleData.title?.substring(0, 50),
        tickers: articleData.tickers,
        sentTo: sentCount
      },
      "📰 Broadcasted Benzinga news"
    );
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
    sequence_numbers: new Map(),
  });

  logger.info(
    { connectionId, ip: req.socket.remoteAddress },
    "✅ Client connected"
  );

  // Enviar mensaje de bienvenida
  sendMessage(connectionId, {
    type: "connected",
    connection_id: connectionId,
    message: "Connected to Tradeul Scanner (Hybrid: Rankings + Real-time)",
    timestamp: new Date().toISOString(),
  });

  // Manejar mensajes del cliente
  ws.on("message", async (message) => {
    try {
      const json = Buffer.from(message).toString("utf-8");
      const data = JSON.parse(json);
      const { action } = data;

      // =============================================
      // SUBSCRIBE TO LIST
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

        // Suscribir cliente
        subscribeClientToList(connectionId, listName);

        // Enviar snapshot inicial
        await sendInitialSnapshot(connectionId, listName);

        sendMessage(connectionId, {
          type: "subscribed_list",
          list: listName,
          timestamp: new Date().toISOString(),
        });
      }

      // =============================================
      // UNSUBSCRIBE FROM LIST
      // =============================================
      else if (action === "unsubscribe_list") {
        const listName = data.list;
        unsubscribeClientFromList(connectionId, listName);

        sendMessage(connectionId, {
          type: "unsubscribed_list",
          list: listName,
          timestamp: new Date().toISOString(),
        });
      }

      // =============================================
      // REQUEST RESYNC
      // =============================================
      else if (action === "resync") {
        const listName = data.list;
        logger.info({ connectionId, listName }, "🔄 Client requested resync");
        await sendInitialSnapshot(connectionId, listName);
      }

      // Suscribirse a SEC Filings
      else if (action === "subscribe_sec_filings") {
        secFilingsSubscribers.add(connectionId);
        logger.info({ connectionId }, "📋 Client subscribed to SEC Filings");
        
        // Enviar confirmación
        sendMessage(connectionId, {
          type: "subscribed",
          channel: "SEC_FILINGS",
          message: "Subscribed to real-time SEC filings"
        });
      }

      // Desuscribirse de SEC Filings
      else if (action === "unsubscribe_sec_filings") {
        secFilingsSubscribers.delete(connectionId);
        logger.info({ connectionId }, "📋 Client unsubscribed from SEC Filings");
        
        sendMessage(connectionId, {
          type: "unsubscribed",
          channel: "SEC_FILINGS"
        });
      }

      // Suscribirse a News (acepta ambos: subscribe_news y subscribe_benzinga_news)
      else if (action === "subscribe_news" || action === "subscribe_benzinga_news") {
        benzingaNewsSubscribers.add(connectionId);
        logger.info({ connectionId }, "📰 Client subscribed to News");
        
        sendMessage(connectionId, {
          type: "subscribed",
          channel: "NEWS",
          message: "Subscribed to real-time news"
        });
      }

      // Desuscribirse de News (acepta ambos: unsubscribe_news y unsubscribe_benzinga_news)
      else if (action === "unsubscribe_news" || action === "unsubscribe_benzinga_news") {
        benzingaNewsSubscribers.delete(connectionId);
        logger.info({ connectionId }, "📰 Client unsubscribed from News");
        
        sendMessage(connectionId, {
          type: "unsubscribed",
          channel: "NEWS"
        });
      }

      // Ping/Pong heartbeat (ignorar, es normal)
      else if (action === "ping" || action === "pong") {
        // Responder con pong si es ping
        if (action === "ping") {
          sendMessage(connectionId, {
            type: "pong",
            timestamp: Date.now()
          });
        }
        // No hacer nada si es pong (es respuesta a nuestro heartbeat)
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
    unsubscribeClientFromAll(connectionId);
    secFilingsSubscribers.delete(connectionId);
    benzingaNewsSubscribers.delete(connectionId);
    connections.delete(connectionId);
    logger.info({ connectionId }, "❌ Client disconnected");
  });

  // Manejar errores
  ws.on("error", (err) => {
    logger.error({ connectionId, err }, "WebSocket error");
    unsubscribeClientFromAll(connectionId);
    secFilingsSubscribers.delete(connectionId);
    benzingaNewsSubscribers.delete(connectionId);
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

processSECFilingsStream().catch((err) => {
  logger.fatal({ err }, "SEC Filings stream processor crashed");
  process.exit(1);
});

processBenzingaNewsStream().catch((err) => {
  logger.fatal({ err }, "Benzinga News stream processor crashed");
  process.exit(1);
});

// =============================================
// POLYGON SUBSCRIPTION STATUS BROADCASTER
// =============================================

/**
 * Publica periódicamente qué tickers están suscritos a Polygon
 * Para que el frontend pueda mostrar indicadores visuales
 */
async function broadcastPolygonSubscriptionStatus() {
  try {
    // Consultar API de Polygon WS
    const response = await fetch('http://polygon_ws:8006/subscriptions');
    const data = await response.json();
    
    const subscribedTickers = new Set(data.subscribed_tickers || []);
    
    // Broadcast a TODOS los clientes conectados
    const message = {
      type: 'polygon_subscription_status',
      subscribed_tickers: Array.from(subscribedTickers),
      count: subscribedTickers.size,
      timestamp: new Date().toISOString()
    };
    
    let sentCount = 0;
    connections.forEach((conn, connectionId) => {
      if (conn.ws.readyState === WebSocket.OPEN) {
        try {
          conn.ws.send(JSON.stringify(message));
          sentCount++;
        } catch (err) {
          logger.error({ connectionId, err }, "Error sending subscription status");
        }
      }
    });
    
    if (sentCount > 0) {
      logger.debug(
        { sentCount, subscribedCount: subscribedTickers.size },
        "📡 Broadcasted Polygon subscription status"
      );
    }
  } catch (err) {
    logger.error({ err }, "Error broadcasting Polygon subscription status");
  }
}

// 🔥 Suscribirse a eventos de nuevo día (después de que Redis conecte)
redisSubscriber.on("connect", () => {
  logger.info("📡 Redis Subscriber connected");
  subscribeToNewDayEvents(redisSubscriber, lastSnapshots)
    .then(() => {
      logger.info("✅ Subscribed to cache clear events");
    })
    .catch((err) => {
      logger.error({ err }, "Failed to subscribe to cache clear events");
    });
});

// Iniciar servidor
server.listen(PORT, () => {
  logger.info({ port: PORT }, "🚀 WebSocket Server started");
  logger.info("📡 Architecture: HYBRID + SEC Filings + Benzinga News");
  logger.info("  ✅ Rankings: Snapshot + Deltas (every 10s)");
  logger.info("  ✅ Price/Volume: Real-time Aggregates (every 1s)");
  logger.info("  ✅ SEC Filings: Real-time stream from SEC Stream API");
  logger.info("  ✅ Benzinga News: Real-time news from Polygon/Benzinga API");
  logger.info("  ✅ Optimized broadcasting with inverted index");
  logger.info("  ✅ Symbol→Lists mapping for aggregates");
  logger.info("  ✅ Polygon subscription status (every 10s)");
  
  // Publicar status cada 10 segundos
  setInterval(broadcastPolygonSubscriptionStatus, 10000);
  
  // Primera publicación después de 2 segundos (dar tiempo a que Polygon WS se conecte)
  setTimeout(broadcastPolygonSubscriptionStatus, 2000);
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
