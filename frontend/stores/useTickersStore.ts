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
  lastUpdate: number | null;
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
    lastMessageTime: number | null;
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
      // IMPORTANTE: Preservar precios en tiempo real de aggregates
      // ============================================================
      initializeList: (listName, snapshot) => {
        const tickers = new Map<string, Ticker>();
        const order: string[] = [];

        // Obtener lista existente para preservar precios en tiempo real
        const existingList = get().lists.get(listName);
        const existingTickers = existingList?.tickers;

        if (snapshot.rows && Array.isArray(snapshot.rows)) {
          snapshot.rows.forEach((ticker: Ticker, index: number) => {
            ticker.rank = ticker.rank ?? index;

            // Preservar precio en tiempo real si el ticker ya existe
            // Los aggregates tienen datos más frescos que los snapshots
            if (existingTickers) {
              const existingTicker = existingTickers.get(ticker.symbol);
              if (existingTicker && existingTicker.price) {
                // Preservar precio, volume_today, high, low del ticker existente
                ticker.price = existingTicker.price;
                ticker.volume_today = existingTicker.volume_today || ticker.volume_today;
                ticker.high = Math.max(existingTicker.high || 0, ticker.high || 0);
                ticker.low = existingTicker.low && ticker.low
                  ? Math.min(existingTicker.low, ticker.low)
                  : existingTicker.low || ticker.low;
                ticker.change_percent = existingTicker.change_percent ?? ticker.change_percent;
              }
            }

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
            lastUpdate: Date.now(),
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
              lastMessageTime: Date.now(),
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
            lastUpdate: Date.now(),
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
            lastUpdate: Date.now(),
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
            lastUpdate: Date.now(),
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
            lastUpdate: Date.now(),
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
            lastUpdate: Date.now(),
          });

          return {
            lists: newLists,
            stats: {
              ...state.stats,
              messagesReceived: state.stats.messagesReceived + deltas.length,
              lastMessageTime: Date.now(),
            },
          };
        }, false, 'applyDeltas');
      },

      // ============================================================
      // BATCH AGGREGATE UPDATES (precio/volumen en tiempo real)
      // Con tracking de dirección para animaciones flash
      // ============================================================
      updateAggregates: (updates) => {
        set((state) => {
          // Structural sharing: only clone Maps for lists with actual changes.
          // Before: new Map() for ALL lists on every call (600 copies/sec).
          // After: only clone lists that contain matching tickers.
          let newLists: Map<string, any> | null = null;
          const now = Date.now();

          state.lists.forEach((list, listName) => {
            let newTickers: Map<string, any> | null = null;

            updates.forEach((aggregateData, symbol) => {
              const ticker = list.tickers.get(symbol);
              if (!ticker) return;

              const newPrice = parseFloat(aggregateData.c);
              const newVolume = parseInt(aggregateData.av, 10);
              const oldPrice = ticker.price || 0;

              // Price flash direction (skip noise < 0.001%)
              let priceFlash: 'up' | 'down' | null = null;
              const priceDiff = Math.abs(newPrice - oldPrice);
              const threshold = oldPrice * 0.00001;

              if (oldPrice > 0 && priceDiff > threshold) {
                priceFlash = newPrice > oldPrice ? 'up' : 'down';
              }

              // Recalculate change_percent from prev_close
              let newChangePercent = ticker.change_percent;
              if (ticker.prev_close && !isNaN(newPrice)) {
                newChangePercent =
                  ((newPrice - ticker.prev_close) / ticker.prev_close) * 100;
              }

              // Real-time VWAP
              const newVwap = parseFloat(aggregateData.vw) || ticker.vwap;
              let newPriceVsVwap = ticker.price_vs_vwap;
              if (newVwap && newVwap > 0 && !isNaN(newPrice)) {
                newPriceVsVwap = ((newPrice - newVwap) / newVwap) * 100;
              }

              // Lazy-clone tickers Map only on first actual change
              if (!newTickers) newTickers = new Map(list.tickers);

              newTickers.set(symbol, {
                ...ticker,
                price: newPrice,
                volume_today: newVolume,
                change_percent: newChangePercent,
                high: Math.max(parseFloat(aggregateData.h) || 0, ticker.high || 0),
                low: ticker.low
                  ? Math.min(parseFloat(aggregateData.l) || 0, ticker.low)
                  : parseFloat(aggregateData.l),
                vwap: newVwap,
                price_vs_vwap: newPriceVsVwap,
                priceFlash,
              });
            });

            // Only clone the list entry if tickers actually changed
            if (newTickers) {
              if (!newLists) newLists = new Map(state.lists);
              newLists.set(listName, {
                ...list,
                tickers: newTickers,
                lastUpdate: now,
              });
            }
          });

          return newLists ? { lists: newLists } : state;
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
      enabled: false,
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

