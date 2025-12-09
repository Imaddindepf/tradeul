/**
 * WebSocket Chat Server
 * 
 * COMPLETELY SEPARATE from scanner WS (port 9000)
 * Runs on port 9001
 * 
 * Features:
 * - Real-time chat messages
 * - Typing indicators
 * - Presence (online users)
 * - Redis Streams for pub/sub
 */

import { WebSocketServer } from 'ws';
import Redis from 'ioredis';
import pino from 'pino';
import { createRequire } from 'module';

// Import CommonJS module
const require = createRequire(import.meta.url);
const { verifyClerkToken, isAuthEnabled } = require('./clerkAuth.cjs');

// ============================================================================
// CONFIGURATION
// ============================================================================

const PORT = parseInt(process.env.CHAT_WS_PORT || '9001');
const REDIS_HOST = process.env.REDIS_HOST || 'localhost';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379');
const REDIS_PASSWORD = process.env.REDIS_PASSWORD;

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  transport: process.env.NODE_ENV !== 'production' 
    ? { target: 'pino-pretty' } 
    : undefined
});

// ============================================================================
// REDIS CLIENTS (Separate from scanner)
// ============================================================================

/** @type {Redis} */
let redisSubscriber;
/** @type {Redis} */
let redisPublisher;

function createRedisClient(name) {
  const client = new Redis({
    host: REDIS_HOST,
    port: REDIS_PORT,
    password: REDIS_PASSWORD || undefined,
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
  });
  
  client.on('connect', () => logger.info({ client: name }, 'Redis connected'));
  client.on('error', (err) => logger.error({ client: name, error: err.message }, 'Redis error'));
  
  return client;
}

// ============================================================================
// WEBSOCKET SERVER
// ============================================================================

const wss = new WebSocketServer({ port: PORT });

/** @type {Map<string, Set<WebSocket>>} Channel/Group ID → Set of WebSockets */
const subscriptions = new Map();

/** @type {Map<WebSocket, {userId: string, channels: Set<string>, userName: string}>} */
const clients = new Map();

/** @type {Map<string, Set<string>>} Channel ID → Set of user IDs online */
const presenceMap = new Map();

// ============================================================================
// MESSAGE HANDLERS
// ============================================================================

async function handleMessage(ws, data) {
  try {
    const message = JSON.parse(data);
    const { type, payload } = message;
    
    logger.info({ type, payload }, 'Message received from client');
    
    switch (type) {
      case 'subscribe':
        handleSubscribe(ws, payload);
        break;
      case 'unsubscribe':
        handleUnsubscribe(ws, payload);
        break;
      case 'typing':
        handleTyping(ws, payload);
        break;
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong' }));
        break;
      default:
        logger.warn({ type }, 'Unknown message type');
    }
  } catch (error) {
    logger.error({ error: error.message }, 'Message handling error');
  }
}

function handleSubscribe(ws, { channel_id, group_id }) {
  const target = channel_id ? `channel:${channel_id}` : `group:${group_id}`;
  
  // Add to subscriptions map
  if (!subscriptions.has(target)) {
    subscriptions.set(target, new Set());
  }
  subscriptions.get(target).add(ws);
  
  // Track in client data
  const clientData = clients.get(ws);
  if (clientData) {
    clientData.channels.add(target);
    
    // Update presence
    if (!presenceMap.has(target)) {
      presenceMap.set(target, new Set());
    }
    presenceMap.get(target).add(clientData.userId);
    
    // Broadcast presence update
    broadcastToTarget(target, {
      type: 'presence',
      payload: {
        target,
        online: Array.from(presenceMap.get(target))
      }
    });
  }
  
  logger.info({ target, totalSubs: subscriptions.get(target)?.size || 0 }, 'Client subscribed');
}

function handleUnsubscribe(ws, { channel_id, group_id }) {
  const target = channel_id ? `channel:${channel_id}` : `group:${group_id}`;
  
  if (subscriptions.has(target)) {
    subscriptions.get(target).delete(ws);
    if (subscriptions.get(target).size === 0) {
      subscriptions.delete(target);
    }
  }
  
  const clientData = clients.get(ws);
  if (clientData) {
    clientData.channels.delete(target);
    
    // Update presence
    if (presenceMap.has(target)) {
      presenceMap.get(target).delete(clientData.userId);
      
      // Broadcast presence update
      broadcastToTarget(target, {
        type: 'presence',
        payload: {
          target,
          online: Array.from(presenceMap.get(target))
        }
      });
    }
  }
}

function handleTyping(ws, { channel_id, group_id }) {
  const target = channel_id ? `channel:${channel_id}` : `group:${group_id}`;
  const clientData = clients.get(ws);
  
  if (!clientData) return;
  
  // Broadcast typing indicator to all in channel except sender
  broadcastToTarget(target, {
    type: 'typing',
    payload: {
      user_id: clientData.userId,
      user_name: clientData.userName,
      target
    }
  }, ws);
}

function broadcastToTarget(target, message, excludeWs = null) {
  const subs = subscriptions.get(target);
  if (!subs) return;
  
  const payload = JSON.stringify(message);
  
  for (const ws of subs) {
    if (ws !== excludeWs && ws.readyState === 1) {
      ws.send(payload);
    }
  }
}

function broadcastToUser(userId, message) {
  const payload = JSON.stringify(message);
  
  for (const [ws, clientData] of clients) {
    if (clientData.userId === userId && ws.readyState === 1) {
      ws.send(payload);
    }
  }
}

