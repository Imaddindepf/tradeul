/**
 * chart_aggregator — Converts raw trades into micro-candles for fluid charts.
 *
 * Reads from:  stream:realtime:trades (Redis Stream, XREADGROUP)
 * Publishes to: chart:trades:{SYMBOL} (Redis Pub/Sub, every FLUSH_MS)
 *
 * Each flush publishes the OHLCV delta of trades received since last flush.
 * The websocket_server subscribes to these channels and forwards to clients.
 * The frontend merges into interval candles via series.update().
 *
 * Result: 5-7 candle updates per second instead of 1 (from A.* aggregates).
 */

const Redis = require("ioredis");

// ── Config ────────────────────────────────────────────────────────────────────
const REDIS_HOST = process.env.REDIS_HOST || "redis";
const REDIS_PORT = parseInt(process.env.REDIS_PORT || "6379", 10);
const REDIS_PASSWORD = process.env.REDIS_PASSWORD || "";
const FLUSH_MS = parseInt(process.env.FLUSH_MS || "150", 10);
const STREAM_KEY = "stream:realtime:trades";
const CONSUMER_GROUP = "chart_aggregator";
const CONSUMER_NAME = "agg_1";
const LOG_INTERVAL_MS = 30_000;

// ── Redis clients ─────────────────────────────────────────────────────────────
const redisOpts = {
  host: REDIS_HOST,
  port: REDIS_PORT,
  password: REDIS_PASSWORD || undefined,
  retryStrategy: (times) => Math.min(times * 100, 5000),
  maxRetriesPerRequest: null,
};

const redisReader = new Redis(redisOpts);
const redisPublisher = new Redis(redisOpts);

redisReader.on("error", (err) => console.error("[reader]", err.message));
redisPublisher.on("error", (err) => console.error("[publisher]", err.message));

// ── In-memory micro-aggregate state ───────────────────────────────────────────
// Map<symbol, { o, h, l, c, v, t, dirty }>
const candles = new Map();

// Stats
let stats = { trades: 0, published: 0, errors: 0 };

// ── Ensure consumer group ─────────────────────────────────────────────────────
async function ensureConsumerGroup() {
  try {
    await redisReader.xgroup("CREATE", STREAM_KEY, CONSUMER_GROUP, "0", "MKSTREAM");
    console.log(`[init] Created consumer group: ${CONSUMER_GROUP}`);
  } catch (err) {
    if (err.message && err.message.includes("BUSYGROUP")) {
      console.log(`[init] Consumer group already exists: ${CONSUMER_GROUP}`);
    } else {
      throw err;
    }
  }
}

// ── Parse Redis stream fields into object ─────────────────────────────────────
function parseFields(fields) {
  const obj = {};
  for (let i = 0; i < fields.length; i += 2) {
    obj[fields[i]] = fields[i + 1];
  }
  return obj;
}

// ── Process trades from Redis Stream ──────────────────────────────────────────
async function processTrades() {
  console.log("[stream] Starting trade consumer loop...");

  while (true) {
    try {
      const results = await redisReader.xreadgroup(
        "GROUP", CONSUMER_GROUP, CONSUMER_NAME,
        "BLOCK", 100,   // 100ms blocking read
        "COUNT", 500,    // Up to 500 trades per batch
        "STREAMS", STREAM_KEY, ">"
      );

      if (!results) continue;

      const ackIds = [];

      for (const [, messages] of results) {
        for (const [id, fields] of messages) {
          const trade = parseFields(fields);
          const symbol = (trade.symbol || "").toUpperCase();
          const price = parseFloat(trade.price);
          const size = parseInt(trade.size || "0", 10);
          const timestamp = parseInt(trade.timestamp || "0", 10);

          ackIds.push(id);

          if (!symbol || !isFinite(price) || price <= 0) continue;

          // Update or create micro-aggregate
          const candle = candles.get(symbol);
          if (!candle || !candle.dirty) {
            // Start new micro-aggregate window
            candles.set(symbol, {
              o: price, h: price, l: price, c: price,
              v: size, t: timestamp, dirty: true,
            });
          } else {
            // Merge into current window
            candle.h = Math.max(candle.h, price);
            candle.l = Math.min(candle.l, price);
            candle.c = price;
            candle.v += size;
            candle.t = Math.max(candle.t, timestamp);
          }

          stats.trades++;
        }
      }

      // ACK processed messages
      if (ackIds.length > 0) {
        try {
          await redisReader.xack(STREAM_KEY, CONSUMER_GROUP, ...ackIds);
        } catch (err) {
          console.error("[stream] ACK error:", err.message);
        }
      }
    } catch (err) {
      if (err.message && err.message.includes("NOGROUP")) {
        console.log("[stream] Consumer group missing, recreating...");
        await ensureConsumerGroup();
      } else {
        console.error("[stream] Error:", err.message);
        stats.errors++;
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
  }
}

// ── Flush dirty candles via Pub/Sub ───────────────────────────────────────────
function startFlushLoop() {
  setInterval(() => {
    for (const [symbol, candle] of candles) {
      if (!candle.dirty) continue;

      const message = JSON.stringify({
        o: candle.o,
        h: candle.h,
        l: candle.l,
        c: candle.c,
        v: candle.v,
        t: candle.t,
      });

      // Publish to channel — no-op if no subscribers
      redisPublisher.publish(`chart:trades:${symbol}`, message).catch((err) => {
        console.error(`[pub] Error publishing ${symbol}:`, err.message);
        stats.errors++;
      });

      stats.published++;

      // Clear: next trade starts a fresh window
      candles.delete(symbol);
    }
  }, FLUSH_MS);

  console.log(`[flush] Publishing dirty candles every ${FLUSH_MS}ms`);
}

// ── Stats logging ─────────────────────────────────────────────────────────────
function startStatsLog() {
  setInterval(() => {
    const symbols = candles.size;
    console.log(
      `[stats] trades=${stats.trades} published=${stats.published} errors=${stats.errors} active_symbols=${symbols}`
    );
    stats = { trades: 0, published: 0, errors: 0 };
  }, LOG_INTERVAL_MS);
}

// ── Graceful shutdown ─────────────────────────────────────────────────────────
function setupGracefulShutdown() {
  const shutdown = async (signal) => {
    console.log(`[shutdown] Received ${signal}, closing...`);
    redisReader.disconnect();
    redisPublisher.disconnect();
    process.exit(0);
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  console.log("╔══════════════════════════════════════════╗");
  console.log("║     chart_aggregator — Trade → Candle    ║");
  console.log("╚══════════════════════════════════════════╝");
  console.log(`  Redis: ${REDIS_HOST}:${REDIS_PORT}`);
  console.log(`  Stream: ${STREAM_KEY}`);
  console.log(`  Flush interval: ${FLUSH_MS}ms`);
  console.log("");

  setupGracefulShutdown();
  await ensureConsumerGroup();
  startFlushLoop();
  startStatsLog();
  await processTrades();
}

main().catch((err) => {
  console.error("[fatal]", err);
  process.exit(1);
});
