/**
 * NewsStore - Store global de noticias
 * 
 * Arquitectura Enterprise:
 * - Estado centralizado de TODAS las noticias
 * - Persistente durante toda la sesión (no depende de componentes)
 * - Deduplicación automática
 * - Buffer de pausa
 * - Integración con WebSocket via NewsProvider
 * 
 * El componente NewsContent SOLO consume este store, no tiene estado propio de noticias.
 */

import { create } from 'zustand';
import { devtools, subscribeWithSelector } from 'zustand/middleware';

// ============================================================================
// TYPES
// ============================================================================

export interface NewsArticle {
  id?: string;
  benzinga_id?: number;
  title: string;
  author: string;
  published: string;
  url: string;
  tickers?: string[];
  channels?: string[];
  teaser?: string;
  body?: string;
  isLive?: boolean;
  receivedAt?: number; // Timestamp de cuando se recibió
  tickerPrices?: Record<string, number>; // Precios capturados cuando llegó la noticia
}

interface NewsState {
  // Noticias
  articles: NewsArticle[];
  
  // Deduplicación
  seenIds: Set<string | number>;
  
  // Estado de conexión
  isConnected: boolean;
  isSubscribed: boolean;
  
  // Control de pausa
  isPaused: boolean;
  pausedBuffer: NewsArticle[];
  
  // Estadísticas
  stats: {
    totalReceived: number;
    liveCount: number;
    lastUpdate: Date | null;
    initialLoadComplete: boolean;
  };
}

interface NewsActions {
  // Agregar noticias
  addArticle: (article: NewsArticle) => boolean; // Retorna true si se agregó (no duplicado)
  addArticlesBatch: (articles: NewsArticle[], markAsLive?: boolean) => number; // Retorna cantidad agregada
  
  // Control de pausa
  setPaused: (paused: boolean) => void;
  resumeWithBuffer: () => void;
  
  // Estado de conexión
  setConnected: (connected: boolean) => void;
  setSubscribed: (subscribed: boolean) => void;
  
  // Utilidades
  markInitialLoadComplete: () => void;
  getArticleById: (id: string | number) => NewsArticle | undefined;
  hasSeenId: (id: string | number) => boolean;
  
  // Reset
  reset: () => void;
}

// ============================================================================
// INITIAL STATE
// ============================================================================

const initialState: NewsState = {
  articles: [],
  seenIds: new Set(),
  isConnected: false,
  isSubscribed: false,
  isPaused: false,
  pausedBuffer: [],
  stats: {
    totalReceived: 0,
    liveCount: 0,
    lastUpdate: null,
    initialLoadComplete: false,
  },
};

// ============================================================================
// STORE
// ============================================================================

