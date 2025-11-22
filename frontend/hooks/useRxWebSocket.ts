/**
 * RxJS WebSocket Hook - Con SharedWorker para Multi-Tab
 * 
 * V3 OPTIMIZADO:
 * - Usa SharedWorker internamente (1 conexión WS para todas las tabs)
 * - Parsing JSON en worker thread (no bloquea UI)
 * - API idéntica a V2 (componentes no cambian)
 * - Fallback a WebSocket directo si SharedWorker no disponible
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import {
  Observable,
  Subject,
  BehaviorSubject,
  timer,
  throwError,
  EMPTY,
  merge,
} from 'rxjs';
import {
  webSocket,
  WebSocketSubject,
  WebSocketSubjectConfig,
} from 'rxjs/webSocket';
import {
  tap,
  retryWhen,
  switchMap,
  catchError,
  share,
  takeUntil,
  bufferTime,
  filter,
  map,
} from 'rxjs/operators';
import type { WebSocketMessage } from '@/lib/types';

// ============================================================================
// SINGLETON WEBSOCKET MANAGER
// ============================================================================

class WebSocketManager {
  private static instance: WebSocketManager | null = null;
  private ws$: WebSocketSubject<any> | null = null;
  private sharedWorker: SharedWorker | null = null;
  private workerPort: MessagePort | null = null;
  private useSharedWorker = false;
  private url: string = '';
  private isConnected = new BehaviorSubject<boolean>(false);
  private connectionId = new BehaviorSubject<string | null>(null);
  private reconnectAttempt = 0;
  private subscribers = new Set<string>();
  private debug = false;

  // Subjects para mensajes
  private snapshotsSubject = new Subject<WebSocketMessage>();
  private deltasSubject = new Subject<WebSocketMessage>();
  private aggregatesSubject = new Subject<WebSocketMessage>();
  private errorsSubject = new Subject<Error>();
  private allMessagesSubject = new BehaviorSubject<WebSocketMessage | null>(null);

  // Heartbeat timer
  private heartbeatTimer: NodeJS.Timeout | null = null;

  private constructor() {
    // Detectar si SharedWorker está disponible
    this.useSharedWorker = typeof SharedWorker !== 'undefined';
  }

  static getInstance(): WebSocketManager {
    if (!WebSocketManager.instance) {
      WebSocketManager.instance = new WebSocketManager();
    }
    return WebSocketManager.instance;
  }

  connect(url: string, debugMode: boolean = false) {
    // Si ya hay una conexión con la misma URL, no hacer nada
    if ((this.ws$ || this.sharedWorker) && this.url === url) {
      if (debugMode) console.log('🔄 [RxWS] Already connected, reusing connection');
      return;
    }

    this.url = url;
    this.debug = debugMode;

    // Limpiar conexiones anteriores
    if (this.ws$) {
      if (this.debug) console.log('🔌 [RxWS] Closing existing connection');
      this.ws$.complete();
      this.ws$ = null;
    }

    // PRIORIDAD: Intentar SharedWorker primero
    if (this.useSharedWorker && typeof window !== 'undefined') {
      try {
        this.connectWithSharedWorker(url, debugMode);
        return;
      } catch (error) {
        if (this.debug) console.warn('⚠️ SharedWorker failed, falling back to direct WebSocket:', error);
        this.useSharedWorker = false; // Disable para futuros intentos
      }
    }

    // FALLBACK: WebSocket directo (código original)
    if (this.debug) console.log('🚀 [RxWS] Creating direct WebSocket to:', url);

    const wsConfig: WebSocketSubjectConfig<any> = {
      url,
      openObserver: {
        next: () => {
          if (this.debug) console.log('🟢 [RxWS-Singleton] Connection opened');
          this.isConnected.next(true);
          this.reconnectAttempt = 0;
          this.startHeartbeat();
        },
      },
      closeObserver: {
        next: () => {
          if (this.debug) console.log('🔴 [RxWS-Singleton] Connection closed');
          this.isConnected.next(false);
          this.connectionId.next(null);
          this.stopHeartbeat();
        },
      },
    };

    this.ws$ = webSocket(wsConfig);

    // Subscribe to incoming messages
    this.ws$
      .pipe(
        tap((message: any) => {

          this.allMessagesSubject.next(message);
        }),
        tap((message: WebSocketMessage) => {
          switch (message.type) {
            case 'snapshot':
              this.snapshotsSubject.next(message);
              break;
            case 'delta':
              this.deltasSubject.next(message);
              break;
            case 'aggregate':
              this.aggregatesSubject.next(message);
              break;
            case 'connected':
              this.connectionId.next(message.connection_id || null);
              if (this.debug) console.log('✅ [RxWS-Singleton] Connection ID:', message.connection_id);
              break;
          }
        }),
        retryWhen((errors) =>
          errors.pipe(
            tap((error) => {
              this.reconnectAttempt++;
              this.errorsSubject.next(error as Error);
              if (this.debug) {
                console.error('❌ [RxWS-Singleton] Error:', error);
                console.log(`🔄 [RxWS-Singleton] Reconnecting... (attempt ${this.reconnectAttempt})`);
              }
            }),
            switchMap((_, attempt) => {
              const backoff = Math.min(3000 * Math.pow(2, attempt), 60000);
              return timer(backoff);
            })
          )
        ),
        catchError((error) => {
          if (this.debug) console.error('❌ [RxWS-Singleton] Fatal error:', error);
          this.isConnected.next(false);
          return EMPTY;
        })
      )
      .subscribe();
  }

  send(message: any) {
    if (this.workerPort) {
      // Enviar a través del SharedWorker
      this.workerPort.postMessage({
        action: 'send',
        payload: message
      });
    } else if (this.ws$ && this.isConnected.value) {
      // Enviar directamente (fallback)
      this.ws$.next(message);
      if (this.debug) console.log('📤 [RxWS] Message sent:', message);
    } else {
      if (this.debug) console.warn('⚠️ [RxWS] Cannot send, not connected');
    }
  }

  subscribe(listName: string) {
    this.subscribers.add(listName);
    if (this.debug) console.log(`📋 [RxWS] Subscribed to list: ${listName} (total: ${this.subscribers.size})`);

    if (this.workerPort) {
      // Suscribir a través del SharedWorker
      this.workerPort.postMessage({
        action: 'subscribe_list',
        list: listName
      });
    } else {
      // Suscribir directamente (fallback)
      this.send({ action: 'subscribe_list', list: listName });
    }
  }

  unsubscribe(listName: string) {
    this.subscribers.delete(listName);
    if (this.debug) console.log(`📋 [RxWS] Unsubscribed from list: ${listName} (total: ${this.subscribers.size})`);

    if (this.workerPort) {
      // Desuscribir a través del SharedWorker
      this.workerPort.postMessage({
        action: 'unsubscribe_list',
        list: listName
      });
    } else {
      // Desuscribir directamente (fallback)
      this.send({ action: 'unsubscribe_list', list: listName });
    }
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected.value) {
        this.send({ action: 'ping' });
      }
    }, 30000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private connectWithSharedWorker(url: string, debugMode: boolean) {
    if (this.debug) console.log('🚀 [RxWS] Using SharedWorker for:', url);

    this.sharedWorker = new SharedWorker('/workers/websocket-shared.js', {
      name: 'tradeul-websocket'
    });
    this.workerPort = this.sharedWorker.port;

    // Configurar handler de mensajes del worker
    this.workerPort.onmessage = (event) => {
      const msg = event.data;

      switch (msg.type) {
        case 'message':
          // Mensaje del WebSocket parseado en el worker
          const message = msg.data;
          this.allMessagesSubject.next(message);

          // Routing a subjects específicos
          switch (message.type) {
            case 'snapshot':
              this.snapshotsSubject.next(message);
              break;
            case 'delta':
              this.deltasSubject.next(message);
              break;
            case 'aggregate':
              this.aggregatesSubject.next(message);
              break;
            case 'connected':
              this.connectionId.next(message.connection_id || null);
              if (this.debug) console.log('✅ [RxWS-SharedWorker] Connection ID:', message.connection_id);
              break;
          }
          break;

        case 'status':
          // Estado de conexión del worker
          this.isConnected.next(msg.isConnected);
          if (this.debug) {
            console.log(`📊 [RxWS-SharedWorker] Status: ${msg.isConnected ? 'connected' : 'disconnected'} (${msg.activePorts} tabs)`);
          }
          break;

        case 'log':
          // Logs del worker (solo en debug)
          if (this.debug) {
            const emoji = { info: 'ℹ️', warn: '⚠️', error: '❌' }[msg.level] || '📝';
            console.log(`${emoji} [SharedWorker]`, msg.message, msg.data || '');
          }
          break;
      }
    };

    this.workerPort.onerror = (error) => {
      if (this.debug) console.error('❌ [RxWS-SharedWorker] Port error:', error);
      this.errorsSubject.next(new Error('SharedWorker port error'));
    };

    this.workerPort.start();

    // Conectar al WebSocket a través del worker
    this.workerPort.postMessage({
      action: 'connect',
      url: url
    });

    if (this.debug) console.log('✅ [RxWS] SharedWorker initialized');
  }

  disconnect() {
    if (this.debug) console.log('🔌 [RxWS] Disconnecting...');
    this.stopHeartbeat();

    if (this.workerPort) {
      // Desconectar SharedWorker (solo si somos la última tab)
      this.workerPort.postMessage({ action: 'disconnect' });
      this.workerPort = null;
      this.sharedWorker = null;
    }

    if (this.ws$) {
      this.ws$.complete();
      this.ws$ = null;
    }

    this.isConnected.next(false);
    this.connectionId.next(null);
    this.subscribers.clear();
  }

  // Observables públicos
  get isConnected$() {
    return this.isConnected.asObservable();
  }

  get connectionId$() {
    return this.connectionId.asObservable();
  }

  get snapshots$(): Observable<WebSocketMessage> {
    return this.snapshotsSubject.asObservable().pipe(share());
  }

  get deltas$(): Observable<WebSocketMessage> {
    return this.deltasSubject.asObservable().pipe(share());
  }

  get aggregates$(): Observable<WebSocketMessage> {
    return this.aggregatesSubject.asObservable().pipe(
      bufferTime(100),
      filter((buffer) => buffer.length > 0),
      map((buffer) => {
        const aggregatesMap = new Map<string, any>();
        buffer.forEach((msg) => {
          if (msg.symbol && msg.data) {
            aggregatesMap.set(msg.symbol, msg.data);
          }
        });
        return {
          type: 'aggregates_batch',
          data: aggregatesMap,
          count: aggregatesMap.size,
          timestamp: new Date().toISOString(),
        } as any;
      }),
      share()
    );
  }

  get errors$(): Observable<Error> {
    return this.errorsSubject.asObservable().pipe(share());
  }

  get messages$(): Observable<WebSocketMessage> {
    return this.allMessagesSubject.asObservable().pipe(
      filter((msg) => msg !== null),
      map((msg) => msg!),
      share()
    );
  }
}

// ============================================================================
// REACT HOOK
// ============================================================================

export interface UseRxWebSocketReturn {
  isConnected: boolean;
  connectionId: string | null;
  messages$: Observable<WebSocketMessage>;
  snapshots$: Observable<WebSocketMessage>;
  deltas$: Observable<WebSocketMessage>;
  aggregates$: Observable<WebSocketMessage>;
  errors$: Observable<Error>;
  send: (payload: any) => void;
  reconnect: () => void;
}

export function useRxWebSocket(url: string, debug: boolean = false): UseRxWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const managerRef = useRef<WebSocketManager>(WebSocketManager.getInstance());
  const isInitializedRef = useRef(false);

  // Inicializar conexión UNA SOLA VEZ
  useEffect(() => {
    if (!isInitializedRef.current) {
      managerRef.current.connect(url, debug);
      isInitializedRef.current = true;
    }

    // Suscribirse a cambios de estado
    const connSub = managerRef.current.isConnected$.subscribe(setIsConnected);
    const idSub = managerRef.current.connectionId$.subscribe(setConnectionId);

    return () => {
      connSub.unsubscribe();
      idSub.unsubscribe();
      // NO desconectamos aquí porque es compartido
    };
  }, [url, debug]);

  const send = useCallback((payload: any) => {
    managerRef.current.send(payload);
  }, []);

  const reconnect = useCallback(() => {
    managerRef.current.disconnect();
    managerRef.current.connect(url, debug);
  }, [url, debug]);

  return {
    isConnected,
    connectionId,
    messages$: managerRef.current.messages$,
    snapshots$: managerRef.current.snapshots$,
    deltas$: managerRef.current.deltas$,
    aggregates$: managerRef.current.aggregates$,
    errors$: managerRef.current.errors$,
    send,
    reconnect,
  };
}

// ============================================================================
// HELPER HOOK - Para gestionar suscripciones a listas
// ============================================================================

export function useListSubscription(listName: string, debug: boolean = false) {
  const manager = WebSocketManager.getInstance();
  const [isConnected, setIsConnected] = useState(false);

  // Track connection state
  useEffect(() => {
    const sub = manager.isConnected$.subscribe(setIsConnected);
    return () => sub.unsubscribe();
  }, [manager]);

  // Subscribe/unsubscribe when connected
  useEffect(() => {
    if (!isConnected) return;

    if (debug) console.log(`🔗 [useListSubscription] Subscribing to: ${listName}`);
    manager.subscribe(listName);

    return () => {
      if (debug) console.log(`🔗 [useListSubscription] Unsubscribing from: ${listName}`);
      manager.unsubscribe(listName);
    };
  }, [listName, isConnected]);
}
