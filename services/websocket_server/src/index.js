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
const { subscribeToNewDayEvents, subscribeToSessionChangeEvents, subscribeToMorningNewsEvents, setConnectionsRef } = require("./cache_cleaner");
const { verifyClerkToken, extractTokenFromUrl, isAuthEnabled } = require("./clerkAuth");

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
// IMPORTANTE: enableReadyCheck: false evita que ioredis ejecute comandos INFO
// en una conexión que está en modo subscriber, lo cual causaría errores
const redisSubscriber = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  enableReadyCheck: false,  // Desactivar health check para conexiones Pub/Sub
  lazyConnect: false,
});

// Clientes Redis DEDICADOS para cada stream bloqueante
// Cada XREAD/XREADGROUP bloqueante necesita su propio cliente para evitar conflictos

const redisQuotes = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  maxRetriesPerRequest: null,
});

const redisBenzingaNews = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  maxRetriesPerRequest: null,
});

const redisRankings = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  maxRetriesPerRequest: null,
});

const redisAggregates = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  maxRetriesPerRequest: null,
});

const redisSECFilings = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  maxRetriesPerRequest: null,
});

// Cliente Redis para escuchar cambios en user scans (Pub/Sub)
const redisUserScans = new Redis({
  ...redisConfig,
  retryStrategy: (times) => Math.min(times * 50, 2000),
  enableReadyCheck: false,
  lazyConnect: false,
});

redis.on("connect", () => {
  logger.info("📡 Connected to Redis");
});

redis.on("error", (err) => {
  logger.error({ err }, "Redis error");
});

// Manejadores de error para conexiones adicionales
redisCommands.on("error", (err) => {
  logger.error({ err }, "Redis Commands error");
});

redisBenzingaNews.on("error", (err) => {
  logger.error({ err }, "Redis Benzinga News error");
});

redisRankings.on("error", (err) => {
  logger.error({ err }, "Redis Rankings error");
});

redisAggregates.on("error", (err) => {
  logger.error({ err }, "Redis Aggregates error");
});

redisSECFilings.on("error", (err) => {
  logger.error({ err }, "Redis SEC Filings error");
});

redisUserScans.on("error", (err) => {
  // Ignorar errores de "subscriber mode" ya que son esperados
  if (err.message && err.message.includes("subscriber mode")) {
    return;
  }
  logger.error({ err }, "Redis User Scans error");
});

redisBenzingaNews.on("connect", () => {
  logger.info("📰 Redis Benzinga News client connected");
});

redisSubscriber.on("error", (err) => {
  // Ignorar errores de "subscriber mode" ya que son esperados con enableReadyCheck: false
  if (err.message && err.message.includes("subscriber mode")) {
    return; // Silenciar este error específico
  }
  logger.error({ err }, "Redis Subscriber error");
});

