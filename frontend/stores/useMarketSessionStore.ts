/**
 * Market Session Store
 * 
 * Store global para el estado del mercado.
 * Se actualiza periódicamente y puede ser usado por cualquier componente.
 */

import { create } from 'zustand';
import type { MarketSession } from '@/lib/types';
import { getMarketSession } from '@/lib/api';

// ============================================================================
// TYPES
// ============================================================================

interface MarketSessionState {
  session: MarketSession | null;
  isLoading: boolean;
  error: string | null;
  lastFetch: Date | null;
  
  // Computed helpers
  isMarketOpen: boolean;
  isPreMarket: boolean;
  isPostMarket: boolean;
  isClosed: boolean;
  
  // Actions
  fetchSession: () => Promise<void>;
  setSession: (session: MarketSession) => void;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}

// ============================================================================
// STORE
// ============================================================================

let pollingInterval: NodeJS.Timeout | null = null;

export const useMarketSessionStore = create<MarketSessionState>((set, get) => ({
  session: null,
  isLoading: false,
  error: null,
  lastFetch: null,
  
  // Computed (se actualizan cuando cambia session)
  isMarketOpen: false,
  isPreMarket: false,
  isPostMarket: false,
  isClosed: true,
  
  fetchSession: async () => {
    set({ isLoading: true, error: null });
    
    try {
      const session = await getMarketSession();
      const currentSession = session.current_session;
      
      set({
        session,
        isLoading: false,
        lastFetch: new Date(),
        isMarketOpen: currentSession === 'MARKET_OPEN',
        isPreMarket: currentSession === 'PRE_MARKET',
        isPostMarket: currentSession === 'POST_MARKET',
        isClosed: currentSession === 'CLOSED',
      });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  },
  
  setSession: (session: MarketSession) => {
    const currentSession = session.current_session;
    set({
      session,
      lastFetch: new Date(),
      isMarketOpen: currentSession === 'MARKET_OPEN',
      isPreMarket: currentSession === 'PRE_MARKET',
      isPostMarket: currentSession === 'POST_MARKET',
      isClosed: currentSession === 'CLOSED',
    });
  },
  
  startPolling: (intervalMs = 30000) => {
    // Fetch immediately
    get().fetchSession();
    
    // Clear existing interval
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }
    
    // Start polling
    pollingInterval = setInterval(() => {
      get().fetchSession();
    }, intervalMs);
  },
  
  stopPolling: () => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  },
}));

// ============================================================================
// SELECTORS (para optimizar re-renders)
// ============================================================================

export const selectSession = (state: MarketSessionState) => state.session;
export const selectIsMarketOpen = (state: MarketSessionState) => state.isMarketOpen;
export const selectIsPreMarket = (state: MarketSessionState) => state.isPreMarket;
export const selectIsPostMarket = (state: MarketSessionState) => state.isPostMarket;
export const selectIsClosed = (state: MarketSessionState) => state.isClosed;
export const selectIsExtendedHours = (state: MarketSessionState) => 
  state.isPreMarket || state.isPostMarket;
export const selectIsTrading = (state: MarketSessionState) => 
  state.isMarketOpen || state.isPreMarket || state.isPostMarket;

// Helper para obtener label del estado
export const getSessionLabel = (session: MarketSession | null): string => {
  if (!session) return 'LOADING';
  
  switch (session.current_session) {
    case 'MARKET_OPEN': return 'MARKET OPEN';
    case 'PRE_MARKET': return 'PRE-MARKET';
    case 'POST_MARKET': return 'POST-MARKET';
    case 'CLOSED': return 'CLOSED';
    default: return 'UNKNOWN';
  }
};

// Helper para obtener color del estado
export const getSessionColor = (session: MarketSession | null): string => {
  if (!session) return 'text-slate-400';
  
  switch (session.current_session) {
    case 'MARKET_OPEN': return 'text-green-500';
    case 'PRE_MARKET': return 'text-blue-500';
    case 'POST_MARKET': return 'text-orange-500';
    case 'CLOSED': return 'text-slate-500';
    default: return 'text-slate-400';
  }
};
