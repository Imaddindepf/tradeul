'use client';

import { useEffect, useRef, useCallback, useState } from 'react';

const DILUTION_WS_URL = process.env.NEXT_PUBLIC_DILUTION_WS_URL || 'wss://dilution.tradeul.com/ws/jobs';

interface JobCompleteData {
  type: 'job_complete';
  ticker: string;
  data: {
    status: 'completed' | 'failed';
    has_warrants?: boolean;
    has_atm?: boolean;
    has_shelf?: boolean;
    duration_seconds?: number;
    error?: string;
  };
  timestamp: string;
}

interface UseDilutionJobNotificationsOptions {
  /**
   * Tickers a los que suscribirse
   */
  tickers: string[];

  /**
   * Callback cuando un job completa
   */
  onJobComplete?: (ticker: string, data: JobCompleteData['data']) => void;

  /**
   * Callback cuando un job falla
   */
  onJobFailed?: (ticker: string, error: string) => void;

  /**
   * Habilitar/deshabilitar el WebSocket
   */
  enabled?: boolean;
}

interface JobNotificationState {
  isConnected: boolean;
  subscribedTickers: Set<string>;
  lastNotification: JobCompleteData | null;
}

/**
 * Hook para recibir notificaciones en tiempo real cuando los jobs de
 * scraping de dilution completan.
 * 
 * @example
 * ```tsx
 * const { isConnected, enqueueJob } = useDilutionJobNotifications({
 *   tickers: [currentTicker],
 *   onJobComplete: (ticker, data) => {
 *     toast.success(`${ticker} analysis ready!`);
 *     refetchData();
 *   }
 * });
 * ```
 */