redisQuotes.on("error", (err) => {
  logger.error({ err }, "Redis Quotes error");
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

// =============================================
// CHART SUBSCRIPTIONS: Suscripciones para charts en tiempo real
// =============================================
// Mapeo ticker → Set<connectionId> (quién tiene un chart abierto de este ticker)
const chartSubscribers = new Map();

// Contador de referencias por ticker para charts
const chartRefCount = new Map();

// =============================================
// QUOTES: Suscripciones por ticker para datos individuales
// =============================================
// Mapeo ticker → Set<connectionId> (quién quiere quotes de este ticker)
const quoteSubscribers = new Map();

// Contador de referencias por ticker (para saber cuándo desuscribirse de Polygon)
const quoteRefCount = new Map();

// Mapeo symbol → lists (para broadcast de aggregates)
// "TSLA" -> Set(["GAPPERS_UP", "MOMENTUM_UP"])
const symbolToLists = new Map();

// Últimos snapshots por lista (cache): listName -> { sequence, rows, timestamp }
const lastSnapshots = new Map();

// =============================================
// USER SCANS: Estructuras para scans personalizados
// =============================================

// Ownership de user scans: scanId -> userId
// Se usa para validar que solo el owner puede suscribirse
const userScanOwners = new Map();

// Símbolos en cada user scan: listName (uscan_X) -> Set<symbol>
// Se usa para mantener suscripciones a Polygon cuando un ticker entra/sale
const userScanSymbols = new Map();

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

// =============================================
// CATALYST ALERTS - Price Snapshots
// =============================================

// Cache de últimos precios conocidos: symbol -> { price, volume, rvol, timestamp }
const lastKnownPrices = new Map();

// Configuración de snapshots
const SNAPSHOT_INTERVAL_MS = 30000; // Guardar snapshot cada 30 segundos
const SNAPSHOT_TTL_SECONDS = 900; // TTL de 15 minutos en Redis
const SNAPSHOT_MAX_ENTRIES = 20; // Máximo 20 entradas por ticker (10 minutos a 30s)

/**
 * Actualizar precio conocido de un ticker
 */
function updateLastKnownPrice(symbol, data) {
  lastKnownPrices.set(symbol, {
    price: parseFloat(data.close || data.c || 0),
    volume: parseInt(data.volume_accumulated || data.av || data.volume || 0, 10),
    rvol: parseFloat(data.rvol || 0),
    timestamp: Date.now(),
  });
}

/**
 * Guardar snapshots de precios en Redis para Catalyst Alerts
 * Ejecutado cada 30 segundos
 */
async function savePriceSnapshots() {
  if (lastKnownPrices.size === 0) return;

  const now = Date.now();
  const pipeline = redisCommands.pipeline();
  let count = 0;

  lastKnownPrices.forEach((data, symbol) => {
    // Solo guardar si el dato es reciente (< 5 segundos)
    if (now - data.timestamp > 5000) return;

    const key = `catalyst:snapshot:${symbol}`;
    const entry = JSON.stringify({
      p: data.price,
      v: data.volume,
      r: data.rvol,
      t: now,
    });

    // LPUSH para añadir al inicio de la lista
    pipeline.lpush(key, entry);
    // LTRIM para mantener solo las últimas N entradas
    pipeline.ltrim(key, 0, SNAPSHOT_MAX_ENTRIES - 1);
    // Renovar TTL
    pipeline.expire(key, SNAPSHOT_TTL_SECONDS);
    count++;
  });

  if (count > 0) {
    try {
      await pipeline.exec();
      logger.debug({ count }, "📸 Catalyst snapshots saved");
    } catch (err) {
      logger.error({ err }, "Error saving catalyst snapshots");
    }
  }
}

/**
 * Obtener snapshots de un ticker para Catalyst Alerts
 * @param {string} symbol - Ticker symbol
 * @returns {Promise<Array>} - Array de snapshots [{p, v, r, t}, ...]
 */
async function getCatalystSnapshots(symbol) {
  try {
    const key = `catalyst:snapshot:${symbol}`;
    const entries = await redisCommands.lrange(key, 0, -1);
    return entries.map(e => JSON.parse(e));
  } catch (err) {
    logger.error({ symbol, err }, "Error getting catalyst snapshots");
    return [];
  }
}

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

  // Actualizar precio conocido para Catalyst Alerts
  updateLastKnownPrice(symbol, data);

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

// Guardar snapshots de precios para Catalyst Alerts cada 30 segundos
setInterval(() => {
  savePriceSnapshots();
}, SNAPSHOT_INTERVAL_MS);

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
 * Con fallback a cache completo cuando las categorías no existen
 */
async function getInitialSnapshot(listName) {
  try {
    // Intentar obtener del cache en memoria primero
    if (lastSnapshots.has(listName)) {
      const cached = lastSnapshots.get(listName);
      const age = Date.now() - new Date(cached.timestamp).getTime();

      // Si es reciente (< 5 minutos), usarlo
      if (age < 300000) {
        logger.debug({ listName, age_ms: age }, "Using cached snapshot");
        return cached;
      }
    }

    // Obtener desde Redis (categoría específica)
    const key = `scanner:category:${listName}`;
    let data = await redisCommands.get(key);
    let rows = null;
    let source = "category";

    if (data) {
      rows = JSON.parse(data);
    } else {
      // FALLBACK: Intentar obtener del cache completo
      logger.info({ listName }, "Category not found, trying complete cache fallback");
      
      const lastScanData = await redisCommands.get("scanner:filtered_complete:LAST");
      if (lastScanData) {
        const parsed = JSON.parse(lastScanData);
        const allTickers = parsed.tickers || [];
        
        // Filtrar por categoría usando lógica similar al scanner
        rows = filterTickersByCategory(allTickers, listName);
        source = "fallback";
        
        logger.info(
          { listName, totalTickers: allTickers.length, filtered: rows.length },
          "📸 Using fallback from complete cache"
        );
      }
    }

    // Si no hay datos, devolver snapshot vacío en lugar de null
    // Esto permite que el cliente sepa que la suscripción fue aceptada
    if (!rows) {
      rows = [];
    }
    
    if (rows.length === 0) {
      logger.info({ listName }, "No tickers in category, returning empty snapshot");
    }

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
      source, // Para debug
    };

    // Guardar en cache
    lastSnapshots.set(listName, snapshot);

    logger.info(
      { listName, sequence: snapshot.sequence, count: rows.length, source },
      "📸 Retrieved snapshot from Redis"
    );

    return snapshot;
  } catch (err) {
    logger.error({ err, listName }, "Error getting snapshot");
    return null;
  }
}

/**
 * Filtrar tickers por categoría (fallback cuando categorías no existen)
 */
function filterTickersByCategory(tickers, listName) {
  const MAX_PER_CATEGORY = 100;
  
  switch (listName) {
    case "gappers_up":
      return tickers
        .filter(t => t.gap_percent > 0)
        .sort((a, b) => (b.gap_percent || 0) - (a.gap_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "gappers_down":
      return tickers
        .filter(t => t.gap_percent < 0)
        .sort((a, b) => (a.gap_percent || 0) - (b.gap_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "momentum_up":
      return tickers
        .filter(t => t.change_percent > 0)
        .sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "momentum_down":
      return tickers
        .filter(t => t.change_percent < 0)
        .sort((a, b) => (a.change_percent || 0) - (b.change_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "winners":
      return tickers
        .filter(t => t.change_percent > 5)
        .sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "losers":
      return tickers
        .filter(t => t.change_percent < -5)
        .sort((a, b) => (a.change_percent || 0) - (b.change_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "high_volume":
      return tickers
        .filter(t => t.rvol > 2)
        .sort((a, b) => (b.rvol || 0) - (a.rvol || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "new_highs":
      return tickers
        .filter(t => t.price_from_high !== null && t.price_from_high >= -1)
        .sort((a, b) => (b.price_from_high || -100) - (a.price_from_high || -100))
        .slice(0, MAX_PER_CATEGORY);
    
    case "new_lows":
      return tickers
        .filter(t => t.price_from_low !== null && t.price_from_low <= 1)
        .sort((a, b) => (a.price_from_low || 100) - (b.price_from_low || 100))
        .slice(0, MAX_PER_CATEGORY);
    
    case "anomalies":
      return tickers
        .filter(t => t.rvol > 5 || Math.abs(t.change_percent || 0) > 10)
        .sort((a, b) => (b.rvol || 0) - (a.rvol || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    case "reversals":
      return tickers
        .filter(t => {
          const priceFromHigh = t.price_from_intraday_high || t.price_from_high;
          const priceFromLow = t.price_from_intraday_low || t.price_from_low;
          return (priceFromHigh !== null && priceFromHigh < -5) || 
                 (priceFromLow !== null && priceFromLow > 5);
        })
        .sort((a, b) => Math.abs(b.change_percent || 0) - Math.abs(a.change_percent || 0))
        .slice(0, MAX_PER_CATEGORY);
    
    default:
      // Para categorías desconocidas, devolver top por score
      return tickers
        .sort((a, b) => (b.score || 0) - (a.score || 0))
        .slice(0, MAX_PER_CATEGORY);
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
 * IMPORTANTE: También maneja "update" y "rerank" para robustez
 * (en caso de que se haya perdido el "add" original)
 */
function updateSymbolToListsIndex(listName, deltas) {
  deltas.forEach((delta) => {
    const symbol = delta.symbol;

    if (delta.action === "add" || delta.action === "update" || delta.action === "rerank") {
      // Agregar/asegurar symbol en lista
      // Esto cubre el caso donde se perdió el "add" original
      if (!symbolToLists.has(symbol)) {
        symbolToLists.set(symbol, new Set());
        logger.info(
          { symbol, listName, action: delta.action },
          "📊 Added missing symbol to index"
        );
      }
      symbolToLists.get(symbol).add(listName);
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
      // INVALIDAR CACHE: Cuando llega un delta, el cache puede estar desactualizado
      // Esto asegura que nuevos clientes lean datos frescos de Redis
      // Especialmente importante al inicio del premarket cuando el cache puede estar vacío
      if (lastSnapshots.has(list)) {
        lastSnapshots.delete(list);
        logger.debug({ list }, "🗑️ Cache invalidated due to incoming delta");
      }

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
        
        // ✅ FIX: Actualizar secuencia ANTES de enviar snapshot para evitar loop infinito
        // Usamos messageSeq porque es la secuencia actual del servidor
        conn.sequence_numbers.set(listName, messageSeq);
        
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
 * Validar ownership de user scan
 * @returns {Promise<{valid: boolean, error?: string}>}
 */
async function validateUserScanOwnership(connectionId, listName) {
  // Solo validar si es un user scan (uscan_X)
  if (!listName.startsWith("uscan_")) {
    return { valid: true };
  }
  
  const conn = connections.get(connectionId);
  if (!conn) {
    return { valid: false, error: "Connection not found" };
  }
  
  const scanId = listName.replace("uscan_", "");
  const userId = conn.user?.sub;
  
  if (!userId) {
    return { valid: false, error: "User not authenticated" };
  }
  
  // Verificar en cache local primero
  if (userScanOwners.has(scanId)) {
    const owner = userScanOwners.get(scanId);
    if (owner === userId) {
      return { valid: true };
    }
    return { valid: false, error: "Not authorized to view this scan" };
  }
  
  // Verificar en Redis
  try {
    const owner = await redisCommands.get(`user_scan:owner:${scanId}`);
    
    if (!owner) {
      // Scan no existe o expiró
      return { valid: false, error: "Scan not found" };
    }
    
    // Guardar en cache local
    userScanOwners.set(scanId, owner);
    
    if (owner === userId) {
      return { valid: true };
    }
    
    return { valid: false, error: "Not authorized to view this scan" };
  } catch (err) {
    logger.error({ err, scanId, userId }, "Error validating scan ownership");
    return { valid: false, error: "Error validating ownership" };
  }
}

/**
 * Suscribir cliente a lista
 * NOTA: Para user scans, se debe validar ownership antes de llamar esta función
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
      isUserScan: listName.startsWith("uscan_"),
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
// QUOTE SUBSCRIPTION MANAGEMENT
// =============================================

/**
 * Suscribir cliente a quotes de un ticker
 * Notifica a polygon_ws si es el primer suscriptor de este ticker
 */
async function subscribeClientToQuote(connectionId, symbol) {
  const symbolUpper = symbol.toUpperCase();
  
  // Añadir a índice ticker → connections
  if (!quoteSubscribers.has(symbolUpper)) {
    quoteSubscribers.set(symbolUpper, new Set());
  }
  quoteSubscribers.get(symbolUpper).add(connectionId);
  
  // Incrementar ref count
  const currentCount = quoteRefCount.get(symbolUpper) || 0;
  quoteRefCount.set(symbolUpper, currentCount + 1);
  
  // Si es el primer suscriptor, notificar a polygon_ws
  if (currentCount === 0) {
    try {
      await redisCommands.xadd(
        "polygon_ws:quote_subscriptions",
        "*",
        "action", "subscribe",
        "symbol", symbolUpper
      );
      logger.info({ symbol: symbolUpper }, "📊 First subscriber - notified polygon_ws to subscribe quote");
    } catch (err) {
      logger.error({ err, symbol: symbolUpper }, "Error notifying polygon_ws for quote subscription");
    }
  }
  
  logger.info({
    connectionId,
    symbol: symbolUpper,
    totalSubscribers: quoteSubscribers.get(symbolUpper).size,
    refCount: quoteRefCount.get(symbolUpper)
  }, "📊 Client subscribed to quote");
  
  return true;
}

/**
 * Desuscribir cliente de quotes de un ticker
 * Notifica a polygon_ws si era el último suscriptor
 */
async function unsubscribeClientFromQuote(connectionId, symbol) {
  const symbolUpper = symbol.toUpperCase();
  
  const subscribers = quoteSubscribers.get(symbolUpper);
  if (!subscribers) return;
  
  // Remover de índice
  subscribers.delete(connectionId);
  
  // Decrementar ref count
  const currentCount = quoteRefCount.get(symbolUpper) || 0;
  const newCount = Math.max(0, currentCount - 1);
  quoteRefCount.set(symbolUpper, newCount);
  
  // Si era el último, limpiar y notificar a polygon_ws
  if (newCount === 0) {
    quoteSubscribers.delete(symbolUpper);
    quoteRefCount.delete(symbolUpper);
    
    try {
      await redisCommands.xadd(
        "polygon_ws:quote_subscriptions",
        "*",
        "action", "unsubscribe",
        "symbol", symbolUpper
      );
      logger.info({ symbol: symbolUpper }, "📊 Last subscriber gone - notified polygon_ws to unsubscribe quote");
    } catch (err) {
      logger.error({ err, symbol: symbolUpper }, "Error notifying polygon_ws for quote unsubscription");
    }
  }
  
  logger.info({
    connectionId,
    symbol: symbolUpper,
    remainingSubscribers: subscribers?.size || 0,
    refCount: newCount
  }, "📊 Client unsubscribed from quote");
}

/**
 * Desuscribir cliente de todos los quotes
 */
async function unsubscribeClientFromAllQuotes(connectionId) {
  // Encontrar todos los tickers a los que está suscrito
  const tickersToUnsubscribe = [];
  
  quoteSubscribers.forEach((subscribers, symbol) => {
    if (subscribers.has(connectionId)) {
      tickersToUnsubscribe.push(symbol);
    }
  });
  
  // Desuscribir de cada uno
  for (const symbol of tickersToUnsubscribe) {
    await unsubscribeClientFromQuote(connectionId, symbol);
  }
}

// =============================================
// CHART SUBSCRIPTION MANAGEMENT
// =============================================

/**
 * Suscribir cliente a aggregates de un ticker para charts
 * Los aggregates vienen cada segundo desde Polygon
 */
async function subscribeClientToChart(connectionId, symbol) {
  const symbolUpper = symbol.toUpperCase();
  
  // Añadir a índice ticker → connections
  if (!chartSubscribers.has(symbolUpper)) {
    chartSubscribers.set(symbolUpper, new Set());
  }
  chartSubscribers.get(symbolUpper).add(connectionId);
  
  // Incrementar ref count
  const currentCount = chartRefCount.get(symbolUpper) || 0;
  chartRefCount.set(symbolUpper, currentCount + 1);
  
  // Si es el primer suscriptor, notificar a polygon_ws
  // (Solo si el ticker no está ya suscrito por el Scanner)
  if (currentCount === 0 && !symbolToLists.has(symbolUpper)) {
    try {
      await redisCommands.xadd(
        "polygon_ws:subscriptions",
        "*",
        "action", "subscribe",
        "symbol", symbolUpper
      );
      logger.info({ symbol: symbolUpper }, "📊 Chart: First subscriber - notified polygon_ws");
    } catch (err) {
      logger.error({ err, symbol: symbolUpper }, "Error notifying polygon_ws for chart");
    }
  }
  
  logger.info({
    connectionId,
    symbol: symbolUpper,
    totalSubscribers: chartSubscribers.get(symbolUpper).size,
    refCount: chartRefCount.get(symbolUpper)
  }, "📈 Client subscribed to chart");
  
  return true;
}

/**
 * Desuscribir cliente de aggregates para chart
 */
async function unsubscribeClientFromChart(connectionId, symbol) {
  const symbolUpper = symbol.toUpperCase();
  
  const subscribers = chartSubscribers.get(symbolUpper);
  if (!subscribers) return;
  
  // Remover de índice
  subscribers.delete(connectionId);
  
  // Decrementar ref count
  const currentCount = chartRefCount.get(symbolUpper) || 0;
  const newCount = Math.max(0, currentCount - 1);
  chartRefCount.set(symbolUpper, newCount);
  
  // Si era el último y no está suscrito por el Scanner, notificar a polygon_ws
  if (newCount === 0) {
    chartSubscribers.delete(symbolUpper);
    chartRefCount.delete(symbolUpper);
    
    if (!symbolToLists.has(symbolUpper)) {
      try {
        await redisCommands.xadd(
          "polygon_ws:subscriptions",
          "*",
          "action", "unsubscribe",
          "symbol", symbolUpper
        );
        logger.info({ symbol: symbolUpper }, "📊 Chart: Last subscriber gone - notified polygon_ws");
      } catch (err) {
        logger.error({ err, symbol: symbolUpper }, "Error notifying polygon_ws for chart unsubscription");
      }
    }
  }
  
  logger.info({
    connectionId,
    symbol: symbolUpper,
    remainingSubscribers: subscribers?.size || 0,
    refCount: newCount
  }, "📈 Client unsubscribed from chart");
}

/**
 * Desuscribir cliente de todos los charts
 */
async function unsubscribeClientFromAllCharts(connectionId) {
  const tickersToUnsubscribe = [];
  
  chartSubscribers.forEach((subscribers, symbol) => {
    if (subscribers.has(connectionId)) {
      tickersToUnsubscribe.push(symbol);
    }
  });
  
  for (const symbol of tickersToUnsubscribe) {
    await unsubscribeClientFromChart(connectionId, symbol);
  }
}

/**
 * Broadcast de aggregate a clientes suscritos a chart de ese ticker
 */
function broadcastChartAggregate(symbol, aggregateData) {
  const subscribers = chartSubscribers.get(symbol);
  if (!subscribers || subscribers.size === 0) return 0;
  
  const message = {
    type: "chart_aggregate",
    symbol: symbol,
    data: aggregateData,
    timestamp: new Date().toISOString()
  };
  
  const messageStr = JSON.stringify(message);
  let sentCount = 0;
  const disconnected = [];
  
  subscribers.forEach((connectionId) => {
    const conn = connections.get(connectionId);
    
    if (!conn || conn.ws.readyState !== WebSocket.OPEN) {
      disconnected.push(connectionId);
      return;
    }
    
    try {
      conn.ws.send(messageStr);
      sentCount++;
    } catch (err) {
      logger.error({ connectionId, err }, "Error sending chart aggregate");
      disconnected.push(connectionId);
    }
  });
  
  // Limpiar conexiones desconectadas
  disconnected.forEach((connectionId) => {
    subscribers.delete(connectionId);
    const currentCount = chartRefCount.get(symbol) || 0;
    chartRefCount.set(symbol, Math.max(0, currentCount - 1));
  });
  
  return sentCount;
}

/**
 * Broadcast de quote a clientes suscritos a ese ticker
 */
function broadcastQuote(symbol, quoteData) {
  const subscribers = quoteSubscribers.get(symbol);
  if (!subscribers || subscribers.size === 0) return;
  
  const now = Date.now();
  const polygonTimestamp = parseInt(quoteData.timestamp || 0, 10); // Unix MS from Polygon
  const latencyFromPolygon = polygonTimestamp > 0 ? now - polygonTimestamp : null;
  
  const message = {
    type: "quote",
    symbol: symbol,
    data: {
      bidPrice: parseFloat(quoteData.bid_price || 0),
      bidSize: parseInt(quoteData.bid_size || 0, 10),
      askPrice: parseFloat(quoteData.ask_price || 0),
      askSize: parseInt(quoteData.ask_size || 0, 10),
      bidExchange: quoteData.bid_exchange,
      askExchange: quoteData.ask_exchange,
      timestamp: quoteData.timestamp,
      // Métricas de latencia
      _latency: {
        polygonTs: polygonTimestamp,      // Timestamp original de Polygon
        serverTs: now,                     // Cuando el WS server lo envía
        latencyMs: latencyFromPolygon      // Latencia Polygon → WS Server
      }
    },
    timestamp: new Date().toISOString()
  };
  
  const messageStr = JSON.stringify(message);
  let sentCount = 0;
  const disconnected = [];
  
  subscribers.forEach((connectionId) => {
    const conn = connections.get(connectionId);
    
    if (!conn || conn.ws.readyState !== WebSocket.OPEN) {
      disconnected.push(connectionId);
      return;
    }
    
    try {
      conn.ws.send(messageStr);
      sentCount++;
    } catch (err) {
      logger.error({ connectionId, err }, "Error sending quote");
      disconnected.push(connectionId);
    }
  });
  
  // Limpiar conexiones desconectadas
  disconnected.forEach((connectionId) => {
    subscribers.delete(connectionId);
    // También decrementar ref count
    const currentCount = quoteRefCount.get(symbol) || 0;
    quoteRefCount.set(symbol, Math.max(0, currentCount - 1));
  });
  
  if (sentCount > 0) {
    logger.debug({
      symbol,
      sentTo: sentCount,
      bid: message.data.bidPrice,
      ask: message.data.askPrice
    }, "📊 Broadcasted quote");
  }
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
      // BLOCK 100ms para baja latencia - Cliente dedicado para rankings
      const results = await redisRankings.xreadgroup(
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
      // BLOCK 100ms para latencia casi en tiempo real - Cliente dedicado para aggregates
      const results = await redisAggregates.xreadgroup(
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

              // Verificar si el símbolo está en alguna lista (Scanner)
              const lists = symbolToLists.get(symbolUpper);

              if (lists && lists.size > 0) {
                // Agregar al buffer con sampling para Scanner
                bufferAggregate(symbolUpper, data);
              }
              
              // NUEVO: Enviar a chart subscribers (sin throttle, cada segundo)
              const chartSubs = chartSubscribers.get(symbolUpper);
              if (chartSubs && chartSubs.size > 0) {
                const chartData = {
                  o: parseFloat(data.open || 0),
                  h: parseFloat(data.high || 0),
                  l: parseFloat(data.low || 0),
                  c: parseFloat(data.close || 0),
                  v: parseInt(data.volume || 0, 10),
                  av: parseInt(data.volume_accumulated || 0, 10),
                  t: parseInt(data.timestamp_end || data.timestamp_start || Date.now(), 10)
                };
                broadcastChartAggregate(symbolUpper, chartData);
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
      // Cliente dedicado para SEC Filings
      const result = await redisSECFilings.xread(
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

  logger.info("📰 Starting Benzinga News stream processor (dedicated Redis client)");

  while (true) {
    try {
      // Usar cliente Redis DEDICADO para evitar bloqueo con otras operaciones
      const result = await redisBenzingaNews.xread(
        "BLOCK",
        5000,
        "COUNT",
        50,
        "STREAMS",
        STREAM_NAME,
        lastId
      );

      if (!result) {
        continue;
      }
      
      logger.info({ messagesCount: result[0]?.[1]?.length || 0 }, "📰 Received news messages from stream");

      for (const [_stream, messages] of result) {
        for (const [id, fields] of messages) {
          lastId = id;
          const message = parseRedisFields(fields);

          // El mensaje viene con type="news" y data=JSON
          if (message.type === "news" && message.data) {
            try {
              const articleData = JSON.parse(message.data);
              
              // Añadir catalyst_metrics si existen
              let catalystMetrics = null;
              if (message.catalyst_metrics) {
                try {
                  catalystMetrics = JSON.parse(message.catalyst_metrics);
                } catch (e) {
                  // Ignorar error de parsing
                }
              }
              
              // Broadcast a todos los clientes suscritos a Benzinga News
              broadcastBenzingaNews(articleData, catalystMetrics);
              
            } catch (parseErr) {
              logger.error({ err: parseErr }, "Error parsing Benzinga news data");
            }
          }
          // Alertas de catalyst (impacto real detectado por el engine)
          else if (message.type === "catalyst_alert" && message.ticker) {
            try {
              let metrics = null;
              if (message.metrics) {
                metrics = typeof message.metrics === "string" 
                  ? JSON.parse(message.metrics) 
                  : message.metrics;
              }
              
              // Broadcast alerta de catalyst directamente
              broadcastCatalystAlert(message.ticker, metrics);
              
            } catch (parseErr) {
              logger.error({ err: parseErr }, "Error parsing catalyst alert");
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
 * Procesador del stream de Quotes
 * Lee stream:realtime:quotes y broadcast a clientes suscritos por ticker
 */
async function processQuotesStream() {
  const streamName = "stream:realtime:quotes";
  const consumerGroup = "websocket_server_quotes";
  const consumerName = "ws_server_1";

  logger.info({ streamName }, "📊 Starting quotes stream consumer");

  // Crear consumer group
  try {
    await redisCommands.xgroup(
      "CREATE",
      streamName,
      consumerGroup,
      "$",
      "MKSTREAM"
    );
    logger.info({ streamName, consumerGroup }, "Created consumer group for quotes");
  } catch (err) {
    logger.debug({ err: err.message }, "Quotes consumer group already exists");
  }

  while (true) {
    try {
      // BLOCK 100ms para latencia casi en tiempo real
      // Usamos redisQuotes (cliente dedicado) para evitar bloqueo con otros streams
      const results = await redisQuotes.xreadgroup(
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

              // Verificar si hay suscriptores para este ticker
              const hasSubscribers = quoteSubscribers.has(symbolUpper);
              const subscriberCount = hasSubscribers ? quoteSubscribers.get(symbolUpper).size : 0;
              
              if (hasSubscribers && subscriberCount > 0) {
                logger.info({
                  symbol: symbolUpper,
                  subscribers: subscriberCount,
                  bid: data.bid_price,
                  ask: data.ask_price
                }, "📊 Broadcasting quote to subscribers");
                broadcastQuote(symbolUpper, data);
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
            logger.error({ err }, "Error acknowledging quote messages");
          }
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 10));
    } catch (err) {
      // Auto-healing: Si el consumer group fue borrado, recrearlo
      if (err.message && err.message.includes('NOGROUP')) {
        logger.warn({ streamName, consumerGroup }, "🔧 Quotes consumer group missing - auto-recreating");
        try {
          await redisCommands.xgroup(
            "CREATE",
            streamName,
            consumerGroup,
            "0",
            "MKSTREAM"
          );
          logger.info({ streamName, consumerGroup }, "✅ Quotes consumer group recreated");
          continue;
        } catch (recreateErr) {
          logger.error({ err: recreateErr }, "Failed to recreate quotes consumer group");
        }
      }
      
      logger.error({ err, streamName }, "Error in quotes stream");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

/**
 * Broadcast de Benzinga News a clientes suscritos
 */
function broadcastBenzingaNews(articleData, catalystMetrics = null) {
  if (benzingaNewsSubscribers.size === 0) {
    logger.debug({ title: articleData.title?.substring(0, 30), tickers: articleData.tickers?.slice(0, 3) }, "📰 News received but no subscribers");
    return;
  }

  const message = {
    type: "benzinga_news",
    article: articleData,
    timestamp: new Date().toISOString()
  };
  
  // Añadir catalyst_metrics si existen (para alertas de movimiento explosivo)
  if (catalystMetrics) {
    message.catalyst_metrics = catalystMetrics;
  }

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
    logger.info(
      {
        benzingaId: articleData.benzinga_id,
        title: articleData.title?.substring(0, 50),
        tickers: articleData.tickers,
        sentTo: sentCount,
        hasCatalystMetrics: !!catalystMetrics
      },
      "📰 Broadcasted Benzinga news"
    );
  }
}

/**
 * Broadcast de alerta de catalyst a clientes suscritos a Benzinga News
 * Estas alertas son diferentes a las noticias: son impactos reales detectados
 */
function broadcastCatalystAlert(ticker, metrics) {
  if (benzingaNewsSubscribers.size === 0) {
    logger.debug({ ticker }, "🚨 Catalyst alert but no subscribers");
    return;
  }

  const message = {
    type: "catalyst_alert",
    ticker: ticker,
    metrics: metrics,
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
      logger.error({ connectionId, err }, "Error sending catalyst alert");
      disconnected.push(connectionId);
    }
  });

  // Limpiar conexiones desconectadas
  disconnected.forEach((connectionId) => {
    benzingaNewsSubscribers.delete(connectionId);
  });

  if (sentCount > 0) {
    logger.info(
      {
        ticker,
        change: metrics?.change_since_news_pct,
        rvol: metrics?.rvol,
        sentTo: sentCount,
      },
      "🚨 Catalyst alert broadcast"
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
wss.on("connection", async (ws, req) => {
  const connectionId = uuidv4();
  ws.connectionId = connectionId;
  
  // =============================================
  // 🔒 AUTENTICACIÓN JWT (si está habilitada)
  // =============================================
  let user = null;
  
  if (isAuthEnabled()) {
    const token = extractTokenFromUrl(req.url);
    
    if (!token) {
      logger.warn({ connectionId, ip: req.socket.remoteAddress }, "❌ Connection rejected: missing token");
      ws.close(4001, "Token required");
      return;
    }
    
    try {
      user = await verifyClerkToken(token);
      logger.info({ connectionId, userId: user.sub }, "🔐 Authenticated");
    } catch (err) {
      logger.warn({ connectionId, error: err.message }, "❌ Connection rejected: invalid token");
      ws.close(4003, "Invalid token");
      return;
    }
  }

  connections.set(connectionId, {
    ws,
    subscriptions: new Set(),
    sequence_numbers: new Map(),
    user, // Guardar info del usuario
  });

  logger.info(
    { connectionId, ip: req.socket.remoteAddress, userId: user?.sub },
    "✅ Client connected"
  );

  // Enviar mensaje de bienvenida con trading_date (para detectar cambio de día)
  // Leemos el estado de sesión de Redis para obtener el trading_date actual
  let tradingDate = null;
  let currentSession = null;
  try {
    const sessionStatus = await redis.get("market:session:status");
    if (sessionStatus) {
      const parsed = JSON.parse(sessionStatus);
      tradingDate = parsed.trading_date;
      currentSession = parsed.current_session;
    }
  } catch (err) {
    logger.warn({ err }, "Could not read market session status");
  }
  
  sendMessage(connectionId, {
    type: "connected",
    connection_id: connectionId,
    message: "Connected to Tradeul Scanner (Hybrid: Rankings + Real-time)",
    timestamp: new Date().toISOString(),
    authenticated: !!user,
    trading_date: tradingDate,
    current_session: currentSession,
  });

  // Manejar mensajes del cliente
  ws.on("message", async (message) => {
    try {
      const json = Buffer.from(message).toString("utf-8");
      const data = JSON.parse(json);
      const { action } = data;

      // =============================================
      // REFRESH TOKEN (sin desconectar)
      // =============================================
      if (action === "refresh_token") {
        const newToken = data.token;
        
        if (!newToken) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'token' parameter"
          });
          return;
        }
        
        if (isAuthEnabled()) {
          try {
            const newUser = await verifyClerkToken(newToken);
            const conn = connections.get(connectionId);
            if (conn) {
              conn.user = newUser;
              logger.debug({ connectionId, userId: newUser.sub }, "🔐 Token refreshed");
            }
            sendMessage(connectionId, {
              type: "token_refreshed",
              success: true,
              timestamp: new Date().toISOString()
            });
          } catch (err) {
            logger.warn({ connectionId, error: err.message }, "❌ Token refresh failed");
            sendMessage(connectionId, {
              type: "token_refresh_failed",
              error: err.message,
              timestamp: new Date().toISOString()
            });
          }
        }
        return;
      }

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

        // Validar ownership para user scans
        if (listName.startsWith("uscan_")) {
          const validation = await validateUserScanOwnership(connectionId, listName);
          if (!validation.valid) {
            logger.warn(
              { connectionId, listName, error: validation.error },
              "User scan access denied"
            );
            sendMessage(connectionId, {
              type: "error",
              message: validation.error || "Access denied",
            });
            return;
          }
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

      // =============================================
      // SUBSCRIBE TO QUOTE (ticker individual)
      // =============================================
      else if (action === "subscribe_quote") {
        const symbol = data.symbol;
        
        if (!symbol) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'symbol' parameter for quote subscription"
          });
          return;
        }
        
        await subscribeClientToQuote(connectionId, symbol);
        
        sendMessage(connectionId, {
          type: "subscribed",
          channel: "QUOTE",
          symbol: symbol.toUpperCase(),
          message: `Subscribed to real-time quotes for ${symbol.toUpperCase()}`
        });
      }

      // =============================================
      // UNSUBSCRIBE FROM QUOTE
      // =============================================
      else if (action === "unsubscribe_quote") {
        const symbol = data.symbol;
        
        if (!symbol) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'symbol' parameter for quote unsubscription"
          });
          return;
        }
        
        await unsubscribeClientFromQuote(connectionId, symbol);
        
        sendMessage(connectionId, {
          type: "unsubscribed",
          channel: "QUOTE",
          symbol: symbol.toUpperCase()
        });
      }

      // =============================================
      // SUBSCRIBE TO MULTIPLE QUOTES (para watchlists)
      // =============================================
      else if (action === "subscribe_quotes") {
        const symbols = data.symbols;
        
        if (!symbols || !Array.isArray(symbols)) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'symbols' array for quotes subscription"
          });
          return;
        }
        
        const subscribedSymbols = [];
        for (const symbol of symbols) {
          await subscribeClientToQuote(connectionId, symbol);
          subscribedSymbols.push(symbol.toUpperCase());
        }
        
        sendMessage(connectionId, {
          type: "subscribed",
          channel: "QUOTES",
          symbols: subscribedSymbols,
          message: `Subscribed to real-time quotes for ${subscribedSymbols.length} symbols`
        });
      }

      // =============================================
      // UNSUBSCRIBE FROM MULTIPLE QUOTES
      // =============================================
      else if (action === "unsubscribe_quotes") {
        const symbols = data.symbols;
        
        if (!symbols || !Array.isArray(symbols)) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'symbols' array for quotes unsubscription"
          });
          return;
        }
        
        for (const symbol of symbols) {
          await unsubscribeClientFromQuote(connectionId, symbol);
        }
        
        sendMessage(connectionId, {
          type: "unsubscribed",
          channel: "QUOTES",
          symbols: symbols.map(s => s.toUpperCase())
        });
      }

      // =============================================
      // SUBSCRIBE TO CHART (real-time aggregates per second)
      // =============================================
      else if (action === "subscribe_chart") {
        const symbol = data.symbol;
        
        if (!symbol) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'symbol' parameter for chart subscription"
          });
          return;
        }
        
        await subscribeClientToChart(connectionId, symbol);
        
        sendMessage(connectionId, {
          type: "subscribed",
          channel: "CHART",
          symbol: symbol.toUpperCase(),
          message: `Subscribed to real-time chart data for ${symbol.toUpperCase()}`
        });
      }

      // =============================================
      // UNSUBSCRIBE FROM CHART
      // =============================================
      else if (action === "unsubscribe_chart") {
        const symbol = data.symbol;
        
        if (!symbol) {
          sendMessage(connectionId, {
            type: "error",
            message: "Missing 'symbol' parameter for chart unsubscription"
          });
          return;
        }
        
        await unsubscribeClientFromChart(connectionId, symbol);
        
        sendMessage(connectionId, {
          type: "unsubscribed",
          channel: "CHART",
          symbol: symbol.toUpperCase()
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
  ws.on("close", async () => {
    unsubscribeClientFromAll(connectionId);
    secFilingsSubscribers.delete(connectionId);
    benzingaNewsSubscribers.delete(connectionId);
    await unsubscribeClientFromAllQuotes(connectionId);
    await unsubscribeClientFromAllCharts(connectionId);  // ✅ Limpiar charts
    connections.delete(connectionId);
    logger.info({ connectionId }, "❌ Client disconnected");
  });

  // Manejar errores
  ws.on("error", async (err) => {
    logger.error({ connectionId, err }, "WebSocket error");
    unsubscribeClientFromAll(connectionId);
    secFilingsSubscribers.delete(connectionId);
    benzingaNewsSubscribers.delete(connectionId);
    await unsubscribeClientFromAllQuotes(connectionId);
    await unsubscribeClientFromAllCharts(connectionId);  // ✅ Limpiar charts
    connections.delete(connectionId);
  });
});

// =============================================
// USER SCANS CHANGE LISTENER
// =============================================

/**
 * Procesar cambios en user scans via Pub/Sub
 * Escucha canal ws:user_scans:changed
 * 
 * Actions:
 * - created: Nuevo scan disponible (cache owner)
 * - updated: Scan modificado (invalidar cache)
 * - deleted: Scan eliminado (desuscribir clientes, limpiar índices)
 */
async function processUserScanChanges() {
  logger.info("🔧 Starting User Scans change listener");
  
  try {
    await redisUserScans.subscribe("ws:user_scans:changed");
    
    redisUserScans.on("message", async (channel, message) => {
      if (channel !== "ws:user_scans:changed") return;
      
      try {
        const data = JSON.parse(message);
        const { action, scan_id, user_id, category, name } = data;
        
        logger.info(
          { action, scan_id, user_id, category },
          "📥 Received user scan change event"
        );
        
        if (action === "created") {
          // Cachear ownership
          userScanOwners.set(String(scan_id), user_id);
          logger.info({ scan_id, user_id }, "✅ Cached user scan owner");
        }
        else if (action === "updated") {
          // Actualizar ownership cache y invalidar snapshot cache
          userScanOwners.set(String(scan_id), user_id);
          lastSnapshots.delete(category);
          logger.info({ scan_id, category }, "🔄 Invalidated user scan cache");
        }
        else if (action === "deleted") {
          // 1. Obtener suscriptores de esta lista
          const listName = category || `uscan_${scan_id}`;
          const subscribers = listSubscribers.get(listName);
          
          if (subscribers && subscribers.size > 0) {
            // 2. Notificar a todos los clientes que el scan fue eliminado
            const notification = {
              type: "scan_deleted",
              list: listName,
              message: "This scan has been deleted by the owner",
              timestamp: new Date().toISOString()
            };
            
            subscribers.forEach((connectionId) => {
              sendMessage(connectionId, notification);
              // Desuscribir cliente
              const conn = connections.get(connectionId);
              if (conn) {
                conn.subscriptions.delete(listName);
                conn.sequence_numbers.delete(listName);
              }
            });
            
            logger.info(
              { listName, subscribersCount: subscribers.size },
              "📤 Notified clients of deleted scan"
            );
          }
          
          // 3. Limpiar índices de suscriptores y ownership
          listSubscribers.delete(listName);
          userScanOwners.delete(String(scan_id));
          lastSnapshots.delete(listName);
          
          // 4. Limpiar símbolos asociados de symbolToLists
          // IMPORTANTE: Iterar symbolToLists y eliminar este listName de cada symbol
          // Esto asegura que si XYZ está en uscan_A y uscan_B, al eliminar uscan_B
          // XYZ sigue en symbolToLists porque uscan_A todavía lo tiene
          let symbolsRemoved = 0;
          symbolToLists.forEach((lists, symbol) => {
            if (lists.has(listName)) {
              lists.delete(listName);
              symbolsRemoved++;
              // Solo eliminar el symbol si no está en ninguna otra lista
              if (lists.size === 0) {
                symbolToLists.delete(symbol);
                logger.debug({ symbol }, "Symbol removed from all lists");
              }
            }
          });
          
          // También limpiar userScanSymbols si existe
          userScanSymbols.delete(listName);
          
          logger.info(
            { scan_id, listName, symbolsRemoved },
            "🗑️ Cleaned up deleted user scan"
          );
        }
      } catch (parseErr) {
        logger.error({ parseErr, message }, "Error parsing user scan change message");
      }
    });
    
    logger.info("✅ User Scans change listener started");
  } catch (err) {
    logger.error({ err }, "Error starting user scans change listener");
  }
}

/**
 * Actualizar índice de símbolos para un user scan
 * Se llama cuando llega un delta o snapshot de un user scan
 */
function updateUserScanSymbols(listName, symbols) {
  if (!listName.startsWith("uscan_")) return;
  
  const oldSymbols = userScanSymbols.get(listName) || new Set();
  const newSymbols = new Set(symbols);
  
  // Símbolos añadidos
  newSymbols.forEach((symbol) => {
    if (!oldSymbols.has(symbol)) {
      if (!symbolToLists.has(symbol)) {
        symbolToLists.set(symbol, new Set());
      }
      symbolToLists.get(symbol).add(listName);
    }
  });
  
  // Símbolos removidos
  oldSymbols.forEach((symbol) => {
    if (!newSymbols.has(symbol)) {
      const lists = symbolToLists.get(symbol);
      if (lists) {
        lists.delete(listName);
        if (lists.size === 0) {
          symbolToLists.delete(symbol);
        }
      }
    }
  });
  
  userScanSymbols.set(listName, newSymbols);
}

// =============================================
// STARTUP
// =============================================

// Iniciar listener de cambios en user scans
processUserScanChanges().catch((err) => {
  logger.error({ err }, "User Scans change listener failed to start");
});

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

processQuotesStream().catch((err) => {
  logger.fatal({ err }, "Quotes stream processor crashed");
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

// 🔥 Suscribirse a eventos de nuevo día y cambio de sesión (después de que Redis conecte)
redisSubscriber.on("connect", () => {
  logger.info("📡 Redis Subscriber connected");
  
  // Setear referencia a las conexiones para broadcasts
  setConnectionsRef(connections);
  
  // Suscribirse a eventos de nuevo día (limpia caches)
  subscribeToNewDayEvents(redisSubscriber, lastSnapshots)
    .then(() => {
      logger.info("✅ Subscribed to cache clear events");
    })
    .catch((err) => {
      logger.error({ err }, "Failed to subscribe to cache clear events");
    });
  
  // Suscribirse a eventos de cambio de sesión del mercado
  subscribeToSessionChangeEvents(redisSubscriber)
    .then(() => {
      logger.info("✅ Subscribed to market session change events");
    })
    .catch((err) => {
      logger.error({ err }, "Failed to subscribe to session change events");
    });
  
  // Suscribirse a notificaciones de Morning News Call
  subscribeToMorningNewsEvents(redisSubscriber)
    .then(() => {
      logger.info("✅ Subscribed to Morning News Call events");
    })
    .catch((err) => {
      logger.error({ err }, "Failed to subscribe to morning news events");
    });
});

// Iniciar servidor
server.listen(PORT, () => {
  logger.info({ port: PORT }, "🚀 WebSocket Server started");
  logger.info("📡 Architecture: HYBRID + SEC Filings + Benzinga News + Quotes + Morning News");
  logger.info("  ✅ Rankings: Snapshot + Deltas (every 10s)");
  logger.info("  ✅ Price/Volume: Real-time Aggregates (every 1s)");
  logger.info("  ✅ SEC Filings: Real-time stream from SEC Stream API");
  logger.info("  ✅ Benzinga News: Real-time news from Polygon/Benzinga API");
  logger.info("  ✅ Quotes: Real-time bid/ask for individual tickers");
  logger.info("  ✅ Morning News Call: Daily briefing at 7:30 AM ET");
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
    redisQuotes.disconnect();
    logger.info("Server shut down complete");
    process.exit(0);
  });
});

process.on("SIGINT", () => {
  logger.info("SIGINT received, shutting down gracefully");
  server.close(() => {
    redis.disconnect();
    redisCommands.disconnect();
    redisQuotes.disconnect();
    logger.info("Server shut down complete");
    process.exit(0);
  });
});
