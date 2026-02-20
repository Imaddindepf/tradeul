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

// Debug solo si está explícitamente habilitado via variable de entorno
// En producción NUNCA se muestran logs de WebSocket
const WS_DEBUG_ENABLED = process.env.NEXT_PUBLIC_WS_DEBUG === 'true';
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
  private allMessagesSubject = new Subject<WebSocketMessage>();
  private tokenRefreshRequestSubject = new Subject<boolean>(); // Para solicitar token nuevo al reconectar

  // Heartbeat timer
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private directWsSub: { unsubscribe: () => void } | null = null;

  private constructor() {
    // Detectar si SharedWorker está disponible
    this.useSharedWorker = typeof SharedWorker !== 'undefined';
  }

  static getInstance(): WebSocketManager {
    if (!WebSocketManager.instance) {
      WebSocketManager.instance = new WebSocketManager();
      // Exponer en window para que otros hooks puedan acceder sin crear nueva conexión
      if (typeof window !== 'undefined') {
        (window as any).__WS_MANAGER__ = WebSocketManager.instance;
      }
    }
    return WebSocketManager.instance;
  }

  connect(url: string, debugMode: boolean = false) {
    // Debug controlado SOLO por variable de entorno (no por parámetro)
    // Esto evita logs en producción aunque alguien pase debug: true
    const effectiveDebug = WS_DEBUG_ENABLED && debugMode;

    // Si ya hay una conexión con la misma URL, no hacer nada
    if ((this.ws$ || this.sharedWorker) && this.url === url) {
      return;
    }

    // Si la URL cambió (ej: se añadió token de auth), reconectar
    if (this.url && this.url !== url) {
      this.disconnect();
    }

    this.url = url;
    this.debug = effectiveDebug;

    // Limpiar conexiones anteriores
    if (this.ws$) {
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

    const wsConfig: WebSocketSubjectConfig<any> = {
      url,
      openObserver: {
        next: () => {
          this.isConnected.next(true);
          this.reconnectAttempt = 0;
          this.startHeartbeat();
        },
      },
      closeObserver: {
        next: () => {
          this.isConnected.next(false);
          this.connectionId.next(null);
          this.stopHeartbeat();
        },
      },
    };

    this.ws$ = webSocket(wsConfig);

    this.directWsSub = this.ws$
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
              break;
          }
        }),
        retryWhen((errors) =>
          errors.pipe(
            tap((error) => {
              this.reconnectAttempt++;
              this.errorsSubject.next(error as Error);
              if (this.debug) {
              }
            }),
            switchMap((_, attempt) => {
              const backoff = Math.min(3000 * Math.pow(2, attempt), 60000);
              return timer(backoff);
            })
          )
        ),
        catchError((error) => {
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
    } else {
    }
  }

  subscribe(listName: string) {
    this.subscribers.add(listName);

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

  /**
   * 📰 Suscribir a News
   */
  subscribeNews() {

    if (this.workerPort) {
      this.workerPort.postMessage({
        action: 'subscribe_news'
      });
    } else {
      this.send({ action: 'subscribe_benzinga_news' });
    }
  }

  /**
   * 📰 Desuscribir de News
   */
  unsubscribeNews() {

    if (this.workerPort) {
      this.workerPort.postMessage({
        action: 'unsubscribe_news'
      });
    } else {
      this.send({ action: 'unsubscribe_benzinga_news' });
    }
  }

  /**
   * 🔐 Actualizar token JWT (para refresh periódico)
   * Actualiza la URL para futuras reconexiones y envía refresh al servidor
   */
  updateToken(newUrl: string, token: string) {
    this.url = newUrl; // Guardar para futuras reconexiones

    if (this.workerPort) {
      this.workerPort.postMessage({
        action: 'update_token',
        url: newUrl,
        token: token
      });
    } else {
      // Sin SharedWorker, enviar directamente
      this.send({ action: 'refresh_token', token });
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


    // SharedWorkers se identifican por URL + nombre
    // Usamos el build timestamp para que cada deploy cree un worker nuevo automáticamente
    const buildVersion = process.env.NEXT_PUBLIC_BUILD_TIMESTAMP || '0';
    this.sharedWorker = new SharedWorker(`/workers/websocket-shared.js?v=${buildVersion}`, {
      name: `tradeul-ws-${buildVersion}`
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
              break;
          }
          break;

        case 'status':
          // Estado de conexión del worker
          this.isConnected.next(msg.isConnected);
          if (this.debug) {
          }
          break;

        case 'log':
          // Logs del worker (solo en debug)
          if (this.debug) {
            const emojiMap: Record<string, string> = { info: 'ℹ️', warn: '⚠️', error: '❌' };
            const emoji = emojiMap[msg.level] || '📝';
          }
          break;

        case 'request_fresh_token':
          // SharedWorker necesita un token nuevo para reconectar
          // Emitir evento para que useAuthWebSocket lo maneje
          this.tokenRefreshRequestSubject.next(true);
          break;
      }
    };

    (this.workerPort as any).onerror = (error: any) => {
      if (this.debug) console.error('❌ [RxWS-SharedWorker] Port error:', error);
      this.errorsSubject.next(new Error('SharedWorker port error'));
    };

    this.workerPort.start();

    // Conectar al WebSocket a través del worker
    this.workerPort.postMessage({
      action: 'connect',
      url: url
    });

  }

  disconnect() {
    this.stopHeartbeat();

    if (this.workerPort) {
      // Desconectar SharedWorker (solo si somos la última tab)
      this.workerPort.postMessage({ action: 'disconnect' });
      this.workerPort = null;
      this.sharedWorker = null;
    }

    if (this.directWsSub) {
      this.directWsSub.unsubscribe();
      this.directWsSub = null;
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
      share()
    );
  }

  // Observable para solicitudes de refresh de token (SharedWorker necesita token nuevo)
  get tokenRefreshRequest$(): Observable<boolean> {
    return this.tokenRefreshRequestSubject.asObservable();
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
  tokenRefreshRequest$: Observable<boolean>; // SharedWorker solicita token nuevo para reconexión
  send: (payload: any) => void;
  subscribeNews: () => void;
  unsubscribeNews: () => void;
  reconnect: () => void;
  updateToken: (newUrl: string, token: string) => void;
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

  const updateToken = useCallback((newUrl: string, token: string) => {
    managerRef.current.updateToken(newUrl, token);
  }, []);

  const subscribeNews = useCallback(() => {
    managerRef.current.subscribeNews();
  }, []);

  const unsubscribeNews = useCallback(() => {
    managerRef.current.unsubscribeNews();
  }, []);

  // Memoizar el objeto retornado para evitar re-renders infinitos
  // Solo cambia cuando isConnected o connectionId cambian
  return useMemo(() => ({
    isConnected,
    connectionId,
    messages$: managerRef.current.messages$,
    snapshots$: managerRef.current.snapshots$,
    deltas$: managerRef.current.deltas$,
    aggregates$: managerRef.current.aggregates$,
    errors$: managerRef.current.errors$,
    tokenRefreshRequest$: managerRef.current.tokenRefreshRequest$,
    send,
    subscribeNews,
    unsubscribeNews,
    reconnect,
    updateToken,
  }), [isConnected, connectionId, send, subscribeNews, unsubscribeNews, reconnect, updateToken]);
}

// ============================================================================
// HELPER HOOK - Para gestionar suscripciones a listas
// ============================================================================

export function useListSubscription(listName: string, debug: boolean = false) {
  const manager = WebSocketManager.getInstance();
  const [isConnected, setIsConnected] = useState(false);
  const effectiveDebug = WS_DEBUG_ENABLED && debug;

  // Track connection state
  useEffect(() => {
    const sub = manager.isConnected$.subscribe(setIsConnected);
    return () => sub.unsubscribe();
  }, [manager]);

  // Subscribe/unsubscribe when connected
  useEffect(() => {
    if (!isConnected) return;

    manager.subscribe(listName);

    return () => {
      manager.unsubscribe(listName);
    };
  }, [listName, isConnected, effectiveDebug]);
}

// ============================================================================
// HELPER HOOK - Para suscribirse a MÚLTIPLES listas a la vez
// ============================================================================

export function useMultiListSubscription(listNames: string[], debug: boolean = false) {
  const manager = WebSocketManager.getInstance();
  const [isConnected, setIsConnected] = useState(false);
  const effectiveDebug = WS_DEBUG_ENABLED && debug;

  // Track connection state
  useEffect(() => {
    const sub = manager.isConnected$.subscribe(setIsConnected);
    return () => sub.unsubscribe();
  }, [manager]);

  // Subscribe/unsubscribe to all lists when connected
  useEffect(() => {
    if (!isConnected || listNames.length === 0) return;


    // Suscribirse a todas las listas
    listNames.forEach(listName => {
      manager.subscribe(listName);
    });

    return () => {
      listNames.forEach(listName => {
        manager.unsubscribe(listName);
      });
    };
  }, [listNames.join(','), isConnected, effectiveDebug]); // eslint-disable-line react-hooks/exhaustive-deps
}
