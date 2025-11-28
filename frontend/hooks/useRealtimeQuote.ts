'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { Subject, filter, map, takeUntil } from 'rxjs';

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

class QuoteManager {
  private static instance: QuoteManager | null = null;
  private ws: WebSocket | null = null;
  private url: string = '';
  private isConnected = false;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  
  // Suscripciones: symbol → Set<callback>
  private subscriptions = new Map<string, Set<(quote: QuoteData) => void>>();
  
  // Cache del último quote por símbolo
  private lastQuotes = new Map<string, QuoteData>();
  
  // Subject para quotes
  private quotesSubject = new Subject<QuoteMessage>();
  
  private debug = false;

  private constructor() {}

  static getInstance(): QuoteManager {
    if (!QuoteManager.instance) {
      QuoteManager.instance = new QuoteManager();
    }
    return QuoteManager.instance;
  }

  connect(url: string, debug: boolean = false) {
    if (this.ws && this.url === url && this.isConnected) {
      if (debug) console.log('📊 [QuoteManager] Already connected');
      return;
    }

    this.url = url;
    this.debug = debug;
    this.doConnect();
  }

  private doConnect() {
    if (this.debug) console.log('📊 [QuoteManager] Connecting to:', this.url);

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        if (this.debug) console.log('📊 [QuoteManager] Connected');
        this.isConnected = true;
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
        if (this.debug) console.log('📊 [QuoteManager] Disconnected');
        this.isConnected = false;
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
    
    const quote: QuoteData = {
      symbol,
      bidPrice: data.bidPrice,
      bidSize: data.bidSize,
      askPrice: data.askPrice,
      askSize: data.askSize,
      bidExchange: data.bidExchange,
      askExchange: data.askExchange,
      midPrice: (data.bidPrice + data.askPrice) / 2,
      spread: data.askPrice - data.bidPrice,
      spreadPercent: ((data.askPrice - data.bidPrice) / data.askPrice) * 100,
      timestamp: data.timestamp,
      lastUpdate: new Date(),
      // Pasar métricas de latencia si existen
      _latency: (data as any)._latency,
    };

    // Guardar en cache
    this.lastQuotes.set(symbol, quote);

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
      if (this.isConnected) {
        this.sendSubscribe(symbolUpper);
      }
    }
    
    this.subscriptions.get(symbolUpper)!.add(callback);
    
    if (this.debug) {
      console.log(`📊 [QuoteManager] Subscribed to ${symbolUpper} (${this.subscriptions.get(symbolUpper)!.size} listeners)`);
    }

    // Enviar último quote conocido inmediatamente
    const lastQuote = this.lastQuotes.get(symbolUpper);
    if (lastQuote) {
      callback(lastQuote);
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
            console.log(`📊 [QuoteManager] Last listener removed for ${symbolUpper}`);
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
      if (this.debug) console.log(`📊 [QuoteManager] Sent subscribe for ${symbol}`);
    }
  }

  private sendUnsubscribe(symbol: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'unsubscribe_quote',
        symbol: symbol
      }));
      if (this.debug) console.log(`📊 [QuoteManager] Sent unsubscribe for ${symbol}`);
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
      if (this.debug) console.log('📊 [QuoteManager] Reconnecting...');
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
    this.isConnected = false;
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
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const managerRef = useRef<QuoteManager>(QuoteManager.getInstance());
  const initializedRef = useRef(false);

  // Inicializar manager
  useEffect(() => {
    if (!initializedRef.current) {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
      managerRef.current.connect(wsUrl, debug);
      initializedRef.current = true;
    }
  }, [debug]);

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

// ============================================================================
// React Hook: useRealtimeQuotes (múltiples símbolos)
// ============================================================================

interface UseRealtimeQuotesReturn {
  quotes: Map<string, QuoteData>;
  isLoading: boolean;
}

/**
 * Hook para obtener quotes en tiempo real de múltiples tickers (para watchlists)
 * 
 * @example
 * ```tsx
 * function Watchlist({ symbols }: { symbols: string[] }) {
 *   const { quotes } = useRealtimeQuotes(symbols);
 *   
 *   return (
 *     <ul>
 *       {symbols.map(symbol => {
 *         const quote = quotes.get(symbol);
 *         return (
 *           <li key={symbol}>
 *             {symbol}: {quote ? `$${quote.midPrice.toFixed(2)}` : 'Loading...'}
 *           </li>
 *         );
 *       })}
 *     </ul>
 *   );
 * }
 * ```
 */
export function useRealtimeQuotes(
  symbols: string[],
  options: UseRealtimeQuoteOptions = {}
): UseRealtimeQuotesReturn {
  const { debug = false } = options;
  const [quotes, setQuotes] = useState<Map<string, QuoteData>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const managerRef = useRef<QuoteManager>(QuoteManager.getInstance());
  const initializedRef = useRef(false);

  // Inicializar manager
  useEffect(() => {
    if (!initializedRef.current) {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
      managerRef.current.connect(wsUrl, debug);
      initializedRef.current = true;
    }
  }, [debug]);

  // Suscribirse a todos los símbolos
  useEffect(() => {
    if (!symbols || symbols.length === 0) {
      setQuotes(new Map());
      setIsLoading(false);
      return;
    }

    setIsLoading(true);

    const handleQuote = (quote: QuoteData) => {
      setQuotes(prev => {
        const next = new Map(prev);
        next.set(quote.symbol, quote);
        return next;
      });
      setIsLoading(false);
    };

    const unsubscribe = managerRef.current.subscribeMultiple(symbols, handleQuote);

    return () => {
      unsubscribe();
    };
  }, [symbols.join(',')]); // Re-suscribir si cambian los símbolos

  return { quotes, isLoading };
}

// Exportar el manager para uso avanzado
export { QuoteManager };

