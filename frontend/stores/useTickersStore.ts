/**
 * Zustand Store - Global State Management para Tickers
 * 
 * Ventajas:
 * - Estado centralizado compartido entre componentes
 * - Actualizaciones optimizadas (solo re-render lo necesario)
 * - DevTools integration
 * - Persistencia opcional
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { Ticker } from '@/lib/types';

// ============================================================================
// TYPES
// ============================================================================

export interface TickersList {
  sequence: number;
  tickers: Map<string, Ticker>;
  order: string[]; // Array de símbolos ordenados por rank
  lastUpdate: Date | null;
}

interface TickersState {
  // Estado por lista (ej: "gappers_up", "momentum_up")
  lists: Map<string, TickersList>;
  
  // WebSocket connection state
  isConnected: boolean;
  connectionId: string | null;
  
  // Stats
  stats: {
    totalLists: number;
    totalTickers: number;
    messagesReceived: number;
    lastMessageTime: Date | null;
  };
}

interface TickersActions {
  // List management
  initializeList: (listName: string, snapshot: any) => void;
  
  // Ticker operations
  addTicker: (listName: string, symbol: string, ticker: Ticker) => void;
  updateTicker: (listName: string, symbol: string, updates: Partial<Ticker>) => void;
  removeTicker: (listName: string, symbol: string) => void;
  rerankTicker: (listName: string, symbol: string, oldRank: number, newRank: number) => void;
  
  // Batch operations (optimizado para deltas)
  applyDeltas: (listName: string, deltas: any[], sequence: number) => void;
  
  // Batch aggregate updates (optimizado para precio/volumen)
  updateAggregates: (updates: Map<string, any>) => void;
  
  // List operations
  clearList: (listName: string) => void;
  updateSequence: (listName: string, sequence: number) => void;
  
  // Connection state
  setConnected: (connected: boolean, connectionId?: string) => void;
  
  // Getters (selectors optimizados)
  getList: (listName: string) => TickersList | undefined;
  getTicker: (listName: string, symbol: string) => Ticker | undefined;
  getOrderedTickers: (listName: string) => Ticker[];
  
  // Reset
  reset: () => void;
}

// ============================================================================
// INITIAL STATE
// ============================================================================

const initialState: TickersState = {
  lists: new Map(),
  isConnected: false,
  connectionId: null,
  stats: {
    totalLists: 0,
    totalTickers: 0,
    messagesReceived: 0,
    lastMessageTime: null,
  },
};

// ============================================================================
// STORE
// ============================================================================

export const useTickersStore = create<TickersState & TickersActions>()(
  devtools(
    (set, get) => ({
      ...initialState,

      // ============================================================
      // INITIALIZE LIST (from snapshot)
      // ============================================================
      initializeList: (listName, snapshot) => {
        const tickers = new Map<string, Ticker>();
        const order: string[] = [];

        if (snapshot.rows && Array.isArray(snapshot.rows)) {
          snapshot.rows.forEach((ticker: Ticker, index: number) => {
            ticker.rank = ticker.rank ?? index;
            tickers.set(ticker.symbol, ticker);
            order.push(ticker.symbol);
          });

          // Ordenar por rank
          order.sort((a, b) => {
            const tickerA = tickers.get(a);
            const tickerB = tickers.get(b);
            return (tickerA?.rank ?? 0) - (tickerB?.rank ?? 0);
          });
        }

        set((state) => {
          const newLists = new Map(state.lists);
          newLists.set(listName, {
            sequence: snapshot.sequence || 0,
            tickers,
            order,
            lastUpdate: new Date(),
          });

          return {
            lists: newLists,
            stats: {
              ...state.stats,
              totalLists: newLists.size,
              totalTickers: Array.from(newLists.values()).reduce(
                (sum, list) => sum + list.tickers.size,
                0
              ),
              messagesReceived: state.stats.messagesReceived + 1,
              lastMessageTime: new Date(),
            },
          };
        }, false, 'initializeList');
      },

      // ============================================================
      // SINGLE TICKER OPERATIONS
      // ============================================================
      addTicker: (listName, symbol, ticker) => {
        set((state) => {
          const list = state.lists.get(listName);
          if (!list) return state;

          const newTickers = new Map(list.tickers);
          newTickers.set(symbol, ticker);

          const newOrder = [...list.order];
          if (!newOrder.includes(symbol)) {
            newOrder.push(symbol);
            // Re-sort by rank
            newOrder.sort((a, b) => {
              const tickerA = newTickers.get(a);
              const tickerB = newTickers.get(b);
              return (tickerA?.rank ?? 0) - (tickerB?.rank ?? 0);
            });
          }

          const newLists = new Map(state.lists);
          newLists.set(listName, {
            ...list,
            tickers: newTickers,
            order: newOrder,
            lastUpdate: new Date(),
          });

          return { lists: newLists };
        }, false, 'addTicker');
      },

      updateTicker: (listName, symbol, updates) => {
        set((state) => {
          const list = state.lists.get(listName);
          if (!list) return state;

          const ticker = list.tickers.get(symbol);
          if (!ticker) return state;

          const newTickers = new Map(list.tickers);
          newTickers.set(symbol, { ...ticker, ...updates });

          const newLists = new Map(state.lists);
          newLists.set(listName, {
            ...list,
            tickers: newTickers,
            lastUpdate: new Date(),
          });

          return { lists: newLists };
        }, false, 'updateTicker');
      },

      removeTicker: (listName, symbol) => {
        set((state) => {
          const list = state.lists.get(listName);
          if (!list) return state;

          const newTickers = new Map(list.tickers);
          newTickers.delete(symbol);

          const newOrder = list.order.filter((s) => s !== symbol);

          const newLists = new Map(state.lists);
          newLists.set(listName, {
            ...list,
            tickers: newTickers,
            order: newOrder,
            lastUpdate: new Date(),
          });

          return { lists: newLists };
        }, false, 'removeTicker');
      },

      rerankTicker: (listName, symbol, oldRank, newRank) => {
        set((state) => {
          const list = state.lists.get(listName);
          if (!list) return state;

          const ticker = list.tickers.get(symbol);
          if (!ticker) return state;

          const newTickers = new Map(list.tickers);
          newTickers.set(symbol, { ...ticker, rank: newRank });

          // Re-sort order
          const newOrder = [...list.order];
          newOrder.sort((a, b) => {
            const tickerA = newTickers.get(a);
            const tickerB = newTickers.get(b);
            return (tickerA?.rank ?? 0) - (tickerB?.rank ?? 0);
          });

          const newLists = new Map(state.lists);
          newLists.set(listName, {
            ...list,
            tickers: newTickers,
            order: newOrder,
            lastUpdate: new Date(),
          });

          return { lists: newLists };
        }, false, 'rerankTicker');
      },

      // ============================================================
      // BATCH OPERATIONS (optimizado)
      // ============================================================
      applyDeltas: (listName, deltas, sequence) => {
        set((state) => {
          const list = state.lists.get(listName);
          if (!list) return state;

          const newTickers = new Map(list.tickers);
          const newOrder = [...list.order];
          let orderChanged = false;

          deltas.forEach((delta: any) => {
            switch (delta.action) {
              case 'add': {
                if (delta.data) {
                  delta.data.rank = delta.rank ?? 0;
                  newTickers.set(delta.symbol, delta.data);
                  if (!newOrder.includes(delta.symbol)) {
                    newOrder.push(delta.symbol);
                    orderChanged = true;
                  }
                }
                break;
              }
              case 'remove': {
                newTickers.delete(delta.symbol);
                const index = newOrder.indexOf(delta.symbol);
                if (index !== -1) {
                  newOrder.splice(index, 1);
                  orderChanged = true;
                }
                break;
              }
              case 'update': {
                if (delta.data) {
                  const oldTicker = newTickers.get(delta.symbol);
                  if (oldTicker) {
                    // Merge con datos existentes (preservar real-time)
                    newTickers.set(delta.symbol, {
                      ...delta.data,
                      price: oldTicker.price || delta.data.price,
                      volume_today: oldTicker.volume_today || delta.data.volume_today,
                      high: Math.max(oldTicker.high || 0, delta.data.high || 0),
                      low:
                        oldTicker.low && delta.data.low
                          ? Math.min(oldTicker.low, delta.data.low)
                          : oldTicker.low || delta.data.low,
                    });
                  } else {
                    newTickers.set(delta.symbol, delta.data);
                  }
                }
                break;
              }
              case 'rerank': {
                const ticker = newTickers.get(delta.symbol);
                if (ticker && delta.new_rank !== undefined) {
                  newTickers.set(delta.symbol, { ...ticker, rank: delta.new_rank });
                  orderChanged = true;
                }
                break;
              }
            }
          });

          // Re-sort solo si hubo cambios de orden
          if (orderChanged) {
            newOrder.sort((a, b) => {
              const tickerA = newTickers.get(a);
              const tickerB = newTickers.get(b);
              return (tickerA?.rank ?? 0) - (tickerB?.rank ?? 0);
            });
          }

          const newLists = new Map(state.lists);
          newLists.set(listName, {
            sequence,
            tickers: newTickers,
            order: newOrder,
            lastUpdate: new Date(),
          });

          return {
            lists: newLists,
            stats: {
              ...state.stats,
              messagesReceived: state.stats.messagesReceived + deltas.length,
              lastMessageTime: new Date(),
            },
          };
        }, false, 'applyDeltas');
      },

      // ============================================================
      // BATCH AGGREGATE UPDATES (precio/volumen en tiempo real)
      // ============================================================
      updateAggregates: (updates) => {
        set((state) => {
          const newLists = new Map(state.lists);
          let updated = false;

          // Iterar todas las listas y actualizar tickers que coincidan
          newLists.forEach((list, listName) => {
            const newTickers = new Map(list.tickers);

            updates.forEach((aggregateData, symbol) => {
              const ticker = newTickers.get(symbol);
              if (!ticker) return; // Ticker no está en esta lista

              const newPrice = parseFloat(aggregateData.c);
              const newVolume = parseInt(aggregateData.av, 10);

              // Recalcular change_percent si tenemos prev_close
              let newChangePercent = ticker.change_percent;
              if (ticker.prev_close && !isNaN(newPrice)) {
                newChangePercent =
                  ((newPrice - ticker.prev_close) / ticker.prev_close) * 100;
              }

              newTickers.set(symbol, {
                ...ticker,
                price: newPrice,
                volume_today: newVolume,
                change_percent: newChangePercent,
                high: Math.max(parseFloat(aggregateData.h) || 0, ticker.high || 0),
                low: ticker.low
                  ? Math.min(parseFloat(aggregateData.l) || 0, ticker.low)
                  : parseFloat(aggregateData.l),
              });

              updated = true;
            });

            if (updated) {
              newLists.set(listName, {
                ...list,
                tickers: newTickers,
                lastUpdate: new Date(),
              });
            }
          });

          return updated ? { lists: newLists } : state;
        }, false, 'updateAggregates');
      },

      // ============================================================
      // LIST OPERATIONS
      // ============================================================
      clearList: (listName) => {
        set((state) => {
          const newLists = new Map(state.lists);
          newLists.delete(listName);

          return {
            lists: newLists,
            stats: {
              ...state.stats,
              totalLists: newLists.size,
              totalTickers: Array.from(newLists.values()).reduce(
                (sum, list) => sum + list.tickers.size,
                0
              ),
            },
          };
        }, false, 'clearList');
      },

      updateSequence: (listName, sequence) => {
        set((state) => {
          const list = state.lists.get(listName);
          if (!list) return state;

          const newLists = new Map(state.lists);
          newLists.set(listName, { ...list, sequence });

          return { lists: newLists };
        }, false, 'updateSequence');
      },

      // ============================================================
      // CONNECTION STATE
      // ============================================================
      setConnected: (connected, connectionId) => {
        set(
          {
            isConnected: connected,
            connectionId: connectionId || null,
          },
          false,
          'setConnected'
        );
      },

      // ============================================================
      // SELECTORS (getters optimizados)
      // ============================================================
      getList: (listName) => {
        return get().lists.get(listName);
      },

      getTicker: (listName, symbol) => {
        const list = get().lists.get(listName);
        return list?.tickers.get(symbol);
      },

      getOrderedTickers: (listName) => {
        const list = get().lists.get(listName);
        if (!list) return [];

        return list.order.map((symbol) => list.tickers.get(symbol)!).filter(Boolean);
      },

      // ============================================================
      // RESET
      // ============================================================
      reset: () => {
        set(initialState, false, 'reset');
      },
    }),
    {
      name: 'tickers-store',
      enabled: process.env.NODE_ENV === 'development',
    }
  )
);

// ============================================================================
// SELECTORS (para evitar re-renders innecesarios)
// ============================================================================

// Selector para una lista específica
export const selectList = (listName: string) => (state: TickersState & TickersActions) =>
  state.lists.get(listName);

// Selector para tickers ordenados de una lista
export const selectOrderedTickers = (listName: string) => (state: TickersState & TickersActions) => {
  const list = state.lists.get(listName);
  if (!list) return [];
  return list.order.map((symbol) => list.tickers.get(symbol)!).filter(Boolean);
};

// Selector para un ticker específico
export const selectTicker = (listName: string, symbol: string) => (state: TickersState & TickersActions) =>
  state.lists.get(listName)?.tickers.get(symbol);

// Selector para conexión WebSocket
export const selectConnection = (state: TickersState & TickersActions) => ({
  isConnected: state.isConnected,
  connectionId: state.connectionId,
});

// Selector para stats
export const selectStats = (state: TickersState & TickersActions) => state.stats;

// ============================================================================
// OPTIMIZED HOOKS CON SHALLOW EQUALITY
// ============================================================================

import { shallow } from 'zustand/shallow';

/**
 * Hook optimizado para una lista completa
 * Solo re-renderiza si el ARRAY de tickers cambia (shallow comparison)
 */
export function useOrderedTickersOptimized(listName: string) {
  return useTickersStore(selectOrderedTickers(listName), shallow);
}

/**
 * Hook optimizado para un ticker específico
 * Solo re-renderiza si ESE ticker específico cambia
 */
export function useTickerOptimized(listName: string, symbol: string) {
  return useTickersStore(selectTicker(listName, symbol), shallow);
}

/**
 * Hook optimizado para conexión
 * Solo re-renderiza si cambia isConnected o connectionId
 */
export function useConnectionOptimized() {
  return useTickersStore(selectConnection, shallow);
}

/**
 * Hook optimizado para stats
 * Solo re-renderiza si cambian las estadísticas
 */
export function useStatsOptimized() {
  return useTickersStore(selectStats, shallow);
}

