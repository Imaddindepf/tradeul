'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Subject, filter, map, takeUntil } from 'rxjs';
import { authFetchStandalone } from './useAuthFetch';
import { useAuth } from '@clerk/nextjs';

// ============================================================================
// Tipos
// ============================================================================

export interface QuoteData {
  symbol: string;
  bidPrice: number;
  bidSize: number;
  askPrice: number;
  askSize: number;
  bidExchange?: string;
  askExchange?: string;
  midPrice: number;
  spread: number;
  spreadPercent: number;
  timestamp: string;
  lastUpdate: Date;
  // Calculated change fields (from prevClose)
  prevClose?: number;
  change?: number;
  changePercent?: number;
  // Métricas de latencia
  _latency?: {
    polygonTs: number;    // Timestamp original de Polygon (Unix MS)
    serverTs: number;     // Cuando WS server lo envió (Unix MS)
    latencyMs: number;    // Latencia Polygon → WS Server
  };
}

interface QuoteMessage {
  type: 'quote';
  symbol: string;
  data: {
    bidPrice: number;
    bidSize: number;
    askPrice: number;
    askSize: number;
    bidExchange?: string;
    askExchange?: string;
    timestamp: string;
  };
  timestamp: string;
}

// ============================================================================
// Singleton Quote Manager (comparte conexión WS)
// ============================================================================

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class QuoteManager {
  private static instance: QuoteManager | null = null;
  private static readonly MAX_CACHE_SIZE = 500;
  private ws: WebSocket | null = null;
  private url: string = '';
  private _isConnected = false;

  get isConnected(): boolean {
    return this._isConnected;
  }
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;

  // Suscripciones: symbol → Set<callback>
  private subscriptions = new Map<string, Set<(quote: QuoteData) => void>>();

  // Cache del último quote por símbolo
  private lastQuotes = new Map<string, QuoteData>();

  // Cache de prevClose por símbolo (para calcular cambio %)
  private prevCloseCache = new Map<string, number>();

  // Cache de snapshots (para fallback cuando no hay quotes)
  private snapshotCache = new Map<string, QuoteData>();
  private snapshotFetching = new Set<string>(); // Evitar múltiples requests simultáneos

  // Subject para quotes
  private quotesSubject = new Subject<QuoteMessage>();

  private debug = false;
  private getTokenFn: (() => Promise<string | null>) | null = null;

  private constructor() { }

  // Configurar función para obtener token de Clerk
  setGetToken(getToken: () => Promise<string | null>) {
    this.getTokenFn = getToken;
  }

  // Fetch prevClose from lightweight prev-day endpoint
  // getToken debe ser pasado desde el hook que usa esta clase
  private async fetchPrevClose(symbol: string, getToken?: () => Promise<string | null>): Promise<number | null> {
    // Check cache first
    if (this.prevCloseCache.has(symbol)) {
      return this.prevCloseCache.get(symbol)!;
    }

    try {
      // Use lightweight prev-close endpoint (just 1 OHLC bar)
      // Si tenemos getToken, usar authFetchStandalone
      let res: Response;
      if (getToken) {
        res = await authFetchStandalone(
          `${API_URL}/api/v1/ticker/${symbol}/prev-close`,
          getToken
        );
      } else {
        res = await fetch(`${API_URL}/api/v1/ticker/${symbol}/prev-close`);
      }

      if (res.ok) {
        const data = await res.json();
        const prevClose = data.close || data.c;
        if (prevClose) {
          this.prevCloseCache.set(symbol, prevClose);
          // FIFO eviction when cache exceeds limit
          if (this.prevCloseCache.size > QuoteManager.MAX_CACHE_SIZE) {
            const it = this.prevCloseCache.keys();
            for (let i = 0; i < 50; i++) this.prevCloseCache.delete(it.next().value!);
          }
          return prevClose;
        }
      }
    } catch (e) {
      // Silently fail - prevClose is optional
    }
    return null;
  }

  // Fetch snapshot as fallback when no quotes are available
  private async fetchSnapshot(symbol: string): Promise<QuoteData | null> {
    // Check if already fetching
    if (this.snapshotFetching.has(symbol)) {
      return null;
    }

    // Check cache first (snapshots are cached for 5 minutes on backend)
    const cached = this.snapshotCache.get(symbol);
    if (cached) {
      const age = Date.now() - cached.lastUpdate.getTime();
      if (age < 60000) { // Use cached snapshot if less than 1 minute old
        return cached;
      }
    }

    this.snapshotFetching.add(symbol);

    try {
      const res = await fetch(`${API_URL}/api/v1/ticker/${symbol}/snapshot`);
      if (!res.ok) {
        return null;
      }

      const data = await res.json();
      const snapshot = data.ticker;

      if (!snapshot || !snapshot.lastQuote) {
        return null;
      }

      const lastQuote = snapshot.lastQuote;
      const bidPrice = lastQuote.p || 0;
      const askPrice = lastQuote.P || 0;
      const bidSize = (lastQuote.s || 0) * 100; // Convert lots to shares
      const askSize = (lastQuote.S || 0) * 100;

      if (bidPrice === 0 || askPrice === 0) {
        return null;
      }

      const midPrice = (bidPrice + askPrice) / 2;
      const prevClose = snapshot.prevDay?.c || null;

      // Calculate change if we have prevClose
      let change: number | undefined;
      let changePercent: number | undefined;
      if (prevClose && prevClose > 0) {
        change = midPrice - prevClose;
        changePercent = ((midPrice - prevClose) / prevClose) * 100;
        // Cache prevClose for future use
        this.prevCloseCache.set(symbol, prevClose);
      }

      const quote: QuoteData = {
        symbol,
        bidPrice,
        bidSize,
        askPrice,
        askSize,
        midPrice,
        spread: askPrice - bidPrice,
        spreadPercent: ((askPrice - bidPrice) / askPrice) * 100,
        timestamp: lastQuote.t?.toString() || Date.now().toString(),
        lastUpdate: new Date(),
        prevClose,
        change,
        changePercent,
        // No latency metrics for snapshot (not real-time)
      };

      // Cache snapshot
      this.snapshotCache.set(symbol, quote);
      // FIFO eviction when cache exceeds limit
      if (this.snapshotCache.size > QuoteManager.MAX_CACHE_SIZE) {
        const it = this.snapshotCache.keys();
        for (let i = 0; i < 50; i++) this.snapshotCache.delete(it.next().value!);
      }

      if (this.debug) {
      }

      return quote;
    } catch (e) {
      if (this.debug) {
        console.error(`📊 [QuoteManager] Error fetching snapshot for ${symbol}:`, e);
      }
      return null;
    } finally {
      this.snapshotFetching.delete(symbol);
    }
  }

  static getInstance(): QuoteManager {
    if (!QuoteManager.instance) {
      QuoteManager.instance = new QuoteManager();
    }
    return QuoteManager.instance;
  }

  connect(url: string, debug: boolean = false) {
    // Si la URL cambió (ej: se añadió token de auth), reconectar
    if (this.url && this.url !== url && this._isConnected) {
      this.disconnect();
    }

    if (this.ws && this.url === url && this._isConnected) {
      return;
    }

    this.url = url;
    this.debug = debug;
    this.doConnect();
  }

  private doConnect() {

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this._isConnected = true;
        this.startHeartbeat();

        // Re-suscribir a todos los símbolos activos
        this.subscriptions.forEach((_, symbol) => {
          this.sendSubscribe(symbol);
        });
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.type === 'quote') {
            this.handleQuote(message as QuoteMessage);
          }
        } catch (err) {
          if (this.debug) console.error('📊 [QuoteManager] Parse error:', err);
        }
      };

      this.ws.onclose = () => {
        this._isConnected = false;
        this.stopHeartbeat();
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        if (this.debug) console.error('📊 [QuoteManager] Error:', err);
      };
    } catch (err) {
      if (this.debug) console.error('📊 [QuoteManager] Connection failed:', err);
      this.scheduleReconnect();
    }
  }

  private handleQuote(message: QuoteMessage) {
    const { symbol, data, timestamp } = message;

    // Get prevClose from cache
    const prevClose = this.prevCloseCache.get(symbol);
    const midPrice = (data.bidPrice + data.askPrice) / 2;

    // Calculate change if we have prevClose
    let change: number | undefined;
    let changePercent: number | undefined;
    if (prevClose && prevClose > 0) {
      change = midPrice - prevClose;
      changePercent = ((midPrice - prevClose) / prevClose) * 100;
    }

    const quote: QuoteData = {
      symbol,
      bidPrice: data.bidPrice,
      bidSize: data.bidSize,
      askPrice: data.askPrice,
      askSize: data.askSize,
      bidExchange: data.bidExchange,
      askExchange: data.askExchange,
      midPrice,
      spread: data.askPrice - data.bidPrice,
      spreadPercent: ((data.askPrice - data.bidPrice) / data.askPrice) * 100,
      timestamp: data.timestamp,
      lastUpdate: new Date(),
      // Change fields
      prevClose,
      change,
      changePercent,
      // Pasar métricas de latencia si existen
      _latency: (data as any)._latency,
    };

    // Guardar en cache with FIFO eviction
    this.lastQuotes.set(symbol, quote);
    if (this.lastQuotes.size > QuoteManager.MAX_CACHE_SIZE) {
      const it = this.lastQuotes.keys();
      for (let i = 0; i < 50; i++) this.lastQuotes.delete(it.next().value!);
    }

    // Notificar a suscriptores
    const callbacks = this.subscriptions.get(symbol);
    if (callbacks) {
      callbacks.forEach(cb => cb(quote));
    }

    // Emitir a través del Subject
    this.quotesSubject.next(message);
  }

  subscribe(symbol: string, callback: (quote: QuoteData) => void): () => void {
    const symbolUpper = symbol.toUpperCase();

    if (!this.subscriptions.has(symbolUpper)) {
      this.subscriptions.set(symbolUpper, new Set());

      // Es el primer suscriptor, enviar subscribe al servidor
      if (this._isConnected) {
        this.sendSubscribe(symbolUpper);
      }

      // Fetch prevClose in background (lightweight endpoint)
      this.fetchPrevClose(symbolUpper, this.getTokenFn || undefined).then(prevClose => {
        if (this.debug && prevClose) {
        }
      });
    }

    this.subscriptions.get(symbolUpper)!.add(callback);

    if (this.debug) {
    }

    // Enviar último quote conocido inmediatamente
    const lastQuote = this.lastQuotes.get(symbolUpper);
    if (lastQuote) {
      callback(lastQuote);
    } else {
      // No hay quote disponible, intentar obtener snapshot como fallback
      this.fetchSnapshot(symbolUpper).then(snapshotQuote => {
        if (snapshotQuote) {
          // Guardar snapshot como último quote
          this.lastQuotes.set(symbolUpper, snapshotQuote);
          // Notificar al callback
          callback(snapshotQuote);
          // Notificar a todos los suscriptores
          const callbacks = this.subscriptions.get(symbolUpper);
          if (callbacks) {
            callbacks.forEach(cb => cb(snapshotQuote));
          }
        }
      });
    }

    // Retornar función de limpieza
    return () => {
      const callbacks = this.subscriptions.get(symbolUpper);
      if (callbacks) {
        callbacks.delete(callback);

        if (callbacks.size === 0) {
          this.subscriptions.delete(symbolUpper);

          // Era el último suscriptor, enviar unsubscribe
          if (this.isConnected) {
            this.sendUnsubscribe(symbolUpper);
          }

          if (this.debug) {
          }
        }
      }
    };
  }

  subscribeMultiple(symbols: string[], callback: (quote: QuoteData) => void): () => void {
    const unsubscribes = symbols.map(symbol => this.subscribe(symbol, callback));

    return () => {
      unsubscribes.forEach(unsub => unsub());
    };
  }

  private sendSubscribe(symbol: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'subscribe_quote',
        symbol: symbol
      }));
    }
  }

  private sendUnsubscribe(symbol: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'unsubscribe_quote',
        symbol: symbol
      }));
    }
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ action: 'ping' }));
      }
    }, 30000);
  }

  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) return;

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.doConnect();
    }, 3000);
  }

  getLastQuote(symbol: string): QuoteData | null {
    return this.lastQuotes.get(symbol.toUpperCase()) || null;
  }

  get quotes$() {
    return this.quotesSubject.asObservable();
  }

  disconnect() {
    this.stopHeartbeat();
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this._isConnected = false;
    this.subscriptions.clear();
    this.lastQuotes.clear();
  }
}

