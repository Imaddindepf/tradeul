/**
 * RxJS WebSocket Hook - Singleton Pattern
 * 
 * IMPORTANTE: Usa una única conexión WebSocket compartida entre todos los componentes.
 * Esto evita múltiples conexiones y el ciclo de reconexión infinito.
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

  private constructor() {}

  static getInstance(): WebSocketManager {
    if (!WebSocketManager.instance) {
      WebSocketManager.instance = new WebSocketManager();
    }
    return WebSocketManager.instance;
  }

  connect(url: string, debugMode: boolean = false) {
    // Si ya hay una conexión con la misma URL, no hacer nada
    if (this.ws$ && this.url === url) {
      if (debugMode) console.log('🔄 [RxWS-Singleton] Already connected, reusing connection');
      return;
    }

    this.url = url;
    this.debug = debugMode;

    if (this.ws$) {
      if (this.debug) console.log('🔌 [RxWS-Singleton] Closing existing connection');
      this.ws$.complete();
    }

    if (this.debug) console.log('🚀 [RxWS-Singleton] Creating new connection to:', url);

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
          if (this.debug) console.log('📥 [RxWS-Singleton] Message received:', message.type);
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
    if (this.ws$ && this.isConnected.value) {
      this.ws$.next(message);
      if (this.debug) console.log('📤 [RxWS-Singleton] Message sent:', message);
    } else {
      if (this.debug) console.warn('⚠️  [RxWS-Singleton] Cannot send, not connected');
    }
  }

  subscribe(listName: string) {
    this.subscribers.add(listName);
    if (this.debug) console.log(`📋 [RxWS-Singleton] Subscribed to list: ${listName} (total: ${this.subscribers.size})`);
    this.send({ action: 'subscribe_list', list: listName });
  }

  unsubscribe(listName: string) {
    this.subscribers.delete(listName);
    if (this.debug) console.log(`📋 [RxWS-Singleton] Unsubscribed from list: ${listName} (total: ${this.subscribers.size})`);
    this.send({ action: 'unsubscribe_list', list: listName });
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected.value) {
        this.send({ action: 'ping' });
        if (this.debug) console.log('💓 [RxWS-Singleton] Heartbeat sent');
      }
    }, 30000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  disconnect() {
    if (this.debug) console.log('🔌 [RxWS-Singleton] Disconnecting...');
    this.stopHeartbeat();
    this.ws$?.complete();
    this.ws$ = null;
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
