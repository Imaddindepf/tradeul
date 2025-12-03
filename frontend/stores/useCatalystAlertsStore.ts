/**
 * Catalyst Alerts Store
 * 
 * Gestiona las alertas de noticias con movimiento explosivo:
 * - Criterios configurables por el usuario
 * - Lista de alertas activas
 * - Estado de activación
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ============================================================================
// Types
// ============================================================================

export interface CatalystMetrics {
  price_at_news: number;
  price_1m_ago: number | null;
  price_5m_ago: number | null;
  change_1m_pct: number | null;
  change_5m_pct: number | null;
  volume: number;
  rvol: number;
  ticker?: string;
  snapshot_time: number;
}

export interface CatalystAlert {
  id: string;
  ticker: string;
  title: string;
  url: string;
  published: string;
  metrics: CatalystMetrics;
  triggeredAt: number;
  dismissed: boolean;
  reason: string; // Ej: "Price +4.2% in 5min"
}

export interface AlertCriteria {
  // Movimiento de precio
  priceChange: {
    enabled: boolean;
    minPercent: number;  // Ej: 3 = 3%
    timeWindow: 1 | 5;   // 1 o 5 minutos
  };
  
  // Volumen
  volumeSpike: {
    enabled: boolean;
    minMultiplier: number;  // Ej: 3 = 3x promedio
  };
  
  // RVOL
  rvol: {
    enabled: boolean;
    minValue: number;  // Ej: 2.5
  };
  
  // Filtros adicionales
  filters: {
    onlyScanner: boolean;     // Solo tickers en scanner
    onlyWatchlist: boolean;   // Solo tickers en watchlist
    maxMarketCap: number | null;  // Ej: 1000000000 (1B)
  };
  
  // Notificaciones
  notifications: {
    popup: boolean;
    sound: boolean;
    squawk: boolean;
  };
}

interface CatalystAlertsState {
  // Estado global
  enabled: boolean;
  
  // Criterios del usuario
  criteria: AlertCriteria;
  
  // Alertas activas
  alerts: CatalystAlert[];
  
  // Acciones
  setEnabled: (enabled: boolean) => void;
  setCriteria: (criteria: Partial<AlertCriteria>) => void;
  addAlert: (alert: CatalystAlert) => void;
  dismissAlert: (id: string) => void;
  clearAlerts: () => void;
  clearDismissed: () => void;
}

// ============================================================================
// Default Values
// ============================================================================

const defaultCriteria: AlertCriteria = {
  priceChange: {
    enabled: true,
    minPercent: 3,
    timeWindow: 5,
  },
  volumeSpike: {
    enabled: false,
    minMultiplier: 3,
  },
  rvol: {
    enabled: false,
    minValue: 2.5,
  },
  filters: {
    onlyScanner: false,
    onlyWatchlist: false,
    maxMarketCap: null,
  },
  notifications: {
    popup: true,
    sound: true,
    squawk: false,
  },
};

// ============================================================================
// Store
// ============================================================================

export const useCatalystAlertsStore = create<CatalystAlertsState>()(
  persist(
    (set, get) => ({
      enabled: false,
      criteria: defaultCriteria,
      alerts: [],
      
      setEnabled: (enabled) => set({ enabled }),
      
      setCriteria: (newCriteria) => set((state) => ({
        criteria: {
          ...state.criteria,
          ...newCriteria,
          priceChange: {
            ...state.criteria.priceChange,
            ...(newCriteria.priceChange || {}),
          },
          volumeSpike: {
            ...state.criteria.volumeSpike,
            ...(newCriteria.volumeSpike || {}),
          },
          rvol: {
            ...state.criteria.rvol,
            ...(newCriteria.rvol || {}),
          },
          filters: {
            ...state.criteria.filters,
            ...(newCriteria.filters || {}),
          },
          notifications: {
            ...state.criteria.notifications,
            ...(newCriteria.notifications || {}),
          },
        },
      })),
      
      addAlert: (alert) => set((state) => {
        // Evitar duplicados (mismo ticker + misma noticia)
        const exists = state.alerts.some(
          (a) => a.ticker === alert.ticker && a.title === alert.title
        );
        if (exists) return state;
        
        // Máximo 50 alertas, eliminar las más antiguas
        const newAlerts = [alert, ...state.alerts].slice(0, 50);
        return { alerts: newAlerts };
      }),
      
      dismissAlert: (id) => set((state) => ({
        alerts: state.alerts.map((a) =>
          a.id === id ? { ...a, dismissed: true } : a
        ),
      })),
      
      clearAlerts: () => set({ alerts: [] }),
      
      clearDismissed: () => set((state) => ({
        alerts: state.alerts.filter((a) => !a.dismissed),
      })),
    }),
    {
      name: 'catalyst-alerts-storage',
      partialize: (state) => ({
        enabled: state.enabled,
        criteria: state.criteria,
        // No persistimos alertas (son transitorias)
      }),
    }
  )
);

// ============================================================================
// Selector Helpers
// ============================================================================

export const useActiveAlerts = () =>
  useCatalystAlertsStore((state) => state.alerts.filter((a) => !a.dismissed));

export const useAlertCount = () =>
  useCatalystAlertsStore((state) => state.alerts.filter((a) => !a.dismissed).length);

export const useAlertsEnabled = () =>
  useCatalystAlertsStore((state) => state.enabled);

