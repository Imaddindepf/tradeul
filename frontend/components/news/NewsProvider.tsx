'use client';

/**
 * NewsProvider - Componente global de ingesta de noticias
 * 
 * Arquitectura Enterprise:
 * - Se monta UNA VEZ en el layout global (nunca se desmonta)
 * - Suscribe al WebSocket y procesa TODOS los mensajes de noticias
 * - Alimenta el NewsStore global
 * - Maneja Squawk (TTS) y Catalyst Alerts
 * 
 * Separación de responsabilidades:
 * - NewsProvider: INGESTA (recibe, procesa, almacena)
 * - NewsContent: PRESENTACIÓN (consume, filtra, muestra)
 */

import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useWebSocket } from '@/contexts/AuthWebSocketContext';
import { useSquawk } from '@/contexts/SquawkContext';
import { useCatalystDetector } from '@/hooks/useCatalystDetector';
import { useNewsStore, NewsArticle } from '@/stores/useNewsStore';
import { useNewsTickersStore } from '@/stores/useNewsTickersStore';

import { decodeHtmlEntities } from '@/lib/html-utils';

interface NewsProviderProps {
  children?: React.ReactNode;
}

export function NewsProvider({ children }: NewsProviderProps) {
  const { t } = useTranslation();

  // WebSocket (ya autenticado desde AuthWebSocketProvider)
  const ws = useWebSocket();

  // Squawk Service (contexto global)
  const squawk = useSquawk();

  // Catalyst detector
  const { processNews: processCatalystNews } = useCatalystDetector();

  // News Store (acciones estables)
  const addArticle = useNewsStore((state) => state.addArticle);
  const addArticlesBatch = useNewsStore((state) => state.addArticlesBatch);
  const setConnected = useNewsStore((state) => state.setConnected);
  const setSubscribed = useNewsStore((state) => state.setSubscribed);
  const markInitialLoadComplete = useNewsStore((state) => state.markInitialLoadComplete);
  const isPaused = useNewsStore((state) => state.isPaused);

  // News Tickers Store (para intersección scanner+news)
  const addNewsArticleToTickers = useNewsTickersStore((state) => state.addNewsArticle);
  const addNewsArticlesBatchToTickers = useNewsTickersStore((state) => state.addNewsArticlesBatch);

  // Refs para evitar re-ejecuciones innecesarias
  const initialLoadDoneRef = useRef(false);
  const isSubscribedRef = useRef(false);
  const wsSendRef = useRef(ws.send);
  wsSendRef.current = ws.send;

  // ================================================================
  // CARGA INICIAL DE NOTICIAS (una sola vez)
  // ================================================================
  useEffect(() => {
    if (initialLoadDoneRef.current) return;
    initialLoadDoneRef.current = true;

    const fetchInitialNews = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/news/api/v1/news?limit=200`);

        if (!response.ok) {
          console.error('[NewsProvider] Failed to fetch initial news:', response.status);
          return;
        }

        const data = await response.json();

        if (data.results && Array.isArray(data.results)) {
          // Agregar al store principal
          const addedCount = addArticlesBatch(data.results, false);

          // Agregar al store de tickers (para intersección scanner+news)
          const tickerArticles = data.results
            .filter((a: NewsArticle) => a.tickers && a.tickers.length > 0)
            .map((a: NewsArticle) => ({
              id: a.benzinga_id || a.id || '',
              title: a.title,
              author: a.author,
              published: a.published,
              url: a.url,
              tickers: a.tickers || [],
              teaser: a.teaser,
            }));

          if (tickerArticles.length > 0) {
            addNewsArticlesBatchToTickers(tickerArticles);
          }

          markInitialLoadComplete();
        }
      } catch (error) {
        console.error('[NewsProvider] Error fetching initial news:', error);
      }
    };

    fetchInitialNews();
  }, [addArticlesBatch, addNewsArticlesBatchToTickers, markInitialLoadComplete]);

  // ================================================================
  // SINCRONIZAR ESTADO DE CONEXIÓN
  // ================================================================
  useEffect(() => {
    setConnected(ws.isConnected);
  }, [ws.isConnected, setConnected]);

  // ================================================================
  // SUSCRIPCIÓN AL WEBSOCKET (solo cuando cambia isConnected)
  // Sin dependencias de store para evitar re-renders que disparen cleanup
  // ================================================================
  useEffect(() => {
    if (!ws.isConnected) {
      if (isSubscribedRef.current) {
        isSubscribedRef.current = false;
        setSubscribed(false);
      }
      return;
    }

    // Solo suscribir si no estamos ya suscritos
    if (isSubscribedRef.current) {
      return;
    }

    // Suscribir a noticias usando el método dedicado del SharedWorker
    ws.subscribeNews();
    isSubscribedRef.current = true;
    setSubscribed(true);

    // NO retornamos cleanup aquí - la desuscripción solo ocurre cuando
    // isConnected cambia a false (manejado arriba)
  }, [ws.isConnected, ws.subscribeNews]); // Añadir ws.subscribeNews a dependencias

  // Cleanup al desmontar el componente
  useEffect(() => {
    return () => {
      if (isSubscribedRef.current) {
        ws.unsubscribeNews();
        isSubscribedRef.current = false;
      }
    };
  }, [ws.unsubscribeNews]);

  // ================================================================
  // PROCESAR MENSAJES DE NOTICIAS
  // ================================================================
  useEffect(() => {
    const subscription = ws.messages$.subscribe((message: any) => {
      // Filtrar solo mensajes de noticias
      if (message.type !== 'news' && message.type !== 'benzinga_news') {
        return;
      }

      if (!message.article) {
        return;
      }

      const article = message.article as NewsArticle;

      // Añadir precios capturados si vienen en el mensaje
      if (message.ticker_prices) {
        try {
          article.tickerPrices = typeof message.ticker_prices === 'string'
            ? JSON.parse(message.ticker_prices)
            : message.ticker_prices;
        } catch (e) {
          // Ignorar si no se puede parsear
        }
      }

      // Agregar al store (el store maneja deduplicación y pausa)
      const wasAdded = addArticle(article);

      if (!wasAdded) {
        // Artículo duplicado, ignorar
        return;
      }

      // Agregar al store de tickers (para intersección scanner+news)
      if (article.tickers && article.tickers.length > 0) {
        addNewsArticleToTickers({
          id: article.benzinga_id || article.id || '',
          title: article.title,
          author: article.author,
          published: article.published,
          url: article.url,
          tickers: article.tickers,
          teaser: article.teaser,
        });
      }

      // Procesar Catalyst Alerts
      if (message.catalyst_metrics) {
        processCatalystNews({
          ...article,
          catalyst_metrics: typeof message.catalyst_metrics === 'string'
            ? JSON.parse(message.catalyst_metrics)
            : message.catalyst_metrics,
        });
      }

      // Squawk (solo si no está pausado)
      if (!isPaused && squawk.isEnabled) {
        const ticker = article.tickers?.[0] || '';
        const decodedTitle = decodeHtmlEntities(article.title);
        const squawkText = ticker
          ? t('news.newsFor', { ticker }) + '. ' + decodedTitle
          : t('news.title') + '. ' + decodedTitle;
        squawk.speak(squawkText);
      }
    });

    return () => subscription.unsubscribe();
  }, [
    ws.messages$,
    addArticle,
    addNewsArticleToTickers,
    processCatalystNews,
    squawk,
    isPaused,
    t
  ]);

  // El provider no renderiza nada visible, solo procesa
  return <>{children}</>;
}

export default NewsProvider;

