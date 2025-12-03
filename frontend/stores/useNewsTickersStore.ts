/**
 * Zustand Store - Tickers con Noticias
 * 
 * Mantiene un registro de noticias por ticker para:
 * 1. Mostrar la intersección "Tickers en Scanner CON Noticias"
 * 2. Mostrar las noticias de un ticker en una mini ventana
 * 
 * TTL Strategy:
 * - Persiste durante TODA la sesión de trading del día
 * - Pre-market (4:00 AM ET) hasta After-hours close (8:00 PM ET)
 * - Reset automático al inicio del nuevo día de trading (4:00 AM ET)
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

// ============================================================================
// TYPES
// ============================================================================

export interface StoredNewsArticle {
  id: string | number;     // benzinga_id o id único
  title: string;
  author: string;
  published: string;       // ISO 8601
  url: string;
  tickers: string[];
  teaser?: string;
}

interface NewsTickerEntry {
  symbol: string;
  newsIds: Set<string>;    // IDs de noticias únicas (para evitar duplicados)
  articles: StoredNewsArticle[];  // Noticias completas para mostrar
  lastNewsAt: number;      // timestamp de última noticia
  tradingDay: string;      // día de trading (YYYY-MM-DD en ET)
}

interface NewsTickersState {
  // Map de tickers con sus noticias
  tickers: Map<string, NewsTickerEntry>;
  
  // Set global de IDs de noticias vistas (para evitar duplicados)
  seenNewsIds: Set<string>;
  
  // Día de trading actual
  currentTradingDay: string;
  
  // Stats
  stats: {
    totalNews: number;
    lastUpdate: Date | null;
    lastCleanup: Date | null;
  };
}

interface NewsTickersActions {
  // Agregar una noticia completa
  addNewsArticle: (article: StoredNewsArticle) => void;
  
  // Agregar batch de noticias (para carga inicial)
  addNewsArticlesBatch: (articles: StoredNewsArticle[]) => void;
  
  // Verificar si un ticker tiene noticias del día
  hasRecentNews: (symbol: string) => boolean;
  
  // Obtener info de un ticker
  getTickerInfo: (symbol: string) => NewsTickerEntry | undefined;
  
  // Obtener noticias de un ticker específico
  getTickerNews: (symbol: string) => StoredNewsArticle[];
  
  // Obtener número de noticias de un ticker
  getNewsCount: (symbol: string) => number;
  
  // Limpiar tickers de días anteriores
  cleanupExpired: () => void;
  
  // Reset completo
  resetForNewSession: () => void;
  
  // Obtener todos los símbolos con noticias del día
  getActiveSymbols: () => string[];
  
  // Obtener Set para búsquedas O(1)
  getActiveSymbolsSet: () => Set<string>;
  
  // Obtener día de trading actual
  getCurrentTradingDay: () => string;
}

// ============================================================================
// HELPER: Calcular día de trading en Eastern Time
// ============================================================================

function getTradingDay(date: Date = new Date()): string {
  try {
    // Solo ejecutar en cliente
    if (typeof window === 'undefined') {
      return date.toISOString().split('T')[0];
    }
    
    const etString = date.toLocaleString('en-US', { 
      timeZone: 'America/New_York',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      hour12: false
    });
    
    const match = etString.match(/(\d{2})\/(\d{2})\/(\d{4}), (\d{2})/);
    if (!match) {
      return date.toISOString().split('T')[0];
    }
    
    const [, month, day, year, hour] = match;
    const hourNum = parseInt(hour, 10);
    
    if (hourNum < 4) {
      const prevDay = new Date(date);
      prevDay.setDate(prevDay.getDate() - 1);
      const prevString = prevDay.toLocaleString('en-US', {
        timeZone: 'America/New_York',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      });
      const prevMatch = prevString.match(/(\d{2})\/(\d{2})\/(\d{4})/);
      if (prevMatch) {
        return `${prevMatch[3]}-${prevMatch[1]}-${prevMatch[2]}`;
      }
    }
    
    return `${year}-${month}-${day}`;
  } catch {
    // Fallback seguro
    return date.toISOString().split('T')[0];
  }
}

// Obtener día de trading de forma segura (lazy)
function getSafeTradingDay(): string {
  if (typeof window === 'undefined') {
    return new Date().toISOString().split('T')[0];
  }
  return getTradingDay();
}

// ============================================================================
// INITIAL STATE (lazy initialization para SSR safety)
// ============================================================================

function getInitialState(): NewsTickersState {
  return {
    tickers: new Map(),
    seenNewsIds: new Set(),
    currentTradingDay: getSafeTradingDay(),
    stats: {
      totalNews: 0,
      lastUpdate: null,
      lastCleanup: null,
    },
  };
}

// ============================================================================
// STORE
// ============================================================================

export const useNewsTickersStore = create<NewsTickersState & NewsTickersActions>()(
  devtools(
    (set, get) => ({
      ...getInitialState(),

      // ============================================================
      // ADD NEWS ARTICLE (desde WebSocket en tiempo real)
      // ============================================================
      addNewsArticle: (article) => {
        if (!article || !article.tickers || article.tickers.length === 0) return;
        
        const newsId = String(article.id);
        const now = Date.now();
        const tradingDay = getTradingDay();
        
        set((state) => {
          // Verificar si ya procesamos esta noticia
          if (state.seenNewsIds.has(newsId)) {
            return state; // Ya la vimos, no hacer nada
          }
          
          // Verificar si cambió el día de trading
          let newTickers = new Map(state.tickers);
          let newSeenIds = new Set(state.seenNewsIds);
          let newTradingDay = state.currentTradingDay;
          
          if (tradingDay !== state.currentTradingDay) {
            newTickers = new Map();
            newSeenIds = new Set();
            newTradingDay = tradingDay;
          }
          
          // Marcar noticia como vista
          newSeenIds.add(newsId);
          
          // Agregar a cada ticker mencionado
          article.tickers.forEach((symbol) => {
            if (!symbol || typeof symbol !== 'string') return;
            
            const upperSymbol = symbol.toUpperCase().trim();
            if (!upperSymbol) return;
            
            const existing = newTickers.get(upperSymbol);
            
            if (existing) {
              // Verificar que no tengamos ya esta noticia para este ticker
              if (!existing.newsIds.has(newsId)) {
                const newNewsIds = new Set(existing.newsIds);
                newNewsIds.add(newsId);
                
                newTickers.set(upperSymbol, {
                  ...existing,
                  newsIds: newNewsIds,
                  articles: [article, ...existing.articles].slice(0, 50), // Max 50 noticias por ticker
                  lastNewsAt: now,
                });
              }
            } else {
              newTickers.set(upperSymbol, {
                symbol: upperSymbol,
                newsIds: new Set([newsId]),
                articles: [article],
                lastNewsAt: now,
                tradingDay,
              });
            }
          });

          return {
            tickers: newTickers,
            seenNewsIds: newSeenIds,
            currentTradingDay: newTradingDay,
            stats: {
              ...state.stats,
              totalNews: state.stats.totalNews + 1,
              lastUpdate: new Date(),
            },
          };
        }, false, 'addNewsArticle');
      },

      // ============================================================
      // ADD BATCH (para carga inicial)
      // ============================================================
      addNewsArticlesBatch: (articles) => {
        if (!articles || articles.length === 0) return;

        const now = Date.now();
        const currentTradingDay = getTradingDay();
        
        set((state) => {
          let newTickers = new Map(state.tickers);
          let newSeenIds = new Set(state.seenNewsIds);
          let newTradingDay = state.currentTradingDay;
          let addedCount = 0;
          
          if (currentTradingDay !== state.currentTradingDay) {
            newTickers = new Map();
            newSeenIds = new Set();
            newTradingDay = currentTradingDay;
          }
          
          articles.forEach((article) => {
            if (!article || !article.tickers || article.tickers.length === 0) return;
            
            const newsId = String(article.id);
            
            // Verificar si ya procesamos esta noticia
            if (newSeenIds.has(newsId)) return;
            
            // Verificar que sea del día de trading actual
            if (article.published) {
              const articleTradingDay = getTradingDay(new Date(article.published));
              if (articleTradingDay !== currentTradingDay) return;
            }
            
            // Marcar como vista
            newSeenIds.add(newsId);
            addedCount++;
            
            // Agregar a cada ticker
            article.tickers.forEach((symbol) => {
              if (!symbol || typeof symbol !== 'string') return;
              
              const upperSymbol = symbol.toUpperCase().trim();
              if (!upperSymbol) return;
              
              const existing = newTickers.get(upperSymbol);
              
              if (existing) {
                if (!existing.newsIds.has(newsId)) {
                  const newNewsIds = new Set(existing.newsIds);
                  newNewsIds.add(newsId);
                  
                  // Insertar ordenado por fecha
                  const updatedArticles = [...existing.articles, article]
                    .sort((a, b) => new Date(b.published).getTime() - new Date(a.published).getTime())
                    .slice(0, 50);
                  
                  newTickers.set(upperSymbol, {
                    ...existing,
                    newsIds: newNewsIds,
                    articles: updatedArticles,
                    lastNewsAt: Math.max(existing.lastNewsAt, new Date(article.published).getTime()),
                  });
                }
              } else {
                newTickers.set(upperSymbol, {
                  symbol: upperSymbol,
                  newsIds: new Set([newsId]),
                  articles: [article],
                  lastNewsAt: article.published ? new Date(article.published).getTime() : now,
                  tradingDay: currentTradingDay,
                });
              }
            });
          });

          return {
            tickers: newTickers,
            seenNewsIds: newSeenIds,
            currentTradingDay: newTradingDay,
            stats: {
              ...state.stats,
              totalNews: state.stats.totalNews + addedCount,
              lastUpdate: new Date(),
            },
          };
        }, false, 'addNewsArticlesBatch');
      },

      // ============================================================
      // CHECK IF TICKER HAS NEWS
      // ============================================================
      hasRecentNews: (symbol) => {
        const state = get();
        const entry = state.tickers.get(symbol.toUpperCase());
        
        if (!entry) return false;
        
        const currentTradingDay = getTradingDay();
        return entry.tradingDay === currentTradingDay && entry.newsIds.size > 0;
      },

      // ============================================================
      // GET TICKER INFO
      // ============================================================
      getTickerInfo: (symbol) => {
        return get().tickers.get(symbol.toUpperCase());
      },

      // ============================================================
      // GET TICKER NEWS (para la mini ventana)
      // ============================================================
      getTickerNews: (symbol) => {
        const entry = get().tickers.get(symbol.toUpperCase());
        if (!entry) return [];
        
        const currentTradingDay = getTradingDay();
        if (entry.tradingDay !== currentTradingDay) return [];
        
        return entry.articles;
      },

      // ============================================================
      // GET NEWS COUNT
      // ============================================================
      getNewsCount: (symbol) => {
        const entry = get().tickers.get(symbol.toUpperCase());
        if (!entry) return 0;
        
        const currentTradingDay = getTradingDay();
        if (entry.tradingDay !== currentTradingDay) return 0;
        
        return entry.newsIds.size;
      },

      // ============================================================
      // CLEANUP EXPIRED
      // ============================================================
      cleanupExpired: () => {
        const currentTradingDay = getTradingDay();
        
        set((state) => {
          if (currentTradingDay !== state.currentTradingDay) {
            return {
              tickers: new Map(),
              seenNewsIds: new Set(),
              currentTradingDay,
              stats: {
                ...state.stats,
                totalNews: 0,
                lastCleanup: new Date(),
              },
            };
          }
          
          return {
            stats: {
              ...state.stats,
              lastCleanup: new Date(),
            },
          };
        }, false, 'cleanupExpired');
      },

      // ============================================================
      // RESET FOR NEW SESSION
      // ============================================================
      resetForNewSession: () => {
        set({
          tickers: new Map(),
          seenNewsIds: new Set(),
          currentTradingDay: getTradingDay(),
          stats: {
            totalNews: 0,
            lastUpdate: null,
            lastCleanup: new Date(),
          },
        }, false, 'resetForNewSession');
      },

      // ============================================================
      // GET ACTIVE SYMBOLS
      // ============================================================
      getActiveSymbols: () => {
        const state = get();
        const currentTradingDay = getTradingDay();
        const active: string[] = [];
        
        state.tickers.forEach((entry, symbol) => {
          if (entry.tradingDay === currentTradingDay && entry.newsIds.size > 0) {
            active.push(symbol);
          }
        });
        
        return active;
      },

      // ============================================================
      // GET ACTIVE SYMBOLS SET
      // ============================================================
      getActiveSymbolsSet: () => {
        const state = get();
        const currentTradingDay = getTradingDay();
        const activeSet = new Set<string>();
        
        state.tickers.forEach((entry, symbol) => {
          if (entry.tradingDay === currentTradingDay && entry.newsIds.size > 0) {
            activeSet.add(symbol);
          }
        });
        
        return activeSet;
      },
      
      // ============================================================
      // GET CURRENT TRADING DAY
      // ============================================================
      getCurrentTradingDay: () => {
        return getTradingDay();
      },
    }),
    {
      name: 'news-tickers-store',
      enabled: process.env.NODE_ENV === 'development',
    }
  )
);

// ============================================================================
// SELECTORS
// ============================================================================

export const selectActiveCount = (state: NewsTickersState & NewsTickersActions) => {
  const currentTradingDay = getTradingDay();
  let count = 0;
  state.tickers.forEach((entry) => {
    if (entry.tradingDay === currentTradingDay && entry.newsIds.size > 0) {
      count++;
    }
  });
  return count;
};

export const selectStats = (state: NewsTickersState & NewsTickersActions) => state.stats;

export const selectCurrentTradingDay = (state: NewsTickersState & NewsTickersActions) => 
  state.currentTradingDay;

// ============================================================================
// HOOKS HELPER
// ============================================================================

export function useHasNews(symbol: string): boolean {
  return useNewsTickersStore((state) => {
    const entry = state.tickers.get(symbol.toUpperCase());
    if (!entry) return false;
    const currentTradingDay = getTradingDay();
    return entry.tradingDay === currentTradingDay && entry.newsIds.size > 0;
  });
}

export function useTickerNewsCount(symbol: string): number {
  return useNewsTickersStore((state) => {
    const entry = state.tickers.get(symbol.toUpperCase());
    if (!entry) return 0;
    const currentTradingDay = getTradingDay();
    if (entry.tradingDay !== currentTradingDay) return 0;
    return entry.newsIds.size;
  });
}

export function useTickerNews(symbol: string): StoredNewsArticle[] {
  return useNewsTickersStore((state) => {
    const entry = state.tickers.get(symbol.toUpperCase());
    if (!entry) return [];
    const currentTradingDay = getTradingDay();
    if (entry.tradingDay !== currentTradingDay) return [];
    return entry.articles;
  });
}

export { getTradingDay };