export const useNewsStore = create<NewsState & NewsActions>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      ...initialState,

      // ============================================================
      // ADD SINGLE ARTICLE (desde WebSocket en tiempo real)
      // ============================================================
      addArticle: (article) => {
        const id = article.benzinga_id || article.id;
        if (!id) return false;
        
        const state = get();
        
        // Verificar duplicado
        if (state.seenIds.has(id)) {
          return false;
        }
        
        const enrichedArticle: NewsArticle = {
          ...article,
          isLive: true,
          receivedAt: Date.now(),
        };
        
        set((state) => {
          const newSeenIds = new Set(state.seenIds);
          newSeenIds.add(id);
          
          // Si está pausado, agregar al buffer
          if (state.isPaused) {
            return {
              seenIds: newSeenIds,
              pausedBuffer: [enrichedArticle, ...state.pausedBuffer],
              stats: {
                ...state.stats,
                totalReceived: state.stats.totalReceived + 1,
              },
            };
          }
          
          // Si no está pausado, agregar directamente
          return {
            articles: [enrichedArticle, ...state.articles],
            seenIds: newSeenIds,
            stats: {
              ...state.stats,
              totalReceived: state.stats.totalReceived + 1,
              liveCount: state.stats.liveCount + 1,
              lastUpdate: new Date(),
            },
          };
        }, false, 'addArticle');
        
        return true;
      },

      // ============================================================
      // ADD BATCH (para carga inicial desde API)
      // ============================================================
      addArticlesBatch: (articles, markAsLive = false) => {
        if (!articles || articles.length === 0) return 0;
        
        let addedCount = 0;
        const now = Date.now();
        
        set((state) => {
          const newSeenIds = new Set(state.seenIds);
          const newArticles: NewsArticle[] = [];
          
          for (const article of articles) {
            const id = article.benzinga_id || article.id;
            if (!id || newSeenIds.has(id)) continue;
            
            newSeenIds.add(id);
            newArticles.push({
              ...article,
              isLive: markAsLive,
              receivedAt: now,
            });
            addedCount++;
          }
          
          if (addedCount === 0) return state;
          
          return {
            articles: [...newArticles, ...state.articles],
            seenIds: newSeenIds,
            stats: {
              ...state.stats,
              totalReceived: state.stats.totalReceived + addedCount,
              lastUpdate: new Date(),
            },
          };
        }, false, 'addArticlesBatch');
        
        return addedCount;
      },

      // ============================================================
      // PAUSE CONTROL
      // ============================================================
      setPaused: (paused) => {
        set({ isPaused: paused }, false, 'setPaused');
      },
      
      resumeWithBuffer: () => {
        set((state) => {
          if (state.pausedBuffer.length === 0) {
            return { isPaused: false };
          }
          
          return {
            articles: [...state.pausedBuffer, ...state.articles],
            pausedBuffer: [],
            isPaused: false,
            stats: {
              ...state.stats,
              liveCount: state.stats.liveCount + state.pausedBuffer.length,
              lastUpdate: new Date(),
            },
          };
        }, false, 'resumeWithBuffer');
      },

      // ============================================================
      // CONNECTION STATE
      // ============================================================
      setConnected: (connected) => {
        set({ isConnected: connected }, false, 'setConnected');
      },
      
      setSubscribed: (subscribed) => {
        set({ isSubscribed: subscribed }, false, 'setSubscribed');
      },

      // ============================================================
      // UTILITIES
      // ============================================================
      markInitialLoadComplete: () => {
        set((state) => ({
          stats: { ...state.stats, initialLoadComplete: true },
        }), false, 'markInitialLoadComplete');
      },
      
      getArticleById: (id) => {
        return get().articles.find(a => 
          (a.benzinga_id && a.benzinga_id === id) || 
          (a.id && a.id === id)
        );
      },
      
      hasSeenId: (id) => {
        return get().seenIds.has(id);
      },

      // ============================================================
      // RESET
      // ============================================================
      reset: () => {
        set(initialState, false, 'reset');
      },
    })),
    {
      name: 'news-store',
      enabled: process.env.NODE_ENV === 'development',
    }
  )
);

// ============================================================================
// SELECTORS (para optimizar re-renders)
// ============================================================================

export const selectArticles = (state: NewsState & NewsActions) => state.articles;
export const selectIsPaused = (state: NewsState & NewsActions) => state.isPaused;
export const selectPausedBuffer = (state: NewsState & NewsActions) => state.pausedBuffer;
export const selectIsConnected = (state: NewsState & NewsActions) => state.isConnected;
export const selectStats = (state: NewsState & NewsActions) => state.stats;

// Selector para filtrar por ticker (memoizado internamente por Zustand)
export const useFilteredArticles = (tickerFilter: string) => {
  return useNewsStore((state) => {
    if (!tickerFilter) return state.articles;
    const upperFilter = tickerFilter.toUpperCase();
    return state.articles.filter(article =>
      article.tickers?.some(t => t.toUpperCase() === upperFilter)
    );
  });
};

// Estadísticas rápidas
export const useLiveCount = () => {
  return useNewsStore((state) => 
    state.articles.filter(a => a.isLive).length
  );
};