export function useDilutionJobNotifications({
  tickers,
  onJobComplete,
  onJobFailed,
  enabled = true,
}: UseDilutionJobNotificationsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const subscribedTickersRef = useRef<Set<string>>(new Set());
  const isConnectingRef = useRef(false);

  // Deduplicación: evitar procesar el mismo mensaje múltiples veces
  const processedJobsRef = useRef<Map<string, number>>(new Map());
  const DEDUP_WINDOW_MS = 10000; // Ignorar mensajes duplicados en 10 segundos

  // Usar refs para callbacks para evitar recrear connect()
  const onJobCompleteRef = useRef(onJobComplete);
  const onJobFailedRef = useRef(onJobFailed);

  // Actualizar refs cuando cambien los callbacks
  useEffect(() => {
    onJobCompleteRef.current = onJobComplete;
  }, [onJobComplete]);

  useEffect(() => {
    onJobFailedRef.current = onJobFailed;
  }, [onJobFailed]);

  const [state, setState] = useState<JobNotificationState>({
    isConnected: false,
    subscribedTickers: new Set(),
    lastNotification: null,
  });

  // Enviar mensaje al WebSocket
  const sendMessage = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Suscribirse a un ticker
  const subscribe = useCallback((ticker: string) => {
    const upperTicker = ticker.toUpperCase();
    sendMessage({ action: 'subscribe', ticker: upperTicker });
    subscribedTickersRef.current.add(upperTicker);
    setState(prev => ({
      ...prev,
      subscribedTickers: new Set(subscribedTickersRef.current)
    }));
  }, [sendMessage]);

  // Cancelar suscripción de un ticker
  const unsubscribe = useCallback((ticker: string) => {
    const upperTicker = ticker.toUpperCase();
    sendMessage({ action: 'unsubscribe', ticker: upperTicker });
    subscribedTickersRef.current.delete(upperTicker);
    setState(prev => ({
      ...prev,
      subscribedTickers: new Set(subscribedTickersRef.current)
    }));
  }, [sendMessage]);

  // Ref para evitar encolar múltiples jobs del mismo ticker
  const pendingEnqueuesRef = useRef<Set<string>>(new Set());

  // Encolar un job de scraping
  const enqueueJob = useCallback(async (
    ticker: string,
    options?: { priority?: boolean; forceRefresh?: boolean }
  ) => {
    const upperTicker = ticker.toUpperCase();
    const apiUrl = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'https://dilution.tradeul.com';

    // Evitar encolar múltiples veces el mismo ticker
    if (pendingEnqueuesRef.current.has(upperTicker)) {
      return { status: 'already_pending', ticker: upperTicker };
    }

    pendingEnqueuesRef.current.add(upperTicker);

    try {
      const params = new URLSearchParams();
      if (options?.priority) params.set('priority', 'true');
      if (options?.forceRefresh) params.set('force_refresh', 'true');

      const response = await fetch(
        `${apiUrl}/api/sec-dilution/${upperTicker}/jobs/scrape?${params}`,
        { method: 'POST' }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      // Suscribirse automáticamente para recibir notificación cuando complete
      subscribe(upperTicker);

      // Limpiar el pending después de 30 segundos para permitir re-encolar si es necesario
      setTimeout(() => {
        pendingEnqueuesRef.current.delete(upperTicker);
      }, 30000);

      return data;
    } catch (error) {
      pendingEnqueuesRef.current.delete(upperTicker);
      console.error('[DilutionJob] Failed to enqueue job:', error);
      throw error;
    }
  }, [subscribe]);

  // Obtener estado de un job
  const getJobStatus = useCallback(async (ticker: string) => {
    const apiUrl = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'https://dilution.tradeul.com';

    try {
      const response = await fetch(
        `${apiUrl}/api/sec-dilution/${ticker}/jobs/status`
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('[DilutionJob] Failed to get job status:', error);
      return null;
    }
  }, []);

  // Conectar WebSocket - NO depende de props que cambian
  const connect = useCallback(() => {
    // Evitar múltiples conexiones simultáneas
    if (isConnectingRef.current) {
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    isConnectingRef.current = true;

    try {
      const ws = new WebSocket(DILUTION_WS_URL);

      ws.onopen = () => {
        isConnectingRef.current = false;
        setState(prev => ({ ...prev, isConnected: true }));

        // Re-suscribirse a tickers existentes
        subscribedTickersRef.current.forEach(ticker => {
          ws.send(JSON.stringify({ action: 'subscribe', ticker }));
        });
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'job_complete') {
            const ticker = data.ticker?.toUpperCase();
            const now = Date.now();

            // Deduplicación: ignorar si ya procesamos este ticker recientemente
            const lastProcessed = processedJobsRef.current.get(ticker);
            if (lastProcessed && (now - lastProcessed) < DEDUP_WINDOW_MS) {
              return;
            }

            // Marcar como procesado
            processedJobsRef.current.set(ticker, now);

            // Limpiar entradas antiguas (más de 60 segundos)
            processedJobsRef.current.forEach((time, key) => {
              if (now - time > 60000) {
                processedJobsRef.current.delete(key);
              }
            });

            setState(prev => ({ ...prev, lastNotification: data }));

            if (data.data.status === 'completed') {
              onJobCompleteRef.current?.(ticker, data.data);
            } else if (data.data.status === 'failed') {
              onJobFailedRef.current?.(ticker, data.data.error || 'Unknown error');
            }
          }
        } catch (e) {
          console.error('[DilutionJob] Failed to parse message:', e);
        }
      };

      ws.onclose = (event) => {
        isConnectingRef.current = false;
        setState(prev => ({ ...prev, isConnected: false }));
        wsRef.current = null;

        // Solo reconectar si no fue un cierre intencional (código 1000)
        if (event.code !== 1000) {
          reconnectTimeoutRef.current = setTimeout(connect, 5000);
        }
      };

      ws.onerror = (error) => {
        console.error('[DilutionJob] WebSocket error:', error);
        isConnectingRef.current = false;
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('[DilutionJob] Failed to connect:', error);
      isConnectingRef.current = false;
    }
  }, []); // Sin dependencias - usa refs para todo

  // Efecto para conectar/desconectar - solo cuando cambia enabled
  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (wsRef.current) {
        // Cerrar con código 1000 para indicar cierre intencional
        wsRef.current.close(1000, 'Component unmounting');
        wsRef.current = null;
      }
      isConnectingRef.current = false;
    };
  }, [enabled, connect]);

  // Efecto para manejar cambios en tickers
  useEffect(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    // Suscribirse a nuevos tickers
    tickers.forEach(ticker => {
      const upperTicker = ticker.toUpperCase();
      if (!subscribedTickersRef.current.has(upperTicker)) {
        subscribe(upperTicker);
      }
    });

    // Cancelar suscripción de tickers removidos
    const currentTickers = new Set(tickers.map(t => t.toUpperCase()));
    subscribedTickersRef.current.forEach(ticker => {
      if (!currentTickers.has(ticker)) {
        unsubscribe(ticker);
      }
    });
  }, [tickers, subscribe, unsubscribe]);

  return {
    ...state,
    subscribe,
    unsubscribe,
    enqueueJob,
    getJobStatus,
  };
}

export default useDilutionJobNotifications;