// ============================================================================
// REDIS STREAM CONSUMER
// ============================================================================

async function startRedisConsumer() {
  const streamPatterns = ['stream:chat:channel:*', 'stream:chat:group:*'];
  
  // Use PSUBSCRIBE for pattern matching
  // But for streams, we need to poll - let's use a hybrid approach
  
  // For simplicity, poll known active streams
  const pollStreams = async () => {
    try {
      // Get all active targets from subscriptions
      for (const target of subscriptions.keys()) {
        const streamKey = `stream:chat:${target}`;
        
        try {
          // Read new messages (non-blocking with XREAD)
          const results = await redisSubscriber.xread(
            'COUNT', 100,
            'BLOCK', 0, // Don't block, just check
            'STREAMS', streamKey, '$'
          );
          
          if (results) {
            for (const [stream, messages] of results) {
              for (const [id, fields] of messages) {
                const type = fields[1]; // type is at index 1 in flat array
                const payloadStr = fields[3]; // payload at index 3
                
                if (payloadStr) {
                  const payload = JSON.parse(payloadStr);
                  
                  // Broadcast to WebSocket clients
                  broadcastToTarget(target, {
                    type: type || 'new_message',
                    payload
                  });
                }
              }
            }
          }
        } catch (e) {
          // Stream might not exist yet, ignore
        }
      }
    } catch (error) {
      logger.error({ error: error.message }, 'Stream poll error');
    }
  };
  
  // Poll every 100ms for low latency
  setInterval(pollStreams, 100);
  
  // Also use pub/sub for instant notifications
  const pubsubClient = createRedisClient('pubsub');
  
  // Subscribe to chat channels and user notifications
  pubsubClient.psubscribe('chat:*', 'user:*', (err) => {
    if (err) {
      logger.error({ error: err.message }, 'PSubscribe error');
    } else {
      logger.info('Subscribed to chat:* and user:* channels');
    }
  });
  
  pubsubClient.on('pmessage', (pattern, channel, message) => {
    try {
      const data = JSON.parse(message);
      
      if (channel.startsWith('user:')) {
        // Direct message to a specific user
        const userId = channel.replace('user:', '');
        broadcastToUser(userId, data);
        logger.info({ userId, type: data.type }, 'User notification sent');
      } else {
        // Chat channel/group message
        const target = channel.replace('chat:', '');
        const subsCount = subscriptions.get(target)?.size || 0;
        logger.info({ channel, target, subsCount }, 'Pub/sub message received');
        broadcastToTarget(target, data);
      }
    } catch (e) {
      logger.error({ error: e.message, channel }, 'Pub/sub message error');
    }
  });
}

// ============================================================================
// CONNECTION HANDLING
// ============================================================================

wss.on('connection', async (ws, req) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const token = url.searchParams.get('token');
  
  let user = { userId: `anon_${Date.now()}`, userName: 'Anonymous' };
  
  // Authenticate if token provided
  if (isAuthEnabled() && token) {
    try {
      const claims = await verifyClerkToken(token);
      if (claims) {
        user = {
          userId: claims.sub,
          userName: claims.name || claims.username || 'User'
        };
        logger.debug({ userId: user.userId }, 'Client authenticated');
      }
    } catch (error) {
      logger.warn({ error: error.message }, 'Auth failed, allowing anonymous');
    }
  }
  
  // Register client
  clients.set(ws, {
    userId: user.userId,
    userName: user.userName,
    channels: new Set()
  });
  
  logger.info({ 
    userId: user.userId,
    total: clients.size 
  }, 'Client connected');
  
  // Send connection confirmation
  ws.send(JSON.stringify({
    type: 'connected',
    payload: {
      userId: user.userId,
      userName: user.userName
    }
  }));
  
  // Message handler
  ws.on('message', (data) => handleMessage(ws, data));
  
  // Cleanup on close
  ws.on('close', () => {
    const clientData = clients.get(ws);
    
    if (clientData) {
      // Remove from all subscriptions
      for (const target of clientData.channels) {
        if (subscriptions.has(target)) {
          subscriptions.get(target).delete(ws);
        }
        
        // Update presence
        if (presenceMap.has(target)) {
          presenceMap.get(target).delete(clientData.userId);
          
          // Broadcast updated presence
          broadcastToTarget(target, {
            type: 'presence',
            payload: {
              target,
              online: Array.from(presenceMap.get(target))
            }
          });
        }
      }
    }
    
    clients.delete(ws);
    logger.info({ total: clients.size }, 'Client disconnected');
  });
  
  ws.on('error', (error) => {
    logger.error({ error: error.message }, 'WebSocket error');
  });
});

// ============================================================================
// STARTUP
// ============================================================================

async function start() {
  logger.info({ port: PORT }, 'Starting Chat WebSocket Server');
  
  // Initialize Redis
  redisSubscriber = createRedisClient('subscriber');
  redisPublisher = createRedisClient('publisher');
  
  await Promise.all([
    redisSubscriber.ping(),
    redisPublisher.ping()
  ]);
  
  // Start stream consumer
  await startRedisConsumer();
  
  logger.info({ 
    port: PORT,
    auth: isAuthEnabled() 
  }, '🚀 Chat WebSocket Server running');
}

start().catch((error) => {
  logger.fatal({ error: error.message }, 'Failed to start server');
  process.exit(1);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  logger.info('Shutting down...');
  
  wss.close();
  await redisSubscriber?.quit();
  await redisPublisher?.quit();
  
  process.exit(0);
});