// ============================================================================
// React Hook: useRealtimeQuote
// ============================================================================

interface UseRealtimeQuoteOptions {
  debug?: boolean;
}

interface UseRealtimeQuoteReturn {
  quote: QuoteData | null;
  isLoading: boolean;
  error: string | null;
}

/**
 * Hook para obtener quotes en tiempo real de un ticker
 * 
 * @example
 * ```tsx
 * function TickerDisplay({ symbol }: { symbol: string }) {
 *   const { quote, isLoading } = useRealtimeQuote(symbol);
 *   
 *   if (isLoading) return <span>Loading...</span>;
 *   if (!quote) return <span>No data</span>;
 *   
 *   return (
 *     <span>
 *       ${quote.midPrice.toFixed(2)} (Bid: ${quote.bidPrice} / Ask: ${quote.askPrice})
 *     </span>
 *   );
 * }
 * ```
 */
export function useRealtimeQuote(
  symbol: string,
  options: UseRealtimeQuoteOptions = {}
): UseRealtimeQuoteReturn {
  const { debug = false } = options;
  const { getToken } = useAuth();
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const managerRef = useRef<QuoteManager>(QuoteManager.getInstance());
  const initializedRef = useRef(false);

  // Inicializar manager y configurar getToken
  useEffect(() => {
    if (!initializedRef.current) {
      // Configurar getToken primero
      managerRef.current.setGetToken(getToken);

      // Construir URL con token si estamos autenticados
      async function initConnection() {
        const baseUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';

        try {
          const token = await getToken();
          let wsUrl = baseUrl;

          if (token) {
            // Añadir token a la URL
            const separator = baseUrl.includes('?') ? '&' : '?';
            wsUrl = `${baseUrl}${separator}token=${token}`;
          }

          managerRef.current.connect(wsUrl, debug);
          initializedRef.current = true;
        } catch (error) {
          // Si falla obtener token, conectar sin auth
          managerRef.current.connect(baseUrl, debug);
          initializedRef.current = true;
        }
      }

      initConnection();
    }
  }, [debug, getToken]);

  // Token refresh is handled centrally by AuthWebSocketContext (every 50s).
  // No duplicate interval here to avoid doubling Clerk's internal state growth.

  // Suscribirse al símbolo
  useEffect(() => {
    if (!symbol) {
      setQuote(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    // Suscribirse
    const unsubscribe = managerRef.current.subscribe(symbol, (newQuote) => {
      setQuote(newQuote);
      setIsLoading(false);
    });

    // Timeout para detectar si no hay datos
    const timeout = setTimeout(() => {
      if (!quote) {
        setIsLoading(false);
        // No es un error, simplemente no hay datos de quote todavía
      }
    }, 5000);

    return () => {
      clearTimeout(timeout);
      unsubscribe();
    };
  }, [symbol]);

  return { quote, isLoading, error };
}

// Exportar el manager para uso avanzado
export { QuoteManager };

